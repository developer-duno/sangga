/**
 * 뷰 `v_floor_stack` 한 행 = "어느 건물의 어느 층" 하나.
 *
 * 이 화면은 이 뷰 하나만 읽는다. 원본 표(parcel·building_floor·unit_business)는
 * 공개키로 잠겨 있고 뷰만 열려 있다(2026-08-08 실측) — 읽을 수 있는 최소 범위다.
 */

/** 한 층 안의 용도별 구획. 면적이 큰 순으로 온다. */
export type FloorUse = {
  use: string | null;
  detail: string | null;
  area_m2: number | null;
};

/** (PNU, 층)으로 붙은 점포. 호 단위가 아니라 층 단위라 D등급(간접 추론)이다. */
export type Store = {
  name: string | null;
  cat: string | null;
};

export type FloorRow = {
  bld_id: string;
  pnu: string;
  /** 지상 n=n / 지하 n=-n / 옥탑=99. 0은 DB 제약으로 존재하지 않는다. */
  floor_no: number;
  floor_label: string | null;
  /** 연면적 산정 제외분(계단실·물탱크실 등)을 뺀 값 — 임대 가능 면적에 가깝다. */
  floor_area_m2: number | null;
  /** 제외분까지 전부 더한 값. */
  floor_area_gross_m2: number | null;
  segment_cnt: number | null;
  /** 그 층에서 면적이 가장 큰 용도. */
  main_use: string | null;
  uses: FloorUse[] | null;
  bld_nm: string | null;
  approve_date: string | null;
  is_jiphap: boolean | null;
  road_addr: string | null;
  road_contact: string | null;
  /**
   * 같은 필지에 있는 건물 동 수. 1보다 크면 점포가 건물 간 중복으로 달린다
   * — 상권정보에 호정보가 전수 결측이라 (PNU, 층)으로만 붙일 수 있기 때문이다.
   */
  bld_cnt_in_pnu: number;
  store_cnt: number | null;
  stores: Store[] | null;
};

/** 검색 결과 한 줄 = 건물 하나(층 여러 개를 접은 것). */
export type BuildingHit = {
  bld_id: string;
  pnu: string;
  bld_nm: string | null;
  road_addr: string | null;
  bld_cnt_in_pnu: number;
  /** 옥탑을 포함한 전체 층 수(뷰 한 행 = 한 층). */
  floor_cnt: number;
  /**
   * 옥탑(99)을 **뺀** 최저·최고 층. 옥탑은 층수가 몇이든 99 하나로 합쳐지므로
   * 여기에 섞으면 "지하 7층 ~ 옥탑"이 되어 지상 최고층(19층)이 사라진다.
   * 층이 옥탑밖에 없으면 둘 다 null.
   */
  min_floor: number | null;
  max_floor: number | null;
  /** 옥탑 층이 따로 있는가. 범위 뒤에 "+ 옥탑"으로 붙인다. */
  has_roof: boolean;
  /**
   * 검색어에 걸린 **전체** 건물 수. 서버 함수 `search_buildings`가 모든 행에 같은 값으로
   * 실어 보낸다 — 목록은 상위 일부만 오므로 "몇 개 중 몇 개"를 정직하게 말하려면 이게 필요하다.
   */
  total_cnt?: number;
};
