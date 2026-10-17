-- =====================================================================
-- 참고 시세는 같은 용도 묶음끼리 — 층 용도로 가르기 · 주거·오피스텔 층은 값 안 냄 · 구 표 둘은 상가만 (2026-10-18a)
-- =====================================================================
-- 결정 0040(👤 2026-10-17·18 결정 10건). 설계 = docs/decisions/0040-참고시세-용도묶음-같은용도끼리.md §4-1.
--
-- 왜
-- --
-- 참고 시세(list_price_bands)의 네 갈래(L2·L4·L5·L6)와 구 단위 두 표(mv_sigungu_tx_stats ·
-- mv_sigungu_tx_yearly)가 **용도 조건 0** 으로 실거래를 모았다. 그래서 상가 층 시세에 업무·숙박 거래가
-- 섞였다 — 강남 3층+ 업무 834만 vs 2종근생 1,621만(섞은 값 922만) · 영등포 숙박 1,786만 vs 판매 544만
-- (섞은 값 785만) · 구 표 630칸 중 31% 가 상가만 세면 10% 이상 다르다(결정 0040 §1).
--
-- 무엇이 바뀌나
-- -------------
--   ① 묶음 함수 둘 — price_use_group_cd(대장 코드) · price_use_group_nm(실거래 이름). `language sql
--      immutable` · search_path·security definer 없음(인라인 — 요약표 33만 행 스캔에서 행마다 호출이
--      남지 않게). 묶음 = shop(1·2종근생·판매) / office(업무) / lodging(숙박) / other(기타) + 대장의
--      resid(주거) · 빈 값은 NULL.
--   ② 층 묶음 함수 price_floor_use_group(pnu, 층) — 그 층 구획을 묶어 면적이 큰 묶음(NULL 맨 뒤 · resid
--      그 다음 뒤 = 집 구획밖에 없는 층만 resid) · 오피스텔 낱말이 있고 shop 구획이 없으면 officetel.
--   ③ list_price_bands + api 쌍둥이 — 반환 칸 끝에 use_group. 1층·지하 판정 뒤에 층 묶음을 보고
--      NULL → no_use · resid → floor_resid · officetel → floor_officetel. 그 밖이면 네 갈래 **모두**
--      `price_use_group_nm(t.main_use) = v_grp`. ⛔ 반환 칸이 바뀌어 `create or replace` 가 거부된다
--      ("cannot change return type") → 부르는 쪽(api)부터 지우고 다시 만든다(2026-10-08a 와 같은 순서).
--   ④ mv_sigungu_tx_stats(구 × 층대 단가) — 상가 거래만(where). 칸 구성 그대로.
--   ⑤ mv_sigungu_tx_yearly(동네 단가 흐름) — 상가 거래만(**where** — 단가·n_all·floor_missing·ym_cnt·
--      first_ym·last_ym 모두 · 결정 0040 D8). 지분은 지금처럼 filter(단가·n·면적에서만 뺀다).
--      ⛔ 물질화뷰는 정의를 못 고친다 → 떨어뜨리고 다시 굽는다(`if not exists` 면 아무 일도 안 한다).
--   ⓘ 머리(security definer · set search_path · stable)와 comment 는 정본(schema.sql)에서 글자 그대로
--      잘라 붙였다(create or replace 는 머리 속성을 새 정의로 덮어쓴다 — 시험이 글자 대조).
--
-- 바꾸지 않는 것
-- --------------
--   · get_sigungu_tx_stats · get_sigungu_tx_yearly — 문자열 본문 sql 함수라 물질화뷰 의존이 기록되지
--     않는다(뷰를 떨어뜨려도 막히지 않고, 같은 이름·같은 칸으로 다시 세우면 그대로 읽는다).
--   · mv_tx_parcel_geog(반경 이웃 표) — "거래가 한 건이라도 있는 필지" 상한만 진다. 묶음은 L4·L5 가
--     거래 쪽에서 건다.
--   · price_gate_sigungu(통과 구) — 이 파일은 표를 안 건드린다. 성적표 v3 로 load_price_gate.py 가 채운다.
--   · 공개 호출 허용 목록(post_load.py --check) — 함수 이름·서명이 그대로라 늘지 않는다. 새 함수 셋은
--     public 에서 닫힌 채 태어난다(revoke · 화면은 api 로만 들어온다).
--
-- 의존 확인 (적용 **전**에 한 번 — 둘 다 0행이어야 drop 이 막히지 않는다)
-- ---------------------------------------------------------------------
--   -- 두 요약표에 기대는 뷰·요약표(자기 자신 제외):
--   select distinct c.relname
--     from pg_depend d
--     join pg_rewrite r on r.oid = d.objid
--     join pg_class c on c.oid = r.ev_class
--    where d.refobjid in ('mv_sigungu_tx_stats'::regclass, 'mv_sigungu_tx_yearly'::regclass)
--      and c.oid not in ('mv_sigungu_tx_stats'::regclass, 'mv_sigungu_tx_yearly'::regclass);
--   -- api 쌍둥이에 기대는 것:
--   select d.classid::regclass, d.objid, d.deptype
--     from pg_depend d
--    where d.refobjid = 'api.list_price_bands(text)'::regprocedure;
--
-- 잠금
-- ----
-- `drop materialized view` 는 그 요약표에 ACCESS EXCLUSIVE 잠금을, `drop function` 은 함수에 잠금을 잡고
-- **commit 까지** 이어진다(PostgreSQL 문서 DROP MATERIALIZED VIEW · 명시 잠금 표). 실거래 표 자체에는
-- 읽기 잠금(ACCESS SHARE)만 걸린다 — 표를 다시 쓰지 않는다. 요약표 둘을 굽는 동안(10-08 07:04 실측 각
-- 1초 안팎) 구 단가·동네 흐름·참고 시세 화면은 오류가 아니라 잠깐 기다림이다 → 그래도 사람 적은 시간에.
-- `lock_timeout = '2s'` 는 **begin 앞**(세션 설정)에 둔다 — 2초 넘게 못 잡으면 통째로 되돌아가 아무것도
-- 안 바뀐다. 다시 돌리면 된다(함수는 create or replace · 뷰는 drop if exists 뒤 다시 굽는다).
--
-- ⛔ 전부 아니면 전무 — `begin; … commit;`
-- -----------------------------------------
-- `scripts/dbx.py -f` 는 자동커밋이다. 함수·뷰를 지운 뒤 끊기면 참고 시세·구 단가·동네 흐름이 통째로
-- 사라진 채 남고 post_load.py 의 refresh 가 "그런 뷰 없음"으로 멈춘다 — 한 덩어리로 묶는다.
-- `notify pgrst` 는 commit **뒤**.
--
-- ① 운영 절차 (결정 0040 §6 — 👤 허락 한 번에 2→3→4 를 한 자리에서 잇는다)
-- -------------------------------------------------------------------------
--   ⓪ 적용 직전 기록: 위 의존 확인 쿼리 둘(0행) · 참고 시세 찬·더운 캐시 실행시간
--      (`explain (analyze, buffers) select * from api.list_price_bands('<본보기 pnu>');` — 10-08a 뒤 73~101ms).
--   ① 워크트리(이 가지)에서 적용:
--        python scripts/dbx.py -f supabase/migrations/2026-10-18a_price_use_group.sql
--   ② python scripts/post_load.py → **워크트리에서** python scripts/post_load.py --check
--      (본 폴더 main 의 옛 정본으로 돌리면 함수 드리프트가 뜬다 · 기대 = 드리프트 0 · 허용 목록 그대로 ·
--       「transaction.main_use 7종 밖」 0).
--   ③ python scripts/load_price_gate.py (성적표 v3 통과구.csv · 관문 3종).
--   ④ 바로 PR 머지(= 배포) → 라이브 엔진 3벌 전/후 캡처. 같은 ⓪ 의 실행시간을 다시 재 PROGRESS 에 전/후.
--
-- 적용한 사람이 보게 되는 것 (파일의 실제 문장 순서)
-- --------------------------------------------------
--   SET · BEGIN ·
--   CREATE FUNCTION · COMMENT · REVOKE · CREATE FUNCTION · COMMENT · REVOKE ·
--   CREATE FUNCTION · COMMENT · REVOKE ·
--   DROP FUNCTION ×2 · CREATE FUNCTION · COMMENT · REVOKE · CREATE FUNCTION · REVOKE · GRANT ·
--   DROP MATERIALIZED VIEW · SELECT n · COMMENT · CREATE INDEX · ANALYZE · REVOKE ·
--   DROP MATERIALIZED VIEW · SELECT n · COMMENT · CREATE INDEX · ANALYZE · REVOKE ·
--   COMMIT · NOTIFY
--
-- ② 되돌리기 — **새 마이그레이션 파일**로(이 파일은 적용된 원장이라 고치지 않는다) + 정본 되돌림(PR revert)
-- -----------------------------------------------------------------------------------------------------
--   순서(결정 0040 §6): ⓐ 화면 PR revert(배포) ⓑ 통과 구 = v2 판으로 —
--     git show 700a254:docs/backtest/통과구.csv > <임시>/통과구-v2.csv
--     python scripts/load_price_gate.py --csv <임시>/통과구-v2.csv
--   ⓒ 아래 SQL(새 파일 `<날짜>_revert_price_use_group.sql`) ⓓ python scripts/post_load.py.
--   ⛔ 묶음 함수 셋은 **맨 끝에** 지운다 — 요약표 둘이 price_use_group_nm 에 기대므로(pg_depend 'n')
--      요약표를 옛 정의로 다시 구운 뒤에야 지워진다. `cascade` 금지(무엇이 같이 사라질지 모른 채 지운다).
--
--   set lock_timeout = '2s';
--   begin;
--   drop function if exists api.list_price_bands(text);
--   drop function if exists public.list_price_bands(text);
--   -- public 9칸 = 2026-10-08a 파일 ⑥ 의 list_price_bands 정의 블록(그 파일 282-479행)과
--   --   `comment on function list_price_bands(text)`(481-489행)를 글자 그대로.
--   revoke all on function list_price_bands(text) from public, anon, authenticated;
--   -- api 쌍둥이 9칸 = 700a254 판 schema.sql 의 api.list_price_bands 정의(그 판 4025-4041행 —
--   --   `git show 700a254:supabase/schema.sql`)를 글자 그대로(window_from 이 마지막 칸).
--   ⓘ 이 머리말에는 함수 정의 문장을 글자로 적지 않는다 — tests/test_schema_function_drift.py 의
--     파서가 주석을 안 걷어 내 그 글자부터 다음 함수 본문까지를 한 함수로 삼키기 때문이다.
--   revoke all on function api.list_price_bands(text)             from public, anon, authenticated;
--   grant execute on function api.list_price_bands(text)             to anon, authenticated;
--   -- 요약표 둘 = 2026-10-08a 파일 ④⑤ 블록(그 파일 192-279행 — drop → create → comment → 유일 색인 →
--   --   analyze → revoke)을 글자 그대로. 상가 조건이 없는 판이다.
--   drop function if exists price_floor_use_group(char(19), smallint);
--   drop function if exists price_use_group_nm(text);
--   drop function if exists price_use_group_cd(text);
--   commit;
--   notify pgrst, 'reload schema';
--   ⓘ 되돌린 뒤 `post_load.py --check` 의 함수 드리프트는 정본을 같은 PR revert 로 되돌려야 0 이 된다.

set lock_timeout = '2s';

-- ⛔ 여기부터 commit 까지가 **한 덩어리**다(위 머리말 참조).
begin;

-- ① 용도 묶음 함수 둘 — 인라인되게 search_path·security definer 없음(정본 머리말 참조).
create or replace function price_use_group_cd(p_cd text)
returns text
language sql
immutable
parallel safe
as $$
  -- 대장 주용도코드(building_floor.main_purps_cd) 앞 두 자리. Z3(옛 기타근린생활)·Z6(옛 판매및영업)은
  -- 옛 분류라 상가로 본다(Z3 에는 사무소·공공시설이 약 1할 섞여 있다 — 알려진한계). Z8 등 그 밖은 other.
  select case
    when nullif(p_cd, '') is null                          then null
    when left(p_cd, 2) in ('03', '04', '07', 'Z3', 'Z6')   then 'shop'
    when left(p_cd, 2) in ('14')                           then 'office'
    when left(p_cd, 2) in ('15')                           then 'lodging'
    when left(p_cd, 2) in ('01', '02')                     then 'resid'
    else                                                        'other'
  end
$$;

comment on function price_use_group_cd(text) is
  '결정 0040 용도 묶음(대장 코드) — main_purps_cd 앞 두 자리: 03·04·07·Z3·Z6=shop(상가) / 14=office(업무) / '
  '15=lodging(숙박) / 01·02=resid(주거) / NULL·빈 글자=NULL / 그 밖=other(기타). '
  '백테스트 USE_GROUP_CD 와 글자 대조(tests/test_price_ladder_sync.py). 인라인되게 search_path 를 안 박는다. 내부용';

revoke all on function price_use_group_cd(text) from public, anon, authenticated;

create or replace function price_use_group_nm(p_nm text)
returns text
language sql
immutable
parallel safe
as $$
  -- 실거래 건물 주용도(transaction.main_use — 국토부 buildingUse 이름 7종). 주거 묶음은 없다
  -- (상업업무용 실거래에는 주택이 안 온다).
  select case
    when nullif(p_nm, '') is null                              then null
    when p_nm in ('제1종근린생활', '제2종근린생활', '판매')     then 'shop'
    when p_nm in ('업무')                                      then 'office'
    when p_nm in ('숙박')                                      then 'lodging'
    else                                                            'other'
  end
$$;

comment on function price_use_group_nm(text) is
  '결정 0040 용도 묶음(실거래 이름) — transaction.main_use: 제1종근린생활·제2종근린생활·판매=shop(상가) / '
  '업무=office / 숙박=lodging / NULL·빈 글자=NULL / 교육연구·기타·모르는 글자=other(기타). '
  '백테스트 USE_GROUP_NM 과 글자 대조(tests/test_price_ladder_sync.py). 인라인되게 search_path 를 안 박는다. 내부용';

revoke all on function price_use_group_nm(text) from public, anon, authenticated;

-- ② 그 층의 용도 묶음 — 표를 읽어 search_path 를 박는다(층마다 한 번 불린다).
create or replace function price_floor_use_group(p_pnu char(19), p_floor smallint)
returns text
language sql
stable
set search_path = public
as $$
  with seg as (
    select bf.main_purps_cd, bf.main_purps_nm, bf.etc_purps, bf.area_m2, bf.area_excluded
      from building_floor bf
     where bf.pnu = p_pnu
       and bf.floor_no = p_floor
  ),
  use_seg as (
    select s.*
      from seg s
     where not s.area_excluded
        or not exists (select 1 from seg x where not x.area_excluded)
  ),
  grp as (
    select price_use_group_cd(u.main_purps_cd) as g,
           sum(coalesce(u.area_m2, 0))         as area
      from use_seg u
     group by 1
  ),
  nm as (
    select '오피스텔'::text as officetel_re
  )
  select case
           when exists (select 1 from use_seg u cross join nm
                         where u.main_purps_nm ~ nm.officetel_re
                            or coalesce(u.etc_purps, '') ~ nm.officetel_re)
            and not exists (select 1 from grp where grp.g = 'shop')
             then 'officetel'
           else (select grp.g from grp
                  order by grp.g is null, grp.g = 'resid', grp.area desc, grp.g
                  limit 1)
         end
$$;

comment on function price_floor_use_group(char(19), smallint) is
  '결정 0040 그 층의 용도 묶음 — 연면적 제외 아닌 구획(없으면 전부)을 price_use_group_cd 로 묶어 면적 합이 '
  '큰 묶음(NULL 맨 뒤 · resid 그 다음 뒤 = 집 구획밖에 없는 층만 resid). 오피스텔 낱말이 있고 shop 구획이 '
  '없으면 officetel. 대장에 그 층이 없으면 NULL. list_price_bands 와 백테스트(pg_temp 사본)가 같은 본문. 내부용';

revoke all on function price_floor_use_group(char(19), smallint) from public, anon, authenticated;

-- ③ 참고 시세 사다리 — 돌려주는 칸이 늘어 replace 가 거부된다 → api(부르는 쪽)를 먼저 지운다
--    (허공을 가리키는 순간을 안 만들려고 — 2026-10-08a 와 같은 순서).
drop function if exists api.list_price_bands(text);
drop function if exists public.list_price_bands(text);

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
  window_from     text,
  use_group       text
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
  -- ⓘ 변수 대입(text→char(19))은 19자를 넘는 입력에서 **자르지 않고 에러**(value too long)를
  --    낸다 — 끝 공백만 조용히 버린다(2026-09-27 라이브 실측, 예전 주석의 "자른다"는 틀렸다).
  --    화면은 19자 pnu 만 보내므로 무해하다(더 긴 입력은 애초에 pnu 가 아니다).
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
  -- 그 층의 용도 묶음(결정 0040) — shop·office·lodging·other·resid·officetel·NULL.
  v_grp      text;
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
                        null::numeric, null::numeric, null::numeric, null::numeric, v_from::text,
                        null::text;
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
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text,
                          null::text;
      continue;
    end if;

    -- 지하(음수)·옥탑(99)·층미상은 백테스트 표본이 **0건**이다(2017년부터 실거래 원본에
    -- 지하층 표기가 오지 않는다 — 알려진한계). 검증된 적 없는 층에는 값을 내지 않는다.
    if v_floor is null or v_floor < 0 or v_floor = 99 then
      return query select v_floor, 'no_evidence'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text,
                          null::text;
      continue;
    end if;

    -- 그 층의 용도 묶음(2026-10-18a · 결정 0040) — 1층·지하 판정 **뒤**, 사다리 **앞**.
    -- 묶음을 모르면(대장 코드 빈칸) 안 낸다 · 주거·오피스텔 층은 상가 시세를 안 낸다.
    v_grp := price_floor_use_group(v_pnu, v_floor);

    if v_grp is null then
      return query select v_floor, 'no_use'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text,
                          null::text;
      continue;
    end if;

    if v_grp = 'resid' then
      return query select v_floor, 'floor_resid'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text,
                          null::text;
      continue;
    end if;

    if v_grp = 'officetel' then
      return query select v_floor, 'floor_officetel'::text, null::text, null::int,
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text,
                          null::text;
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
            -- ⛔ 네 갈래 **모두** 지분 거래(is_share)를 뺀다(2026-10-08a) — 건물 일부 몫만 사고판
            --    거래라 ㎡당 단가가 약 0.39배로 낮게 나온다. 한 갈래만 빠뜨리면 그 단계의 밴드만
            --    조용히 내려앉는다(에러 0). 칸 조건이라 색인(idx_tx_pnu·idx_tx_pnu10_ym)은 그대로 탄다.
            -- ⛔ 네 갈래 **모두** 같은 용도 묶음(price_use_group_nm(t.main_use) = v_grp)만 센다(2026-10-18a ·
            --    결정 0040 D1) — 지분과 같은 병이다: 한 갈래만 빠지면 그 단계만 업무·숙박이 조용히 섞인다.
            --    묶음 함수는 인라인되는 immutable SQL 이라 행마다 함수 호출이 남지 않는다.
            -- L2 — 같은 필지 같은 층
            select 'L2'::text as lvl, t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null and not t.is_share
               and price_use_group_nm(t.main_use) = v_grp
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
             where t.tx_type = '집합' and t.unit_price is not null and not t.is_share
               and price_use_group_nm(t.main_use) = v_grp
               and t.contract_ym >= v_from
               and t.floor_no = v_floor and t.pnu = any(v_near100)
            union all
            -- L5 — 반경 500m 같은 층
            select 'L5', t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null and not t.is_share
               and price_use_group_nm(t.main_use) = v_grp
               and t.contract_ym >= v_from
               and t.floor_no = v_floor and t.pnu = any(v_near500)
            union all
            -- L6 — 같은 법정동(PNU 앞 10자리) 같은 층대
            -- "행정동" 이 아니라 법정동인 이유: 실거래의 동은 문자, 건물의 동은 코드라
            -- 이름 대조가 조용히 어긋난다(성적표 §1 · 결정 0012 §4).
            select 'L6', t.unit_price, t.bld_area_m2
              from transaction t
             where t.tx_type = '집합' and t.unit_price is not null and not t.is_share
               and price_use_group_nm(t.main_use) = v_grp
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
                          null::numeric, null::numeric, null::numeric, null::numeric, v_from::text,
                          v_grp;
    else
      return query select v_floor, 'ok'::text, v_stage, v_n,
                          v_p25, v_med, v_p75, v_area, v_from::text,
                          v_grp;
    end if;
  end loop;
  return;
end;
$$;

comment on function list_price_bands(text) is
  'Stage B(결정 0013) 이 필지의 층별 참고 시세 밴드 — 곁의 실거래(최근 24개월·집합·지분 거래 제외 — 2026-10-08a)로 어림한 '
  '추정값이며 감정평가가 아니다. 한 층에 한 줄이고 status 가 그 줄의 성격을 말한다: '
  'gate_fail(이 구는 기준선 미달 — 층 나열 없이 한 줄) / floor_1f(1층 미제공) / '
  'no_evidence(지하·옥탑·층미상 — 백테스트 표본 0건) / no_use(대장에 그 층 용도 없음) / '
  'floor_resid(주거 층) / floor_officetel(오피스텔 층) / no_estimate(표본 부족) / ok(밴드). '
  '2026-10-18a(결정 0040): 네 갈래 모두 그 층의 대장 용도 묶음(price_floor_use_group)과 같은 묶음 거래만 센다 — '
  'use_group 은 ok·no_estimate 줄의 묶음(shop 상가·office 업무·lodging 숙박·other 기타), 다른 줄은 NULL. '
  'ok 인 줄은 stage(L2·L4·L5·L6)와 n(표본 수)을 **반드시 함께** 표시한다(절대 규칙 3). '
  'p25/median/p75 는 ㎡당 단가, median_area_m2 는 총액 환산용 후보 면적 중앙값이다. '
  'security definer — transaction·parcel·price_gate_sigungu 가 anon 에게 닫혀 있어 '
  '소유자 권한으로 대신 읽는다. 나가는 것은 층·통계값뿐(개별 거래·상호명은 나가지 않는다)';

-- public 원본은 닫는다 — 화면이 부르는 것은 api.list_price_bands 뿐(2026-09-05a)
revoke all on function list_price_bands(text) from public, anon, authenticated;

create or replace function api.list_price_bands(p_pnu text)
returns table (
  floor_no        smallint,
  status          text,
  stage           text,
  n               int,
  p25             numeric,
  median          numeric,
  p75             numeric,
  median_area_m2  numeric,
  window_from     text,
  use_group       text
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_price_bands(p_pnu) $$;

revoke all on function api.list_price_bands(text)             from public, anon, authenticated;
grant execute on function api.list_price_bands(text)             to anon, authenticated;

-- ④ 구 × 층대 단가 — 상가 거래만. 물질화뷰는 정의를 못 고친다 → 떨어뜨리고 다시 굽는다.
--    ⓘ get_sigungu_tx_stats 는 문자열 본문 sql 함수라 의존이 기록되지 않아 막지 않는다(머리말).
drop materialized view if exists mv_sigungu_tx_stats;

create materialized view mv_sigungu_tx_stats as
with win as (
  select to_char((now() at time zone 'Asia/Seoul') - interval '24 months', 'YYYYMM') as from_ym
)
select
  t.sigungu_code,
  case
    when t.floor_no is null then '층미상'
    when t.floor_no < 0    then '지하'
    when t.floor_no = 1    then '1층'
    when t.floor_no = 2    then '2층'
    else                        '3층이상'
  end                                                              as floor_band,
  min(w.from_ym)                                                   as window_from,
  count(*)::int                                                    as n,
  percentile_cont(0.5)  within group (order by t.unit_price)       as median_unit_price,
  percentile_cont(0.25) within group (order by t.unit_price)       as p25_unit_price,
  percentile_cont(0.75) within group (order by t.unit_price)       as p75_unit_price
from transaction t
cross join win w
where t.tx_type = '집합'
  and t.unit_price is not null
  and not t.is_share
  and price_use_group_nm(t.main_use) = 'shop'
  and t.contract_ym >= w.from_ym
group by t.sigungu_code, 2;

comment on materialized view mv_sigungu_tx_stats is
  'Stage A(결정 0012) 구×층대 실거래 단가 분포 — 집합(구분소유) 거래만, 갱신 시점 기준 24개월. '
  '2026-10-08a: 지분 거래(is_share)는 뺀다 — 건물 일부 몫이라 ㎡당 단가가 낮게 나온다. '
  '2026-10-18a: 상가(근생·판매) 거래만 — 결정 0040 D3(price_use_group_nm(main_use) = shop · 업무·숙박·기타는 안 센다). '
  'window_from 은 그 창의 시작 달을 굳혀 둔 것이다(화면이 "최근 24개월"만 적으면 갱신을 미룬 날 '
  '그 문구가 조용히 거짓말이 된다). n 은 단가를 낼 수 있었던 행 수 = 중앙값의 실제 근거 수다. '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 로 갱신할 것. '
  '⛔ anon 에게 열지 않는다 — 화면은 get_sigungu_tx_stats() 로만 읽는다.';

-- 뷰와 함께 사라진 유일 색인을 다시 만든다 — 없으면 post_load 의 refresh concurrently 가 멈춘다.
create unique index if not exists idx_msts_key on mv_sigungu_tx_stats (sigungu_code, floor_band);

analyze mv_sigungu_tx_stats;

-- ⛔ 다시 만든 뷰는 다시 열려 있을 수 있다(pg_default_acl) — 만든 자리에서 다시 닫는다.
revoke all on mv_sigungu_tx_stats from public, anon, authenticated;

-- ⑤ 동네 단가 흐름 — 상가 거래만(where — 건수까지 상가만 · 결정 0040 D8). 지분은 그대로 filter.
drop materialized view if exists mv_sigungu_tx_yearly;

create materialized view mv_sigungu_tx_yearly as
select
  t.sigungu_code,
  substr(t.contract_ym, 1, 4)                                                   as yr,
  count(*)::int                                                                 as n_all,
  count(*) filter (where t.unit_price is not null and not t.is_share)::int      as n,
  percentile_cont(0.5)  within group (order by t.unit_price)
    filter (where t.unit_price is not null and not t.is_share)                  as median_unit_price,
  percentile_cont(0.25) within group (order by t.unit_price)
    filter (where t.unit_price is not null and not t.is_share)                  as p25_unit_price,
  percentile_cont(0.75) within group (order by t.unit_price)
    filter (where t.unit_price is not null and not t.is_share)                  as p75_unit_price,
  -- 그 해 단가의 **근거가 된 거래 한 건**이 얼마나 큰 물건이었나(2026-09-09b).
  -- ⛔ filter 를 위 셋과 **똑같이** 둔다 — 다른 모집단에서 재면 두 숫자가 서로 다른 거래를
  --    말하게 된다. `unit_price` 는 `bld_area_m2 > 0` 일 때만 생기는 생성 컬럼이라, 이
  --    filter 하나로 면적이 0·빈 행은 자연히 빠진다(면적 조건을 따로 적을 이유가 없다).
  percentile_cont(0.5)  within group (order by t.bld_area_m2)
    filter (where t.unit_price is not null and not t.is_share)                  as median_area_m2,
  count(*) filter (where t.floor_no is null)::int                               as floor_missing,
  count(distinct t.contract_ym)::int                                            as ym_cnt,
  min(t.contract_ym)                                                            as first_ym,
  max(t.contract_ym)                                                            as last_ym
from transaction t
where t.tx_type = '집합'
  and price_use_group_nm(t.main_use) = 'shop'
group by t.sigungu_code, substr(t.contract_ym, 1, 4);

comment on materialized view mv_sigungu_tx_yearly is
  '결정 0027 구×연도 집합(구분소유) 실거래 단가 요약 — 동네 매매 단가 흐름 카드의 재료. '
  'n 은 단가가 있어 중앙값 근거가 된 행 수, n_all 은 그 해 집합 거래 전부(층 미상 비율 분모), '
  'ym_cnt·first_ym·last_ym 은 자료가 해의 일부뿐인지 화면이 적기 위한 값. '
  '2026-09-09b: median_area_m2 = 그 해 단가의 근거가 된 거래 **한 건**의 건물면적 중앙값(㎡) — '
  '단가와 같은 모집단에서 잰다. 다른 해보다 유난히 작으면 초소형 구획이 무더기로 거래된 해다. '
  '2026-10-08a: 지분 거래(is_share)는 단가 셋·n·median_area_m2 에서 빼고 n_all·floor_missing·ym_cnt·first_ym·last_ym 에는 센다. '
  '2026-10-18a: 상가(근생·판매) 거래만 — 결정 0040 D3·D8(where — 단가·n_all·floor_missing·ym_cnt·first_ym·last_ym 모두 상가 거래만). '
  '⚠️ 자료를 새로 넣으면 `python scripts/post_load.py` 로 갱신할 것. '
  '⛔ anon 에게 열지 않는다 — 화면은 api.get_sigungu_tx_yearly() 로만 읽는다.';

create unique index if not exists idx_msty_key on mv_sigungu_tx_yearly (sigungu_code, yr);

analyze mv_sigungu_tx_yearly;

revoke all on mv_sigungu_tx_yearly from public, anon, authenticated;

commit;

-- 반환 칸이 늘었으므로 스키마 캐시를 다시 읽게 한다. 안 알리면 화면이 옛 칸 구성으로 부르다
-- 404(PGRST202)를 맞는다.
notify pgrst, 'reload schema';
