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
  /**
   * 화면에 보일 건물 이름. **원본 건물명이 아니다** — 서버(`building_display_nm`)가
   * ① 건물명 끝의 개인 성명을 지우고 ② 건물명이 없으면 동명칭으로 대신하되
   * '주건축물제1동' 같은 일반 라벨은 버린 결과다(2026-08-08e).
   * 둘 다 없으면 null이고, 그때만 화면이 '(이름 없는 건물)'로 적는다.
   */
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

/**
 * 화면 각주용 집계 한 행(뷰 `v_coverage_stats`).
 *
 * v_floor_stack과 **같은 분기 기준**이라 화면의 점포 목록과 각주가 항상 같은 분기를 말한다.
 */
export type CoverageStats = {
  /** '202603' 형태의 분기 스냅샷 키. */
  snapshot_ym: string;
  /** 그 분기의 전체 점포 수. */
  store_cnt: number;
  /** 그중 층이 적히지 않아 어느 층에도 붙지 못하는 점포 수. */
  floor_missing_cnt: number;
  /** 층 결측 비율(%). 소수 첫째 자리까지. */
  floor_missing_pct: number;
};

/** 검색 결과 한 줄 = 건물 하나(층 여러 개를 접은 것). */
export type BuildingHit = {
  bld_id: string;
  pnu: string;
  /**
   * 화면에 보일 건물 이름. `FloorRow.bld_nm`과 **같은 규칙**(서버 `building_display_nm`)이다
   * — 개인 성명은 지워지고, 건물명이 없으면 동명칭이 대신 온다(일반 라벨은 제외).
   * 검색도 이 값 하나만 보므로 **보이는 것 = 검색되는 것**이 항상 일치한다.
   */
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
