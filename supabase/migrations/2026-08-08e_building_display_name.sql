-- =====================================================================
-- 마이그레이션 2026-08-08 (e) — 건물 표시명: 동명칭 폴백 + 개인 성명 가리기
-- =====================================================================
-- 어떻게 쓰나: Supabase 대시보드 → SQL Editor → New query → 이 파일 전체
--             붙여넣기 → Run. 몇 번을 실행해도 안전하다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 (2026-08-08 P2-3 조사, 라이브 실측으로 확정)
-- ─────────────────────────────────────────────────────────────────────
-- (1) **이름이 있는데 검색이 못 찾는 건물이 404개 있다.**
--     건축물대장에는 이름 칸이 둘이다 — `building.bld_nm`(건물명)과
--     `building.dong_nm`(동명칭). 지금 검색·화면은 앞의 하나만 본다.
--     실측: bld_nm 없음 7,044개 중 dong_nm 있음 688개, 그 중 '주건축물제1동'·
--     '가동' 같은 일반 라벨 284개를 뺀 **404개가 진짜 이름**이다(7층 이상 43개).
--
--     라이브 확인(공개키, 화면과 같은 경로):
--       '노보텔앰배서더서울'(16층 호텔) → 0건   ← dong_nm 에 실재
--       'WeWork Building'(19층)      → 0건
--       '역삼동 718빌딩'(20층)        → 0건
--       '강남텔레피아빌딩'(13층)       → 0건
--     대조군으로 bld_nm 에 있는 이름 10개는 전부 1~2건이 나왔고, 없는 문자열
--     2개는 0건이 나왔다 — 즉 "검색이 아무거나 0건을 뱉는 것"이 아니라
--     **dong_nm 을 안 보기 때문**임이 갈렸다.
--
-- (2) **건물명 칸에 개인 성명이 섞여 있다.** bld_nm 5,361개 중 93개가
--     '역삼동 610-2 단독주택 (김남연)' 형태다. 괄호 안 값의 빈도가 거의 전부
--     1회로 흩어진다 — 건물 이름이면 반복될 텐데 그렇지 않으니 사람 이름이다.
--     원본(건축물대장)이 공개 데이터라 열람 자체는 위법이 아니지만, 우리 화면에
--     성명을 그대로 얹는 것은 별개 문제다. 지금은 앱이 배포 전이라 실제 외부
--     노출은 0이며, 이 조치는 **배포 전에 미리 막는 것**이다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 어떻게 고치나
-- ─────────────────────────────────────────────────────────────────────
-- `building_display_nm(bld_nm, dong_nm)` 하나로 "화면에 보일 이름"을 정하고,
-- **검색도 표시도 전부 이 값 하나만** 쓴다. 그래서 "보이는 것 = 검색되는 것"이
-- 항상 일치한다. 원본 표 `building` 의 값은 건드리지 않는다(되돌릴 수 있게).
--
-- ⚠️ 원본 성명은 API 응답에도 실리지 않는다 — 뷰와 검색 함수가 내보내는
--    `bld_nm` 은 이미 가려진 값이다. 브라우저 개발자도구로도 원문을 못 본다.
--
-- ⚠️ 함수를 IMMUTABLE 로 잡는 이유: 그래야 이 식 위에 인덱스를 걸 수 있다.
--    인덱스가 없으면 검색이 매번 12,405행을 훑는다(전국 확장 시 치명적).
-- =====================================================================


-- ─────────────────────────────────────────────────────────────────────
-- 1) 개인 성명 가리기
-- ─────────────────────────────────────────────────────────────────────
-- '… 단독주택 (김남연)' → '… 단독주택'
-- 괄호 안이 건물을 가리키는 말(빌딩·타워·상가 등)이면 건드리지 않는다
-- ('썬프라자(태양빌딩)' 은 그대로 둔다).
-- 이름만 남는 경우('(김남연)' 뿐)는 빈 문자열이 되므로 NULL 로 돌려 동명칭
-- 폴백이 이어받게 한다.
create or replace function mask_person_name(nm text)
returns text
language sql
immutable
parallel safe
as $$
  select case
    when nm is null then null
    when nm ~ '\([가-힣]{2,4}\)\s*$'
     and nm !~ '\([가-힣]*(빌딩|타워|하우스|플라자|프라자|스퀘어|센터|주택|상가|본관|별관|신관|구관|아파트|오피스|사옥|회관|시장)[가-힣]*\)\s*$'
    then nullif(btrim(regexp_replace(nm, '\s*\([가-힣]{2,4}\)\s*$', '')), '')
    else nm
  end
$$;

comment on function mask_person_name(text) is
  '건물명 끝의 (사람이름)을 지운다. 원본 표는 그대로 두고 내보낼 때만 가린다. '
  'IMMUTABLE — 이 식 위에 인덱스를 걸기 위해 필요하다';


-- ─────────────────────────────────────────────────────────────────────
-- 2) 화면에 보일 건물 이름
-- ─────────────────────────────────────────────────────────────────────
-- 우선순위: 건물명(성명 가림) → 동명칭(일반 라벨이면 버림) → NULL
--
-- 일반 라벨이란 이름이 아니라 "몇 번째 동인지"를 적은 것이다. 실측 상위 15종
-- (주건축물제1동 190·가동 12·나동 11·1동 8·2동 7·A동 7·B동 6·1 5·주건축물제2동 2·
--  D동 2·근린생활시설 2·다동 1·2 1·C동 1·3동 1)을 아래 한 줄이 전부 덮는다.
-- 이걸 이름으로 쓰면 화면에 '주건축물제1동'이 190개 뜬다 — 이름이 없는 것만
-- 못하다.
--
-- ⛔ 아래 `public.` 을 떼지 말 것 (2026-08-08 실패로 확인).
--    CREATE INDEX 가 도는 동안 Postgres 는 보안을 위해 search_path 를
--    `pg_catalog, pg_temp` 로 **일시적으로 바꾼다**(공식 문서 명시). 그 순간
--    public 이 안 보이므로 이름만 적은 `mask_person_name(...)` 은
--    "함수가 존재하지 않습니다"(42883)로 실패하고 마이그레이션 전체가 되돌아간다.
--    함수가 없어서가 아니라 **그 순간에만 안 보여서** 나는 오류다.
create or replace function building_display_nm(bld_nm text, dong_nm text)
returns text
language sql
immutable
parallel safe
as $$
  select coalesce(
    nullif(btrim(public.mask_person_name(bld_nm)), ''),
    case
      when btrim(coalesce(dong_nm, '')) = '' then null
      when btrim(dong_nm) ~ '^((주|부속)?건축물)?(제)?[0-9]*동$|^[가-힣]동$|^[A-Za-z]동$|^[0-9]+$|^(근린생활시설|본관|별관|신관|구관|관리동|경비실|주차장|창고)$'
        then null
      else btrim(dong_nm)
    end
  )
$$;

comment on function building_display_nm(text, text) is
  '§8.1 화면에 보일 건물 이름. 건물명(성명 가림) → 동명칭(일반 라벨 제외) → NULL. '
  '검색과 표시가 이 함수 하나만 쓰므로 "보이는 것 = 검색되는 것"이 항상 일치한다';


-- 도우미 함수는 공개 롤에게 열지 않는다. search_buildings·뷰가 소유자 권한으로
-- 대신 부르므로 anon 이 직접 실행할 필요가 없다(알려진한계 §4 "새 함수는 기본적으로
-- anon 에게 열린다" 대응).
revoke all on function mask_person_name(text) from public;
revoke all on function building_display_nm(text, text) from public;


-- ─────────────────────────────────────────────────────────────────────
-- 3) 검색용 인덱스 — 표시명 그 식 위에 건다
-- ─────────────────────────────────────────────────────────────────────
-- WHERE 절과 **글자 하나까지 같은 식**이어야 인덱스를 탄다.
-- 이름이 둘 다 없는 건물은 NULL 이라 색인되지 않는다 = 이름으로는 안 찾힌다(의도).
-- 식 인덱스는 식을 괄호로 감싸는 형태로 쓴다(연산자 클래스가 뒤에 붙을 때 안전).
create index if not exists idx_building_display_nm
  on building using gin ((building_display_nm(bld_nm, dong_nm)) gin_trgm_ops);

-- 기존 idx_building_nm(원본 bld_nm)은 검색이 더는 쓰지 않지만 지우지 않는다 —
-- 다른 조회가 쓸 수 있고, 12,405행짜리 표라 유지 비용이 사실상 0이다.


-- ─────────────────────────────────────────────────────────────────────
-- 4) 스택 뷰 — 제목에 쓰는 이름도 같은 규칙으로
-- ─────────────────────────────────────────────────────────────────────
-- 컬럼 이름(bld_nm)과 타입(text)은 그대로라 create or replace 로 안전하게 바뀐다.
-- 값의 뜻만 "원본 건물명" → "화면에 보일 이름"으로 바뀐다.
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
  building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
  b.approve_date,
  b.is_jiphap,
  p.road_addr,
  p.road_contact,
  pb.bld_cnt_in_pnu,
  st.store_cnt,
  st.stores
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
  '⚠️ bld_nm은 원본이 아니라 building_display_nm() 결과다(동명칭 폴백 + 개인 성명 가림, 2026-08-08e)';


-- ─────────────────────────────────────────────────────────────────────
-- 5) 검색 함수 — 이름 가지를 표시명 하나로 통일
-- ─────────────────────────────────────────────────────────────────────
-- 반환 컬럼·타입이 그대로라 create or replace 가 통한다(프론트 계약 불변).
--
-- ⛔ WHERE를 OR로 되돌리지 말 것 — 두 조인 테이블에 걸친 OR은 인덱스를 무력화한다
--    (2026-08-08c 에서 EXPLAIN ANALYZE 로 확정).
-- ⛔ 이름 가지의 식을 idx_building_display_nm 과 다르게 쓰지 말 것 — 한 글자만
--    달라도 인덱스를 안 탄다.
create or replace function search_buildings(q text, lim int default 25)
returns table (
  bld_id         text,
  pnu            char(19),
  bld_nm         text,
  road_addr      text,
  bld_cnt_in_pnu int,
  floor_cnt      int,
  min_floor      smallint,
  max_floor      smallint,
  has_roof       boolean,
  total_cnt      bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with pat as (
    -- 빈 검색어(NULL·''·공백뿐)는 NULL 패턴으로 만들어 아래에서 0건이 되게 한다.
    -- LIKE 특수문자는 리터럴로. 역슬래시를 **먼저** 바꿔야 한다.
    select case
             when coalesce(btrim(q), '') = '' then null
             else '%' ||
                  replace(replace(replace(q, '\', '\\'), '%', '\%'), '_', '\_') ||
                  '%'
           end as p
  ),
  hit as (
    select b.bld_id, b.pnu,
           building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
           pc.road_addr
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and building_display_nm(b.bld_nm, b.dong_nm) ilike pat.p escape '\'
    union
    select b.bld_id, b.pnu,
           building_display_nm(b.bld_nm, b.dong_nm),
           pc.road_addr
      from building b
      join parcel pc on pc.pnu = b.pnu
      cross join pat
     where pat.p is not null
       and pc.road_addr ilike pat.p escape '\'
  ),
  -- 그릴 층이 하나도 없는 건물은 목록에 올리지 않는다(눌러도 빈 화면).
  eligible as (
    select h.*, count(*) over () as total_cnt
    from hit h
    where exists (
      select 1 from building_floor f
      where f.bld_id = h.bld_id and f.floor_no is not null
    )
  ),
  -- 무거운 층 집계는 실제로 보여줄 몇 개에만 돌린다.
  top as (
    select e.*
    from eligible e
    order by
      (lower(e.bld_nm) = lower(q))      desc nulls last,  -- 이름이 검색어와 정확히 같음
      (e.bld_nm ilike q || '%')         desc nulls last,  -- 이름이 검색어로 시작
      (e.bld_nm is null)                asc,              -- 이름 있는 건물 먼저
      length(e.bld_nm)                  asc nulls last,   -- 짧고 핵심적인 이름 먼저
      e.road_addr                       asc nulls last,   -- 그다음 주소순(동네가 고루 섞인다)
      e.bld_id
    limit greatest(1, least(coalesce(lim, 25), 100))
  )
  select
    t.bld_id, t.pnu, t.bld_nm, t.road_addr,
    (select count(*)::int from building b2 where b2.pnu = t.pnu) as bld_cnt_in_pnu,
    fs.floor_cnt, fs.min_floor, fs.max_floor, fs.has_roof,
    t.total_cnt
  from top t
  join lateral (
    -- 옥탑(99)은 범위에서 뺀다. 섞으면 최고층이 항상 99가 되어 지상 최고층이 사라진다.
    select
      count(*)::int                                    as floor_cnt,
      min(s.floor_no) filter (where s.floor_no <> 99)  as min_floor,
      max(s.floor_no) filter (where s.floor_no <> 99)  as max_floor,
      coalesce(bool_or(s.floor_no = 99), false)        as has_roof
    from v_building_floor_stack s
    where s.bld_id = t.bld_id
  ) fs on true
  order by
    (lower(t.bld_nm) = lower(q))      desc nulls last,
    (t.bld_nm ilike q || '%')         desc nulls last,
    (t.bld_nm is null)                asc,
    length(t.bld_nm)                  asc nulls last,
    t.road_addr                       asc nulls last,
    t.bld_id;
$$;

comment on function search_buildings(text, int) is
  '§8.1 건물 검색. 건물 1개 = 1행이며 total_cnt로 정확한 전체 건수를 함께 준다. '
  'security definer — 원본 표가 anon에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '입력의 % _ \ 는 서버가 리터럴로 이스케이프하고, 빈 검색어는 0건으로 잘라낸다. '
  '이름은 building_display_nm() 하나만 본다(동명칭 폴백 + 개인 성명 가림) — 보이는 것 = 검색되는 것. '
  '⛔ WHERE를 OR로 되돌리지 말 것 — 두 조인 테이블에 걸친 OR은 gin_trgm 인덱스를 무력화한다';

revoke all on function search_buildings(text, int) from public;
grant execute on function search_buildings(text, int) to anon, authenticated;

-- 뷰 권한은 재정의로 사라지지 않지만 멱등하게 다시 못 박는다.
grant select on v_floor_stack to anon, authenticated;
alter view v_floor_stack set (security_invoker = false);


-- =====================================================================
-- 확인 (붙여넣고 Run 한 뒤 이 쿼리들로 검산)
-- =====================================================================
-- 기대: 1건씩 — 예전에는 전부 0건이었다
--   select bld_nm, total_cnt from search_buildings('노보텔', 25);
--   select bld_nm, total_cnt from search_buildings('WeWork Building', 25);
--   select bld_nm, total_cnt from search_buildings('강남텔레피아빌딩', 25);
--
-- 기대: 예전과 같음(대조군) — 이 변경이 멀쩡하던 것을 깨지 않았는지
--   select count(*) from search_buildings('글라스톤빌딩', 25);   -- 1
--   select max(total_cnt) from search_buildings('빌딩', 25);      -- 1742 부근
--   select count(*) from search_buildings('', 25);                -- 0
--
-- 기대: 0건 — 개인 성명으로는 더 이상 찾히지 않는다
--   select count(*) from search_buildings('김남연', 25);
--
-- 기대: 가려진 이름이 나온다('… (안제호)'가 아니라 '…')
--   select bld_nm from search_buildings('역삼동 609-26', 25);
--
-- 기대: 화면에 이름이 붙는 건물이 404개 늘어난다
--   select count(*) from building
--    where bld_nm is null and building_display_nm(bld_nm, dong_nm) is not null;
--
-- 기대: 성명이 가려진 건물 수
--   select count(*) from building where mask_person_name(bld_nm) <> bld_nm;
--
-- 기대: 인덱스를 타는지 (Bitmap Index Scan 이 보여야 한다)
--   explain analyze select * from search_buildings('빌딩', 25);
-- =====================================================================
