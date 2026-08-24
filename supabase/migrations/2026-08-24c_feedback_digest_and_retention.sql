-- =====================================================================
-- 의견함 — 주간 건수 알림 · 보관 정책 · 하루 상한 (2026-08-24c)
-- =====================================================================
-- 우편함(2026-08-24b)을 만들어 놓고 **읽을 계기가 없었다.** 지금은 dbx.py 로만 읽을 수
-- 있고, 그걸 정기적으로 열어 볼 장치가 없다. "나중에 읽겠다"에 조건이 없으면 영영 안
-- 읽는다 — 이 레포는 이미 그 일을 겪었다(감시가 죽은 걸 나흘 뒤에 알았고, 그래서 감시
-- 셋이 서로를 보게 만들었다). 읽히지 않는 의견함은 값어치가 0인데 보안·CI 부담만 진다.
--
-- 셋을 한꺼번에 넣는다. 따로 넣으면 안 되는 이유가 각각 있다:
--   ① 주간 건수 알림 — 읽을 계기. 이것이 없으면 나머지 둘의 근거(숫자)도 안 생긴다.
--   ② 보관 정책(90일) — 오래된 자유 글을 언제까지 쥐고 있을지. 본문에 사람이 스스로
--      연락처를 적어 넣을 수 있으므로(요구한 수집은 아니지만 막을 수 없다) 기한이 필요하다.
--   ③ 하루 상한 — ①이 없으면 적정선을 못 정하고, ②가 없으면 한 번 막힌 뒤 영영 안 풀린다.
--
-- ⛔ **이번에도 밖으로 새 문을 열지 않는다.** 정확히 무엇이 늘었는지:
--   · 새로 열린 것 = `api.get_feedback_stats()` **하나**뿐이고, 그것은 **숫자만** 준다
--     (건수·총량·가장 오래된 글의 나이). body(본문)·context(곁다리)는 어떤 경로로도 안 나간다.
--   · 지우는 함수는 **밖에 안 연다.** api 통과 함수를 아예 안 만들었다 —
--     편지가 들어올 때 `submit_feedback` 이 소유자 권한으로 스스로 치운다.
--   · 표 `app_feedback` 은 여전히 통째로 닫혀 있다(2026-08-24b 그대로).
--
-- ⚠️ 치우는 일을 `pg_cron` 에 맡기지 않았다. 확장은 켤 수 있지만(라이브 실측 확인),
--    정본(schema.sql)에 넣으면 **서버 설정이 미리 안 된 환경에서 통째 재생이 깨진다** —
--    도커 재생은 이 레포가 적대검증에 쓰는 도구라 망가뜨리면 손해가 더 크다.
--    대신 "아무도 안 보내면 안 치워진다"는 빈틈은 **주간 보고가 가장 오래된 글의 나이를
--    함께 알려주는 것**으로 메운다(기한을 넘겼으면 이슈가 열린다).

-- ── 보관 정책 ────────────────────────────────────────────────────────────────
create or replace function purge_old_feedback()
returns bigint
language plpgsql
volatile
security definer
set search_path = public
as $$
declare
  v_deleted bigint;
begin
  -- ⚠️ 90일은 인자가 아니라 **본문에 박힌 상수**다. 인자로 열어 두면 "유연성"이라는
  --    이름으로 언젠가 최근 글까지 지울 수 있는 문이 된다. 기한을 바꾸려면 이 파일을
  --    고쳐 새 마이그레이션을 내야 한다 — 그 마찰이 방어선이다.
  delete from app_feedback where created_at < now() - interval '90 days';
  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$$;

comment on function purge_old_feedback() is
  '90일보다 오래된 의견·오류 기록을 지운다(멱등 — 이미 지워졌으면 0). 인자가 없어 그 '
  '기한을 밖에서 바꿀 방법이 없다. ⛔ api 통과 함수를 만들지 않는다 — 밖에서 부를 수 '
  '없어야 한다. 부르는 곳은 submit_feedback 안(편지가 올 때)과 dbx.py(사람) 둘뿐.';

revoke all on function purge_old_feedback() from public, anon, authenticated;

-- ── 넣기 함수 교체 — 하루 상한 + 들어온 김에 치우기 ──────────────────────────
-- ⚠️ 2026-08-24b 판을 통째로 대체한다. 바뀐 곳은 두 군데(하루 상한 검사 · 끝의 치우기)뿐이고
--    나머지는 그대로다. 일부만 고칠 수 없어서(함수는 통째로 교체된다) 전문을 다시 적는다.
create or replace function submit_feedback(
  p_kind    text,
  p_body    text,
  p_context jsonb default null
)
returns boolean
language plpgsql
volatile
security definer
set search_path = public
as $$
declare
  v_kind text := lower(btrim(coalesce(p_kind, '')));
  v_body text := btrim(coalesce(p_body, ''));
  v_ctx  jsonb := p_context;
begin
  -- 예외를 던지지 않고 거짓을 돌려준다 — 오류 기록 경로에서 예외가 나면
  -- **오류를 알리다 오류가 나는** 꼴이 된다.
  if v_kind not in ('opinion', 'error') then
    return false;
  end if;
  if v_body = '' then
    return false;
  end if;

  -- 거절이 아니라 자르기 — 긴 의견을 통째로 버리는 것이 더 나쁘다.
  v_body := left(v_body, 2000);

  -- 곁다리가 너무 크면 곁다리만 버린다. 본문은 살린다.
  if v_ctx is not null and char_length(v_ctx::text) > 4000 then
    v_ctx := null;
  end if;

  -- ⛔ 인터넷에 열린 구멍은 언젠가 봇이 찾는다. "아직 아무도 모른다"는 방어가 아니다.
  --    IP 를 모르므로(PostgREST 뒤라 client_addr 이 프록시다) 전역 상한으로 막는다.
  --
  -- ⛔ **세기와 넣기 사이를 잠그지 않으면 상한이 안 걸린다.** 동시에 들어온 요청들은
  --    각자 자기 시점의 count 를 보므로 서로가 넣는 중이라는 것을 모른 채 전부 통과한다
  --    (READ COMMITTED 기본 격리). 그러면 천천히 보내는 사람만 막히고 **한꺼번에 쏟아붓는
  --    봇은 그대로 지나간다** — 막으려던 상대를 정확히 못 막는다(2026-08-24 적대검증).
  perform pg_advisory_xact_lock(hashtext('app_feedback_rate_limit'));

  -- 분당 상한(2026-08-24b) — 순간적으로 쏟아붓는 것을 막는다.
  if (select count(*) from app_feedback where created_at > now() - interval '1 minute') >= 60 then
    return false;
  end if;

  -- 하루 상한(2026-08-24c) — 분당 상한만으로는 하루 86,400통까지 열려 있다.
  -- 본문 2,000자 + 곁다리 4,000자면 하루 500MB 까지 자랄 수 있는 문이라, 창고 등급을
  -- 생각하면 그대로 둘 수 없다.
  --
  -- ⛔ **"표 전체 총량"으로 막지 않는다.** 총량 상한은 한 번 차면 90일이 지날 때까지
  --    정상 사용자를 **영구히** 막는다 — 봇 한 번에 서비스가 통째로 벙어리가 된다.
  --    하루 창은 하루면 저절로 풀리므로 그 함정이 없다.
  -- ⚠️ 1,000 은 **안전망이지 사업 기준이 아니다.** 지금 실사용은 하루 0~몇 통이라
  --    수백 배 여유다. 주간 알림이 실제 건수를 보여주기 시작하면 그 숫자로 조인다.
  -- ⚠️ 종류별로 따로 센다 — 합쳐서 재면 오류가 쏟아지는 날(정작 알림이 가장 필요한 날)
  --    사람의 의견이 밀려난다.
  if (select count(*) from app_feedback
      where kind = v_kind and created_at > now() - interval '1 day') >= 1000 then
    return false;
  end if;

  insert into app_feedback (kind, body, context) values (v_kind, v_body, v_ctx);

  -- 들어온 김에 오래된 것을 치운다(보관 정책). 예약 장치를 새로 들이지 않고 이미 있는
  -- 길에 얹는다 — 밖에 새 문을 안 여는 가장 싼 방법이다.
  --
  -- ⚠️ 치우다 실패해도 **편지 넣기를 막지 않는다.** 이 함수는 오류 보고 경로이기도 해서
  --    "오류를 알리다 오류가 나면 안 된다"는 원칙이 이미 서 있다. 치우기는 곁다리 살림이고,
  --    그 살림이 실제로 도는지는 get_feedback_stats().oldest_days 가 따로 감시한다
  --    (조용히 삼켜도 눈이 있는 자리다).
  begin
    perform purge_old_feedback();
  exception when others then
    null;
  end;

  return true;
end;
$$;

comment on function submit_feedback(text, text, jsonb) is
  '화면에서 온 짧은 글 한 통을 app_feedback 에 넣는다. 넣었으면 true, 모양이 아니거나 '
  '상한(분당 60 · 종류별 하루 1,000)에 걸리면 false — 예외를 던지지 않는다. 넣은 뒤 '
  '90일 지난 글을 함께 치운다(2026-08-24c). security definer: 표가 anon 에게 통째로 '
  '닫혀 있어 소유자 권한으로 대신 넣는다.';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function submit_feedback(text, text, jsonb) from public, anon, authenticated;

-- ── 주간 알림이 읽는 숫자 ────────────────────────────────────────────────────
create or replace function get_feedback_stats(p_days integer default 7)
returns table(
  opinion_cnt  bigint,   -- 최근 p_days 일 동안 온 사람의 의견
  error_cnt    bigint,   -- 최근 p_days 일 동안 화면이 자동으로 남긴 오류
  total_cnt    bigint,   -- 표에 남아 있는 전부 (보관 정책 덕에 최대 90일치)
  oldest_days  integer   -- 가장 오래된 글의 나이(일). 비어 있으면 NULL
)
language sql
stable
security definer
set search_path = public
as $$
  select
    count(*) filter (
      where kind = 'opinion'
        and created_at > now() - (least(greatest(coalesce(p_days, 7), 1), 90) || ' days')::interval
    ),
    count(*) filter (
      where kind = 'error'
        and created_at > now() - (least(greatest(coalesce(p_days, 7), 1), 90) || ' days')::interval
    ),
    count(*),
    -- ⭐ 이 한 칸이 "치우기가 실제로 도는지"를 지켜본다. 편지가 안 들어오는 동안에는
    --    치우기도 안 돌기 때문에(치우기를 넣기 경로에 얹었다), 이 값이 90을 넘으면
    --    보관 정책이 밀린 것이고 주간 알림이 그 사실로 이슈를 연다.
    (extract(epoch from (now() - min(created_at))) / 86400)::integer
  from app_feedback;
$$;

comment on function get_feedback_stats(integer) is
  '의견함 숫자만 돌려준다 — 최근 p_days(기본 7·1~90 사이로 자름)일 의견/오류 건수, 표 '
  '전체 건수, 가장 오래된 글의 나이(일). ⛔ body·context 는 어떤 칸으로도 안 나간다. '
  '주간 알림 워크플로 전용(2026-08-24c).';

revoke all on function get_feedback_stats(integer) from public, anon, authenticated;

-- api 통과 함수 — 화면이 아니라 GitHub Actions 주간 워크플로가 공개키(anon)로 부른다.
-- ⓘ 공개키는 비밀값이 아니다 — 이미 배포된 화면의 자바스크립트 묶음에 그대로 실려 있어
--   누구나 라이브에서 읽을 수 있다. 워크플로에 둬도 노출면이 늘지 않는다(비밀값 0 유지).
create or replace function api.get_feedback_stats(p_days integer default 7)
returns table(
  opinion_cnt bigint,
  error_cnt   bigint,
  total_cnt   bigint,
  oldest_days integer
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.get_feedback_stats(p_days) $$;

revoke all on function api.get_feedback_stats(integer) from public, anon, authenticated;
grant execute on function api.get_feedback_stats(integer) to anon, authenticated;

-- ⛔ api.purge_old_feedback 은 **일부러 안 만든다.** 지우는 일이 밖에서 불릴 수 있으면,
--    지금은 무해해도 "유연성"을 이유로 인자가 붙는 날 데이터 파괴 창구가 된다.

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';

-- =====================================================================
-- 완료
-- =====================================================================
