-- =====================================================================
-- 오래된 허가를 한 줄 더 적기 — count_nearby_permits.stale_cnt (2026-09-05b)
-- =====================================================================
-- 무엇이 문제였나
-- ----------------
-- "새로 올라오는 상가 건물 N동"은 지금까지 **사용승인이 안 난 허가**만 보고 셌다. 그런데
-- 2026-09-01 감사의 라이브 실측은 이렇게 나왔다 — 서울 상업계열 미준공 **9,295건 중
-- 3,337건(35.9%)** 이 허가 후 **2년 넘게 착공 기록이 없다**. 건축법 §11⑦ 은 허가 후
-- 2년(1년 연장 가능) 미착공이면 허가가 실효된다고 본다. 즉 화면이 "곧 올라온다"고 말한
-- 것의 3분의 1은 **안 올라올 수도 있는 것**이었다.
--
-- 사장님 결재(2026-09-05): 숫자는 그대로 두고 한 줄을 더한다
-- ----------------------------------------------------------
-- ⛔ **제외하지 않는다.** 걸러 내면 사용자가 보는 수가 조용히 줄어드는데, 그 기준(2년? 3년?)을
--    우리가 추정으로 정해야 한다. 대신 "그중 N동은 허가 후 2년 넘게 착공하지 않았습니다"를
--    **사실 그대로** 한 줄 더 적는다.
-- ⛔ **"실효됐다"고 단정하지 않는다.** 원본(건축HUB 기본개요)에는 실효 상태 칸이 아예 없다.
--    연장했을 수도, 착공해 놓고 신고를 안 했을 수도 있다. 우리가 아는 것은 "그 달 자료에
--    착공 기록이 없다"까지이고, 화면 문장도 거기까지만 말한다.
-- ⛔ **재는 자는 기준월의 말일이다 — 오늘이 아니다.** 이 표는 그 달의 상태를 찍은 것이라,
--    오늘로 재면 자료가 보지 못한 시간까지 섞어 세게 된다(월 1회 수동 갱신이라 갱신이
--    늦으면 그만큼 조용히 부푼다).
--
-- ⛔ 반환 표에 칸을 더하므로 `create or replace` 로는 못 고친다
-- -------------------------------------------------------------
-- PostgreSQL 은 `returns table` 의 칸 구성이 바뀌면 replace 를 거부한다
-- ("cannot change return type of existing function"). 그래서 **먼저 떨어뜨린다** — api 쪽을
-- 먼저 떨어뜨리고(그것이 public 을 부른다), 그다음 public 을 떨어뜨린다.
-- ⓘ 이 순서는 **관습**이지 PostgreSQL 이 강제하는 것이 아니다 — 문자열 본문(`as $$ … $$`)
--    함수는 본문 안에서 부르는 함수와의 의존 관계를 기록하지 않아(공식 문서: 의존 추적은
--    `BEGIN ATOMIC` 형태만), public 을 먼저 지워도 막히지 않고 api 쪽 본문만 잠시 허공을
--    가리킨다. 부르는 쪽부터 지우면 그 허공 상태 자체가 안 생긴다(2026-09-05 독립 검토 정정).
--
-- ⓘ 덮개 인덱스(idx_arch_permit_pnu 의 include 네 칸)에 `arch_pms_day` 는 없다. 그래서 이
--    함수의 arch_permit 읽기가 Index Only Scan → Index Scan 으로 바뀌는데, **라이브 실측**
--    (2026-09-05, 강남 표본 필지·허가 54건·2회째)으로 4.067ms → 4.044ms — 차이가 소음이다.
--    반경 안 허가는 수십 건이라 힙 읽기 수십 번은 재지 않는다. 인덱스를 다시 짓지 않는다.
--    (수천 건이 걸리는 자리가 생기면 그때 include 에 arch_pms_day 를 더한다.)
--
-- 실행법
-- ------
--   python scripts/dbx.py -f supabase/migrations/2026-09-05b_permit_stale_cnt.sql
--
-- 적용한 사람이 보게 되는 것
-- --------------------------
--   · DROP FUNCTION ×2 · CREATE FUNCTION ×2 · COMMENT · REVOKE ×2 · GRANT · NOTIFY
--   · 화면의 "새로 올라오는 상가 건물" 줄 아래에 "그중 N동은 …" 한 줄이 붙는다.
--     N이 0이면 안 붙는다 — 그것도 정상이다.
--   · `python scripts/post_load.py --check` 는 그대로 exit 0 이어야 한다. 공개 호출
--     목록은 하나도 안 늘었다 — 같은 함수에 칸만 하나 더한 것이다.
--
-- 되돌리기: 2026-08-28b 의 같은 블록(칸 셋짜리 판)을 그대로 다시 돌린다 — 그때도 drop 이
-- 먼저다(같은 이유로 replace 가 거부된다).

-- ⛔ api(부르는 쪽)를 먼저 떨어뜨린다 — 막혀서가 아니라, 허공을 가리키는 순간을 안 만들려고(머리말 참조).
drop function if exists api.count_nearby_permits(text);
drop function if exists public.count_nearby_permits(text);

create or replace function count_nearby_permits(p_pnu text)
returns table (
  total_cnt    int,
  started_cnt  int,
  stale_cnt    int,
  base_ym      text
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ **파라미터를 그대로 쓰지 말 것.** 서명은 text 인데 pnu 컬럼은 char(19) 다.
  --    `char컬럼 = text파라미터` 는 컬럼 쪽이 캐스트돼 **인덱스가 통째로 무력해진다**
  --    (2026-08-16b 라이브 실측: 459.8ms ↔ 0.796ms).
  v_pnu char(19) := p_pnu;
  v_ym  char(6);
  -- 기준월의 **말일**. '2년 넘게 미착공'을 재는 자다 — 오늘이 아니라 **자료가
  -- 말하는 시점**이다. 이 표는 그 달의 상태를 찍은 것이라, 오늘로 재면 자료가
  -- 보지 못한 시간까지 섞어 세게 된다.
  v_month_end date;
begin
  select max(a.loaded_ym) into v_ym from arch_permit a;
  -- 아직 한 번도 안 담았다 = 줄 0개. "0곳"과 "모른다"는 다른 말이다.
  if v_ym is null then
    return;
  end if;
  v_month_end := (to_date(v_ym, 'YYYYMM') + interval '1 month' - interval '1 day')::date;

  return query
    with me as (
      select p.geom::geography as gg
        from parcel p
       where p.pnu = v_pnu and p.geom is not null
    ),
    near as (
      -- ⚠️ char(19)[] 이라야 한다. text[] 로 두면 배열 조건이 인덱스 안으로 못 들어가
      --    힙 필터로 밀린다(list_industry_mix 주석의 실측과 같은 병).
      -- 마지막 인자 false = 구면으로 잰다. 형제 함수들과 같은 자를 쓴다.
      select coalesce(array_agg(p.pnu), '{}'::char(19)[]) as pnus
        from parcel p cross join me
       where p.geom is not null
         and st_dwithin(p.geom::geography, me.gg, 500, false)
    ),
    hit as (
      -- ⛔ 허가일은 **세는 데만** 쓴다. 밖으로 나가는 것은 여전히 개수뿐이다.
      select a.real_stcns_day, a.arch_pms_day
        from arch_permit a cross join near
       where a.pnu = any(near.pnus)
         and a.loaded_ym = v_ym
         -- 표에는 미준공만 담기지만 규칙을 한 군데에만 두지 않는다 — 언젠가 누가 완공분까지
         -- 담기로 해도 이 화면은 계속 '곧 올라올 것'만 말해야 한다.
         and a.use_apr_day is null
         and left(a.main_purps_cd, 2) = any(array['03', '04', '07', '14'])
    )
    select (select count(*) from hit)::int,
           (select count(*) from hit where hit.real_stcns_day is not null)::int,
           -- ⛔ **재는 자는 기준월의 말일이다 — 오늘이 아니다.** 자료가 그 달
           --    상태라, 오늘로 재면 자료가 보지 못한 시간까지 섞어 세게 된다.
           -- ⛔ **빼는 수가 아니다.** 위 전체 곳수 안에 들어 있는 부분집합이다.
           -- ⛔ **'실효됐다'가 아니다.** 원본에 실효 칸이 아예 없어, 우리가 아는
           --    것은 '그 달 자료에 착공 기록이 없다'까지다(사장님 결재 2026-09-05).
           --    부등호도 **넘는 것만** 센다 — 딱 2년은 아직 아니다.
           (select count(*) from hit
             where hit.real_stcns_day is null
               and hit.arch_pms_day < (v_month_end - interval '2 years')::date)::int,
           v_ym::text
     where exists (select 1 from me);
end;
$$;

comment on function count_nearby_permits(text) is
  '이 필지에서 반경 500m 안에 **곧 올라올 상가 건물**이 몇 곳인가 — 전체 곳수, 그중 이미 '
  '착공한 곳수, 자료의 기준월. 대상은 사용승인이 안 난 최근(2023-01-01 이후) 허가분 중 '
  '주용도 대분류가 03(1종근생)·04(2종근생)·07(판매)·14(업무)인 것뿐이다. '
  '⛔ 주용도가 빈 값인 허가는 세지 않는다(모르는 것을 상가라고 부르지 않는다). '
  '⛔ 필지 좌표가 없으면 줄을 아예 안 돌려준다 — 0 곳과 "모른다"는 다른 말이다. '
  'security definer — arch_permit·parcel 이 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다. '
  '**나가는 것은 개수와 기준월뿐이다 — 건물 주소·이름은 한 글자도 안 나간다.** '
  '2026-09-05b: stale_cnt = 그중 **기준월 말일 기준으로 허가 후 2년 넘게 착공 기록이 '
  '없는** 곳수(전체 곳수 안에 들어 있는 부분집합이다). ⛔ "허가가 실효됐다"는 뜻이 '
  '아니다 — 원본에 실효 칸이 없어 단정하지 않는다.';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function count_nearby_permits(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.count_nearby_permits(p_pnu text)
returns table (
  total_cnt    int,
  started_cnt  int,
  stale_cnt    int,
  base_ym      text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.count_nearby_permits(p_pnu) $$;

revoke all on function api.count_nearby_permits(text) from public, anon, authenticated;
grant execute on function api.count_nearby_permits(text) to anon, authenticated;

-- ⛔ public.count_nearby_permits 는 끝까지 닫아 둔다 — 통과 함수가 security definer 라
--    소유자 권한으로 부르므로 anon 에게 열 필요가 없다.

-- 칸이 하나 늘었으므로 스키마 캐시를 다시 읽게 한다. 안 알리면 화면이 예전 칸 구성으로
-- 부르다 404(PGRST202) 를 맞는다.
notify pgrst, 'reload schema';
