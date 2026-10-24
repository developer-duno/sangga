import type { FloorIndustryRow, FloorRow } from '../types';
import { formatFloor } from './format';

/*
  층 목록 카드의 층별 업종 띠(결정 0038 D · V4 · 👤 2026-10-17 「가」).

  층 줄의 면적 막대 아래 **가는 띠** 하나 — 색 = 소진공 **대분류** · 길이 = 이 땅의 그 층 점포 수(이 건물 층 목록에서 가장 많은 층 = 막대 칸
  끝까지). 값은 함수 `list_floor_industry(p_pnu)` 를 그대로 나른다 — 층 줄 「점포 N」(`v_floor_stack.store_cnt`)과 같은 행 집합이다.

  지키는 것:
   · 띠 합 = 그 층 store_cnt — 한 층이라도 어긋나면 **응답을 통째로 버린다**(`floorIndustryView` 가 null). 띠와 옆 글이 다른 수를 말하면
     에러 없이 거짓이다(보여 주는 분기가 두 요청 사이에 바뀐 순간 등).
   · 색은 고정(§2-7) — 음식=파랑 · 소매=주황 · 과학·기술=청록 · 교육=노랑 · 부동산=분홍 · 그 밖=회색. 띠 안 순서 = 범례 순서(흑백 종이에서도
     순서로 읽힌다) · 대분류가 없는 가게는 「그 밖」.
   · 없는 값은 그리지 않는다 — 점포 0 인 층은 띠가 없다(0 너비 조각을 최소 폭으로 키우지 않는다 · §2-4).
   · DOM 을 재지 않는다 — 폭은 전부 %(§2-3).
   · 비율을 글자로 내지 않는다 — 여기 % 는 폭에만 쓴다(결정 0033).
   · 층 번호가 없는 가게는 「층 모름 N곳」 한 줄 · 이 건물 층 목록에 없는 층 번호의 가게는 「자리 없는 점포 N곳」 한 줄(숨기지 않는다).
*/

export type FloorIndustryCat = 'food' | 'retail' | 'sci' | 'edu' | 'realty' | 'other';

/** 범주 고정 표(§2-7) — 차례가 곧 띠 안 순서·범례 순서다. `token` = `styles.css` `:root` 의 색 변수 이름. */
export const FLOOR_INDUSTRY_CATS: ReadonlyArray<{
  key: FloorIndustryCat;
  label: string;
  codes: readonly string[];
  token: string;
}> = [
  { key: 'food', label: '음식', codes: ['I2'], token: '--ind-food' },
  { key: 'retail', label: '소매', codes: ['G2'], token: '--ind-retail' },
  { key: 'sci', label: '과학·기술', codes: ['M1'], token: '--ind-sci' },
  { key: 'edu', label: '교육', codes: ['P1'], token: '--ind-edu' },
  { key: 'realty', label: '부동산', codes: ['L1'], token: '--ind-realty' },
  { key: 'other', label: '그 밖', codes: [], token: '--ind-other' },
];

const LABEL: Record<FloorIndustryCat, string> = Object.fromEntries(
  FLOOR_INDUSTRY_CATS.map((c) => [c.key, c.label]),
) as Record<FloorIndustryCat, string>;

/** 대분류 코드 → 띠 범주. 표에 없는 코드·빈 코드는 「그 밖」. */
export function industryCatOf(cd: string | null | undefined): FloorIndustryCat {
  const code = typeof cd === 'string' ? cd.trim() : '';
  return FLOOR_INDUSTRY_CATS.find((c) => c.codes.includes(code))?.key ?? 'other';
}

/**
 * 응답 모양 검사 — 하나라도 어긋나면 **통째로** null(그 응답을 버린다 · 띠·「층 모름」 줄을 안 그린다).
 * 줄마다: 층 = null 이거나 0 이 아닌 정수 · 대분류 코드·이름 = 글자 또는 null · 점포 수 = 1 이상의 정수.
 * ⓘ 빈 배열은 정상이다(이 분기에 이 땅 가게가 없다).
 */
export function parseFloorIndustry(data: unknown): FloorIndustryRow[] | null {
  if (!Array.isArray(data)) return null;
  const out: FloorIndustryRow[] = [];
  for (const row of data) {
    if (typeof row !== 'object' || row === null) return null;
    const { floor_no: f, cat_l_cd: cd, cat_l_nm: nm, store_cnt: n } = row as Record<string, unknown>;
    if (f !== null && (typeof f !== 'number' || !Number.isInteger(f) || f === 0)) return null;
    if (cd !== null && typeof cd !== 'string') return null;
    if (nm !== null && typeof nm !== 'string') return null;
    if (typeof n !== 'number' || !Number.isSafeInteger(n) || n < 1) return null;
    out.push({ floor_no: f, cat_l_cd: cd, cat_l_nm: nm, store_cnt: n });
  }
  return out;
}

/** 한 묶음(층 하나 · 층 모름)의 띠 — 범주는 고정 차례, 0 인 범주는 없다. */
export type FloorBand = {
  total: number;
  parts: ReadonlyArray<{ key: FloorIndustryCat; n: number }>;
};

export type FloorIndustryView = {
  /** 층 목록에 있고 점포가 1곳 이상인 층만. */
  byFloor: ReadonlyMap<number, FloorBand>;
  /** byFloor 가운데 가장 많은 점포 수(띠 길이의 자 — 이 층이 막대 칸 끝까지). byFloor 가 비면 0. */
  max: number;
  /** 층 번호가 없는 가게(na 묶음). 없으면 null. */
  unknown: FloorBand | null;
  /** 이 건물 층 목록에 없는 층 번호의 가게. 없으면 null. 층은 층 목록처럼 위층 먼저. */
  placeless: { total: number; floors: ReadonlyArray<{ floor_no: number; n: number }> } | null;
};

function bandOf(rows: ReadonlyArray<FloorIndustryRow>): FloorBand {
  const by = new Map<FloorIndustryCat, number>();
  for (const r of rows) {
    const k = industryCatOf(r.cat_l_cd);
    by.set(k, (by.get(k) ?? 0) + r.store_cnt);
  }
  const parts = FLOOR_INDUSTRY_CATS.filter((c) => (by.get(c.key) ?? 0) > 0).map((c) => ({
    key: c.key,
    n: by.get(c.key)!,
  }));
  return { total: parts.reduce((s, p) => s + p.n, 0), parts };
}

/**
 * 응답 + 층 목록 → 그릴 것. **층 목록의 층마다 띠 합 ≠ 그 층 store_cnt 면 null**(통째로 버린다).
 * store_cnt 가 null 인 층은 0 으로 본다(그 층에 띠가 오면 어긋남 — 모르는 수 옆에 띠를 그리지 않는다).
 */
export function floorIndustryView(
  rows: ReadonlyArray<FloorIndustryRow>,
  floors: ReadonlyArray<Pick<FloorRow, 'floor_no' | 'store_cnt'>>,
): FloorIndustryView | null {
  const onList = new Set(floors.map((f) => f.floor_no));
  const grouped = new Map<number, FloorIndustryRow[]>();
  const unknownRows: FloorIndustryRow[] = [];
  for (const r of rows) {
    if (r.floor_no === null) unknownRows.push(r);
    else grouped.set(r.floor_no, [...(grouped.get(r.floor_no) ?? []), r]);
  }
  const byFloor = new Map<number, FloorBand>();
  for (const f of floors) {
    const band = bandOf(grouped.get(f.floor_no) ?? []);
    if (band.total !== (f.store_cnt ?? 0)) return null;
    if (band.total > 0) byFloor.set(f.floor_no, band);
  }
  const placelessFloors = [...grouped.entries()]
    .filter(([no]) => !onList.has(no))
    .map(([no, rs]) => ({ floor_no: no, n: rs.reduce((s, r) => s + r.store_cnt, 0) }))
    .sort((a, b) => b.floor_no - a.floor_no);
  const placelessTotal = placelessFloors.reduce((s, p) => s + p.n, 0);
  const unknown = bandOf(unknownRows);
  return {
    byFloor,
    max: Math.max(0, ...[...byFloor.values()].map((b) => b.total)),
    unknown: unknown.total > 0 ? unknown : null,
    placeless: placelessTotal > 0 ? { total: placelessTotal, floors: placelessFloors } : null,
  };
}

/**
 * 띠 조각 폭(%) — 조각마다 `n ÷ 자 × 100`(띠 전체 길이 = 그 층 점포 수 ÷ 자). 자가 0 이하·띠보다 작으면 null(그리지 않는다).
 */
export function bandSegments(
  band: FloorBand,
  max: number,
): Array<{ key: FloorIndustryCat; pct: number }> | null {
  if (!Number.isFinite(max) || max <= 0 || band.total <= 0 || band.total > max) return null;
  return band.parts.map((p) => ({ key: p.key, pct: (p.n / max) * 100 }));
}

function partsText(band: FloorBand, unit: string): string {
  return band.parts.map((p) => `${LABEL[p.key]} ${p.n.toLocaleString('ko-KR')}${unit}`).join(' · ');
}

/** 띠 하나의 이름(읽는 기기 · 올리면 이름) — `1층 가게 업종(대분류): 음식 2곳 · 소매 1곳`. */
export function bandLabel(floorNo: number, floorLabel: string | null, band: FloorBand): string {
  return `${formatFloor(floorNo, floorLabel)} 가게 업종(대분류): ${partsText(band, '곳')}`;
}

/** 범례 줄 머리(👤 결정 D — 「대분류」·「이 땅의 가게」·펼친 목록은 소분류). ⓘ 문구는 구현자 제안(2026-10-24). */
export const FLOOR_INDUSTRY_LEGEND_LEAD =
  '막대 아래 가는 띠 = 이 땅의 가게 수와 업종 대분류(층을 펼치면 나오는 가게 목록은 소분류)';

/** 범례에 올릴 범주 — 그려진 띠에 실제로 든 것만, 고정 차례. */
export function legendCats(view: FloorIndustryView): FloorIndustryCat[] {
  const seen = new Set<FloorIndustryCat>();
  for (const b of view.byFloor.values()) for (const p of b.parts) seen.add(p.key);
  return FLOOR_INDUSTRY_CATS.filter((c) => seen.has(c.key)).map((c) => c.key);
}

/** 범주 이름표. */
export function industryCatLabel(key: FloorIndustryCat): string {
  return LABEL[key];
}

/**
 * 카드 아래 「층 모름」 한 줄(👤 결정 D) — `층 모름 20곳 — 원본에 층이 비어 있거나 읽을 수 없는 가게, 숫자 없이 "지하"라고만 적힌 가게 (음식 10 · 소매 5 · 그 밖 5)`.
 * ⓘ 꼴은 시안(Q6iSgycc… D 「가」) 그대로 + 「읽을 수 없는」(2-2c D2' 의 층 미상 풀이 낱말).
 */
export function unknownStoresText(band: FloorBand): string {
  return (
    `층 모름 ${band.total.toLocaleString('ko-KR')}곳 — 원본에 층이 비어 있거나 읽을 수 없는 가게, ` +
    `숫자 없이 "지하"라고만 적힌 가게 (${partsText(band, '')})`
  );
}

/**
 * 카드 아래 「자리 없는 점포」 한 줄(👤 결정 D) — `자리 없는 점포 3곳 — 이 건물 층 목록에 없는 층에 적힌 가게 (7층 2곳 · 지하 3층 1곳)`.
 * 한 땅에 건물이 여러 동이면(`multiDong` — 층 줄의 `bld_cnt_in_pnu > 1`) 「 · 이 땅의 다른 동 가게일 수 있습니다」를 더한다(👤 2026-10-24 ·
 * 점포는 땅 단위라 옆 동 층의 가게가 여기 든다). 한 동짜리 땅은 그대로.
 */
export function placelessStoresText(p: NonNullable<FloorIndustryView['placeless']>, multiDong = false): string {
  const floors = p.floors.map((f) => `${formatFloor(f.floor_no, null)} ${f.n.toLocaleString('ko-KR')}곳`).join(' · ');
  const dong = multiDong ? ' · 이 땅의 다른 동 가게일 수 있습니다' : '';
  return `자리 없는 점포 ${p.total.toLocaleString('ko-KR')}곳 — 이 건물 층 목록에 없는 층에 적힌 가게${dong} (${floors})`;
}
