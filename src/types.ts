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
  /**
   * 건물 스펙 4칸 — **층이 아니라 건물 한 채**의 값이라 같은 건물의 모든 층 행에
   * 같은 값이 실려 온다(화면은 head 행 하나만 읽는다).
   *
   * ⛔ **0 은 "0" 이 아니라 "대장에 안 적힘"이다.** 원본이 미기재를 '0' 으로 주고,
   *    롯데월드타워가 주차 0·건폐율 0 으로 들어와 있어 값으로는 둘을 못 가른다.
   *    그래서 화면은 0 을 값으로 적지 않는다 — `describeSpec`(FloorStack.tsx)
   *    한 곳에서만 뜻을 정한다.
   * ⓘ "NULL 은 0행" 은 **현재 적재분(서울·대전 30개 구)의 관찰값**이지 구조적 보장이
   *    아니다 — 적재기는 결측을 NULL 로 쓴다(load_building_ledger.py 의 `_to_float`,
   *    주차는 4종이 전부 결측일 때 `sum_parking` 이 None). [C] 전국 적재 뒤에는 다시
   *    세어 볼 것. 화면은 어차피 0·null 을 똑같이 "미상"으로 적어 어느 쪽이어도 안 깨진다.
   */
  /** 연면적 ㎡. */
  total_area_m2: number | null;
  /** 용적률 %. 정의상 100%를 훌쩍 넘는 것이 정상이다(층을 쌓을수록 커진다). */
  far: number | null;
  /** 건폐율 %. 정의상 0~100 이지만 원본에 소스 오류가 섞여 있다(최댓값 79,095% 실측). */
  bcr: number | null;
  /**
   * 주차대수 — 한 숫자가 아니라 **주차 4종의 합**이다(옥내자주·옥내기계·옥외자주·
   * 옥외기계). 일부만 적힌 대장이면 적힌 것만 더한 **부분합**이라 실제보다 작을 수
   * 있다(load_building_ledger.py 의 `sum_parking`).
   */
  parking_cnt: number | null;
  /**
   * 이 건물이 선 **필지의 대표 좌표**(2026-08-25a). 지도 마커 자리이자, 링크로 들어온
   * 사람의 건물을 되살릴 때 쓰는 값이다.
   *
   * ⛔ 서버는 `parcel.lat/lng` **칸이 아니라** `parcel.geom` 에서 뽑는다. 검색
   *    (`search_buildings`)과 상권 판정(`list_building_districts`)이 전부 geom 을 보므로,
   *    칸을 섞으면 같은 건물인데 **들어온 길에 따라 마커 자리가 갈린다**(2026-08-14e).
   * ⓘ 한 땅에 건물이 여럿이면 그 건물들이 **같은 자리**에 찍힌다(검색도 같은 한계다).
   * ⚠️ 선택 필드다 — 마이그레이션(2026-08-25a)이 적용되기 전 서버는 이 칸을 안 준다.
   *    없으면 마커만 안 찍히고 화면은 안 깨진다.
   */
  lat?: number | null;
  lng?: number | null;
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

// ── 실거래 사실 표시 (Stage A · 결정 0012) ──────────────────────────────────
//
// ⚠️ 여기 오는 값은 **추정이 아니다.** 신고된 거래 그대로이거나 그것을 센 값이다.
//    추정 밴드(Stage B)는 결정 0013 으로 결재됐고 아래 `PriceBand` 로 따로 온다.
//    **이 블록의 값은 여전히 추정이 아니다** — 둘을 한 타입·한 블록으로 합치지 말 것.

/** 함수 `list_parcel_transactions(pnu)` 한 행 = 그 필지에서 일어난 거래 하나. */
export type ParcelTransaction = {
  /** 지상 n=n / 지하 n=-n / 옥탑=99. ⚠️ 2017년부터 국토부가 층을 빈 값으로 줘 null 이 흔하다. */
  floor_no: number | null;
  /** 계약 년월 '202605'. */
  contract_ym: string;
  contract_day: number | null;
  /** 전용면적(㎡). */
  bld_area_m2: number | null;
  price_won: number;
  /** 원/㎡ (DB 생성 컬럼). 면적이 없으면 null. */
  unit_price: number | null;
  /** '집합'(구분소유) / '일반'(통건물). 통건물은 지번이 마스킹돼 여기 거의 안 온다. */
  tx_type: string | null;
};

/**
 * 함수 `get_sigungu_tx_stats(sigungu)` 한 행 = 그 구의 층대 하나.
 *
 * 다섯 칸(지하·1층·2층·3층이상·층미상)이 **항상 같은 순서로** 온다. 표본이 없으면
 * `n: 0` 으로 오지 그 칸이 빠지지는 않는다 — 칸이 사라지면 "그 층은 아예 안 판다"처럼 읽힌다.
 */
export type SigunguTxStat = {
  floor_band: string;
  /** 중앙값을 낸 실제 표본 수. 화면은 5건 미만이면 수치를 감춘다(검증 규칙의 미표시 원칙). */
  n: number;
  median_unit_price: number | null;
  p25_unit_price: number | null;
  p75_unit_price: number | null;
  /**
   * 집계한 창의 시작 달('202408'). 화면이 "최근 24개월"이라고만 적으면 갱신을 미룬 날
   * 그 문구만 조용히 거짓말이 되므로, 실제로 어느 달부터인지를 서버가 준다.
   */
  window_from: string | null;
  /** 구 이름. 화면에 지역명을 글자로 박지 않기 위해 서버가 준다. */
  sigungu_nm: string | null;
};

// ── 참고 매매 시세 밴드 (Stage B · 결정 0013) ───────────────────────────────
//
// ⚠️ 여기 오는 값은 **추정이다.** 위 Stage A 와 화면에서도 카드를 갈라 그린다
//    (`section.tx` = 사실 / `section.band` = 추정). 두 블록을 합치지 말 것.

/**
 * 함수 `list_price_bands(p_pnu)` 한 행.
 *
 * ⚠️ **파라미터 이름이 이 함수만 `p_pnu` 다**(형제는 `bld_id`·`pnu`·`sigungu`). 컬럼명과
 *    충돌하지 않게 접두사를 붙인 것인데, 습관대로 `{ pnu: … }` 로 부르면 목(mock)은 인자
 *    이름을 안 보므로 테스트는 전부 초록인 채 **라이브에서만** PGRST202 가 난다.
 *
 * `status` 다섯이 각각 **다른 말**을 한다 — 절대 같은 문구로 뭉뚱그리지 않는다:
 *  · `gate_fail`   — 이 **구 전체**를 아직 안 낸다. 표본이 모자란 게 아니고, 시험에
 *                    떨어진 것만도 아니다(판정이 아예 없는 구도 여기로 온다).
 *                    이때만 `floor_no` 가 null 이고 **딱 한 줄**로 온다.
 *  · `floor_1f`    — 1층은 방침상 안 낸다(자리에 따라 값이 갈리는데 그 자리를 모른다).
 *  · `no_evidence` — 지하·옥탑. 검증에 쓸 거래가 **한 건도 없어** 검증한 적이 없다.
 *                    ⛔ "표본 부족"이라 적으면 "더 모으면 나오나?"라는 오해가 된다.
 *  · `no_estimate` — 곁 거래를 못 찾았다. 거래가 쌓이면 나올 수 있다.
 *  · `ok`          — 값이 있다. 근거 단계(`stage`)와 표본 수(`n`)를 **항상 함께** 적는다.
 *
 * `ok` 가 아니면 `stage`·`n`·사분위·`median_area_m2` 가 전부 null 이다.
 */
export type PriceBand = {
  /** 지상 n=n / 지하 n=-n / 옥탑=99. ⚠️ `gate_fail` 일 때만 null 이다. */
  floor_no: number | null;
  /** 위 다섯 중 하나. ⚠️ 서버가 여섯 번째를 늘릴 수 있으므로 화면은 모르는 값이면 침묵한다. */
  status: string;
  /**
   * 채택된 근거 단계 — 'L2'(같은 필지 같은 층) · 'L4'(100m) · 'L5'(500m) ·
   * 'L6'(같은 법정동 같은 층대). ⚠️ 서버 타입이 text 라 여기서도 좁은 유니온으로 두지
   * 않는다 — 모르는 코드가 오면 값을 내지 않는 쪽이 안전하다.
   * ⛔ 'L1'·'L3' 은 **존재하지 않는다**(사다리에 그 칸이 없다).
   */
  stage: string | null;
  /** 그 단계에서 쓴 거래 건수. ⚠️ L2·L6 의 최소 표본이 **1건**이라 n=1 이 정상적으로 온다. */
  n: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  /**
   * ⚠️ **이 층의 면적이 아니다.** 근거로 쓴 곁 거래들의 전용면적 중앙값이다
   * — 총액을 환산하는 자일 뿐이라 "이 층 32.8㎡"라고 적으면 거짓말이 된다.
   * 면적이 적힌 거래가 하나도 없으면 null 이고, 그때는 총액을 아예 안 그린다.
   */
  median_area_m2: number | null;
  /**
   * 후보 거래를 모은 창의 시작 달('202408'). ⚠️ Stage A 의 이력(202401 고정)과 달리
   * **오늘 기준 롤링 24개월**이라 두 블록의 기간이 다르다. 화면에 기간을 글자로 박지 않는다.
   */
  window_from: string | null;
};

/**
 * 함수 `list_base_prices(p_pnu)` 한 행 = 이 필지의 어느 층 하나.
 *
 * ⚠️ **파라미터 이름이 `p_pnu` 다**(`list_price_bands` 와 같은 이유 — 컬럼명 `pnu` 와
 *    겹치면 SQL 안에서 어느 쪽인지 갈리지 않는다). 목(mock)은 인자 **이름**을 안 보므로
 *    `{ pnu: … }` 로 잘못 부르면 테스트는 전부 초록이고 **라이브에서만** PGRST202 가 난다.
 *
 * ⛔ **이건 시세가 아니다.** 국세청이 해마다 고시하는 **세금 매길 때 쓰는 기준가격**이고,
 *    같은 화면의 `PriceBand`(우리가 곁 거래로 어림한 추정)와는 **다른 자로 잰 다른 값**이다.
 *    두 값을 한 줄에 섞거나 서로 견주는 문구를 쓰지 말 것 — 사람은 나란히 놓인 두 숫자를
 *    자동으로 "같은 것의 두 가지 측정"으로 읽는다.
 *
 * ⛔ **총액으로 환산하지 말 것.** 이 함수는 면적을 **아예 안 내보낸다**. 총액을 재려면
 *    전용면적만이 아니라 (전용 + 공유)를 곱해야 하는데(공용부를 빼면 적게 나온다) 그
 *    면적이 여기 없다. 바로 위 밴드 블록에 `toTotalWon(median, median_area_m2)` 가 있어
 *    베껴 쓰기 딱 좋은 자리인데, 그 면적은 **곁 거래들의 전용면적 중앙값**이라 이 값과
 *    아무 상관이 없다 — 곱하는 순간 남의 면적으로 만든 가짜 총액이 된다.
 *    (면적이 정말 필요하면 서버에 새로 청해서 받는다. 화면이 지어내지 않는다.)
 *
 * ⓘ 서버가 '상가' 종류만 모아 층마다 **가운데값**을 낸다. 그래서 `ho_cnt`(그 층에서 센
 *   호 수)가 늘 함께 온다 — 값만 떼어 내보내면 절대 규칙 3(근거·표본 병기) 위반이다.
 * ⓘ 오피스텔은 주거 가격이라 섞으면 상가 값이 끌려가므로 서버가 뺀다 — 그래서 **오피스텔만
 *   있는 건물은 빈 목록**으로 온다(0원이 아니다. 화면은 그때 줄을 안 그린다).
 */
export type BasePrice = {
  /**
   * 지상 n=n / 지하 n=-n / **옥탑=99**. 층별 스택과 같은 규칙이라 `formatFloor` 로 적는다
   * — 안 거치면 옥탑이 화면에 **"99층"**으로 그려진다(전국 14행뿐이라 눈으로는 거의 못 잡는다).
   *
   * ⚠️ **null 을 허용해 둔다.** 적재기가 층 구분값 셋(지상·지하·옥탑) 밖이면 적재를 통째로
   *    멈추므로 지금은 NULL 이 안 들어온다(2026-08-27 적재 담당 확인). 그래도 컬럼이 NULL 을
   *    허용하고 함수는 `group by n.floor_no` 로 그 묶음을 그대로 내보내므로, 화면은 그 줄을
   *    조용히 버린다 — 어느 층에도 붙일 수 없는 값을 억지로 얹는 것이 곧 거짓말이다.
   */
  floor_no: number | null;
  /**
   * ㎡당 고시가격(원)의 중앙값.
   *
   * ⚠️ 이름을 **서버가 정한다** — `supabase/schema.sql` 의 `list_base_prices` 반환 칸이
   *    `median_price_per_m2` 다. 한 글자만 어긋나도 여기서는 `undefined` 가 되어 줄이
   *    **조용히 사라지고**, 목(mock)은 그 어긋남을 못 보므로 테스트는 전부 초록이다
   *    (라이브에서만 티가 나는 종류다 — 서버 쪽을 고치면 여기도 같은 커밋에서 고친다).
   */
  median_price_per_m2: number;
  /** 그 중앙값을 낸 호 수. */
  ho_cnt: number;
  /**
   * 고시일 '2026-01-01'. 그 필지의 **가장 최근 고시일자 하나**라 해가 쌓여도 섞이지 않는다
   * (서버가 최근 한 해만 골라 센다). 화면은 이 값을 그대로 적는다 — 연도를 지어내지 않는다.
   */
  notice_date: string;
};

// ── 상권 임대 동향 (결정 0024 — 부동산원 조사값 그대로) ──────────────────────
//
// ⛔ **추정이 아니다.** 한국부동산원이 분기마다 표본을 조사해 공표한 값을 그대로 나른다.
//    절대 규칙 5 가 말하는 "수익률·층별효용비율 역산"은 백테스트와 재결재를 거친 뒤의
//    일이고(매매가 결정 0013 으로 그렇게 했다), 이 카드는 그 앞 단계다 — 조사값을 옮겨
//    적기만 한다. 그래서 이 타입에 `floor_util_ratio` 가 없다(있으면 언젠가 곱하게 된다).
// ⛔ **이 건물의 임대료가 아니다.** 이 건물이 속한 **상권**을 조사한 값이다.

/** 상권 하나 × 건물 종류 하나의 조사값(함수 `list_rent_stats` 한 행). */
export type RentStat = {
  /** 우리 상권 이름('역삼역'). 어느 상권의 값인지 화면이 밝히는 데 쓴다. */
  district_nm: string | null;
  /**
   * 부동산원 쪽 조사구역 이름 전체 경로('서울>강남>테헤란로').
   *
   * ⚠️ 우리 상권 이름과 **다른 이름**이라 함께 적는다. 한 상권이 조사구역 **둘**에 이어져
   *    있을 수 있고(부동산원이 건물 종류마다 서울 권역 분할을 달리한다), 그때는 같은
   *    상권 밑에 서로 다른 조사구역의 값이 나란히 온다 — 이름이 없으면 사람은 같은 것을
   *    두 번 보는 줄 안다.
   */
  rone_region_nm: string;
  /**
   * 건물 종류 — '집합상가' · '중대형상가' · '소규모상가' · '오피스'.
   *
   * ⛔ **넷을 더하거나 평균 내지 않는다.** 모집단이 다른 네 조사라 섞는 순간 아무것도 아닌
   *    숫자가 된다. 화면은 한 번에 하나만 보여주고, 무엇을 보는 중인지 늘 글자로 적는다.
   * ⚠️ 타입을 그 넷으로 좁히지 않는다(`LhNotice.kind_nm` 과 같은 이유) — 화면은 이 글자를
   *    그대로 적기만 하므로 종류가 늘어도 안 깨진다.
   */
  bld_type: string;
  /** 조사 분기 '2026Q2'. **줄마다 다를 수 있다**(종류·조사구역마다 최신 분기를 따로 고른다). */
  quarter: string;
  /** 공실률(%). 공표값 그대로. */
  vacancy_rate: number | null;
  /**
   * ㎡당 임대료. **단위가 천원/㎡ 다**(부동산원 공표 단위 `UI_NM` 그대로 — 원본 raw 실측).
   *
   * ⛔ 서버가 미리 원으로 바꾸지 않는다. "서버 값 = 공표값"이라는 대조를 남겨 두려고 그렇게
   *    했으므로, 원 단위로 바꿔 적는 일은 화면이 하고 그 사실도 화면이 밝힌다.
   * ⛔ **기간(월·연)과 층 기준을 우리가 단정하지 않는다.** 공표 자료가 그 둘을 이 값 옆에
   *    적어 주지 않아(공공데이터포털 메타에도 없다) 확인되지 않은 말을 붙이지 않는다.
   */
  rent_per_m2: number | null;
  /**
   * 투자수익률(%). **분기 값**이다(원본 `DTACYCLE_CD='QY'`).
   *
   * ⛔ 4를 곱해 연으로 바꾸지 않는다 — 공표되지 않은 값을 우리가 지어내는 일이다.
   */
  yield_rate: number | null;
};

// ── 업종 분포 (결정 0014 "상권 지표 계산" 1단계) ────────────────────────────
//
// ⚠️ 여기 오는 값은 **추정이 아니다.** 상권정보에 등록된 점포를 그대로 센 개수다.
//    다만 "이 건물만의 점포"가 **아니라** 이 땅 둘레(상권·반경)의 점포다 — 이 건물 것도
//    그 안에 포함되고 이웃 가게까지 함께 센다. 층별 스택의 점포 칸과 세는 대상 자체가
//    다르므로 두 숫자를 견주면 안 된다.
// ⛔ 상호명은 한 글자도 오지 않는다(서버가 개수만 낸다). 그 상태를 유지할 것.

/** 업종 한 칸. 대분류(`list_industry_mix`)와 중분류(`list_industry_detail`)가 같은 모양이다. */
export type IndustryCat = {
  /** 대분류는 2자리('I2'), 중분류는 4자리('I201'). */
  cd: string;
  nm: string | null;
  n: number;
};

/** 한 스코프(상권 하나 또는 반경)의 집계. */
export type IndustryScope = {
  /** 이 스코프의 점포 총수. `cats` 의 합과 같다. */
  total: number;
  /** 많은 순으로 온다. 같으면 코드순이라 순서가 흔들리지 않는다. */
  cats: IndustryCat[];
};

/** 상권 하나의 집계 — 위 `IndustryScope` 에 상권 이름표가 붙은 것. */
export type IndustryDistrict = IndustryScope & {
  district_id: string;
  name: string | null;
  /** `list_industry_detail` 에는 안 온다(대분류 응답에만 있다). */
  type?: string | null;
  /** 공공누리 1유형(출처표시) 의무. ⛔ 화면에 글자로 박지 말 것. */
  source_nm?: string | null;
};

/**
 * 함수 `list_industry_mix(p_pnu)` 의 응답(대분류).
 *
 * ⚠️ **`radius` 가 null 인 것과 `total: 0` 인 것은 다른 말이다.**
 *  · `null`   — 필지 좌표가 없어 **잴 수가 없었다**(모른다). 화면은 그 블록을 감춘다.
 *  · `total:0` — 재 봤더니 반경 안에 점포가 없었다(사실).
 * 둘을 같이 다루면 "모르는 것"을 "없는 것"이라 말하게 된다.
 *
 * ⚠️ `districts` 를 **더하지 말 것.** 상권이 겹치는 자리의 점포는 양쪽에 세어진다
 *    (2026-08-22 라이브 실측: 상권 안 462,858곳 중 17,946곳 = 3.9%). 합계는 부풀려진다.
 */
export type IndustryMix = {
  /** 두 블록이 함께 쓰는 분기('202606'). 화면이 기준 시점을 글자로 박지 않게 서버가 준다. */
  snapshot_ym: string | null;
  /** 반경 몇 m 로 쟀나. 화면에 '500m'를 박으면 서버가 바꾸는 날 거짓말이 된다. */
  radius_m: number;
  districts: IndustryDistrict[];
  radius: IndustryScope | null;
};

/**
 * 함수 `list_industry_detail(p_pnu, p_cat)` 의 응답(고른 대분류 안의 중분류).
 *
 * ⚠️ `cat_l_cd` 는 **물어본 값을 그대로 되돌려 준 것**이다. 사용자가 그 사이 다른 업종을
 *    고르면 늦게 도착한 답을 버려야 하는데, 이 칸이 없으면 목록이 조용히 뒤바뀐다.
 */
export type IndustryDetail = {
  snapshot_ym: string | null;
  radius_m: number;
  cat_l_cd: string;
  districts: IndustryDistrict[];
  radius: IndustryScope | null;
};

/**
 * 함수 `count_nearby_permits(p_pnu)` 의 응답 — 이 땅 둘레의 **미준공 상업 계열 건축 인허가**.
 *
 * 위 업종 분포와 같은 카드에 서지만 **자로 잰 것이 다르다**: 저쪽은 지금 장사 중인 가게
 * 개수이고, 이쪽은 아직 다 안 지어진 건물 동수다. 그래서 두 숫자를 더하거나 견주면 안 된다.
 *
 * ⚠️ **추정이 아니라 공식 인허가 기록**이다. 그렇다고 "곧 완공"·"예정"이라 적지 않는다 —
 *    허가를 받고도 안 짓거나 용도가 바뀌는 일이 흔해서, 우리가 아는 사실은 "그 달 기준으로
 *    이런 허가가 살아 있다"까지다.
 * ⓘ 자료가 하나도 없으면 `total_cnt: 0` 으로 온다. 그때 화면은 그 줄만 조용히 생략한다
 *   ("없음"이라 적으면 모르는 것과 없는 것이 뒤섞인다 — 업종 분포와 같은 규칙).
 */
export type NearbyPermits = {
  /** 미준공 상업 계열 인허가 건물 수. */
  total_cnt: number;
  /**
   * 그중 **실착공**까지 간 것. 나머지(`total_cnt - started_cnt`)가 '허가만' 받은 것이다.
   *
   * ⚠️ 뜻이 부분집합이라 `total_cnt` 보다 클 수 없다. 그런데도 크게 오면 화면은 그 줄을
   *    통째로 버린다 — 쪼갤 수 없는 수를 억지로 쪼개면 '허가만 -3동'이 나온다.
   */
  started_cnt: number;
  /** 어느 달 기준으로 센 것인가('202607'). 화면이 연·월을 글자로 박지 않게 서버가 준다. */
  base_ym: string;
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

/**
 * LH(한국토지주택공사)가 낸 상가 분양·임대 공고 하나(함수 `list_lh_notices` 한 행).
 *
 * ⛔ **값(분양가·보증금·임대료)은 담지 않는다.** 조건은 공고문마다 다르고 정정 공고로
 *    바뀌기도 해서, 우리가 옮겨 적는 순간 틀릴 수 있는 값이 된다. 화면은 "무엇이 열려
 *    있는지"만 말하고 나머지는 링크로 넘긴다.
 * ⓘ 거르기·정렬은 **서버가 한다**(마감 지난 공고 제외 · 해당 시도 + 전국 공고 · 마감
 *   임박순). 화면에서 다시 거르지 않는다 — 같은 규칙이 두 곳에 있으면 언젠가 갈린다.
 */
export type LhNotice = {
  /** 공고 하나를 가리키는 열쇠. 목록의 key 로 쓴다. */
  pan_id: string;
  pan_nm: string;
  /**
   * 공고 종류. 지금은 넷이다 — '분양 입찰' · '임대 추첨' · '임대 입찰' · '공모·심사'.
   *
   * ⚠️ 타입을 그 넷으로 **좁히지 않는다.** 화면은 이 글자를 배지에 그대로 적기만 하므로
   *    새 종류가 생겨도 안 깨지는데, 좁혀 두면 런타임 검사(문자열인가)와 타입이 어긋나
   *    "검사는 통과했는데 타입은 거짓말"인 상태가 된다.
   */
  kind_nm: string;
  /** 진행 상태('공고중'·'접수중' 등). 이것도 서버 글자를 그대로 적는다. */
  pan_ss: string;
  /** 공고일·마감일. **없을 수 있다**(마감일이 안 정해진 공고가 있다). */
  notice_date: string | null;
  close_date: string | null;
  /** LH 쪽 상세 페이지. 화면은 이 주소로만 넘긴다(신청·가격을 우리가 옮겨 적지 않는다). */
  dtl_url: string;
  /** 우리가 이 줄을 받아 둔 시각. 요약 줄에 그대로 밝힌다 — 낡음을 감추지 않는다. */
  collected_at: string;
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
