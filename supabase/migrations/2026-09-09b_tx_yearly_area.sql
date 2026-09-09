-- =====================================================================
-- 그 해 단가의 근거가 된 거래 **한 건의 크기** — median_area_m2 (2026-09-09b)
-- =====================================================================
-- 결정 0027(동네 매매 단가 흐름) 카드에 **사실 한 칸을 더한다.** 숫자를 빼거나 거르는
-- 것이 아니다.
--
-- 무엇이 보이지 않았나 (라이브 실측)
-- ----------------------------------
-- 강남구의 ㎡당 중앙값이 두 해만 앞뒤 해(600~800만)의 2~3배로 튄다(1,706만·2,117만).
-- 원인은 시세가 오른 것이 아니라 역삼동 한 건물의 **4~5㎡ 구획 1,086건**이 그 두 해에
-- 무더기로 거래된 것이었다. 작은 구획일수록 ㎡당 단가가 높으니, 그 무더기가 그 해의
-- 가운데값을 통째로 끌어올린 것이다.
--
-- 그 두 해의 '거래 한 건 면적 중앙값'은 16.4㎡·18.3㎡, 다른 해는 40~46㎡ — 그러니
-- **면적 중앙값 한 칸만 나란히 적으면** 기준선(10㎡ 같은 선)을 하나도 안 긋고도 그 사실이
-- 사람 눈에 보인다. 줄 꼬리에 이미 있는 '층 미상 21%'와 같은 방식이다.
--
-- ⛔ 거르지 않는다
-- ----------------
-- 초소형 구획을 빼고 다시 재는 것은 **우리가 선을 긋는 일**이고(몇 ㎡부터 뺄 것인가?),
-- 그러면 이 카드가 '사실 집계'에서 '보정값'으로 성격이 바뀐다. 결정 0027 §1 과
-- 2026-09-05b(허가 실효 한 줄)의 판단을 그대로 따른다 — 숫자는 그대로 두고 한 칸을 더한다.
--
-- ⛔ 단가와 **같은 모집단**에서 잰다
-- ---------------------------------
-- filter 를 median/p25/p75 와 글자 그대로 같게 둔다(`where t.unit_price is not null`).
-- 다른 조건에서 재면 두 숫자가 서로 다른 거래를 말하게 되어, 나란히 적는 뜻이 사라진다.
-- ⓘ `unit_price` 는 `bld_area_m2 > 0` 일 때만 생기는 생성 컬럼이라, 이 filter 하나로
--   면적이 0·빈 행은 자연히 빠진다.
--
-- ⛔ 물질화뷰는 칸을 나중에 못 붙인다
-- ----------------------------------
-- `alter materialized view … add column` 이라는 것이 없다. 그리고 09-09a 의 `create
-- materialized view **if not exists**` 를 다시 돌려도 **아무 일도 안 한다**(에러 0 ·
-- 화면만 옛 셈을 계속 말한다). 그래서 **떨어뜨리고 다시 만든다** — 09-09a 머리말이
-- 미리 적어 둔 그 방법이다.
--
-- ⛔ 반환 표에 칸을 더하므로 `create or replace` 로는 못 고친다
-- -------------------------------------------------------------
-- PostgreSQL 이 replace 를 거부한다("cannot change return type of existing function").
-- 그래서 먼저 떨어뜨린다 — **부르는 쪽(api)을 먼저**, 그다음 public
-- (2026-09-05b 와 같은 순서다. 문자열 본문 함수는 의존을 기록하지 않아 막히지는 않지만,
--  허공을 가리키는 순간 자체를 안 만든다).
--
-- ⛔ 다시 만든 뷰는 그 자리에서 다시 닫는다
-- ----------------------------------------
-- Supabase 는 새로 만드는 표·물질화뷰를 anon 에게 자동으로 연다(pg_default_acl). 09-09a
-- 의 revoke 는 **그때 만든 그 객체**에만 걸렸으므로, 다시 만든 뷰는 다시 열려 있을 수 있다
-- — 형제 뷰들과 글자 그대로 같은 revoke 를 여기서 한 번 더 둔다.
--
-- 실행법
-- ------
--   python scripts/dbx.py -f supabase/migrations/2026-09-09b_tx_yearly_area.sql
--
-- 적용한 사람이 보게 되는 것
-- --------------------------
--   · DROP FUNCTION ×2 · DROP MATERIALIZED VIEW · CREATE MATERIALIZED VIEW · COMMENT
--     · CREATE INDEX · ANALYZE · REVOKE · CREATE FUNCTION ×2 · COMMENT · REVOKE ×2
--     · GRANT · NOTIFY
--   · 뷰를 다시 만드는 데 시간이 좀 걸린다(전 기간 거래를 다시 훑는다 — 32만 행).
--   · 화면 줄 꼬리가 "1,550건 · 층 미상 10%" → "… · 한 건 면적 중앙값 40㎡" 가 된다.
--   · `python scripts/post_load.py --check` 는 그대로 exit 0 이어야 한다. 공개 호출
--     목록은 하나도 안 늘었다 — 같은 함수에 칸만 하나 더한 것이다.
--   · 적용 뒤 `python scripts/post_load.py` 는 평소대로 돌린다(갱신 목록은 안 바뀐다).
--
-- 되돌리기: 2026-09-09a 를 그대로 다시 돌린다 — 단 그 파일의 `create materialized view
-- **if not exists**` 는 이미 있는 뷰에 아무 일도 안 하므로, 먼저 `drop materialized view
-- mv_sigungu_tx_yearly;` 를 하고 돌려야 한다.

-- ⛔ 부르는 쪽(api)을 먼저 떨어뜨린다 — 막혀서가 아니라, 허공을 가리키는 순간을 안 만들려고.
drop function if exists api.get_sigungu_tx_yearly(text);
drop function if exists public.get_sigungu_tx_yearly(text);

-- ⛔ 칸을 더하려면 다시 만드는 수밖에 없다(위 머리말 참조). 함수를 먼저 떨어뜨렸으므로
--    이 순서에서 뷰를 지우는 것을 막을 것이 없다.
drop materialized view if exists mv_sigungu_tx_yearly;

create materialized view mv_sigungu_tx_yearly as
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
  -- 그 해 단가의 **근거가 된 거래 한 건**이 얼마나 큰 물건이었나(2026-09-09b).
  -- ⛔ filter 를 위 셋과 **똑같이** 둔다 — 다른 모집단에서 재면 두 숫자가 서로 다른 거래를
  --    말하게 된다. `unit_price` 는 `bld_area_m2 > 0` 일 때만 생기는 생성 컬럼이라, 이
  --    filter 하나로 면적이 0·빈 행은 자연히 빠진다(면적 조건을 따로 적을 이유가 없다).
  percentile_cont(0.5)  within group (order by t.bld_area_m2)
    filter (where t.unit_price is not null)                                     as median_area_m2,
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
  '2026-09-09b: median_area_m2 = 그 해 단가의 근거가 된 거래 **한 건**의 건물면적 중앙값(㎡) — '
  '단가와 같은 모집단에서 잰다. 다른 해보다 유난히 작으면 초소형 구획이 무더기로 거래된 해다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 로 갱신할 것. '
  '⛔ anon 에게 열지 않는다 — 화면은 api.get_sigungu_tx_yearly() 로만 읽는다.';

-- `concurrently` 갱신의 전제 조건(없으면 갱신 중 이 표를 읽는 화면이 통째로 잠긴다).
-- ⓘ 뷰를 떨어뜨릴 때 인덱스도 함께 사라졌으므로 여기서 다시 만든다.
create unique index if not exists idx_msty_key on mv_sigungu_tx_yearly (sigungu_code, yr);

analyze mv_sigungu_tx_yearly;

-- ⛔ 다시 만든 뷰는 다시 열려 있을 수 있다(pg_default_acl) — 만든 자리에서 다시 닫는다.
--    화면은 함수로만 읽는다.
revoke all on mv_sigungu_tx_yearly from public, anon, authenticated;

create or replace function get_sigungu_tx_yearly(sigungu text)
returns table (
  yr                text,
  n                 int,
  n_all             int,
  median_unit_price numeric,
  p25_unit_price    numeric,
  p75_unit_price    numeric,
  median_area_m2    numeric,
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
         m.median_area_m2, m.floor_missing, m.ym_cnt, m.first_ym, m.last_ym,
         (select o.sigungu_nm from mv_open_sigungu o
           where o.sigungu_code = get_sigungu_tx_yearly.sigungu)
  from mv_sigungu_tx_yearly m
  where m.sigungu_code = get_sigungu_tx_yearly.sigungu
  order by m.yr;
$$;

comment on function get_sigungu_tx_yearly(text) is
  '결정 0027 구 실거래 단가의 연도별 흐름 — 집합 거래만, 연도 오름차순, 자료가 있는 해만. '
  '화면은 n<5 면 수치를 감추고 "표본 부족"만 적는다(절대 규칙 3). security definer — 물질화뷰가 '
  'anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. sigungu_nm 은 구 이름(화면에 지역명을 박지 않기 위해). '
  '2026-09-09b: median_area_m2 = 그 해 단가의 근거가 된 거래 한 건의 건물면적 중앙값(㎡). '
  '⛔ 숫자를 거르는 칸이 아니다 — 초소형 구획이 무더기로 거래된 해를 사람이 알아보게 하는 사실 한 칸이다.';

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
  median_area_m2    numeric,
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

-- 칸이 하나 늘었으므로 스키마 캐시를 다시 읽게 한다. 안 알리면 화면이 예전 칸 구성으로
-- 부르다 404(PGRST202) 를 맞는다 — DB 에는 멀쩡히 있는데 화면만 안 되는, 찾기 어려운 고장이다.
notify pgrst, 'reload schema';
