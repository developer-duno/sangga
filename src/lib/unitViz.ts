/**
 * 층을 펼친 호 목록 위의 「호실 크기 칸」 한 줄(결정 0038 G · V3) — 순수 계산만.
 *
 * 칸 하나 = 호 하나 · 칸 폭 = 그 호 전용면적 ÷ 칸 줄에 그린 호 면적 합(%). **크기 비교이지 자리 배치가 아니다**
 * (대장에는 호가 어디 붙어 있는지가 없다 — 차례는 목록 차례 그대로).
 *
 * 지키는 것:
 *  · 칸은 첫 `UNIT_CELL_MAX`(50) 호까지 — 응답 `total_cnt` 가 더 많으면 「그 밖 N호」(면적 합은 50줄만 받아선 못 세므로
 *    적지 않는다 · 서버 호출 0 · 결정 0038 §7). 「더 보기」로 목록이 늘어도 칸 줄은 첫 50호 그대로다.
 *  · 전용면적이 없거나 0 이하인 호는 칸 없이 「–」(0 너비로 그리지 않는다 · §2-4) — 이름만 따로 센다.
 *  · 폭 % 는 그림 좌표일 뿐 글로 내지 않는다(§2-6 · 새 비율 글 0).
 *  · DOM 을 재지 않는다 — 칸 안 글자(「101호 · 54.0㎡」)를 넣을지는 **그 꼴의 가장 좁은 칸 줄 폭**(`UNIT_CELL_REF`)에서
 *    칸 폭이 글자 폭을 넉넉히 넘는지로 미리 정한다(V2 `TX_PLOT_REF` 와 같은 방식 · §2-3). 넓은 화면·종이 벌과 휴대폰 벌
 *    두 벌을 계산해 CSS 가 고른다.
 *
 * 못 보는 것: 글꼴이 바뀌어 한 글자가 어림(`txLabelWidth`)보다 넓어지면 글자가 칸에 꽉 낄 수 있다 — E2E 가 실제 상자로
 *   글자가 칸 안인지 다시 본다.
 */
import type { FloorUnit } from '../types';
import { txLabelWidth } from './txViz';
import { formatUnitArea, unitDisplayName } from './unitTable';
import { stackPct } from './viz';

/** 칸 줄에 그리는 호 수 상한(결정 0038 G — 목록 첫 쪽 `FLOOR_UNITS_PAGE` 와 같은 50). */
export const UNIT_CELL_MAX = 50;

/** 칸 안 글자 좌우 안쪽 여백(px · CSS `.ucell__lab` 의 padding 과 같다). */
export const UNIT_CELL_PAD = 4;
/** 칸 사이 흰 줄(px · CSS `.ucell + .ucell` 의 border-left 와 같다). */
export const UNIT_CELL_SEP = 1;
/** 「그 밖 N호」 글과 칸 줄 사이 틈(px · CSS `.ucells__row` 의 gap 과 같다). */
export const UNIT_CELL_REST_GAP = 8;

/**
 * 기준 폭(px · 칸 줄 바깥 상자 `.ucells__row` 의 가장 좁은 폭 이하) — 꼴 둘 × 벌 둘.
 *  · `detail` = 펼친 층 상세의 셋째 칸 「호실」 안 · `print` = 호실 구성표 고르기로 받은 층 줄 아래(`.floor__unitprint`).
 *  · `wide` = 721px 이상 화면 + 종이(A4 · 여백 12mm) · `narrow` = 휴대폰(720px 이하 화면 · 360px 까지 덮는다).
 * 2026-10-21 E2E 실측(칸 줄 바깥 폭 px) — 아래 값은 그 최솟값 아래로 내림:
 *    detail: 1280 두 칸 211 · **1024 두 칸 157** · 1023 한 열 241 · 721 한 열 195 · 종이(703 · 한 칸으로 접힘) 529 / 412 238 · **360 186**
 *    print : 1280 653 · **1024 492** · 1023 742 · 721 604 · 종이(703) 583 / 412 292 · **360 240**
 *  ⓘ 320px 전화(더 좁다)는 못 덮는다 · playwright 가 휴대폰 폭(412)을 그대로 둔 채 흉내 낸 종이(print 292)도 못 덮는다 —
 *    실제 종이는 A4 폭(703)이다. E2E CA 가 실제 폭 ≥ 기준 폭과 글자가 칸 안인지 다시 잰다.
 */
export const UNIT_CELL_REF = {
  detail: { wide: 150, narrow: 180 },
  print: { wide: 480, narrow: 230 },
} as const;

export type UnitCellRef = { wide: number; narrow: number };

/** 칸 하나. `pct` = 칸 줄 안 폭(%) · `text` = 칸 안 글자 · `labWide`·`labNarrow` = 그 벌에서 글자를 넣나. */
export type UnitCell = {
  text: string;
  pct: number;
  labWide: boolean;
  labNarrow: boolean;
};

export type UnitCells = {
  /** 그리는 칸(목록 차례). 비어 있으면 칸 줄을 안 그린다(전부 면적 없음). */
  cells: UnitCell[];
  /** 면적이 없거나 0 이하라 칸 없이 「–」로 적는 호 이름(목록 차례). */
  blanks: string[];
  /** 칸 줄에 안 넣은 나머지 호 수(= 그 층 전체 − 칸 줄이 본 호 수). 0 이면 「그 밖」 글이 없다. */
  rest: number;
};

/** 「그 밖 N호」(결정 0038 G 원문). */
export function unitCellsRestText(rest: number): string {
  return `그 밖 ${rest.toLocaleString('ko-KR')}호`;
}

/** 칸 안 글자 — 목록과 같은 서식 함수(`unitDisplayName` · `formatUnitArea`) · 예 「101호 · 54.0㎡」. */
export function unitCellText(ho: string | null, area: number): string {
  return `${unitDisplayName(ho)} · ${formatUnitArea(area)}`;
}

/** 칸 폭(%)이 기준 폭(px)에서 글자 + 좌우 여백 + 칸 사이 줄을 담나. */
export function unitCellLabelFits(pct: number, text: string, refW: number): boolean {
  return (pct / 100) * refW >= txLabelWidth(text) + 2 * UNIT_CELL_PAD + UNIT_CELL_SEP;
}

function isPositiveArea(v: number | null): v is number {
  return typeof v === 'number' && Number.isFinite(v) && v > 0;
}

/**
 * 호 목록 → 칸 줄. 목록이 0줄이면 null(주거·오피스텔·미상 층은 목록이 0줄이라 칸도 없다 · 결정 0038 G).
 * `total` = 응답 `total_cnt`(그 층 전체 호 수 · 모르면 null — 그때는 받은 줄 수).
 */
export function unitCells(units: FloorUnit[], total: number | null, ref: UnitCellRef): UnitCells | null {
  if (units.length === 0) return null;
  const shown = units.slice(0, UNIT_CELL_MAX);
  const all = typeof total === 'number' && Number.isFinite(total) ? total : units.length;
  const rest = Math.max(0, all - shown.length);
  const blanks: string[] = [];
  const drawn: Array<{ ho: string | null; area: number }> = [];
  for (const u of shown) {
    if (isPositiveArea(u.excl_area_m2)) drawn.push({ ho: u.ho, area: u.excl_area_m2 });
    else blanks.push(unitDisplayName(u.ho));
  }
  const pcts = stackPct(drawn.map((d, i) => ({ key: String(i), n: d.area })));
  // 「그 밖 N호」가 줄 끝에 서면 칸 줄이 그만큼 좁아진다 — 기준 폭에서 그 글 폭 + 틈을 뺀다.
  const restW = rest > 0 ? txLabelWidth(unitCellsRestText(rest)) + UNIT_CELL_REST_GAP : 0;
  const wideW = ref.wide - restW;
  const narrowW = ref.narrow - restW;
  const cells: UnitCell[] = (pcts ?? []).map((p) => {
    const d = drawn[Number(p.key)];
    const text = unitCellText(d.ho, d.area);
    return {
      text,
      pct: p.pct,
      labWide: unitCellLabelFits(p.pct, text, wideW),
      labNarrow: unitCellLabelFits(p.pct, text, narrowW),
    };
  });
  return { cells, blanks, rest };
}

/** 칸 없이 적는 호(「–」) 이름을 이만큼까지만 적는다 — 넘으면 「외 N호」. */
export const UNIT_CELL_BLANK_NAMES = 5;

/** 면적 없는 호 한 줄 — 예 「전용면적 값이 없는 호(칸 없음): B01호 – · B02호 –」. 없으면 null. */
export function unitCellsBlankText(blanks: string[]): string | null {
  if (blanks.length === 0) return null;
  const head = blanks.slice(0, UNIT_CELL_BLANK_NAMES).map((n) => `${n} –`).join(' · ');
  const more = blanks.length - UNIT_CELL_BLANK_NAMES;
  return `전용면적 값이 없는 호(칸 없음): ${head}${more > 0 ? ` 외 ${more.toLocaleString('ko-KR')}호` : ''}`;
}

/** 칸 줄 설명 글(결정 0038 G 원문 「크기 비교이지 자리 배치가 아님」). */
export const UNIT_CELLS_NOTE = '크기 비교이지 자리 배치가 아닙니다.';
