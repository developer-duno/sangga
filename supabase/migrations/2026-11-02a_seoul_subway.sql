-- =====================================================================
-- 2026-11-02a — 서울 지하철 승하차 자료·DB (결정 0045 PR⑥ · 표 둘 + 함수 + 신선도 18번 줄 + 서울시 세 줄 +6개월 · 화면 0)
-- =====================================================================
--
-- 왜
-- --
-- 「상권 인구」 카드에 이 건물 둘레 지하철역의 승하차 인원을 한 덩이로 붙이기 위한 창고다(👤 결정 0045 ④-1·2 — 서울 지하철만 ·
-- 반경 500m · 역마다 거리 · 문구 「승하차 인원(카드 기준)」 · 「유동인구」 안 씀 · 카드 안 한 덩이 · 화면 재계산 0). 서울시가
-- 공표하는 교통카드(1회용 포함) 개찰 기준 역별·시간대별 승하차(OA-12252)와 역 좌표(역사마스터 OA-21232)를 **그대로** 싣는다.
-- 👤 2026-11-02 결정 다섯: ① 서울시 세 줄 신선도 날짜 = 분기말 + 6개월 − 1일(「가」 — 서울시 안내문 날짜) · Q1 환승역은 역 이름으로
-- 합친다(이름 같고 600m 안) · Q2 자료 없는 노선 역도 「승하차 자료 없음」으로 보인다 · Q3 500m 안 역이 없으면 그 한 줄 + 1.5km 안
-- 가장 가까운 역 이름·거리 · Q4 승차·하차 나란히 + 시간대 여섯 칸.
--
-- 무엇이 생기나 (새 객체 + 신선도 함수 다시 만들기 — 기존 표의 행·칸은 한 글자도 안 바꾼다)
-- ---------------------------------------------------------------------------------------
--   ① 표 둘 — subway_station(역사마스터 한 줄 · 수도권 784역 · 좌표 점 geom + gist(geography) · 묶음 group_id · has_ridership) ·
--      subway_ridership_m(달 · 원문 호선 · 원문 역 한 줄 · 승차·하차 24시간대 48칸 + 합 둘 · 기본키 = 원문 열쇠 · station_id 는
--      FK(유일 아님 — 짝표 뒤 같은 역으로 원문 두 줄이 모일 수 있다 · 메인 결정 ⑥-1)). 둘 다 RLS 켬 + 권한 회수(공개키 0).
--      수집 scripts/collectors/collect_seoul_subway.py · 적재 scripts/collectors/load_seoul_subway.py(관문 ⒜~⒣ · 한 트랜잭션).
--   ② 함수 list_nearby_subway(p_pnu text) + api 쌍둥이 — 필지에서 500m 안 역 묶음마다(가까운 순 · 최대 10줄) 최근 12개월
--      하루 평균 승하차(Σ 합 ÷ Σ 그 달들의 일수) + 시간대 여섯 칸 · status no_coord → not_seoul → no_data(표가 비었음 — 화면은
--      덩이를 숨긴다) → no_station(한 줄 · 1.5km 안 가장 가까운 역) → 묶음마다 ok. 공개 호출 허용 총계 38 → 39(post_load.py
--      ANON_CALLABLE_ALLOWLIST).
--   ③ get_data_freshness 다시 만들기 — 18번 줄 「지하철 승하차 (서울시)」(기준 = max(use_mm) · 다음 예정 = 기준월 + 2개월의 5일 ·
--      새 규칙 'subway' — 202609 → 2026-11-05) · **서울시 세 줄(11·13·14 · 'seoul_openclose') = 분기말 + 6개월 − 하루**(20262 →
--      2026-11-30 · 👤 「가」 — 옛 + 5개월은 서울시 게시 달보다 한 달 일러 분기마다 헛경보가 떴다) · comment 「열일곱」.
--      나머지 열네 줄·규칙은 글자 그대로다(상권정보 202606 → 2026-10-31 그대로).
--      ⓘ api.get_data_freshness 는 다시 만들지 않는다 — 통과 함수라 본문이 그대로다(2026-11-01a·b 와 같은 판단).
-- ⛔ 머리(language · stable · security definer · set search_path)와 comment 는 정본(schema.sql)과 글자 그대로다 —
--    tests/test_seoul_subway_migration.py 가 대조한다(CLAUDE.md ⛔ 2026-10-01a).
-- ⛔ 서명은 하나뿐이다(이름당 pg_proc 1 · 인자 (text)).
-- ⛔ 반경은 parcel.geom 점과 역 점만 · st_dwithin(geography, 500, false) — bbox 선필터는 gist 가 스스로 한다(따로 안 적는다 ·
--    2026-11-02 운영 임시 표 실측: 첫 호출 122ms · 더운 11ms).
--
-- 잠금
-- ----
-- 새 표·새 색인·새 함수 만들기와 함수 교체(create or replace)는 **기존 표를 잠그지 않는다**(새 표의 색인은 빈 표 위라 즉시 ·
-- ACCESS EXCLUSIVE 를 잡는 문장 0). 형제 관습대로 `lock_timeout` 은 **begin 앞**(세션 설정)에 둔다 — 함수 카탈로그 행을 다른
-- 세션이 쥐고 있으면 오래 줄 서지 않고 실패한다(통째 롤백 · 다시 돌리면 된다 · 전부 멱등).
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 중간에 끊기면 신선도 함수가 없는 표를 읽거나 api 쌍둥이 없이 원본만 남는다.
-- `notify pgrst` 는 commit **뒤**.
--
-- 실행 순서 — 마이그(DB 먼저) → 머지 → 본 폴더에서 수집 → 적재 → post_load · --check (Claude 가 dbx 로 · 사장님께 여쭌 뒤)
-- ------------------------------------------------------------------------------------------------------------------
-- 이 PR 은 화면이 0 이다. 마이그만 들어가고 적재 전이면 함수는 no_data(화면 덩이 숨김) · 신선도 18번 줄은 '자료 없음'이다.
--   ① python scripts/dbx.py -f supabase/migrations/2026-11-02a_seoul_subway.sql
--      (적용 즉시 서울시 세 줄 예정일이 +6개월로 — 20262 → 2026-11-30 · 그물 6호의 11/02 이슈 셋(개업·폐업 · 추정매출 ·
--       길단위인구)은 라이브에 오른 것을 본 뒤 닫는다)
--   ② 머지(main) — 본 폴더에서 수집·적재 명령이 생긴다
--   ③ 적재 **전** 디스크 판정 — 지금 사용량 + 약 25MB(추정 — 71달 × 약 620행 × 48칸) + WAL 여유 1GB 가 디스크의 85% 미만일 때만
--   ④ python scripts/collectors/collect_seoul_subway.py --dry-run --end-month <게시된 최근 달>   — 호출 1 + 장부 읽기만
--      python scripts/collectors/collect_seoul_subway.py --end-month <달> --master-too          — 달 약 70 + 마스터 1 ≈ 71회
--   ⑤ python scripts/collectors/load_seoul_subway.py --dry-run → 실적재(관문 ⒣: 승하차 역 ⊂ 마스터 — 어긋나면 통째 롤백)
--   ⑥ python scripts/post_load.py → python scripts/post_load.py --check — 0 이어야 한다(허용 목록 총계 39 · 정본↔라이브 함수 일치)
--   ⑦ python scripts/backup_raw.py — data/raw/seoul_subway 가 늘었다
--   ⓘ ①과 머지 사이에 **본 폴더(main)** 에서 `--check` 를 돌리면 api.list_nearby_subway 가 허용 목록 밖 공개 함수로
--     [사고]가 되고 get_data_freshness 가 정본과 달라 [사고]가 되는 것이 **정상**이다 — 그 창은 PR 가지 판으로 잰다.
--
-- 적용 뒤 확인 (dbx + anon 키로 **화면 요청 그대로**)
-- ------------------------------------------------
--   select oid::regprocedure, proconfig, prosecdef, provolatile from pg_proc
--    where proname = 'list_nearby_subway';                         -- 두 줄(public·api) · 둘 다 prosecdef t · provolatile s
--   select has_table_privilege('anon', 'subway_station', 'select'),
--          has_table_privilege('anon', 'subway_ridership_m', 'select');   -- f · f
--   select src, basis, next_expected from api.get_data_freshness()
--    where src in ('상권 개업·폐업 (서울시)', '지하철 승하차 (서울시)', '점포·업종 (상권정보)');
--     → 20262 | 2026-11-30 · (적재 전) null | null · 202606 | 2026-10-31
--   ⑤ 적재 뒤: select status, station_nm, lines, dist_m, months_n, on_daily, off_daily
--                from api.list_nearby_subway('<충무로역 500m 안 서울 필지 19자리>');   → ok · 충무로 · {3호선,4호선} · …
--   explain (analyze) select * from public.list_nearby_subway('<서울 필지>');   -- idx_subway_station_geog Index Scan 확인
--   anon 키:
--     POST /rest/v1/rpc/list_nearby_subway {"p_pnu":"<서울 필지>"}             → 200 · [ok 줄 1~10 또는 no_station 한 줄]
--     POST /rest/v1/rpc/list_nearby_subway {"p_pnu":"3020010100100010000"}    → 200 · [not_seoul 한 줄]
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로 (신선도 함수 먼저 → api → public → 표 나중 — 표부터 지우면 함수가 없는 표를 읽어 신선도 표가
-- 통째로 사라진다 · 0045 171행 역순 규칙): `set lock_timeout = '5s'; begin;` →
--   ① 2026-11-01b_sgis_district_pop.sql 의 get_data_freshness 정의 첫 줄부터 그 함수의 revoke 줄까지(comment 포함)를
--      글자 그대로(18번 줄이 없고 서울시 세 줄이 + 5개월인 판)
--   ② drop function api.list_nearby_subway(text); drop function list_nearby_subway(text);
--   ③ drop table subway_ridership_m; drop table subway_station;
-- → `commit;` → `notify pgrst, 'reload schema';` 그리고 이 PR revert(정본 · post_load 허용 목록 39 → 38 · ANALYZE_TABLES 둘 ·
-- 그물 6호 힌트). 적용된 이 파일은 고치지 않는다(원장).

set statement_timeout = '60s';
set lock_timeout = '5s';

begin;

-- =====================================================================
-- 표·함수: 서울 지하철 승하차 — 역사마스터 + 월별 시간대 승하차 (2026-11-02a · 결정 0045 PR⑥)
-- =====================================================================
-- 서울시가 공표하는 교통카드(1회용 포함) 개찰 기준 지하철 역별·시간대별 승하차 인원(OA-12252 `CardSubwayTime`)과
-- 역사마스터(OA-21232 `subwayStationMaster` — 역 좌표)를 **그대로** 싣는다(👤 결정 0045 ④-1·2 — 서울 지하철만 ·
-- 반경 500m · 역마다 거리 · 문구 「승하차 인원(카드 기준)」 · 「유동인구」 안 씀).
-- 수집 scripts/collectors/collect_seoul_subway.py → 적재 scripts/collectors/load_seoul_subway.py(마스터 upsert ·
-- 승하차 달 단위 교체 · 한 트랜잭션 · 짝표 씨앗 scripts/seeds/subway_*_map.csv).
-- ⛔ 환승역은 서울시가 관리 호선 한 줄에 몰아 센다(충무로 3호선 = 승차 100~190 · 하차 0 / 4호선 = 승차 약 95만) —
--    그래서 호선마다 줄을 세우지 않고 **역 묶음(group_id)** 으로 합친다(정규화 이름이 같고 서로 600m 안 · 👤 Q1 「가」).
-- 표 둘은 공개키에게 닫혀 있다(RLS 켬 + 정책 0 + 권한 회수) — 화면은 list_nearby_subway 로만 읽는다.
-- 승하차 표를 get_data_freshness 가 읽으므로 그 함수보다 **앞**에 둔다.
create table if not exists subway_station (
  station_id     text primary key,
  station_nm     text not null,
  name_norm      text not null,
  line_nm        text not null,
  group_id       integer not null,
  lat            double precision not null,
  lng            double precision not null,
  geom           geometry(Point, 4326) not null,
  has_ridership  boolean not null default false,
  loaded_at      timestamptz not null default now()
);

create index if not exists idx_subway_station_geog on subway_station using gist ((geom::geography));
create index if not exists idx_subway_station_group on subway_station (group_id);

comment on table subway_station is
  '결정 0045 PR⑥ 서울시 역사마스터(OA-21232 subwayStationMaster) — 수도권 전체 역(2026-11-02 784역 · 서울 밖 279역 포함 · '
  '서울 경계 건물의 500m 안 경기 역도 잡힌다). station_id = BLDN_ID 원문 · station_nm = BLDN_NM 원문 · line_nm = ROUTE 원문 · '
  'lat/lng = WGS84 십진수 도 그대로(geom 은 그 점 · SRID 4326). name_norm = 공백 전부 제거 → 괄호와 그 안 제거(「잠실(송파구청)」 '
  '→ 「잠실」 · 적재기가 셈). group_id = 같은 역 묶음 — name_norm 이 같고 서로 600m 안(하버사인 · 사슬도 한 묶음)인 역들 '
  '(600m 넘어 갈리는 같은 이름 = 다른 역 — 양평 5호선/중앙선 · 운정 · 신촌 2호선/경의중앙선). has_ridership = 승하차 행이 한 번이라도 '
  '붙은 역(신분당선·GTX 등 서울시 승하차 자료 밖 노선 역은 false). 적재 scripts/collectors/load_seoul_subway.py(upsert · '
  '승하차가 가리키지 않는 사라진 역만 지움). 공개키 읽기 금지 — 화면은 list_nearby_subway 로만 읽는다';

alter table subway_station enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on subway_station from public, anon, authenticated;

-- 월별 승하차 — 서울시 원문 한 줄(달 · 원문 호선 · 원문 역)이 한 줄. 기본키 = 원문 열쇠(짝표 뒤 같은 마스터 역으로 원문 두
-- 줄이 모일 수 있다 — 창동 4호선 + 창동 경원선 · 공항철도 역의 경의선 라벨 줄 · 둘 다 진짜 자료라 합치지도 버리지도 않는다).
create table if not exists subway_ridership_m (
  use_mm        char(6) not null check (use_mm ~ '^\d{6}$'),
  ride_line_nm  text not null,
  ride_sttn_nm  text not null,
  station_id    text not null references subway_station (station_id),
  line_nm       text not null,
  on_sum        integer not null,
  off_sum       integer not null,
  on_h04        integer not null,
  on_h05        integer not null,
  on_h06        integer not null,
  on_h07        integer not null,
  on_h08        integer not null,
  on_h09        integer not null,
  on_h10        integer not null,
  on_h11        integer not null,
  on_h12        integer not null,
  on_h13        integer not null,
  on_h14        integer not null,
  on_h15        integer not null,
  on_h16        integer not null,
  on_h17        integer not null,
  on_h18        integer not null,
  on_h19        integer not null,
  on_h20        integer not null,
  on_h21        integer not null,
  on_h22        integer not null,
  on_h23        integer not null,
  on_h00        integer not null,
  on_h01        integer not null,
  on_h02        integer not null,
  on_h03        integer not null,
  off_h04       integer not null,
  off_h05       integer not null,
  off_h06       integer not null,
  off_h07       integer not null,
  off_h08       integer not null,
  off_h09       integer not null,
  off_h10       integer not null,
  off_h11       integer not null,
  off_h12       integer not null,
  off_h13       integer not null,
  off_h14       integer not null,
  off_h15       integer not null,
  off_h16       integer not null,
  off_h17       integer not null,
  off_h18       integer not null,
  off_h19       integer not null,
  off_h20       integer not null,
  off_h21       integer not null,
  off_h22       integer not null,
  off_h23       integer not null,
  off_h00       integer not null,
  off_h01       integer not null,
  off_h02       integer not null,
  off_h03       integer not null,
  job_ymd       date,
  loaded_at     timestamptz not null default now(),
  primary key (use_mm, ride_line_nm, ride_sttn_nm),
  check (on_sum >= 0 and off_sum >= 0)
);

create index if not exists idx_subway_ridership_station on subway_ridership_m (station_id, use_mm);

comment on table subway_ridership_m is
  '결정 0045 PR⑥ 서울시 지하철 호선별 역별 시간대별 승하차 인원(OA-12252 CardSubwayTime) — 교통카드(선후불 + 1회용) 개찰 '
  '기준 · 「환승객 여부와 상관없이 집계」(포털 FAQ — 환승 통로로 갈아탄 사람은 개찰을 안 지나 안 센다) · 공공누리 1유형. '
  '한 줄 = (달 use_mm, 원문 호선 ride_line_nm, 원문 역 ride_sttn_nm) · on_h04~on_h03 / off_h04~off_h03 = 그 달 합계 '
  '(서울시 칸 차례 4시 → 23시 → 0시 → 3시) · on_sum/off_sum = 24칸 합 · job_ymd = 서울시 작업일(다음 달 3일 꼴). '
  'station_id = 짝표(scripts/seeds/subway_*_map.csv) 뒤 붙은 역사마스터 역 · line_nm = 그 행이 붙은 호선(호선 짝표 뒤 글 · '
  '역 짝표 map 행은 원문 호선 그대로 — 단 호선 짝표로 바뀌는 경의선 라벨 행(계양·검암·김포공항)은 씨앗의 마스터 호선). '
  '⛔ 환승역은 서울시가 관리 호선 한 줄에 몰아 센다(충무로 3호선 하차 0) — 호선마다 줄을 세우지 말고 subway_station.group_id '
  '로 묶어 더한다. 같은 원문 줄이 두 번 온 달(202603·202607 — 값이 완전히 같음)은 적재기가 하나로 넣는다. '
  '적재 scripts/collectors/load_seoul_subway.py(달 단위 교체). 공개키 읽기 금지 — 화면은 list_nearby_subway 로만 읽는다';

alter table subway_ridership_m enable row level security;

-- ⛔ Supabase 는 새 표를 anon 에 자동으로 연다(pg_default_acl) — 만든 자리에서 닫는다.
revoke all on subway_ridership_m from public, anon, authenticated;

-- 필지에서 500m 안 서울 지하철 역 묶음마다(가까운 순 · 최대 10줄) 최근 12개월 하루 평균 승하차 + 시간대 여섯 칸.
--   상태 = no_coord → not_seoul → no_data → no_station(한 줄 · 가장 가까운 역이 1,500m 안이면 이름·호선·거리) → 묶음마다 ok.
create or replace function list_nearby_subway(p_pnu text)
returns table (
  status           text,
  group_id         integer,
  station_nm       text,
  lines            text[],
  lines_with_data  text[],
  dist_m           integer,
  has_data         boolean,
  window_from      char(6),
  window_to        char(6),
  months_n         integer,
  on_daily         integer,
  off_daily        integer,
  bins             jsonb,
  nearest_nm       text,
  nearest_lines    text[],
  nearest_dist_m   integer
)
language sql
stable
security definer
set search_path = public
as $$
  with me as (
    -- 좌표가 없으면 「역 없음」이라는 **단정**이 새어 나가지 않게 따로 가른다(no_coord).
    -- ⛔ pnu 칸은 char(19) — 인자를 그대로 견주면 칸 쪽이 text 로 캐스트돼 색인이 죽는다.
    select p.geom::geography as gg
    from parcel p
    where p.pnu = p_pnu::char(19) and p.geom is not null
  ),
  win as (
    -- 창 = 표 전체 기준 최근 12개월(👤 0045 ③-0 ⓕ) — 모든 역이 같은 창이다(역마다 제 최신 달로 잡지 않는다).
    select max(r.use_mm) as to_mm,
           to_char(to_date(max(r.use_mm), 'YYYYMM') - interval '11 months', 'YYYYMM') as from_mm
    from subway_ridership_m r
  ),
  near as (
    -- 반경 500m(구 판정 · 함정 8 — parcel.geom 점만 · bbox 선필터는 gist 가 스스로 한다).
    select s.station_id, s.group_id, st_distance(s.geom::geography, me.gg, false) as d
    from subway_station s cross join me
    where st_dwithin(s.geom::geography, me.gg, 500, false)
  ),
  head as (
    -- 건물 단위 상태 넷 — 판정 순서가 곧 뜻이다(위부터, 서로 배타).
    --   no_coord    필지 좌표 없음(서울이든 아니든 — 모르는 것은 모른다고)
    --   not_seoul   시·도가 서울이 아님(서울시 지하철 자료는 서울만)
    --   no_data     역사마스터가 비었거나 승하차 표가 비었음 — 화면은 덩이 자체를 안 그린다(적재 전 창에 「역 없음」이라는
    --               거짓이 서지 않게 · 메인 결정 ⓓ)
    --   no_station  500m 안 역 0(사실 — 서울 열린 건물 땅의 약 35.7% · 2026-11-02 실측)
    -- 넷 다 아니면 null → 묶음마다 ok 한 줄씩이 대신 나간다.
    select case
             when not exists (select 1 from me) then 'no_coord'
             when left(p_pnu::char(19), 2) <> '11' then 'not_seoul'
             when not exists (select 1 from subway_station) or (select w.to_mm from win w) is null then 'no_data'
             when not exists (select 1 from near) then 'no_station'
           end as status
  ),
  grp as (
    -- 반경 안 역이 든 묶음 — 거리 = 묶음 역 가운데 가장 가까운 점 · 가까운 순 10묶음까지.
    select n.group_id, min(n.d) as d
    from near n
    group by n.group_id
    order by min(n.d), n.group_id
    limit 10
  ),
  gst as (
    -- 묶음의 역 전부(500m 밖 같은 역사 역도 — 묶음 = 한 역사).
    select g.group_id, s.station_id, s.station_nm, s.line_nm
    from grp g join subway_station s on s.group_id = g.group_id
  ),
  rides as (
    -- 창 안 승하차 행 — 묶음 안 모든 역의 모든 원문 줄(환승역 몰아 세기가 여기서 합쳐진다).
    select gs.group_id, r.*
    from gst gs
    join subway_ridership_m r on r.station_id = gs.station_id
    cross join win w
    where r.use_mm between w.from_mm and w.to_mm
  ),
  days as (
    -- 분모 = 창 안 그 묶음이 **가진** 달들의 일수 합(빠진 달은 분모에도 안 넣는다 · 메인 결정 ⓔ).
    select m.group_id, count(*)::int as months_n,
           sum(extract(day from (to_date(m.use_mm, 'YYYYMM') + interval '1 month' - interval '1 day')))::int as n_days
    from (select distinct x.group_id, x.use_mm from rides x) m
    group by m.group_id
  ),
  agg as (
    -- 시간대 여섯 칸(👤 Q4 「나」) = 4~7 · 7~10 · 10~14 · 14~17 · 17~21 · 21~(다음 날 4시 전까지).
    select x.group_id,
           sum(x.on_sum)::numeric as on_s, sum(x.off_sum)::numeric as off_s,
           sum(x.on_h04 + x.on_h05 + x.on_h06)::numeric as on_1,
           sum(x.off_h04 + x.off_h05 + x.off_h06)::numeric as off_1,
           sum(x.on_h07 + x.on_h08 + x.on_h09)::numeric as on_2,
           sum(x.off_h07 + x.off_h08 + x.off_h09)::numeric as off_2,
           sum(x.on_h10 + x.on_h11 + x.on_h12 + x.on_h13)::numeric as on_3,
           sum(x.off_h10 + x.off_h11 + x.off_h12 + x.off_h13)::numeric as off_3,
           sum(x.on_h14 + x.on_h15 + x.on_h16)::numeric as on_4,
           sum(x.off_h14 + x.off_h15 + x.off_h16)::numeric as off_4,
           sum(x.on_h17 + x.on_h18 + x.on_h19 + x.on_h20)::numeric as on_5,
           sum(x.off_h17 + x.off_h18 + x.off_h19 + x.off_h20)::numeric as off_5,
           sum(x.on_h21 + x.on_h22 + x.on_h23 + x.on_h00 + x.on_h01 + x.on_h02 + x.on_h03)::numeric as on_6,
           sum(x.off_h21 + x.off_h22 + x.off_h23 + x.off_h00 + x.off_h01 + x.off_h02 + x.off_h03)::numeric as off_6,
           array_agg(distinct x.line_nm order by x.line_nm) as lines_with_data
    from rides x
    group by x.group_id
  ),
  glines as (
    -- 호선 = 묶음 역들의 마스터 호선 ∪ 창 안 붙은 승하차 행의 호선(⊇ lines_with_data · 메인 결정 ⑥-1).
    select u.group_id, array_agg(distinct u.ln order by u.ln) as lines
    from (select gs.group_id, gs.line_nm as ln from gst gs
          union
          select x.group_id, x.line_nm from rides x) u
    group by u.group_id
  ),
  rep as (
    -- 묶음 대표 이름 = station_id 가 가장 작은 역의 원문 이름.
    select distinct on (gs.group_id) gs.group_id, gs.station_nm
    from gst gs
    order by gs.group_id, gs.station_id
  ),
  nearest as (
    -- no_station 줄의 가장 가까운 역 하나(KNN) — 1,500m 안일 때만 이름·호선·거리를 낸다(👤 Q3 「가」 · 승하차 수는 안 냄).
    select s.group_id, st_distance(s.geom::geography, me.gg, false) as d
    from subway_station s cross join me
    order by s.geom::geography <-> me.gg
    limit 1
  ),
  nearest_out as (
    select (select r.station_nm from subway_station r where r.group_id = nr.group_id
             order by r.station_id limit 1) as nm,
           (select array_agg(distinct r.line_nm order by r.line_nm) from subway_station r
             where r.group_id = nr.group_id) as lines,
           round(nr.d)::int as dist_m
    from nearest nr
    where nr.d <= 1500
  ),
  rows_out as (
    -- 빈 상태 넷은 한 줄(status 만 값 · no_station 만 가장 가까운 역 셋).
    select hd.status,
           null::integer as group_id, null::text as station_nm, null::text[] as lines,
           null::text[] as lines_with_data, null::integer as dist_m, null::boolean as has_data,
           null::char(6) as window_from, null::char(6) as window_to, null::integer as months_n,
           null::integer as on_daily, null::integer as off_daily, null::jsonb as bins,
           (select o.nm from nearest_out o where hd.status = 'no_station') as nearest_nm,
           (select o.lines from nearest_out o where hd.status = 'no_station') as nearest_lines,
           (select o.dist_m from nearest_out o where hd.status = 'no_station') as nearest_dist_m,
           0::double precision as sort_d, 0 as sort_g
    from head hd
    where hd.status is not null
    union all
    -- 묶음마다 ok — 하루 평균 = Σ(창 안 합) ÷ Σ(그 달들의 일수)(월별 평균의 평균이 아니다 · 메인 결정 ⓔ).
    -- 창 안 승하차가 없는 묶음(신분당선 등 서울시 자료 밖 노선 역)은 has_data false · 숫자 칸 null(👤 Q2 「가」).
    select 'ok', g.group_id, rp.station_nm, gl.lines, a.lines_with_data, round(g.d)::int,
           a.group_id is not null,
           w.from_mm::char(6), w.to_mm::char(6), coalesce(dy.months_n, 0),
           round(a.on_s / dy.n_days)::int, round(a.off_s / dy.n_days)::int,
           case when a.group_id is not null then jsonb_build_object(
             'h04_07', jsonb_build_object('on', round(a.on_1 / dy.n_days)::int, 'off', round(a.off_1 / dy.n_days)::int),
             'h07_10', jsonb_build_object('on', round(a.on_2 / dy.n_days)::int, 'off', round(a.off_2 / dy.n_days)::int),
             'h10_14', jsonb_build_object('on', round(a.on_3 / dy.n_days)::int, 'off', round(a.off_3 / dy.n_days)::int),
             'h14_17', jsonb_build_object('on', round(a.on_4 / dy.n_days)::int, 'off', round(a.off_4 / dy.n_days)::int),
             'h17_21', jsonb_build_object('on', round(a.on_5 / dy.n_days)::int, 'off', round(a.off_5 / dy.n_days)::int),
             'h21_04', jsonb_build_object('on', round(a.on_6 / dy.n_days)::int, 'off', round(a.off_6 / dy.n_days)::int))
           end,
           null::text, null::text[], null::integer,
           g.d, g.group_id
    from grp g
    cross join win w
    join rep rp on rp.group_id = g.group_id
    join glines gl on gl.group_id = g.group_id
    left join agg a on a.group_id = g.group_id
    left join days dy on dy.group_id = g.group_id
    where (select hd.status from head hd) is null
  )
  select ro.status, ro.group_id, ro.station_nm, ro.lines, ro.lines_with_data, ro.dist_m, ro.has_data,
         ro.window_from, ro.window_to, ro.months_n, ro.on_daily, ro.off_daily, ro.bins,
         ro.nearest_nm, ro.nearest_lines, ro.nearest_dist_m
  from rows_out ro
  -- 가까운 묶음이 먼저(거리 같으면 묶음 번호 차례).
  order by ro.sort_d, ro.sort_g;
$$;

comment on function list_nearby_subway(text) is
  '결정 0045 PR⑥ 이 필지에서 반경 500m 안 서울 지하철 역 묶음마다(가까운 순 · 최대 10줄) 서울시 공표 교통카드 승하차 — '
  '묶음 = 정규화 이름이 같고 서로 600m 안인 역들(환승역 · 서울시가 관리 호선 한 줄에 몰아 세므로 호선마다 따로 내지 않는다 — '
  '충무로 3호선 하차 0). 줄마다 대표 이름 · 호선 전부(lines = 마스터 호선 ∪ 붙은 승하차 호선) · 창 안 자료가 있는 호선 · 거리(m · '
  '묶음 역 가운데 가장 가까운 점) · 창(표 전체 최근 달 기준 12개월 · window_from~window_to) · 그 묶음이 가진 달 수 months_n · '
  '하루 평균 승차·하차(창 안 합 ÷ 그 달들의 일수 합) · 시간대 여섯 칸 bins(h04_07 · h07_10 · h10_14 · h14_17 · h17_21 · h21_04 '
  '마다 on·off 하루 평균). 창 안 승하차가 없는 묶음(신분당선·GTX 등 서울시 자료 밖 노선)은 has_data false · 숫자 null. '
  '상태(위부터 배타): no_coord(필지 좌표 없음) → not_seoul(서울 아님) → no_data(역사마스터나 승하차 표가 비었음 — 화면은 덩이를 '
  '안 그린다) → no_station(500m 안 역 0 · 한 줄 · 가장 가까운 역이 1,500m 안이면 nearest_nm·nearest_lines·nearest_dist_m) → '
  '묶음마다 ok. 역 승하차 수이지 이 건물 앞을 지나는 사람 수(유동인구)가 아니고 이 건물의 값이 아니다. '
  'security definer (subway_station·subway_ridership_m·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 역 이름·호선·거리와 역 묶음 합계 수뿐이다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function list_nearby_subway(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_nearby_subway(p_pnu text)
returns table (
  status           text,
  group_id         integer,
  station_nm       text,
  lines            text[],
  lines_with_data  text[],
  dist_m           integer,
  has_data         boolean,
  window_from      char(6),
  window_to        char(6),
  months_n         integer,
  on_daily         integer,
  off_daily        integer,
  bins             jsonb,
  nearest_nm       text,
  nearest_lines    text[],
  nearest_dist_m   integer
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_nearby_subway(p_pnu) $$;

revoke all on function api.list_nearby_subway(text) from public, anon, authenticated;
grant execute on function api.list_nearby_subway(text) to anon, authenticated;

-- ⛔ public.list_nearby_subway 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.

-- ── 신선도 표 18번 줄(지하철 승하차) · 서울시 세 줄 + 6개월 ─────────────────────────────────
-- 승하차 표(위)를 읽으므로 표 **뒤**에 다시 만든다.
create or replace function get_data_freshness()
returns table (
  src           text,
  basis_kind    text,
  basis         text,
  next_expected date,
  cadence       text
)
language sql
stable
security definer
set search_path = public
as $$
  with raw as (
    -- ⓘ 순서를 ord 로 못 박는다. union all 은 순서를 보장하지 않으므로, 이 숫자가 없으면
    --   화면의 줄 순서가 실행할 때마다 달라질 수 있다(사람은 그걸 자료가 바뀐 것으로 읽는다).
    select 1 as ord,
           '점포·업종 (상권정보)'::text as src,
           '분기'::text                 as basis_kind,
           (select r.published_ym::text from snapshot_release r) as basis,
           'sangkwon'::text             as rule_kind,
           '분기마다 (다음 분기 자료가 공개되면 사람이 적재)'::text as cadence
    union all
    -- 2026-10-15a — 실거래는 매달 최근 6개월을 다시 받는다(사장님 결정 2026-10-15 · 규칙 'tx').
    select 2, '실거래 (매매)', '계약월',
           (select max(t.contract_ym)::text from transaction t),
           'tx',
           '월 1회 (최근 6개월 다시 받기)'
    union all
    -- 2026-10-15a — 기준은 적재일(max(building.updated_at))이 아니라 표지의 판이다(30개 구를 다 넣은 뒤
    --   사람이 올린다). 규칙은 인허가와 같은 월간 갈래 — 건축HUB 일괄 파일도 다음 달 20일 무렵 게시된다.
    select 3, '건축물대장', '판',
           (select r.release_ym::text from ledger_release r),
           'permit',
           '월간 파일 (사람이 적재)'
    union all
    select 4, '상권 경계', '계산일',
           (select (max(t.computed_at) at time zone 'Asia/Seoul')::date::text from district t),
           'none',
           '비정기 (원천이 바뀌면)'
    union all
    select 5, 'LH 상가 공고', '수집일',
           (select (max(t.collected_at) at time zone 'Asia/Seoul')::date::text from lh_notice t),
           'none',
           '주 1회 감시 · 적재는 사람'
    union all
    select 6, '건축 인허가', '기준월',
           (select max(t.loaded_ym)::text from arch_permit t),
           'permit',
           '월 1회'
    union all
    select 7, '국세청 기준시가', '고시일',
           (select max(t.notice_date)::text from nts_base_price t),
           'nts',
           '연 1회 (매년 3월 고시)'
    union all
    select 8, '상권 임대 동향 (부동산원)', '분기',
           (select max(t.quarter)::text from rent_stat t),
           'rone',
           '분기마다'
    union all
    -- ⓘ 9번(옛 성적표 줄)은 2026-10-18a(결정 0041)에 뺐다 — 뒤 번호는 그대로 둔다(순서만 정하는 칸이다).
    -- 2026-10-12b — 기준은 우리가 받아 둔 날(updated_at)이 아니라 개별공시지가의 공시 연도다
    --   (사장님 결정 2026-10-12). smallint 라 '2026' 네 자리로 나온다.
    select 10, '필지 (토지 특성)', '공시 연도',
           (select max(t.land_price_year)::text from parcel t),
           'land_year',
           '연 1회 (브이월드)'
    union all
    -- 결정 0033 — 서울시 상권분석서비스 개업·폐업. 분기 꼴이 'YYYYQ' 다섯 자리(Q 없음)다.
    select 11, '상권 개업·폐업 (서울시)', '분기',
           (select max(t.quarter)::text from district_openclose t),
           'seoul_openclose',
           '분기마다'
    union all
    -- 2026-10-29a(결정 0044) — 대전시 동네 폐업. 기준 = 사람이 대전시 사이트에서 받은 날(표지 한 줄)이다.
    select 12, '동네 폐업 (대전시)', '받은 날',
           (select r.received_on::text from daejeon_closure_release r),
           'daejeon_closure',
           '분기마다 (사람이 대전시 사이트에서 받음)'
    union all
    -- 2026-10-31a(결정 0045) — 서울시 상권분석서비스 추정매출·길단위인구. 분기 꼴은 개업·폐업과 같은 'YYYYQ' 라
    --   같은 규칙(seoul_openclose — 분기말 + 6개월 - 하루 · 👤 2026-11-02 「가」 · 2026-11-02a 부터)을 쓴다.
    select 13, '상권 추정매출 (서울시)', '분기',
           (select max(t.quarter)::text from district_sales t),
           'seoul_openclose',
           '분기마다'
    union all
    select 14, '상권 길단위인구 (서울시)', '분기',
           (select max(t.quarter)::text from district_pop_flow t),
           'seoul_openclose',
           '분기마다'
    union all
    -- 2026-10-31a(결정 0045 · 사장님 결정 10-31 「다음 예정 없음」) — 상주·직장인구는 한 줄. 기준 = 값이 마지막으로
    --   바뀐 분기 둘을 글로 합친다(표지 seoul_trdar_release). 서울시 공지는 연 1회지만 실제 갱신이 불규칙(상주
    --   2024·2025 건너뜀)이라 예정일을 계산하지 않는다('none' → null). 표지가 비면 basis 도 null(화면 '자료 없음').
    select 15, '상권 상주·직장인구 (서울시)', '값이 바뀐 분기',
           (select '상주 ' || left(a.value_quarter, 4) || '년 ' || right(a.value_quarter, 1) || '분기, 직장 '
                   || left(b.value_quarter, 4) || '년 ' || right(b.value_quarter, 1) || '분기'
              from seoul_trdar_release a, seoul_trdar_release b
             where a.tbl = 'district_pop_resident' and b.tbl = 'district_pop_worker'),
           'none',
           '연 1회 (서울시 공지) · 실제는 불규칙 — 예정일 계산 안 함'
    union all
    -- 2026-11-01a(결정 0045 PR④) — 가게 이력 결과표의 마지막 분기. 점포 줄(ord 1)과 같은 `sangkwon` 규칙 — 같은 분기면
    --   같은 날 「지났습니다」가 뜬다(정상 · 새 분기 적재 → 빌드 → 적재 순서). 표지가 비면 basis null(화면 '자료 없음').
    select 16, '가게 이력 (점포 자료 누적)', '분기',
           (select r.last_ym::text from store_history_release r),
           'sangkwon',
           '분기마다 (새 분기 점포 자료를 적재한 뒤 다시 굽는다)'
    union all
    -- 2026-11-01b(결정 0045 PR⑤) — SGIS 집계구 통계를 대전 상권에 나눠 담은 결과표의 받은 날(표지 sgis_census_release).
    --   사람이 SGIS 자료제공에서 연 1회 신청해 받는다 — 받은 날 + 12개월(규칙 'sgis'). 표지가 비면 basis null(화면 '자료 없음').
    select 17, '상권 인구 (통계청 집계구)', '받은 날',
           (select r.received_on::text from sgis_census_release r),
           'sgis',
           '연 1회 (사람이 SGIS 자료제공에서 신청해 받음)'
    union all
    -- 2026-11-02a(결정 0045 PR⑥) — 서울시 지하철 승하차의 기준월(표 전체 max(use_mm) — 기본키 첫 칸이 받친다).
    --   서울시가 매달 5일 무렵 전월분을 게시한다 — 기준월 + 2개월의 5일(규칙 'subway'). 표가 비면 basis null(화면 '자료 없음').
    select 18, '지하철 승하차 (서울시)', '기준월',
           (select max(t.use_mm)::text from subway_ridership_m t),
           'subway',
           '매달 (서울시가 다음 달 5일 무렵 전월분 게시)'
  ),
  norm as (
    -- 분기 규칙을 쓰는 세 줄을 **같은 모양('YYYYMM' 분기말 달)** 으로 맞춘다. 이렇게 해야
    -- 아래 계산이 한 번만 적힌다 — 세 벌로 적어 두면 한쪽만 고쳐지는 날 자료끼리 서로
    -- 다른 주기를 말한다.
    -- ⛔ 서울시 분기 꼴('20262')은 둘째 갈래(`YYYYQn`)에도 첫째 갈래(여섯 자리)에도 안 걸린다 —
    --   셋째 갈래가 없으면 그 줄은 에러 없이 '정해진 주기 없음'(null)이 된다(결정 0033 v3 재검사).
    select r.*,
           case
             when r.rule_kind = 'sangkwon' and r.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
               then r.basis
             when r.rule_kind = 'rone' and r.basis ~ '^\d{4}Q[1-4]$'
               then left(r.basis, 4) || lpad((right(r.basis, 1)::int * 3)::text, 2, '0')
             when r.rule_kind = 'seoul_openclose' and r.basis ~ '^\d{4}[1-4]$'
               then left(r.basis, 4) || lpad((right(r.basis, 1)::int * 3)::text, 2, '0')
           end as q_ym
    from raw r
  )
  select n.src,
         n.basis_kind,
         n.basis,
         case
           -- 서울시 상권분석서비스 분기 자료(개업·폐업·추정매출·길단위인구 — 'seoul_openclose'): 분기말 + 6개월 - 하루
           --   (👤 2026-11-02 「가」 · 2026-11-02a — 서울시 안내문 「1분기 5월 말 · 2분기 8월 말 · 3분기 11월 말 ·
           --   4분기 다음 해 2월 말」 게시). 아래 일반 분기 갈래보다 **앞**에 둔다(case 는 위에서부터 고른다).
           when n.q_ym is not null and n.rule_kind = 'seoul_openclose'
             then (to_date(n.q_ym, 'YYYYMM') + interval '6 months' - interval '1 day')::date
           -- 분기 자료(상권정보 · 부동산원 · 가게 이력): 다음 분기가 **공개되는 달**의 말일(분기말 + 5개월 - 하루).
           when n.q_ym is not null
             then (to_date(n.q_ym, 'YYYYMM') + interval '5 months' - interval '1 day')::date
           -- 월간 자료(인허가 기준월 · 건축물대장 판): 다음 판이 **공개되는 달**의 말일(기준월 + 3개월 - 하루).
           when n.rule_kind = 'permit' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '3 months' - interval '1 day')::date
           -- 실거래: 계약월 + 2개월 - 하루(사장님 결정 2026-10-15 — 매달 최근 6개월을 다시 받는다).
           when n.rule_kind = 'tx' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '2 months' - interval '1 day')::date
           -- 연 1회: 다음 해 3월 31일(국세청 고시가 매년 3월).
           when n.rule_kind = 'nts' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then make_date(left(n.basis, 4)::int + 1, 3, 31)
           -- 연 1회: 개별공시지가는 공시 연도의 다음 해 6월 30일(사장님 결정 2026-10-12).
           --   네 자리 연도일 때만 — 모양이 다르면 ::int 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'land_year' and n.basis ~ '^\d{4}$'
             then make_date(n.basis::int + 1, 6, 30)
           -- 대전시 동네 폐업: 받은 날 + 3개월(분기마다 사람이 받는다 — 2026-10-29a · 결정 0044).
           --   'YYYY-MM-DD' 일 때만 — 모양이 다르면 ::date 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'daejeon_closure' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then (n.basis::date + interval '3 months')::date
           -- SGIS 상권 인구: 받은 날 + 12개월(연 1회 사람이 신청해 받는다 — 2026-11-01b · 결정 0045 PR⑤).
           --   'YYYY-MM-DD' 일 때만 — 모양이 다르면 ::date 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'sgis' and n.basis ~ '^\d{4}-\d{2}-\d{2}$'
             then (n.basis::date + interval '12 months')::date
           -- 지하철 승하차(서울시): 기준월 + 2개월의 5일(서울시가 매달 5일 무렵 전월분 게시 — 2026-11-02a · 결정 0045 PR⑥).
           --   'YYYYMM' 일 때만 — 모양이 다르면 to_date 가 터져 표가 통째로 사라진다.
           when n.rule_kind = 'subway' and n.basis ~ '^\d{4}(0[1-9]|1[0-2])$'
             then (to_date(n.basis, 'YYYYMM') + interval '2 months' + interval '4 days')::date
         end as next_expected,
         n.cadence
  from norm n
  order by n.ord;
$$;

comment on function get_data_freshness() is
  '화면 아래 "이 자료는 언제 것인가" 표. 열일곱 갈래 자료의 가장 최근 도장(분기·계약월·판·'
  '계산일·수집일·기준월·고시일·공시 연도·받은 날·값이 바뀐 분기)을 창고에서 읽어 한 줄씩 준다. '
  '⛔ 숫자를 화면에 박지 않기 위한 함수다 — 신선도를 글자로 적어 두면 적재하는 순간부터 '
  '그 글자만 거짓말을 한다. next_expected 도 사람이 적는 값이 아니라 규칙으로 계산한다: '
  '분기 자료는 분기말 달 + 5개월 - 하루(다음 분기가 공개되는 달의 말일 · 서울시 상권분석서비스 분기 자료는 + 6개월 - 하루 — 분기 꼴 셋 '
  '''YYYYMM''·''YYYYQn''·''YYYYQ''(서울시 다섯 자리)를 같은 분기말 달로 맞춘 뒤 한 번만 계산), 월간 자료'
  '(인허가 기준월·건축물대장 판)는 기준월 + 3개월 - 하루(다음 판이 공개되는 달의 말일), 실거래는 계약월 + '
  '2개월 - 하루(매달 최근 6개월을 다시 받는다), 국세청 기준시가는 고시일의 다음 해 3월 31일, '
  '필지(개별공시지가)는 공시 연도의 다음 해 6월 30일(기준값이 네 자리 연도일 때만), 대전시 동네 폐업은 '
  '받은 날 + 3개월(분기마다 사람이 받는다 · 기준값이 YYYY-MM-DD 일 때만), SGIS 상권 인구는 받은 날 + 12개월(연 1회 · 같은 모양일 때만), 지하철 승하차(서울시)는 기준월 + 2개월의 5일(매달 · YYYYMM 일 때만). '
  '서울 상권 추정매출·길단위인구는 '
  '개업·폐업과 같은 분기 규칙(분기말 + 6개월 - 하루 — 서울시 안내문의 게시 달 말일)이고, 서울 상권 상주·직장인구는 실제 갱신이 불규칙해 예정일을 계산하지 않는다'
  '(기준 = 값이 마지막으로 바뀐 분기 둘을 글로 합침). '
  '주기가 없는 자료는 null 이다 — 없는 주기를 지어내면 "늦었다"는 거짓 신호가 뜬다. '
  '기준값이 그 모양이 아니면 계산하지 않고 그 칸만 비운다(to_date 가 터지면 표가 통째로 '
  '사라진다). timestamptz 는 전부 Asia/Seoul 로 옮겨 날짜를 자른다 — 이 DB 가 UTC 라 '
  '그냥 자르면 한국 새벽 0~9시에 어제 날짜가 찍힌다. '
  '⛔ api_quota_log 는 안 본다 — 그건 우리 호출 장부이지 자료의 나이가 아니고, 하한선일 뿐이다. '
  '자료가 0행이면 basis 가 null 이고 줄은 그대로 나온다(화면이 "자료 없음"이라 적는다 — '
  '줄을 빼면 "그런 자료를 안 쓴다"로 읽힌다). '
  'security definer (열일곱 표가 전부 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 집계 도장 열일곱 개뿐이고 원본 행은 한 줄도 안 나간다). 2026-09-05d · 월간 규칙 2026-10-01a · '
  '서울 개업·폐업 2026-10-05b · 필지 공시 연도 2026-10-12b · 실거래·대장 판 월간 규칙 2026-10-15a · '
  '성적표 줄 뺌 2026-10-18a(결정 0041) · 대전시 동네 폐업 2026-10-29a(결정 0044) · 서울 상권 4종 세 줄 2026-10-31a(결정 0045) · 가게 이력 2026-11-01a(결정 0045 PR④) · SGIS 상권 인구 2026-11-01b(결정 0045 PR⑤) · 지하철 승하차·서울시 세 줄 + 6개월 2026-11-02a(결정 0045 PR⑥)';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function get_data_freshness() from public, anon, authenticated;

commit;

notify pgrst, 'reload schema';
