import { describe, it, expect } from 'vitest';
import { LABEL_MAX_LEVEL, labelPointOf, showLabels } from './districtLabels';
import { pointInGeometry } from './geo';
import type { DistrictGeometry, Ring } from '../types';

/**
 * 지도 상권 이름표 — 자리 잡기와 켜는 시점.
 *
 * 여기서 지키는 것은 둘이다:
 *  ① 이름표는 **그 상권 면 안**에 앉는다(굽은 상권·구멍 뚫린 상권 포함)
 *  ② 처음 배율에서는 안 켜고 **한 단계 확대부터** 켠다
 *
 * ⚠️ 좌표는 GeoJSON 순서([경도, 위도])로 적고, 돌려받는 값은 카카오 순서({lat, lng})다.
 */

/** 닫힌 사각 고리 하나. 좌표는 GeoJSON 순서다. */
function box(west: number, south: number, east: number, north: number): Ring {
  return [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
    [west, south],
  ];
}

/** 도형이 실제로 그 점을 품는지 — 판정은 지도 클릭과 **같은 셈**(geo.ts)으로 한다. */
function contains(geom: DistrictGeometry, at: { lat: number; lng: number }): boolean {
  return pointInGeometry(at.lng, at.lat, geom);
}

describe('showLabels — 켜는 시점', () => {
  it('처음 배율(6)에서는 안 켠다 — 한 구에 수십 개가 겹쳐 글자 죽이 된다', () => {
    expect(showLabels(6)).toBe(false);
    expect(showLabels(7)).toBe(false);
    expect(showLabels(14)).toBe(false);
  });

  it('한 단계 확대(5)부터 켠다 — 더 당겨도 계속 켜져 있다', () => {
    expect(showLabels(5)).toBe(true);
    expect(showLabels(4)).toBe(true);
    expect(showLabels(1)).toBe(true);
  });

  it('경계값은 상수 하나로 정해져 있다 — 화면과 시험이 각자 숫자를 들고 있지 않다', () => {
    expect(LABEL_MAX_LEVEL).toBe(5);
    expect(showLabels(LABEL_MAX_LEVEL)).toBe(true);
    expect(showLabels(LABEL_MAX_LEVEL + 1)).toBe(false);
  });
});

describe('labelPointOf — 이름표 자리', () => {
  it('네모난 상권은 한가운데', () => {
    const geom: DistrictGeometry = { type: 'Polygon', coordinates: [box(127.0, 37.5, 127.1, 37.6)] };
    const at = labelPointOf(geom);
    expect(at).not.toBeNull();
    expect(at?.lng).toBeCloseTo(127.05, 6);
    expect(at?.lat).toBeCloseTo(37.55, 6);
  });

  it('치우친 상권은 **무게** 쪽에 앉는다 — 사각 범위의 한가운데가 아니다', () => {
    // 밑변이 넓고 위로 갈수록 좁아지는 삼각형. 사각 범위(bbox)의 한가운데도 면 **안**이라
    // "면 안이냐"만 봐서는 두 방식이 갈리지 않는다 — 그래서 자리를 값으로 못박는다.
    const tri: Ring = [
      [127.0, 37.5],
      [127.4, 37.5],
      [127.1, 37.6],
      [127.0, 37.5],
    ];
    const geom: DistrictGeometry = { type: 'Polygon', coordinates: [tri] };
    const at = labelPointOf(geom);

    // 삼각형의 무게중심 = 꼭짓점 평균.
    expect(at?.lng).toBeCloseTo((127.0 + 127.4 + 127.1) / 3, 6);
    expect(at?.lat).toBeCloseTo((37.5 + 37.5 + 37.6) / 3, 6);
    // 사각 범위의 한가운데(127.2, 37.55)도 면 안이지만 **다른 자리**다 — 그걸 쓰면 위 값이 깨진다.
    expect(contains(geom, { lat: 37.55, lng: 127.2 })).toBe(true);
  });

  it('ㄱ자로 굽은 상권도 면 안에 앉는다', () => {
    // 아래로 넓고 왼쪽으로 솟은 ㄱ자. 사각 범위(bbox)의 한가운데는 (127.05, 37.55)인데
    // 그 자리는 **오려낸 빈 구석**이라 이름이 남의 자리에 뜬다.
    const el: Ring = [
      [127.0, 37.5],
      [127.1, 37.5],
      [127.1, 37.54],
      [127.04, 37.54],
      [127.04, 37.6],
      [127.0, 37.6],
      [127.0, 37.5],
    ];
    const geom: DistrictGeometry = { type: 'Polygon', coordinates: [el] };
    const at = labelPointOf(geom);

    expect(at).not.toBeNull();
    expect(contains(geom, at!)).toBe(true);
    // 사각 범위의 한가운데(빈 구석)를 그대로 쓴 것이 아님을 못박는다.
    expect(contains(geom, { lat: 37.55, lng: 127.05 })).toBe(false);
  });

  it('팔이 가는 ㄱ자 — 무게중심이 면 밖으로 나가는 모양에서도 면 안에 앉는다', () => {
    // 팔이 가늘면 무게가 굽은 안쪽 빈 자리로 쏠려 **무게중심 자체가 면 밖**이다.
    // 무게중심만 믿고 확인을 빼면 여기서 이름이 상권 밖에 뜬다.
    const thin: Ring = [
      [127.0, 37.5],
      [127.1, 37.5],
      [127.1, 37.51],
      [127.01, 37.51],
      [127.01, 37.6],
      [127.0, 37.6],
      [127.0, 37.5],
    ];
    const geom: DistrictGeometry = { type: 'Polygon', coordinates: [thin] };
    const at = labelPointOf(geom);

    expect(at).not.toBeNull();
    expect(contains(geom, at!)).toBe(true);
  });

  it('한가운데가 뚫린 상권은 구멍을 피한다', () => {
    const geom: DistrictGeometry = {
      type: 'Polygon',
      coordinates: [box(127.0, 37.5, 127.1, 37.6), box(127.04, 37.54, 127.06, 37.56)],
    };
    const at = labelPointOf(geom);

    expect(at).not.toBeNull();
    expect(contains(geom, at!)).toBe(true);
  });

  it('떨어진 두 덩이는 **큰 쪽**에만 단다 — 같은 이름이 두 번 뜨면 상권이 둘로 읽힌다', () => {
    const big = box(127.0, 37.5, 127.1, 37.6);
    const small = box(127.3, 37.3, 127.31, 37.31);
    const geom: DistrictGeometry = { type: 'MultiPolygon', coordinates: [[small], [big]] };

    const at = labelPointOf(geom);
    // 파일 순서와 무관하게(작은 조각이 먼저 와도) 넓은 쪽이 이긴다.
    expect(at?.lng).toBeCloseTo(127.05, 6);
    expect(at?.lat).toBeCloseTo(37.55, 6);
  });

  it('그릴 수 없는 도형이면 자리도 없다 — 0,0 같은 가짜 좌표를 만들지 않는다', () => {
    expect(labelPointOf({ type: 'MultiPolygon', coordinates: [] })).toBeNull();
    expect(labelPointOf({ type: 'Polygon', coordinates: [[]] })).toBeNull();
  });

  it('찌부러진 고리(한 줄)에는 안 단다 — 0으로 나눈 값(NaN)을 좌표라고 내놓지 않는다', () => {
    const line: Ring = [
      [127.0, 37.5],
      [127.2, 37.5],
      [127.0, 37.5],
    ];
    expect(labelPointOf({ type: 'Polygon', coordinates: [line] })).toBeNull();
  });
});
