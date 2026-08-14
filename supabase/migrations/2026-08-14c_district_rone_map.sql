-- =====================================================================
-- district ↔ R-ONE 임대통계 상권 매핑표 (2026-08-14)
-- =====================================================================
-- 무엇을 하나
-- -----------
-- "이 상권(district)의 임대료 참고값을 rent_stat 의 어느 줄에서 읽을 것인가"를
-- 사람이 한 번 정해 두는 표다. 상가 임대료 실거래는 존재하지 않으므로(절대 규칙 5)
-- 부동산원 임대동향(rent_stat)으로 역산하는 것이 유일한 경로인데, 두 자료는 상권을
-- 부르는 이름이 서로 달라 코드가 그때그때 이름을 맞춰 볼 수 없다.
--
-- 왜 코드가 아니라 **이름 경로**에 거나 (rone_region_nm)
-- ------------------------------------------------------
-- rent_stat 의 키는 (quarter, region_code, bld_type) 인데, **같은 상권 이름이
-- 통계 종류(bld_type 4종)마다 다른 region_code 를 갖는다**(대전은 이름 12개 vs
-- 코드 28개 — 2026-08-14 실측). region_code 하나를 골라 박으면 그 종류의 통계만
-- 읽히고 나머지 3종은 조용히 사라진다. 그래서 종류를 가로지르는 유일한 공통 축인
-- `region_nm` **전체 경로**("서울>강남>테헤란로", "대전>둔산")에 건다.
--
-- 왜 미매핑 상권에는 **행이 아예 없나**
-- -------------------------------------
-- "모른다"를 빈 문자열·NULL 로 적어 두면 조인이 조용히 성립해 엉뚱한 상권의 임대료가
-- 붙는다. 행이 없으면 조인이 안 되고, 화면은 상위 근사(권역: "서울>도심")나 "표본 없음"
-- 으로 자연히 내려간다. **없는 매핑을 지어내지 않는 것**이 이 표의 안전장치다.
-- (틀린 매핑 하나는 임대료 추정을 배 단위로 흔든다 — 없는 편이 낫다.)
--
-- ★ 왜 PK 가 (district_id, rone_region_nm) 복합인가 — 한 상권이 경로 **둘**일 수 있다
-- ----------------------------------------------------------------------------------
-- 부동산원이 **통계 종류(bld_type)마다 서울 권역을 다르게 나눈다.** 라이브 실측
-- (2026-08-14, rent_stat distinct):
--   · 오피스                      → 서울>여의도마포>{공덕역·당산역·여의도} · 서울>기타>홍대/합정
--   · 소규모·중대형·집합상가      → 서울>영등포신촌>{공덕역·당산역·여의도·홍대/합정}
-- 즉 같은 상권(공덕역·당산역·여의도·홍대/합정)이 종류에 따라 **경로가 둘**이다. 하나만
-- 고르면 나머지 종류의 통계가 통째로 사라지므로, 둘 다 담을 수 있게 PK 를 복합으로 둔다.
-- 조회가 (이름 경로, bld_type)으로 rent_stat 을 찾을 때 **존재하는 쪽이 자연히 골라진다** —
-- 그래서 이 표에 bld_type 칸을 두지 않는다(자료가 이미 아는 것을 두 번 적지 않는다).

create table if not exists district_rone_map (
  district_id     text not null references district(district_id),
  rone_region_nm  text not null,          -- rent_stat.region_nm 전체 경로 ("대전>둔산")
  match_method    text not null,          -- 'exact' | 'normalized' | 'token' | 'manual'
  note            text,
  created_at      timestamptz default now(),
  primary key (district_id, rone_region_nm)
);

comment on table district_rone_map is
  'district(상권 경계) → rent_stat(부동산원 임대동향) 상권 이름 잇기. '
  'R-ONE 상권 하나에 district 여럿이 붙고, district 하나도 경로를 **둘까지** 가질 수 있다 '
  '(PK 가 복합인 이유). 부동산원이 bld_type 마다 서울 권역 분할을 달리해 같은 상권이 '
  '오피스는 여의도마포·기타, 상가는 영등포신촌으로 갈리기 때문이다 — 라이브 실측 2026-08-14, '
  '이중 경로 잎 = 공덕역·당산역·여의도·홍대/합정. '
  '⚠️ 이 표에 **없는** district 는 "아직 이을 근거가 없다"는 뜻이며, 그 상태가 정상이다 — '
  '없는 매핑을 지어내면 임대료 추정이 통째로 틀어진다(내부용 표, 화면에 직접 안 나간다).';

comment on column district_rone_map.rone_region_nm is
  'rent_stat.region_nm 의 **전체 경로**를 그대로 적는다. region_code 가 아닌 이유: '
  '같은 상권이라도 bld_type(오피스/중대형상가/소규모상가/집합상가)마다 코드가 달라 '
  '코드로 박으면 나머지 종류의 통계가 조용히 안 읽힌다(2026-08-14 실측).';

comment on column district_rone_map.match_method is
  '어떻게 이었나 — exact(이름 그대로) / normalized(꼬리 시설어를 떼고 같음) / '
  'token(앞말 겹침, 기계 판단) / manual(사람이 지리 지식으로 정함). '
  '나중에 "이 매핑을 얼마나 믿을 수 있나"를 되물을 때의 유일한 근거다.';

comment on column district_rone_map.note is
  'manual 이면 **왜 그렇게 판단했는지**를 적는다(예: 동춘당이 송촌동 소재). '
  '근거 없는 manual 은 다음 사람이 검증할 수 없다.';

-- 역방향 조회용: "이 R-ONE 상권에 붙은 district 가 몇 개인가"(1:N 의 N 쪽).
create index if not exists idx_district_rone_map_region
  on district_rone_map (rone_region_nm);

-- ⛔ Supabase 는 public 스키마에 **새로 생기는 표를 anon 에 자동으로 연다**
--    (pg_default_acl). 2026-08-13 에 새 물질화뷰 2개가 실제로 그렇게 열려 있었다 —
--    2026-08-08 의 `revoke ... on all tables` 는 그때 있던 것만 닫는 일회성 명령이라
--    이후에 만든 것에는 효력이 없다. 그래서 만든 자리에서 바로 닫는다.
--    이 표는 내부용이다(화면은 rent_stat 를 직접 읽지 않고 함수를 거친다).
--    ⚠️ post_load.py 의 허용목록은 **건드리지 않는다** — 이 표가 열려 있으면
--       `python scripts/post_load.py --check` 가 [사고]로 잡는 것이 정상 동작이다.
revoke all on district_rone_map from public, anon, authenticated;

alter table district_rone_map enable row level security;
-- 정책은 일부러 하나도 만들지 않는다(RLS 켬 + 정책 0개 = 공개 롤에게 완전히 안 보인다).
-- 적재 스크립트는 service_role 로 접속하며 RLS 를 우회한다.
