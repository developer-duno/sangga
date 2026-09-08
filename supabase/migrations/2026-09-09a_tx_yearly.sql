-- =====================================================================
-- 동네 매매 단가 흐름 — 구×연도 실거래 단가 요약 (2026-09-09a)
-- =====================================================================
-- 로드맵 Wave 5 『동네 20년 단가 흐름』 · 결정 0027. 표는 하나도 안 만든다 —
-- 이미 있는 `transaction` 을 **해마다 묶어 보는 길**을 뚫는다.
--
-- 왜 필요한가
-- -----------
-- 화면이 지금 실거래로 말할 수 있는 것은 두 가지뿐이다: 이 필지의 개별 기록
-- (`list_parcel_transactions`)과 구의 **최근 24개월** 층대별 분포
-- (`mv_sigungu_tx_stats` · 결정 0012). 둘 다 "지금 얼마쯤인가"에 답하지 "그동안 어떻게
-- 움직였나"에는 답하지 못한다. 그런데 2024-01 이전 거래는 지번이 가려져 PNU 가 0 이라
-- 건물에는 못 붙이고, 구 단위로는 붙일 수 있다 — 그래서 **지역 카드로만** 낸다
-- (로드맵 원문의 규칙이고, 결정 0027 §1 이 그대로 못 박았다).
--
-- 왜 물질화뷰인가
-- ---------------
-- percentile 을 매 요청마다 20년치 위에서 돌리면 느리고, 자료는 적재할 때만 바뀐다
-- (형제 `mv_sigungu_tx_stats` 와 같은 이유). 갱신은 `python scripts/post_load.py`
-- 한 곳 — 그 목록(REFRESH_MVS)에서 빠지면 화면만 옛 해를 계속 말한다(에러 0).
--
-- ⛔ 나가는 것은 **구×연도 요약 한 줄씩**이다
-- -------------------------------------------
-- 그 해의 거래 수·단가 중앙값·가운데 절반·층 미상 수, 그리고 그 해가 얼마나 온전한지
-- (자료가 있는 달 수와 첫/끝 달). **개별 거래(필지·층·단가)는 이 뷰에 아예 없다** —
-- 그건 이미 필지 단위 함수가 따로 하는 일이고, 여기로 새어 나가면 안 된다.
--
-- ⚠️ n 과 n_all 을 둘 다 두는 까닭
-- --------------------------------
-- n 은 단가(unit_price)가 있어 **중앙값의 근거가 된** 행 수, n_all 은 그 해 집합 거래
-- 전부(= 층 미상 비율의 분모)다. 하나만 두면 "근거 수"와 "그 해 거래 수"가 섞여, 몇
-- 건으로 낸 가운데값을 많은 표본처럼 말하게 된다(절대 규칙 3).
--
-- ⚠️ ym_cnt·first_ym·last_ym 을 두는 까닭
-- ---------------------------------------
-- 자료가 해의 일부뿐인 해(첫해·올해)를 화면이 "(9~12월분)"이라 적을 수 있게 하려는
-- 것이다. 안 적으면 그 해가 유난히 한산했던 것처럼 보인다.
--
-- ⚠️ 24개월 창은 건드리지 않는다
-- ------------------------------
-- `mv_sigungu_tx_stats`·참고 시세 게이트·성적표는 이 파일이 손대지 않는다. 백필로 들어온
-- 거래는 전부 그 창(최근 24개월) 밖이라 저쪽 숫자는 그대로다.
--
-- ⚠️ 새 함수는 이제 닫힌 채로 태어난다 (2026-09-01b)
-- --------------------------------------------------
-- 전역 기본권한에서 PUBLIC EXECUTE 를 빼 뒀으므로, 화면이 부를 함수는 **명시로** 열어야
-- 한다. 아래 `grant execute on function api.get_sigungu_tx_yearly(text) to anon,
-- authenticated;` 한 줄이 그것이다 — 빼면 화면에서 `permission denied for function` 이 난다.
--
-- 적용
-- ----
-- Supabase SQL Editor 에 통째로 붙여 실행한다(기존 표 변경 0 · 되돌리려면 두 함수와
-- 물질화뷰를 drop). 실행 뒤 `python scripts/post_load.py` 로 요약표를 굽고,
-- `python scripts/post_load.py --check` 로 공개 롤 권한이 그대로인지 본다.

-- ⚠️ `if not exists` 는 **이미 있으면 아무 일도 안 한다** — 아래 정의를 고친 뒤 이 파일을
--    다시 붙여 넣어도 라이브의 옛 뷰가 그대로 남는다(에러 0 · 화면만 옛 셈을 계속 말한다).
--    뷰 정의를 바꿀 때는 새 마이그레이션에서 `drop materialized view …;` 뒤에 `create …` 로.
create materialized view if not exists mv_sigungu_tx_yearly as
select
  t.sigungu_code,
  substr(t.contract_ym, 1, 4)                                                   as yr,
  count(*)::int                                                                 as n_all,
  count(*) filter (where t.unit_price is not null)::int                         as n,
  percentile_cont(0.5)  within group (order by t.unit_price)
    filter (where t.unit_price is not null)                                     as median_unit_price,
  percentile_cont(0.25) within group (order by t.unit_price)
    filter (where t.unit_price is not null)                                     as p25_unit_price,
  percentile_cont(0.75) within group (order by t.unit_price)
    filter (where t.unit_price is not null)                                     as p75_unit_price,
  count(*) filter (where t.floor_no is null)::int                               as floor_missing,
  count(distinct t.contract_ym)::int                                            as ym_cnt,
  min(t.contract_ym)                                                            as first_ym,
  max(t.contract_ym)                                                            as last_ym
from transaction t
where t.tx_type = '집합'
group by t.sigungu_code, substr(t.contract_ym, 1, 4);

comment on materialized view mv_sigungu_tx_yearly is
  '결정 0027 구×연도 집합(구분소유) 실거래 단가 요약 — 동네 매매 단가 흐름 카드의 재료. '
  'n 은 단가가 있어 중앙값 근거가 된 행 수, n_all 은 그 해 집합 거래 전부(층 미상 비율 분모), '
  'ym_cnt·first_ym·last_ym 은 자료가 해의 일부뿐인지 화면이 적기 위한 값. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 로 갱신할 것. '
  '⛔ anon 에게 열지 않는다 — 화면은 api.get_sigungu_tx_yearly() 로만 읽는다.';

-- `concurrently` 갱신의 전제 조건(없으면 갱신 중 이 표를 읽는 화면이 통째로 잠긴다).
create unique index if not exists idx_msty_key on mv_sigungu_tx_yearly (sigungu_code, yr);

analyze mv_sigungu_tx_yearly;

-- ⛔ Supabase 는 새로 만드는 표·물질화뷰를 anon 에게 자동으로 연다(pg_default_acl). 기본
--    권한을 닫아 뒀어도(2026-08-13f·g) **만든 자리에서 한 번 더** 닫는다 — 그 기본값은
--    "그것을 실행한 롤이 만드는 것"에만 걸리기 때문이다. 화면은 함수로만 읽는다.
revoke all on mv_sigungu_tx_yearly from public, anon, authenticated;

-- 연도 오름차순. 구 이름도 서버가 준다(화면에 지역명을 박지 않는다 — get_sigungu_tx_stats 와 같은 원칙).
-- 표본이 없는 해는 행이 없다 — 이 카드는 "이어진 흐름"이 아니라 "자료가 있는 해의 사실"이라 빈 해를 0 으로 채우지 않는다
-- (채우면 "그 해엔 거래가 없었다"로 읽히는데 실제로는 자료가 없는 것일 수 있다).
create or replace function get_sigungu_tx_yearly(sigungu text)
returns table (
  yr                text,
  n                 int,
  n_all             int,
  median_unit_price numeric,
  p25_unit_price    numeric,
  p75_unit_price    numeric,
  floor_missing     int,
  ym_cnt            int,
  first_ym          text,
  last_ym           text,
  sigungu_nm        text
)
language sql
stable
security definer
set search_path = public
as $$
  select m.yr, m.n, m.n_all, m.median_unit_price, m.p25_unit_price, m.p75_unit_price,
         m.floor_missing, m.ym_cnt, m.first_ym, m.last_ym,
         (select o.sigungu_nm from mv_open_sigungu o
           where o.sigungu_code = get_sigungu_tx_yearly.sigungu)
  from mv_sigungu_tx_yearly m
  where m.sigungu_code = get_sigungu_tx_yearly.sigungu
  order by m.yr;
$$;

comment on function get_sigungu_tx_yearly(text) is
  '결정 0027 구 실거래 단가의 연도별 흐름 — 집합 거래만, 연도 오름차순, 자료가 있는 해만. '
  '화면은 n<5 면 수치를 감추고 "표본 부족"만 적는다(절대 규칙 3). security definer — 물질화뷰가 '
  'anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. sigungu_nm 은 구 이름(화면에 지역명을 박지 않기 위해).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_sigungu_tx_yearly(text) from public, anon, authenticated;

-- api 쌍둥이 — 화면이 부르는 문. (public 원본은 닫힌 채, 이 문만 anon 에게 연다 — 2026-09-01b 규칙)
create or replace function api.get_sigungu_tx_yearly(sigungu text)
returns table (
  yr                text,
  n                 int,
  n_all             int,
  median_unit_price numeric,
  p25_unit_price    numeric,
  p75_unit_price    numeric,
  floor_missing     int,
  ym_cnt            int,
  first_ym          text,
  last_ym           text,
  sigungu_nm        text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.get_sigungu_tx_yearly(sigungu) $$;

revoke all on function api.get_sigungu_tx_yearly(text) from public, anon, authenticated;
grant execute on function api.get_sigungu_tx_yearly(text) to anon, authenticated;

-- ⛔ public.get_sigungu_tx_yearly 는 끝까지 닫아 둔다 — 통과 함수가 security definer 라
--    소유자 권한으로 부르므로 anon 에게 열 필요가 없다.
-- ⛔ 물질화뷰 mv_sigungu_tx_yearly 자체도 열지 않는다(화면은 함수로만 읽는다).

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';
