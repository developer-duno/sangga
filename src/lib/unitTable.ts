import type { FloorUnit, UnitFloorKind, UnitFloorSummary } from '../types';

/**
 * 호실 구성표(결정 0032)의 **순수 규칙**만 모은다 — 서버 응답 모양 검사 · 요약 한 줄 글 ·
 * 층 줄에 붙을 자리가 없는 호실 세기 · 안내 문장.
 *
 * 컴포넌트에서 빼 둔 이유는 `rentStats.ts`·`lhNotices.ts` 와 같다 — 틀리기 쉬운 곳이 전부
 * 여기고, 화면을 띄우지 않고 시험할 수 있어야 한다.
 *
 * ⛔ **층 종류를 여기서 판정하지 않는다.** `floor_kind` 는 서버가 두 함수에서 글자 그대로 같은
 *    판정식으로 정한다(결정 0032 「층 종류를 가르는 자」). 화면이 이름을 보고 다시 가르면
 *    요약과 목록이 서로 다른 말을 한다 — 여기서는 받은 값을 글로 옮기기만 한다.
 * ⛔ **면적을 계산하지 않는다.** 가운데값·최소·최대는 서버가 낸 값을 그대로 적는다. 층끼리
 *    더해 "이 건물 호실 N개"를 만들지 않는다(복층·되풀이 이름 때문에 어느 셈도 정확하지 않다).
 */

/** 서버가 줄 수 있는 층 종류 다섯. 이 밖의 값이 온 줄은 그 줄만 뺀다(뜻을 지어내지 않는다). */
export const UNIT_FLOOR_KINDS: ReadonlySet<string> = new Set<UnitFloorKind>([
  'commercial',
  'mixed',
  'residential',
  'officetel',
  'unknown',
]);

/**
 * 호 목록을 주는 층 종류. 서버도 이 둘에서만 목록을 준다 — 화면은 그 밖의 층에서
 * **목록을 부르지조차 않는다**(아파트 세대 목록 요청이 나가지 않게).
 */
export function hasUnitList(kind: UnitFloorKind): boolean {
  return kind === 'commercial' || kind === 'mixed';
}

/** 숫자 칸 하나. 숫자거나 숫자 글자면 숫자로, 아니면 undefined(= 모양이 틀림). */
function toNum(v: unknown): number | undefined {
  if (typeof v === 'number') return Number.isFinite(v) ? v : undefined;
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
}

/** 빈 칸 허용 숫자. null·undefined → null, 숫자 → 숫자, 그 밖 → undefined(모양이 틀림). */
function toNullableNum(v: unknown): number | null | undefined {
  if (v === null || v === undefined) return null;
  return toNum(v);
}

/**
 * `list_unit_floor_summary` 응답 검사.
 *
 * - 배열이 아니면 **null**(= 실패). 화면은 요약도 "자료 없음" 안내도 그리지 않는다.
 * - 빈 배열은 빈 배열(= 이 건물에 호실 자료가 없다 — 안내가 선다). 둘을 섞지 않는다.
 * - 모양이 이상한 줄은 **그 줄만** 뺀다. ⛔ `.every()` 로 통째 거부하지 않는다 — 한 줄 때문에
 *   요약 전체가 사라지는 일이 LH 카드에서 실제로 났다(레포 CLAUDE.md).
 * - 빈 칸 허용: 면적 셋은 null 이 정상이다(주거·오피스텔·미상 층). 층도 null 이면 "층 미상" 묶음.
 */
export function parseUnitSummary(data: unknown): UnitFloorSummary[] | null {
  if (!Array.isArray(data)) return null;
  const out: UnitFloorSummary[] = [];
  for (const raw of data) {
    if (raw === null || typeof raw !== 'object') continue;
    const r = raw as Record<string, unknown>;
    const floorNo = toNullableNum(r.floor_no);
    const unitCnt = toNum(r.unit_cnt);
    const med = toNullableNum(r.median_area_m2);
    const min = toNullableNum(r.min_area_m2);
    const max = toNullableNum(r.max_area_m2);
    const kind = r.floor_kind;
    if (floorNo === undefined || (floorNo !== null && !Number.isInteger(floorNo))) continue;
    if (unitCnt === undefined || !Number.isInteger(unitCnt) || unitCnt < 0) continue;
    if (med === undefined || min === undefined || max === undefined) continue;
    if (typeof kind !== 'string' || !UNIT_FLOOR_KINDS.has(kind)) continue;
    out.push({
      floor_no: floorNo,
      unit_cnt: unitCnt,
      median_area_m2: med,
      min_area_m2: min,
      max_area_m2: max,
      floor_kind: kind as UnitFloorKind,
    });
  }
  return out;
}

/**
 * `list_floor_units` 응답 검사. 배열이 아니면 null(= 실패). 이상한 줄은 그 줄만 뺀다.
 * 빈 칸 허용: `ho` 는 null·'' 둘 다 온다 · 면적도 null 일 수 있다.
 */
export function parseFloorUnits(data: unknown): FloorUnit[] | null {
  if (!Array.isArray(data)) return null;
  const out: FloorUnit[] = [];
  for (const raw of data) {
    if (raw === null || typeof raw !== 'object') continue;
    const r = raw as Record<string, unknown>;
    const ho = r.ho;
    const area = toNullableNum(r.excl_area_m2);
    const total = toNum(r.total_cnt);
    if (!(ho === null || ho === undefined || typeof ho === 'string')) continue;
    if (area === undefined) continue;
    if (total === undefined || !Number.isInteger(total) || total < 0) continue;
    out.push({ ho: ho ?? null, excl_area_m2: area, total_cnt: total });
  }
  return out;
}

/**
 * 면적 한 칸 — 소수 첫째 자리까지 늘 적는다('4.0㎡'). 값이 아니면(빈 값·0 이하) '—'.
 * ⓘ 평 환산은 붙이지 않는다 — 몇 ㎡짜리 칸 수백 개를 줄줄이 적는 자리라 괄호가 읽기를 막는다.
 */
export function formatUnitArea(m2: number | null | undefined): string {
  if (m2 === null || m2 === undefined || !Number.isFinite(m2) || m2 <= 0) return '—';
  return `${m2.toLocaleString('ko-KR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}㎡`;
}

/**
 * 층 줄 아래 둘째 줄(`.floor__units`)에 적는 요약 한 줄(결정 0032 `:143-145`).
 *
 * - 목록 제공 층: `호실 N칸 · 보통 A㎡ · B~C㎡` (1칸이면 `호실 1칸 · A㎡`)
 * - 주거 층: `세대 N` · 오피스텔 층: `오피스텔 N실` · 미상: `호실 N칸 · 용도 미상`
 *
 * ⓘ 목록 제공 층인데 면적이 하나도 값이 아니면(전부 0 이하) 면적 조각만 뺀다 — 없는 면적을
 *   '0㎡'로 적지 않는다.
 */
export function unitSummaryText(row: UnitFloorSummary): string {
  const n = row.unit_cnt.toLocaleString('ko-KR');
  switch (row.floor_kind) {
    case 'residential':
      return `세대 ${n}`;
    case 'officetel':
      return `오피스텔 ${n}실`;
    case 'unknown':
      return `호실 ${n}칸 · 용도 미상`;
    default: {
      const head = `호실 ${n}칸`;
      if (formatUnitArea(row.median_area_m2) === '—') return head;
      if (row.unit_cnt === 1) return `${head} · ${formatUnitArea(row.median_area_m2)}`;
      const range =
        formatUnitArea(row.min_area_m2) !== '—' && formatUnitArea(row.max_area_m2) !== '—'
          ? ` · ${formatUnitArea(row.min_area_m2).replace('㎡', '')}~${formatUnitArea(row.max_area_m2)}`
          : '';
      return `${head} · 보통 ${formatUnitArea(row.median_area_m2)}${range}`;
    }
  }
}

/** 호 이름 — 대장 원문 그대로. 빈 이름(null·'')은 "(호 이름 없음)"(결정 0032 문구 표). */
export function unitDisplayName(ho: string | null): string {
  return ho === null || ho === '' ? '(호 이름 없음)' : ho;
}

/**
 * 층 줄에 붙을 자리가 없는 호실(결정 0032 `:154-156`).
 *
 * 층 목록은 층별개요(`v_floor_stack`)에서 오므로 ① 층이 빈 호실 ② 층별개요에 없는 층의 호실은
 * 붙을 줄이 없다. 조용히 사라지지 않게 셈을 돌려준다(셋 다 0 이면 화면이 그 줄을 안 그린다).
 */
export function orphanUnits(
  summary: UnitFloorSummary[],
  stackFloorNos: number[],
): { noFloorUnits: number; missingFloors: number; missingFloorUnits: number } {
  const onStack = new Set(stackFloorNos);
  let noFloorUnits = 0;
  let missingFloors = 0;
  let missingFloorUnits = 0;
  for (const r of summary) {
    if (r.floor_no === null) noFloorUnits += r.unit_cnt;
    else if (!onStack.has(r.floor_no)) {
      missingFloors += 1;
      missingFloorUnits += r.unit_cnt;
    }
  }
  return { noFloorUnits, missingFloors, missingFloorUnits };
}

/** 위 셈을 한 줄 글로. 둘 다 없으면 null(줄을 안 그린다). */
export function orphanUnitsText(o: ReturnType<typeof orphanUnits>): string | null {
  const parts: string[] = [];
  if (o.noFloorUnits > 0) parts.push(`층을 알 수 없는 호실 ${o.noFloorUnits.toLocaleString('ko-KR')}칸`);
  if (o.missingFloors > 0) {
    parts.push(
      `층 목록에 없는 층 ${o.missingFloors.toLocaleString('ko-KR')}개의 호실 ${o.missingFloorUnits.toLocaleString('ko-KR')}칸`,
    );
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}

/**
 * 호실 자료가 없는 건물(요약 0줄)의 안내 한 줄(결정 0032 `:157-159` · 문구 `:174`).
 *
 * ⛔ 집합건물인데 이 동에 호실이 안 붙은 경우를 "일반 건물이라"로 단정하지 않는다 — 같은 땅
 *    다른 동에만 호실이 붙은 동이 실제로 많다(1만 2천여 동). 건물 종류를 모르면 중립 문장만.
 * ⛔ "같은 땅 다른 동" 절은 **그 땅에 동이 둘 이상일 때만**(`bldCntInPnu > 1`) — 한 동뿐인 땅에서
 *    그 말을 하면 없는 동을 가리킨다. 동 수를 모르거나 1 이면 중립 문장만.
 */
export function noUnitDataText(
  isJiphap: boolean | null | undefined,
  bldCntInPnu?: number | null,
): string {
  const head = '이 건물에는 호실 자료가 없습니다';
  if (isJiphap === false) {
    return `${head} — 칸별로 등기가 나뉘지 않은 일반 건물이면 원래 없는 자료입니다.`;
  }
  if (isJiphap === true && typeof bldCntInPnu === 'number' && bldCntInPnu > 1) {
    return `${head} — 같은 땅 다른 동에 붙어 있을 수 있습니다.`;
  }
  return `${head}.`;
}

/** '보통' 각주(결정 0032 문구 표). */
export const UNIT_MEDIAN_NOTE = "'보통'은 그 층 호실 전용면적의 가운데값입니다.";

/** 복층 각주(결정 0032 문구 표). */
export const UNIT_MULTI_FLOOR_NOTE = '여러 층에 걸친 호실은 걸친 층마다 한 번씩 셉니다.';

/** 주거·오피스텔 층의 상세 칸 안내(결정 0032 `:149`). */
export const UNIT_HOME_FLOOR_NOTE = '주거·오피스텔 층은 호 목록을 보여 주지 않습니다.';
