import { describe, it, expect } from 'vitest';
import { boundsOf, pointInGeometry, pointInPolygon, pointInRing, polygonsOf, ringsToPath } from './geo';
import type { DistrictFeature, DistrictGeometry, Ring } from '../types';

/**
 * 도형 판정 테스트.
 *
 * 이 판정이 틀리면 지도에서 누른 자리의 상권 목록이 틀린다 — 그런데 **에러가 안 난다.**
 * 그럴듯한 목록이 나와서 눈으로는 못 잡는다. 그래서 구멍·여러 덩이·경계선까지 못박는다.
 *
 * ⚠️ 좌표는 GeoJSON 순서(경도, 위도)다. 함수 인자도 (lng, lat) 순이다 — 뒤집으면
 *    서울 상권이 남태평양에 그려진다.
 */

/** (0,0)–(10,10) 정사각형. 좌표는 [경도, 위도]. */
const SQUARE: Ring = [
  [0, 0],
  [10, 0],
  [10, 10],
  [0, 10],
  [0, 0],
];

/** 위 정사각형 한가운데의 (4,4)–(6,6) 구멍. */
const HOLE: Ring = [
  [4, 4],
  [6, 4],
  [6, 6],
  [4, 6],
  [4, 4],
];

/** (20,20)–(30,30) 두 번째 덩이 — MultiPolygon 검사용. */
const FAR_SQUARE: Ring = [
  [20, 20],
  [30, 20],
  [30, 30],
  [20, 30],
  [20, 20],
];

describe('pointInRing — 고리 하나', () => {
  it('안은 안, 밖은 밖이다', () => {
    expect(pointInRing(5, 5, SQUARE)).toBe(true);
    expect(pointInRing(15, 5, SQUARE)).toBe(false);
    expect(pointInRing(5, 15, SQUARE)).toBe(false);
    expect(pointInRing(-1, 5, SQUARE)).toBe(false);
  });

  it('경계선은 왼쪽·아래가 안, 오른쪽·위가 밖이다(반열림 규칙)', () => {
    // ⚠️ 이 값들은 "그래야 옳다"가 아니라 **한 점이 두 번 세어지지 않게** 고른 규칙이다.
    //    상권 경계는 도로 한가운데를 지나 서로 맞닿는 일이 많아서, 규칙이 없으면
    //    맞닿은 두 상권이 같은 점을 둘 다 품거나 둘 다 안 품는다.
    expect(pointInRing(0, 5, SQUARE)).toBe(true); // 왼쪽 변
    expect(pointInRing(10, 5, SQUARE)).toBe(false); // 오른쪽 변
    expect(pointInRing(5, 0, SQUARE)).toBe(true); // 아래 변
    expect(pointInRing(5, 10, SQUARE)).toBe(false); // 위 변
  });

  it('꼭짓점에서도 규칙이 갈라지지 않는다', () => {
    expect(pointInRing(0, 0, SQUARE)).toBe(true); // 왼쪽·아래 모서리
    expect(pointInRing(10, 10, SQUARE)).toBe(false); // 오른쪽·위 모서리
  });

  it('첫 점과 끝 점이 안 닫혀 있어도 닫힌 것으로 본다', () => {
    // GeoJSON 은 닫아서 주지만, 굽는 쪽이 바뀌어 안 닫히더라도 답이 달라지면 안 된다.
    const open: Ring = SQUARE.slice(0, -1);
    expect(pointInRing(5, 5, open)).toBe(true);
    expect(pointInRing(15, 5, open)).toBe(false);
  });
});

describe('pointInPolygon — 구멍', () => {
  it('구멍 안은 밖으로 본다', () => {
    expect(pointInPolygon(5, 5, [SQUARE])).toBe(true); // 구멍이 없으면 안
    expect(pointInPolygon(5, 5, [SQUARE, HOLE])).toBe(false); // 구멍이 생기면 밖
  });

  it('구멍 밖·테두리 안은 여전히 안이다', () => {
    expect(pointInPolygon(1, 1, [SQUARE, HOLE])).toBe(true);
    expect(pointInPolygon(9, 9, [SQUARE, HOLE])).toBe(true);
  });

  it('고리가 하나도 없으면 밖이다', () => {
    expect(pointInPolygon(5, 5, [])).toBe(false);
  });
});

describe('pointInGeometry — Polygon · MultiPolygon', () => {
  const polygon: DistrictGeometry = { type: 'Polygon', coordinates: [SQUARE, HOLE] };
  const multi: DistrictGeometry = {
    type: 'MultiPolygon',
    coordinates: [[SQUARE, HOLE], [FAR_SQUARE]],
  };

  it('Polygon 은 그 하나만 본다', () => {
    expect(pointInGeometry(1, 1, polygon)).toBe(true);
    expect(pointInGeometry(25, 25, polygon)).toBe(false);
  });

  it('MultiPolygon 은 떨어진 덩이 중 하나만 품어도 안이다', () => {
    // 한 상권이 길 건너로 갈라진 경우다. 첫 덩이만 보면 두 번째 덩이가 통째로 사라진다.
    expect(pointInGeometry(1, 1, multi)).toBe(true);
    expect(pointInGeometry(25, 25, multi)).toBe(true);
    expect(pointInGeometry(5, 5, multi)).toBe(false); // 구멍은 덩이가 여럿이어도 구멍이다
    expect(pointInGeometry(15, 15, multi)).toBe(false); // 두 덩이 사이
  });

  it('polygonsOf 는 두 모양을 같은 형태로 펼친다', () => {
    expect(polygonsOf(polygon)).toHaveLength(1);
    expect(polygonsOf(multi)).toHaveLength(2);
  });
});

describe('boundsOf — 한눈에 담을 범위', () => {
  function feature(geometry: DistrictGeometry): DistrictFeature {
    return {
      type: 'Feature',
      geometry,
      properties: {
        district_id: 'x',
        district_nm: '테스트상권',
        district_type: '골목상권',
        source_nm: '테스트 출처',
        sigungu_code: '11680',
        area_m2: 1,
      },
    };
  }

  it('여러 상권을 전부 담는다', () => {
    const bounds = boundsOf([
      feature({ type: 'Polygon', coordinates: [SQUARE] }),
      feature({ type: 'MultiPolygon', coordinates: [[FAR_SQUARE]] }),
    ]);
    expect(bounds).toEqual({ swLng: 0, swLat: 0, neLng: 30, neLat: 30 });
  });

  it('구멍은 범위를 넓히지 않는다 — 언제나 테두리 안이다', () => {
    expect(boundsOf([feature({ type: 'Polygon', coordinates: [SQUARE, HOLE] })])).toEqual({
      swLng: 0,
      swLat: 0,
      neLng: 10,
      neLat: 10,
    });
  });

  it('상권이 하나도 없으면 null 이다 — 지도를 어디로 맞출지 모른다는 뜻', () => {
    expect(boundsOf([])).toBeNull();
  });
});

describe('ringsToPath — 좌표 순서 뒤집기', () => {
  it('[경도, 위도] 를 {lat, lng} 로 바꾼다', () => {
    // 서울시청 근처 값으로 확인한다 — 뒤집히면 위도 126도(북극 너머)가 되어 눈에 띈다.
    expect(ringsToPath([[[126.9784, 37.5665]]])).toEqual([[{ lat: 37.5665, lng: 126.9784 }]]);
  });

  it('구멍 고리도 함께 넘긴다 — 카카오 Polygon 이 그 순서를 그대로 쓴다', () => {
    expect(ringsToPath([SQUARE, HOLE])).toHaveLength(2);
  });
});
