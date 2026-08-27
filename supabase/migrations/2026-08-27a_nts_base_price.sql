-- =====================================================================
-- 국세청 기준시가 — 상업용건물·오피스텔 호실 단위 (2026-08-27a)
-- =====================================================================
-- 무엇이 들어오나
-- ---------------
-- 국세청이 해마다 1월 1일자로 고시하는 **㎡당 기준시가**를 호실 하나에 한 줄씩 담는다
-- (2026년 판 실측 2,490,451행 · 전국 17개 시도). 원본은 공공데이터포털 3036455,
-- `data/raw/nts_base_price/상업용건물_오피스텔_기준시가_20260101.zip` 안의 xlsx 다.
--
-- ⛔ **세금을 매길 때 쓰는 과세표준이지, 시장에서 사고파는 값이 아니다.** 화면에 낼 때는
--    "국세청 고시 기준시가"라는 이름 그대로 쓰고, 다른 말로 바꿔 부르지 않는다
--    (절대 규칙 2 — 금지 표현 목록은 tests/test_load_price_gate.py 가 지킨다).
--
-- ⭐ 왜 귀한가: 이 자료는 **층·호실 단위로 값이 매겨진 유일한 전국 공공자료**다. 실거래는
--    거래가 있어야 생기지만(전국 필지의 3.0%만 보유), 기준시가는 대상 건물의 **모든 호실**에
--    빠짐없이 있다. 그래서 "이 건물 3층은 1층의 몇 할인가" 같은 층별 상대값을 실거래가 없는
--    곳에서도 말할 수 있다.
--
-- 원본 열 15개 (실측 — 문서에 적힌 14개가 아니다)
-- ------------------------------------------------
--   상가건물번호 · 상가종류코드 · 고시일자 · 법정동코드 · 특수지코드 · 번지 · 호 ·
--   상가건물블록주소 · 상가건물동주소 · 건물층구분코드 · 상가건물층주소 · 상가건물호주소 ·
--   고시가격 · 전용면적 · **공유면적**
--
-- ⚠️ **공유면적을 같이 담는다.** 처음 설계에는 없었는데(열이 14개인 줄 알았다) 실제 파일에
--    있었다. 안 담으면 나중에 누군가 `고시가격 × 전용면적`으로 총액을 계산하고 **공용부만큼
--    조용히 적게** 나온다 — 원본에 있는 칸을 버려서 생긴 오차라 어디서도 안 잡힌다.
--
-- 단위 검증 (추측 없이 실측으로 확정)
-- ------------------------------------
-- `고시가격`이 ㎡당인지 총액인지 원본 어디에도 안 적혀 있다. 전 행 분포로 갈랐다:
--   · 고시가격      중앙값 1,890,000원 (최소 5,000 · 최대 54,600,000)
--   · 가격 × 전용면적 중앙값 7,926만원 (p99 8.47억)
-- 총액이라면 상가 한 칸이 189만원이라는 뜻이 되어 말이 안 된다. **㎡당 단가**로 확정.
--
-- 층 표기 (절대 규칙 4)
-- ---------------------
-- `건물층구분코드` 실측 distinct 3종: 지상층 2,373,818 · 지하층 116,619 · **옥탑층 14**.
-- 지상 n → n / 지하 n → -n / **옥탑 → 99**(층 번호와 무관하게). 0 은 CHECK 로 막는다 —
-- 지하와 결측이 섞이면 집계가 조용히 오염된다.
-- ⚠️ 옥탑층이 14행뿐이라 "지상·지하 둘뿐"이라고 넘겨짚기 딱 좋은 자리였다. 적재기는 모르는
--    구분값을 만나면 NULL 로 흘려보내지 않고 **통째로 멈춘다**.
--
-- PNU 조립 · 광주전남 재코딩
-- ---------------------------
-- PNU 19 = 법정동코드(10) + 대지구분(1) + 본번(4) + 부번(4).
--   · 특수지코드 '일반지번' → 1 · '산' → 2
--   · **'가,확정예정지번'(11,008행) → 조립 불가**. pnu 를 NULL 로 두고 행은 **버리지 않는다**
--     (아직 지번이 확정 안 된 신축분이라 나중에 붙을 수 있다).
--   · 원본은 **옛 법정동코드**를 쓴다 — 광주 29(48,978행)·전남 46(19,043행). 우리 DB 는
--     통합 코드 12 를 쓰므로(전남광주통합특별시) 시군구 5자리를 바꿔 준다. 안 바꾸면 이
--     68,021행이 **에러 하나 없이** 어느 필지에도 안 붙는다.
--
-- 왜 표에 열어 두는 문이 없나
-- ----------------------------
-- 화면은 `list_base_prices()` 하나로만 읽는다. 표 자체는 anon 에게 통째로 닫아 둔다 —
-- 상호명·호실 목록이 통째로 나가는 길을 만들지 않는다(다른 표와 같은 방식).
-- REST(api 스키마) pass-through 뷰도 **일부러 안 만든다**: 적재기는 psql(dbx.py)로만
-- 다루므로 REST 경로가 필요 없고, 안 만드는 것이 곧 노출면을 줄이는 일이다.

create table if not exists nts_base_price (
  id              bigserial primary key,
  -- 조립 실패('가,확정예정지번')를 **버리지 않고** 담기 위해 NULL 을 허용한다.
  pnu             char(19),
  -- 원본이 적어 준 법정동코드 그대로(광주 29·전남 46 포함). pnu 는 재코딩된 값이라
  -- 원본을 잃으면 "우리가 바꾼 것"과 "원래 그랬던 것"을 다시 못 가린다.
  bjd_code_orig   char(10)  not null,
  -- '일반지번' / '산' / '가,확정예정지번'. 코드로 줄이지 않고 원문을 남긴다 —
  -- 새 구분값이 생기면 그 사실이 자료에 그대로 보여야 한다.
  special_cd      text      not null,
  bld_nm          text,                 -- 상가건물블록주소 (= 건물 이름)
  dong_nm         text,                 -- 상가건물동주소   (예: '1(단일)')
  floor_no        smallint,             -- 지상 n / 지하 -n / 옥탑 99 / 불명 NULL
  ho              text,                 -- 상가건물호주소 (22행은 비어 있다 → NULL)
  area_m2         numeric(12,2),        -- 전용면적
  common_area_m2  numeric(12,2),        -- 공유면적 (총액을 재려면 전용+공유가 필요하다)
  price_per_m2    numeric(14,2),        -- 고시가격 = ㎡당 (위 단위 검증 참조)
  kind            text      not null,   -- 상가종류코드: '상가' / '오피스텔'
  notice_date     date      not null,   -- 고시일자 (2026년 판은 전 행 2026-01-01)
  created_at      timestamptz default now(),
  constraint chk_nts_floor check (floor_no is null or floor_no <> 0)
);

comment on table nts_base_price is
  '국세청 상업용건물·오피스텔 기준시가(호실 단위, 연 1회 고시). 고시가격은 **㎡당 단가**다 '
  '(전 행 분포로 확정 — 중앙값 189만원/㎡). ⛔ 과세표준이지 시세가 아니다. '
  '⛔ anon 에게 통째로 닫혀 있고 list_base_prices() 로만 읽는다. 원본 zip = '
  'data/raw/nts_base_price/ (포털 3036455).';
comment on column nts_base_price.pnu is
  '필지고유번호 19자리. 특수지코드가 ''가,확정예정지번''이면 조립 불가라 NULL(행은 보존).';
comment on column nts_base_price.bjd_code_orig is
  '원본 법정동코드. 광주 29·전남 46 은 우리 DB 통합코드 12 로 재코딩해 pnu 를 만들지만 '
  '이 칸은 원본 그대로 둔다.';
comment on column nts_base_price.floor_no is
  '지상n=n / 지하n=-n / 옥탑=99 / 불명=NULL. ⛔ 0 은 CHECK 로 막는다 — 지하와 결측이 '
  '섞이면 층별 집계가 조용히 오염된다(절대 규칙 4).';
comment on column nts_base_price.price_per_m2 is
  '고시가격(원/㎡). 총액을 재려면 (전용면적 + 공유면적)을 곱해야 한다 — 전용면적만 '
  '곱하면 공용부만큼 적게 나온다.';

-- 화면이 보는 길은 "이 필지의 층별"뿐이다. 필지 하나당 수십~수백 행이라 pnu 만으로 충분하다.
create index if not exists idx_nts_pnu on nts_base_price (pnu);

-- 같은 고시연도를 다시 넣을 때(재적재) 지우는 자리. 249만 행을 전수 훑지 않게 한다.
create index if not exists idx_nts_notice on nts_base_price (notice_date);

-- RLS 를 켜되 정책은 하나도 만들지 않는다 = 전부 거부(다른 표와 같은 방식).
alter table nts_base_price enable row level security;

-- ⛔ RLS 만 믿지 않는다 — security definer 경로는 RLS 를 우회하므로 권한이 방어선이다.
--    ⚠️ 정본 위쪽의 `revoke all on all tables in schema public` 은 그 줄을 지날 때의 표만
--       닫는 일회성 명령이라 여기서 만든 표에는 안 걸린다. 만든 자리에서 다시 닫는다.
revoke all on nts_base_price from public, anon, authenticated;
-- bigserial 이 함께 만드는 시퀀스도 닫는다(표만 닫으면 "닫았다"가 반쪽이 된다).
revoke all on sequence nts_base_price_id_seq from public, anon, authenticated;

-- =====================================================================
-- list_base_prices — 이 필지의 층별 기준시가
-- =====================================================================
-- 층 하나에 한 줄. 값이 없으면 **줄이 아예 없다**(0 을 만들어 내지 않는다).
--
-- ⛔ **'상가' 종류만 센다.** 같은 건물에 오피스텔(1,331,606행)과 상가(1,158,845행)가 섞여
--    있는데, 오피스텔은 주거 가격이라 함께 중앙값을 내면 상가 값이 통째로 끌려간다.
--    실측 예: 신부파스칼텔 1층 상가 290만원/㎡ ↔ 2층 오피스텔 184만원/㎡.
--
-- ⛔ **여러 해가 쌓여도 한 해만 본다.** 이 표는 해마다 새 고시분이 들어오므로, 필터 없이
--    묶으면 2026년과 2027년 값의 중앙값이라는 뜻 없는 숫자가 나온다. 그 필지에 있는
--    **가장 최근 고시일자**만 골라 그 안에서 센다.
--
-- ⚠️ 파라미터를 p_ 로 시작하는 이유: `pnu` 는 컬럼 이름과 겹친다. 겹치면 PostgreSQL 이
--    컬럼을 우선 집어 `where n.pnu = n.pnu`(= 전 국토)가 된다(list_price_bands 와 같은 함정).
create or replace function list_base_prices(p_pnu text)
returns table (
  floor_no             smallint,
  median_price_per_m2  numeric,
  ho_cnt               int,
  notice_date          date
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  -- ⛔ **파라미터를 그대로 쓰지 말 것.** 서명은 text 인데 pnu 컬럼은 char(19) 다.
  --    `char컬럼 = text파라미터` 는 컬럼 쪽이 text 로 캐스트돼 **인덱스가 통째로 무력해진다**
  --    (2026-08-16b 라이브 실측: 459.8ms ↔ 0.796ms). 서명은 text 로 두고(PostgREST 가 보내는
  --    값이 text 다) 안에서 char(19) 로 받아 쓴다.
  v_pnu  char(19) := p_pnu;
  v_date date;
begin
  select max(n.notice_date) into v_date
    from nts_base_price n
   where n.pnu = v_pnu and n.kind = '상가';

  -- 이 필지에 상가 기준시가가 없다 = 줄 0개. 빈 목록과 "0원"은 다른 말이다.
  if v_date is null then
    return;
  end if;

  return query
    select n.floor_no,
           -- percentile_cont 는 numeric 을 double precision 으로 받아 계산한다. 고시가격은
           -- 원 단위 정수이므로 소수점을 남길 이유가 없어 되돌릴 때 반올림한다.
           round(percentile_cont(0.5) within group (order by n.price_per_m2)::numeric, 0),
           count(*)::int,
           v_date
      from nts_base_price n
     where n.pnu = v_pnu
       and n.kind = '상가'
       and n.notice_date = v_date
       and n.price_per_m2 is not null
     group by n.floor_no
     -- 위층이 먼저 — 층별 스택 화면과 같은 순서(높은 층이 위).
     order by n.floor_no desc nulls last;
end;
$$;

comment on function list_base_prices(text) is
  '이 필지의 층별 국세청 기준시가 — 층, ㎡당 고시가격 중앙값, 호실 수, 고시일자. '
  '⛔ 종류가 ''상가''인 호실만 센다(오피스텔은 주거 가격이라 섞으면 상가 값이 끌려간다). '
  '⛔ 그 필지의 가장 최근 고시일자 한 해만 본다. 값이 없으면 줄이 없다(0 을 만들지 않는다).';

-- ⚠️ create or replace 는 권한을 유지하지만, 대시보드가 같은 함수를 다시 만들면
--    Supabase 기본 권한이 anon 을 자동으로 붙인다. 만든 자리에서 다시 닫는다.
revoke all on function list_base_prices(text) from public, anon, authenticated;

-- 화면이 실제로 부르는 것. public 은 REST 노출에서 빠져 있어(2026-08-24 옛 문 닫기)
-- api 쪽에 통과 함수가 없으면 화면에서 못 부른다.
create or replace function api.list_base_prices(p_pnu text)
returns table (
  floor_no             smallint,
  median_price_per_m2  numeric,
  ho_cnt               int,
  notice_date          date
)
language sql
stable
security definer
set search_path = ''
as $$ select * from public.list_base_prices(p_pnu) $$;

revoke all on function api.list_base_prices(text) from public, anon, authenticated;
grant execute on function api.list_base_prices(text) to anon, authenticated;

-- ⛔ public.list_base_prices 는 끝까지 닫아 둔다 — 통과 함수가 security definer 라
--    소유자 권한으로 부르므로 anon 에게 열 필요가 없다.

-- 안 알리면 새 스키마 캐시가 다음 재시작까지 안 잡혀 404 가 난다.
notify pgrst, 'reload schema';
