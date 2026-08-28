-- =====================================================================
-- 건축인허가 — 곧 올라오는 건물 (2026-08-28b)
-- =====================================================================
-- 무엇이 들어오나
-- ---------------
-- 건축 허가를 받았지만 **아직 사용승인이 안 난** 건물이다. 원본은 건축HUB 대용량 파일
-- 분류 01 · opnTaskCd 0101(기본개요, 전국·월간). 한 줄에 허가일·착공일·사용승인일이 같이
-- 들어 있어서 **사용승인일이 빈 칸이면 아직 안 지어진 건물**이라는 뜻이 된다.
--
-- 2026-07 판 실측: zip 438,460,281 bytes · 원본 6,498,901행
--   − 사용승인이 났다(이미 지어짐)      3,301,029
--   − 허가일 형식 이상(범위 밖)             1,354
--   − 허가일 2023-01-01 미만·빈 값      2,639,991
--   = **적재 대상 556,527행** (그중 실제 착공한 것 61,332행)
--
-- ⚠️ **월 1회 수동 갱신이다.** 건축HUB 일괄 파일은 최근 3개월치만 남는다 — 받은 zip 은
--    `python scripts/backup_raw.py` 로 반드시 백업한다(절대 규칙 6 과 같은 이유).
--
-- 왜 용도로 안 거르고 다 담나
-- ----------------------------
-- "상가"만 골라 담으면 나중에 그 집합을 넓히거나 좁힐 때 원본이 없어 다시 못 만든다(위의
-- 3개월 보관). 표에는 미준공·최근 허가분을 통째로 담고, **무엇을 상가로 볼지는 읽는 함수
-- 한 곳에서만** 정한다. 556,527행은 그래도 작다.
--
-- ⛔ 한 칸짜리 PK 로 두면 다음 달 적재가 통째로 실패한다
-- -------------------------------------------------------
-- 관리_허가대장_PK 는 한 파일 안에서는 중복 0 이지만, **다음 달 파일에도 같은 값이 다시
-- 나온다**(같은 허가건이니 당연하다). 적재기는 `loaded_ym` 단위로 지우고 넣으므로, PK 가
-- 한 칸이면 지난달 행과 부딪혀 새 달 적재가 통째로 롤백된다. 그래서 **(PK, 기준월) 두 칸**을
-- 키로 삼는다 — 달마다 한 벌씩 쌓이고, 읽는 함수는 **가장 최근 기준월 한 벌만** 본다.
--
-- ⛔ 관리_허가대장_PK 는 bigint 에 안 들어간다
-- ---------------------------------------------
-- 실측 길이 분포에 22자리가 794,704행 있다(`1000000000000000045934`). bigint 최대는 19자리다.
-- 원본 정의도 VARCHAR(33)이므로 **text** 로 담는다. 숫자로 바꾸려다 넘치면 조용히 다른 건물이
-- 된다.
--
-- ⚠️ 옛 시도코드가 아주 조금 섞여 있다
-- -------------------------------------
-- 이 자료는 전남광주통합(12)을 이미 쓰고 있다(적재 대상 중 12 가 50,020행). 다만 옛 코드로
-- 남은 행이 조금 있다 — 42(강원) 26 · 45(전북) 23 · 46(전남) 16 · 29(광주) 1 = **66행**,
-- 그리고 시군구코드가 빈 행 204. 우리 parcel 에 없는 코드라 **그 행들은 어느 필지에도 안
-- 붙는다** — 0.05% 라 재코딩 규칙을 만들지 않는다(국세청 기준시가는 68,021행이라 만들었다).
--
-- ⚠️ 허가일에 오타가 섞여 있다
-- ----------------------------
-- 3000-01-01 처럼 달력에는 있지만 말이 안 되는 허가일이 70행(0.013%) 있다. **버리지 않는다** —
-- 날짜만 오타일 뿐 실재하는 미준공 허가라, 버리면 진짜 건물이 사라진다. 적재기가 dry-run
-- 리포트에 '기준월 이후 허가일' 몇 행인지 찍어 보여 준다.
--
-- ⛔ 대지_구분_코드는 PNU 대지구분과 코드가 다르다
-- -------------------------------------------------
-- 파일의 '0'이 PNU '1'(대지), '1'이 PNU '2'(산)다. 적재기는 대장 변환기가 이미 확정해 둔
-- 매핑(`convert_bldrgst_bulk.PLAT_GB_TO_PNU`)을 **그대로 가져다 쓴다**. 실측 조립률 99.959%
-- (블록·특수지번 6,587행 제외 분모). 조립 못 한 행도 버리지 않고 pnu 를 비워 담는다.

create table if not exists arch_permit (
  -- 관리_허가대장_PK. **숫자로 담지 않는다** — 22자리가 있어 bigint 를 넘는다(머리말 참조).
  mgm_pmsrgst_pk  text      not null,
  -- 기준월(YYYYMM). 달마다 한 벌이 쌓이고, 읽는 함수는 가장 최근 한 벌만 본다.
  loaded_ym       char(6)   not null,
  -- 조립 실패(블록·특수지번 등)를 **버리지 않고** 담기 위해 NULL 을 허용한다.
  pnu             char(19),
  sigungu_cd      char(5),
  plat_plc        text,                   -- 대지 위치(지번 주소 원문)
  arch_gb_nm      text,                   -- 신축·증축·개축 …
  main_purps_cd   text,                   -- 주용도 코드(5자리). 앞 두 글자가 대분류다
  main_purps_nm   text,
  tot_area        numeric(19,9),          -- 연면적(㎡)
  -- 필터가 '유효한 날짜이면서 2023-01-01 이상'만 통과시키므로 비어 있을 수 없다.
  arch_pms_day    date      not null,
  real_stcns_day  date,                   -- 실제 착공일. 있으면 **땅을 파기 시작한 것**
  -- 담는 행은 전부 NULL 이다(그것이 곧 '미준공'이다). 칸을 남겨 두는 이유는 표만 보고도
  -- 그 뜻을 알 수 있게 하기 위해서고, 적재 SQL 이 "전부 NULL 인가"를 다시 확인한다.
  use_apr_day     date,
  crtn_day        date,                   -- 원본 생성일자
  created_at      timestamptz default now(),
  primary key (mgm_pmsrgst_pk, loaded_ym)
);

comment on table arch_permit is
  '건축인허가 기본개요 중 **아직 사용승인이 안 난 최근 허가분**(건축HUB 분류 01·0101, 전국 월간). '
  '2026-07 판 실측 556,527행(원본 6,498,901행에서). 달마다 한 벌이 쌓이며 읽는 함수는 가장 '
  '최근 기준월만 본다. ⛔ anon 에게 통째로 닫혀 있고 count_nearby_permits() 로만 읽는다 — '
  '그것도 개수만 나간다(건물 주소·이름은 한 글자도 안 나간다). '
  '⚠️ 원본은 건축HUB 에 최근 3개월치만 남는다 — 받은 zip 은 backup_raw.py 로 백업할 것.';
comment on column arch_permit.mgm_pmsrgst_pk is
  '관리 허가대장 PK. **text 다** — 22자리 값이 있어 bigint 를 넘친다(원본도 VARCHAR(33)).';
comment on column arch_permit.loaded_ym is
  '원본 파일의 기준월(YYYYMM). 같은 허가건이 달마다 다시 나오므로 PK 의 한 칸이다 — '
  '한 칸짜리 PK 로 두면 다음 달 적재가 PK 충돌로 통째로 실패한다.';
comment on column arch_permit.use_apr_day is
  '사용승인일. 이 표에서는 **항상 NULL** 이다(그것이 곧 미준공이라는 뜻) — 값이 생기면 '
  '적재 관문이 통째로 되돌린다.';
comment on column arch_permit.real_stcns_day is
  '실제 착공일. 있으면 이미 공사가 시작된 것이라 "곧"이 더 가깝다는 뜻이다.';

-- 읽는 길은 "이 필지들 중 상가 미준공 몇 곳"뿐이다. 그래서 pnu 로 찾고, 세는 데 필요한
-- 칸을 **include 로 함께 실어** 힙에 안 가게 한다(idx_ub_pnu_cat 과 같은 처방).
-- ⛔ include 네 칸을 지우지 말 것 — 지워도 **에러는 안 나고 느려지기만 한다**(가장 늦게
--    발견되는 종류의 회귀다). 반경 안 이웃 필지가 수백~천 개라 힙 방문이 그만큼 늘어난다.
create index if not exists idx_arch_permit_pnu on arch_permit (pnu)
  include (loaded_ym, use_apr_day, main_purps_cd, real_stcns_day);

-- 같은 기준월을 다시 넣을 때(월 1회 갱신) 지우는 자리. 55만 행을 전수 훑지 않게 한다.
create index if not exists idx_arch_permit_ym on arch_permit (loaded_ym);

-- RLS 를 켜되 정책은 하나도 만들지 않는다 = 전부 거부(다른 표와 같은 방식).
alter table arch_permit enable row level security;

-- ⛔ RLS 만 믿지 않는다 — security definer 경로는 RLS 를 우회하므로 권한이 방어선이다.
--    ⚠️ 정본 위쪽의 `revoke all on all tables in schema public` 은 그 줄을 지날 때의 표만
--       닫는 일회성 명령이라 여기서 만든 표에는 안 걸린다. 만든 자리에서 다시 닫는다.
revoke all on arch_permit from public, anon, authenticated;

-- =====================================================================
-- count_nearby_permits — 이 필지 둘레에 곧 올라올 상가 건물이 몇 곳인가
-- =====================================================================
-- 한 줄만 돌려준다: 전체 곳수 · 그중 이미 착공한 곳수 · 어느 달 자료인가.
--
-- ## 무엇을 '상가'로 보나 (2026-07 판 적재 대상 556,527행 실측 분포가 근거다)
--
--   03 제1종근린생활시설  24,952   ← 동네 가게(소매·음식·미용 …)
--   04 제2종근린생활시설  39,882   ← 음식점·학원·사무소 … (04005 제조업소 1건 포함)
--   07 판매시설            1,617
--   14 업무시설            5,967
--   합계                  72,419  (적재 대상의 13.0%)
--
-- 일부러 뺀 것과 까닭:
--   · 15 숙박 6,609 · 16 위락 338 · 27 관광휴게 338 — 상가 매물 축이 아니다(확정 설계 §1 의
--     용도 4축에서 상업/업무만 본다).
--   · 17 공장 8,600 · 18 창고 7,629 — 산업물류 축이다.
--   · 01 단독주택 46,519 · 02 공동주택 5,056 — 주거다.
--   · **주용도가 빈 값 389,822행(70%)은 세지 않는다.** 모르는 것을 상가라고 부르지 않는다 —
--     여기를 열면 화면 숫자가 대여섯 배로 부풀고, 그 대부분이 상가가 아니다.
-- 앞 두 글자로 보는 이유: 코드가 대분류(2) + 세분류(3) 구조라, `04005 제조업소` 같은 하위
-- 코드가 새로 나와도 저절로 따라온다.
--
-- ## 왜 반경을 이웃 필지 배열로 재나
-- list_price_bands·list_industry_mix 가 같은 화면에서 이미 "반경 500m"를 이 방식으로
-- 정의해 쓴다. 두 블록이 서로 다른 자로 500m 를 재면 한 화면에서 '500m 안'이 두 가지를
-- 뜻하게 된다. `geom::geography` 로 바로 재면 gist 인덱스가 죽는다(2026-08-22 실측 47.7초).
--
-- ⛔ 좌표가 없으면 **줄을 아예 안 돌려준다**. 0 을 돌려주면 "둘레에 아무것도 안 생긴다"는
--    단정이 되는데, 사실은 모르는 것이다(list_industry_mix 와 같은 원칙).
create or replace function count_nearby_permits(p_pnu text)
returns table (
  total_cnt    int,
  started_cnt  int,
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
begin
  select max(a.loaded_ym) into v_ym from arch_permit a;
  -- 아직 한 번도 안 담았다 = 줄 0개. "0곳"과 "모른다"는 다른 말이다.
  if v_ym is null then
    return;
  end if;

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
      select a.real_stcns_day
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
  '**나가는 것은 개수와 기준월뿐이다 — 건물 주소·이름은 한 글자도 안 나간다.**';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function count_nearby_permits(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.count_nearby_permits(p_pnu text)
returns table (
  total_cnt    int,
  started_cnt  int,
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

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';
