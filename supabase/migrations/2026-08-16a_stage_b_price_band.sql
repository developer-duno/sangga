-- =====================================================================
-- Stage B — 참고 시세 밴드의 **서버 쪽** (2026-08-16, 결정 0013)
-- =====================================================================
-- 결정 0012 는 시세 표시를 두 단계로 갈랐고, Stage A(사실 표시)는 2026-08-15a 로 이미
-- 라이브에 있다. 여기서 만드는 것은 **Stage B** — 곁의 실거래로 "이 언저리"를 어림해
-- 밴드로 내보내는 길이다. 그 착수 여부는 성적표 v1(`docs/backtest/성적표-v1.md`)을 들고
-- 사장님이 재결재했고, 그 결재문이 결정 0013 이다.
--
-- ⛔ 절대 규칙 2 — 감정평가사 독점 업무를 연상시키는 표현(CLAUDE.md 금지 목록)은 이 파일
--    어디에도 쓰지 않는다. 여기 있는 것은 전부 **참고·추정**이며, 근거 단계(stage)와
--    표본 수(n)를 함께 낸다(절대 규칙 3). 근거를 숨긴 숫자는 내보내지 않는다.
--
-- 세 가지를 만든다:
--   ① price_gate_sigungu   — "이 구에서 참고 시세를 내도 되는가"의 정본 (결정 0013 §2)
--   ② price_floor_band()   — 층 번호 → 층대 이름 (백테스트와 **같은** 정의)
--   ③ list_price_bands()   — 이 필지의 층마다 밴드(또는 안 내는 이유)를 돌려준다
--
-- ## 왜 구 단위 게이트인가 (전 지역에 켜지 않는가)
--
-- 성적표 v1 은 "어디서나 믿을 만하다"를 보여주지 못했다. 어떤 구에서는 사다리가
-- **구 평균보다도 못하다**(금천구: 사다리 26.0% vs 구 평균 17.6%). 이미 화면에 있는
-- 구 평균보다 못한 값을 "추정"이라며 얹으면 후퇴다. 그래서 두 조건을 모두 만족한
-- 구에서만 켠다 — ① 운영 MdAPE ≤ 30% ② 같은 구에서 사다리가 구 평균을 이길 것.
--
-- ## 왜 목록을 표(DB)에 두나 — 화면·문서가 아니라
--
-- 목록을 화면 코드나 문서에 복사하면 성적표를 다시 뽑는 날 그 사본만 조용히 낡는다
-- (`list_open_sigungu()` 때 실제로 겪은 드리프트 — 확정 설계 9). 통과 구의 진실은
-- 서버 한 곳이고, 그 표를 채우는 것은 사람 손이 아니라 백테스트 산출물이다:
--   python scripts/backtest_price.py      → docs/backtest/통과구.csv
--   python scripts/load_price_gate.py     → price_gate_sigungu

-- =====================================================================
-- ① price_gate_sigungu — 참고 시세를 켜도 되는 구
-- =====================================================================
-- ## 왜 판정 근거(n_paired·ladder_mdape·base_mdape)까지 같이 넣나
--
-- 참·거짓만 남기면 "왜 이 구가 꺼져 있나"를 다음 사람이 성적표를 다시 뽑아야 알 수 있다.
-- 판정과 그 근거를 같은 줄에 두면, 표 한 번 조회로 "26.0% 인데 구 평균이 17.6% 라 졌다"
-- 까지 말할 수 있다. 숫자는 **짝지은 비교**(두 방법 모두 성립한 거래만)의 MdAPE 다.
create table if not exists price_gate_sigungu (
  sigungu_code  text        primary key,          -- PNU 앞 5자리
  sigungu_nm    text,
  n_paired      int,                              -- 짝지은 비교에 쓴 검증 거래 수
  ladder_mdape  numeric,                          -- 운영 모드(사다리) 오차 중앙값 (0~1)
  base_mdape    numeric,                          -- 대조군(구 평균) 오차 중앙값 (0~1)
  gate_pass     boolean     not null,
  loaded_at     timestamptz not null default now()
);

comment on table price_gate_sigungu is
  '결정 0013 §2 참고 시세 출시 기준선 — 이 구에서 밴드를 화면에 내도 되는가의 정본. '
  '조건 둘을 모두 만족해야 true: ① 사다리 MdAPE <= 30% ② 사다리가 BASE(구 평균)를 이김. '
  '⛔ 손으로 구를 넣고 빼지 않는다 — scripts/backtest_price.py 가 만든 docs/backtest/통과구.csv 를 '
  'scripts/load_price_gate.py 로만 갱신한다(결정 0013 §4). 기준선 자체를 바꾸는 것은 재결재 사항이다. '
  '⛔ anon 에게 열지 않는다 — 화면은 list_price_bands() 로만 읽는다.';

comment on column price_gate_sigungu.ladder_mdape is
  '짝지은 비교(두 방법 모두 성립한 거래만) 기준 운영 모드 MdAPE. 비율이다(0.29 = 29%)';
comment on column price_gate_sigungu.base_mdape is
  '같은 집합에서 잰 구 평균(BASE)의 MdAPE. 이 값보다 ladder_mdape 가 작아야 통과다';

-- 2026-08-13f 가 기본 권한을 바꿔 뒀지만, 그 명령이 닿지 않는 경로(대시보드가 만든 것 등)가
-- 남아 있으므로 **만든 자리에서 한 번 더 닫는다.** 라이브 확인은 post_load.py --check 가 한다.
revoke all on price_gate_sigungu from public, anon, authenticated;

-- =====================================================================
-- ② price_floor_band — 층 번호 → 층대 이름
-- =====================================================================
-- ## 왜 mv_sigungu_tx_stats 의 CASE 를 안 쓰고 새로 만드나 (정의가 셋이 되는데도)
--
-- Stage A 의 층대(mv_sigungu_tx_stats)는 **옥탑(99)을 '3층이상'에 흡수**한다. 결정 0012 의
-- 층대 정의가 ">=3" 이라서다. 그런데 Stage B 의 근거인 백테스트(`scripts/backtest_price.py`
-- 의 `floor_band()`)는 옥탑을 **따로** 센다 — 그래서 성적표가 "옥탑은 근거 0건"이라고
-- 말할 수 있었고, 결정 0013 §3 이 옥탑을 미제공으로 정할 수 있었다.
-- 두 정의를 하나로 합치면 둘 중 하나가 근거와 어긋난다: Stage A 로 맞추면 옥탑이 3층+
-- 표본에 섞여 "검증된 적 없는 층"에 값이 나가고, Stage B 로 맞추면 이미 라이브에 나가는
-- Stage A 화면의 칸이 하루아침에 바뀐다. 그래서 **Stage B 는 자기 근거와 같은 자를 쓴다.**
-- ⛔ 그러니 이 함수와 mv_sigungu_tx_stats 의 CASE 를 "중복"이라며 합치지 말 것.
--
-- ## 왜 search_path 를 안 박나
--
-- 이 함수는 표를 한 줄도 읽지 않는다(순수 계산). SET 절을 붙이면 SQL 함수 인라인이 막혀
-- 후보 한 줄마다 함수 호출이 남는다 — 같은 이유로 형제 함수 search_key() 도 안 박았다.
create or replace function price_floor_band(p_floor smallint)
returns text
language sql
immutable
parallel safe
as $$
  select case
    when p_floor is null then '층미상'
    when p_floor < 0     then '지하'
    when p_floor = 1     then '1층'
    when p_floor = 2     then '2층'
    when p_floor = 99    then '옥탑'
    else                      '3층+'
  end
$$;

comment on function price_floor_band(smallint) is
  'Stage B(결정 0013) 층대 이름 — scripts/backtest_price.py 의 floor_band() 와 **같은 정의**다. '
  '지하=음수 / 1층 / 2층 / 3층+ / 옥탑=99 / 층미상=NULL(절대 규칙 4: 0 은 쓰지 않는다). '
  '⚠️ mv_sigungu_tx_stats 의 층대(옥탑을 3층이상에 흡수)와 일부러 다르다 — Stage A 와 Stage B 는 '
  '각자의 근거와 같은 자를 쓴다. 내부용이라 anon 에게 열지 않는다';

revoke all on function price_floor_band(smallint) from public, anon, authenticated;

-- =====================================================================
-- 반경 조회용 지리 인덱스
-- =====================================================================
-- 기존 idx_parcel_geom 은 **geometry** 인덱스라 미터 단위 반경 질의(geography)에 붙지 않는다.
-- 4326 geometry 로 거리를 재면 단위가 '도(degree)'라 위도에 따라 실제 거리가 달라진다 —
-- 백테스트는 haversine(미터)로 쟀으므로 화면도 미터로 잰다. 다만 "같은 자로 쟀다"가
-- "성적표 숫자가 곧 이 화면의 성적"이라는 뜻은 아니다 — 아래 사다리 주석 참조.
-- ⚠️ 이 인덱스를 만드는 동안 parcel(1.1M 행)에 **쓰기가 잠긴다**(SHARE 락 — 읽기는 된다).
--    대시보드 SQL Editor 는 한 트랜잭션이라 concurrently 를 쓸 수 없다. 적재 작업과
--    겹치지 않는 시간에 적용할 것.
-- ⓘ 좌표는 지금 parcel.lat/lng 와 geom 이 같은 값에서 나온다(load_sangkwon_snapshot 이
--    lat/lng 로 geom 을 만든다). 둘이 어긋나지 않게 하는 제약은 아직 없다(별건).
create index if not exists idx_parcel_geog on parcel using gist ((geom::geography));

-- =====================================================================
-- ③ list_price_bands — 이 필지의 층별 참고 시세 밴드
-- =====================================================================
-- ## 무엇을 돌려주나
--
-- 층 하나에 한 줄. `status` 가 그 줄의 성격을 말한다:
--   gate_fail    — 이 구는 아직 참고 시세를 내지 않는다(결정 0013 §2). 층 나열도 하지 않는다
--   floor_1f     — 1층은 제공하지 않는다(백테스트 MdAPE 45.2% — 코너·전면 여부가 자료에 없다)
--   no_evidence  — 지하·옥탑·층미상. 백테스트 표본이 **0건**이라 아무 말도 할 수 없다
--   no_estimate  — 사다리가 어느 단계도 못 세웠다("표본 부족")
--   ok           — 밴드를 낸다. stage(근거 단계)와 n(표본 수)을 반드시 함께 쓴다
--
-- ## 왜 밴드가 p25~p75 인가
--
-- 추정 한 점(중앙값)만 내면 "이 가격이다"로 읽힌다. 성적표가 말하는 것은 "이 언저리다"뿐이다
-- (전체 MdAPE 29.1%). 그래서 후보 거래 단가의 **사분위 폭**을 그대로 내보낸다 — 폭이 곧
-- "곁의 가게들이 실제로 이만큼 갈렸다"는 사실이다. 총액 환산은 화면이 median_area_m2 로 한다.
--
-- ## 사다리 (결정 0012 §6.2 · 백테스트와 같은 순서·같은 최소 표본)
--
--   L2  같은 필지 + 같은 층          최소 1건
--   L4  반경 100m + 같은 층          최소 3건
--   L5  반경 500m + 같은 층          최소 5건
--   L6  같은 법정동 + 같은 층대      최소 1건
--
-- ⛔ 이 최소 표본은 `scripts/backtest_price.py` 의 `MIN_SAMPLES` 와 **같은 값이라야 한다.**
--    갈라지면 화면과 성적표가 서로 다른 방법이 되는데 어디서도 에러가 안 난다.
-- ⚠️ 다만 **같아지는 것은 사다리 규칙과 최소 표본까지**다. 후보를 고르는 창은 서로 다르다:
--    백테스트는 학습 구간(~202512)의 거래만 후보로 쓰고, 여기서는 **오늘 기준 롤링 24개월**을
--    쓴다(검증 구간의 거래도 후보가 된다). 그래서 성적표의 29.1%·45.2% 같은 숫자는 이 함수의
--    성적이 아니라 **참고치**다 — "이 규칙이 그때 그 자료에서 이 정도였다"까지만 말한다.
-- ⚠️ BASE(구 평균)는 사다리에 넣지 않는다. 대조군이지 단계가 아니다(성적표 §1).
--
-- ## 왜 후보를 한 번만 모으고 층마다 다시 안 재나
--
-- 반경은 **필지 위치**로 정해지므로 층이 바뀌어도 이웃은 그대로다. 건물 한 채에 층이
-- 열몇 개니, 층마다 반경을 다시 재면 같은 지리 조회를 열몇 번 반복하게 된다.
--
-- ## 왜 24개월인가 · 왜 KST 인가
--
-- Stage A 의 구 분포(mv_sigungu_tx_stats)와 같은 창을 쓴다 — 한 화면에서 두 숫자가 서로
-- 다른 기간을 말하면 비교가 거짓말이 된다. now() 는 UTC 라 월말·월초에 한 달이 어긋나므로
-- KST 로 고정한다(timezone 룰).
--
-- ⚠️ 파라미터를 p_ 로 시작하는 이유: `pnu`·`floor_no` 는 컬럼 이름과 겹친다. 겹치면
--    PostgreSQL 이 컬럼을 우선 집어 `where t.pnu = t.pnu`(= 전 국토 거래)가 된다
--    (list_parcel_transactions·list_building_districts 가 밟을 뻔한 함정).
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
  v_from     text;
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
   where g.sigungu_code = substr(p_pnu, 1, 5);

  -- 아직 판정이 없는 구(표에 줄이 없음)도 '아니오'다 — 모르면 안 낸다.
  if v_gate is not true then
    return query select null::smallint, 'gate_fail'::text, null::text, null::int,
                        null::numeric, null::numeric, null::numeric, null::numeric, v_from;
    return;
  end if;

  select p.geom::geography into v_geog from parcel p where p.pnu = p_pnu;

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
     where bf.pnu = p_pnu
     order by 1
  loop
    -- 1층은 값이 자리(코너·전면·골목)로 갈리는데 그 자리가 공공데이터에 없다.
    -- 백테스트 MdAPE 45.2% — 다른 층대의 두 배다. 그래서 "모른다"고 말한다(결정 0013 §3).
    if v_floor = 1 then
      return query select v_floor, 'floor_1f'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from;
      continue;
    end if;

    -- 지하(음수)·옥탑(99)·층미상은 백테스트 표본이 **0건**이다(2017년부터 실거래 원본에
    -- 지하층 표기가 오지 않는다 — 알려진한계). 검증된 적 없는 층에는 값을 내지 않는다.
    if v_floor is null or v_floor < 0 or v_floor = 99 then
      return query select v_floor, 'no_evidence'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from;
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
               and t.pnu = p_pnu and t.floor_no = v_floor
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
               and substr(t.pnu, 1, 10) = substr(p_pnu, 1, 10)
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
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from;
    else
      return query select v_floor, 'ok'::text, v_stage, v_n,
                          v_p25, v_med, v_p75, v_area, v_from;
    end if;
  end loop;
  return;
end;
$$;

comment on function list_price_bands(text) is
  'Stage B(결정 0013) 이 필지의 층별 참고 시세 밴드 — 곁의 실거래(최근 24개월·집합)로 어림한 '
  '추정값이며 감정평가가 아니다. 한 층에 한 줄이고 status 가 그 줄의 성격을 말한다: '
  'gate_fail(이 구는 기준선 미달 — 층 나열 없이 한 줄) / floor_1f(1층 미제공) / '
  'no_evidence(지하·옥탑·층미상 — 백테스트 표본 0건) / no_estimate(표본 부족) / ok(밴드). '
  'ok 인 줄은 stage(L2·L4·L5·L6)와 n(표본 수)을 **반드시 함께** 표시한다(절대 규칙 3). '
  'p25/median/p75 는 ㎡당 단가, median_area_m2 는 총액 환산용 후보 면적 중앙값이다. '
  'security definer — transaction·parcel·price_gate_sigungu 가 anon 에게 닫혀 있어 '
  '소유자 권한으로 대신 읽는다. 나가는 것은 층·통계값뿐(개별 거래·상호명은 나가지 않는다)';

-- 화면이 부르는 함수만 명시적으로 연다(2026-08-13g 이후 함수는 기본으로 닫혀 있다).
grant execute on function list_price_bands(text) to anon, authenticated;
