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

/** 건물이 들어가 있는 상권 하나. 이름·종류만 나온다(경계 좌표는 안 나간다). */
export type DistrictHit = {
  name: string | null;
  /** '골목상권'·'발달상권'·'전통시장'·'관광특구' 4종(서울 상권분석서비스 원본 그대로). */
  type: string | null;
};

/**
 * 함수 `list_building_districts(bld_id)`의 응답.
 *
 * ⚠️ **두 가지 "상권 없음"을 구분해야 한다.**
 *  · `covered: false` — 그 지역엔 상권 경계 자료 **자체가 아직 없다**(예: 대전).
 *    상권 밖이라는 뜻이 아니라 "알 수 없다"는 뜻이다.
 *  · `covered: true` + `districts: []` — 자료는 있는데 이 건물이 **어느 경계에도 안 든다**.
 *    이건 정상 상태다(서울에도 이런 건물이 흔하다).
 * 둘을 같은 문구로 말하면 "자료가 없는 것"을 "상권 밖"이라고 단정하게 된다.
 */
export type BuildingDistricts = {
  covered: boolean;
  districts: DistrictHit[];
  /**
   * 이 지역 상권 자료의 출처 목록(예: `['서울특별시 상권분석서비스']`).
   * 공공누리 1유형(출처표시) 의무라 상권을 보여줄 때 함께 나가야 하는데, 문구를 화면에
   * 박아 두면 소스가 늘어난 날(서울시 + 소상공인시장진흥공단) **코드를 한 줄도 안 고쳤는데
   * 거짓말이 시작된다**. 그래서 서버가 자료에서 읽어 준 것을 그대로 보여준다.
   *
   * ⚠️ 물음표(선택)인 이유: 이 키를 주는 마이그레이션 전의 라이브는 안 보낸다.
   * 그때는 출처 줄만 조용히 생략한다(상권 이름은 그대로 보인다).
   */
  sources?: string[];
};

/**
 * 지금 검색할 수 있는 시군구 하나(뷰 `list_open_sigungu()` 한 행).
 *
 * ⚠️ 이 목록은 서버에서만 받는다 — 프론트에 하드코딩하면 자료 없는 구를 고를 수 있게
 * 되고, 고르면 아무것도 안 나와 "고장난 것"처럼 보인다.
 */
export type OpenSigungu = {
  sido_code: string;
  sido_nm: string;
  sigungu_code: string;
  sigungu_nm: string;
  building_cnt: number;
};

// ── 지도에 그리는 상권 면 (정적 파일 public/districts.geojson) ──────────────
//
// 경계는 DB에서 조회하지 않고 미리 구워 둔 파일에서 읽는다(결정 0010 §3). 상권은
// 1,687개뿐이고 거의 안 변하는데, 지도를 열 때마다 도형을 뽑으면 느리기만 하다.

/** GeoJSON 좌표 한 점. ⚠️ **[경도, 위도] 순서**다 — 카카오맵의 {lat, lng}과 반대다. */
export type Position = [number, number];

/** 폴리곤의 고리 하나. 첫 고리가 바깥 테두리이고, 뒤따르는 고리는 구멍이다. */
export type Ring = Position[];

export type DistrictGeometry =
  | { type: 'Polygon'; coordinates: Ring[] }
  | { type: 'MultiPolygon'; coordinates: Ring[][] };

/** 상권 면 하나의 속성. 굽는 스크립트(scripts/build_district_geojson.py)가 넣는 칸 그대로. */
export type DistrictProps = {
  district_id: string;
  district_nm: string | null;
  district_type: string | null;
  /**
   * 출처 문구(예: '서울특별시 상권분석서비스'). 공공누리 1유형(출처표시) 의무라
   * 지도에 함께 나가야 한다 — ⛔ 화면에 글자로 박지 말 것. 소스가 둘이 된 순간
   * (서울시 + 소상공인시장진흥공단) 코드를 안 고쳤는데 한쪽에 거짓말이 된다.
   */
  source_nm: string;
  sigungu_code: string;
  area_m2: number | null;
};

export type DistrictFeature = {
  type: 'Feature';
  properties: DistrictProps;
  geometry: DistrictGeometry;
};

export type DistrictGeoJson = {
  type: 'FeatureCollection';
  /** 굽던 시점의 라이브 상태. `post_load.py --check`가 이 값으로 파일이 낡았는지 잡는다. */
  meta: { district_cnt: number; max_computed_at: string };
  /**
   * ⚠️ **면적 내림차순**으로 구워져 있고, 이 순서가 곧 그리는 순서다(결정 0010 §5).
   * 뒤집으면 좁은 골목상권이 넓은 발달상권에 덮여 보이지 않는다. 정렬하지 말 것.
   */
  features: DistrictFeature[];
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
  /**
   * 지번(구주소) 한 줄. 예: '서울특별시 강남구 역삼동 823-4'.
   *
   * 실무에서 지번으로 찾는 일이 많아 검색 대상에 넣었다(2026-08-11). 화면에도
   * 같이 보여줘야 "823-4로 검색했는데 왜 이 건물이 나왔나"를 알 수 있다.
   *
   * ⚠️ 선택 필드다 — 마이그레이션(2026-08-11_search_by_jibun)이 라이브에 적용되기
   *    전에는 서버가 이 칸을 안 준다. 없으면 그냥 안 보이면 된다(화면은 안 깨진다).
   */
  jibun_addr?: string | null;
  /**
   * 이 건물이 선 필지의 좌표(`parcel.geom`에서 뽑은 것). 지도에 마커를 찍는 데만 쓴다.
   *
   * ⚠️ 선택 필드다 — `jibun_addr`와 같은 이유다. 이 칸을 주는 마이그레이션
   *    (2026-08-14e_search_with_coords)이 라이브에 적용되기 전에는 서버가 안 보낸다.
   *    없으면 마커만 안 찍히면 된다(지도도 화면도 안 깨진다).
   *
   * ⚠️ 건물이 아니라 **필지** 좌표다. 한 땅에 여러 동이 있으면 같은 점을 가리킨다.
   */
  lat?: number | null;
  lng?: number | null;
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
