-- =====================================================================
-- 마이그레이션 2026-09-27c — 첫 방문(찬 캐시) 속도: 층별 화면 함수 두 곳 (로드맵 속도 P6)
-- =====================================================================
-- **(라이브 적용 예정)**
--
-- 실행법: `python scripts/dbx.py -f supabase/migrations/2026-09-27c_p6_cold_cache.sql`
--   한 트랜잭션(begin … commit)이라 중간에 끊기면 통째로 되돌아간다. 새 요약표는 수천 행이라
--   굽는 데 수 초다. 표를 잠그는 것은 없다(새 표를 만들고 함수 본문만 바꾼다).
--
-- 무엇을 바꾸나 (2026-09-27 라이브 실측 — 근거는 pg_temp 시제품 대조)
--   ① list_parcel_transactions — 본문 비교 `t.pnu = list_parcel_transactions.pnu` 가 char(19)
--      칸을 text 로 캐스트해 idx_tx_pnu 를 못 탔다. 거래 0건 필지에서 PREPARE 실측:
--        text 판 = idx_tx_pnu10_ym 으로 2024년 이후 거래 28,568행을 훑어 1,876쪽 · 25.8ms
--        char(19) 판 = idx_tx_pnu Index Scan Backward · 2쪽 · 0.049ms
--      → `list_parcel_transactions.pnu::char(19)` 로 견준다. 서명·반환·정렬·상한·202401 은 그대로.
--   ② 새 요약표 mv_tx_parcel_geog — 거래가 한 건이라도 있고 좌표가 있는 필지만(4,384곳).
--      유일 색인(pnu — refresh concurrently 전제) + GiST(geog). anon 에게 닫는다.
--      post_load.py 의 REFRESH_MVS 에 들어간다.
--   ③ list_price_bands — 반경 100m·500m 이웃 배열을 만드는 한 문장만 parcel → 새 요약표.
--      이웃 배열은 L4·L5 의 `t.pnu = any(…)` 에만 쓰여 거래 없는 필지를 빼도 결과가 같다.
--      게이트·층 루프·L2/L4/L5/L6·최소 표본·반환은 한 글자도 안 바꿨다.
--
-- 증명 (pg_temp 에 새 표·새 함수 두 개를 복제해 라이브 public.* 옛 함수와 같은 문장 안에서 비교)
--   결과 md5 대조 · 만진 쪽 수 비교 — 수치는 PR 본문과 PROGRESS 에 적는다.
--
-- 되돌리기 (두 함수의 옛 본문을 다시 박고 표를 지운다 — 권한은 create or replace 가 유지한다):
--   2026-09-27c 이전 정본(커밋 242dc03)의 `list_parcel_transactions`·`list_price_bands` 정의를
--   `create or replace` 로 다시 실행한 **뒤에** `drop materialized view if exists mv_tx_parcel_geog;`
--   (순서가 반대면 새 list_price_bands 가 없는 표를 불러 참고 시세 카드가 통째로 실패한다)
--   그리고 post_load.py 의 REFRESH_MVS 에서 그 이름을 뺀다(안 빼면 갱신이 없는 표를 불러 멈춘다).
--
-- 적용 뒤 확인:
--   ① select count(*) from mv_tx_parcel_geog;          -- 수천 행(2026-09-27 기준 4,384)
--   ② select has_table_privilege('anon', 'mv_tx_parcel_geog', 'select');   -- f
--   ③ 찬 캐시 첫 호출을 다시 잰다(메인 몫).

begin;

-- =====================================================================
-- 반경 이웃 찾기 전용 요약표 — 거래가 있는 필지만 (2026-09-27c)
-- =====================================================================
-- list_price_bands 의 반경 100m·500m 이웃은 L4·L5 의 `t.pnu = any(…)` 에만 쓰인다 — 거래가
-- 없는 필지는 이웃 배열에 들어 있어도 아무것도 안 건진다. 그런데 예전에는 그 이웃을
-- parcel(전국 111만 행 · 힙 416MB · idx_parcel_geog 90MB)에서 찾아, 첫 방문(찬 캐시)마다
-- 반경 안 필지 수백 곳을 훑느라 창고에서 수백 쪽을 꺼냈다(2026-09-27 라이브 실측 —
-- 이 함수 찬 캐시 첫 호출 74~789쪽의 대부분). 거래가 있고 좌표가 있는 필지는 4,384곳뿐이다.
-- ⛔ **거래 조건을 좁히지 말 것**(집합·단가 있음·24개월 등). 그 조건은 L4·L5 가 거래 쪽에서
--    이미 건다 — 여기서 또 걸면 두 곳이 같은 규칙을 따로 들게 되고, 한쪽만 고치는 날 조용히
--    갈린다. 이 표는 "거래가 한 건이라도 있는 필지"라는 가장 넓은 상한만 진다.
-- ⛔ 좌표는 parcel.geom 에서만 뽑는다(lat/lng 칸을 쓰면 검색·상권판정과 자리가 갈린다).
-- ⚠️ **자료를 새로 넣으면 `python scripts/post_load.py`** — 안 하면 새로 거래가 생긴 필지가
--    이웃에서 조용히 빠진다(에러 0 — 형제 요약표들과 같은 방식).
create materialized view if not exists mv_tx_parcel_geog as
select p.pnu,
       p.geom::geography as geog
  from parcel p
 where p.geom is not null
   and exists (select 1 from transaction t where t.pnu = p.pnu);

comment on materialized view mv_tx_parcel_geog is
  'list_price_bands 반경 이웃 찾기 전용(2026-09-27c) — 거래가 한 건이라도 있고 좌표가 있는 필지만. '
  '이웃 배열은 L4·L5 의 t.pnu = any(…) 에만 쓰여 거래 없는 필지를 빼도 결과가 같다. '
  'parcel 전국 111만 행 대신 이 표(수천 행)를 훑어 찬 캐시 첫 호출의 창고 읽기를 줄인다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 를 반드시 돌릴 것 — '
  '안 하면 새 거래 필지가 이웃에서 조용히 빠진다(에러가 아니다).';

-- ⛔ 유니크가 없으면 `refresh materialized view concurrently` 가 아예 안 된다(post_load.py).
create unique index if not exists idx_mtpg_pnu  on mv_tx_parcel_geog (pnu);
-- 반경 조회(st_dwithin geography)를 받치는 색인 — 없으면 이 표를 통째로 훑는다.
create index if not exists idx_mtpg_geog        on mv_tx_parcel_geog using gist (geog);

analyze mv_tx_parcel_geog;

-- ⛔ 이 표는 정본(schema.sql) 아래쪽의 기본권한 회수보다 먼저 만들어진다 — 새 환경에서 이 줄이
--    없으면 anon 이 거래 있는 필지 목록과 좌표를 REST 로 통째 읽는다. 화면은 함수로만 읽는다.
revoke all on mv_tx_parcel_geog from public, anon, authenticated;

-- ── ① 이 필지의 실거래 이력 — 비교만 char(19) 로 ─────────────────────────────
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
  -- ⛔ `::char(19)` 캐스트를 지우지 말 것(2026-09-27c). pnu 칸이 char(19) 인데 text 와 견주면
  --    **칸 쪽**이 text 로 캐스트돼 idx_tx_pnu 를 못 탄다 — 라이브 실측으로 거래 0건 필지가
  --    idx_tx_pnu10_ym 으로 2024년 이후 거래 2.8만 행을 훑어 1,876쪽을 만졌다(찬 캐시면
  --    그 쪽마다 창고 읽기다). 캐스트하면 idx_tx_pnu 한 번에 2쪽이다. 형제 함수들의 `p_pnu::char(19)` 와
  --    같은 처방이다(2026-08-16b). 서명(pnu text)은 화면 약속이라 그대로 둔다.
  where t.pnu = list_parcel_transactions.pnu::char(19)
    and t.contract_ym >= '202401'
  -- 계약일이 없는 행(구 자료)이 최신인 척 위로 올라오면 안 된다 → nulls last.
  -- 마지막 tx_id 는 같은 날 여러 건일 때 순서가 호출마다 흔들리지 않게 하는 못이다.
  order by t.contract_ym desc, t.contract_day desc nulls last, t.tx_id
  limit 100;
$$;

-- ── ③ list_price_bands — 이웃 찾기 한 문장만 새 요약표로 ─────────────────────
create or replace function list_price_bands(p_pnu text)
returns table (
  floor_no        smallint,
  status          text,
  stage           text,
  n               int,
  p25             numeric,
  median          numeric,
  p75             numeric,
  median_area_m2  numeric,
  window_from     text
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ **파라미터를 그대로 쓰지 말 것.** 서명은 text 인데 pnu 컬럼은 세 표(parcel·
  --    building_floor·transaction) 모두 char(19) 다. `char컬럼 = text파라미터` 는 컬럼 쪽이
  --    text 로 캐스트돼 인덱스가 통째로 무력해진다(2026-08-16b 라이브 실측):
  --      · building_floor 층 목록: text 비교 cost 31,239 · 459.8ms ↔ char 비교 cost 2.07 · 0.796ms
  --      · 함수 전체:              707~733ms          ↔ char(19) 파라미터 복제본 73~101ms
  --    L4 주석의 배열 이야기와 **같은 병의 스칼라판**이다 — 파라미터와 컬럼의 타입을 맞춘다.
  -- ⓘ text→char(19) 캐스트는 19자를 넘는 입력을 자르지만, pnu 는 19자 고정이라 무해하다
  --    (더 긴 입력은 애초에 pnu 가 아니고, 잘려도 없는 필지라 빈 결과다).
  v_pnu      char(19) := p_pnu;
  -- ⚠️ **char(6) 이다.** contract_ym 컬럼이 char(6) 인데 여기를 text 로 두면
  --    `char컬럼 >= text변수` 비교에서 컬럼이 text 로 캐스트돼 인덱스 조건으로
  --    못 들어간다(2026-08-16b 가 pnu 에서 겪은 것과 **같은 병**). 나갈 때만
  --    `::text` 로 되돌린다 — window_from 은 text 로 약속돼 있다.
  v_from     char(6);
  v_gate     boolean;
  v_geog     geography;
  -- ⚠️ text[] 가 아니라 char(19)[] 인 이유: transaction.pnu 가 char(19) 라 text 와 견주면
  --    캐스트가 끼어 배열 조건이 인덱스 안으로 못 들어간다(아래 L4 주석의 실측 참조).
  v_near100  char(19)[];
  v_near500  char(19)[];
  v_floor    smallint;
  v_band     text;
  v_stage    text;
  v_n        int;
  v_p25      numeric;
  v_med      numeric;
  v_p75      numeric;
  v_area     numeric;
begin
  v_from := to_char((now() at time zone 'Asia/Seoul') - interval '24 months', 'YYYYMM');

  -- ⓘ 여기만 `::char(5)` 가 없는 것은 실수가 아니다(2026-08-22 라이브 실측).
  --    price_gate_sigungu.sigungu_code 는 **text** 다(mv_open_sigungu·parcel·transaction
  --    쪽 sigungu_code 가 char(5) 인 것과 다르다). substr() 의 결과도 text 라 지금이
  --    이미 타입이 맞은 상태다 — 여기에 ::char(5) 를 붙이면 text→char(5)→text 로
  --    되돌아가는 군더더기 캐스트가 생기고, 덤으로 bpchar 의 뒤 공백 무시 규칙까지
  --    끌어들인다. 타입을 맞추라는 규칙(2026-08-16b)은 **상대 컬럼의 타입**을 보라는
  --    뜻이지 char 로 통일하라는 뜻이 아니다.
  select g.gate_pass into v_gate
    from price_gate_sigungu g
   where g.sigungu_code = substr(v_pnu, 1, 5);

  -- 아직 판정이 없는 구(표에 줄이 없음)도 '아니오'다 — 모르면 안 낸다.
  if v_gate is not true then
    return query select null::smallint, 'gate_fail'::text, null::text, null::int,
                        null::numeric, null::numeric, null::numeric, null::numeric, v_from::text;
    return;
  end if;

  select p.geom::geography into v_geog from parcel p where p.pnu = v_pnu;

  -- 500m 안을 한 번만 훑고 100m 는 거기서 걸러 쓴다(백테스트 neighbors_within 과 같은 방식).
  -- 좌표가 없으면 두 배열이 비고, 반경 단계는 후보 0건이 되어 저절로 건너뛴다
  -- (백테스트의 coords_missing 과 같은 취급 — 죽지 않고 아래 단계로 내려간다).
  -- 마지막 인자 false = **구면**으로 잰다(기본값 true 는 회전타원체). 백테스트가 쓴
  -- haversine 이 구면이라 자를 맞춘 것이다. 남는 차이는 반지름 소수점뿐이고
  -- (PostGIS 6,371,008.7714m vs 백테스트 6,371,008.8m) 500m 에서 1mm 미만이라 무시한다.
  -- ⛔ 이웃은 parcel(전국 111만 행)이 아니라 **거래가 있는 필지만 모은 요약표**
  --    mv_tx_parcel_geog 에서 찾는다(2026-09-27c). 이웃 배열은 아래 L4·L5 의
  --    `t.pnu = any(…)` 에만 쓰이므로, 거래가 없는 필지는 들어 있어도 아무것도 안 건진다
  --    — 빼도 결과가 같다(라이브 md5 대조로 증명). 찬 캐시에서 parcel 의 GiST·힙을 훑던
  --    수백 쪽이 수십 쪽으로 준다. ⚠️ 새 실거래를 넣고 `post_load.py` 를 안 돌리면 그
  --    필지가 이웃에서 조용히 빠진다(요약표 갱신 목록 REFRESH_MVS 에 들어 있다).
  if v_geog is not null then
    select coalesce(array_agg(p.pnu) filter (
             where st_dwithin(p.geog, v_geog, 100, false)), '{}'),
           coalesce(array_agg(p.pnu), '{}')
      into v_near100, v_near500
      from mv_tx_parcel_geog p
     where st_dwithin(p.geog, v_geog, 500, false);
  end if;
  v_near100 := coalesce(v_near100, '{}');
  v_near500 := coalesce(v_near500, '{}');

  for v_floor in
    select distinct bf.floor_no from building_floor bf
     where bf.pnu = v_pnu
     order by 1
  loop
    -- 1층은 값이 자리(코너·전면·골목)로 갈리는데 그 자리가 공공데이터에 없다.
    -- 백테스트 MdAPE 45.2% — 다른 층대의 두 배다. 그래서 "모른다"고 말한다(결정 0013 §3).
    if v_floor = 1 then
      return query select v_floor, 'floor_1f'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text;
      continue;
    end if;

    -- 지하(음수)·옥탑(99)·층미상은 백테스트 표본이 **0건**이다(2017년부터 실거래 원본에
    -- 지하층 표기가 오지 않는다 — 알려진한계). 검증된 적 없는 층에는 값을 내지 않는다.
    if v_floor is null or v_floor < 0 or v_floor = 99 then
      return query select v_floor, 'no_evidence'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text;
      continue;
    end if;

    v_band := price_floor_band(v_floor);

    select a.lvl, a.cnt, a.q25, a.q50, a.q75, a.area_med
      into v_stage, v_n, v_p25, v_med, v_p75, v_area
      from (
        select c.lvl,
               count(*)::int                                              as cnt,
               -- 자리수를 원본 컬럼과 맞춘다(unit_price=numeric(14,2)·bld_area_m2=numeric(10,2)).
               -- 보간 결과는 소수점이 끝없이 늘어나 화면·JSON 에 의미 없는 자리가 실린다.
               (percentile_cont(0.25) within group (order by c.unit_price))
                 ::numeric(14,2)                                           as q25,
               (percentile_cont(0.5)  within group (order by c.unit_price))
                 ::numeric(14,2)                                           as q50,
               (percentile_cont(0.75) within group (order by c.unit_price))
                 ::numeric(14,2)                                           as q75,
               -- 총액 환산의 자 — 화면이 "㎡당 단가 × 이 면적"으로 억 단위를 만든다.
               -- 면적이 없는 행은 빼고 잰다(있는 것처럼 0 을 섞으면 총액이 작아진다).
               (percentile_cont(0.5)  within group (order by c.bld_area_m2)
                 filter (where c.bld_area_m2 is not null))
                 ::numeric(10,2)                                           as area_med
          from (
            -- L2 — 같은 필지 같은 층
            select 'L2'::text as lvl, t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null
               and t.contract_ym >= v_from
               and t.pnu = v_pnu and t.floor_no = v_floor
            union all
            -- L4 — 반경 100m 같은 층
            -- ⚠️ 배열의 타입이 성능을 가른다(2026-08-16 라이브 EXPLAIN 실측, 이웃 839필지):
            --    · `t.pnu::text = any(text[])` → 배열이 **힙 필터**로 밀려 1,957행을 읽고 버림
            --      (buffers 618 · 4.4~5.7ms)
            --    · `join unnest(...) on t.pnu = nb.pnu` → 해시 조인이라 1,934행을 먼저 뜸
            --      (buffers 610 · 8.1~8.2ms)
            --    · `t.pnu = any(char(19)[])` → **Index Cond** 로 들어가 idx_tx_pnu 를 그대로 탐
            --      (buffers 133 · heap blocks 392→5 · 2.5~2.7ms) ← 이것을 쓴다
            --    핵심은 캐스트를 없애 **컬럼과 배열의 타입을 맞추는 것**이다.
            select 'L4', t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null
               and t.contract_ym >= v_from
               and t.floor_no = v_floor and t.pnu = any(v_near100)
            union all
            -- L5 — 반경 500m 같은 층
            select 'L5', t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null
               and t.contract_ym >= v_from
               and t.floor_no = v_floor and t.pnu = any(v_near500)
            union all
            -- L6 — 같은 법정동(PNU 앞 10자리) 같은 층대
            -- "행정동" 이 아니라 법정동인 이유: 실거래의 동은 문자, 건물의 동은 코드라
            -- 이름 대조가 조용히 어긋난다(성적표 §1 · 결정 0012 §4).
            select 'L6', t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null
               and t.contract_ym >= v_from
               and t.pnu is not null
               and substr(t.pnu, 1, 10) = substr(v_pnu, 1, 10)
               and price_floor_band(t.floor_no) = v_band
          ) c
         group by c.lvl
      ) a
      -- 최소 표본은 백테스트 MIN_SAMPLES 와 같은 값이다(위 ⛔ 주석 참조).
      join (values ('L2', 1, 1), ('L4', 2, 3), ('L5', 3, 5), ('L6', 4, 1))
             as s(lvl, ord, min_n) on s.lvl = a.lvl
     where a.cnt >= s.min_n
     order by s.ord
     limit 1;   -- 처음 성립하는 단계를 채택한다(사다리 걷기)

    if v_stage is null then
      return query select v_floor, 'no_estimate'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text;
    else
      return query select v_floor, 'ok'::text, v_stage, v_n,
                          v_p25, v_med, v_p75, v_area, v_from::text;
    end if;
  end loop;
  return;
end;
$$;

commit;

-- 함수 서명은 그대로라 화면(api.*)은 바뀌는 것이 없다. 새 표는 PostgREST 에 안 열린다.
notify pgrst, 'reload schema';
