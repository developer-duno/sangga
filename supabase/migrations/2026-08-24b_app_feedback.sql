-- =====================================================================
-- 마이그레이션 2026-08-24b — 보던 사람이 말을 걸 수 있는 우편함
-- =====================================================================
-- 실행법 ⚠️ **대시보드 SQL Editor 로 돌린다.** 표 하나 + 함수 둘이라 빠르고,
--   한 트랜잭션에 들어간다(중간에 실패하면 통째로 없던 일이 된다).
--   → 붙여넣고 Run → 아래 6) 검산 쿼리 → `python scripts/post_load.py --check`.
--
-- ─────────────────────────────────────────────────────────────────────
-- 왜 하나
-- ─────────────────────────────────────────────────────────────────────
-- 2026-08-24 첫 배포로 이 서비스는 남이 볼 수 있는 곳이 됐다. 그런데 화면에는
-- **되돌려 말할 자리가 한 곳도 없다** — 다 보고 나서 할 수 있는 일이 뒤로 가기뿐이다.
-- 동시에 화면이 오류로 죽어도 **우리가 그것을 알 방법이 0** 이다(서버가 없어 로그가
-- 남는 곳이 없고, 보는 사람은 하얀 화면만 본다).
--
-- 둘은 다른 문제로 보이지만 필요한 것이 같다 — "밖에서 안으로 짧은 글 한 통을 넣는 길".
-- 그래서 표 하나·함수 하나로 둘 다 받는다(`kind` 로 가른다). 길을 두 번 뚫지 않는다.
--
-- ─────────────────────────────────────────────────────────────────────
-- ⛔ 이것은 "쓰기 권한을 여는 일"이 아니다 — 그 구분이 이 파일의 핵심이다
-- ─────────────────────────────────────────────────────────────────────
-- 2026-08-24 같은 날 우리는 REST 노출에서 public 을 빼(옛 문 닫기) "공개 롤이 고칠 수
-- 있는 것 0" 을 만들었다. 그 직후에 쓰기를 연다면 성과를 스스로 깎는 셈인데, 여는 방식이
-- 다르다:
--   · 표(app_feedback) 는 anon 에게 **통째로 닫는다**(select·insert·update·delete 전부).
--     RLS 도 켜지만 정책은 하나도 만들지 않는다 = 기본 거부. 시퀀스까지 회수한다.
--   · 대신 **정해진 모양의 편지만 넣는 함수** 하나를 연다. 이 레포의 공개 기능이 전부
--     쓰는 바로 그 방식이다(search_buildings·list_price_bands …).
-- 우편함에 편지를 넣을 수 있다고 우편함 **안을 읽을 수 있는 것은 아니다.** 넣은 사람도
-- 자기가 넣은 편지를 다시 못 본다. 읽기는 서비스 권한(dbx.py)만 할 수 있다.
--
-- ⛔ 개인정보는 받지 않는다 — 이름·연락처·이메일 칸이 아예 없다
--    받는 순간 개인정보처리방침·보관기간·파기절차가 따라붙는다. 아직 아무도 모르는
--    서비스가 **오지도 않은 문의를 위해 법적 의무부터 짊어지는 것은 순서가 거꾸로다.**
--    답장이 필요할 만큼 쌓이면 그때 칸을 붙인다. 지금은 "무엇을 보다 무엇이 아쉬웠나"
--    만으로 충분하고, 그것이 이 표의 값어치 전부다.
--    ⚠️ 그래서 body 에 사람이 연락처를 적어 넣을 수는 있다 — 그건 우리가 **요구한** 수집이
--       아니지만, 읽는 사람이 그 사실을 알고 다뤄야 한다. 화면 안내문에 "연락처는 적지
--       마세요"를 둔다(src/components/FeedbackBox.tsx).
--
-- ─────────────────────────────────────────────────────────────────────
-- 1) 표 — 밖에서는 통째로 잠긴다
-- ─────────────────────────────────────────────────────────────────────
create table if not exists app_feedback (
  id          bigserial primary key,
  -- 'opinion' = 사람이 쓴 의견 / 'error' = 화면이 죽으며 자동으로 남긴 것.
  -- 한 표에 담되 섞이지 않게 가른다. 조회 목적이 달라 나중에 갈라내기도 쉽다.
  kind        text not null check (kind in ('opinion', 'error')),
  -- 본문. 상한은 함수가 자르지만, 함수를 우회하는 길(서비스 권한 직접 insert)이
  -- 생겨도 표가 스스로 지키게 제약을 둔다.
  -- ⛔ **여기 담긴 글을 나중에 화면에 뿌릴 때 그대로 HTML 로 넣지 말 것.** 지금은 읽는
  --    화면이 없어서(dbx.py 로만 본다) 위험이 0 이지만, 관리 화면을 만드는 PR 은 이 표를
  --    처음 보는 사람이 쓸 수 있다. 저장할 때는 아무것도 안 거른다 — 거르는 책임은
  --    **보여주는 쪽**에 있다(2026-08-24 적대검증이 남긴 예고).
  body        text not null check (char_length(body) between 1 and 2000),
  -- 무엇을 보던 중이었나(건물·구·화면). 오류면 브라우저 종류까지.
  -- ⚠️ 모양을 강제하지 않는다 — 화면이 담는 칸이 늘 때마다 마이그레이션을 하게 되면
  --    "그냥 안 담는" 선택을 하게 된다. 읽는 쪽에서 없는 칸을 견디게 쓴다.
  context     jsonb,
  created_at  timestamptz not null default now()
);

comment on table app_feedback is
  '화면에서 들어온 짧은 글 한 통. kind=opinion 은 사람이 쓴 의견, kind=error 는 '
  '화면이 죽으며 자동으로 남긴 것. ★ anon 에게 통째로 닫혀 있고 api.submit_feedback() '
  '함수로만 들어온다(넣기 전용 — 넣은 사람도 못 읽는다). 개인정보 칸 없음(2026-08-24b).';

-- 분당 상한을 재는 쿼리(아래 함수)가 매번 전수를 훑지 않게 한다. 표가 커질수록
-- 이 인덱스가 없으면 편지 한 통 넣는 값이 표 크기에 비례해 올라간다.
create index if not exists idx_app_feedback_created on app_feedback (created_at desc);

-- ─────────────────────────────────────────────────────────────────────
-- 2) 잠금 — 표는 밖에서 아무것도 못 한다
-- ─────────────────────────────────────────────────────────────────────
-- RLS 를 켜되 정책은 **하나도 만들지 않는다** = 전부 거부(이 레포의 다른 표와 같은 방식).
alter table app_feedback enable row level security;

-- ⛔ RLS 만 믿지 않는다. Supabase 는 새 객체마다 anon 에 권한을 자동으로 주고
--    (pg_default_acl), 뷰·security definer 경로는 RLS 를 우회한다 — **권한이 방어선**이다.
revoke all on app_feedback from public, anon, authenticated;
-- ⚠️ bigserial 은 시퀀스를 함께 만든다. 표만 회수하고 시퀀스를 두면 nextval 이 열린 채
--    남는다(직접적인 유출은 아니지만 "닫았다"는 말이 반쪽이 된다).
revoke all on sequence app_feedback_id_seq from public, anon, authenticated;

-- ─────────────────────────────────────────────────────────────────────
-- 3) 넣기 전용 함수 — 밖으로 열리는 유일한 구멍
-- ─────────────────────────────────────────────────────────────────────
-- 반환값이 boolean 인 이유: void 로 두면 화면이 성공·실패를 모른 채 "보냈습니다"를
-- 띄우게 된다. 못 받았으면 못 받았다고 말할 수 있어야 한다(거짓 안심 금지).
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
  -- 모양이 아니면 받지 않는다. 예외를 던지지 않고 거짓을 돌려준다 —
  -- 오류 기록 경로(kind=error)에서 예외가 나면 **오류를 알리다 오류가 나는** 꼴이 된다.
  if v_kind not in ('opinion', 'error') then
    return false;
  end if;
  if v_body = '' then
    return false;
  end if;

  -- 상한은 자른다(거절이 아니라 자르기 — 긴 의견을 통째로 버리는 것이 더 나쁘다).
  v_body := left(v_body, 2000);

  -- 딸림 정보가 지나치게 크면 버린다. 본문은 살린다 — 곁다리 때문에 본문을 잃지 않는다.
  if v_ctx is not null and char_length(v_ctx::text) > 4000 then
    v_ctx := null;
  end if;

  -- ⛔ 인터넷에 열린 구멍은 언젠가 봇이 찾는다. "아직 아무도 모른다"는 방어가 아니다.
  --    IP 를 모르므로(PostgREST 뒤라 client_addr 이 프록시다) 전역 분당 상한으로 막는다.
  --    사람이 1분에 60통을 쓸 일은 없고, 봇이 창고를 채우는 것은 이걸로 멈춘다.
  --    ⚠️ 전역이라 봇 하나가 그 순간 다른 사람의 의견도 막는다. IP 없이 할 수 있는
  --       최선이고, 둘 중에는 창고를 지키는 쪽이 낫다는 판단이다.
  --
  -- ⛔ **세기와 넣기 사이를 잠그지 않으면 이 상한은 안 걸린다.**
  --    동시에 들어온 요청들은 각자 자기 시점의 count 를 보므로, 서로가 넣는 중이라는 것을
  --    모른 채 전부 "아직 60 미만이네" 하고 통과한다(READ COMMITTED 기본 격리). 그러면
  --    천천히 보내는 사람만 막히고 **한꺼번에 쏟아붓는 봇은 그대로 지나간다** — 막으려던
  --    상대를 정확히 못 막는다(2026-08-24 적대검증이 잡은 구멍).
  --    ⇒ 거래 단위 잠금으로 **줄을 세운다.** 이 표의 통행량에서는 값이 싸다(편지 한 통당
  --      잠금 하나). 함수가 끝나면 자동으로 풀린다(xact = 트랜잭션 범위).
  perform pg_advisory_xact_lock(hashtext('app_feedback_rate_limit'));

  if (select count(*) from app_feedback where created_at > now() - interval '1 minute') >= 60 then
    return false;
  end if;

  insert into app_feedback (kind, body, context) values (v_kind, v_body, v_ctx);
  return true;
end;
$$;

comment on function submit_feedback(text, text, jsonb) is
  '화면에서 온 짧은 글 한 통을 app_feedback 에 넣는다. 넣었으면 true, 모양이 아니거나 '
  '분당 상한(60)에 걸리면 false — 예외를 던지지 않는다(오류를 알리다 오류가 나면 안 된다). '
  'security definer: 표가 anon 에게 통째로 닫혀 있어 소유자 권한으로 대신 넣는다.';

-- 새 함수의 EXECUTE 는 Postgres 가 PUBLIC 에 기본으로 준다 — 먼저 회수한다.
revoke all on function submit_feedback(text, text, jsonb) from public, anon, authenticated;

-- ─────────────────────────────────────────────────────────────────────
-- 4) api 스키마 통과 함수 — 화면이 실제로 부르는 것
-- ─────────────────────────────────────────────────────────────────────
-- 화면은 db.schema='api' 로 붙는다(2026-08-22e). public 은 REST 노출에서 빠져 있어
-- 여기에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.submit_feedback(
  p_kind    text,
  p_body    text,
  p_context jsonb default null
)
returns boolean
language sql
volatile
security definer
set search_path = ''
as $$ select public.submit_feedback(p_kind, p_body, p_context) $$;

revoke all on function api.submit_feedback(text, text, jsonb) from public, anon, authenticated;
grant execute on function api.submit_feedback(text, text, jsonb) to anon, authenticated;

-- ⛔ public.submit_feedback 은 **끝까지 닫아 둔다.** 통과 함수가 security definer 라
--    소유자 권한으로 부르므로 anon 에게 열 필요가 없다(다른 공개 함수와 같은 구조).

-- ⛔ **이 줄을 빠뜨리면 화면에서 404(PGRST202) 가 난다.** PostgREST 는 스키마를 캐시하므로
--    새 함수를 만들어도 알려 주기 전까지는 "그런 함수 없다"고 답한다. DB 에는 멀쩡히 있는데
--    화면만 안 되는, 원인을 찾기 어려운 종류의 고장이다(2026-08-24 적용 때 실제로 빠뜨려
--    손으로 따로 쳐야 했다 — 그래서 여기 적어 둔다).
notify pgrst, 'reload schema';

-- ─────────────────────────────────────────────────────────────────────
-- 5) 검산 — 붙여넣고 Run 한 뒤 이걸 돌린다
-- ─────────────────────────────────────────────────────────────────────
-- ① 표가 밖에서 잠겨 있나 (기대: 네 줄 전부 false)
--    select has_table_privilege('anon','app_feedback','select') as sel,
--           has_table_privilege('anon','app_feedback','insert') as ins,
--           has_table_privilege('anon','app_feedback','update') as upd,
--           has_table_privilege('anon','app_feedback','delete') as del;
--
-- ② 열린 것은 통과 함수 하나뿐인가 (기대: api 는 true, public 은 false)
--    select has_function_privilege('anon','api.submit_feedback(text,text,jsonb)','execute')    as api_open,
--           has_function_privilege('anon','public.submit_feedback(text,text,jsonb)','execute') as public_open;
--
-- ③ 실제로 들어가나 (기대: t, 그리고 표에 1행)
--    select public.submit_feedback('opinion', '검산용 편지', '{"probe":true}'::jsonb);
--    select id, kind, body, context, created_at from app_feedback order by id desc limit 1;
--
-- ④ 검산 흔적 지우기 (기대: DELETE 1)
--    delete from app_feedback where context ? 'probe';
--
-- ⑤ 모양이 아닌 것은 거절하나 (기대: 셋 다 f, 표에 아무것도 안 늘어남)
--    select public.submit_feedback('spam',    'x',  null) as bad_kind,
--           public.submit_feedback('opinion', '',   null) as empty_body,
--           public.submit_feedback('opinion', '   ', null) as blank_body;
