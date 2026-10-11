import type {
  IndustryCat,
  IndustryDetail,
  IndustryDistrict,
  IndustryFloorScope,
  IndustryFloors,
  IndustryMedian,
  IndustryMedianPop,
  IndustryMix,
  IndustryScope,
} from '../types';
import { SIDOS } from './regions';

/**
 * 업종 분포 화면의 순수 계산만 모은다(결정 0014).
 *
 * 컴포넌트에서 빼 둔 이유는 `priceBand.ts` 와 같다 — 여기 있는 규칙들은 화면을 띄우지
 * 않고도 시험할 수 있어야 하고, 실제로 틀리기 쉬운 곳이 전부 여기다.
 */

/** 막대 하나 = 한 스코프 안에서 그 업종이 차지하는 몫. */
export type MixBar = IndustryCat & {
  /** 0~100. 막대 폭에만 쓴다. */
  pct: number;
};

/**
 * 스코프 하나를 막대 목록으로 바꾼다.
 *
 * ⚠️ 몫의 분모는 **그 스코프의 total** 이지 화면 전체가 아니다. 상권과 반경은 세는 대상이
 *    달라 분모를 공유할 수 없다(합치면 어느 쪽도 아닌 숫자가 된다).
 * ⚠️ total 이 0 이면 0% 로 둔다 — 0 으로 나눠 NaN 이 폭에 들어가면 막대가 통째로 사라진다.
 */
export function toBars(scope: IndustryScope): MixBar[] {
  const total = scope.total;
  return scope.cats.map((c) => ({
    ...c,
    pct: total > 0 ? (c.n / total) * 100 : 0,
  }));
}

/**
 * 셀렉트에 채울 대분류 목록.
 *
 * 서버는 스코프마다 그 스코프에 **있는** 업종만 준다. 상권에는 있고 반경에는 없는 업종이
 * 실제로 있으므로(반대도 마찬가지) 한쪽만 보면 고를 수 없는 업종이 생긴다 — 전부 합친다.
 *
 * ⚠️ 정렬에 쓰는 수는 **여러 스코프의 합**이라 어느 스코프의 점포 수도 아니다. 고르는
 *    차례를 정하는 데만 쓰고 **화면에 적지 않는다**(적으면 겹쳐 센 수를 사실처럼 보여주게 된다).
 */
export function catOptions(mix: IndustryMix): Array<{ cd: string; nm: string | null }> {
  const seen = new Map<string, { cd: string; nm: string | null; rank: number }>();

  const absorb = (cats: IndustryCat[]) => {
    for (const c of cats) {
      const prev = seen.get(c.cd);
      if (prev) {
        prev.rank += c.n;
        // 이름은 먼저 온 것을 지킨다. 다만 앞이 비어 있었으면 채운다.
        if (prev.nm === null) prev.nm = c.nm;
      } else {
        seen.set(c.cd, { cd: c.cd, nm: c.nm, rank: c.n });
      }
    }
  };

  for (const d of mix.districts) absorb(d.cats);
  if (mix.radius) absorb(mix.radius.cats);

  return [...seen.values()]
    .sort((a, b) => b.rank - a.rank || a.cd.localeCompare(b.cd))
    .map(({ cd, nm }) => ({ cd, nm }));
}

/**
 * 서버 응답의 **모양**을 확인한다.
 *
 * ⛔ 곁다리 섹션 하나가 렌더 중에 터지면 **층별 화면이 통째로 오류 안내로 바뀐다.**
 *    타입 단언(`as IndustryMix`)은 컴파일 때만 사는 약속이라 런타임에는 아무것도 막아
 *    주지 않는다 — 실제로 막는 것은 이 검사뿐이다.
 *    ⓘ **정정 2026-09-01**: 이 주석은 원래 "이 레포에는 ErrorBoundary 가 하나도 없다"로
 *      시작했는데, 2026-08-24(결정 0016)에 그물이 **셋** 생겼다(`main.tsx` · 지도 · 층별
 *      화면). 그래도 이 검사가 덜 중요해지지는 않는다 — 그물은 **터진 뒤** 하얀 화면만
 *      면하게 해 줄 뿐이고, 사용자가 보려던 층별 화면은 그 순간 통째로 사라진다.
 *      여기서 걸러 내면 **그 섹션 하나만 조용히 빠지고 나머지는 그대로 보인다.**
 *
 * 무엇이 들어올 수 있나: 마이그레이션 적용 전 라이브의 오류 객체, 옛 판 함수의 응답,
 * 다른 함수의 응답(목이 갈라 답하지 않으면 실제로 이런 일이 난다).
 *
 * ⚠️ 칸(cats) 하나하나까지 본다. `n` 이 숫자가 아니면 `n.toLocaleString()` 에서 터지고,
 *    그건 곧 화이트스크린이다.
 */
export function isCat(x: unknown): x is IndustryCat {
  if (typeof x !== 'object' || x === null) return false;
  const c = x as Record<string, unknown>;
  return (
    typeof c.cd === 'string' &&
    typeof c.n === 'number' &&
    (c.nm === null || c.nm === undefined || typeof c.nm === 'string')
  );
}

export function isScope(x: unknown): x is IndustryScope {
  if (typeof x !== 'object' || x === null) return false;
  const s = x as Record<string, unknown>;
  return typeof s.total === 'number' && Array.isArray(s.cats) && s.cats.every(isCat);
}

/**
 * 상권 한 묶음. 스코프에 이름표가 붙은 것이라 스코프 조건을 그대로 물려받는다.
 * `district_id` 는 화면이 key 로 쓰므로 문자열이라야 한다.
 */
export function isDistrict(x: unknown): x is IndustryDistrict {
  if (!isScope(x)) return false;
  return typeof (x as unknown as Record<string, unknown>).district_id === 'string';
}

/**
 * ⚠️ `radius` 는 **null 이어도 정상**이다 — "필지 좌표가 없어 못 쟀다"는 뜻이라 빈 집계와
 *    구분해야 한다. 여기서 null 을 거르면 그 뜻이 통째로 사라진다.
 */
function hasCommonShape(x: unknown): boolean {
  if (typeof x !== 'object' || x === null) return false;
  const m = x as Record<string, unknown>;
  if (typeof m.radius_m !== 'number') return false;
  if (!Array.isArray(m.districts) || !m.districts.every(isDistrict)) return false;
  return m.radius === null || isScope(m.radius);
}

export function isIndustryMix(x: unknown): x is IndustryMix {
  return hasCommonShape(x);
}

/** 상세는 위에 더해 `cat_l_cd` 가 있어야 한다 — 늦게 온 답을 버리는 유일한 근거다. */
export function isIndustryDetail(x: unknown): x is IndustryDetail {
  if (!hasCommonShape(x)) return false;
  return typeof (x as Record<string, unknown>).cat_l_cd === 'string';
}

/**
 * 상권 이름표 한 줄('강남역(발달상권)').
 *
 * 이름이 없으면 그 자리를 비워 두지 않는다 — 빈 제목은 "상권이 아닌 무언가"처럼 읽힌다.
 */
export function districtLabel(d: IndustryDistrict): string {
  const name = d.name || '(이름 없는 상권)';
  return d.type ? `${name}(${d.type})` : name;
}

/**
 * 화면에 밝힐 출처 목록. 서버가 상권마다 실어 보낸 것을 중복 없이 모은다.
 *
 * ⛔ 문구를 화면에 글자로 박지 않는다 — 소스가 둘이 된 순간(서울시 + 소상공인시장진흥공단)
 *    코드를 한 줄도 안 고쳤는데 한쪽이 거짓말이 된다(상권 줄·지도와 같은 원칙).
 */
export function districtSources(districts: IndustryDistrict[]): string[] {
  const out = new Set<string>();
  for (const d of districts) if (d.source_nm) out.add(d.source_nm);
  return [...out].sort();
}

// ── 업종별 층 분포 (물결 2-2 · 결정 0036 결정 18 ⑲~㉑) ─────────────────────────

/** 층 묶음의 화면 차례 — 지하부터 위로, 층 미상은 맨 끝. 서버는 열쇠만 주고 차례는 여기서 정한다. */
export const FLOOR_BAND_ORDER = ['b', '1', '2', '3+', 'na'] as const;

export const FLOOR_BAND_LABELS: Record<(typeof FLOOR_BAND_ORDER)[number], string> = {
  b: '지하',
  '1': '1층',
  '2': '2층',
  '3+': '3층 이상',
  na: '층 미상',
};

/** 0 이상 정수인가 — 개수 칸 하나. */
function isCount(x: unknown): x is number {
  return typeof x === 'number' && Number.isInteger(x) && x >= 0;
}

/**
 * 한 범위의 층 묶음 — total 과 열쇠 다섯이 전부 0 이상 정수여야 한다.
 * ⚠️ 열쇠 하나라도 빠지면 거른다 — 빠진 묶음을 0 으로 채우면 "모르는 것"을 "없음"이라 적게 된다.
 */
export function isFloorScope(x: unknown): x is IndustryFloorScope {
  if (typeof x !== 'object' || x === null) return false;
  const s = x as Record<string, unknown>;
  if (!isCount(s.total)) return false;
  if (typeof s.bands !== 'object' || s.bands === null) return false;
  const bands = s.bands as Record<string, unknown>;
  return FLOOR_BAND_ORDER.every((k) => isCount(bands[k]));
}

/**
 * 응답 모양 검사. 걸리면 **이 응답 하나만** 버린다 — 층 줄만 빠지고 카드·상세는 그대로 선다.
 * `radius` 는 null 이어도 정상(좌표가 없어 못 잼 — 빈 집계와 다르다).
 */
export function isIndustryFloors(x: unknown): x is IndustryFloors {
  if (typeof x !== 'object' || x === null) return false;
  const m = x as Record<string, unknown>;
  if (typeof m.radius_m !== 'number' || typeof m.cat_l_cd !== 'string') return false;
  if (!(m.cat_m_cds === null || (Array.isArray(m.cat_m_cds) && m.cat_m_cds.every((c) => typeof c === 'string')))) {
    return false;
  }
  if (!Array.isArray(m.districts)) return false;
  const districtsOk = m.districts.every(
    (d) => isFloorScope(d) && typeof (d as unknown as Record<string, unknown>).district_id === 'string',
  );
  if (!districtsOk) return false;
  return m.radius === null || isFloorScope(m.radius);
}

/** 중분류 목록 둘이 같은 질문인가(순서 무관 · null 은 null 하고만 같다) — 늦게 온 답을 버릴 때 쓴다. */
export function sameCatMs(a: readonly string[] | null, b: readonly string[] | null): boolean {
  if (a === null || b === null) return a === b;
  return [...a].sort().join(',') === [...b].sort().join(',');
}

/** 블록 열쇠(상권 `district_id` · 반경 `__radius__`) → 그 범위의 층 묶음. */
export function floorScopeByKey(floors: IndustryFloors | null): Map<string, IndustryFloorScope> {
  const out = new Map<string, IndustryFloorScope>();
  if (floors === null) return out;
  for (const d of floors.districts) out.set(d.district_id, d);
  if (floors.radius) out.set('__radius__', floors.radius);
  return out;
}

/**
 * 층 줄 한 줄 — `층별 음식: 지하 4곳 · 1층 700곳 · 2층 150곳 · 3층 이상 80곳 · 층 미상 300곳 (24%)`.
 *
 * ⛔ 층 미상은 숨기지 않는다 — 같은 줄의 한 칸 + 괄호 %(그 범위 총수 대비). 빼면 남은 넷이 전부처럼 읽힌다.
 * total 이 0 이면 null — 줄을 안 그린다("0곳"만 늘어선 줄은 위 "가게가 없습니다"와 같은 말을 두 번 한다).
 */
export function floorLine(label: string, scope: IndustryFloorScope): string | null {
  if (scope.total <= 0) return null;
  const n = (v: number) => v.toLocaleString('ko-KR');
  const parts = FLOOR_BAND_ORDER.map((k) => `${FLOOR_BAND_LABELS[k]} ${n(scope.bands[k])}곳`);
  const naPct = Math.round((100 * scope.bands.na) / scope.total);
  return `층별 ${label}: ${parts.join(' · ')} (${naPct}%)`;
}

// ── 업종 비중 비교 (물결 2-3 · 결정 0036 결정 18 ㉓~㉖) ─────────────────────────
//
// ⛔ 숫자만 나란히 — 많다·적다·높다·낮다·%p 차이·배수를 쓰지 않는다(👤 ㉕ · 판단처럼 읽히면 안 된다).
// ⛔ 30(점포 기준)은 서버 `min_total` 값을 쓴다 — 여기 30 을 박지 않는다.
// ⛔ 지역 이름은 서버가 안 준다 — `sido_cd` 로 `SIDOS` 에서 찾고, 없으면 지역 글자를 뺀다.

/** 비교 글 옆 배지 — 사실(A)이 아니라 견줄 숫자(C)다(상세계획 §7.4 C·D 시각 구분). */
export const MEDIAN_BADGE = 'C등급 · 비교값';

/** 시·도 코드 두 자리 → 짧은 이름('서울'). 표에 없으면 null(그때는 지역 글자를 뺀다). */
export function sidoNameOf(code: string): string | null {
  return SIDOS.find((s) => s.code === code)?.name ?? null;
}

/** 모집단의 이름 — 같은 종류면 그 종류 이름(DB 값 그대로), 시·도 전체면 '상권 전체'. */
function popKind(pop: IndustryMedianPop): string {
  return pop.scope === 'type' && pop.district_type ? pop.district_type : '상권 전체';
}

function popWho(sidoName: string | null, pop: IndustryMedianPop): string {
  return sidoName ? `${sidoName} ${popKind(pop)}` : popKind(pop);
}

/** 막대 줄 아래 둘째 줄 — `서울 골목상권 가운데 25.0%` · `서울 상권 전체 가운데 25.9%` · `대전 주요상권 가운데 36.2%`. */
export function medianLine(sidoName: string | null, pop: IndustryMedianPop, medPct: number): string {
  return `${popWho(sidoName, pop)} 가운데 ${medPct.toFixed(1)}%`;
}

/** 블록 머리 아래 설명 한 줄(배지 뒤에 붙는 글) — 모집단 곳 수와 30(서버 값)을 밝힌다(절대 규칙 3 표본 병기). */
export function medianNote(sidoName: string | null, pop: IndustryMedianPop, minTotal: number): string {
  const n = (v: number) => v.toLocaleString('ko-KR');
  return (
    `가운데값은 ${popWho(sidoName, pop)} ${n(pop.n)}곳(점포 ${n(minTotal)}곳 이상 상권)의 업종 비중을 ` +
    `크기순으로 세웠을 때 한가운데 값입니다 — 비교용 숫자입니다.`
  );
}

/**
 * 이 상권 점포가 기준에 못 미칠 때의 사실 한 줄 — `점포 12곳 — 30곳이 안 돼 비교값은 적지 않습니다.`
 * 0곳이면 null(블록에 이미 '등록된 점포가 없습니다'가 선다 — 같은 말을 두 번 하지 않는다) · 기준 이상이면 null.
 */
export function medianTooSmall(total: number, minTotal: number): string | null {
  if (total <= 0 || total >= minTotal) return null;
  const n = (v: number) => v.toLocaleString('ko-KR');
  return `점포 ${n(total)}곳 — ${n(minTotal)}곳이 안 돼 비교값은 적지 않습니다.`;
}

function isPosInt(x: unknown): x is number {
  return typeof x === 'number' && Number.isInteger(x) && x > 0;
}

function isMedianPop(x: unknown): x is IndustryMedianPop {
  if (typeof x !== 'object' || x === null) return false;
  const p = x as Record<string, unknown>;
  if (typeof p.sido_cd !== 'string' || !isPosInt(p.n)) return false;
  // 같은 종류(type)면 종류 이름이 있어야 한다 — 없으면 'null 가운데' 같은 글이 선다.
  if (p.scope === 'type') return typeof p.district_type === 'string' && p.district_type !== '';
  return p.scope === 'all' && p.district_type === null;
}

function isMedianCat(x: unknown): boolean {
  if (typeof x !== 'object' || x === null) return false;
  const c = x as Record<string, unknown>;
  return (
    typeof c.cd === 'string' &&
    (c.nm === null || c.nm === undefined || typeof c.nm === 'string') &&
    typeof c.med_pct === 'number' &&
    Number.isFinite(c.med_pct) &&
    c.med_pct >= 0 &&
    c.med_pct <= 100
  );
}

/**
 * 응답 모양 검사. 걸리면 **이 응답 통째로** 버린다 — 비교 글·설명 줄만 없고 카드·막대·총수는 그대로 선다.
 * ⓘ pop 이 null 이면 cats 는 비어 있어야 한다(서버 약속 — 어긋나면 그 응답을 믿지 않는다).
 */
export function isIndustryMedian(x: unknown): x is IndustryMedian {
  if (typeof x !== 'object' || x === null) return false;
  const m = x as Record<string, unknown>;
  if (!(m.snapshot_ym === null || typeof m.snapshot_ym === 'string')) return false;
  if (!isPosInt(m.min_total) || !isPosInt(m.min_pop)) return false;
  if (!Array.isArray(m.districts)) return false;
  return m.districts.every((d) => {
    if (typeof d !== 'object' || d === null) return false;
    const r = d as Record<string, unknown>;
    if (typeof r.district_id !== 'string' || !isCount(r.total)) return false;
    if (!(r.type === null || typeof r.type === 'string')) return false;
    if (!Array.isArray(r.cats) || !r.cats.every(isMedianCat)) return false;
    if (r.pop === null) return r.cats.length === 0;
    return isMedianPop(r.pop);
  });
}

/** 상권 블록 하나에 붙일 글 묶음. */
export type MedianView = {
  /** 대분류 코드 → 그 줄 둘째 줄 글. 없는 코드는 그 줄만 비교 글 없음. */
  lines: Map<string, string>;
  /** 블록 머리 아래 설명(배지 뒤 글) — 모집단이 있을 때만. */
  note: string | null;
  /** 점포가 기준 미만일 때의 사실 한 줄. */
  tooSmall: string | null;
};

/**
 * 응답에서 상권 하나의 글 묶음을 만든다. 그 상권 줄이 응답에 없으면 null(비교 글 0 — 서버가 모집단을 못 골랐다).
 * ⛔ 분기가 업종 분포와 다르면(`mixYm` ≠ 응답 분기) 통째로 null — 막대와 비교 글이 서로 다른 분기를 말하지 않게.
 */
export function medianViewOf(
  median: IndustryMedian | null,
  districtId: string,
  mixYm: string | null,
): MedianView | null {
  if (median === null || median.snapshot_ym !== mixYm) return null;
  const d = median.districts.find((x) => x.district_id === districtId);
  if (!d) return null;
  if (d.pop === null) {
    const tooSmall = medianTooSmall(d.total, median.min_total);
    return tooSmall === null ? null : { lines: new Map(), note: null, tooSmall };
  }
  const pop = d.pop;
  const sido = sidoNameOf(pop.sido_cd);
  const lines = new Map<string, string>();
  for (const c of d.cats) lines.set(c.cd, medianLine(sido, pop, c.med_pct));
  return { lines, note: medianNote(sido, pop, median.min_total), tooSmall: null };
}
