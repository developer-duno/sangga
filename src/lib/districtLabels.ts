import { pointInPolygon, polygonsOf } from './geo';
import type { DistrictGeometry, Ring } from '../types';

/**
 * 지도 위 상권 **이름표**의 자리와 켜는 시점.
 *
 * 두 가지만 정한다:
 *  ① **어디에 놓을까** — 면의 무게중심(신발끈 공식). ⛔ 사각 범위(bbox)의 한가운데를 쓰면
 *     ㄱ자로 굽은 상권에서 이름이 **면 밖 빈 자리**에 뜬다(굽은 안쪽이 상권이 아닌데도
 *     그 한복판이 사각형의 중심이 되기 때문이다). 골목상권은 길을 따라 굽은 모양이 흔하다.
 *  ② **언제 켤까** — 한 단계 확대(level ≤ 5)부터. 처음 배율(6)에서는 한 구에 수십~수백 개가
 *     겹쳐 글자 죽이 되므로 색면과 범례만 보여 준다.
 *
 * ⚠️ GeoJSON 좌표는 **[경도, 위도]** 순서다(카카오는 {lat, lng}). 여기서는 GeoJSON 순서로
 *    계산하고 **돌려줄 때 한 번만** 뒤집는다 — 중간에서 뒤집으면 어느 쪽이 뒤집힌 값인지
 *    알 수 없게 된다.
 */

/**
 * 이름표를 켜는 확대 수준의 상한.
 *
 * 카카오 ROADMAP 은 1~14 이고 **숫자가 작을수록 확대**다. 지도의 첫 배율이 6 이므로
 * 5 는 "한 단계 확대한 순간"이다.
 */
export const LABEL_MAX_LEVEL = 5;

/** 지금 배율에서 이름표를 보일까. 처음 배율(6)에서는 끈다. */
export function showLabels(level: number): boolean {
  return level <= LABEL_MAX_LEVEL;
}

/**
 * 고리 하나가 감싼 넓이(부호 있는 값의 두 배).
 *
 * 신발끈 공식 그대로다. 부호는 고리를 도는 방향(시계/반시계)에 따라 갈리므로 **크기를
 * 견줄 때는 절댓값**을 쓴다. 단위는 도(°)의 제곱이라 실제 면적(㎡)이 아니지만, 우리는
 * **같은 상권 안 조각끼리 큰 쪽을 고르는 데만** 쓰므로 단위가 무엇이든 상관없다.
 */
function doubleAreaOf(ring: Ring): number {
  let sum = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    sum += xj * yi - xi * yj;
  }
  return sum;
}

/**
 * 고리의 무게중심.
 *
 * 넓이가 0인 고리(한 점·한 줄로 찌부러진 것)는 null 이다 — 나눗셈이 무너지기도 하고,
 * 애초에 **면으로 그려지지 않는** 것이라 이름표를 달 자리가 없다.
 */
function centroidOf(ring: Ring): { x: number; y: number } | null {
  const a2 = doubleAreaOf(ring);
  if (a2 === 0) return null;

  let cx = 0;
  let cy = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const w = xj * yi - xi * yj;
    cx += (xi + xj) * w;
    cy += (yi + yj) * w;
  }
  return { x: cx / (3 * a2), y: cy / (3 * a2) };
}

/**
 * 위도 y 를 지나는 가로줄이 테두리를 넘는 지점들의 경도.
 *
 * ⚠️ 구멍 고리까지 **함께** 넣는다. 그러면 정렬한 지점들을 앞에서부터 둘씩 묶은 구간
 *    (0-1, 2-3, …)이 곧 "면 안"이 된다(홀짝 규칙) — 구멍은 저절로 빠진다.
 *    셈 자체는 `geo.ts` 의 `pointInRing` 과 같은 식이지만, 그쪽은 **몇 번 넘었나(홀짝)**
 *    를 돌려주고 여기는 **어디서 넘었나(좌표)** 가 필요해 따로 둔다.
 */
function crossingsAt(rings: Ring[], y: number): number[] {
  const xs: number[] = [];
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      if (yi > y !== yj > y) xs.push(((xj - xi) * (y - yi)) / (yj - yi) + xi);
    }
  }
  return xs.sort((a, b) => a - b);
}

/**
 * 그 위도에서 면이 가장 넓게 이어지는 구간의 한가운데.
 *
 * 무게중심이 면 밖으로 나갔을 때(아래 참조) 물러설 자리다. 어디에도 못 앉히면 null.
 */
function widestInsideX(rings: Ring[], y: number): number | null {
  const xs = crossingsAt(rings, y);
  let best: number | null = null;
  let bestWidth = 0;
  for (let i = 0; i + 1 < xs.length; i += 2) {
    const width = xs[i + 1] - xs[i];
    if (width > bestWidth) {
      bestWidth = width;
      best = (xs[i] + xs[i + 1]) / 2;
    }
  }
  return best;
}

/**
 * 이름표를 놓을 자리. 그릴 수 없는 도형이면 null 이다(그때는 이름표를 안 단다).
 *
 * ① **떨어진 두 덩이(MultiPolygon)면 큰 쪽**에만 단다. 작은 조각까지 달면 같은 이름이
 *    두 번 뜬다 — 지도에서 그건 상권이 둘이라는 뜻으로 읽힌다.
 * ② 그 조각의 **무게중심**을 쓴다.
 * ③ ⚠️ **무게중심이 면 밖일 수 있다.** 팔이 가는 ㄱ자(길을 따라 굽은 골목상권)에서는
 *    무게가 굽은 안쪽 빈 자리로 쏠린다 — 무게중심은 "면 안"을 보장하는 값이 아니다.
 *    그래서 나온 자리가 실제로 면 안인지 **확인하고**(구멍도 함께 본다), 밖이면 그 위도에서
 *    면이 가장 넓은 구간의 한가운데로 옮긴다. 이 확인을 빼면 대부분 잘 맞다가 굽은 상권
 *    몇 개에서만 이름이 남의 자리에 뜬다 — 눈으로만 잡히는 종류의 결함이다.
 */
export function labelPointOf(geom: DistrictGeometry): { lat: number; lng: number } | null {
  let best: Ring[] | null = null;
  let bestArea = -1;
  for (const rings of polygonsOf(geom)) {
    const outer = rings[0];
    if (!outer || outer.length === 0) continue;
    const area = Math.abs(doubleAreaOf(outer));
    if (area > bestArea) {
      bestArea = area;
      best = rings;
    }
  }
  if (!best) return null;

  const c = centroidOf(best[0]);
  if (!c) return null;
  if (pointInPolygon(c.x, c.y, best)) return { lat: c.y, lng: c.x };

  const x = widestInsideX(best, c.y);
  return x === null ? null : { lat: c.y, lng: x };
}
