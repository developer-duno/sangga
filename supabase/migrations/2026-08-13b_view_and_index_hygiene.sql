-- =====================================================================
-- 뷰·인덱스·불변식 위생 3건 (2026-08-13, 적대검증 확정분)
-- =====================================================================
-- 셋 다 "지금 당장 고장나 있지는 않지만, 조건이 하나 바뀌면 조용히 새거나 낭비되는" 것들이다.

-- ── 1) v_unit_current 가 개인 성명을 그대로 내보내고 있었다 ──────────────────
-- building.bld_nm 에는 '… 단독주택 (김남연)' 처럼 **개인 성명**이 든 값이 있다
-- (2026-08-08 실측 5,361개 중 93개). 그래서 화면에 나가는 이름은 전부
-- building_display_nm() 을 거치기로 정했는데, 이 뷰만 원본을 그대로 실어 보내고 있었다.
--
-- 지금 당장 새고 있지는 않다 — 이 뷰는 anon 에게 grant 되어 있지 않다(v_floor_stack 과
-- v_coverage_stats 둘만 열려 있다). 하지만 "노출되지 않아서 안전한 것"은 안전한 게
-- 아니라 **아직 안 걸린 것**이다. 나중에 이 뷰를 열면 그 순간 새기 시작한다.
create or replace view v_unit_current as
select
  u.unit_id,
  u.bld_id,
  u.pnu,
  u.floor_no,
  u.ho,
  u.excl_area_m2,
  -- ⚠️ 원본 b.bld_nm 이 아니다. 동명칭 폴백 + 개인 성명 가림을 거친 값이다
  --    (v_floor_stack 과 같은 규칙 — "보이는 것 = 검색되는 것" 을 뷰마다 어긋나게 두지 않는다).
  building_display_nm(b.bld_nm, b.dong_nm) as bld_nm,
  b.approve_date,
  p.road_addr,
  p.road_contact,
  ub.biz_name,
  ub.cat_s_nm,
  ub.snapshot_ym,
  (ub.biz_no is null) as is_vacant,
  u.lat,
  u.lng
from unit u
join building b on b.bld_id = u.bld_id
join parcel   p on p.pnu    = u.pnu
left join lateral (
  select x.biz_no, x.biz_name, x.cat_s_nm, x.snapshot_ym
  from unit_business x
  where x.unit_id = u.unit_id
  order by x.snapshot_ym desc
  limit 1
) ub on true;

comment on view v_unit_current is
  '최신 스냅샷 기준. is_vacant는 D등급(간접 추론) 지표이므로 화면에서 구분 표시할 것. '
  '⚠️ bld_nm은 원본이 아니라 building_display_nm() 결과다(동명칭 폴백 + 개인 성명 가림, 2026-08-13). '
  '⛔ §8.6 층별 스택 뷰에는 쓰지 말 것 — unit_business.unit_id가 라이브 전 행 NULL(상권정보에 호정보가 '
  '없다)이라 이 뷰는 호실 63,717행 100%를 공실로 판정한다(2026-08-07 실측). 스택 뷰는 v_floor_stack을 쓴다. '
  'ℹ️ 린트 0010(security definer view) 의도적 예외 — 원본 표는 RLS로 닫혀 있고 이 뷰가 대신 읽는다';

-- ── 2) idx_tx_pnu 는 대부분이 빈 값인 컬럼을 통째로 색인하고 있었다 ──────────
-- 실측(2026-08-13): transaction 22,662행 중 pnu 가 있는 것은 1,757행 = **7.8%**.
-- 나머지 92.2% 는 NULL 인데도 인덱스에 자리를 차지한다. 조회는 항상
-- `where pnu = ...` 형태(= NULL 은 절대 안 찾는다)라 **NULL 을 뺀 부분 인덱스로
-- 충분**하고, 같은 파일의 idx_unit_floor 가 이미 그 방식을 쓰고 있다(관례 일치).
-- 효과는 속도가 아니라 크기·유지비다 — 실거래가 전국으로 늘수록 격차가 커진다.
-- ⚠️ 컬럼 구성은 그대로 둔다. 원래 (pnu, contract_ym) **복합** 인덱스이고, 뒤 컬럼을
--    빼면 "이 필지의 몇 년 몇 월 거래" 조회가 인덱스를 덜 타게 된다. 여기서 바꾸는 것은
--    **조건 하나(NULL 제외)뿐**이다.
drop index if exists idx_tx_pnu;
create index if not exists idx_tx_pnu
  on transaction (pnu, contract_ym) where pnu is not null;

comment on index idx_tx_pnu is
  '실거래 → 필지 조인용. NULL 을 뺀 부분 인덱스다 — pnu 가 채워진 행은 7.8%뿐이고(2026-08-13 실측: '
  '22,662행 중 1,757행) 조회는 항상 값이 있는 pnu 를 찾으므로 나머지를 색인할 이유가 없다';

-- ── 3) unit_business 의 "절대 UPDATE/DELETE 금지"가 말로만 있었다 ───────────
-- 분기 스냅샷은 포털에서 내려가면 **재수집이 불가능**하다(CLAUDE.md 절대 규칙 6).
-- 그래서 이 표는 append-only 로 쓰기로 했고 적재기도 그렇게 동작한다
-- (load_sangkwon_snapshot.py 는 ignore-duplicates 만 쓴다 — 2026-08-13 grep 확인:
--  UPDATE·DELETE 를 하는 코드가 한 줄도 없다).
-- 그런데 그 약속이 **주석에만** 있었다. 주석은 실수로 돌린 SQL 한 줄을 못 막는다.
--
-- ⚠️ 정당한 정비가 필요하면(예: 잘못 적재된 분기를 걷어내기) 잠깐 끄고 하면 된다:
--      alter table unit_business disable trigger unit_business_append_only;
--      ... 정비 ...
--      alter table unit_business enable trigger unit_business_append_only;
--    끄는 것 자체가 "지금 되돌릴 수 없는 일을 한다"는 신호가 되도록 일부러 한 단계 둔다.
-- ⚠️ 문(statement) 단위 트리거다. 한 가지 함정을 알고 있어야 한다 — PostgreSQL 은
--    `insert ... on conflict do update` 에서 **문 단위 UPDATE 트리거를 (한 행도 안 바뀌어도)
--    발동**시킨다. 지금 적재기는 unit_business 에 `ignore-duplicates`(= do nothing) 만 쓰므로
--    안 걸리지만(2026-08-13 확인: load_sangkwon_snapshot.py 141행 `"unit_business":
--    "ignore-duplicates"`), 누군가 `merge-duplicates` 로 바꾸면 적재가 통째로 막힌다.
--    그건 사고가 아니라 **의도한 경보**다 — append-only 를 깨는 변경이기 때문이다.
create or replace function unit_business_append_only()
returns trigger
language plpgsql
as $$
begin
  raise exception
    'unit_business 는 append-only 입니다 (시도: %). 분기 스냅샷은 포털에서 내려가면 '
    '재수집이 불가능합니다(절대 규칙 6). 정말 필요하면 트리거를 잠깐 끄고 하세요: '
    'alter table unit_business disable trigger unit_business_append_only;', tg_op
    using errcode = 'restrict_violation';
end
$$;

drop trigger if exists unit_business_append_only on unit_business;
create trigger unit_business_append_only
  before update or delete on unit_business
  for each statement
  execute function unit_business_append_only();

comment on function unit_business_append_only() is
  'unit_business 의 append-only 불변식을 DB 에서 강제한다. 주석으로만 있던 약속을 '
  '실제 방어로 바꾼 것(2026-08-13). 적재기는 ignore-duplicates 만 쓰므로 영향이 없다';
