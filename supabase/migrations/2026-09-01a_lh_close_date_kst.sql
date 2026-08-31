-- =====================================================================
-- 마이그레이션 2026-09-01a — LH 공고 마감 판정을 **한국 날짜**로
-- =====================================================================
-- 실행법: python scripts/dbx.py -f supabase/migrations/2026-09-01a_lh_close_date_kst.sql
--   → 그다음 `python scripts/post_load.py --check` (노출면 재측정).
--
-- ─────────────────────────────────────────────────────────────────────
-- 무엇이 잘못돼 있었나
-- ─────────────────────────────────────────────────────────────────────
-- `list_lh_notices`(2026-08-28a 로 만든 것)가 마감을 `close_date >= current_date` 로
-- 걸렀다. `current_date` 는 **그 세션의 시간대**로 오늘을 정하는데, 이 DB 는 UTC 다:
--
--     pg_settings.TimeZone = UTC (source = configuration file)   ← 2026-08-31 실측
--     pg_roles.rolconfig — authenticator·anon·authenticated 누구도 TimeZone 미설정
--
-- 화면이 지나가는 길(PostgREST → authenticator → anon)도 그래서 UTC 다. 결과:
-- **한국 시각 00:00~09:00 사이에는 어제 한국에서 끝난 공고가 목록에 그대로 남는다**
-- (그 시각 UTC 는 아직 어제라 `close_date >= current_date` 가 참이다). 최대 9시간.
--
-- 이 화면의 값어치가 정확히 "지금 신청할 수 있는 것만 보여 준다"라서, 끝난 공고를
-- 아침 내내 보여 주는 것은 이 카드가 하겠다고 한 일의 반대다. 게다가 사용자는
-- 그 링크를 눌러 LH 청약센터까지 가서야 마감을 알게 된다(헛걸음).
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 2026-08-28a 를 고치지 않고 새 파일을 만드나
-- ─────────────────────────────────────────────────────────────────────
-- 마이그레이션은 **날짜 원장**이다 — "그날 라이브에 무엇을 넣었나"의 기록이라,
-- 이미 적용된 파일을 제자리에서 고치면 그 기록 자체가 사라진다. 이 레포는 실제로
-- 그렇게 해 왔다(2026-08-16a 의 파라미터 타입 결함도 그 파일을 고치지 않고
-- `2026-08-16b_price_band_param_cast.sql` 로 덮었다).
-- ⇒ 28a 의 `current_date` 와 그 설명 주석은 **역사로 그대로 둔다.** 지금 있어야 할
--   모습은 이 파일과 `supabase/schema.sql` 이 말한다.
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 이 식인가 (타입까지)
-- ─────────────────────────────────────────────────────────────────────
--     now()                          → timestamptz (절대 시각)
--     … at time zone 'Asia/Seoul'    → timestamp   (서울 벽시계)
--     … ::date                       → date        (서울 달력 날짜)
-- `close_date` 가 date 라 그대로 견줄 수 있고, 식이 STABLE 이라 인덱스
-- `idx_lh_notice_close on lh_notice (close_date)` 도 그대로 탄다.
--
-- ⚠️ **레포에 선례가 없는 용법이다.** `at time zone 'Asia/Seoul'` 자체는 이미 쓰지만
--    (schema.sql 의 실거래 24개월 창), 그쪽은 `to_char(… , 'YYYYMM')` 로 **문자열 창**을
--    만드는 다른 일이다. `::date` 로 캐스트해 date 컬럼과 비교하는 것은 여기가 처음이라,
--    되돌아가지 않도록 `tests/test_lh_notice_migration.py` 가 못 박는다.
--
-- ⓘ 같은 UTC 판정이 적재기 요약에도 있었다(`scripts/collectors/collect_lh_notices.py`).
--   함수만 고치면 아침에 적재기와 화면이 서로 다른 수를 말하므로 함께 고쳤다.

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
       --    아침 9시까지 남는다(위 머리말). 마감일을 **모르는** 것(NULL)은 여전히 뺀다.
       and (n.close_date is null or n.close_date >= (now() at time zone 'Asia/Seoul')::date)
     order by n.close_date asc nulls last, n.notice_date desc nulls last, n.pan_id;
end;
$$;

comment on function list_lh_notices(text) is
  '이 지역에서 지금 살아 있는 LH 상가 공고(마감 지난 것은 뺀다 — 창고에는 남아 있다). '
  '''전국'' 공고는 어느 지역을 골라도 함께 나온다. 시군구 코드를 넘겨도 앞 2자리로 본다. '
  '⛔ 마감 판정은 **한국 날짜**다(2026-09-01a) — DB 세션이 UTC 라 current_date 를 쓰면 '
  '한국 새벽 0~9시에 어제 끝난 공고가 남는다.';

-- ⛔ create or replace 는 권한을 보존하지만, 형제 마이그레이션과 같은 모양으로 한 번 더
--    닫아 둔다(만든 자리에서 닫기 — 2026-08-28a·08-31a·08-31b 와 같은 처방).
revoke all on function list_lh_notices(text) from public, anon, authenticated;

commit;

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';
