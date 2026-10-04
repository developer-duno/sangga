-- =====================================================================
-- 호실 구성표 — list_unit_floor_summary / list_floor_units + api 쌍둥이 (2026-10-04b)
-- =====================================================================
-- 결정 0032(호실 구성표: 층마다 몇 칸으로 쪼개져 있고 칸이 얼마나 넓은가)의 창고 함수 조각(PR-U1).
--
-- 왜
-- --
-- `unit`(호실) 표 2,950,009행은 2026-08 에 들어온 뒤 **읽는 함수가 0개**였다(공개키로는 표도 못
-- 연다). 그런데 호실 줄의 73.39% 가 주용도 '공동주택' 건물 안에 있어, 그대로 열면 대부분 아파트
-- 세대 목록이다. 그래서 표는 계속 닫아 두고 **함수 둘**로만 내보낸다:
--
--   ① list_unit_floor_summary(p_bld_id) — 건물을 열 때 한 번. 층마다 호실 수 · 전용면적
--      가운데값·최소·최대 · 층 종류(floor_kind). ⛔ 주거·오피스텔·미상 층은 면적 셋이 null
--      (한두 세대뿐인 층이면 그 집의 전용면적이 공개 주소로 나간다).
--   ② list_floor_units(p_bld_id, p_floor_no, p_limit, p_offset) — 층을 눌렀을 때. 호 이름 ·
--      전용면적 · 그 층 전체 수. ⛔ 그 층 종류가 commercial·mixed 가 아니면 **0줄**이다 —
--      화면이 안 부르는 것만으로는 세대 목록이 공개 주소로 긁힌다. 서버가 막는다.
--
-- 층 종류는 두 함수가 **글자 그대로 같은** 판정식(`kind` CTE)으로 정한다 — 요약과 목록이 서로
-- 다른 말을 하면 안 된다(tests/test_unit_table_migration.py 가 두 본문을 글자 대조한다).
-- 판정의 자(결정 0032 「층 종류를 가르는 자」): 층별개요(building_floor)의 그 층 줄 가운데 연면적
-- 제외분이 아니고 주용도 이름이 빈 값이 아닌 줄을 보고, 줄마다 주용도 이름과 기타용도 둘 다로
-- 살림집 · 오피스텔 · 치지 않는 것(부대시설·복리시설·주차장) · 그 밖 으로 나눈다.
--   ⛔ 주택 **코드**(01·02)로 가르지 않는다(단지 안 상가 = 생활편익시설이 주택 코드라 숨는다).
--   ⛔ 건물 주용도로 걸러 내지 않는다(치지 않는 것뿐인 층 한 경우만 본다).
--
-- ⛔ 인자는 bld_id(text)다 — pnu 가 아니다. 한 땅에 동이 여럿이면 pnu 로는 옆 동 호실이 섞인다.
--
-- 잠금
-- ----
-- 새 함수만 만든다 — 표·뷰를 바꾸지 않고 drop 도 없다. 표 잠금이 없어 아무 때나 적용해도 된다.
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 중간에 끊기면 api 쌍둥이 없이 원본만 남거나(화면 404)
-- 권한이 반쯤 걸린 채 남는다 — 한 덩어리로 묶는다. `notify pgrst` 는 commit **뒤**.
--
-- 실행법
-- ------
--   python scripts/dbx.py -f supabase/migrations/2026-10-04b_unit_table.sql
--   (합친 뒤 본 폴더 main 에서 — 그다음 python scripts/post_load.py --check : 공개 호출 허용
--    목록 21 → 23, 총계 25 → 27. 합치기 전에 main 에서 --check 를 돌리면 허용 목록에 없는
--    공개 함수 둘로 [사고]가 난다)
--
-- 적용한 사람이 보게 되는 것 (파일의 실제 문장 순서)
-- --------------------------
--   BEGIN · CREATE FUNCTION · COMMENT · REVOKE · CREATE FUNCTION · COMMENT · REVOKE ·
--   CREATE FUNCTION · REVOKE · GRANT · CREATE FUNCTION · REVOKE · GRANT · COMMIT · NOTIFY
--
-- 되돌리기 = 새 마이그레이션으로 함수 넷을 drop(api 먼저) + post_load.py 허용 목록에서 둘을 뺀다
-- (표·칸 변화 없음 — 화면은 함수가 없으면 조용히 생략한다). 적용된 이 파일은 고치지 않는다(원장).

begin;

-- ── 1) 층별 요약 ────────────────────────────────────────────────────────────
create or replace function list_unit_floor_summary(p_bld_id text)
returns table (
  floor_no       smallint,
  unit_cnt       int,
  median_area_m2 numeric,
  min_area_m2    numeric,
  max_area_m2    numeric,
  floor_kind     text
)
language sql
stable
security definer
set search_path = public
as $$
  with u as (
    -- idx_unit_bld (bld_id, floor_no) 를 탄다. 호실 없는 건물은 여기서 0줄 → 결과도 0줄.
    select un.floor_no, un.excl_area_m2, un.floor_use
    from unit un
    where un.bld_id = p_bld_id
  ),
  fl as (
    -- 층 빈 값(floor_no is null) 호실도 한 줄로 모인다("층 미상" 줄).
    -- 복층 호실은 걸친 층마다 한 줄씩 들어 있어 층마다 한 번씩 세어진다.
    -- 면적은 0 보다 큰 것만 센다(0 이하 94행은 값이 아니다).
    select u.floor_no,
           max(u.floor_use) as first_use,
           count(*)::int    as unit_cnt,
           round((percentile_cont(0.5) within group (order by u.excl_area_m2)
                  filter (where u.excl_area_m2 > 0))::numeric, 2) as median_area_m2,
           min(u.excl_area_m2) filter (where u.excl_area_m2 > 0)   as min_area_m2,
           max(u.excl_area_m2) filter (where u.excl_area_m2 > 0)   as max_area_m2
    from u
    group by u.floor_no
  ),
  -- ▼ 층 종류 판정 — list_floor_units 와 글자 그대로 같다(tests/test_unit_table_migration.py) ▼
  kind as (
    select fl.*,
           case
             -- 층별개요에 쓸 줄이 없다 → 그 층 호실들의 첫 용도(unit.floor_use) 이름으로.
             -- ⓘ 이 길은 치지 않는 것·건물 주용도 규칙을 안 본다 — 이 길로 오는 층의 첫 용도에
             --    부대시설·복리시설·주차장은 0층이라(2026-10-04 검사관 실측) 지금은 해가 없다.
             when bf.n = 0 then
               case
                 when fl.first_use ~ nm.officetel_re then 'officetel'
                 when fl.first_use ~ nm.home_re then 'residential'
                 when nullif(btrim(fl.first_use), '') is not null then 'commercial'
                 else 'unknown'
               end
             when bf.has_other and bf.has_counted_home_or_ot then 'mixed'
             when bf.has_other then 'commercial'
             when bf.has_officetel then 'officetel'
             when bf.has_home then 'residential'
             -- 치지 않는 것(부대시설·복리시설·주차장)뿐인 층 — 이때만 건물 주용도를 본다.
             when (select b.main_use from building b where b.bld_id = p_bld_id) = '공동주택'
               then 'residential'
             else 'commercial'
           end as floor_kind
    from fl
    cross join (
      -- 이름 목록은 여기 한 곳뿐이다. 바꾸면 층 종류별 층 수가 바뀐다(결정 0032 실측과 대조할 것).
      -- ⓘ '공관'만은 이름 **전체**가 '공관'일 때만(^공관$) — 부분 일치면 외국공관·이공관·건공관이
      --    살림집으로 잡힌다(2026-10-04 실측 · 그 밖으로 간다). 나머지 낱말은 부분 일치.
      -- ⓘ 아파트(?!형공장) — '아파트형공장'(지식산업센터 옛 이름 · 기타용도 1,110행 · 84동)은 살림집이
      --    아니다('아파트형주택' 28행은 살림집이라 (?!형) 으로 넓히지 않는다). 주택·(?<!비)주거 —
      --    '점포,주택'·'노인복지주택'·'사무실,주거시설' 꼴이 그 밖으로 가 목록이 나가던 것을 막는다.
      --    '(비주거)'·'비주거(기타…)' 는 비주거라는 뜻이라 뒤보기 부정으로 뺀다(검사관 지적 2026-10-04).
      -- ⓘ 주택(?!용?계단)·주거(?!용?계단) — '주거계단실'·'주택계단실'·'주택용계단실'은 상가 층에 붙은
      --    계단 이름이지 살림집이 아니다(재검사 실측 9층 · 2026-10-04). '주택용대피소'는 그대로 걸린다.
      select '(아파트(?!형공장)|공동주택|다세대|연립|다가구|단독주택|다중주택|기숙사|도시형생활|주택(?!용?계단)|(?<!비)주거(?!용?계단)|^공관$)'::text as home_re,
             '오피스텔'::text                                       as officetel_re,
             array['부대시설', '복리시설', '주차장']::text[]        as skip_nm
    ) nm
    cross join lateral (
      select count(*) as n,
             coalesce(bool_or(f.main_purps_nm ~ nm.home_re
                              or coalesce(f.etc_purps, '') ~ nm.home_re), false)      as has_home,
             coalesce(bool_or(f.main_purps_nm ~ nm.officetel_re
                              or coalesce(f.etc_purps, '') ~ nm.officetel_re), false) as has_officetel,
             -- 섞임 판정 전용: 치지 않는 것(부대시설·복리시설·주차장) 줄은 "섞임 판정에서 없는 셈 친다"
             -- (결정 0032 :75) — 그 줄의 기타용도에 '(아파트)'·'(오피스텔)'이 적혀 있어도 상가 층을 섞임으로
             -- 보내지 않는다. ⓘ has_home·has_officetel 은 모든 줄 그대로(그 줄뿐인 층은 지금처럼 주거·오피스텔).
             coalesce(bool_or(not (f.main_purps_nm = any (nm.skip_nm))
                              and (f.main_purps_nm ~ nm.home_re or f.main_purps_nm ~ nm.officetel_re
                                   or coalesce(f.etc_purps, '') ~ nm.home_re
                                   or coalesce(f.etc_purps, '') ~ nm.officetel_re)), false) as has_counted_home_or_ot,
             -- 한 줄 = 한 갈래: 주용도·기타용도 어느 쪽에도 살림집·오피스텔 낱말이 없고 치지 않는 것도
             -- 아닌 줄만 '그 밖'이다('업무시설 / 기타용도 오피스텔' 한 줄은 오피스텔이지 섞임이 아니다).
             coalesce(bool_or(f.main_purps_nm !~ nm.home_re
                              and f.main_purps_nm !~ nm.officetel_re
                              and coalesce(f.etc_purps, '') !~ nm.home_re
                              and coalesce(f.etc_purps, '') !~ nm.officetel_re
                              and not (f.main_purps_nm = any (nm.skip_nm))), false)   as has_other
      from building_floor f
      where f.bld_id = p_bld_id
        and f.floor_no = fl.floor_no
        and not f.area_excluded
        and nullif(btrim(f.main_purps_nm), '') is not null
    ) bf
  )
  -- ▲ 층 종류 판정 끝 ▲
  select k.floor_no,
         k.unit_cnt,
         -- ⛔ 목록을 주는 층(commercial·mixed)에서만 면적을 낸다 — 주거·오피스텔·미상 층은 null.
         case when k.floor_kind in ('commercial', 'mixed') then k.median_area_m2 end as median_area_m2,
         case when k.floor_kind in ('commercial', 'mixed') then k.min_area_m2 end    as min_area_m2,
         case when k.floor_kind in ('commercial', 'mixed') then k.max_area_m2 end    as max_area_m2,
         k.floor_kind
  from kind k
  -- 높은 층이 위(옥탑 99 맨 위 · 층 미상 맨 끝). 정렬은 화면 편의일 뿐 계약이 아니다.
  order by k.floor_no desc nulls last;
$$;

comment on function list_unit_floor_summary(text) is
  '결정 0032 호실 구성표 — 한 건물(bld_id)의 층마다 호실 수와 전용면적(가운데값·최소·최대, 0 이하 제외) '
  '그리고 층 종류(floor_kind: commercial · mixed · residential · officetel · unknown). '
  '⛔ residential·officetel·unknown 층은 면적 셋이 null 이다(한두 세대뿐인 층이면 그 집 크기가 나간다). '
  '층 종류는 층별개요의 그 층 줄 전부(주용도 이름 + 기타용도)로 정하고, 층별개요가 없는 층은 '
  'unit.floor_use(그 층 첫 용도)로 정한다 — list_floor_units 와 글자 그대로 같은 판정식. '
  '호실 0 건물은 0줄. ⛔ 인자는 bld_id 다(pnu 로 받으면 같은 땅 옆 동 호실이 섞인다). '
  'security definer (unit·building_floor·building 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '나가는 것은 층별 수와 목록 제공 층의 면적 요약뿐이다).';

-- 새 함수는 닫힌 채 태어나지만(2026-09-01b) 대시보드 판은 다르다 — 만든 자리에서 닫는다.
revoke all on function list_unit_floor_summary(text) from public, anon, authenticated;

-- ── 2) 한 층의 호 목록 ──────────────────────────────────────────────────────
create or replace function list_floor_units(
  p_bld_id   text,
  p_floor_no int,
  p_limit    int default 50,
  p_offset   int default 0
)
returns table (
  ho           text,
  excl_area_m2 numeric,
  total_cnt    bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with u as (
    -- p_floor_no 가 빈 값이면 `=` 가 참이 안 돼 0줄이다("층 미상" 호실은 목록을 주지 않는다).
    select un.unit_id, un.floor_no, un.ho, un.excl_area_m2, un.floor_use
    from unit un
    where un.bld_id = p_bld_id
      and un.floor_no = p_floor_no
  ),
  fl as (
    select u.floor_no,
           max(u.floor_use) as first_use
    from u
    group by u.floor_no
  ),
  -- ▼ 층 종류 판정 — list_unit_floor_summary 와 글자 그대로 같다(tests/test_unit_table_migration.py) ▼
  kind as (
    select fl.*,
           case
             -- 층별개요에 쓸 줄이 없다 → 그 층 호실들의 첫 용도(unit.floor_use) 이름으로.
             -- ⓘ 이 길은 치지 않는 것·건물 주용도 규칙을 안 본다 — 이 길로 오는 층의 첫 용도에
             --    부대시설·복리시설·주차장은 0층이라(2026-10-04 검사관 실측) 지금은 해가 없다.
             when bf.n = 0 then
               case
                 when fl.first_use ~ nm.officetel_re then 'officetel'
                 when fl.first_use ~ nm.home_re then 'residential'
                 when nullif(btrim(fl.first_use), '') is not null then 'commercial'
                 else 'unknown'
               end
             when bf.has_other and bf.has_counted_home_or_ot then 'mixed'
             when bf.has_other then 'commercial'
             when bf.has_officetel then 'officetel'
             when bf.has_home then 'residential'
             -- 치지 않는 것(부대시설·복리시설·주차장)뿐인 층 — 이때만 건물 주용도를 본다.
             when (select b.main_use from building b where b.bld_id = p_bld_id) = '공동주택'
               then 'residential'
             else 'commercial'
           end as floor_kind
    from fl
    cross join (
      -- 이름 목록은 여기 한 곳뿐이다. 바꾸면 층 종류별 층 수가 바뀐다(결정 0032 실측과 대조할 것).
      -- ⓘ '공관'만은 이름 **전체**가 '공관'일 때만(^공관$) — 부분 일치면 외국공관·이공관·건공관이
      --    살림집으로 잡힌다(2026-10-04 실측 · 그 밖으로 간다). 나머지 낱말은 부분 일치.
      -- ⓘ 아파트(?!형공장) — '아파트형공장'(지식산업센터 옛 이름 · 기타용도 1,110행 · 84동)은 살림집이
      --    아니다('아파트형주택' 28행은 살림집이라 (?!형) 으로 넓히지 않는다). 주택·(?<!비)주거 —
      --    '점포,주택'·'노인복지주택'·'사무실,주거시설' 꼴이 그 밖으로 가 목록이 나가던 것을 막는다.
      --    '(비주거)'·'비주거(기타…)' 는 비주거라는 뜻이라 뒤보기 부정으로 뺀다(검사관 지적 2026-10-04).
      -- ⓘ 주택(?!용?계단)·주거(?!용?계단) — '주거계단실'·'주택계단실'·'주택용계단실'은 상가 층에 붙은
      --    계단 이름이지 살림집이 아니다(재검사 실측 9층 · 2026-10-04). '주택용대피소'는 그대로 걸린다.
      select '(아파트(?!형공장)|공동주택|다세대|연립|다가구|단독주택|다중주택|기숙사|도시형생활|주택(?!용?계단)|(?<!비)주거(?!용?계단)|^공관$)'::text as home_re,
             '오피스텔'::text                                       as officetel_re,
             array['부대시설', '복리시설', '주차장']::text[]        as skip_nm
    ) nm
    cross join lateral (
      select count(*) as n,
             coalesce(bool_or(f.main_purps_nm ~ nm.home_re
                              or coalesce(f.etc_purps, '') ~ nm.home_re), false)      as has_home,
             coalesce(bool_or(f.main_purps_nm ~ nm.officetel_re
                              or coalesce(f.etc_purps, '') ~ nm.officetel_re), false) as has_officetel,
             -- 섞임 판정 전용: 치지 않는 것(부대시설·복리시설·주차장) 줄은 "섞임 판정에서 없는 셈 친다"
             -- (결정 0032 :75) — 그 줄의 기타용도에 '(아파트)'·'(오피스텔)'이 적혀 있어도 상가 층을 섞임으로
             -- 보내지 않는다. ⓘ has_home·has_officetel 은 모든 줄 그대로(그 줄뿐인 층은 지금처럼 주거·오피스텔).
             coalesce(bool_or(not (f.main_purps_nm = any (nm.skip_nm))
                              and (f.main_purps_nm ~ nm.home_re or f.main_purps_nm ~ nm.officetel_re
                                   or coalesce(f.etc_purps, '') ~ nm.home_re
                                   or coalesce(f.etc_purps, '') ~ nm.officetel_re)), false) as has_counted_home_or_ot,
             -- 한 줄 = 한 갈래: 주용도·기타용도 어느 쪽에도 살림집·오피스텔 낱말이 없고 치지 않는 것도
             -- 아닌 줄만 '그 밖'이다('업무시설 / 기타용도 오피스텔' 한 줄은 오피스텔이지 섞임이 아니다).
             coalesce(bool_or(f.main_purps_nm !~ nm.home_re
                              and f.main_purps_nm !~ nm.officetel_re
                              and coalesce(f.etc_purps, '') !~ nm.home_re
                              and coalesce(f.etc_purps, '') !~ nm.officetel_re
                              and not (f.main_purps_nm = any (nm.skip_nm))), false)   as has_other
      from building_floor f
      where f.bld_id = p_bld_id
        and f.floor_no = fl.floor_no
        and not f.area_excluded
        and nullif(btrim(f.main_purps_nm), '') is not null
    ) bf
  )
  -- ▲ 층 종류 판정 끝 ▲
  select u.ho,
         u.excl_area_m2,
         count(*) over () as total_cnt   -- 쪽 나누기 전 그 층 호실 줄 전부의 수
  from u
  join kind k on k.floor_no = u.floor_no
  -- ⛔ 목록은 commercial·mixed 층에서만 — 주거·오피스텔·미상 층은 0줄(서버가 막는다).
  where k.floor_kind in ('commercial', 'mixed')
  -- 자연 정렬: 숫자가 든 이름 먼저, 이름 안 숫자 덩어리 **전부**를 차례로 numeric 으로 견준다
  -- (`10층001호`·`101동1001호` 꼴 — 첫 덩어리만 보면 결국 글자 순으로 떨어진다). 숫자 없는 이름은
  -- 그 뒤 글자 순, 빈 이름은 맨 끝. 마지막 동률은 이름 글자 순, 그래도 같으면 unit_id(쪽 나누기 안정).
  order by coalesce(u.ho ~ '[0-9]', false) desc,
           array(select m.g[1]::numeric
                   from regexp_matches(u.ho, '[0-9]+', 'g') with ordinality as m(g, i)
                  order by m.i),
           nullif(u.ho, '') asc nulls last,   -- 빈 글자도 NULL 과 같이 맨 끝
           u.unit_id
  -- 한 번에 최대 200줄(결정 0026·0028 과 같은 상한) · 1 미만·빈 값이면 기본 50 · offset 음수면 0.
  limit  case when p_limit is null or p_limit < 1 then 50 else least(p_limit, 200) end
  offset greatest(0, coalesce(p_offset, 0));
$$;

comment on function list_floor_units(text, int, int, int) is
  '결정 0032 호실 구성표 — 한 건물(bld_id)의 한 층 호 목록(호 이름은 대장 원문 그대로 · 전용면적 · '
  '쪽 나누기 전 그 층 전체 수 total_cnt). ⛔ 그 층 종류가 commercial·mixed 가 아니면 0줄이다 — '
  '주거·오피스텔·미상 층의 세대 목록은 어떤 인자로도 나가지 않는다(서버가 막는다). '
  '층 종류는 list_unit_floor_summary 와 글자 그대로 같은 판정식. mixed 층에는 주거·오피스텔 호실도 '
  '함께 나온다(결정 0032 결정 3 — 호실마다의 용도는 아직 담지 않았다). p_floor_no 가 빈 값이면 0줄. '
  '한 번에 최대 200줄(p_limit 1 미만이면 50) · 자연 정렬(이름 안 숫자 덩어리 전부를 numeric 으로). '
  '⛔ 인자는 bld_id 다(pnu 로 받으면 같은 땅 옆 동 호실이 섞인다). '
  'security definer (unit·building_floor·building 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다).';

revoke all on function list_floor_units(text, int, int, int) from public, anon, authenticated;

-- ── 3) api 쌍둥이 — 화면이 부르는 문 ────────────────────────────────────────
-- (public 원본은 닫힌 채, 이 문만 anon 에게 연다 — 2026-09-01b 규칙)
create or replace function api.list_unit_floor_summary(p_bld_id text)
returns table (
  floor_no       smallint,
  unit_cnt       int,
  median_area_m2 numeric,
  min_area_m2    numeric,
  max_area_m2    numeric,
  floor_kind     text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_unit_floor_summary(p_bld_id) $$;

revoke all on function api.list_unit_floor_summary(text) from public, anon, authenticated;
grant execute on function api.list_unit_floor_summary(text) to anon, authenticated;

create or replace function api.list_floor_units(
  p_bld_id   text,
  p_floor_no int,
  p_limit    int default 50,
  p_offset   int default 0
)
returns table (
  ho           text,
  excl_area_m2 numeric,
  total_cnt    bigint
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_floor_units(p_bld_id, p_floor_no, p_limit, p_offset) $$;

revoke all on function api.list_floor_units(text, int, int, int) from public, anon, authenticated;
grant execute on function api.list_floor_units(text, int, int, int) to anon, authenticated;

-- ⛔ public 원본 둘과 표 unit 은 끝까지 닫아 둔다 — 열면 아파트 세대 목록이 통째로 긁힌다.

commit;

-- ⛔ 커밋 **뒤**여야 한다. 안 알리면 DB 에는 함수가 있는데 화면만 404(PGRST202)가 난다.
notify pgrst, 'reload schema';
