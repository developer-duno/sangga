import { describe, expect, it } from 'vitest';
import { buildingFromFloorRows } from './restoreBuilding';
import type { FloorRow } from '../types';

/**
 * 여기서 특히 지키는 것
 * ---------------------
 * 이 함수의 존재 이유는 **검색으로 들어올 때와 링크로 들어올 때가 같아 보이는 것**이다.
 * 그러니 층수 세는 규칙(옥탑을 세느냐 마느냐)을 가장 집요하게 본다 — 규칙이 갈리면
 * 같은 건물이 "지하2~15층"과 "지하2~99층"으로 달리 적히는데, 에러가 안 나서 못 찾는다.
 *
 * 서버 정본: schema.sql 의 `search_buildings`
 *   floor_cnt = count(*)                              ← 옥탑도 센다
 *   min/max   = min/max(floor_no) filter (floor_no<>99)
 *   has_roof  = bool_or(floor_no = 99)
 */

function row(floor_no: number, extra: Partial<FloorRow> = {}): FloorRow {
  return {
    bld_id: '1168010100107110006_10241100261590',
    pnu: '1168010100107110006',
    floor_no,
    floor_label: null,
    floor_area_m2: null,
    floor_area_gross_m2: null,
    segment_cnt: null,
    main_use: null,
    uses: null,
    bld_nm: '역삼빌딩',
    approve_date: null,
    is_jiphap: null,
    road_addr: '서울특별시 강남구 테헤란로 1',
    road_contact: null,
    bld_cnt_in_pnu: 1,
    store_cnt: null,
    stores: null,
    total_area_m2: null,
    far: null,
    bcr: null,
    parking_cnt: null,
    lat: 37.4994498380844,
    lng: 127.0331,
    ...extra,
  };
}

describe('buildingFromFloorRows', () => {
  it('층이 한 줄도 없으면 되살리지 않는다', () => {
    // 층 자료가 없는 건물이 239동 실재한다. 없는 것을 지어내면 화면이 빈 껍데기를 그린다.
    expect(buildingFromFloorRows([])).toBeNull();
  });

  it('건물 이름·주소·필지·좌표를 첫 행에서 가져온다', () => {
    const hit = buildingFromFloorRows([row(1), row(2)]);
    expect(hit).toMatchObject({
      bld_id: '1168010100107110006_10241100261590',
      pnu: '1168010100107110006',
      bld_nm: '역삼빌딩',
      road_addr: '서울특별시 강남구 테헤란로 1',
      lat: 37.4994498380844,
      lng: 127.0331,
      bld_cnt_in_pnu: 1,
    });
  });

  it('층수는 옥탑까지 센다 (검색 서버와 같은 규칙)', () => {
    const hit = buildingFromFloorRows([row(-1), row(1), row(2), row(99)]);
    expect(hit?.floor_cnt).toBe(4);
  });

  it('최저·최고층에서는 옥탑을 뺀다', () => {
    const hit = buildingFromFloorRows([row(-2), row(1), row(15), row(99)]);
    expect(hit?.min_floor).toBe(-2);
    expect(hit?.max_floor).toBe(15);
    expect(hit?.has_roof).toBe(true);
  });

  it('옥탑이 없으면 옥탑 없음이라고 한다', () => {
    const hit = buildingFromFloorRows([row(1), row(2)]);
    expect(hit?.has_roof).toBe(false);
    expect(hit?.max_floor).toBe(2);
  });

  it('옥탑만 있는 건물은 최저·최고층이 없다', () => {
    // 99 를 빼고 나면 셀 층이 없다. 여기서 99 가 새어 나오면 "99층 건물"이 만들어진다.
    const hit = buildingFromFloorRows([row(99)]);
    expect(hit?.floor_cnt).toBe(1);
    expect(hit?.min_floor).toBeNull();
    expect(hit?.max_floor).toBeNull();
    expect(hit?.has_roof).toBe(true);
  });

  it('층 순서가 뒤죽박죽이어도 범위를 맞게 잡는다', () => {
    const hit = buildingFromFloorRows([row(7), row(-3), row(99), row(2)]);
    expect(hit?.min_floor).toBe(-3);
    expect(hit?.max_floor).toBe(7);
  });

  it('좌표가 없는 필지면 좌표를 null 로 둔다 (0,0 으로 채우지 않는다)', () => {
    // 0,0 은 아프리카 앞바다다. 지도에 엉뚱한 마커를 찍느니 안 찍는 편이 맞다.
    const hit = buildingFromFloorRows([row(1, { lat: null, lng: null })]);
    expect(hit?.lat).toBeNull();
    expect(hit?.lng).toBeNull();
  });

  it('서버가 아직 좌표 칸을 안 주더라도 깨지지 않는다', () => {
    // 마이그레이션 2026-08-25a 적용 전 상태. 칸이 없으면 undefined 로 온다.
    const bare = row(1);
    delete (bare as Partial<FloorRow>).lat;
    delete (bare as Partial<FloorRow>).lng;
    const hit = buildingFromFloorRows([bare]);
    expect(hit?.lat).toBeNull();
    expect(hit?.lng).toBeNull();
  });

  it('이름 없는 건물도 되살린다', () => {
    const hit = buildingFromFloorRows([row(1, { bld_nm: null })]);
    expect(hit?.bld_nm).toBeNull();
    expect(hit?.bld_id).toBeTruthy();
  });
});
