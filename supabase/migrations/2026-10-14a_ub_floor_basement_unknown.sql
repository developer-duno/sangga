-- =====================================================================
-- 2026-10-14a — 점포 표에 '지하인데 층 모름' 칸 하나 (물결 2-2c PR① · 결정 0036)
-- =====================================================================
-- 왜
-- --
-- 소상공인 상권정보 원본 층정보에는 숫자 없이 지하 표시만 적힌 값이 있다 — 2026-10-13 원본 전수 실측으로
-- 그 꼴은 '지' 한 글자뿐이다(202606 서울 8,750 · 대전 27 · 그 밖 6,511 / 202603 서울 7,743 · 대전 18 ·
-- 그 밖 5,597). 층 정규화(scripts/normalize_floor.py)는 몇 층인지 모르니 floor_no 를 NULL 로 둔다(절대 규칙 4
-- — 층 번호를 지어내지 않는다). 그래서 업종별 층 줄은 이 가게들을 '층 미상'에 셌다.
-- 👤 2026-10-13 「지하 칸에 넣기」: 층 번호는 지금처럼 비워 두고 '지하인데 층 모름' 표시 칸 하나만 더한다.
--
-- 무엇을 바꾸나
-- -------------
--   ① unit_business 끝에 floor_basement_unknown boolean(NULL 허용 · 기본값 없음 — 메타데이터만 바뀐다).
--      👤 D1(2026-10-13): **이 칸이 생긴 뒤 적재한 분기만** true/false 이고, 그 전 분기(202603·202606 …)는
--      NULL 로 둔다 — append only 를 지키고 거슬러 채우지 않는다. 새 적재기(load_sangkwon_snapshot.py)는
--      늘 true/false 를 넣는다(정본 판정 함수 normalize_floor.is_basement_without_number).
--   ② 제약 chk_ub_basement_unknown — 칸이 true 이면 floor_no 는 NULL 이어야 한다(층을 아는 가게에
--      '층 모름' 표시가 붙으면 업종 층 줄이 한 가게를 두 번 센다). NOT VALID 로 붙이고 commit **뒤**에
--      VALIDATE 한다 — 붙이는 순간의 잠금(ACCESS EXCLUSIVE) 안에서 1.5GB 를 훑지 않게.
--   ③ api.unit_business 를 다시 만든다 — 적재기는 REST 로 쓰는데 profile 헤더를 안 보내 PostgREST 의
--      첫 스키마(api)를 탄다. `select *` 뷰는 만든 날의 칸으로 굳어 있어, 안 고치면 적재기 upsert 가
--      새 칸을 못 찾는다(PGRST204 — 2026-10-08a·2026-10-11c 와 같은 일).
--
-- 바꾸지 않는 것
-- --------------
--   · 화면·요약표·함수 — 이 칸을 읽는 곳은 PR②(마이그레이션 C·B · 디스크 확장 뒤)다. 이 파일이 먼저
--     올라가도 화면은 그대로다(옛 함수는 새 칸을 모른다).
--   · 공개 호출 허용 목록(post_load.py --check) — 새 함수·새 공개 객체가 없다. api.unit_business 는
--     service_role 전용 그대로다(아래에서 회수 뒤 다시 준다).
--   · 옛 분기 행 — 한 행도 안 고친다(append-only 트리거 unit_business_append_only 도 그대로).
--
-- 잠금 (PostgreSQL 17 문서 sql-altertable — 2026-10-13 확인)
-- -----------------------------------------------------------
--   · `add column` — ACCESS EXCLUSIVE("An ACCESS EXCLUSIVE lock is acquired unless explicitly noted" —
--     ADD COLUMN 은 따로 적힌 예외가 아니다). "If no DEFAULT is specified, NULL is used. In neither case is
--     a rewrite of the table required." — 기본값이 없어 표를 다시 쓰지 않는다(디스크 0).
--   · `add constraint … check … not valid` — ACCESS EXCLUSIVE("most forms of ADD table_constraint require an
--     ACCESS EXCLUSIVE lock" — 예외는 ADD FOREIGN KEY 뿐). NOT VALID 라 "this potentially-lengthy scan is
--     skipped" — 붙이는 데 훑기가 없다.
--   · `create or replace view api.unit_business` — 그 뷰에 ACCESS EXCLUSIVE(2026-10-11c 와 같은 판단).
--   · 위 셋은 한 덩어리(begin … commit)라 잠금이 **commit 까지** 이어진다 — 그동안 점포 표를 읽는 화면
--     (층별 화면 점포·업종 카드·상호명 검색)은 오류가 아니라 잠깐 기다림이다. 덩어리에 훑기가 없어 곧 끝난다.
--   · `validate constraint` — "This command acquires a SHARE UPDATE EXCLUSIVE lock." 읽기·쓰기를 막지 않는다
--     (같은 잠금을 쓰는 VACUUM·ANALYZE·다른 DDL 과만 부딪친다 — 그래서 post_load 와 동시에 돌리지 않는다).
--     표 전체(약 1.5GB)를 훑으므로 몇 분 걸릴 수 있다 → 맨 앞 `set statement_timeout = '900s'`
--     (dbx.py 연결 기본 제한은 2분이다 — 2026-09-27 실측).
--   · `lock_timeout = '2s'` 는 **begin 앞**(세션 설정)에 둔다 — 오래 도는 조회가 점포 표를 쥐고 있어 2초 넘게
--     못 잡으면 덩어리가 통째로 되돌아가 아무것도 안 바뀐다. 다시 돌리면 된다.
--
-- 디스크
-- ------
-- 0 — 칸 추가는 메타데이터만, NOT VALID 제약·VALIDATE 는 읽기만, 뷰는 정의만 바뀐다. 색인도 안 만든다
-- (색인 include 에 칸을 더하는 것은 PR② 의 마이그레이션 C — 그쪽이 디스크 +약 300MB).
--
-- ⛔ 언제 돌리나
-- --------------
--   · 배치 창 01:30~12:00 **밖**에(👤 · 사람 적은 시간).
--   · 적재(load_sangkwon_snapshot.py)·post_load.py 와 **동시에 돌리지 않는다** — 적재 도중에 칸이 생기면
--     한 분기 안에 NULL 행과 true/false 행이 섞인다(적재기 끝의 null 확인이 잡지만 append-only 라 못 고친다).
--     post_load 의 vacuum 과는 VALIDATE 가 같은 잠금이라 서로 기다린다.
--   · ⛔ 이 파일을 적용한 **뒤에만** 새 분기를 새 적재기로 넣는다. 옛 적재기(칸 없는 판)로 넣으면 그 분기는
--     NULL 로 굳는다(👤 D1 — 거슬러 채우지 않는다).
--
-- 실행
-- ----
--   python scripts/dbx.py -f supabase/migrations/2026-10-14a_ub_floor_basement_unknown.sql
--   ⓘ 덩어리(begin … commit) 안에서 실패하면 통째로 되돌아간다 → 원인을 없애고 이 파일을 그대로 다시 돌린다.
--   ⓘ commit 뒤 VALIDATE 에서 실패하면(시간 초과 등) 칸·제약·뷰는 이미 들어가 있다 — 이 파일을 다시 돌리면
--     add constraint 가 "이미 있다"로 덩어리째 되돌아가므로(아무것도 안 바뀐다) **VALIDATE 줄만** 다시 돌린다:
--       python scripts/dbx.py -c "set statement_timeout = '900s'; alter table unit_business validate constraint chk_ub_basement_unknown;"
--
-- 적용 뒤 확인
-- ------------
--   select table_schema, data_type, is_nullable, column_default from information_schema.columns
--    where table_name = 'unit_business' and column_name = 'floor_basement_unknown' order by 1;
--     -- api | boolean | YES | (null)  ·  public | boolean | YES | (null)
--   select convalidated from pg_constraint where conname = 'chk_ub_basement_unknown';      -- t
--   select count(*) from unit_business where floor_basement_unknown is not null;            -- 0 (옛 분기는 NULL)
--   python scripts/collectors/load_sangkwon_snapshot.py --sigungu-code all --dry-run --dir data/raw/sangkwon_202606
--     -- 적재 전 관문: 서울(11) 8,750 · 대전(30) 27 … 전부 [일치] · exit 0 (쓰기 0)
--   python scripts/post_load.py --check                                                      -- exit 0
--
-- 되돌리기
-- --------
-- **새 마이그레이션 파일**로: set lock_timeout → begin → `alter table unit_business drop constraint if exists
-- chk_ub_basement_unknown;` → (칸은 남겨도 해가 없다 — 꼭 지우려면 api.unit_business 를 먼저 drop 하고
-- `alter table unit_business drop column floor_basement_unknown;` 뒤 api 뷰·권한을 정본대로 다시) → commit → notify.
-- 정본 schema.sql 은 PR revert 로 함께 되돌린다. 적용된 이 파일은 고치지 않는다(원장).

set lock_timeout = '2s';
set statement_timeout = '900s';

-- ⛔ 여기부터 commit 까지가 **한 덩어리**다(위 머리말 참조).
begin;

-- ① 칸 — 표 맨 뒤에. 기본값 없는 NULL 칸이라 표를 다시 쓰지 않는다.
alter table unit_business
  add column if not exists floor_basement_unknown boolean;

comment on column unit_business.floor_basement_unknown is
  '지하인데 층 모름 — 원본 층정보가 숫자 없이 지하 표시만(실측 "지") · floor_no 는 NULL 그대로(층 번호를 지어내지 않는다). '
  '이 칸이 생긴 뒤 적재한 분기만 true/false, 그 전 분기는 null(append only — 거슬러 채우지 않는다 · 👤 2026-10-13 D1). '
  '판정 = scripts/normalize_floor.py is_basement_without_number(2026-10-14a)';

-- ② 제약 — 붙일 때는 훑지 않는다(NOT VALID). 훑기는 commit 뒤 VALIDATE 가 한다.
alter table unit_business
  add constraint chk_ub_basement_unknown
  check (floor_basement_unknown is not true or floor_no is null) not valid;

-- ③ 표에 더한 칸을 적재기의 문(api.unit_business)에도 싣는다 — `select *` 는 만든 날의 칸으로 굳는다.
create or replace view api.unit_business    as select * from public.unit_business;
revoke all on api.unit_business    from public, anon, authenticated;
grant select, insert, update, delete on api.unit_business    to service_role;

commit;

-- ④ 있는 행 확인 — SHARE UPDATE EXCLUSIVE(읽기·쓰기 안 막음). 지금 있는 행은 전부 칸이 NULL 이라 걸릴 행이 없다.
alter table unit_business validate constraint chk_ub_basement_unknown;

-- ⛔ 커밋 **뒤**여야 한다 — 표·뷰의 칸이 바뀌었으니 PostgREST 가 스키마 캐시를 다시 읽어야 적재기 upsert 가
--    새 칸을 찾는다(PGRST204). 롤백된 판에서 헛알림이 가지 않게.
notify pgrst, 'reload schema';
