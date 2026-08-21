import type { IndustryCat, IndustryDistrict, IndustryMix, IndustryScope } from '../types';

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
 * 한 스코프에서 고른 업종이 몇 곳인가 — "경쟁 카운트".
 *
 * ⚠️ 못 찾으면 0 이 아니라 **null** 이다. 아직 답이 안 왔을 때(로딩)와 정말 0곳일 때를
 *    화면이 갈라 말해야 하는데, 0 으로 뭉개면 "없다"고 단정하게 된다.
 */
export function scopeTotal(scope: IndustryScope | null | undefined): number | null {
  if (!scope) return null;
  return scope.total;
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
