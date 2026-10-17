import type { BasePrice, FloorRow, RentStat, SigunguTxStat } from '../types';
import { pairBasePrices } from './basePrice';
import { TX_MIN_SAMPLE } from './appConstants';
import { formatFloor, formatManWon, formatMonthKo } from './format';
import { defaultBldType, floorRentLines, quarterLabel, rentSummary } from './rentStats';

/**
 * 「층 차이 세 잣대 (공표값 나란히)」 카드의 **순수 짝짓기**(결정 0036 결정 15 · 물결 1-C2).
 *
 * 이 건물의 층마다 세 자료를 **각자 원래 단위 그대로** 한 줄에 나란히 놓는다:
 *   ① 국세청 기준시가(그 층 호실들의 ㎡당 가운데값 — `pairBasePrices` 그대로)
 *   ② 구 실거래 단가(그 층이 속한 Stage A 층대의 ㎡당 중앙값 — `get_sigungu_tx_stats` 그대로)
 *   ③ 부동산원 층별 임대료(임대 카드의 기본 종류 · 서버 차례 첫 조사구역의 `floor_rent` 그대로 — 천원/㎡)
 *
 * ⛔ **나누기·비율·% 를 만들지 않는다**(결정 15 · 결정 0031) — "2층은 1층의 몇 %"를 우리가 계산하면
 *    일부러 안 내보내는 층별효용비율을 다시 만드는 셈이다. 층끼리도, 자료끼리도 견주는 산수를 넣지 말 것.
 *    여기서 하는 일은 **고르기와 글자로 옮기기**뿐이다.
 * ⛔ 없는 값을 이웃 값으로 메우지 않는다 — 열쇠가 없는 층(옥탑·지하 2층 이하)은 '–' 다.
 */

/** 빈 칸 표기(값이 없거나 그 자료를 못 받았다). */
export const GAP_NONE = '–';

/** 칸 하나 — 값 글자 + 작은 글(근거·이름표). 값이 없으면 `value` 가 `GAP_NONE`, `sub` 는 null. */
export type GapCell = { value: string; sub: string | null };

/** 줄 하나 = 이 건물의 층 하나. */
export type GapRow = {
  floorNo: number;
  label: string;
  base: GapCell;
  tx: GapCell;
  rent: GapCell;
};

/** 칸 머리(출처·범위). 서버 값으로만 만든다 — 지역·달·조사구역 이름 하드코딩 0. */
export type GapHeads = {
  base: string;
  tx: string;
  rent: string;
};

const NONE: GapCell = { value: GAP_NONE, sub: null };

/**
 * 층 → 구 실거래 층대 이름(Stage A · `mv_sigungu_tx_stats` 의 정의 그대로 — 옥탑 99 는 '3층이상').
 * ⓘ 층 번호 0 은 없다(절대 규칙 4) — 들어오면 '3층이상' 으로 가지 않게 null.
 */
export function txBandOf(floorNo: number): string | null {
  if (floorNo < 0) return '지하';
  if (floorNo === 1) return '1층';
  if (floorNo === 2) return '2층';
  if (floorNo >= 3) return '3층이상';
  return null;
}

/**
 * 층 → 부동산원 층 구간 열쇠 후보(앞이 먼저). 옥탑·지하 2층 이하는 부동산원이 구간을 발표하지
 * 않으므로 빈 목록(→ '–').
 */
export function rentKeysOf(floorNo: number): readonly string[] {
  if (floorNo === 99) return [];
  if (floorNo === -1) return ['-1'];
  if (floorNo >= 1 && floorNo <= 5) return [String(floorNo)];
  if (floorNo >= 6 && floorNo <= 10) return ['6-10', '6+'];
  if (floorNo >= 11) return ['11+', '6+'];
  return [];
}

/** 천원/㎡ 공표값을 **그대로** 적는다(원으로 바꾸지 않는다 — 칸 머리 단위가 천원/㎡). */
function formatThousandWon(v: number): string {
  return v.toLocaleString('ko-KR', { maximumFractionDigits: 2 });
}

/** 임대 카드가 처음 보여 주는 줄 — 기본 종류(`defaultBldType`)의 서버 차례 첫 줄. 없으면 null. */
export function pickRentRow(rows: readonly RentStat[] | null): RentStat | null {
  if (rows === null || rows.length === 0) return null;
  const type = defaultBldType(rows);
  if (type === null) return null;
  return rows.find((r) => r.bld_type === type) ?? null;
}

/**
 * 세 자료를 층마다 한 줄로 짝짓는다. 줄 차례 = `floors` 차례(층 목록 카드와 같다 — 높은 층 위).
 * 자료가 null(못 받음)이면 그 칸은 전부 '–'.
 */
export function floorGapRows(
  floors: readonly FloorRow[],
  basePrices: BasePrice[] | null,
  txStats: readonly SigunguTxStat[] | null,
  rentRows: readonly RentStat[] | null,
): GapRow[] {
  const baseByFloor = new Map(
    pairBasePrices(basePrices, [...floors]).map((r) => [r.base.floor_no, r.base] as const),
  );
  const rentRow = pickRentRow(rentRows);
  const rentLines = rentRow ? floorRentLines(rentRow.floor_rent) : [];
  const rentSrc = (rentRow?.floor_rent ?? {}) as Record<string, unknown>;

  return floors.map((f) => {
    const b = baseByFloor.get(f.floor_no);
    const base: GapCell = b
      ? { value: formatManWon(b.median_price_per_m2), sub: `호 ${b.ho_cnt.toLocaleString('ko-KR')}개 가운데값` }
      : NONE;

    let tx: GapCell = NONE;
    const bandName = txBandOf(f.floor_no);
    const s = bandName && txStats ? txStats.find((x) => x.floor_band === bandName) : undefined;
    if (s) {
      const n = s.n.toLocaleString('ko-KR');
      tx =
        s.n >= TX_MIN_SAMPLE && s.median_unit_price !== null
          ? { value: `㎡당 ${formatManWon(s.median_unit_price)}`, sub: `${s.floor_band} · ${n}건` }
          : { value: `표본 부족 (${n}건)`, sub: null };
    }

    let rent: GapCell = NONE;
    for (const key of rentKeysOf(f.floor_no)) {
      const line = rentLines.find((l) => l.key === key);
      const v = rentSrc[key];
      if (line && typeof v === 'number') {
        // 줄마다 '이 건물 값 아님'이 읽히게 작은 글에 '상권 평균'을 박는다(검사관 🟠).
        rent = { value: formatThousandWon(v), sub: `상권 평균 · ${line.label}` };
        break;
      }
    }

    return { floorNo: f.floor_no, label: formatFloor(f.floor_no, f.floor_label), base, tx, rent };
  });
}

/**
 * 칸 머리 셋. 구 이름·창 시작 달·조사구역 이름은 **서버가 준 값**이다.
 * 부동산원이 조사 대상이 아니거나(빈 배열) 좌표가 없으면 임대 카드의 요약 글을 그대로 쓴다.
 */
export function floorGapHeads(
  txStats: readonly SigunguTxStat[] | null,
  rentRows: readonly RentStat[] | null,
  noCoord: boolean,
): GapHeads {
  const guName = txStats?.find((s) => s.sigungu_nm)?.sigungu_nm ?? null;
  const from = txStats?.find((s) => s.window_from)?.window_from ?? null;
  // 날짜 말투는 카드 머리 날짜 줄과 같은 '2024년 10월'(F2 · 👤 2026-10-16 ④) — 못 읽으면 원본 그대로.
  // 구 층대 단가는 상가(근생·판매) 거래만 센 값이다(결정 0040 D3) — 칸 머리도 그렇게 말한다.
  const tx = ['구 상가 실거래 단가', guName, from ? `${formatMonthKo(from) ?? from}부터` : null]
    .filter((x): x is string => x !== null)
    .join(' · ');

  let rent = '부동산원 임대료(월) · 천원/㎡';
  if (rentRows !== null && rentRows.length === 0) {
    rent = `${rent} · ${rentSummary([], noCoord)}`;
  } else {
    const row = pickRentRow(rentRows);
    if (row) {
      const q = quarterLabel(row.quarter);
      rent = `${rent} · ${row.rone_region_nm} ${row.bld_type} 평균 — 이 건물 값 아님${q ? ` (${q} 조사)` : ''}`;
    }
  }

  return { base: '국세청 기준시가 · 원/㎡ · 이 건물', tx, rent };
}

/**
 * 카드를 세울 만한가 — **값이 든 칸(자료)이 둘 이상**이고 그중 하나는 국세청·부동산원이어야 한다(👤 2026-10-11).
 * 구 실거래는 거의 늘 오므로, 국세청·부동산원이 둘 다 비면(실패·null·빈 배열·모든 층 '–') 그 한 칸만으로
 * '나란히'가 성립하지 않는다 — 카드째 숨긴다. 칸에 값이 들었다 = 작은 글(`sub`)이 있다(표본 부족·'–' 은 없다).
 */
export function floorGapShowable(rows: readonly GapRow[]): boolean {
  const has = (k: 'base' | 'tx' | 'rent') => rows.some((r) => r[k].sub !== null);
  const filled = (['base', 'tx', 'rent'] as const).filter(has).length;
  return filled >= 2 && (has('base') || has('rent'));
}

/** 구 실거래 표본 전체(배지 옆 건수). 못 받았으면 null. */
export function txTotal(txStats: readonly SigunguTxStat[] | null): number | null {
  if (txStats === null || txStats.length === 0) return null;
  return txStats.reduce((sum, s) => sum + (s.n ?? 0), 0);
}

/** 접힌 요약 — ⛔ 값을 적지 않는다(한정어를 담을 자리가 없어 이 건물 값으로 읽힌다). */
export const FLOOR_GAP_SUMMARY = '국세청 · 구 실거래 · 부동산원 — 층마다 나란히';

/** 발 문구(👤 2026-10-11 결정 글자 그대로). */
export const FLOOR_GAP_FOOT = '세 값은 서로 다른 자료·다른 단위입니다 — 서로 나누거나 비율을 계산하지 않았습니다.';
export const FLOOR_GAP_BASE_NOTE = '국세청 기준시가는 세무 기준가격 — 시세가 아닙니다.';
