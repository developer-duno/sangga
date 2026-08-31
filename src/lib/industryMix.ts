import type {
  IndustryCat,
  IndustryDetail,
  IndustryDistrict,
  IndustryMix,
  IndustryScope,
} from '../types';

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
