-- =====================================================================
-- 마이그레이션 2026-08-22b — 사다리 L6(같은 법정동) 단계에 인덱스를 붙인다
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로 돌린다.**
--   `create index concurrently` 가 아니라 보통 create 라 한 트랜잭션에 들어간다.
--   → Supabase 대시보드 → SQL Editor 에 이 파일을 통째로 붙여 실행.
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇이 문제인가
-- ─────────────────────────────────────────────────────────────────────
-- `list_price_bands` 의 사다리 마지막 칸 L6 은 **같은 법정동**을 이렇게 찾는다:
--
--     and substr(t.pnu, 1, 10) = substr(v_pnu, 1, 10)
--
-- 왼쪽이 **함수를 씌운 값**이라 기존 `idx_tx_pnu (pnu, contract_ym)` 은 못 쓴다
-- (인덱스는 pnu 원본으로 정렬돼 있는데 조건은 그 앞 10자리를 자른 값이다).
-- 그래서 이 칸은 매번 넓게 훑는다. 성적표 §1 기준 **채택의 53%가 L6** 이고,
-- 이 조회는 **층 수 × 호출**만큼 돈다 — 거래가 쌓일수록 그대로 느려진다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 처방 1 — 자른 값 그대로를 색인한다(표현식 인덱스)
-- ─────────────────────────────────────────────────────────────────────
-- 조건에 쓰는 식(`substr(pnu,1,10)`)을 그대로 인덱스 키로 만든다. 두 번째 칸에
-- contract_ym 을 붙여 24개월 창까지 인덱스 안에서 자른다.
--
-- 부분 조건(`where pnu is not null`)을 기존 idx_tx_pnu 와 똑같이 맞춘 이유:
-- pnu 가 NULL 이면 substr 도 NULL 이라 어차피 `=` 로 안 걸린다. 즉 뜻은 같은데
-- **인덱스만 작아진다**(실거래에는 PNU 없는 행이 많다 — 2024 이전분).
--
-- ─────────────────────────────────────────────────────────────────────
-- 처방 2 — v_from 을 char(6) 으로 (#64 와 같은 병의 재발 방지)
-- ─────────────────────────────────────────────────────────────────────
-- 위 인덱스의 두 번째 칸 contract_ym 은 **char(6)** 인데, 함수 안 `v_from` 은
-- **text** 였다. `char컬럼 >= text변수` 는 컬럼 쪽이 text 로 캐스트돼 **인덱스
-- 조건(Index Cond)으로 못 들어가고 필터로 밀린다** — 2026-08-16b 가 pnu 에서
-- 잡았던 것과 같은 병이다. 선언을 char(6) 으로 맞추고, 나갈 때만 `::text` 로
-- 되돌린다(window_from 은 text 로 약속돼 있다).
--
-- ⚠️ **함수 로직은 한 글자도 안 바꿨다.** 사다리 규칙·최소 표본·얼리 엑싯 전부 그대로다
--    — 지금은 "사다리 결과가 같은가"를 기계로 대조할 수단이 없으므로(백테스트는 학습
--    구간을 쓰고 함수는 롤링 24개월을 쓴다), 눈에 안 보이는 변화를 만들지 않는다.
--    바뀐 것은 **변수 타입과 캐스트 위치**뿐이다.
--
-- ⚠️ 표현식 인덱스는 **ANALYZE 전에는 통계가 없어** 플래너가 안 고른다. 그래서 맨 끝에
--    analyze 를 붙였다.
--
-- 검산 (실행 후):
--   explain (analyze, buffers)
--   select count(*) from transaction t
--    where t.pnu is not null
--      and substr(t.pnu,1,10) = '1168010100'
--      and t.contract_ym >= '202408';
--     → "Index Scan using idx_tx_pnu10_ym" 이 보이고, contract_ym 이
--       **Index Cond 안에** 들어가 있어야 한다(Filter 로 밀려 있으면 처방 2가 안 먹은 것).

create index if not exists idx_tx_pnu10_ym
  on transaction (substr(pnu, 1, 10), contract_ym)
  where pnu is not null;

comment on index idx_tx_pnu10_ym is
  '사다리 L6(같은 법정동 = PNU 앞 10자리) 전용 표현식 인덱스. 조건이 substr 로 자른 값이라 '
  'idx_tx_pnu(pnu, contract_ym) 로는 못 탄다. 부분 조건은 idx_tx_pnu 와 같게 맞췄다 '
  '(substr(NULL) 은 어차피 = 로 안 걸리니 뜻은 같고 인덱스만 작아진다).';

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
  if v_geog is not null then
    select coalesce(array_agg(p.pnu) filter (
             where st_dwithin(p.geom::geography, v_geog, 100, false)), '{}'),
           coalesce(array_agg(p.pnu), '{}')
      into v_near100, v_near500
      from parcel p
     where p.geom is not null
       and st_dwithin(p.geom::geography, v_geog, 500, false);
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

-- security definer 함수는 replace 해도 권한이 남지만, 명시해 두는 편이 안전하다
-- (2026-08-13g 이후 함수는 기본으로 닫혀 있다).
grant execute on function list_price_bands(text) to anon, authenticated;

-- 표현식 인덱스는 통계가 따로 잡힌다 — 이걸 안 돌리면 플래너가 새 인덱스를 안 고른다.
analyze transaction;
