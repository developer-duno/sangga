-- =====================================================================
-- 마이그레이션 2026-08-24a — 층별 화면에 건물 스펙 4칸을 내보낸다
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로 돌린다.** 전부 메타데이터 조작이라 빠르고,
--   한 트랜잭션에 들어간다(중간에 실패하면 통째로 없던 일이 된다).
--   → 붙여넣고 Run → 아래 6) 검산 쿼리 → `python scripts/post_load.py --check`.
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 하나 (로드맵 Wave 2 PR-B)
-- ─────────────────────────────────────────────────────────────────────
-- `building` 표에는 연면적·용적률·건폐율·주차대수가 이미 들어와 있는데(건축HUB 대장,
-- A등급 실측) 화면이 읽는 뷰가 그 넷을 안 내보낸다. 그래서 사람이 건물을 봐도
-- "이 건물이 얼마나 큰가"를 못 본다 — 자료가 없어서가 아니라 **창구가 없어서**다.
-- 이 마이그레이션은 뷰 끝에 네 칸을 덧붙이기만 한다(계산 0, 새 표 0).
--
-- ⛔ 이 값들의 함정 — **0 은 "0" 이 아니라 "미기재"다**
--    대장이 안 적은 칸을 원본이 NULL 이 아니라 '0' 으로 준다. 실제로 롯데월드타워가
--    주차 0·건폐율 0 으로 들어와 있어, "정말 0" 과 "안 적힘" 을 값으로는 못 가른다.
--    ⓘ "NULL 이 0행" 은 **현재 적재분(서울·대전 30개 구)의 관찰값**이지 구조적 보장이
--      아니다 — 적재기는 결측을 NULL 로 쓴다(load_building_ledger.py 의 `_to_float`,
--      주차는 `sum_parking` 이 4종 전부 결측일 때 None). 즉 NULL 이 생길 수 있는 길은
--      열려 있고, [C] 전국 적재 뒤에는 **다시 세어 봐야 한다**(§5 검산의 parking_null).
--      화면은 어차피 NULL·0 을 똑같이 "미상"으로 적으므로 어느 쪽이어도 안 깨진다.
--    **뷰에서는 원본 그대로 내보내고**(서버가 뜻을 지어내지 않는다), 0 을 "미상"으로
--    읽는 판단은 화면 한 곳에서만 한다(src/components/FloorStack.tsx 의 `describeSpec`).
-- ⓘ `parking_cnt` 는 한 숫자가 아니라 **주차 4종의 합**이다 — 옥내자주·옥내기계·
--    옥외자주·옥외기계(indr/oudr × Auto/Mech). 일부만 적힌 대장이면 적힌 것만 더한
--    **부분합**이라 실제 주차대수보다 작을 수 있다(load_building_ledger.py `sum_parking`).
-- ⛔ `bcr`(건폐율)에는 소스 오류가 섞여 있다 — 2026-08-11 실측으로 24만 행 중 7행이
--    1만%를 넘고 최댓값이 79,095% 다(building.bcr 컬럼 주석). 상한도 화면이 건다.
--
-- ⚠️ **api 쌍둥이를 반드시 다시 만든다** (2026-08-22 실측 불변식)
--    `api.v_floor_stack` 은 `select * from public.v_floor_stack` 로 만들었지만,
--    뷰의 `*` 는 **만들 때의 칼럼 목록으로 굳는다.** public 뷰에 칼럼을 덧붙여도
--    쌍둥이는 옛 칼럼만 낸다 — 에러가 아니라 **조용한 누락**이라 아무도 모른다.
--    그래서 이 파일은 ① public 뷰 교체 → ② api 쌍둥이 재생성 → ③ 스키마 리로드
--    3종 세트다. 순서를 바꾸면 ②가 옛 목록을 다시 굳힌다.
--
-- ⚠️ `create or replace view` 는 **칼럼을 끝에 더하는 것만** 된다. 기존 칼럼의
--    이름·순서·타입을 바꾸거나 지우려 하면 PostgreSQL 이 거절한다(그래서 아래 정의는
--    기존 목록을 한 글자도 안 건드리고 뒤에만 넷을 붙였다). drop 하지 말 것 —
--    drop 하면 그 사이 화면이 통째로 죽고, 권한·주석도 같이 날아간다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 적용 순서
-- ─────────────────────────────────────────────────────────────────────
--   ① 이 파일을 SQL Editor 에서 Run.
--   ② 아래 6) 검산 — 새 4칸이 api 쪽에서도 실제로 나오는지 본다.
--      ⚠️ 이게 머지 조건이다. E2E 는 REST 를 모킹하므로 라이브 드리프트를 못 잡는다.
--   ③ 화면 배포. 값이 안 오면 4칸이 전부 "미상"으로 보일 뿐 화면은 안 죽는다
--      (칼럼이 없으면 undefined → 미상). 즉 ①과 ③ 사이에 죽는 구간이 없다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 되돌리기
-- ─────────────────────────────────────────────────────────────────────
-- 2026-08-13c 의 뷰 정의(= 이 파일에서 끝 4줄을 뺀 것)를 다시 Run 하면 된다…가
-- **아니다.** `create or replace` 는 칼럼을 못 지운다. 정말 되돌리려면
-- `drop view api.v_floor_stack; drop view public.v_floor_stack;` 뒤에 옛 정의를
-- 새로 만들고 권한(`grant select ... to anon, authenticated`)과
-- `alter view ... set (security_invoker = false)` 를 다시 걸어야 한다.
-- 그럴 일은 거의 없다 — 칼럼이 남아 있어도 화면이 안 읽으면 그만이다.
-- =====================================================================


-- =====================================================================
-- 1) public.v_floor_stack — 기존 목록 그대로 + 끝에 건물 스펙 4칸
-- =====================================================================
create or replace view v_floor_stack as
select
  s.bld_id,
  s.pnu,
  s.floor_no,
  s.floor_label,
  s.floor_area_m2,
  s.floor_area_gross_m2,
  s.segment_cnt,
  s.main_use,
  s.uses,
  -- ⚠️ 원본 건물명이 아니라 화면에 보일 이름이다(동명칭 폴백 + 개인 성명 가림).
  --    원본은 building.bld_nm 에 그대로 있고, 이 뷰는 내보낼 때만 가린다.
  b.display_nm as bld_nm,   -- 함수를 부르지 않는다(2026-08-13c 저장 컬럼)
  b.approve_date,
  b.is_jiphap,
  p.road_addr,
  p.road_contact,
  pb.bld_cnt_in_pnu,
  st.store_cnt,
  st.stores,
  -- ── 여기부터 2026-08-24a 가 더한 건물 스펙 4칸 ─────────────────────────
  -- 층이 아니라 **건물 한 채**의 값이라 같은 건물의 모든 층 행에 같은 값이 실린다
  -- (화면은 head 행 하나만 읽는다). 원본을 그대로 낸다 — 0 을 NULL 로 바꾸는 것도
  -- 상한을 거는 것도 여기서 하지 않는다. 서버가 뜻을 지어내면 나중에 그 판단을
  -- 누가 어디서 했는지 못 찾는다(집계·백테스트는 원본이 필요하다).
  -- ⛔ 0 은 "0" 이 아니라 **대장 미기재**다 — 롯데월드타워가 주차 0·건폐율 0 으로
  --    들어와 있어 값으로는 둘을 못 가른다. "NULL 이 0행" 은 현재 적재분(서울·대전
  --    30개 구)의 관찰값이지 구조적 보장이 아니다(적재기는 결측을 NULL 로 쓴다 —
  --    load_building_ledger.py 의 _to_float·sum_parking). [C] 전국 적재 후 다시 셀 것.
  b.total_area_m2,          -- 연면적 ㎡ (0 = 미기재)
  b.far,                    -- 용적률 % (0 = 미기재)
  b.bcr,                    -- 건폐율 % (0 = 미기재, 소스 오류로 100 초과 실재)
  b.parking_cnt             -- 주차 4종(옥내외 × 자주/기계) 합 (0 = 미기재, 일부만 적힌 대장이면 부분합)
from v_building_floor_stack s
join building b on b.bld_id = s.bld_id
join parcel   p on p.pnu    = s.pnu
join lateral (
  select count(*)::int as bld_cnt_in_pnu
  from building b2
  where b2.pnu = s.pnu
) pb on true
left join lateral (
  select
    count(*)::int as store_cnt,
    jsonb_agg(jsonb_build_object('name', ub.biz_name, 'cat', ub.cat_s_nm)) as stores
  from unit_business ub
  where ub.pnu = s.pnu
    and ub.floor_no = s.floor_no
    and ub.snapshot_ym = (select max(snapshot_ym) from unit_business)
) st on true;

comment on view v_floor_stack is
  '§8.6 층별 스택 뷰. store_cnt/stores는 (PNU, 층) 매칭이라 bld_cnt_in_pnu>1이면 건물 간 중복 — D등급 표시 필수. '
  '★ 공개 접근: 이 뷰만 anon/authenticated에게 SELECT 허용된다(아래 "공개 접근 정책" 절). '
  '원본 표는 RLS 켬 + 정책 0개 + 권한 회수로 닫혀 있고, 이 뷰가 소유자 권한으로 대신 읽는다. '
  '⚠️ bld_nm은 원본이 아니라 building_display_nm() 결과다(동명칭 폴백 + 개인 성명 가림, 2026-08-08e). '
  '⚠️ total_area_m2·far·bcr·parking_cnt 는 **건물 한 채**의 값이라 층마다 되풀이된다. '
  '0 은 "0" 이 아니라 "대장 미기재"다(NULL 은 현재 적재분 30개 구에서 0행 — 관찰값이지 보장이 아니다. '
  '적재기는 결측을 NULL 로 쓴다: load_building_ledger.py 의 _to_float·sum_parking. 전국 적재 후 다시 셀 것). '
  'bcr 은 소스 오류로 100 을 넘는 행이 있고, parking_cnt 는 주차 4종(옥내외 × 자주/기계) 합이라 '
  '일부만 적힌 대장이면 부분합이다 — 뜻풀이·상한은 화면이 한 곳에서 한다(2026-08-24a). '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표 401 + 상호명·성명 노출 확대. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';


-- =====================================================================
-- 2) api 쌍둥이 재생성 — `select *` 는 만들 때 굳는다
-- =====================================================================
-- 이 한 줄이 빠지면 화면(스키마 api)은 새 4칸을 **영영 못 본다.** public 쪽만 보고
-- "칼럼 늘었네" 하고 넘어가는 것이 이 변경의 가장 흔한 실패다.
create or replace view api.v_floor_stack as select * from public.v_floor_stack;


-- =====================================================================
-- 3) 권한 재확인 — 회수 먼저, 그다음 부여
-- =====================================================================
-- `create or replace view` 는 원칙적으로 기존 권한을 보존한다. 그래도 다시 적는 이유:
-- Supabase 는 새 객체마다 anon 에 권한을 자동으로 붙이고(pg_default_acl), 그 자동
-- 부여에는 INSERT·DELETE 가 섞여 있었다(2026-08-22 라이브 실측). `grant` 는 더하기라
-- 자동으로 붙은 쓰기를 못 걷어낸다 — 그래서 **회수를 먼저** 한다.
revoke all on api.v_floor_stack from public, anon, authenticated;
grant select on api.v_floor_stack to anon, authenticated;

-- ℹ️ **public.v_floor_stack 에는 revoke 를 걸지 않는다.** 정본이 이미 그렇게 정해 뒀다 —
--    이 뷰는 라이브·새 환경 둘 다 SELECT 하나뿐인 것이 실측됐고(2026-08-22, 어긋나 있던
--    것은 v_coverage_stats 쪽뿐), 여기서 회수를 새로 걸면 그 결정과 두 곳이 갈라진다.
--    읽기 권한만 한 번 더 못 박는다(있으면 아무 일도 안 일어나는 문장이다).
grant select on v_floor_stack to anon, authenticated;

-- 뷰가 소유자(postgres) 권한으로 원본 표를 읽는다는 뜻. 이게 false 라야 RLS 로 닫아 둔
-- 원본 표를 뷰가 대신 읽어 줄 수 있다(true 면 화면이 통째로 401 이 된다).
-- 기본값이지만 교체 뒤에 다시 적는다 — `create or replace` 가 뷰 옵션을 보존하는지에
-- 기대지 않는다(기대가 틀리면 증상이 "화면 전체 401" 이라 대가가 크다).
alter view v_floor_stack set (security_invoker = false);


-- =====================================================================
-- 4) PostgREST 에게 "스키마가 바뀌었다"고 알린다
-- =====================================================================
-- 안 알리면 새 칼럼이 스키마 캐시에 안 잡혀, 다음 재시작 전까지 화면이 계속 옛 4칸
-- 없는 응답을 받는다(에러가 아니라 조용한 누락이라 더 나쁘다).
notify pgrst, 'reload schema';


-- =====================================================================
-- 5) 확인 (Run 한 뒤 이 쿼리들로 검산 — ★ 머지 조건)
-- =====================================================================
-- 기대: 아래 4개가 모두 나온다. **api 쪽으로도** 물어야 한다(public 만 보면
--       쌍둥이가 굳어 있는 것을 못 잡는다 — 이 변경의 핵심 함정).
--
--   select column_name from information_schema.columns
--   where table_schema = 'api' and table_name = 'v_floor_stack'
--     and column_name in ('total_area_m2','far','bcr','parking_cnt')
--   order by 1;
--
-- 기대: 값이 실제로 실려 온다(칼럼만 생기고 전부 미기재면 조인이 끊긴 것이다).
--       ⚠️ `is not null` 로 거르면 안 된다 — 미기재가 NULL 이 아니라 0 으로 오므로
--          그 조건은 0 행까지 통과시켜 판별력이 0 이다. **화면이 값으로 치는 것과
--          같은 조건**(0 초과)으로 물어야 실제로 실려 오는지를 잰다.
--
--   select bld_nm, total_area_m2, far, bcr, parking_cnt
--   from api.v_floor_stack
--   where total_area_m2 > 0 and parking_cnt > 0
--   limit 5;
--
-- 기대: 화면이 "미상"으로 적을 몫이 얼마나 되는지 — 그 표기가 과한지 가늠한다.
--       ⓘ far_max 는 **분포를 한 번 보는 용도**다. 용적률은 정의상 100%를 훌쩍 넘으므로
--         "크다"가 곧 오류가 아니다 — 상한을 걸라는 뜻이 아니고, bcr 처럼 자릿수가
--         터무니없는 값이 섞였는지만 눈으로 확인한다(걸 근거가 생기면 그때 결재).
--
--   select
--     count(*)                                              as bld_cnt,
--     count(*) filter (where coalesce(total_area_m2,0) = 0) as area_zero,
--     count(*) filter (where coalesce(parking_cnt,0)   = 0) as parking_zero,
--     count(*) filter (where bcr > 100)                     as bcr_over_100,
--     -- 화면 상한(MAX_TOTAL_AREA_M2 = 100만㎡)에 몇 채가 걸리는지. 눈에 띄게 많으면
--     -- 상한을 올릴 게 아니라 원본 적재를 먼저 의심할 것.
--     count(*) filter (where total_area_m2 > 1000000)       as area_over_cap,
--     -- 미기재는 0 으로 온다고 알고 있지만, 적재기는 결측을 NULL 로도 쓴다
--     -- (_to_float·sum_parking). 실제로 NULL 이 생겼는지는 세어 봐야 안다.
--     count(*) filter (where parking_cnt is null)           as parking_null,
--     max(far)                                              as far_max
--   from building;
--
-- 기대: REST 로도 같은 칼럼이 온다(브라우저가 실제로 받는 경로 그대로).
--
--   curl "$SANGGA_SUPABASE_URL/rest/v1/v_floor_stack?select=bld_nm,total_area_m2,far,bcr,parking_cnt&limit=1" \
--        -H "apikey: $ANON" -H "Accept-Profile: api"
--
-- 기대: 노출 **객체**가 안 늘었다 — python scripts/post_load.py --check
--       ⚠️ 이 점검이 세는 것은 "anon 이 읽을 수 있는 표·뷰·함수"이지 **칼럼이 아니다.**
--          이미 열린 뷰에 칼럼을 붙이는 이번 같은 변경은 이 점검을 그냥 통과한다.
--          민감한 칼럼(상호명·개인 성명·좌표 등)을 붙일 때는 기계가 아니라 **사람이**
--          "이걸 공개해도 되는가"를 직접 판단할 것. 이번 4칸은 건축물대장 공개 항목이다.
-- =====================================================================
