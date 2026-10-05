import type {
  DistrictOpenClose,
  OpenCloseIndustry,
  OpenCloseOther,
  OpenCloseQuarter,
  OpenCloseStatus,
} from '../types';
import { SIDOS } from './regions';
import { formatRate } from './rentStats';

/**
 * "상권 개업·폐업 (서울시 공표)" 카드의 **순수 계산**만 모은다(결정 0033).
 *
 * 컴포넌트에서 빼 둔 이유는 `rentStats.ts` 와 같다 — 분기 글자 변환 · 서버 응답 모양 ·
 * 추이 칸 만들기 · 접힌 요약 한 줄이 실제로 틀리기 쉬운 곳이고, 화면을 띄우지 않고 시험할
 * 수 있어야 한다.
 *
 * ⛔ **비율을 다시 계산하지 않는다.** 상권 전체 비율은 서버가 서울시 산식(개업·폐업 점포 ÷
 *    유사 업종 점포 × 100)으로 내고, 업종 비율은 서울시 공표값 그대로 온다. 여기서 하는 산수는
 *    추이 막대의 **높이**(그 상권 창 안 최댓값에 대한 비례)뿐이다 — 값이 아니라 그림의 크기다.
 * ⛔ **분기·연도 글자를 박지 않는다.** 어느 분기를 그릴지는 서버의 창(`window_quarters`)이
 *    정한다 — 박아 두면 다음 분기가 적재되는 날부터 이 파일만 옛말을 한다(가드 시험이 본다).
 */

/** 서버가 주는 줄 상태 다섯. 이 밖의 글자가 오면 모양 검사에서 떨어진다. */
export const OPEN_CLOSE_STATUSES: readonly OpenCloseStatus[] = [
  'no_coord',
  'not_seoul',
  'outside_seoul_district',
  'ok',
  'no_data',
];

/**
 * 상권 합산 비율을 내는 최소 표본(유사 업종 점포 수 합).
 *
 * ⓘ 판정은 **서버가** 한다(이 값보다 적으면 비율이 null 로 온다 — 결정 0033 결정 7). 여기
 *   숫자는 그 사실을 사람 말로 적는 데만 쓴다. 서버 상수를 바꾸면 이것도 함께 바꾼다.
 */
export const OPEN_CLOSE_MIN_SAMPLE = 30;

/** 서울시 분기 표기(연도 넷 + 분기 하나 · Q 없음)를 연도와 분기로. 읽을 수 없으면 null. */
export function splitQuarter(quarter: string | null | undefined): { year: string; q: string } | null {
  if (typeof quarter !== 'string') return null;
  const m = /^(\d{4})([1-4])$/.exec(quarter.trim());
  return m ? { year: m[1], q: m[2] } : null;
}

/**
 * 분기 표기 → '○○○○년 ○분기'. 읽을 수 없으면 **null**(원본 코드를 화면에 새지 않는다 —
 * `rentStats.quarterLabel` 과 같은 결이다. 그쪽은 'Q' 가 낀 부동산원 꼴만 읽는다).
 */
export function openCloseQuarterLabel(quarter: string | null | undefined): string | null {
  const s = splitQuarter(quarter);
  return s ? `${s.year}년 ${s.q}분기` : null;
}

/** 점포 수 표기('1,234곳'). 값이 없으면 '–'(0 이 아니다 — 모르는 것을 0 이라 적지 않는다). */
export function formatStoreCount(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '–';
  return `${n.toLocaleString('ko-KR')}곳`;
}

/**
 * 개업·폐업 한 칸의 글. 비율이 있으면 '개업 5곳 1.13%', 없으면 '개업 5곳'(비율을 지어내지 않는다).
 * ⓘ 비율 표기는 임대 카드와 같은 자(`formatRate` — 소수 둘째 자리까지)다.
 */
export function countRateText(label: string, count: number | null, rate: number | null): string {
  const r = formatRate(rate);
  return r === null ? `${label} ${formatStoreCount(count)}` : `${label} ${formatStoreCount(count)} ${r}`;
}

/** 업종 표 한 칸('1곳 (1%)' · 비율이 없으면 '1곳 (–)'). 비율은 공표값 그대로다. */
export function tableCellText(count: number | null, rate: number | null): string {
  return `${formatStoreCount(count)} (${formatRate(rate) ?? '–'})`;
}

/**
 * pnu 앞 두 자리로 시·도 짧은 이름을 고른다(대전 → '대전'). 목록에 없으면 null.
 * ⛔ 지역 이름을 화면에 박지 않는다 — 이 표(`SIDOS`)가 정본이다.
 */
export function sidoNameOfPnu(pnu: string): string | null {
  const code = pnu.slice(0, 2);
  return SIDOS.find((s) => s.code === code)?.name ?? null;
}

/** 창의 크기를 사람 말로 — 네 분기로 나눠지면 '최근 2년(8분기)', 아니면 '최근 N분기'. */
export function windowText(windowQuarters: readonly string[]): string {
  const n = windowQuarters.length;
  return n > 0 && n % 4 === 0 ? `최근 ${n / 4}년(${n}분기)` : `최근 ${n}분기`;
}

// ── 추이 칸 ─────────────────────────────────────────────────────────────────

/** 추이 그림의 한 칸 = 창 안의 분기 하나. */
export type TrendCell = {
  quarter: string;
  /** '○○○○년 ○분기'. 못 읽으면 원본 대신 빈 글자. */
  label: string;
  year: string;
  q: string;
  /**
   * ok = 두 비율이 있다 · nosample = 그 분기 자료는 있지만 표본이 모자라 비율이 없다 ·
   * missing = 그 상권에 그 분기 자료가 **아예 없다**(막대 0 이 아니라 빈 칸이다).
   */
  kind: 'ok' | 'nosample' | 'missing';
  openRt: number | null;
  closeRt: number | null;
  /** 막대 높이(%) — 그 상권 창 안의 두 비율 중 최댓값을 100 으로 둔 비례. ok 가 아니면 0. */
  openH: number;
  closeH: number;
  /** 그 분기 유사 업종 점포 수 합(nosample 이 몇 곳인지 적는 데 쓴다). missing 이면 null. */
  similr: number | null;
};

/**
 * 창(`window_quarters` — 최신 → 옛)과 그 상권의 분기 합(`quarters`)으로 추이 칸을 만든다.
 * **옛 분기가 왼쪽, 최신이 오른쪽**이다(읽는 방향 = 시간 방향).
 *
 * ⛔ 그 상권에 없는 분기는 **빈 칸(missing)** 이다 — 0 막대로 그리면 "개업·폐업이 0"으로 읽힌다.
 * ⛔ 비율이 null 인 분기(표본 부족)도 막대를 그리지 않는다(`nosample`).
 * ⓘ 0 은 값이다 — 비율이 0 인 분기는 ok 이고 높이만 0 이다.
 */
export function trendCells(
  windowQuarters: readonly string[],
  quarters: readonly OpenCloseQuarter[],
): TrendCell[] {
  const byQ = new Map(quarters.map((x) => [x.quarter, x]));
  const cells: TrendCell[] = [...windowQuarters].reverse().map((quarter): TrendCell => {
    const s = splitQuarter(quarter);
    const base = {
      quarter,
      label: s ? `${s.year}년 ${s.q}분기` : '',
      year: s?.year ?? '',
      q: s?.q ?? '',
      openH: 0,
      closeH: 0,
    };
    const hit = byQ.get(quarter);
    if (!hit) return { ...base, kind: 'missing', openRt: null, closeRt: null, similr: null };
    if (hit.opbiz_rt === null || hit.clsbiz_rt === null) {
      return { ...base, kind: 'nosample', openRt: null, closeRt: null, similr: hit.similr_induty_stor_co };
    }
    return {
      ...base,
      kind: 'ok',
      openRt: hit.opbiz_rt,
      closeRt: hit.clsbiz_rt,
      similr: hit.similr_induty_stor_co,
    };
  });
  const max = Math.max(0, ...cells.flatMap((c) => (c.kind === 'ok' ? [c.openRt ?? 0, c.closeRt ?? 0] : [])));
  if (max > 0) {
    for (const c of cells) {
      if (c.kind !== 'ok') continue;
      c.openH = ((c.openRt ?? 0) / max) * 100;
      c.closeH = ((c.closeRt ?? 0) / max) * 100;
    }
  }
  return cells;
}

/** 그 상권 최신 분기의 합 한 줄. 없으면 null(모양 검사가 ok 줄에는 있음을 보장한다). */
export function latestOf(row: DistrictOpenClose): OpenCloseQuarter | null {
  return row.quarters?.find((x) => x.quarter === row.latest_quarter) ?? null;
}

// ── 접힌 요약 ───────────────────────────────────────────────────────────────

/**
 * 접혀 있어도 보이는 한 줄.
 *
 * ⓘ 임대 카드와 달리 값을 적는다 — 대신 **상권 이름을 맨 앞에** 둬서 "이 건물이 아니라 그
 *   상권의 값"이라는 한정어가 같은 줄에 함께 있게 한다. 상권이 여럿이면 첫 상권(서버 차례 =
 *   좁은 상권 먼저) 이름 뒤에 '외 N곳'.
 * ⓘ 빈 상태(서울 아님·상권 없음·좌표 없음·자료 없음)는 그 사실을 그대로 한 줄로 적는다.
 */
export function openCloseSummary(rows: readonly DistrictOpenClose[], pnu: string): string {
  const head = rows.find((r) => r.status !== 'ok' && r.status !== 'no_data');
  if (head) {
    if (head.status === 'not_seoul') {
      const sido = sidoNameOfPnu(pnu);
      return sido === null
        ? '서울 상권만 다루는 자료라 이 건물에는 없습니다'
        : `서울 상권만 다루는 자료라 이 건물(${sido})에는 없습니다`;
    }
    if (head.status === 'outside_seoul_district') return '이 건물이 속한 서울시 상권이 없습니다';
    return '위치 정보가 없어 속한 상권을 찾지 못했습니다';
  }

  const districts = rows.filter((r) => r.status === 'ok' || r.status === 'no_data');
  const firstOk = districts.find((r) => r.status === 'ok');
  const lead = firstOk ?? districts[0];
  const name = districtName(lead);
  const others = districts.length - 1;
  const who = others > 0 ? `${name} 외 ${others}곳` : name;
  if (!firstOk) return `${who} · ${windowText(lead?.window_quarters ?? [])} 서울시 자료 없음`;

  const latest = latestOf(firstOk);
  const label = openCloseQuarterLabel(firstOk.latest_quarter);
  if (!latest || !label) return who;
  const open = summaryPart('개업', latest.opbiz_stor_co, latest.opbiz_rt);
  const close = summaryPart('폐업', latest.clsbiz_stor_co, latest.clsbiz_rt);
  return `${who} · ${label} ${open} · ${close}`;
}

function summaryPart(label: string, count: number | null, rate: number | null): string {
  const r = formatRate(rate);
  return r === null ? `${label} ${formatStoreCount(count)}` : `${label} ${formatStoreCount(count)}(${r})`;
}

/** 상권 이름. 비어 있으면 빈칸 대신 이렇게 적는다(빈 제목은 상권이 아닌 무언가로 읽힌다). */
export function districtName(row: DistrictOpenClose | undefined): string {
  return row?.district_nm || '(이름 없는 상권)';
}

// ── 모양 검사 ───────────────────────────────────────────────────────────────

function isNullableNumber(x: unknown): x is number | null {
  return x === null || (typeof x === 'number' && Number.isFinite(x));
}

function isNullableString(x: unknown): x is string | null {
  return x === null || x === undefined || typeof x === 'string';
}

const COUNT_KEYS = [
  'similr_induty_stor_co',
  'stor_co',
  'frc_stor_co',
  'opbiz_stor_co',
  'clsbiz_stor_co',
] as const;

function hasCountsAndRates(r: Record<string, unknown>): boolean {
  return (
    COUNT_KEYS.every((k) => isNullableNumber(r[k] ?? null)) &&
    isNullableNumber(r.opbiz_rt ?? null) &&
    isNullableNumber(r.clsbiz_rt ?? null)
  );
}

export function isOpenCloseQuarter(x: unknown): x is OpenCloseQuarter {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return typeof r.quarter === 'string' && hasCountsAndRates(r);
}

function isIndustry(x: unknown): x is OpenCloseIndustry {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return typeof r.svc_induty_cd === 'string' && isNullableString(r.svc_induty_cd_nm) && hasCountsAndRates(r);
}

/**
 * 업종 표 줄들. 배열이 아니거나 한 줄이라도 모양이 이상하면 **null**(그 표만 빠진다 — 카드는 선다).
 *
 * ⛔ 이상한 줄 하나만 빼고 나머지를 그리지 않는다 — 상위 10 표에서 한 줄이 빠지면 '그 밖 N업종'
 *    줄과 숫자가 맞지 않게 된다. 표 전체를 빼는 것이 정직하다.
 */
export function industryRows(x: unknown): OpenCloseIndustry[] | null {
  return Array.isArray(x) && x.length > 0 && x.every(isIndustry) ? x : null;
}

/** '그 밖 N업종' 한 줄. 없거나 모양이 이상하면 null(그 줄만 빠진다). */
export function otherIndustries(x: unknown): OpenCloseOther | null {
  if (typeof x !== 'object' || x === null || Array.isArray(x)) return null;
  const r = x as Record<string, unknown>;
  return typeof r.industry_count === 'number' && r.industry_count > 0 && hasCountsAndRates(r)
    ? (x as OpenCloseOther)
    : null;
}

function isRow(x: unknown): x is DistrictOpenClose {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  if (typeof r.status !== 'string' || !(OPEN_CLOSE_STATUSES as readonly string[]).includes(r.status)) {
    return false;
  }
  if (!Array.isArray(r.window_quarters) || !r.window_quarters.every((q) => typeof q === 'string')) {
    return false;
  }
  if (r.status === 'ok') {
    return (
      typeof r.district_id === 'string' &&
      isNullableString(r.district_nm) &&
      isNullableString(r.district_type) &&
      typeof r.latest_quarter === 'string' &&
      Array.isArray(r.quarters) &&
      r.quarters.every(isOpenCloseQuarter) &&
      r.quarters.some((q) => (q as OpenCloseQuarter).quarter === r.latest_quarter)
    );
  }
  if (r.status === 'no_data') {
    return typeof r.district_id === 'string' && isNullableString(r.district_nm) && isNullableString(r.district_type);
  }
  return true;
}

/**
 * 서버 응답의 **모양**을 본다. 하나라도 어긋나면 false → 카드가 통째로 빠진다(콘솔 경고만).
 *
 * ⛔ 빈 배열도 false 다 — 서버는 어떤 필지에도 적어도 한 줄(상태 줄 또는 상권 줄)을 준다.
 *    빈 답은 이 함수가 아는 답이 아니라서 "자료 없음"이라 적으면 거짓이 될 수 있다.
 * ⓘ 업종 표 두 칸(`industries`·`other_industries`)은 여기서 보지 않는다 — 이상하면 그 표만
 *   빠진다(`industryRows`·`otherIndustries` · 임대 카드의 선택 칸과 같은 결).
 */
export function isOpenCloseList(x: unknown): x is DistrictOpenClose[] {
  return Array.isArray(x) && x.length > 0 && x.every(isRow);
}
