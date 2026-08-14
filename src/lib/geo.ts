import type { DistrictFeature, DistrictGeometry, Ring } from '../types';

/**
 * 도형 판정 도구 — "지도에서 누른 점이 어느 상권 안인가"를 우리가 직접 센다.
 *
 * ⛔ 카카오 Polygon 의 개별 click 이벤트를 쓰지 않는 이유:
 *    상권은 서로 겹친다(한 자리가 발달상권이면서 골목상권일 수 있다). 겹친 면을 클릭하면
 *    **맨 위 하나만** 이벤트를 받으므로, 그걸 쓰면 화면이 "이 자리의 상권은 하나"라고
 *    말하게 된다. #51 의 "속한 상권"은 겹치면 **전부** 나열하는데, 한 화면 안에서 겹침을
 *    두 가지로 다루면 사용자가 헷갈린다(결정 0010 §5). 그래서 맵 클릭 한 번을 받아
 *    1,687개(한 구는 수십~수백 개)를 우리가 훑는다 — 그 정도는 눈 깜짝할 새다.
 */

/**
 * 한 고리(닫힌 선) 안에 점이 있는가 — ray casting.
 *
 * 점에서 오른쪽으로 반직선을 쏴서 테두리를 몇 번 지나는지 센다. 홀수면 안, 짝수면 밖이다.
 * 구멍이 있는 도형도 이 셈 하나로 풀린다(구멍 테두리를 한 번 더 지나므로 짝수가 된다) —
 * 다만 우리 자료는 구멍이 별도 고리로 오므로 pointInPolygon 이 명시적으로 뺀다.
 *
 * ⚠️ **경계선 위의 점**은 왼쪽·아래를 안, 오른쪽·위를 밖으로 본다(반열림 규칙).
 *    맞닿은 두 면이 그 선을 공유할 때 한 점이 양쪽에 다 들거나 어디에도 안 드는 일을
 *    막는 표준 관례다. 상권 경계는 도로 한가운데를 지나는 일이 많아 실제로 일어난다.
 *
 * @param lng 경도(x)  @param lat 위도(y)
 */
export function pointInRing(lng: number, lat: number, ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    // 이 변이 점의 위도를 가로지르는가 → 가로지를 때만 교차점 x 를 구한다.
    // (yi > lat) !== (yj > lat) 는 위쪽 끝을 배제하는 반열림 비교다.
    if (yi > lat !== yj > lat) {
      const cross = ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
      if (lng < cross) inside = !inside;
    }
  }
  return inside;
}

/**
 * 폴리곤 하나(바깥 테두리 + 구멍들) 안에 점이 있는가.
 *
 * GeoJSON 은 첫 고리가 바깥, 나머지가 구멍이다. 구멍 안이면 밖으로 본다 —
 * 구멍을 무시하면 "상권 한가운데 뚫린 공원"이 상권 안이라고 나온다.
 */
export function pointInPolygon(lng: number, lat: number, rings: Ring[]): boolean {
  if (rings.length === 0 || !pointInRing(lng, lat, rings[0])) return false;
  for (let i = 1; i < rings.length; i += 1) {
    if (pointInRing(lng, lat, rings[i])) return false;
  }
  return true;
}

/** 폴리곤 목록으로 펼친다 — Polygon 은 1개, MultiPolygon 은 여러 개다(한 상권이 떨어진 두 덩이). */
export function polygonsOf(geom: DistrictGeometry): Ring[][] {
  return geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates;
}

/** 상권 도형(Polygon·MultiPolygon) 안에 점이 있는가. 조각 중 하나라도 품으면 안이다. */
export function pointInGeometry(lng: number, lat: number, geom: DistrictGeometry): boolean {
  return polygonsOf(geom).some((rings) => pointInPolygon(lng, lat, rings));
}

/** 남서–북동 두 점으로 나타낸 사각 범위. */
export type Bounds = { swLat: number; swLng: number; neLat: number; neLng: number };

/**
 * 여러 상권을 한눈에 담는 범위. 하나도 없으면 null 이다
 * (그때는 지도를 어디로 맞출지 알 수 없으므로 손대지 않는다).
 */
export function boundsOf(features: DistrictFeature[]): Bounds | null {
  let swLat = Infinity;
  let swLng = Infinity;
  let neLat = -Infinity;
  let neLng = -Infinity;

  for (const f of features) {
    for (const rings of polygonsOf(f.geometry)) {
      // 바깥 테두리만 보면 된다 — 구멍은 언제나 그 안이다.
      for (const [lng, lat] of rings[0] ?? []) {
        if (lng < swLng) swLng = lng;
        if (lng > neLng) neLng = lng;
        if (lat < swLat) swLat = lat;
        if (lat > neLat) neLat = lat;
      }
    }
  }

  if (swLat === Infinity) return null;
  return { swLat, swLng, neLat, neLng };
}

/**
 * GeoJSON 고리들을 카카오 Polygon 의 path 모양으로 바꾼다.
 *
 * 좌표 순서가 서로 반대라 여기서 한 번에 뒤집는다 — GeoJSON 은 [경도, 위도],
 * 카카오는 {lat, lng} 이다. 이 변환을 컴포넌트에 흩뿌리면 한 군데서 뒤집는 것을
 * 잊는 날 도형이 지구 반대편(바다 한가운데)에 그려진다.
 */
export function ringsToPath(rings: Ring[]): { lat: number; lng: number }[][] {
  return rings.map((ring) => ring.map(([lng, lat]) => ({ lat, lng })));
}
