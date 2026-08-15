-- =====================================================================
-- Stage A — 층별 화면에 실거래 "사실"을 표시한다 (2026-08-15, 결정 0012)
-- =====================================================================
-- 결정 0012 는 시세 표시를 두 단계로 갈랐다. 여기서 만드는 것은 **Stage A** 뿐이고,
-- Stage A 에는 **추정이 한 톨도 없다** — 신고된 거래를 그대로 보여주거나, 그것을
-- 세어서 중앙값·사분위를 내는 것뿐이다. 그래서 "적정가격" 규칙(절대 규칙 2) 리스크가 0 이다.
-- (추정 밴드 = Stage B 는 백테스트 성적표가 나온 뒤에 따로 결재한다.)
--
-- 두 가지를 만든다:
--   ① list_parcel_transactions(pnu)  — 이 필지의 실거래 이력 (있는 건물만)
--   ② mv_sigungu_tx_stats + get_sigungu_tx_stats(sigungu) — 구×층대 단가 분포 (항상)
--
-- ## 왜 ① 만으로는 화면이 텅 비나 (그래서 ② 가 있다)
--
-- 실측(2026-08-15): 화면 건물 필지 중 **자기 실거래가 있는 곳은 서울 1.8% · 대전 1.4%**
-- 뿐이다. ① 만 붙이면 98% 건물에서 아무것도 안 보인다. ② 는 그 건물이 속한 구의
-- 층대별 단가 분포라 **항상** 보여줄 수 있다.
--
-- ## 왜 구(시군구) 단위인가 — 법정동이 아니라
--
-- 실거래의 동 이름은 **문자**(emd_nm)이고 건물의 법정동은 **코드**다. 두 체계를 이름으로
-- 대조하면 조용히 어긋난다. 구는 pnu 앞 5자리로 확정되므로 어긋날 자리가 없다.
-- 법정동 단위는 이름↔코드 매핑을 검증한 뒤의 경로로만 남긴다(결정 0012 §4).
--
-- ## 왜 집합(구분소유) 거래만 세나
--
-- 통건물(일반) 거래는 지번이 **100% 마스킹**돼(알려진한계) 필지에 못 붙고, 무엇보다
-- 건물 한 채 값이라 ㎡당 단가의 성격이 호실 거래와 다르다. 섞으면 분포가 오염된다.

-- =====================================================================
-- ① 이 필지의 실거래 이력
-- =====================================================================
-- ## 왜 202401 부터인가
--
-- 실거래 지번은 **2024-01 부터만 공개**된다(그 전은 100% `'6**'` 마스킹 — 알려진한계).
-- 즉 2023-12 이전에 pnu 가 붙어 있다면 그건 조립이 아니라 사고다. 구간을 명시해
-- "이 목록이 무엇의 전부인지"를 함수가 스스로 말하게 한다.
--
-- ## 왜 100 행에서 끊나
--
-- 한 필지에 거래가 **852건**인 곳이 실제로 있다(라이브 실측 2026-08-15, 대단지 집합상가).
-- 화면은 이력을 훑어보는 곳이지 원장부가 아니다. 상한이 없으면 그 한 건물에서 화면과
-- 응답이 통째로 무너진다.
--
-- ## 왜 본문에서 함수명으로 한정하나
--
-- 파라미터 이름 `pnu` 가 `transaction.pnu` 컬럼과 겹친다. 그냥 `pnu` 라고 쓰면
-- PostgreSQL 이 컬럼을 우선 집어 `where t.pnu = t.pnu`(= 전 국토 거래)가 된다.
-- list_building_districts 가 `bld_id` 로 똑같이 밟을 뻔했던 함정이다.
create or replace function list_parcel_transactions(pnu text)
returns table (
  floor_no     smallint,
  contract_ym  text,
  contract_day smallint,
  bld_area_m2  numeric,
  price_won    bigint,
  unit_price   numeric,
  tx_type      text
)
language sql
stable
security definer
set search_path = public
as $$
  select t.floor_no,
         t.contract_ym::text,
         t.contract_day,
         t.bld_area_m2,
         t.price_won,
         t.unit_price,
         t.tx_type
  from transaction t
  where t.pnu = list_parcel_transactions.pnu
    and t.contract_ym >= '202401'
  -- 계약일이 없는 행(구 자료)이 최신인 척 위로 올라오면 안 된다 → nulls last.
  -- 마지막 tx_id 는 같은 날 여러 건일 때 순서가 호출마다 흔들리지 않게 하는 못이다.
  order by t.contract_ym desc, t.contract_day desc nulls last, t.tx_id
  limit 100;
$$;

comment on function list_parcel_transactions(text) is
  'Stage A(결정 0012) 이 필지의 실거래 이력 — 추정이 아니라 신고된 거래 그대로. '
  '지번이 공개된 구간(202401 이후)만 나온다: 그 전은 지번이 100% 마스킹돼 필지에 붙지 않는다. '
  '최신순 100행 상한(한 필지 852건인 곳이 실재한다). 없는 pnu 는 빈 결과(에러가 아니다). '
  'security definer — transaction 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 층·계약시점·면적·금액·단가·거래유형뿐(상호명·개인정보 없음)';

-- =====================================================================
-- ② 구 × 층대 실거래 단가 분포 (사전계산)
-- =====================================================================
-- ## 왜 사전계산(물질화뷰)인가
--
-- 건물 하나를 열 때마다 4만 건을 정렬해 백분위를 내는 것은 낭비다. 구×층대는
-- 많아야 수백 행이고 자료가 늘 때만 바뀐다 — CLAUDE.md 성능 원칙(상권=사전계산)과 같은 결.
--
-- ## 창(窓)은 "갱신 시점 기준 24개월"이다
--
-- 물질화뷰는 갱신할 때 계산돼 그대로 굳는다. 그러니 여기서 잰 창의 시작점을
-- `window_from` 칸에 **함께 굳혀 둔다.** 화면이 "최근 24개월"이라고만 적으면, 오래
-- 갱신을 안 한 날 그 문구만 조용히 거짓말이 된다 — 실제로 어느 달부터인지를 자료가 말하게 한다.
-- 시각은 KST 로 고정한다(now() 는 UTC 라 월말·월초에 한 달이 어긋난다 — timezone 룰).
--
-- ## 왜 unit_price 가 있는 행만 세나
--
-- `n` 은 화면에 "표본 N건"으로 나가는 숫자이고, 중앙값·사분위는 unit_price 로 낸다.
-- 면적이 없어 단가가 안 나오는 행을 n 에 세면 **근거로 쓴 것보다 표본이 많다고 말하게 된다**.
-- 판정 로직이 세는 것과 같은 방법으로 근거를 재라 — 2026-08-13 에 배운 것.
--
-- ⚠️ 층대 '지하'는 지금 **항상 0 건**이다. 2017년부터 국토부가 상업업무용 실거래의
--    `floor` 를 빈 값으로 준다(알려진한계 — 우리 파싱 문제가 아니다). 그래서 지하는
--    '층미상'에 흡수돼 있다. 칸을 지우지 않는 이유는, 자료가 돌아오는 날 화면이
--    저절로 따라오게 하기 위해서다(칸을 지우면 그날 코드를 고쳐야 한다).
-- ⚠️ 옥탑(99)은 '3층이상'에 들어간다. 결정 0012 의 층대 정의가 ">=3" 이라서다.
create materialized view if not exists mv_sigungu_tx_stats as
with win as (
  select to_char((now() at time zone 'Asia/Seoul') - interval '24 months', 'YYYYMM') as from_ym
)
select
  t.sigungu_code,
  case
    when t.floor_no is null then '층미상'
    when t.floor_no < 0    then '지하'
    when t.floor_no = 1    then '1층'
    when t.floor_no = 2    then '2층'
    else                        '3층이상'
  end                                                              as floor_band,
  min(w.from_ym)                                                   as window_from,
  count(*)::int                                                    as n,
  percentile_cont(0.5)  within group (order by t.unit_price)       as median_unit_price,
  percentile_cont(0.25) within group (order by t.unit_price)       as p25_unit_price,
  percentile_cont(0.75) within group (order by t.unit_price)       as p75_unit_price
from transaction t
cross join win w
where t.tx_type = '집합'
  and t.unit_price is not null
  and t.contract_ym >= w.from_ym
group by t.sigungu_code, 2;

comment on materialized view mv_sigungu_tx_stats is
  'Stage A(결정 0012) 구×층대 실거래 단가 분포 — 집합(구분소유) 거래만, 갱신 시점 기준 24개월. '
  'window_from 은 그 창의 시작 달을 굳혀 둔 것이다(화면이 "최근 24개월"만 적으면 갱신을 미룬 날 '
  '그 문구가 조용히 거짓말이 된다). n 은 단가를 낼 수 있었던 행 수 = 중앙값의 실제 근거 수다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 로 갱신할 것. '
  '⛔ anon 에게 열지 않는다 — 화면은 get_sigungu_tx_stats() 로만 읽는다.';

-- `concurrently` 갱신의 전제 조건이다(없으면 갱신 중 이 표를 읽는 화면이 통째로 잠긴다).
create unique index if not exists idx_msts_key on mv_sigungu_tx_stats (sigungu_code, floor_band);

analyze mv_sigungu_tx_stats;

-- ── 래퍼 함수 — 층대 순서를 서버가 못 박는다 ────────────────────────────────
-- ## 왜 값 목록(values)을 왼쪽에 두고 left join 하나
--
-- 표본이 0 인 층대는 물질화뷰에 **행 자체가 없다.** 그대로 내보내면 화면에서 그 층대가
-- 통째로 사라져 "지하는 아예 안 판다"처럼 읽힌다. 다섯 칸을 항상 같은 순서로 내보내고
-- 비어 있으면 n=0 으로 말하는 것이, 없는 것을 없다고 말하는 유일한 방법이다.
--
-- ## 왜 구 이름을 서버가 주나
--
-- 화면에 지역명을 글자로 박으면 자료가 늘거나 이름이 바뀌는 날 화면만 낡는다
-- (list_open_sigungu·list_building_districts 와 같은 원칙). 이름의 출처는 한 곳뿐이다.
create or replace function get_sigungu_tx_stats(sigungu text)
returns table (
  floor_band        text,
  n                 int,
  median_unit_price numeric,
  p25_unit_price    numeric,
  p75_unit_price    numeric,
  window_from       text,
  sigungu_nm        text
)
language sql
stable
security definer
set search_path = public
as $$
  select b.band,
         coalesce(s.n, 0),
         s.median_unit_price,
         s.p25_unit_price,
         s.p75_unit_price,
         -- 창은 갱신할 때 한 번 정해져 표 전체가 같은 값을 가진다. 그 구에 거래가
         -- 한 건도 없어도 "언제부터 세었는지"는 말할 수 있어야 하므로 전체에서 읽는다.
         (select max(m.window_from) from mv_sigungu_tx_stats m),
         (select o.sigungu_nm from mv_open_sigungu o
           where o.sigungu_code = get_sigungu_tx_stats.sigungu)
  from (values ('지하', 1), ('1층', 2), ('2층', 3), ('3층이상', 4), ('층미상', 5)) as b(band, ord)
  left join mv_sigungu_tx_stats s
    on s.sigungu_code = get_sigungu_tx_stats.sigungu
   and s.floor_band  = b.band
  order by b.ord;
$$;

comment on function get_sigungu_tx_stats(text) is
  'Stage A(결정 0012) 구 실거래 단가 분포 — 층대 5칸을 **항상 같은 순서로** 돌려준다. '
  '표본이 없는 층대는 물질화뷰에 행이 없으므로 여기서 n=0 으로 채운다(칸이 사라지면 '
  '"그 층은 아예 안 판다"처럼 읽힌다). 화면은 n<5 면 수치를 감추고 "표본 부족"만 적는다. '
  'window_from 은 집계한 창의 시작 달, sigungu_nm 은 구 이름(화면에 지역명을 박지 않기 위해 '
  '서버가 준다). security definer — 물질화뷰가 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다';

-- =====================================================================
-- 노출면 — 함수 둘만 연다
-- =====================================================================
-- ⛔ 물질화뷰는 열지 않는다. Supabase 는 새로 만드는 표·물질화뷰를 **자동으로** anon 에
--    열어 왔다(2026-08-13 실제 사고: `GET /rest/v1/mv_search_parcel` 이 200 이었다).
--    2026-08-13f 가 기본 권한을 바꿔 뒀지만, 그 명령이 닿지 않는 경로(대시보드가 만든
--    것 등)가 남아 있으므로 **만든 자리에서 한 번 더 닫는다.** 라이브 확인은
--    `python scripts/post_load.py --check` 가 한다(정적 검사로는 못 잡는 종류다).
revoke all on mv_sigungu_tx_stats from public, anon, authenticated;

-- 화면이 부르는 함수만 명시적으로 연다(2026-08-13g 이후 함수는 기본으로 닫혀 있다).
grant execute on function list_parcel_transactions(text) to anon, authenticated;
grant execute on function get_sigungu_tx_stats(text) to anon, authenticated;
