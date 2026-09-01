-- =====================================================================
-- 마이그레이션 2026-09-01c — 함수 안 주석이 코드와 **반대말**을 하고 있었다
-- =====================================================================
-- 실행법: python scripts/dbx.py -f supabase/migrations/2026-09-01c_lh_comment_fix.sql
--   → 그다음 `python scripts/post_load.py --check`
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇이 잘못돼 있었나 (2026-09-01 적대검증에서 발견 — 내가 만든 결함)
-- ─────────────────────────────────────────────────────────────────────
-- `2026-09-01a` 로 넣은 주석 한 줄이 코드와 정반대를 말한다:
--
--     -- … 마감일을 **모르는** 것(NULL)은 여전히 뺀다.      ← 주석
--     and (n.close_date is null or n.close_date >= …)      ← 코드는 **남긴다**
--
-- 게다가 같은 함수 31줄 위의 기존 주석과도 정면 충돌한다("마감일을 모르는 공고(NULL)는
-- 빼지 않는다 — 모른다고 숨기면 살아 있는 공고가 조용히 사라진다").
--
-- ⛔ 왜 주석 하나에 마이그레이션을 쓰나: **이 주석은 함수 본문 안에 있다.** 즉 라이브
--    `pg_proc.prosrc` 에 그대로 실려 있어서, 나중에 누가 DB 안에서 이 함수를 읽으면
--    "NULL 은 뺀다"는 **틀린 안내**를 그대로 믿는다. 그 방향으로 고치면 마감일 미상
--    공고가 조용히 사라진다(지금은 `test_keeps_the_ones_with_no_close_date` 가 막지만,
--    주석이 시험과 싸우는 상태 자체가 결함이다).
--
-- ⛔ **`2026-09-01a` 를 제자리에서 고치지 않는다.** 그 파일은 이미 적용됐고, 마이그레이션은
--    "그날 라이브에 무엇을 넣었나"의 날짜 원장이다. 실제로 라이브 함수 소스에 그 옛 문구가
--    들어 있으므로(실측), 그 파일은 지금도 라이브를 정확히 재현한다 — 고치면 그 성질이
--    깨진다. ⓘ 이 규칙을 바로 앞에서 못 박아 놓고 내가 어겼다가 되돌린 자리다.
--
-- ⚠️ 코드는 **한 글자도 안 바뀐다.** 바뀌는 것은 함수 본문 안 주석 한 줄뿐이다.

begin;

create or replace function list_lh_notices(p_sido text)
returns table (
  pan_id       text,
  pan_nm       text,
  kind_nm      text,
  pan_ss       text,
  notice_date  date,
  close_date   date,
  dtl_url      text,
  collected_at timestamptz
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
    select n.pan_id, n.pan_nm, n.kind_nm, n.pan_ss,
           n.notice_date, n.close_date, n.dtl_url, n.collected_at
      from lh_notice n
     where ((v_sido is not null and n.sido_code = v_sido) or n.is_nationwide)
       -- ⛔ `current_date` 로 되돌리지 말 것 — 이 DB 는 UTC 라 한국 새벽에 끝난 공고가
       --    아침 9시까지 남는다(2026-09-01a 머리말).
       -- ⛔ 마감일을 **모르는** 것(NULL)은 이 판정에서 **제외한다 = 그대로 남긴다.**
       --    모른다 ≠ 끝났다 — 모른다고 숨기면 살아 있는 공고가 조용히 사라진다.
       --    (2026-09-01c: 여기 주석이 "여전히 뺀다"로 적혀 코드와 반대말을 하고 있었다.)
       and (n.close_date is null or n.close_date >= (now() at time zone 'Asia/Seoul')::date)
     order by n.close_date asc nulls last, n.notice_date desc nulls last, n.pan_id;
end;
$$;

comment on function list_lh_notices(text) is
  '이 지역에서 지금 살아 있는 LH 상가 공고(마감 지난 것은 뺀다 — 창고에는 남아 있다). '
  '''전국'' 공고는 어느 지역을 골라도 함께 나온다. 시군구 코드를 넘겨도 앞 2자리로 본다. '
  '⛔ 마감 판정은 **한국 날짜**다(2026-09-01a) — DB 세션이 UTC 라 current_date 를 쓰면 '
  '한국 새벽 0~9시에 어제 끝난 공고가 남는다.';

-- 만든 자리에서 다시 닫는다(형제 마이그레이션과 같은 관습).
revoke all on function list_lh_notices(text) from public, anon, authenticated;

commit;

notify pgrst, 'reload schema';
