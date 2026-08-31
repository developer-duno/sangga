import { describe, it, expect } from 'vitest';
import {
  hasMore,
  isDistrictLandList,
  isParcelBuildingList,
  landToHit,
  landsSummary,
  parcelBuildingToHit,
} from './districtBuildings';
import type { DistrictLand, ParcelBuilding } from '../types';

/**
 * 상권 → 건물 목록의 순수 계산.
 *
 * 여기서 막는 것은 **에러 없이 조용히 틀리는 종류**다. 실제로 틀릴 수 있는 자리는 넷이다.
 *
 *  ① 뜻밖의 서버 응답이 렌더까지 흘러간다 → 지도까지 함께 사라진다.
 *  ② 땅의 점포 수가 **건물의 것으로 둔갑**해 선택된 건물에 얹혀 흘러다닌다.
 *  ③ 잘렸다는 사실을 안 적어 "이 상권엔 50곳뿐"으로 읽힌다.
 *  ④ '더 보기'가 남아 있는데 눌러도 아무 일이 없다(또는 반대로 일찍 사라진다).
 */

function land(over: Partial<DistrictLand> = {}): DistrictLand {
  return {
    pnu: '1114011100100010000',
    store_cnt: 317,
    bld_cnt_in_pnu: 4,
    bld_id: '1114011100100010000_100312042',
    bld_nm: '롯데호텔 및 백화점',
    road_addr: '서울특별시 중구 남대문로 81',
    jibun_addr: '서울특별시 중구 소공동 1',
    lat: 37.5651,
    lng: 126.9815,
    floor_cnt: 43,
    min_floor: -7,
    max_floor: 35,
    has_roof: true,
    total_parcel_cnt: 955,
    total_bld_cnt: 1098,
    ...over,
  };
}

function dong(over: Partial<ParcelBuilding> = {}): ParcelBuilding {
  return {
    bld_id: '1114011100100010000_100312041',
    bld_nm: '롯데호텔 및 백화점',
    dong_nm: '본관동',
    total_area_m2: 110982.26,
    floor_cnt: 41,
    min_floor: -3,
    max_floor: 37,
    has_roof: true,
    ...over,
  };
}

describe('응답 모양 보기', () => {
  it('제대로 된 답을 통과시킨다', () => {
    expect(isDistrictLandList([land()])).toBe(true);
    expect(isParcelBuildingList([dong()])).toBe(true);
  });

  it('빈 배열은 **정상**이다 — 건물이 한 동도 없는 상권이 10곳 실재한다', () => {
    expect(isDistrictLandList([])).toBe(true);
    expect(isParcelBuildingList([])).toBe(true);
  });

  it('칸이 빠졌거나 종류가 다르면 막는다', () => {
    expect(isDistrictLandList([{ ...land(), store_cnt: '317' }])).toBe(false);
    expect(isDistrictLandList([{ ...land(), bld_id: null }])).toBe(false);
    expect(isDistrictLandList([{ ...land(), total_parcel_cnt: undefined }])).toBe(false);
    expect(isParcelBuildingList([{ ...dong(), has_roof: null }])).toBe(false);
  });

  it('배열이 아니면 막는다 — 라이브가 오류 **객체**를 주는 경우가 이 모양이다', () => {
    expect(isDistrictLandList({ message: 'PGRST202' })).toBe(false);
    expect(isDistrictLandList(null)).toBe(false);
    expect(isParcelBuildingList('오류')).toBe(false);
  });

  it('비어도 되는 칸은 null 이어도 통과한다', () => {
    expect(isDistrictLandList([land({ bld_nm: null, road_addr: null, lat: null })])).toBe(true);
    expect(isParcelBuildingList([dong({ dong_nm: null, total_area_m2: null })])).toBe(true);
  });
});

describe('땅 한 줄 → 건물 한 채', () => {
  it('검색 결과와 같은 칸을 채운다', () => {
    const hit = landToHit(land());
    expect(hit.bld_id).toBe('1114011100100010000_100312042');
    expect(hit.pnu).toBe('1114011100100010000');
    expect(hit.bld_cnt_in_pnu).toBe(4);
    expect(hit.min_floor).toBe(-7);
    expect(hit.has_roof).toBe(true);
  });

  it('⛔ 점포 수를 건물 쪽으로 실어 보내지 않는다', () => {
    // 땅의 점포 수가 선택된 건물에 얹히면, 나중에 누군가 층별 화면에서 그것을 쓰는 날
    // "이 건물 점포"라는 뜻으로 조용히 틀린다. 세는 대상이 다르다.
    expect('store_cnt' in landToHit(land())).toBe(false);
    expect('total_parcel_cnt' in landToHit(land())).toBe(false);
  });

  it('펼친 동은 **그 동의 층**과 **그 땅의 주소**를 함께 갖는다', () => {
    const hit = parcelBuildingToHit(land(), dong());
    // 층은 동마다 다르다 — 대표 동(-7~35)이 아니라 본관동(-3~37)의 것이어야 한다.
    expect([hit.min_floor, hit.max_floor]).toEqual([-3, 37]);
    expect(hit.bld_id).toBe('1114011100100010000_100312041');
    // 주소·좌표는 같은 땅이라 땅에서 가져온다(동 목록 함수는 주소를 안 준다).
    expect(hit.road_addr).toBe('서울특별시 중구 남대문로 81');
    expect(hit.lat).toBe(37.5651);
    expect(hit.pnu).toBe('1114011100100010000');
  });
});

describe('몇 곳 중 몇 곳인가', () => {
  it('잘렸으면 그 사실을 적는다', () => {
    const shown = Array.from({ length: 50 }, (_, i) => land({ pnu: `p${i}` }));
    expect(landsSummary(shown)).toBe('955곳 · 건물 1,098동 · 이 중 50곳');
  });

  it('다 보여줬으면 "이 중 …"을 안 붙인다', () => {
    const all = Array.from({ length: 3 }, (_, i) =>
      land({ pnu: `p${i}`, total_parcel_cnt: 3, total_bld_cnt: 5 }),
    );
    expect(landsSummary(all)).toBe('3곳 · 건물 5동');
  });

  it('빈 목록이면 빈 글자 — 없는 숫자를 지어내지 않는다', () => {
    expect(landsSummary([])).toBe('');
  });

  it('땅 수와 동 수를 **둘 다** 적는다 — 955곳에 1,098동이라 하나만 적으면 어긋난다', () => {
    const s = landsSummary([land()]);
    expect(s).toContain('955곳');
    expect(s).toContain('1,098동');
  });
});

describe('더 받을 것이 남았나', () => {
  it('전부 받았으면 없다 — 마지막 쪽이 딱 떨어져도 그렇다', () => {
    const all = Array.from({ length: 50 }, (_, i) =>
      land({ pnu: `p${i}`, total_parcel_cnt: 50 }),
    );
    expect(hasMore(all)).toBe(false);
  });

  it('아직 남았으면 있다', () => {
    expect(hasMore([land()])).toBe(true);
  });

  it('빈 목록에서는 없다', () => {
    expect(hasMore([])).toBe(false);
  });
});
