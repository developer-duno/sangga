-- =====================================================================
-- 성적표 공개 — 통과 구 게이트를 화면이 읽는 길 (2026-09-05e)
-- =====================================================================
-- 로드맵 Wave 4 『성적표 공개 + 방법 공개』. 표는 하나도 안 만든다 —
-- 이미 있는 `price_gate_sigungu`(결정 0013 §2 의 정본)를 **처음으로 읽는 길**을 뚫는다.
--
-- 왜 필요한가
-- -----------
-- 결정 0013 §4 는 "통과 구 목록의 정본은 서버 한 곳"이라고 못박아 두었고, 그래서 지금까지
-- 이 표의 유일한 독자는 `list_price_bands` 하나였다(그 함수는 "이 구가 통과했나"만 보고
-- 밴드를 낼지 말지 정한다). 화면이 "어느 구가 왜 켜지고 꺼졌나"를 보여주려면 같은 표를
-- **목록으로** 읽어야 하는데, 그 길이 없어서 지금까지 화면·문서에 목록을 베끼는 것 말고는
-- 방법이 없었다 — 그게 바로 §4 가 금지한 사본 드리프트다.
--
-- ⛔ 나가는 것은 **구별 요약 한 줄씩**이다
-- ---------------------------------------
-- 표에 있는 그대로(구 코드·이름·짝지은 거래 수·사다리 MdAPE·구평균 MdAPE·통과 여부·
-- 적재 시각) 나간다. **검증 거래 하나하나(`docs/backtest/검증거래별원자료.csv` 에 있는
-- 그것)는 여기로 나가지 않는다** — 애초에 이 표에 없다. 그 원자료는 개별 실거래를
-- 필지·층·단가까지 담고 있어, 어떤 형태로든 밖으로 내보내려면 별건 판단이 필요하다.
--
-- ⛔ 손으로 고치는 표가 아니다
-- ----------------------------
-- 이 표를 채우는 것은 사람 손이 아니라 백테스트 산출물이다(결정 0013 §4):
--   python scripts/backtest_price.py      → docs/backtest/통과구.csv
--   python scripts/load_price_gate.py     → price_gate_sigungu
-- 그래서 이 함수는 **읽기만** 한다. 여기에 쓰기가 붙는 날 그 규칙이 우회된다.
--
-- ⚠️ 새 함수는 이제 닫힌 채로 태어난다 (2026-09-01b)
-- --------------------------------------------------
-- 전역 기본권한에서 PUBLIC EXECUTE 를 빼 뒀으므로, 화면이 부를 함수는 **명시로** 열어야
-- 한다. 아래 `grant execute on function api.list_price_gate() to anon, authenticated;`
-- 한 줄이 그것이다 — 빼면 화면에서 `permission denied for function` 이 난다.
--
-- 적용
-- ----
-- Supabase SQL Editor 에 통째로 붙여 실행한다(표 변경 0 · 되돌리려면 두 함수를 drop).
-- 실행 뒤 `python scripts/post_load.py --check` 로 공개 롤 권한이 그대로인지 본다.

create or replace function list_price_gate()
returns table (
  sigungu_code  text,
  sigungu_nm    text,
  n_paired      int,
  ladder_mdape  numeric,
  base_mdape    numeric,
  gate_pass     boolean,
  loaded_at     timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
  -- 표를 **그대로** 나른다. 여기서 거르거나 정렬 규칙을 새로 정하지 않는다 —
  -- 통과한 구만 주면 "왜 우리 구는 없나"에 답할 수 없고(탈락 사유가 이 화면의 본론이다),
  -- 화면이 다시 계산하면 판정이 두 곳에 생겨 언젠가 갈린다.
  -- ⓘ 30개 구뿐이라 상한(limit)을 두지 않는다. 이 표는 성적표를 다시 뽑아야 늘고,
  --   그때도 열린 지역 수만큼이다(형제 함수들의 limit 은 수만 행짜리 목록에 있는 것이다).
  select g.sigungu_code,
         g.sigungu_nm,
         g.n_paired,
         g.ladder_mdape,
         g.base_mdape,
         g.gate_pass,
         g.loaded_at
  from price_gate_sigungu g
  order by g.sigungu_code;
$$;

comment on function list_price_gate() is
  '2026-09-05e 참고 시세 게이트(결정 0013 §2)의 구별 판정과 그 근거 — 구 코드·이름, '
  '짝지은 검증 거래 수, 사다리 MdAPE, 구평균(BASE) MdAPE, 통과 여부, 적재 시각. '
  '⛔ 나가는 것은 구별 요약뿐이다 — 검증 거래 하나하나(필지·층·단가)는 이 표에 아예 없다. '
  '⛔ 통과 구 목록의 정본은 이 표 한 곳이다(결정 0013 §4) — 화면·문서가 목록을 베끼지 '
  '않게 하려고 이 읽기 길을 뚫었다. 표를 채우는 것은 사람 손이 아니라 backtest_price.py → '
  'load_price_gate.py 다. ⛔ 통과한 구만 거르지 않는다 — 탈락 사유(구평균을 못 이겼다 등)를 '
  '말하려면 떨어진 구도 함께 있어야 한다. '
  'security definer (price_gate_sigungu 가 anon 에게 통째로 닫혀 있어 소유자 권한으로 '
  '대신 읽는다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function list_price_gate() from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_price_gate()
returns table (
  sigungu_code  text,
  sigungu_nm    text,
  n_paired      int,
  ladder_mdape  numeric,
  base_mdape    numeric,
  gate_pass     boolean,
  loaded_at     timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_price_gate() $$;

revoke all on function api.list_price_gate() from public, anon, authenticated;
grant execute on function api.list_price_gate() to anon, authenticated;

-- ⛔ public.list_price_gate 는 끝까지 닫아 둔다 — 통과 함수가 security definer 라
--    소유자 권한으로 부르므로 anon 에게 열 필요가 없다.
-- ⛔ 표 price_gate_sigungu 자체는 열지 않는다(2026-08-16a 의 revoke + RLS 그대로).

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';
