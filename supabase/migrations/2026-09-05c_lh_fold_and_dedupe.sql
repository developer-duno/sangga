-- =====================================================================
-- 마이그레이션 2026-09-05c — 이 지역 공고라 해 놓고 남의 도시를 잔뜩 섞어 세고 있었다
-- =====================================================================
-- 실행법: python scripts/dbx.py -f supabase/migrations/2026-09-05c_lh_fold_and_dedupe.sql
--   → 그다음 `python scripts/post_load.py --check`
--   → 확인: 서울(11)로 부르면 `is_nationwide=false` 인 줄이 **먼저** 오고, 같은 제목이
--     여러 줄이던 것이 한 줄로 줄면서 그 줄의 `dup_cnt` 가 1 이상이 된다.
--       select is_nationwide, count(*) from api.list_lh_notices('11') group by 1;
--       -- 기대: 줄 수가 적용 전(39)보다 **줄어 있어야** 하고(같은 공고를 묶으므로),
--       --      false 쪽은 2026-09-05 실측대로 **4 근처**여야 한다. 정확한 값을 여기
--       --      박아 두지 않는다 — 창고가 매주 바뀌므로 박아 두면 곧 거짓말이 된다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇이 잘못돼 있었나 (2026-09-01 2차 감사 실측 + 2026-09-05 재실측)
-- ─────────────────────────────────────────────────────────────────────
-- ① **카드에 뜨는 것의 열에 아홉이 그 지역 공고가 아니다.**
--    2026-09-05 실측: 살아 있는 공고 52건 중 LH 가 지역을 '전국'이라 적은 것 **35건**,
--    서울 **4건**, 대전 **1건**(나머지는 아직 안 연 시도). 즉 서울을 고른 사람이 보는
--    39줄 중 35줄이 인천계양·부산명지·청주모충처럼 **다른 도시** 공고다.
--
-- ⛔ `is_nationwide` 의 뜻을 **바로잡아 둔다.** 예전 메모(알려진한계 §3·ROADMAP)는
--    "LH 지역본부 칸이 **비었다**"는 뜻이라 적었는데 **틀렸다.** 수집기 `map_sido` 실측:
--    빈 칸은 `(None, False)` 로 떨어지고, `is_nationwide` 가 참이 되는 것은 LH 가
--    `CNP_CD_NM` 에 **'전국'이라고 글자로 적어 준 경우뿐**이다. 결측이 아니라 LH 의 말이다.
--    그러니 우리가 할 말은 "지역 미상"이 아니라 **"LH가 지역을 '전국'으로 적었다"** 다.
--
-- ② **같은 공고가 여러 줄로 세어진다.**
--    2026-09-01 실측: 살아 있는 64줄 = 서로 다른 물건 **59개**(약 8%가 재게시·[정정공고]).
--    2026-09-05 실측: 52건 → 정규화 제목 기준 **47개**(중복 5). 카드가 말하는 'N건'이
--    그만큼 부풀어 있었다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 결재 (사장님, 2026-09-05)
-- ─────────────────────────────────────────────────────────────────────
-- ① LH 가 '전국'으로 적은 공고는 **접어 둔다** — 목록에는 그 지역 공고가 먼저 서고,
--    나머지는 "LH가 지역을 '전국'으로 적은 공고 N건" 이라는 묶음으로 접힌다.
--    ⛔ **제목에서 도시를 추측하지 않는다.** '인천계양'·'부산명지'가 제목에 있다고 그 줄을
--       인천·부산 공고로 옮기면, 지명이 안 든 제목·같은 이름의 다른 동네에서 조용히 틀린다.
--       틀린 지역표는 "없는 것"보다 나쁘다 — 사용자가 그 말을 믿고 헛걸음한다.
--    ⛔ **걸러서 지우지도 않는다.** 걸러 내면 서울 카드가 39→4건으로 사실상 빈다.
--       접어 두면 세 가지가 동시에 지켜진다: 그 지역 것이 먼저 보이고 · 나머지도 여전히
--       닿을 수 있고 · 무엇이 왜 접혔는지 화면이 글자로 밝힌다.
-- ② **종류가 같고, 대괄호 표시와 공백을 지운 제목이 같으면 한 줄**(최신 것)로 묶고
--    "정정·재게시 N회"를 적는다. 건수도 묶은 뒤 기준으로 센다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 묶는 열쇠가 `(kind_cd, regexp_replace(pan_nm, '\[[^]]*\]|\s+', '', 'g'))` 인가
-- ─────────────────────────────────────────────────────────────────────
-- 재게시는 두 가지 방식으로 제목을 흔든다: 앞에 `[정정공고]`·[취소공고] 같은 대괄호 표시가
-- 붙거나, 띄어쓰기가 달라진다. **둘 다 지워야** 같은 물건이 같은 열쇠를 갖는다 —
-- 하나만 지우면 라이브에서 60개·62개가 나왔다(둘 다 지운 값은 59개, 2026-09-01 실측).
--
-- ⛔ **제목만으로는 부족하다 — 종류(kind_cd)를 함께 잡는다.** 분양과 임대는 제목이 같아도
--    **다른 물건**이라 합치면 하나가 화면에서 사라진다. 라이브 실측(2026-09-05):
--    살아 있는 공고는 제목만 47 = 제목+종류 47 로 **오늘은 차이가 0** 이지만, 창고 전체
--    (마감 포함)는 제목만 **417** vs 제목+종류 **419** — 같은 제목에 종류가 다른 쌍이
--    실제로 **2건** 있었다. 오늘 안 겪는다고 안 나는 것이 아니다(그 2건이 다시 열리는 날
--    조용히 합쳐진다). ⓘ kind_cd 는 화면에 안 내보낸다 — 묶는 데만 쓴다.
-- ⛔ 제목을 **더 뭉개지 않는다**(숫자·기호까지 지우는 식). 묶는 기준이 헐거워지면 서로 다른
--    공고를 합치는데, 그건 여러 줄로 세는 것보다 **나쁘다** — 사용자가 못 보는 공고가 생긴다.
-- ⛔ `pan_id` 로 묶지 않는다 — 재게시는 **새 pan_id 를 받는다**(그래서 여러 줄이 된 것이다).
--
-- 무엇이 남는가(최신 판정): `notice_date desc nulls last, collected_at desc, pan_id desc`.
-- 공고일이 가장 늦은 것이 최신이고, 같으면 나중에 받아 둔 것, 그래도 같으면 pan_id 로
-- 정해 **답이 매번 흔들리지 않게** 한다(정렬 기준이 부족하면 같은 질문에 다른 답이 온다).
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 `limit 200` 인가 (보안 스캔 low)
-- ─────────────────────────────────────────────────────────────────────
-- 이 함수만 상한이 없었다 — 형제 `list_district_buildings` 는 200 에서 끊는다. 지금은 살아
-- 있는 공고가 52건이라 닿을 일이 없지만, 상한 없는 목록 함수는 자료가 늘거나 누가 반복해서
-- 부르는 날 창고·화면을 함께 끌어내린다. 같은 자릿수로 맞춰 둔다.
-- ⚠️ 200 에 닿으면 조용히 잘린다 — 마감 임박순이라 잘리는 쪽은 **먼 미래·마감일 미상**이다.
--    실제로 닿기 시작하면(공고가 200건을 넘으면) 그때는 상한이 아니라 페이지를 만들 때다.

begin;

-- 반환 표에 칸(is_nationwide·dup_cnt)을 더하므로 `create or replace` 로는 못 바꾼다
-- (`cannot change return type of existing function`). 지우고 다시 만들면 권한도 함께
-- 사라지므로 **아래에서 grant 를 반드시 다시 준다** — 안 주면 화면이 401 로 죽는다.
drop function if exists api.list_lh_notices(text);
drop function if exists public.list_lh_notices(text);

create or replace function list_lh_notices(p_sido text)
returns table (
  pan_id        text,
  pan_nm        text,
  kind_nm       text,
  pan_ss        text,
  notice_date   date,
  close_date    date,
  dtl_url       text,
  collected_at  timestamptz,
  is_nationwide boolean,
  dup_cnt       int
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ 파라미터를 그대로 쓰지 않는다 — 서명은 text 인데 컬럼은 char(2) 라, 그대로 비교하면
  --    컬럼 쪽이 캐스트돼 인덱스가 무력해진다(2026-08-16b 와 같은 함정).
  -- ⚠️ 앞 2자리만 쓴다 — 화면의 지역 고르개는 시군구 코드(11680)를 들고 있다.
  v_sido char(2) := nullif(left(btrim(coalesce(p_sido, '')), 2), '');
begin
  return query
    with alive as (
      -- ⛔ kind_cd 는 화면에 안 나가지만 **묶는 열쇠의 절반**이라 여기서 함께 든다
      --    (아래 partition 참조). 빼면 분양과 임대가 한 줄로 합쳐진다.
      select n.pan_id, n.pan_nm, n.kind_nm, n.kind_cd, n.pan_ss,
             n.notice_date, n.close_date, n.dtl_url, n.collected_at, n.is_nationwide,
             -- ⛔ 같은 공고를 묶는 열쇠(2026-09-05c). **대괄호 표시와 공백을 둘 다** 지운다 —
             --    재게시는 `[정정공고]` 가 붙거나 띄어쓰기가 달라지는 두 가지로 흔들려서,
             --    하나만 지우면 라이브에서 60·62 가 나왔다(둘 다 지우면 59 — 2026-09-01 실측).
             -- ⛔ 여기서 제목을 더 뭉개지 말 것 — 열쇠가 헐거워지면 **서로 다른 공고가 합쳐져**
             --    사용자가 못 보는 공고가 생긴다(여러 줄로 세는 것보다 나쁘다).
             regexp_replace(n.pan_nm, '\[[^]]*\]|\s+', '', 'g') as norm_key
        from lh_notice n
       where ((v_sido is not null and n.sido_code = v_sido) or n.is_nationwide)
         -- ⛔ `current_date` 로 되돌리지 말 것 — 이 DB 는 UTC 라 한국 새벽에 끝난 공고가
         --    아침 9시까지 남는다(2026-09-01a 머리말).
         -- ⛔ 마감일을 **모르는** 것(NULL)은 이 판정에서 **제외한다 = 그대로 남긴다.**
         --    모른다 ≠ 끝났다 — 모른다고 숨기면 살아 있는 공고가 조용히 사라진다.
         and (n.close_date is null or n.close_date >= (now() at time zone 'Asia/Seoul')::date)
         -- ⛔ LH 가 **끝났다고 적어 준 것**은 마감일과 무관하게 뺀다(2026-09-01d).
         --    마감일이 먼 미래로 적힌 공고는 날짜 필터가 원리적으로 못 거른다 —
         --    실측으로 '접수마감'인데 마감일 2028-12-31 인 것이 2건 있었고 하나는 [취소공고]다.
         -- ⛔ **허용 목록으로 바꾸지 말 것** — 새 상태가 생기는 날 살아 있는 공고가 통째로
         --    사라진다(표 정의가 CHECK 를 안 건 것과 같은 이유). 모르는 상태는 통과시킨다.
         and (n.pan_ss is null or n.pan_ss <> '접수마감')
    ),
    ranked as (
      -- 같은 열쇠(**종류 + 정규화 제목**) 안에서 **최신 한 줄만** 남긴다(rn=1). 최신은
      -- 공고일 → 받아 둔 시각 → pan_id 순으로 정한다 — 마지막 pan_id 까지 두는 것은
      -- 같은 질문에 매번 같은 답이 나오게 하기 위해서다(정렬 기준이 부족하면 흔들린다).
      -- ⛔ 종류(kind_cd)를 partition 에서 빼지 말 것 — 분양과 임대는 제목이 같아도 다른
      --    물건이라 합치면 하나가 화면에서 사라진다(창고 전체 실측 417 vs 419 = 2쌍).
      -- dup_cnt = **나 말고 몇 줄이 더 있었나**(0 이면 재게시 없음). 화면은 이 값이 있을
      -- 때만 "정정·재게시 N회"를 적는다.
      select a.*,
             row_number() over (partition by a.kind_cd, a.norm_key
                                    order by a.notice_date desc nulls last,
                                             a.collected_at desc,
                                             a.pan_id desc) as rn,
             (count(*) over (partition by a.kind_cd, a.norm_key) - 1)::int as dup_cnt
        from alive a
    )
    -- ⚠️ 바깥 별칭을 `n` 으로 둔다 — 아래 정렬이 `n.close_date` 로 읽혀야 마감 임박순 가드
    --    (tests/test_lh_notice_migration.py)가 옛 판들과 **같은 글자**로 이 함수를 지킨다.
    select n.pan_id, n.pan_nm, n.kind_nm, n.pan_ss,
           n.notice_date, n.close_date, n.dtl_url, n.collected_at,
           n.is_nationwide, n.dup_cnt
      from ranked n
     where n.rn = 1
     order by n.close_date asc nulls last, n.notice_date desc nulls last, n.pan_id
     -- ⛔ 상한을 없애지 말 것(2026-09-05c) — 형제 list_district_buildings 와 같은 자릿수다.
     --    닿으면 조용히 잘리는 쪽은 마감이 먼 것·마감일 미상이다. 닿기 시작하면 상한을
     --    늘릴 게 아니라 페이지를 만들 때다.
     limit 200;
end;
$$;

comment on function list_lh_notices(text) is
  '이 지역에서 지금 살아 있는 LH 상가 공고(마감 지난 것은 뺀다 — 창고에는 남아 있다). '
  '''전국'' 공고는 어느 지역을 골라도 함께 나온다. 시군구 코드를 넘겨도 앞 2자리로 본다. '
  '⛔ 마감 판정은 **한국 날짜**다(2026-09-01a) — DB 세션이 UTC 라 current_date 를 쓰면 '
  '한국 새벽 0~9시에 어제 끝난 공고가 남는다. '
  '⛔ LH 가 ''접수마감''이라 적은 것은 마감일과 무관하게 뺀다(2026-09-01d) — '
  '마감일이 먼 미래인 공고는 날짜만으로는 영영 못 거른다. '
  '⛔ is_nationwide 는 **LH 가 지역을 ''전국''이라 적었다**는 뜻이다(칸이 빈 것이 아니다) — '
  '화면은 그 줄들을 접어 두고 제목으로 지역을 추측하지 않는다(2026-09-05c). '
  '⛔ **종류가 같고** 대괄호 표시·공백을 지운 제목이 같으면 **최신 한 줄만** 주고 dup_cnt 로 나머지 수를 '
  '알린다(2026-09-05c) — 재게시는 새 pan_id 를 받아 같은 물건이 여러 줄이 된다. '
  '⛔ 200건에서 끊는다(2026-09-05c) — 상한 없는 목록은 자료가 늘 때 창고·화면을 함께 끈다.';

-- 만든 자리에서 다시 닫는다(형제 마이그레이션과 같은 관습).
revoke all on function list_lh_notices(text) from public, anon, authenticated;

create or replace function api.list_lh_notices(p_sido text)
returns table (
  pan_id        text,
  pan_nm        text,
  kind_nm       text,
  pan_ss        text,
  notice_date   date,
  close_date    date,
  dtl_url       text,
  collected_at  timestamptz,
  is_nationwide boolean,
  dup_cnt       int
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_lh_notices(p_sido) $$;

revoke all on function api.list_lh_notices(text) from public, anon, authenticated;
grant execute on function api.list_lh_notices(text) to anon, authenticated;

-- ⛔ public.list_lh_notices 는 끝까지 닫아 둔다 — 통과 함수가 security definer 다.
-- ⚠️ 2026-09-01b 부터 새 함수는 **닫힌 채 태어난다**(기본 권한 회수). 즉 위 grant 한 줄이
--    없으면 화면이 `permission denied for function` 을 만난다 — 지웠다 다시 만든 함수는
--    옛 권한을 하나도 물려받지 않는다.

commit;

notify pgrst, 'reload schema';
