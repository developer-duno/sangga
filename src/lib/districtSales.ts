import type { DistrictSales, DistrictSalesIndustry, DistrictSalesQuarter, OpenCloseStatus } from '../types';
import { chipMatch, type FounderChip } from './founderChips';
import { formatLandPriceAmount } from './landPrice';
import { OPEN_CLOSE_STATUSES, openCloseQuarterLabel, sidoNameOfPnu, splitQuarter, windowText } from './openClose';

/**
 * 「업종별 추정매출 (서울시 추정)」 카드의 **순수 계산**만 모은다(결정 0045 PR③ · 컴포넌트에 계산 0).
 *
 * ⛔ **공표값 그대로다.** 금액(`amt`)·건수(`co`)는 서울시가 공표한 **분기(3개월) 합계**(원 · 건)다 — 화면이 나누지 않는다
 *    (점포당·한 달·하루로 바꾸지 않는다 · 👤 결정 ①). 여기서 하는 산수는 막대의 **높이·길이**(카드 안 최댓값에 대한 비례)뿐이다.
 * ⛔ **이 건물의 값이 아니다.** 이 건물이 속한 서울시 상권 전체의 값이다. 상권이 여럿이면 상권마다 따로 두고 더하지 않는다.
 * ⛔ **분기·연도 글자를 박지 않는다.** 어느 분기를 그릴지는 서버의 창(`window_quarters`)이 정한다(시험이 원문을 훑는다).
 * ⛔ 판단 낱말(많다·높다 같은 말)과 비율 글자를 쓰지 않는다 — 숫자만 나란히.
 */

// ── 빈 상태 넷 — 개업·폐업 카드와 같은 글(두 카드가 같은 함수 상태를 받는다) ────────────────

/** 건물 단위 상태 줄(no_coord · not_seoul · outside_seoul_district)의 접힌 요약 — `openCloseSummary` 와 같은 글. */
export function headSummary(status: OpenCloseStatus, pnu: string): string {
  if (status === 'not_seoul') {
    const sido = sidoNameOfPnu(pnu);
    return sido === null
      ? '서울 상권만 다루는 자료라 이 건물에는 없습니다'
      : `서울 상권만 다루는 자료라 이 건물(${sido})에는 없습니다`;
  }
  if (status === 'outside_seoul_district') return '이 건물이 속한 서울시 상권이 없습니다';
  return '위치 정보가 없어 속한 상권을 찾지 못했습니다';
}

/** 건물 단위 상태 줄의 펼친 본문 — 개업·폐업 카드와 같은 글. */
export function headBody(status: OpenCloseStatus, pnu: string): string {
  if (status === 'not_seoul') {
    const sido = sidoNameOfPnu(pnu);
    return sido === null
      ? '서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물에는 그 자료가 없습니다.'
      : `서울시 상권분석서비스는 서울 상권만 다룹니다 — 이 건물(${sido})에는 그 자료가 없습니다.`;
  }
  if (status === 'outside_seoul_district') return '이 건물이 속한 서울시 상권이 없어 자료가 없습니다.';
  return '이 건물의 위치 정보가 없어 속한 상권을 찾지 못했습니다.';
}

/** 상권 이름. 비어 있으면 빈칸 대신 이렇게 적는다(개업·폐업 카드와 같다). */
export function districtLabel(row: { district_nm: string | null } | undefined): string {
  return row?.district_nm || '(이름 없는 상권)';
}

/** 상권 덩어리 제목 — 이름 · 종류. */
export function districtTitle(row: { district_nm: string | null; district_type: string | null }): string {
  const name = districtLabel(row);
  return row.district_type ? `${name} · ${row.district_type}` : name;
}

/** 건수·명수 — 한국 꼴 쉼표 + 단위. 값이 없으면 '–'(0 이 아니다). */
export function formatCount(n: number | null | undefined, unit: string): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '–';
  return `${n.toLocaleString('ko-KR')}${unit}`;
}

/** 금액 — 개별공시지가 줄과 같은 서식(「7억 2,300만원」). 값이 없으면 '–'. */
export function formatAmount(won: number | null | undefined): string {
  if (won === null || won === undefined || !Number.isFinite(won)) return '–';
  return formatLandPriceAmount(won);
}

// ── 모양 검사 ───────────────────────────────────────────────────────────────

function isCount(x: unknown): x is number {
  return typeof x === 'number' && Number.isInteger(x) && x >= 0;
}

function isNullableString(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'string';
}

/** 서울시 분기 꼴(연도 넷 + 분기 하나 · Q 없음). */
export function isQuarterCode(x: unknown): x is string {
  return typeof x === 'string' && splitQuarter(x) !== null && x.trim() === x;
}

function isSalesQuarter(x: unknown): x is DistrictSalesQuarter {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return isQuarterCode(r.quarter) && isCount(r.amt) && isCount(r.co);
}

function isSalesIndustry(x: unknown): x is DistrictSalesIndustry {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return typeof r.cd === 'string' && typeof r.nm === 'string' && isCount(r.amt) && isCount(r.co);
}

function isSalesRow(x: unknown): x is DistrictSales {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  if (typeof r.status !== 'string' || !(OPEN_CLOSE_STATUSES as readonly string[]).includes(r.status)) return false;
  if (!Array.isArray(r.window_quarters) || !r.window_quarters.every((q) => typeof q === 'string')) return false;
  if (r.status === 'ok' || r.status === 'no_data') {
    // ⛔ 상권 줄인데 창이 비어 있으면 받지 않는다 — "최근 0분기" 같은 말을 지어내게 된다.
    if (r.window_quarters.length === 0) return false;
    if (typeof r.district_id !== 'string' || !isNullableString(r.district_nm) || !isNullableString(r.district_type)) {
      return false;
    }
  }
  if (r.status === 'ok') {
    return (
      isQuarterCode(r.latest_quarter) &&
      Array.isArray(r.trend) &&
      r.trend.every(isSalesQuarter) &&
      Array.isArray(r.top) &&
      r.top.length <= 5 &&
      r.top.every(isSalesIndustry) &&
      isCount(r.rest_cnt) &&
      isCount(r.rest_amt) &&
      isCount(r.rest_co) &&
      Array.isArray(r.industries) &&
      r.industries.every(isSalesIndustry)
    );
  }
  return true;
}

/**
 * 서버 응답(`list_district_sales`)의 **모양**을 본다. 하나라도 어긋나면 false → 카드가 통째로 빠진다(콘솔 경고만).
 * ⛔ 빈 배열도 false(서버는 어떤 필지에도 적어도 한 줄을 준다) · 섞인 답(정상 줄 + 이상한 줄 하나)도 통째로 거부한다.
 */
export function isDistrictSalesList(x: unknown): x is DistrictSales[] {
  return Array.isArray(x) && x.length > 0 && x.every(isSalesRow);
}

// ── 접힌 요약 ───────────────────────────────────────────────────────────────

/**
 * 접혀 있어도 보이는 한 줄 — `openCloseSummary` 규칙 그대로.
 * ⛔ **여기에 값을 적지 않는다**(한정어 「이 건물이 아니라 그 상권」을 담을 자리가 없다). 분기는 표 전체 최신(`window_quarters[0]`).
 */
export function salesSummary(rows: readonly DistrictSales[], pnu: string): string {
  const head = rows.find((r) => r.status !== 'ok' && r.status !== 'no_data');
  if (head) return headSummary(head.status, pnu);
  const districts = rows.filter((r) => r.status === 'ok' || r.status === 'no_data');
  const lead = districts[0];
  const others = districts.length - 1;
  const who = others > 0 ? `${districtLabel(lead)} 외 상권 ${others}곳` : districtLabel(lead);
  const wq = lead?.window_quarters ?? [];
  if (!districts.some((r) => r.status === 'ok')) {
    return `${who} · ${windowText(wq)} 안에 서울시 추정매출 자료가 없습니다`;
  }
  const label = openCloseQuarterLabel(wq[0]);
  return label ? `${who} · ${label}까지 서울시 추정` : who;
}

// ── 큰 숫자 줄 ──────────────────────────────────────────────────────────────

export type SalesBig = {
  /** 「○○○○년 2분기(3개월) 매출 7억 2,300만원」 */
  amount: string;
  /** 「결제 15,208건」 */
  count: string;
  /** 「14업종 합」 */
  industries: string;
};

/**
 * 큰 숫자 줄 — 그 상권 `latest_quarter` 분기의 trend 칸 값 그대로(재계산 0 · top·rest 를 더하지 않는다).
 * trend 에 그 분기가 없으면 금액·건수 자리에 '–'. ok 줄이 아니면 null.
 */
export function salesBigText(row: DistrictSales): SalesBig | null {
  if (row.status !== 'ok') return null;
  const label = openCloseQuarterLabel(row.latest_quarter);
  if (!label) return null;
  const t = row.trend?.find((q) => q.quarter === row.latest_quarter);
  return {
    amount: `${label}(3개월) 매출 ${t ? formatAmount(t.amt) : '–'}`,
    count: `결제 ${t ? formatCount(t.co, '건') : '–'}`,
    industries: `${(row.top?.length ?? 0) + (row.rest_cnt ?? 0)}업종 합`,
  };
}

/** 이 상권 자료가 창의 최신보다 옛 분기에서 멈췄으면 「이 상권 자료는 ○○○○년 ○분기까지입니다.」 아니면 null. */
export function salesLagText(row: DistrictSales): string | null {
  if (row.status !== 'ok') return null;
  const w = row.window_quarters[0];
  if (w === undefined || w === row.latest_quarter) return null;
  const label = openCloseQuarterLabel(row.latest_quarter);
  return label ? `이 상권 자료는 ${label}까지입니다.` : null;
}

// ── 흐름 막대 ───────────────────────────────────────────────────────────────

export type SalesTrendCell = {
  quarter: string;
  /** '○○○○년 ○분기'. 못 읽으면 빈 글자. */
  label: string;
  year: string;
  q: string;
  /** ok = 그 분기 값이 있다 · missing = 그 상권에 그 분기 자료가 **아예 없다**(0 막대가 아니라 '–'). */
  kind: 'ok' | 'missing';
  amt: number | null;
  co: number | null;
  /** 막대 높이(%) — 그 상권 눈금(`salesScaleMax`)에 대한 비례. missing 이면 0. */
  h: number;
  /** 창의 가장 최근 칸(오른쪽 끝) — 짙은 색. */
  last: boolean;
};

/**
 * 창(`window_quarters` 전부 · 최신 → 옛)으로 칸을 만든다 — **옛 분기가 왼쪽, 최신이 오른쪽**.
 * ⛔ 그 상권에 없는 분기는 '–'(missing)다 — 0 막대로 그리면 「매출 0」으로 읽힌다. ⓘ 0 은 값이다(높이 0 막대).
 */
export function salesTrendCells(row: DistrictSales, scaleMax: number): SalesTrendCell[] {
  const byQ = new Map((row.trend ?? []).map((t) => [t.quarter, t]));
  const ordered = [...row.window_quarters].reverse();
  return ordered.map((quarter, i): SalesTrendCell => {
    const s = splitQuarter(quarter);
    const hit = byQ.get(quarter);
    const base = {
      quarter,
      label: s ? `${s.year}년 ${s.q}분기` : '',
      year: s?.year ?? '',
      q: s?.q ?? '',
      last: i === ordered.length - 1,
    };
    if (!hit) return { ...base, kind: 'missing', amt: null, co: null, h: 0 };
    return { ...base, kind: 'ok', amt: hit.amt, co: hit.co, h: scaleMax > 0 ? (hit.amt / scaleMax) * 100 : 0 };
  });
}

/**
 * **상권 하나의 눈금** — 그 상권 창 안 금액 가운데 가장 큰 값(검사 뒤 보완 F1).
 * ⛔ 카드 하나에 눈금 하나로 두지 않는다 — 운영 실측에서 관광특구 3개월 매출(1,163억)이 골목상권 가운데값(19.9억)의 약
 *    58배라, 공통 눈금이면 좁은 상권 막대가 2% 높이로 사라진다. 그래서 상권 덩어리마다 제 눈금 글을 함께 적는다
 *    (상권끼리 막대 키를 견주지 않게 · 개업·폐업 카드는 비율이라 공통 눈금 그대로다).
 * 창 밖 분기는 세지 않는다. 그릴 막대가 없거나 전부 0 이면 0.
 */
export function salesScaleMax(row: DistrictSales): number {
  if (row.status !== 'ok' || !row.trend) return 0;
  const inWindow = new Set(row.window_quarters);
  let max = 0;
  for (const t of row.trend) if (inWindow.has(t.quarter) && t.amt > max) max = t.amt;
  return max;
}

/** 막대 눈금 한 줄 — 「막대가 꽉 차면 7억 6,000만원(3개월 합)」(목업 글자 그대로). */
export function salesScaleText(scaleMax: number): string {
  return `막대가 꽉 차면 ${formatAmount(scaleMax)}(3개월 합)`;
}

// ── 업종 표 ─────────────────────────────────────────────────────────────────

export type SalesTableRow = {
  cd: string;
  name: string;
  amount: string;
  count: string;
  /** 막대 길이(%) — 이 줄 금액 ÷ 상위 첫 줄 금액(그림의 길이에만 · 글자로 내지 않는다). */
  w: number;
  /** 창업자 칩의 짝 업종 줄인가. */
  hit: boolean;
};

export type SalesTable = {
  rows: SalesTableRow[];
  /** 「그 밖 N업종 (더해서)」 줄 — 0업종이면 null. */
  rest: { label: string; amount: string; count: string } | null;
  /** hit 줄 꼬리 「 · 고른 업종(카페)」 — 칩이 없으면 null. */
  hitTail: string | null;
  /** 상위 5 밖이지만 업종 전부에 있는 칩 업종 — **코드마다 한 줄**(더하지 않는다). */
  chipOutside: string[];
  /** 칩 업종 전부가 이 자료에 없을 때 한 줄. */
  chipNone: string | null;
  /** 칩 업종 일부만 없을 때 빠진 이름 한 줄. */
  chipPartial: string | null;
};

/**
 * 업종 표 — 상위 5(top 차례 그대로) + 「그 밖 N업종 (더해서)」 + 창업자 칩 줄들.
 * ⛔ 칩 코드가 여럿(미용 셋 · 학원 다섯)이어도 **더하지 않고** 코드마다 따로 적는다.
 */
export function salesTableRows(row: DistrictSales, chip: FounderChip): SalesTable {
  const top = row.top ?? [];
  const inds = row.industries ?? [];
  const first = top[0]?.amt ?? 0;
  const match = chipMatch(chip);
  const codes = match?.seoul ?? [];
  const rows = top.map(
    (t): SalesTableRow => ({
      cd: t.cd,
      name: t.nm || t.cd,
      amount: formatAmount(t.amt),
      count: formatCount(t.co, '건'),
      w: first > 0 ? (t.amt / first) * 100 : 0,
      hit: codes.includes(t.cd),
    }),
  );
  const restCnt = row.rest_cnt ?? 0;
  const rest =
    restCnt > 0
      ? { label: `그 밖 ${restCnt}업종 (더해서)`, amount: formatAmount(row.rest_amt), count: formatCount(row.rest_co, '건') }
      : null;
  if (match === null) return { rows, rest, hitTail: null, chipOutside: [], chipNone: null, chipPartial: null };

  const chipOutside: string[] = [];
  const missing: string[] = [];
  for (const cd of codes) {
    if (top.some((t) => t.cd === cd)) continue;
    const ind = inds.find((i) => i.cd === cd);
    if (ind) {
      chipOutside.push(
        `고른 업종(${chip}): ${ind.nm || match.seoulNm[cd] || cd} ${formatAmount(ind.amt)} · ${formatCount(ind.co, '건')} (3개월 합 · 상위 5 밖)`,
      );
    } else {
      missing.push(cd);
    }
  }
  // 「이 자료에 없다」는 업종 전부와 상위 5 를 **함께** 보고 정한다(검사 뒤 보완 F11 — 업종 전부 목록이 상위 5 줄을 빠뜨린
  // 이상한 답이 와도 표에 굵게 선 업종을 「없다」고 말하지 않게).
  const present = (cd: string) => inds.some((i) => i.cd === cd) || top.some((t) => t.cd === cd);
  const allMissing = codes.length > 0 && codes.every((cd) => !present(cd));
  const chipNone = allMissing ? `고른 업종(${chip})은 이 자료에 없습니다` : null;
  const chipPartial =
    !allMissing && missing.length > 0
      ? `고른 업종 가운데 ${missing.map((cd) => match.seoulNm[cd] ?? cd).join('·')}은 이 자료에 없습니다`
      : null;
  return { rows, rest, hitTail: ` · 고른 업종(${chip})`, chipOutside, chipNone, chipPartial };
}

// ── 글 ──────────────────────────────────────────────────────────────────────

/** 카드 첫 줄 — 굵은 앞부분(목업 글자 그대로). */
export const SALES_LEAD_STRONG = '이 건물이 속한 상권의 추정매출입니다';
/** 카드 첫 줄 — 나머지(「상권 값」은 굵게 — 컴포넌트가 이 셋을 이어 그린다). */
export const SALES_LEAD_REST: readonly [string, string, string] = [
  ' — 서울시가 카드 결제 금액으로 추정해 공표한 ',
  '상권 값',
  ' 그대로이고, 이 건물의 매출이 아닙니다.',
];

/** 배지(C등급 — 추정). */
export const SALES_BADGE = 'C등급 · 서울시 추정';
/** 배지 옆 작은 글(목업). */
export const SALES_BADGE_NOTE = '서울시 상권분석서비스 · 카드사 결제 기반 추정';

/**
 * 발 문구 다섯(목업 글자 그대로 · 메인 정정 — 「현금 매출은 들어 있지 않습니다」는 넣지 않는다).
 * 둘째는 [굵은 앞, 나머지]. ⓘ 「점포당 월평균」은 셋째 줄 **한 곳**에서 서울시 화면을 설명할 때만 나온다(시험이 지킨다).
 */
export const SALES_NOTES = {
  source: '출처: 서울시 상권분석서비스 「상권-추정매출」(열린데이터광장 · 공공누리 1유형 출처표시).',
  notBuilding: ['이 상권 전체의 값이며 이 건물의 값이 아닙니다.', ' 상권이 여럿이면 상권마다 따로 적고 더하지 않습니다.'] as const,
  unit: '금액·건수는 서울시가 공표한 분기(3개월) 합계 그대로입니다 — 서울시 화면은 이 값을 점포당 월평균으로 바꿔 보여 줍니다.',
  method: '카드사 결제 금액에 서울시가 보정 비율을 곱해 추정한 값이고, 산출식·표본은 서울시가 공개하지 않습니다.',
  industry: '업종은 서울시 생활밀접업종 기준이라 「업종 분포」 카드(소상공인시장진흥공단)와 다릅니다.',
} as const;

/** 상권 줄인데 창 안에 자료가 없음(no_data). */
export function salesNoDataText(row: DistrictSales): string {
  return `${windowText(row.window_quarters)} 동안 서울시가 이 상권의 추정매출 자료를 내지 않았습니다.`;
}

/** 흐름 그림에 '–' 칸이 있을 때 한 줄. */
export const SALES_GAP_NOTE = '‘–’ 칸은 그 분기에 서울시가 이 상권 자료를 내지 않은 것입니다.';
