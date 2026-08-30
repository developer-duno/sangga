import type { RentStat } from '../types';

/**
 * "상권 임대 동향" 카드의 **순수 계산**만 모은다(결정 0024).
 *
 * 컴포넌트에서 빼 둔 이유는 `industryMix.ts`·`lhNotices.ts` 와 같다 — 여기 있는 규칙들은
 * 화면을 띄우지 않고도 시험할 수 있어야 하고, 실제로 틀리기 쉬운 곳이 전부 여기다
 * (단위 환산 · 종류 고르기 · 분기 표기 · 서버 응답 모양).
 *
 * ⛔ **계산을 지어내지 않는다.** 여기서 하는 산수는 딱 하나, 공표 단위(천원/㎡)를 원으로
 *    바꾸는 곱하기뿐이다. 종류끼리 더하기·평균, 분기 수익률 × 4(연 환산), 층별효용비율을
 *    곱해 층으로 펴는 것 — 전부 여기 넣지 말 것. 그건 역산이고, 역산은 백테스트와
 *    재결재를 거친 뒤의 일이다(매매가 결정 0013 으로 그렇게 했다).
 */

/**
 * 건물 종류를 보여줄 차례. **맨 앞이 기본값**이다.
 *
 * 집합상가가 먼저인 이유 — 이 서비스가 다루는 상가의 대부분이 구분소유(집합)이고
 * (확정 설계 1의 거래단위 축), 층·호실로 쪼개 보는 이 화면의 단위와도 같다.
 *
 * ⚠️ 이 목록에 없는 종류가 와도 **버리지 않는다**(뒤에 이름순으로 붙는다). 부동산원이
 *    종류를 늘리는 날 화면이 조용히 그것만 빠뜨리면 아무도 모른다.
 */
export const BLD_TYPE_ORDER = ['집합상가', '중대형상가', '소규모상가', '오피스'] as const;

/** 화면에 그리는 조사값 한 칸(라벨 + 이미 사람 말로 바뀐 값). */
export type RentMetric = {
  /** 화면 key + 시험용 식별자. */
  key: 'vacancy' | 'rent' | 'yield';
  label: string;
  value: string;
};

/** 화면에 그리는 줄 하나 = 상권 하나 × 조사구역 하나. */
export type RentRow = {
  key: string;
  /** 우리 상권 이름. 없으면 빈칸 대신 이렇게 적는다 — 빈 제목은 상권이 아닌 무언가로 읽힌다. */
  districtNm: string;
  /** 부동산원 조사구역 이름(전체 경로). 우리 이름과 다른 이름이라 함께 적는다. */
  regionNm: string;
  /** '2026년 2분기'. 못 읽으면 null 이고, 그때 화면은 분기 도장을 안 찍는다. */
  quarter: string | null;
  /** 값이 있는 것만 담는다. 하나도 없으면 그 줄은 아예 안 온다(`toRentRows` 가 거른다). */
  metrics: RentMetric[];
};

/**
 * 분기 표기 '2026Q2' → '2026년 2분기'. 읽을 수 없으면 **null**.
 *
 * ⚠️ `format.ts` 형제들과 달리 '—'나 원본을 되돌려 주지 않는다(`formatMonthKo` 와 같은 결) —
 *    이 값은 "언제 조사한 것인가"를 말하는 자리에만 쓰이고, 그 자리에 '2026Q2'가 박히면
 *    "(2026Q2 조사)"처럼 원본 코드가 그대로 새어 나간다.
 */
export function quarterLabel(quarter: string | null | undefined): string | null {
  if (!quarter) return null;
  const m = /^(\d{4})Q([1-4])$/.exec(quarter.trim());
  return m ? `${m[1]}년 ${m[2]}분기` : null;
}

/**
 * ㎡당 임대료 표기. 공표 단위가 **천원/㎡** 라 원으로 바꿔 적는다('27,063원').
 *
 * ⛔ **기간(월·연)과 층 기준을 붙이지 않는다.** 부동산원 공표 자료가 이 값 옆에 그 둘을
 *    적어 주지 않아(공공데이터포털 메타에도 없다) 확인되지 않은 한정어를 우리가 지어내지
 *    않는다. 대신 화면이 "부동산원이 공표한 ㎡당 값"이라고만 말한다.
 * ⓘ 원 단위로 바꾸는 것은 화면 몫이다 — 서버는 공표값 그대로 준다(그래야 "서버 값 =
 *   공표값" 대조가 남는다).
 */
export function formatRentPerM2(thousandWon: number | null | undefined): string | null {
  if (thousandWon === null || thousandWon === undefined || !Number.isFinite(thousandWon)) {
    return null;
  }
  return `${Math.round(thousandWon * 1000).toLocaleString('ko-KR')}원`;
}

/**
 * 비율 표기 '10.08%'. 값이 아니면 null.
 *
 * 소수 둘째 자리까지 두는 이유 — 분기 투자수익률은 1% 안팎이라 첫째 자리로 뭉개면
 * 0.82%와 0.84%가 같은 값이 된다(같은 자를 공실률에도 쓴다).
 */
export function formatRate(rate: number | null | undefined): string | null {
  if (rate === null || rate === undefined || !Number.isFinite(rate)) return null;
  return `${rate.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}%`;
}

/**
 * 나온 건물 종류 목록. **보여줄 차례대로** 준다(`BLD_TYPE_ORDER` → 나머지는 이름순).
 *
 * ⛔ 종류를 합치지 않는다 — 모집단이 다른 네 조사라 섞으면 아무것도 아닌 숫자가 된다.
 *    그래서 화면은 한 번에 하나만 보여주고, 이 목록이 그 고르개를 채운다.
 */
export function typeOptions(rows: readonly RentStat[]): string[] {
  const seen = new Set<string>();
  for (const r of rows) if (typeof r?.bld_type === 'string' && r.bld_type) seen.add(r.bld_type);

  const known = BLD_TYPE_ORDER.filter((t) => seen.has(t));
  const rest = [...seen]
    .filter((t) => !(BLD_TYPE_ORDER as readonly string[]).includes(t))
    .sort((a, b) => a.localeCompare(b, 'ko-KR'));
  return [...known, ...rest];
}

/**
 * 처음에 보여줄 종류. 없으면 null(그때는 고르개도 값도 안 그린다).
 *
 * ⚠️ '집합상가'를 화면에 글자로 박지 않는다 — 그 종류가 없는 상권이 실제로 있고, 박아
 *    두면 그런 자리에서 **아무 줄도 없는 카드**가 된다. 있는 것 중 첫째를 고른다.
 */
export function defaultBldType(rows: readonly RentStat[]): string | null {
  return typeOptions(rows)[0] ?? null;
}

/**
 * 고른 종류의 줄들을 화면이 그릴 모양으로.
 *
 * ⛔ **값이 하나도 없는 줄은 버린다.** 부동산원은 지표별로 따로 공표해서 어떤 분기에는
 *    한 지표만 오기도 하는데(적재기의 부분 병합), 셋 다 비어 있는 줄을 그리면 상권 이름만
 *    적힌 빈 줄이 남아 "여기는 값이 0"처럼 읽힌다.
 * ⛔ 없는 지표에 '—'를 적지도 않는다 — 칸을 만들어 두면 조사 안 한 것을 조사했는데
 *    비어 있는 것처럼 보인다(층별 스택의 도로접면과 같은 규칙).
 */
export function toRentRows(rows: readonly RentStat[], bldType: string): RentRow[] {
  const out: RentRow[] = [];
  rows.forEach((r, i) => {
    if (r.bld_type !== bldType) return;

    const metrics: RentMetric[] = [];
    const vacancy = formatRate(r.vacancy_rate);
    if (vacancy !== null) metrics.push({ key: 'vacancy', label: '공실률', value: vacancy });
    const rent = formatRentPerM2(r.rent_per_m2);
    if (rent !== null) metrics.push({ key: 'rent', label: '㎡당 임대료', value: rent });
    const yieldRate = formatRate(r.yield_rate);
    if (yieldRate !== null) {
      // '분기'를 라벨에 박아 둔다 — 이 값만 떼어 보면 연 수익률로 읽히고, 상가 수익률을
      // 연 4~5%로 아는 사람에게 0.8%는 "형편없는 자리"라는 정반대의 뜻이 된다.
      metrics.push({ key: 'yield', label: '투자수익률(분기)', value: yieldRate });
    }
    if (metrics.length === 0) return;

    out.push({
      key: `rent-${i}-${r.rone_region_nm}`,
      districtNm: r.district_nm || '(이름 없는 상권)',
      regionNm: r.rone_region_nm,
      quarter: quarterLabel(r.quarter),
      metrics,
    });
  });
  return out;
}

/**
 * 접혀 있어도 보이는 한 줄.
 *
 * ⛔ **여기에 값을 적지 않는다.** 접힌 요약은 한정어("이 건물이 아니라 상권", "어느 종류")를
 *    함께 담을 자리가 없는데, 숫자만 요약에 나오면 사람은 그것을 이 건물 값으로 읽는다.
 *    그래서 "무엇이 들어 있는지"와 "언제 것인지"만 말한다.
 * ⓘ 줄이 하나도 없으면 그 사실을 그대로 적는다 — 이 카드에서 가장 흔한 정상 상태다.
 */
export function rentSummary(rows: readonly RentStat[]): string {
  if (rows.length === 0) return '부동산원 조사 대상 상권이 아닙니다';

  const labels = '공실률 · ㎡당 임대료 · 투자수익률';
  const quarters = new Set<string>();
  for (const r of rows) {
    const q = quarterLabel(r.quarter);
    if (q !== null) quarters.add(q);
  }
  // 분기가 여럿인 것은 결함이 아니다 — (조사구역, 종류)마다 최신 분기를 따로 고르기
  // 때문이다. 그때 하나만 골라 적으면 나머지 줄에 대해 거짓말이 되므로 개수만 말하고,
  // 어느 줄이 언제 것인지는 줄마다 적는다.
  if (quarters.size === 1) return `${labels} · ${[...quarters][0]} 조사`;
  if (quarters.size > 1) return `${labels} · 조사 분기 ${quarters.size}개`;
  return labels;
}

function isNullableNumber(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'number';
}

/**
 * 서버 응답의 **모양**을 본다.
 *
 * 타입 단언(`as RentStat[]`)은 컴파일 때만 사는 약속이라 런타임에는 아무것도 막아 주지
 * 않는다. 뜻밖의 답(마이그레이션 적용 전 라이브의 오류 객체, 다른 함수의 응답)이 그대로
 * 렌더로 흘러 들어가면 그 자리에서 터지고, 그러면 이 카드 하나 때문에 층별 화면 전체가
 * 그물(ErrorBoundary)에 걸려 오류 안내로 바뀐다 — 곁다리로 본체를 잃지 않는다.
 */
export function isRentStat(x: unknown): x is RentStat {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    (r.district_nm === null || r.district_nm === undefined || typeof r.district_nm === 'string') &&
    typeof r.rone_region_nm === 'string' &&
    typeof r.bld_type === 'string' &&
    typeof r.quarter === 'string' &&
    isNullableNumber(r.vacancy_rate) &&
    isNullableNumber(r.rent_per_m2) &&
    isNullableNumber(r.yield_rate)
  );
}

/** ⓘ 빈 배열은 **정상**이다 — "이 자리는 부동산원 조사 대상 상권이 아니다"라는 뜻이다. */
export function isRentStatList(x: unknown): x is RentStat[] {
  return Array.isArray(x) && x.every(isRentStat);
}
