-- =====================================================================
-- 2026-08-25a — v_floor_stack 에 좌표 2칸 (lat·lng)
-- =====================================================================
-- 왜 필요한가
-- ─────────────────────────────────────────────────────────────────────
-- 링크로 들어온 사람(공유 링크·새로고침·즐겨찾기)은 **검색을 거치지 않는다.**
-- 그런데 지금 화면이 건물 정보를 얻는 길은 검색(`search_buildings`) 하나뿐이라,
-- 주소에 건물 번호만 있는 상태에서는 이름·주소·좌표를 되찾을 방법이 없다.
--
-- 다행히 층별 뷰(`v_floor_stack`)가 이미 대부분을 갖고 있다 — bld_id·pnu·bld_nm·
-- road_addr·bld_cnt_in_pnu. **딱 하나 없는 것이 지도 마커 자리(좌표)** 라서 그 둘만
-- 더한다. 새 함수(RPC)를 만들 필요가 없다.
--
-- ⛔ **`parcel.lat` / `parcel.lng` 칸을 쓰면 안 된다** (2026-08-14e 가 이미 정한 규칙)
-- ─────────────────────────────────────────────────────────────────────
-- parcel 에는 lat·lng 칸도 있지만, 그 둘과 `geom` 은 **서로 다른 시점에 채워질 수 있는
-- 별개의 칸**이다. 검색(`search_buildings`)은 `st_y(p.geom)`·`st_x(p.geom)` 에서 뽑고,
-- 상권 판정(`list_building_districts`)도 `st_contains(d.geom, p.geom)` 으로 geom 만 본다.
--
-- 여기서 lat/lng 칸을 쓰면 **같은 건물인데 들어온 길에 따라 마커가 다른 자리에 찍힌다**
-- (검색으로 들어오면 A, 링크로 들어오면 B). 게다가 "지도 위 마커는 상권 밖인데 아래
-- 글자는 상권 안"이라고 말하게 된다 — 에러가 안 나고 눈으로만 이상한, 가장 찾기
-- 어려운 종류의 어긋남이다. **같은 칸(geom)을 보게 못박는다.**
--
-- ⚠️ **api 쌍둥이를 반드시 다시 만든다** (2026-08-22 실측 불변식 · 24a 가 겪은 그대로)
-- ─────────────────────────────────────────────────────────────────────
-- `api.v_floor_stack` 은 `select * from public.v_floor_stack` 인데, 뷰의 `*` 는
-- **만들 때의 칼럼 목록으로 굳는다.** public 뷰에 칼럼을 덧붙여도 쌍둥이는 옛 칼럼만
-- 낸다 — 에러가 아니라 **조용한 누락**이라 아무도 모른다. 그래서 이 파일도
-- ① public 뷰 교체 → ② api 쌍둥이 재생성 → ③ 스키마 리로드 3종 세트다.
-- 순서를 바꾸면 ②가 옛 목록을 다시 굳힌다.
--
-- ⚠️ `create or replace view` 는 **칼럼을 끝에 더하는 것만** 된다. 아래 정의는 기존
--    21칸을 한 글자도 안 건드리고 뒤에 둘만 붙였다. drop 하지 말 것 — drop 하면 그
--    사이 화면이 통째로 죽고 권한·주석도 같이 날아간다.
--
-- ⓘ 좌표가 없는 필지: `st_y(null)` 은 NULL 이다. 화면은 lat·lng 를 **선택 필드**로 받아
--    없으면 마커를 안 찍는다 — 없는 좌표를 0,0(아프리카 앞바다)으로 채우지 않는다.
--
-- ⓘ 비용: `parcel p` 조인은 이미 있던 것이라 조인이 늘지 않는다. st_y/st_x 는 좌표
--    하나를 꺼내는 아주 싼 함수라 층 행마다 계산해도 부담이 없다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 적용 순서
-- ─────────────────────────────────────────────────────────────────────
--   ① 이 파일을 Run.
--   ② 아래 5) 검산 — 새 2칸이 **api 쪽에서도** 나오는지, 그리고 검색이 주는 좌표와
--      **값이 같은지** 본다. ★ 이게 머지 조건이다(E2E 는 REST 를 모킹하므로 라이브
--      드리프트를 못 잡는다 — 24a 가 남긴 교훈).
--   ③ 화면 배포. 좌표가 안 와도 마커만 안 찍힐 뿐 화면은 안 죽는다(선택 필드).
--      즉 ①과 ③ 사이에 죽는 구간이 없다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 되돌리기
-- ─────────────────────────────────────────────────────────────────────
-- `create or replace` 는 칼럼을 못 지운다. 정말 되돌리려면 drop 후 옛 정의를 새로
-- 만들고 권한·security_invoker 를 다시 걸어야 한다. 그럴 일은 거의 없다 — 칼럼이
-- 남아 있어도 화면이 안 읽으면 그만이다.
-- =====================================================================


-- =====================================================================
-- 1) public.v_floor_stack — 기존 21칸 그대로 + 끝에 좌표 2칸
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
  -- ── 2026-08-24a 가 더한 건물 스펙 4칸 (0 = 대장 미기재, 뜻풀이는 화면이 한다) ──
  b.total_area_m2,          -- 연면적 ㎡ (0 = 미기재)
  b.far,                    -- 용적률 % (0 = 미기재)
  b.bcr,                    -- 건폐율 % (0 = 미기재, 소스 오류로 100 초과 실재)
  b.parking_cnt,            -- 주차 4종(옥내외 × 자주/기계) 합 (0 = 미기재, 부분합 가능)
  -- ── 2026-08-25a 가 더한 좌표 2칸 ──────────────────────────────────────
  -- ⛔ parcel.lat/lng 칸이 아니라 **geom** 에서 뽑는다. 검색(search_buildings)·상권
  --    판정(list_building_districts)이 전부 geom 을 보므로 같은 칸을 봐야 한다.
  --    칸을 섞으면 들어온 길에 따라 마커 자리가 갈리는데, 에러가 안 나서 못 찾는다.
  -- ⓘ 필지 중심이 아니라 필지 도형의 대표 좌표다 — 한 땅에 건물이 여럿이면 그 건물들이
  --    **같은 자리**에 찍힌다(검색도 같은 한계를 갖는다, 2026-08-14e).
  st_y(p.geom)::double precision as lat,
  st_x(p.geom)::double precision as lng
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
  '⚠️ lat·lng 는 **parcel.geom 에서 뽑은** 필지 대표 좌표다(2026-08-25a). parcel 에 있는 lat/lng '
  '칸과는 다른 칸이며, 그 칸을 쓰면 검색·상권판정과 자리가 갈린다(2026-08-14e 규칙). '
  '한 땅에 건물이 여럿이면 같은 자리에 찍힌다 — 검색도 같은 한계다. 좌표 없는 필지는 NULL(마커 생략). '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — security_invoker=true로 되돌리면 원본 표 401 + 상호명·성명 노출 확대. '
  '재검토 방아쇠: 공개 배포일 / 지도·반경 검색(§6.4) 착수일';


-- =====================================================================
-- 2) api 쌍둥이 재생성 — `select *` 는 만들 때 굳는다
-- =====================================================================
-- 이 한 줄이 빠지면 화면(스키마 api)은 새 2칸을 **영영 못 본다.** public 쪽만 보고
-- "칼럼 늘었네" 하고 넘어가는 것이 이 변경의 가장 흔한 실패다(24a 가 남긴 경고).
create or replace view api.v_floor_stack as select * from public.v_floor_stack;


-- =====================================================================
-- 3) 권한 재확인 — 회수 먼저, 그다음 부여
-- =====================================================================
-- Supabase 는 새 객체마다 anon 에 권한을 자동으로 붙이고(pg_default_acl), 그 자동
-- 부여에는 INSERT·DELETE 가 섞여 있었다(2026-08-22 라이브 실측). `grant` 는 더하기라
-- 자동으로 붙은 쓰기를 못 걷어낸다 — 그래서 **회수를 먼저** 한다.
revoke all on api.v_floor_stack from public, anon, authenticated;
grant select on api.v_floor_stack to anon, authenticated;

-- ℹ️ public.v_floor_stack 에는 revoke 를 걸지 않는다(정본이 그렇게 정해 뒀다 — 2026-08-24a
--    주석 참조). 읽기 권한만 한 번 더 못 박는다(있으면 아무 일도 안 일어나는 문장이다).
grant select on v_floor_stack to anon, authenticated;

-- 뷰가 소유자(postgres) 권한으로 원본 표를 읽는다는 뜻. 이게 false 라야 RLS 로 닫아 둔
-- 원본 표를 뷰가 대신 읽어 줄 수 있다(true 면 화면이 통째로 401 이 된다).
alter view v_floor_stack set (security_invoker = false);


-- =====================================================================
-- 4) PostgREST 에게 "스키마가 바뀌었다"고 알린다
-- =====================================================================
-- 안 알리면 새 칼럼이 스키마 캐시에 안 잡혀, 다음 재시작 전까지 화면이 계속 좌표
-- 없는 응답을 받는다(에러가 아니라 조용한 누락이라 더 나쁘다).
notify pgrst, 'reload schema';


-- =====================================================================
-- 5) 확인 (Run 한 뒤 이 쿼리들로 검산 — ★ 머지 조건)
-- =====================================================================
-- ① 두 스키마의 칼럼 수가 같아야 한다(둘 다 23). 다르면 쌍둥이가 안 갱신된 것이다.
--
--   select table_schema, count(*) as cols
--   from information_schema.columns
--   where table_name = 'v_floor_stack' and table_schema in ('public','api')
--   group by table_schema order by table_schema;
--
-- ② api 쪽에서 좌표가 실제로 나오는지.
--
--   select bld_id, bld_nm, lat, lng
--   from api.v_floor_stack
--   where lat is not null
--   limit 3;
--
-- ③ ★ 가장 중요 — **검색이 주는 좌표와 값이 같은지.** 다르면 칸을 섞은 것이다.
--    (0 행이 나와야 정상: 값이 다른 건물이 하나도 없다는 뜻)
--
--   select f.bld_id, f.lat as stack_lat, s.lat as search_lat
--   from (select distinct on (bld_id) bld_id, lat, lng
--         from api.v_floor_stack order by bld_id) f
--   join lateral (
--     select st_y(p.geom)::double precision as lat, st_x(p.geom)::double precision as lng
--     from building b join parcel p on p.pnu = b.pnu where b.bld_id = f.bld_id
--   ) s on true
--   where f.lat is distinct from s.lat or f.lng is distinct from s.lng
--   limit 5;
--
-- ④ 공개 롤이 이 뷰에 대해 갖는 권한이 SELECT 하나뿐인지.
--
--   select grantee, privilege_type
--   from information_schema.role_table_grants
--   where table_schema = 'api' and table_name = 'v_floor_stack'
--   order by grantee, privilege_type;
