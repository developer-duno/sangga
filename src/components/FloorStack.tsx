import { Fragment, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { supabase } from '../lib/supabase';
import { startSidePrefetch, type SidePrefetch } from '../lib/sidePrefetch';
import {
  FLOOR_STACK_VIEW,
  COVERAGE_STATS_VIEW,
  BUILDING_DISTRICTS_FN,
  PARCEL_TX_FN,
  SIGUNGU_TX_STATS_FN,
  BASE_PRICES_FN,
  TX_LIST_CAP,
  TX_OPEN_SINCE_LABEL,
  TX_BASEMENT_MISSING_SINCE,
  TX_MIN_SAMPLE,
  UNIT_FLOOR_SUMMARY_FN,
  FLOOR_UNITS_FN,
  FLOOR_UNITS_PAGE,
  LAND_PRICE_FN,
} from '../lib/appConstants';
import { LAND_PRICE_BADGE, landPriceText, parseLandPrice } from '../lib/landPrice';
import { TX_STAT_BADGE } from '../lib/floorGap';
import {
  TX_SHAPE_LABEL,
  txBandAxisMaxWon,
  txBandMark,
  txPlot,
  type TxBandMark,
  type TxPlot,
  type TxShape,
} from '../lib/txViz';
import { cssVar, VIZ_TONES } from '../lib/viz';
import type {
  BasePrice,
  BuildingDistricts,
  BuildingHit,
  CoverageStats,
  FloorRow,
  ParcelLandPrice,
  FloorUnit,
  ParcelBuilding,
  ParcelTransaction,
  SigunguTxStat,
  UnitFloorSummary,
} from '../types';
import {
  UNIT_HOME_FLOOR_NOTE,
  UNIT_MEDIAN_NOTE,
  UNIT_MULTI_FLOOR_NOTE,
  formatUnitArea,
  hasUnitList,
  noUnitDataText,
  orphanUnits,
  orphanUnitsText,
  parseFloorUnits,
  parseUnitSummary,
  unitDisplayName,
  unitSummaryText,
} from '../lib/unitTable';
import {
  UNKNOWN_SPEC,
  describeElevator,
  describeHoCnt,
  describeSpec,
  describeStructure,
  formatArea,
  formatApproveDate,
  formatFloor,
  formatJiphap,
  formatManWon,
  formatMonthKo,
  formatParking,
  formatQuarter,
  formatWon,
  formatYearMonth,
  floorMissingPhrase,
} from '../lib/format';
import { FOUNDER_CHIP_ALL, type FounderChip } from '../lib/founderChips';
import {
  UNIT_PRINT_CONCURRENCY,
  runLimited,
  unitPrintCapText,
  unitPrintFailedText,
  unitPrintLoadingText,
  unitPrintMoreText,
  unitPrintPlan,
  type UnitPrintMode,
} from '../lib/unitPrint';
import { lacksCoord } from '../lib/rentStats';
import { buildingFromFloorRows } from '../lib/restoreBuilding';
import { dongSuffix, moreDongCount, siblingName, siblingWindow } from '../lib/buildingHead';
import { siblingToHit } from '../lib/districtBuildings';
import { isPlainLeftClick } from '../lib/spaLink';
import {
  SECTION_PLAN,
  sectionOrder,
  sectionPlansFor,
  type SectionKey,
  type SectionPlan,
  type ViewerRole,
} from '../lib/sectionCards';
import { IndustryMixSection } from './IndustryMixSection';
import { RentStatSection } from './RentStatSection';
import { OpenCloseSection } from './OpenCloseSection';
import { EmptySection } from './EmptySection';
import { FloorGapSection } from './FloorGapSection';
import { SectionCard } from './SectionCard';
import { RoleSummary } from './RoleSummary';

/**
 * 구 단가에서 수치를 보여줄 최소 표본 수(결정 0012).
 *
 * 이보다 적으면 중앙값·사분위를 **적지 않는다.** 3건으로 낸 중앙값은 숫자 모양만
 * 통계일 뿐이고, 화면에 적히는 순간 사람은 그걸 근거로 쓴다 — 검증 규칙의 미표시 원칙이다.
 *
 * ⚠️ 값 자체는 `appConstants` 에 있다(결정 0027) — 입구의 『동네 매매 단가 흐름』 카드도
 *    같은 자로 가려야 해서다. 두 곳에 5 를 따로 적어 두면 한쪽만 고치는 날 같은 자료를
 *    두 화면이 다르게 가린다.
 */
const MIN_SAMPLE = TX_MIN_SAMPLE;

/**
 * 도로접면을 **적지 않는** 값(로드맵 Wave 2 PR-A).
 *
 * '맹지'는 "접한 길이 없다", '지정되지않음'은 "조사가 안 됐다"에 가까운데 둘 다 칸을
 * 만들어 두면 사람은 그중 한쪽으로 단정해 읽는다. 모르는 것을 아는 것처럼 말하지
 * 않으려면 칸 자체를 안 만드는 편이 맞다.
 */
const ROAD_CONTACT_HIDDEN = new Set(['맹지', '지정되지않음']);

/**
 * 헤더에 이름을 적는 업종 수. 나머지는 "외 N종"으로 세기만 한다.
 * 셋을 넘기면 요약이 아니라 목록이 되고, 그건 층을 펼쳤을 때 보는 것과 같아진다.
 */
const BIZ_TOP_N = 3;

/**
 * 건폐율을 값으로 적는 상한(%).
 *
 * 정의상 0~100 인데 원본에 소스 오류가 섞여 있다 — 2026-08-11 실측으로 24만 행 중
 * 7행이 1만%를 넘고 최댓값이 79,095% 다(`building.bcr` 컬럼 주석). 넘는 값은 값이
 * 아니라 오류이므로 "미상"으로 적는다. 숫자 모양으로 적히는 순간 사람은 그걸 근거로 쓴다.
 */
const MAX_BCR_PCT = 100;

/**
 * 연면적을 값으로 적는 상한(㎡).
 *
 * 우리 자료의 최댓값이 861만㎡ 인데(로드맵 Wave 2 PR-B 실측), 한 동의 연면적이라기보다
 * 단지 전체를 한 행에 몰아 적은 오기입에 가깝다. 100만㎡ 는 "이보다 큰 건물은 없다"는
 * 뜻이 아니라 **넘으면 오기입일 확률이 훨씬 높다**는 판단이다.
 *
 * ⚠️ 이 상한은 오류를 거르는 용도지 큰 건물을 감추는 용도가 아니다. 걸리는 건물이
 *    눈에 띄게 늘면 상한을 올릴 게 아니라 **원본 적재**를 먼저 의심할 것.
 */
const MAX_TOTAL_AREA_M2 = 1_000_000;

/** 용적률·건폐율 표기. 대장은 소수 둘째 자리까지 주지만 화면에서는 뜻이 없어 첫째 자리로. */
function formatPercent(n: number): string {
  return `${n.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}%`;
}

/*
  ⓘ `UNKNOWN_SPEC`·`describeSpec`·`formatParking`·`formatJiphap` 은 `lib/format.ts` 로 옮겼다
    (2026-10-11 · 물결 1-A2(iii)) — 중개사 검색 결과의 소유 구조 줄이 같은 '미상' 규칙을 쓴다.
*/

/**
 * 도로접면 한 조각. **원문 그대로** 내보낸다.
 *
 * ⛔ '큰길'·'골목' 같은 말로 옮겨 적지 않는다. 시세 사다리가 쓰는 등급(road_grade)과
 *    화면이 서로 다른 말을 하기 시작하면 같은 땅에 기준이 둘 생긴다 — 나중에 어느 쪽이
 *    맞는지 아무도 못 가린다.
 */
function displayRoadContact(raw: string | null): string | null {
  const v = (raw ?? '').trim();
  if (v === '' || ROAD_CONTACT_HIDDEN.has(v)) return null;
  return v;
}

/**
 * 이 건물 층들에 붙은 점포를 업종 이름으로 센다. 많은 순, 같으면 이름순이라
 * 순서가 흔들리지 않는다.
 *
 * ⚠️ 여기 `cat` 은 상권정보의 **소분류 이름**이다(서버 `cat_s_nm`). 대분류가 아니므로
 *    "대분류"라고 적으면 거짓말이 되고, 아래 `IndustryMixSection`(대분류로 세는 곳)의
 *    숫자와 견줘도 안 된다 — 세는 단위부터 다르다.
 * ⚠️ 업종 이름이 빈 점포는 순위에서 뺀다. 세는 대상이 "업종"인데 업종을 모르는 것을
 *    한 칸으로 만들면, 모르는 것이 업종 하나인 것처럼 보인다.
 */
function topCategories(floors: FloorRow[]) {
  const counts = new Map<string, number>();
  for (const f of floors) {
    for (const s of f.stores ?? []) {
      const cat = (s.cat ?? '').trim();
      if (cat === '') continue;
      counts.set(cat, (counts.get(cat) ?? 0) + 1);
    }
  }
  const sorted = [...counts.entries()].sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ko-KR'),
  );
  return { top: sorted.slice(0, BIZ_TOP_N), etc: Math.max(sorted.length - BIZ_TOP_N, 0) };
}

/**
 * 층별 스택 뷰 — 이 서비스의 시그니처 화면(§8.6).
 *
 * 위가 고층, 아래가 지하로 쌓는다. 막대 길이는 그 층의 임대 가능 면적에 비례한다.
 *
 * ⚠️ 층 행에 채우는 칸은 층·용도·면적·점포 4개뿐이다 — 여기에는 여전히 **사실만** 그린다.
 *    (참고 매매 시세 추정 카드는 결정 0041 로 내렸다 — 층마다 공표값은 『층별 공표값 나란히』가 모은다.) 공실 이력은
 *    Phase 5 산출물이라 아직 없다(빈칸을 그럴듯하게 채우면 없는 근거를 있는 것처럼
 *    보이게 만든다).
 */

type Props = {
  building: BuildingHit;
  /**
   * 첫 화면 역할 단추로 고른 역할(결정 0036 결정 18). 카드 **순서·펼침**만 바뀐다 — 자료는 한 벌.
   * null·안 줌 = 역할을 고르기 전 화면 그대로.
   */
  viewerRole?: ViewerRole | null;
  /**
   * 창업자가 고른 업종 칩(결정 0036 결정 18 ⑨). 업종 분포·개업·폐업 카드에 그대로 내려 준다 —
   * 짝짓기는 그 카드들이 `lib/founderChips.ts` 의 표로 한다. 안 줌·'전체' = 지금 화면 그대로.
   */
  founderChip?: FounderChip;
  /**
   * 인쇄 단추 옆 「호실 구성표」 고르기(결정 0036 결정 8 · 물결 1-C2). 고르면 그 층들의 호 목록을 층 줄
   * 아래에 **화면에서도** 펼친다 — 그래서 Ctrl+P 로 뽑아도 같은 종이다. 안 줌·'none' = 지금 화면 그대로.
   * ⓘ 손님 화면의 기본값('지하~3층')은 App 이 정한다 — 이 부품의 기본값은 시험·옛 부모용 'none'.
   */
  unitPrintMode?: UnitPrintMode;
  /**
   * 손님이 **직접** 고를 때마다 1씩 오르는 신호 — 그때만 층 목록 카드를 펼친다(👤 2026-10-11). 기본값으로
   * 정해진 고르기는 카드를 강제로 펼치지 않는다(펼침 상한 4 · 역할별 접힘 그대로 — 접힌 카드도 본문은 DOM 에
   * 있어 종이에 나온다, 결정 0020). 0·안 줌 = 펼치지 않는다.
   */
  unitPrintOpenSignal?: number;
  /**
   * 이 건물에서 호 목록이 있는 층 수를 알린다(요약을 받은 뒤 한 번) — App 이 0개면 고르기 줄을 숨긴다.
   * 요약을 못 받았으면 부르지 않는다(App 은 모름 = 숨김으로 읽는다).
   */
  onUnitListedCount?: (bldId: string, count: number) => void;
  /**
   * 역할 요약 판(결정 0039 W2)의 「한 장으로 뽑기」가 인쇄 창 **전에** 부른다 — App 의 `handleBeforePrint`(인쇄 단추와 같은 것).
   * 안 줌 = 기록 없이 인쇄만.
   */
  onBeforePrint?: () => void;
  /**
   * 같은 땅의 동 목록(결정 0042 H5 · `list_parcel_buildings` — App 이 `bld_cnt_in_pnu > 1` 일 때 한 번 받는다).
   * 2줄 이상이면 머리 사양 칸 아래 「같은 땅 다른 동: …」 링크 줄. null·안 줌 = 그 줄 없음.
   */
  dongs?: readonly ParcelBuilding[] | null;
  /** 이 건물이 있는 구의 이름(지역 고르개가 서버 목록에서 알려 준 것) — 있으면 「○○구 다른 건물 찾기」 링크. */
  sigunguName?: string | null;
  /** 같은 땅 다른 동 링크의 보통 누름 — 화면 안에서 그 동으로(App 의 `handleSelectBuilding`). */
  onSelectBuilding?: (hit: BuildingHit) => void;
  /** 「○○구 다른 건물 찾기」의 보통 누름 — 화면 안에서 찾기 칸으로(넓은 화면 = 위 칸 펼침 · 휴대폰 = 찾기 탭). */
  onFindInSigungu?: () => void;
};

/** 고른 층 하나의 첫 쪽 호 목록(받은 줄 + 그 층 전체 호실 수). */
type PrintedUnits = { units: FloorUnit[]; total: number };

/**
 * 긴 목록 창(S2 · 👤 2026-10-15) — 이만큼만 **화면에** 보이고 나머지는 「전부 보기」로 펼친다.
 * 이 줄 수 이하면 단추도 없다(지금 그대로).
 *  · 층 목록 = **아래 10줄**(👤 검사 뒤 다시 여쭘 — 지하·1층·2층이 바로 보이게). 서버 순서(위층부터)는
 *    그대로 두고 앞쪽(위층) 줄을 숨긴다 · 단추는 목록 맨 위. → `floorFoldCut`
 *  · 이 땅 거래 목록 = 처음 10건 · 단추는 목록 아래.
 * ⛔ 줄은 늘 전부 그린다 — 넘치는 줄에는 `list__folded` 이름표만 붙고, 숨김은 styles.css 의
 *    `@media screen` 규칙이 한다. 그래서 종이에는 늘 전부 나오고 `floor-N` id 도 늘 있다.
 */
const LIST_FOLD_AT = 10;

/**
 * 층 목록에서 화면에 숨는 줄의 수 — 서버 순서(위층부터)의 **앞쪽** 이만큼(index < 이 값)이 숨는다.
 * 펼쳤거나 10줄 이하면 0. 건너뛰기·호실 고르기·접기 정리가 모두 이 한 곳으로 '숨은 줄인가'를 판다.
 */
function floorFoldCut(count: number, all: boolean): number {
  return all ? 0 : Math.max(0, count - LIST_FOLD_AT);
}

/** 다음 그림이 그려진 뒤에 부른다(jsdom 처럼 requestAnimationFrame 이 없으면 setTimeout). */
function afterPaint(cb: () => void) {
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(cb);
  else setTimeout(cb, 0);
}

/**
 * 긴 목록의 「전부 보기」/「접기」 단추(S2). 펼친 뒤에도 같은 자리에 남아 다시 접는다(👤 "둔다").
 * 접을 때는 그 카드 머리가 화면 안에 오게 굴린다 — 긴 목록 아래에서 접으면 화면이 엉뚱한 카드에 가 있다.
 * ⛔ 종이에는 안 나온다(`@media print` · 누르는 장치).
 */
function ListFoldButton({
  expanded,
  controls,
  moreText,
  lessText,
  onToggle,
}: {
  expanded: boolean;
  /** 이 단추가 펼치고 접는 목록의 id. */
  controls: string;
  moreText: string;
  lessText: string;
  onToggle: (expanded: boolean) => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  return (
    <button
      ref={ref}
      type="button"
      className="list__fold"
      aria-expanded={expanded}
      aria-controls={controls}
      onClick={() => {
        onToggle(!expanded);
        if (expanded) {
          // 줄이 줄어든 **뒤에** 재야 자리가 맞다. jsdom 에는 scrollIntoView 가 없어 `?.`.
          const head = ref.current?.closest('.card')?.querySelector('.card__h');
          afterPaint(() => head?.scrollIntoView?.({ block: 'nearest' }));
        }
      }}
    >
      {expanded ? lessText : moreText}
    </button>
  );
}

export function FloorStack({
  building,
  viewerRole = null,
  founderChip = FOUNDER_CHIP_ALL,
  onBeforePrint,
  unitPrintMode = 'none',
  unitPrintOpenSignal = 0,
  onUnitListedCount,
  dongs = null,
  sigunguName = null,
  onSelectBuilding,
  onFindInSigungu,
}: Props) {
  const plans = sectionPlansFor(viewerRole);
  const [floors, setFloors] = useState<FloorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openFloor, setOpenFloor] = useState<number | null>(null);
  /** 층 목록을 「전부 보기」로 펼쳤나(S2). 건물이 바뀌면 다시 처음 10줄 — 주소·이 기기에 남기지 않는다. */
  const [floorsAll, setFloorsAll] = useState(false);
  const floorsListId = useId();
  /** 지금 화면에서 숨은 위층 줄의 수(앞쪽 index < 이 값). */
  const floorCut = floorFoldCut(floors.length, floorsAll);
  /** 그 층이 **접힌 창**에서 숨는 줄인가(지금 펼쳐져 있어도 접힌 기준으로 판다). null·없는 층 = 아니다. */
  const isFloorFolded = (no: number | null) => {
    if (no === null) return false;
    const idx = floors.findIndex((f) => f.floor_no === no);
    return idx >= 0 && idx < floorFoldCut(floors.length, false);
  };
  /** 각주에 쓸 집계. 건물과 무관하므로 처음 한 번만 읽는다. */
  const [stats, setStats] = useState<CoverageStats | null>(null);
  /** 이 건물이 속한 상권. 못 읽으면 null로 남고, 그때는 그 줄을 아예 그리지 않는다. */
  const [districts, setDistricts] = useState<BuildingDistricts | null>(null);
  /** 이 땅에서 신고된 실거래(Stage A). 대부분의 건물에서 빈 배열이 정상이다. */
  const [txs, setTxs] = useState<ParcelTransaction[] | null>(null);
  /** 이 구의 층대별 단가 분포(Stage A). 못 읽으면 null로 남고 그 블록만 안 그린다. */
  const [txStats, setTxStats] = useState<SigunguTxStat[] | null>(null);
  /**
   * 이 필지의 층별 국세청 기준시가. null = 아직 안 왔거나 못 읽음. 『층별 공표값 나란히』와 역할 요약 판(투자자)이 쓴다.
   *
   * ⓘ "못 읽음"을 따로 두지 않는다 — 둘 다 **그 칸을 '–' 로 두는 것**으로 끝나기 때문이다.
   *   상태를 하나 더 만들면 쓰는 곳 없이 갈래만 는다.
   */
  const [basePrices, setBasePrices] = useState<BasePrice[] | null>(null);
  /** 기준시가 조회가 실패했나 — 층별 공표값 칸 머리의 이유 줄이 「불러오지 못했습니다」와 「상가 기준시가 없음」(빈 배열)을 가른다(👤 2026-10-18 ②). */
  const [basePricesFailed, setBasePricesFailed] = useState(false);
  /**
   * 이 건물의 층별 호실 요약(결정 0032). null = 아직 안 왔거나 **못 읽음** — 그때는 요약 줄도
   * "자료 없음" 안내도 안 그린다. 빈 배열 = 물어봤더니 호실 자료가 없는 건물(안내가 선다).
   */
  const [unitSummary, setUnitSummary] = useState<UnitFloorSummary[] | null>(null);
  /**
   * 이 땅의 개별공시지가(결정 0036 결정 7). null = 아직 안 왔거나 **못 읽음·값 없음** — 셋 다 줄을
   * 안 그리는 것으로 끝나므로 상태를 가르지 않는다('자료 없음'이라 적지 않는다).
   */
  const [landPrice, setLandPrice] = useState<ParcelLandPrice | null>(null);
  /**
   * 층 목록 카드를 **펼치라고 부르는 신호**. 호실 구성표 고르기가 1씩 올린다.
   *
   * ⛔ 이게 없으면 사용자가 층 목록을 접어 둔 상태에서 고른 층이 **접힌 카드 안에** 있어
   *    눌렀는데 화면이 안 변한다 — 사람은 고장 났다고 읽는다.
   */
  const [floorsOpenSignal, setFloorsOpenSignal] = useState(0);
  /**
   * 곁 카드(업종 분포·둘레 인허가·임대 동향·개업·폐업) 요청을 건물을 고른 순간 먼저 보내 둔 것.
   * 카드들은 층 목록이 온 뒤에야 마운트되므로, 여기서 먼저 보내 두면 그만큼 일찍 온다
   * (`lib/sidePrefetch.ts` · 로드맵 속도 P3).
   *
   * ⓘ ref 에도 담아 두는 이유: 개발 모드(StrictMode)는 effect 를 두 번 돌리는데, 같은 필지면
   *   ref 의 것을 다시 쓰게 해 **요청이 두 번 나가지 않게** 한다. 화면에 넘기는 것은 state 다.
   */
  const sidePrefetchRef = useRef<SidePrefetch | null>(null);
  const [sidePrefetch, setSidePrefetch] = useState<SidePrefetch | null>(null);
  /** 호실 구성표 고르기로 받은 층별 첫 쪽 호 목록(물결 1-C2). 실패한 층은 아예 안 담는다(그 층만 빠진다). */
  const [printedUnits, setPrintedUnits] = useState<ReadonlyMap<number, PrintedUnits>>(new Map());
  /**
   * 고른 층들을 받는 진행 — 전체 층 수 · 끝난 층 수(이미 받아 둔 층 포함) · 못 받은 층 수.
   * 화면에만 「불러오는 중 (12/30층)」, 끝난 뒤 실패가 있으면 그 수를 한 줄(화면·종이).
   */
  const [unitLoad, setUnitLoad] = useState({ total: 0, done: 0, failed: 0 });
  /** effect 안에서 '이미 받아 둔 층'을 읽는 거울 — 바꾼 고르기에서 받은 층을 버리지 않고 다시 쓴다(깜빡임 0). */
  const printedRef = useRef<ReadonlyMap<number, PrintedUnits>>(new Map());
  const unitPlan = unitPrintPlan(
    unitSummary,
    floors.map((f) => f.floor_no),
    unitPrintMode,
  );
  // effect 의존을 글자 하나로 — 배열은 그릴 때마다 새 물건이라 그대로 넣으면 끝없이 다시 부른다.
  const unitPlanKey = unitPlan.floors.join(',');

  useEffect(() => {
    let cancelled = false;
    supabase
      .from(COVERAGE_STATS_VIEW)
      .select('*')
      .limit(1)
      .then(({ data, error: err }) => {
        if (cancelled) return;
        if (err || !data || data.length === 0) {
          // 각주 숫자는 없어도 화면 본체는 정상이다. 실패해도 옛 숫자를 되살리지 않는다
          // — 틀린 숫자를 보여주는 것이 숫자를 안 보여주는 것보다 나쁘다.
          console.warn('각주 집계 조회 실패 — 숫자 없이 표시합니다', err);
          return;
        }
        const row = data[0] as CoverageStats;
        setStats({
          snapshot_ym: row.snapshot_ym,
          store_cnt: Number(row.store_cnt),
          floor_missing_cnt: Number(row.floor_missing_cnt),
          floor_missing_pct: Number(row.floor_missing_pct),
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setOpenFloor(null);
    setFloorsAll(false);

    supabase
      .from(FLOOR_STACK_VIEW)
      .select('*')
      .eq('bld_id', building.bld_id)
      .order('floor_no', { ascending: false })
      .then(({ data, error: err }) => {
        if (cancelled) return;
        if (err) {
          // 원문에는 내부 표 이름이 섞여 나올 수 있다 — 콘솔에만 남긴다.
          console.error('층 정보 조회 실패', err);
          setError('층 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
        } else setFloors((data ?? []) as FloorRow[]);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [building.bld_id]);

  // 곁 카드 요청을 지금 출발시킨다 — 층 목록을 기다리지 않는다. 보관은 이 필지 한 벌뿐이라
  // 건물이 바뀌면 옛 것은 버려진다(카드도 pnu 가 다른 결과는 받지 않는다).
  useEffect(() => {
    if (sidePrefetchRef.current?.pnu !== building.pnu) {
      sidePrefetchRef.current = startSidePrefetch(building.pnu);
    }
    setSidePrefetch(sidePrefetchRef.current);
  }, [building.pnu]);

  useEffect(() => {
    let cancelled = false;
    // 건물이 바뀌는 순간 옛 상권을 지운다 — 안 지우면 새 건물 밑에 앞 건물의 상권이
    // 잠깐 붙어 보인다(그 짧은 순간이 그대로 틀린 정보다).
    setDistricts(null);

    supabase.rpc(BUILDING_DISTRICTS_FN, { bld_id: building.bld_id }).then(({ data, error: err }) => {
      if (cancelled) return;
      if (err || !data) {
        // 각주 집계와 같은 철학이다 — 이 줄이 없어도 화면 본체(층 목록)는 정상이다.
        // 못 읽었을 때 "상권 없음"이라고 적으면, 모르는 것을 아는 것처럼 말하게 된다.
        console.warn('상권 조회 실패 — 상권 줄 없이 표시합니다', err);
        return;
      }
      setDistricts(data as BuildingDistricts);
    });

    return () => {
      cancelled = true;
    };
  }, [building.bld_id]);

  // ── 호실 구성표 (결정 0032) ──────────────────────────────────────────────
  //
  // ⛔ 의존은 `[building.bld_id]` 다 — 기준시가처럼 `[building.pnu]` 로 두면 같은 땅 다른 동으로
  //    옮길 때 다시 안 부른다(지금은 App.tsx 의 key=bld_id 재마운트가 가려 줄 뿐이다).
  // ⛔ 곁 카드 미리 부르기(`sidePrefetch`)에 끼우지 않는다 — 그 보관 열쇠가 pnu 라 옆 동과 섞인다.
  // ⛔ 실패(함수 없음 PGRST202 포함)와 0줄을 섞지 않는다 — 실패면 null 로 남아 요약도 "자료
  //    없음" 안내도 안 그린다. 실패를 "자료 없음"이라 적으면 모르는 것을 없다고 말하게 된다.
  useEffect(() => {
    let cancelled = false;
    setUnitSummary(null);

    supabase.rpc(UNIT_FLOOR_SUMMARY_FN, { p_bld_id: building.bld_id }).then(({ data, error: err }) => {
      if (cancelled) return;
      const rows = err ? null : parseUnitSummary(data);
      if (rows === null) {
        console.warn('호실 요약 조회 실패 — 요약 없이 표시합니다', err);
        return;
      }
      setUnitSummary(rows);
    });

    return () => {
      cancelled = true;
    };
  }, [building.bld_id]);

  // ── 호실 구성표 고르기 (결정 0036 결정 8 · 물결 1-C2) ─────────────────────────
  //
  // ⛔ 부르는 층은 `unitPrintPlan` 이 정한다 — 호 목록이 있는 층만(주거·오피스텔·미상 층은 요청 0) ·
  //    층마다 첫 쪽(offset 0) · 동시에 4개까지 · '전부'는 아래층부터 30개 층까지.
  // ⛔ 실패한 층은 그 층만 빠진다(다른 층은 선다) — 층마다 '못 불러왔습니다'를 늘어놓지 않고, 다 끝난 뒤
  //    못 받은 층 수만 한 줄로 적는다(화면·종이 · 👤 2026-10-11).
  // ⓘ 고르기를 바꿔도(지하~3층 → 전부) 이미 받은 층은 버리지 않고 다시 쓴다 — 새 계획에 없는 층만 지운다.
  // ⛔ 늦은 답 가드 `cancelled` — 고르기를 바꾼 뒤 옛 고르기의 답이 오면 버린다(지우면 '넣지 않음'으로 돌린
  //    뒤에도 목록이 되살아난다 · FloorStack.test 가 잡는다).
  useEffect(() => {
    const targets = unitPlanKey === '' ? [] : unitPlanKey.split(',').map(Number);
    const keep = new Map([...printedRef.current].filter(([no]) => targets.includes(no)));
    printedRef.current = keep;
    setPrintedUnits(keep);
    const toFetch = targets.filter((no) => !keep.has(no));
    setUnitLoad({ total: targets.length, done: targets.length - toFetch.length, failed: 0 });
    if (toFetch.length === 0) return;
    let cancelled = false;
    void runLimited(
      toFetch,
      UNIT_PRINT_CONCURRENCY,
      async (floorNo) => {
        let ok = false;
        try {
          const { data, error: err } = await supabase.rpc(FLOOR_UNITS_FN, {
            p_bld_id: building.bld_id,
            p_floor_no: floorNo,
            p_limit: FLOOR_UNITS_PAGE,
            p_offset: 0,
          });
          if (cancelled) return;
          const rows = err ? null : parseFloorUnits(data);
          if (rows === null) {
            console.warn('호실 구성표 — 이 층 목록을 못 받아 빼고 표시합니다', floorNo, err);
            return;
          }
          ok = true;
          const next = new Map(printedRef.current).set(floorNo, {
            units: rows,
            total: rows[0]?.total_cnt ?? 0,
          });
          printedRef.current = next;
          setPrintedUnits(next);
        } finally {
          if (!cancelled) {
            setUnitLoad((l) => ({ ...l, done: l.done + 1, failed: l.failed + (ok ? 0 : 1) }));
          }
        }
      },
      () => cancelled,
    );
    return () => {
      cancelled = true;
    };
  }, [building.bld_id, unitPlanKey]);

  // 손님이 직접 고를 때만 층 목록 카드를 펼친다(기본값으로는 안 펼친다 — 위 prop 머리말).
  useEffect(() => {
    if (unitPrintOpenSignal > 0) setFloorsOpenSignal((n) => n + 1);
  }, [unitPrintOpenSignal]);
  /*
    손님이 직접 고른 순간(신호가 바뀐 그림) 고른 층 중 하나라도 숨은 위층이면 층 목록을 '전부'로 — 안 그러면 받은 호
    목록이 숨은 줄에 붙어 화면에서 안 보인다(S2 검사 맹점 B · 종이에는 늘 나온다). 신호와 고르기는 App 이 한 번에 바꾸므로
    같은 그림의 고르기를 읽는다. ⓘ 그리는 도중에 상태를 맞추는 React 공식 꼴(SectionCard 와 같은 꼴) — 층·고르기가 바뀔
    때마다 다시 펼치지 않고 신호가 바뀐 그 한 번만 판다.
  */
  const [seenUnitSignal, setSeenUnitSignal] = useState(unitPrintOpenSignal);
  if (seenUnitSignal !== unitPrintOpenSignal) {
    setSeenUnitSignal(unitPrintOpenSignal);
    if (unitPrintOpenSignal > 0 && unitPlan.floors.some((no) => isFloorFolded(no))) setFloorsAll(true);
  }

  // 호 목록이 있는 층 수를 App 에 알린다(0개면 고르기 줄을 숨긴다). 요약을 못 받았으면 알리지 않는다.
  const listedCount =
    unitSummary === null
      ? null
      : unitPrintPlan(unitSummary, floors.map((f) => f.floor_no), 'all').listedCount;
  useEffect(() => {
    if (listedCount !== null) onUnitListedCount?.(building.bld_id, listedCount);
  }, [building.bld_id, listedCount, onUnitListedCount]);

  // ── 개별공시지가 한 줄 (결정 0036 결정 7 · 물결 1-C1) ─────────────────────
  //
  // ⓘ 의존은 `[building.pnu]` 다 — 땅값은 필지 값이라 같은 땅 다른 동이면 같은 값이다(호실 요약과 반대).
  //    ⚠️ 그래도 실제 화면에서는 같은 땅 다른 동으로 옮기면 **다시 부른다** — App 이 건물마다 이 화면을
  //    새로 만든다(`App.tsx` 의 `key={`stack:${selected.bld_id}`}`). 의존을 pnu 로 둔 것은 자가 맞아서지 아끼려는 게 아니다.
  // ⛔ 곁 카드 미리 부르기(`sidePrefetch`)에 끼우지 않는다 — 카드가 아니라 머리 한 줄이다.
  // ⛔ 실패(함수 없음 PGRST202 포함)·0줄·모양 이상은 전부 줄 없음 — '자료 없음'이라 적지 않는다.
  // ⓘ 늦게 온 옛 필지의 답은 `cancelled` 로 버린다(pnu 가 바뀌면 앞 요청의 then 이 아무것도 안 한다).
  useEffect(() => {
    let cancelled = false;
    setLandPrice(null);

    supabase.rpc(LAND_PRICE_FN, { p_pnu: building.pnu }).then(({ data, error: err }) => {
      if (cancelled) return;
      const v = err ? null : parseLandPrice(data);
      if (err) console.warn('개별공시지가 조회 실패 — 그 줄 없이 표시합니다', err);
      setLandPrice(v);
    });

    return () => {
      cancelled = true;
    };
  }, [building.pnu]);

  // ── 실거래 사실 표시 (Stage A · 결정 0012) ────────────────────────────────
  //
  // 두 질문을 따로 던진다. 하나는 "이 땅에서 무슨 거래가 있었나"(대부분 빈 배열이 정답),
  // 다른 하나는 "이 구의 층대별 단가는 어디쯤인가"(항상 답이 있다). 하나가 실패해도
  // 다른 하나는 보여야 하므로 상태도 따로 둔다.
  //
  // ⚠️ 구 코드는 pnu 앞 5자리다 — 화면이 고른 구를 따로 받아 오지 않는다. 건물은
  //    반드시 자기 필지 위에 있으므로 이 값은 어긋날 수가 없고, prop 으로 받으면
  //    "고른 구"와 "건물이 선 구"가 갈라지는 상태를 하나 더 만들게 된다.
  useEffect(() => {
    let cancelled = false;
    setTxs(null);
    setTxStats(null);
    setBasePrices(null);
    setBasePricesFailed(false);

    supabase.rpc(PARCEL_TX_FN, { pnu: building.pnu }).then(({ data, error: err }) => {
      if (cancelled) return;
      if (err || !data) {
        // 못 읽었으면 "거래 없음"이라고 적지 않는다 — 없는 것과 모르는 것은 다르다.
        console.warn('실거래 이력 조회 실패 — 이력 없이 표시합니다', err);
        return;
      }
      setTxs(data as ParcelTransaction[]);
    });

    supabase
      .rpc(SIGUNGU_TX_STATS_FN, { sigungu: building.pnu.slice(0, 5) })
      .then(({ data, error: err }) => {
        if (cancelled) return;
        if (err || !data) {
          console.warn('구 실거래 단가 조회 실패 — 그 블록 없이 표시합니다', err);
          return;
        }
        setTxStats(data as SigunguTxStat[]);
      });

    // ── 국세청 기준시가 ────────────────────────────────────────────────────
    //
    // ⚠️ 인자 이름이 이 함수만 `p_pnu` 다(형제 둘은 pnu·sigungu — 컬럼명 `pnu` 와 겹친다).
    //    목은 인자 이름을 안 보므로 습관대로 `{ pnu: … }` 로 부르면 테스트는 전부 초록인 채
    //    **라이브에서만** PGRST202 가 난다.
    // ⓘ 못 읽었으면 그 칸만 '–' 이고, 칸 머리 아래에 「기준시가를 불러오지 못했습니다」 한 줄(빈 배열의 「상가 기준시가 없음」과 섞지 않는다).
    supabase.rpc(BASE_PRICES_FN, { p_pnu: building.pnu }).then(({ data, error: err }) => {
      if (cancelled) return;
      if (err || !Array.isArray(data)) {
        console.warn('기준시가 조회 실패 — 그 줄 없이 표시합니다', err);
        setBasePricesFailed(true);
        return;
      }
      setBasePrices(data as BasePrice[]);
    });

    return () => {
      cancelled = true;
    };
  }, [building.pnu]);

  /*
    h1 글 = 건물 이름 + 같은 땅 동 구분(결정 0042 보완 F3 — 첫 HTML h1·탭 제목과 같은 `dongSuffix` · 동 목록은 App 이 이미 받는다 ·
    동이 하나면 이름 그대로). 일찍 끝나는 갈래(불러오는 중·오류·층 0개)도 이 h1 을 그린다 — 건물을 연 동안 App 은 사이트 이름을
    p 로 내리므로 여기서 안 그리면 h1 이 0개가 된다(보완 F4).
  */
  const dongLabel =
    dongs && building.bld_cnt_in_pnu > 1 ? dongSuffix(building.bld_id, dongs, building.bld_cnt_in_pnu) : null;
  const titleText = (name: string | null | undefined) =>
    [name?.trim() || null, dongLabel].filter(Boolean).join(' ') || '(이름 없는 건물)';
  const bareTitle = <h1 className="stack__title">{titleText(building.bld_nm)}</h1>;

  if (loading)
    return (
      <>
        {bareTitle}
        <p className="msg msg--loading">층 정보를 불러오는 중…</p>
      </>
    );
  if (error)
    return (
      <>
        {bareTitle}
        <p className="msg msg--error">{error}</p>
      </>
    );
  if (floors.length === 0)
    return (
      <>
        {bareTitle}
        <p className="msg">이 건물에는 층 정보가 없습니다.</p>
      </>
    );

  const head = floors[0];
  const roadContact = displayRoadContact(head.road_contact);
  // 물결 2-1 머리 칸(2026-10-12). null 이면 칸을 안 그린다 — 뜻풀이는 lib/format.ts 한 곳.
  const structure = describeStructure(head.strct_nm);
  // 승강기 합 0 의 갈림(6층 이상만 '미상')에 쓰는 지상 최고층 — 검색·링크 되살리기와 같은 규칙(옥탑 99 제외).
  const topFloor = buildingFromFloorRows(floors)?.max_floor ?? null;
  const elevator = describeElevator(head.elevator_ride, head.elevator_emgen, true, topFloor);
  const ledgerHo = describeHoCnt(head.is_jiphap, head.ho_cnt, head.bld_main_use);
  const maxArea = Math.max(...floors.map((f) => f.floor_area_m2 ?? 0), 1);
  const totalStores = floors.reduce((sum, f) => sum + (f.store_cnt ?? 0), 0);

  // 층 뱃지용 — 어느 층에서 몇 건이 신고됐나. 층이 없는 거래(2017년부터 흔하다)는 어느
  // 층에도 붙일 수 없으니 여기서 세지 않는다. 대신 아래 목록에 "층 미상"으로 그대로 남는다
  // — 세지 못한 것을 목록에서까지 지우면 건수가 조용히 줄어든다.
  const txCountByFloor = new Map<number, number>();
  for (const t of txs ?? []) {
    if (t.floor_no === null) continue;
    txCountByFloor.set(t.floor_no, (txCountByFloor.get(t.floor_no) ?? 0) + 1);
  }

  // 호실 요약을 층 번호로 짝짓는다(결정 0032). 인덱스로 맞추면 층이 어긋난다 — 층 목록은
  // 층별개요에서, 요약은 호실 표에서 오므로 서로 없는 층이 있다. 붙을 자리가 없는 호실은
  // 카드 맨 아래 한 줄로 따로 센다(조용히 사라지지 않게).
  const unitByFloor = new Map<number, UnitFloorSummary>();
  for (const u of unitSummary ?? []) {
    if (u.floor_no !== null) unitByFloor.set(u.floor_no, u);
  }
  const orphanLine =
    unitSummary && unitSummary.length > 0
      ? orphanUnitsText(orphanUnits(unitSummary, floors.map((f) => f.floor_no)))
      : null;
  // 각주·등급 문장은 **층 줄에 실제로 붙은 요약**을 보고 세운다(요약 표에 줄이 있다는 것만으로는
  // 안 된다 — 주거 층뿐인 아파트에 '보통'·면적 곱셈 안내가 뜨거나, 층 줄에 못 붙고 따로 떨어진
  // 호실뿐인 건물에 복층 각주가 뜬다).
  //   · 면적을 적는 요약(목록 제공 층 commercial·mixed)이 하나라도 붙었나 → '보통' 각주 · 등급 문단 보탬
  //   · 어떤 요약이든 층 줄에 하나라도 붙었나 → 복층 각주
  const attachedUnits = floors
    .map((f) => unitByFloor.get(f.floor_no))
    .filter((u): u is UnitFloorSummary => u !== undefined);
  const hasAttachedUnits = attachedUnits.length > 0;
  const hasListedUnits = attachedUnits.some((u) => hasUnitList(u.floor_kind));

  // 각주 숫자는 DB에서 계산해 온다. 못 불러왔으면 숫자를 빼고 경고만 남긴다
  // — 옛 숫자로 되돌리면 이 코드가 고치려던 문제(화면만 틀려지는 것)가 그대로 살아난다.
  // 글은 `floorMissingPhrase` 하나에서 — 역할 요약 판의 1층 칸이 같은 글을 쓴다(결정 0039 W2).
  const missingPhrase = floorMissingPhrase(stats?.floor_missing_pct) ?? '적지 않은 수';
  // "서비스 지역"을 밝히는 이유: 뷰가 세는 범위가 **지금 볼 수 있는 구**뿐이다(2026-08-22a).
  // 예전에는 전국을 세서, 화면이 보여주지도 않는 지역까지 섞인 숫자를 각주가 말했다.
  const basisPhrase = stats
    ? `근거: ${formatQuarter(stats.snapshot_ym)} 상권정보 중 서비스 지역(지금 볼 수 있는 구) ${stats.store_cnt.toLocaleString('ko-KR')}곳 기준.`
    : '근거: 서비스 지역(지금 볼 수 있는 구)의 상권정보 최신 분기 기준.';

  /*
    여기부터가 **층별 화면 카드**다(로드맵 Wave 2 『한 장 요약 접힘 틀』).
    제목·역할 태그·기본 펼침은 전부 `SECTION_PLAN` 한 표에서 온다 — 카드마다 따로
    정하면 "첫 화면에 몇 장이 펼쳐져 있나"를 아무 데서도 셀 수 없어 상한(4장)이
    조용히 깨진다.
    역할을 고르면 **순서·펼침만** `ROLE_SECTION_LAYOUT` 이 덮어쓴다(결정 0036 결정 18) — 그래서
    카드를 여기 이름으로 담아 두고, 그리는 차례는 아래 `sectionOrder` 가 정한다.
    ⓘ 그릴 때 key 를 카드 이름으로 준다 — 역할을 바꿔도 카드는 **자리만 옮기고** 받아 둔
      자료를 그대로 쓴다(새로 묻지 않는다). 펼침은 `SectionCard` 가 새 표대로 다시 세운다.
  */
  const cards: Record<SectionKey, ReactNode> = {
    district: <DistrictCard info={districts} plan={plans.district} />,
    floors: (
      <SectionCard
        plan={plans.floors}
        className="card--floors"
        summary={`층 ${floors.length}개 · 점포 ${totalStores.toLocaleString('ko-KR')}곳`}
        openSignal={floorsOpenSignal}
      >
        {head.bld_cnt_in_pnu > 1 && (
          <p className="warn">
            <strong>이 땅에 건물이 {head.bld_cnt_in_pnu}동 있습니다.</strong> 점포는 호수가
            아니라 “땅 + 층”으로만 붙일 수 있어서(상권정보에 호 정보가 없음), 아래 점포 목록에
            옆 동 점포가 섞여 보일 수 있습니다.
          </p>
        )}

        {/*
          업종 요약. 헤더에 붙는 말이지만 자리는 **위 경고 아래**여야 한다 — 이 숫자는
          점포를 "땅 + 층"으로 붙여 센 것이라 옆 동 점포가 그대로 섞여 있다. 요약을 경고보다
          위에 두면 사람이 먼저 숫자를 읽고 그다음에야 "섞여 있다"는 말을 만나게 되는데,
          그 순서로는 이미 읽은 숫자가 안 고쳐진다. 자리를 바꾸지 말 것.
        */}
        <BizSummary floors={floors} />

        {/* '전부'인데 층이 상한보다 많으면 그렇다고 적는다(종이에도 · 👤 글자). */}
        {unitPlan.capped && (
          <p className="floor__unitprint-cap">{unitPrintCapText(unitPlan.listedCount)}</p>
        )}
        {/* 받는 동안 화면에만(종이에서 빠진다) · 끝난 뒤 못 받은 층이 있으면 그 수(화면·종이). */}
        {unitLoad.done < unitLoad.total && (
          <p className="floor__unitprint-loading">{unitPrintLoadingText(unitLoad.done, unitLoad.total)}</p>
        )}
        {unitLoad.done >= unitLoad.total && unitLoad.failed > 0 && (
          <p className="floor__unitprint-failed">{unitPrintFailedText(unitLoad.failed)}</p>
        )}

        {/* 아래 10줄 창의 단추는 목록 **맨 위**(숨은 위층이 단추 바로 아래에서 펼쳐진다 · 👤 그림). */}
        {floors.length > LIST_FOLD_AT && (
          <ListFoldButton
            expanded={floorsAll}
            controls={floorsListId}
            moreText={`위층 전부 보기 (${(floors.length - LIST_FOLD_AT).toLocaleString('ko-KR')}개 층 더)`}
            lessText="층 목록 접기"
            onToggle={(next) => {
              setFloorsAll(next);
              // 접으면 숨는 줄에 열린 층이 있으면 닫는다 — 안 그러면 안 보이는 층이
              // '펼쳐져 있음'으로 남는다(검사 맹점 C).
              if (!next && isFloorFolded(openFloor)) setOpenFloor(null);
            }}
          />
        )}
        <ol className="floors" id={floorsListId}>
          {floors.map((f, i) => {
            // 면적이 아예 없는 층(그 층이 전부 연면적 제외분 — 전체의 약 3%)에는 막대를
            // 그리지 않는다. 최소 폭 2%를 강제하면 "면적 미상"이 "아주 좁은 층"처럼 보인다.
            const hasArea = f.floor_area_m2 != null;
            const ratio = hasArea ? f.floor_area_m2! / maxArea : 0;
            const isOpen = openFloor === f.floor_no;
            const txCount = txCountByFloor.get(f.floor_no) ?? 0;
            const unitRow = unitByFloor.get(f.floor_no);
            // 호 목록이 든 채 펼쳐진 층 — 종이에서는 이 층만 줄 단위로 끊는다(50~200줄이면 한 장보다 크다).
            const unitsOpen = isOpen && unitRow !== undefined && hasUnitList(unitRow.floor_kind);
            // 고르기로 받은 호 목록 — 이미 펼친 층(상세의 호 목록)과 겹치면 한 벌만(상세 쪽).
            const printed = unitsOpen ? undefined : printedUnits.get(f.floor_no);
            return (
              // 옥탑도 지하와 같은 "근거 없는 층"이라 색으로 갈라 둔다(결정 0001 가드 4).
              // id 는 이 층을 바로 찾을 때 쓰는 이름표다(`floor--1` = 지하 1층).
              <li
                key={f.floor_no}
                id={`floor-${f.floor_no}`}
                className={`floor${
                  f.floor_no < 0 ? ' floor--under' : f.floor_no === 99 ? ' floor--roof' : ''
                }${unitsOpen ? ' floor--units-open' : ''}${printed ? ' floor--unitprint' : ''}${
                  // 아래 10줄만 남기고 위층 줄은 펼치기 전까지 화면에서만 숨는다(S2 — 종이에는 늘 전부).
                  i < floorCut ? ' list__folded' : ''
                }`}
              >
                {/*
                  층 줄 + 호실 요약 둘째 줄을 한 덩어리로 묶는다 — 종이에서 둘이 갈리지 않게.
                  ⓘ 요약은 버튼 **밖**에 둔다. 버튼 안에 넣으면 층 줄의 칸 수(좁은 화면에서는 줄 수)가
                    늘고, 버튼 이름에 요약 글이 섞인다.
                */}
                <div className="floor__head">
                  <button
                    className="floor__row"
                    onClick={() => setOpenFloor(isOpen ? null : f.floor_no)}
                  >
                    <span className="floor__label">{formatFloor(f.floor_no, f.floor_label)}</span>
                    <span className="floor__bar">
                      {hasArea && (
                        <span
                          className="floor__fill"
                          style={{ width: `${Math.max(ratio * 100, 2)}%` }}
                        />
                      )}
                    </span>
                    <span className="floor__use">{f.main_use || '용도 미상'}</span>
                    <span className="floor__area">{formatArea(f.floor_area_m2)}</span>
                    <span className="floor__stores">
                      {f.store_cnt != null ? `점포 ${f.store_cnt}` : '—'}
                    </span>
                    {/*
                      거래가 있는 층에만 뱃지를 단다. 0건일 때 "거래 0건"이라고 적으면
                      "이 층은 안 팔린다"는 단정이 되는데, 실제로는 지번이 가려진 거래·층이
                      빠진 거래가 그 밑에 깔려 있다(칸은 비워 두되 자리는 남긴다).
                    */}
                    <span className="floor__tx">{txCount > 0 ? `거래 ${txCount}건` : ''}</span>
                    <span className="floor__caret">{isOpen ? '▲' : '▼'}</span>
                  </button>
                  {unitRow && <p className="floor__units">{unitSummaryText(unitRow)}</p>}
                </div>

                {printed && <PrintedUnitList printed={printed} />}

                {isOpen && (
                  <FloorDetail floor={f} bldId={building.bld_id} unitRow={unitRow} />
                )}
              </li>
            );
          })}
        </ol>

        {/*
          호실 구성표의 카드 맨 아래 줄들(결정 0032).
          ⛔ `unitSummary === null`(아직 안 옴 · 실패 · 함수 없음)이면 아무것도 안 그린다 —
             실패를 "자료 없음"이라 적으면 거짓이다. 빈 배열일 때만 "자료 없음" 안내가 선다.
        */}
        {orphanLine && <p className="floor__units-orphan">{orphanLine}</p>}
        {hasAttachedUnits && (
          <p className="floor__units-note">
            {hasListedUnits && <>{UNIT_MEDIAN_NOTE} </>}
            {UNIT_MULTI_FLOOR_NOTE}
          </p>
        )}
        {unitSummary !== null && unitSummary.length === 0 && (
          <p className="floor__units-none">
            {noUnitDataText(head.is_jiphap, head.bld_cnt_in_pnu)}
          </p>
        )}
      </SectionCard>
    ),
    /*
      둘레의 업종 분포(결정 0014). 자기가 알아서 묻고, 못 읽으면 스스로 사라진다
      — 마이그레이션 적용 전 라이브에서는 함수가 없어(PGRST202) 그 상태가 된다.

      ⚠️ 여기 숫자는 **이 건물만의 점포가 아니다** — 이 땅 둘레(속한 상권 · 반경 500m)의
         이웃 가게까지 센 것이고 이 건물 것도 그 안에 포함된다. 바로 위 층 목록의 점포
         칸과 세는 대상이 다르므로 두 숫자를 견주면 안 된다.
      ⓘ 역할을 고르기 전·창업자 차례에서는 층 목록 **바로 아래**에 붙어 있어 눈으로는
         이어져 보인다. 그래서 갈라 놓는 일은 자리가 아니라 **말**이 한다 — 섹션 제목("둘레의")과 첫 줄("이 건물만이
         아니라…")이 그 장치다. 자리를 옮겨 해결한 것이 아니니 그 문구를 지우지 말 것.
    */
    industry: (
      <IndustryMixSection
        pnu={building.pnu}
        prefetch={sidePrefetch}
        plan={plans.industry}
        chip={founderChip}
      />
    ),
    tx: <TransactionSection txs={txs} stats={txStats} plan={plans.tx} bldId={building.bld_id} />,
    /*
      층별 공표값 나란히(결정 0036 결정 15 · 물결 1-C2 → 결정 0041 — 내린 참고 매매 시세 카드의 자리). 이미 받은
      기준시가·구 단가를 그대로 넘기고, 부동산원 조사값은 임대 카드와 같은 미리 보낸 답을 카드가 스스로 받는다. ⛔ 비율 계산 0.
    */
    floorgap: (
      <FloorGapSection
        floors={floors}
        basePrices={basePrices}
        basePricesFailed={basePricesFailed}
        txStats={txStats}
        pnu={building.pnu}
        prefetch={sidePrefetch}
        noCoord={lacksCoord(building)}
        plan={plans.floorgap}
      />
    ),
    /*
      상권 임대 동향(결정 0024). 자기가 알아서 묻고, 못 읽으면 스스로 사라진다
      — 마이그레이션 적용 전 라이브에서는 함수가 없어(PGRST202) 그 상태가 된다.

      ⚠️ 대상이 이 건물이 아니라 이 건물이 속한 상권이다 — 다른 카드의 값과 **한 줄에 섞거나
         서로 견주는 문구를 쓰지 않는다**(카드 안의 첫 줄과 등급 문단이 그 경계를 지킨다).
    */
    rent: (
      <RentStatSection
        pnu={building.pnu}
        prefetch={sidePrefetch}
        noCoord={lacksCoord(building)}
        plan={plans.rent}
      />
    ),
    /*
      상권 개업·폐업(결정 0033 — 서울시 공표 그대로). 임대 카드와 같은 뼈대 — 스스로 묻고,
      못 읽으면(함수 없음 PGRST202·모양 이상) 스스로 사라진다. 서울 밖·상권 밖이면 카드는
      서서 그렇다고 적는다. ⛔ 이 건물이 아니라 속한 서울시 상권 전체의 값이다.
    */
    openclose: (
      <OpenCloseSection
        pnu={building.pnu}
        prefetch={sidePrefetch}
        plan={plans.openclose}
        chip={founderChip}
      />
    ),
    /*
      빈 카드 셋(결정 0036 결정 2 · 물결 1-B). ⛔ 아무것도 부르지 않는다 — `sidePrefetch` 도 안 받는다.
      자료가 들어오면 그 카드만 제 컴포넌트로 바꾼다.
    */
    sales: <EmptySection kind="sales" pnu={building.pnu} plan={plans.sales} />,
    pop: <EmptySection kind="pop" pnu={building.pnu} plan={plans.pop} />,
    history: <EmptySection kind="history" pnu={building.pnu} plan={plans.history} />,
  };

  /*
    내부 링크 줄(결정 0042 H5) — 같은 땅 다른 동(동 목록이 이 땅 것이고 2줄 이상일 때만)과 구 코드.
    실을 동 = 자기 차례 앞뒤 창(`siblingWindow` — 첫 HTML 과 같은 함수 · 보완 F2) · 「외 N동」의 N 도 같은 셈(`moreDongCount`).
  */
  const shownDongs = dongs && head.bld_cnt_in_pnu > 1 ? siblingWindow(building.bld_id, dongs) : [];
  const moreDongs = dongs && shownDongs.length > 0 ? moreDongCount(head.bld_cnt_in_pnu, dongs, shownDongs.length) : 0;
  const sggCode = building.pnu.slice(0, 5);

  return (
    <section className="stack">
      {/*
        역할 요약 판(결정 0039 W2) — 건물 머리 **위**(첫 3초에 보이게). 역할이 없으면 아무것도 안 그린다.
        ⓘ 층 행이 이 건물 것이 아니면(건물이 바뀐 첫 그림) 판이 스스로 안 그린다(`roleSummaryView`) · 곁 카드 값은 판이 pnu 로 대조한다.
      */}
      <RoleSummary
        role={viewerRole}
        chip={founderChip}
        building={building}
        floors={floors}
        stats={stats}
        txs={txs}
        txStats={txStats}
        basePrices={basePrices}
        landPrice={landPrice}
        noCoord={lacksCoord(building)}
        prefetch={sidePrefetch}
        onBeforePrint={onBeforePrint}
      />
      <header className="stack__head">
        {/* 건물을 연 동안 이 이름이 화면의 h1(결정 0042 H1 — 사이트 이름은 App 머리에서 p 로 내려간다 · h1 은 정확히 1개). */}
        <h1 className="stack__title">{titleText(head.bld_nm)}</h1>
        <p className="stack__addr">{head.road_addr || '주소 없음'}</p>
        <dl className="stack__facts">
          <div>
            <dt>사용승인</dt>
            <dd>{formatApproveDate(head.approve_date)}</dd>
          </div>
          <div>
            <dt>건물 종류</dt>
            {/* null 은 '미상'(결정 0036 결정 18 ⑦) — 모르는 것을 '일반건물'로 단정하지 않는다. */}
            <dd>{formatJiphap(head.is_jiphap) ?? UNKNOWN_SPEC}</dd>
          </div>
          <div>
            <dt>층 수</dt>
            <dd>{floors.length}개</dd>
          </div>
          <div>
            <dt>점포(참고)</dt>
            <dd>{totalStores.toLocaleString('ko-KR')}곳</dd>
          </div>
          {/*
            도로접면은 토지특성 원문 그대로다(displayRoadContact 주석 참조). 값이 없거나
            '맹지'·'지정되지않음'이면 이 칸 자체가 안 생긴다 — 빈 칸을 남기면 "조사했는데
            아무것도 아니었다"처럼 읽힌다.
          */}
          {roadContact && (
            <div>
              <dt>도로접면</dt>
              <dd>{roadContact}</dd>
            </div>
          )}
          {/*
            건물 스펙 4칸(로드맵 Wave 2 PR-B). 도로접면과 달리 **값이 없어도 칸을 지우지
            않는다** — 이 넷은 건물을 볼 때 으레 찾는 항목이라, 칸이 없으면 사람은
            "안 나온다"가 아니라 "이 화면은 그걸 안 보여준다"로 읽고 다른 데를 찾아간다.
            "미상"이라고 적어 두면 그게 우리가 아는 전부라는 사실 자체가 정보가 된다.
            ⛔ 0 을 값으로 적지 않는 이유는 UNKNOWN_SPEC 주석 참조(0 = 대장 미기재).
          */}
          <div>
            <dt>연면적</dt>
            <dd>{describeSpec(head.total_area_m2, formatArea, MAX_TOTAL_AREA_M2)}</dd>
          </div>
          <div>
            <dt>용적률</dt>
            <dd>{describeSpec(head.far, formatPercent)}</dd>
          </div>
          <div>
            <dt>건폐율</dt>
            <dd>{describeSpec(head.bcr, formatPercent, MAX_BCR_PCT)}</dd>
          </div>
          <div>
            <dt>주차</dt>
            <dd>{describeSpec(head.parking_cnt, formatParking)}</dd>
          </div>
          {/*
            물결 2-1(2026-10-12 · 👤) — 주차 바로 뒤 구조 → 승강기 → 내진설계 → 대장 호수.
            ⛔ 칸이 아예 안 오면(undefined — 마이그레이션 2026-10-11c 전 서버) 넷 다 칸 없음.
            ⛔ 승강기는 승용 + 비상용 합 · 합 0 이나 둘 다 null 이면 지상 최고층 6층 이상만 '미상', 5층 이하·모름은 칸 없음(👤 결정 A).
            ⛔ 내진설계는 true 일 때만 칸 — '미적용'이라 쓰지 않는다(false 에 1988년 전·작은 건물·미기재가 섞여 있다).
            ⛔ 대장 호수는 집합건물이고 1호 이상이고 건물 주용도가 주거(공동주택·단독주택)가 아닐 때만 칸(👤 결정 B ·
               주용도를 모르면 칸 없음) — 0 은 대부분 호실이 없는 건물이라 '미상'도 안 쓴다.
               이름표 '대장 호수'는 층 목록의 「호실 N칸」(우리 호실 표로 센 것)과 구분하려는 것이다.
          */}
          {structure !== null && (
            <div>
              <dt>구조</dt>
              <dd>{structure}</dd>
            </div>
          )}
          {elevator !== null && (
            <div>
              <dt>승강기</dt>
              <dd>{elevator}</dd>
            </div>
          )}
          {head.seismic_design === true && (
            <div>
              <dt>내진설계</dt>
              <dd>적용</dd>
            </div>
          )}
          {ledgerHo !== null && (
            <div>
              <dt>대장 호수</dt>
              <dd>{ledgerHo}</dd>
            </div>
          )}
        </dl>
        {/*
          개별공시지가 한 줄(결정 0036 결정 7). 값이 없거나 못 읽었으면 **줄 자체가 없다** —
          '미상'·'자료 없음'으로 적지 않는다(위 네 칸과 다른 이유: 실패를 없음으로 말하면 거짓이다).
          ⓘ 내용이라 종이에도 그대로 나온다(`.stack__head` 가 통째로 한 장에 머문다).
        */}
        {landPrice && (
          <p className="stack__land">
            {/* 👤 2026-10-11 — 기준시가 줄의 「A등급 · 공식 고시」와 같은 꼴 · 이 줄은 '공시'. */}
            <span className="grade__badge">{LAND_PRICE_BADGE}</span>
            <span className="stack__land-text">{landPriceText(landPrice)}</span>
          </p>
        )}
        {/*
          내부 링크 줄(결정 0042 H5) — 진짜 `<a href>` 라 검색 봇이 따라가고, 사람의 보통 누름은 화면 안에서 처리한다.
          ⓘ 글자 = 동 목록 함수 값(`siblingName` — 첫 HTML 링크와 같은 함수) · 구 이름은 지역 고르개가 준 것 · 틀 두 줄은 메인 판단.
          ⛔ 종이에서는 빠진다(`@media print` 의 `.stack__links` — 누르는 문).
          ⓘ 휴대폰은 첫 줄 「같은 땅 다른 동 (외 N동)」 + 한 줄 칩(옆으로 밀기 · 👤 2026-10-19 「가」) — 칸을 span 으로만 나눠
            넓은 화면 그림·글(textContent)은 그대로 두고, 휴대폰 묶음(`@media screen and (max-width: 720px)`)이 점을 숨기고 칩으로 바꾼다.
            한 벌만 그린다(숨긴 점은 `display: none` 이라 낭독기도 안 읽는다). ⛔ 첫 줄 「같은 땅 다른 동:」은 쪼개지 않는다 — 쌍점만 칸으로
            감싸면 넓은 화면 글자 자리가 밀린다(휴대폰은 styles.css 가 이 글을 0 크기로 두고 `::before` 로 쌍점 없이 다시 쓴다 — 글자를 바꾸면 거기도).
        */}
        {(shownDongs.length > 0 || sigunguName) && (
          <nav className="stack__links" aria-label="관련 페이지">
            {shownDongs.length > 0 && dongs && (
              <p className="stack__links-row stack__links-row--dongs">
                <span className="stack__links-lead">같은 땅 다른 동:</span>{' '}
                <span className="stack__links-chips">
                  {shownDongs.map((d, i) => (
                    <Fragment key={d.bld_id}>
                      {i > 0 && <span className="stack__links-sep"> · </span>}
                      <a
                        className="stack__links-a"
                        href={`/?sgg=${sggCode}&bld=${d.bld_id}`}
                        onClick={(e) => {
                          if (!onSelectBuilding || !isPlainLeftClick(e)) return;
                          e.preventDefault();
                          onSelectBuilding(siblingToHit(building, d));
                        }}
                      >
                        {siblingName(d, dongs, head.bld_cnt_in_pnu)}
                      </a>
                    </Fragment>
                  ))}
                </span>
                {/* 첫 HTML 과 같은 상한(10) — 한 땅에 102동인 단지도 있다(DMC파크뷰자이 실측). 넘치면 수만 적는다(N = 뷰 동 수 − 자기 − 보인 수).
                    ⓘ 앞 띄어쓰기는 칸 밖 글이다 — 휴대폰 묶음(flex)에서는 빈 글이라 사라지고, 괄호는 그 묶음의 ::before·::after 가 단다. */}
                {moreDongs > 0 && (
                  <>
                    {' '}
                    <span className="stack__links-more">외 {moreDongs}동</span>
                  </>
                )}
              </p>
            )}
            {sigunguName && (
              <p className="stack__links-row">
                <a
                  className="stack__links-a"
                  href={`/?sgg=${sggCode}`}
                  onClick={(e) => {
                    if (!onFindInSigungu || !isPlainLeftClick(e)) return;
                    e.preventDefault();
                    onFindInSigungu();
                  }}
                >
                  {sigunguName} 다른 건물 찾기
                </a>
              </p>
            )}
          </nav>
        )}
      </header>

      {sectionOrder(viewerRole).map((k) => (
        <Fragment key={k}>{cards[k]}</Fragment>
      ))}

      <p className="grade">
        <span className="grade__badge">D등급 · 간접 추론</span>
        점포 목록은 호수가 아니라 <strong>“땅 + 층”</strong>으로 맞춘 값입니다. 어느 호실인지까지는
        알 수 없습니다. 면적·용도와 위 건물 스펙(연면적·용적률·건폐율·주차)은 건축물대장{' '}
        <strong>실측(A등급)</strong>입니다. 대장에 안 적힌 칸은 “미상”으로 둡니다 — 원본이
        미기재를 <strong>0</strong>으로 주기 때문에 0을 값으로 적으면 없는 사실이 생깁니다.{' '}
        {/* 👤 2026-10-19 「한 문장 더한다」 — 승강기·대장 호수 칸을 두지 않는 까닭(물결 2-1 PR② 의 숨김 규칙) · 글자 그대로. */}
        승강기는 5층 이하 건물에서 대장에 0대로 적혀 있으면 칸을 두지 않고, 공동주택·단독주택은 대장 호수가 세대 수라
        칸을 두지 않습니다.
        {/*
          결정 0032 — 호실 면적을 적는 요약(목록 제공 층)이 층 줄에 하나라도 붙었을 때만 보탠다
          (주거·오피스텔 층뿐인 건물은 면적을 안 적으므로 곱셈 안내가 할 말이 아니다).
          👤 문구는 2026-10-04 사장님이 쉬운 말로 고르신 글자 그대로다(옛 문장은 결정 0032 에).
        */}
        {hasListedUnits && (
          <>
            {' '}
            호실 목록은 건축물대장에 칸별로 적힌 내용 그대로입니다. 면적은 그 칸 안쪽만 잰 넓이라(복도·계단
            몫은 빠짐) 분양 광고의 면적보다 작습니다. 어느 칸에 어떤 가게가 있는지는 자료가 없어 알 수
            없습니다.{' '}
            <strong>
              이 호실 면적에 임대 카드의 ㎡당 임대료를 곱해도 이 호실의 월세가 아닙니다. 임대료는
              동네(상권) 평균이고, 면적을 재는 방법도 다릅니다.
            </strong>
          </>
        )}
      </p>
      <p className="grade grade--sub">
        <strong>점포 수는 실제와 다를 수 있습니다.</strong> ① <strong>빠짐</strong> — 상권정보에 층이
        적히지 않은 점포가 <strong>{missingPhrase}</strong>인데, 이런 점포는 어느 층에도 붙지
        않아 목록에서 통째로 빠집니다. ② <strong>겹침</strong> — 한 주소를 여러 점포가 나눠 쓰는
        공유오피스나 같은 땅의 옆 동 점포가 함께 잡혀 실제보다 많아 보일 수 있습니다.
        <br />
        {/*
          이 숫자들은 뷰 v_coverage_stats에서 읽어 온다. v_floor_stack의 점포가 분기 표지
          `snapshot_ym = (select r.published_ym from snapshot_release r)`를 따라가고(결정 0035 —
          각주 요약표는 같은 분기로 구운 뒤 post_load 가 표지를 올린다), 각주도 같은 기준으로
          따라가야 새 분기 적재 때 화면만 틀려지지 않는다.
          (예전에는 "32.9%·64,239곳"이 문자열로 박혀 있었다.)
        */}
        {basisPhrase}
      </p>
    </section>
  );
}

/**
 * "속한 상권" 카드.
 *
 * 말해야 하는 상태가 셋이고, 셋을 절대 같은 문장으로 뭉뚱그리지 않는다:
 *  ① 상권 여럿에 걸침 → **전부** 나열한다(하나만 고르면 그 고르는 규칙이 숨은 판단이 된다)
 *  ② 자료는 있는데 어느 경계에도 안 듦 → "없음". 서울에서도 흔한 **정상 상태**다
 *     (비율 수치는 여기 적지 않는다 — 자료가 바뀌면 그 숫자만 낡는다)
 *  ③ 그 지역에 상권 경계 자료 자체가 없음 → "준비 중". "상권 밖"이 아니라 "모른다"는 뜻이다
 *
 * ⚠️ 답(상권 이름·없음·준비 중)과 **출처는 요약 줄에 둔다** — 접었을 때 사라지면 안 되기
 *    때문이다. 출처 표기는 공공누리 1유형(출처표시) 의무이고, 접힘은 숨김이 아니다.
 *    펼쳤을 때 나오는 본문은 그 답을 **어떻게 읽어야 하는지**(겹침·경계 밖·자료 없음)만 말한다.
 * ⚠️ 출처 문구를 여기 글자로 박지 않는다. 소스가 둘이 되는 날(서울시 + 소상공인시장
 *    진흥공단) 코드를 한 줄도 안 고쳤는데 화면이 틀린 말을 하기 때문이다 — 서버가 자료에서
 *    읽어 준 `sources` 를 그대로 보여준다.
 */
function DistrictCard({
  info,
  plan = SECTION_PLAN.district,
}: {
  info: BuildingDistricts | null;
  plan?: SectionPlan;
}) {
  // 아직 안 왔거나 못 읽었으면 카드 자체를 안 그린다(위 useEffect에서 콘솔 경고만 남긴다).
  if (!info) return null;

  return (
    <SectionCard
      plan={plan}
      className="card--district"
      summary={<DistrictAnswer info={info} />}
    >
      <p className="card__note">
        <DistrictNote info={info} />
      </p>
    </SectionCard>
  );
}

/** 답 한 줄 — 접혀 있어도 항상 보이는 부분. */
function DistrictAnswer({ info }: { info: BuildingDistricts }) {
  if (!info.covered) return <>이 지역은 상권 경계 자료가 아직 준비되지 않았습니다.</>;

  if (info.districts.length === 0) {
    return (
      <>
        없음 — 어느 상권 경계에도 들지 않는 위치입니다.
        <DistrictSource sources={info.sources} />
      </>
    );
  }

  const names = info.districts
    .map((d) => {
      const name = d.name || '(이름 없음)';
      return d.type ? `${name}(${d.type})` : name;
    })
    .join(' · ');

  return (
    <>
      {names}
      <DistrictSource sources={info.sources} />
    </>
  );
}

/**
 * 그 답을 어떻게 읽어야 하나 — 상태 셋이 각각 다른 말을 한다.
 *
 * ⛔ "준비 중"(③)을 "상권 밖"(②)처럼 말하지 말 것. ②는 자료를 읽고 내린 판정이고
 *    ③은 읽을 자료가 없다는 뜻이라, 같은 말로 적으면 모르는 것을 아는 것처럼 말하게 된다.
 */
function DistrictNote({ info }: { info: BuildingDistricts }) {
  if (!info.covered) {
    return (
      <>
        이 지역의 상권 경계 자료가 들어오면 이 자리에 상권 이름이 나옵니다.{' '}
        <strong>상권 밖이라는 뜻이 아닙니다</strong> — 아직 모른다는 뜻입니다.
      </>
    );
  }

  if (info.districts.length === 0) {
    return (
      <>
        경계 밖도 <strong>정상입니다.</strong> 장사가 안 되는 자리라는 뜻이 아니라, 이 지역의
        상권 경계로 묶이지 않은 위치라는 뜻입니다.
      </>
    );
  }

  return (
    <>
      경계가 겹치는 자리는 걸친 곳을 하나만 고르지 않고 <strong>전부</strong> 적습니다. 하나만
      고르면 그 고르는 규칙이 숨은 판단이 되기 때문입니다.
    </>
  );
}

/**
 * 출처 한 조각. 서버가 준 목록을 그대로 잇는다(한 지역에 소스가 둘이면 둘 다 적는다).
 * 목록이 없거나 비면 아무것도 그리지 않는다 — 모르는 출처를 지어내지 않기 위해서다.
 */
function DistrictSource({ sources }: { sources?: string[] }) {
  if (!sources || sources.length === 0) return null;
  return <span className="stack__district-src">출처: {sources.join(' · ')}</span>;
}

/**
 * "많은 업종" 한 줄 — 층을 하나씩 펼치지 않아도 이 건물이 무슨 가게로 채워져 있는지
 * 한눈에 보이게 한다. 이미 받아 온 점포 목록을 세기만 하므로 서버에 더 묻지 않는다.
 *
 * 셀 업종이 하나도 없으면(점포가 없거나 업종이 전부 비어 있으면) 아무것도 안 그린다
 * — "업종 없음"이라고 적으면 모르는 것을 없는 것이라 말하게 된다.
 *
 * 라벨에 "층이 적힌 점포 기준"을 박는 이유: 층이 안 적힌 점포(약 3곳 중 1곳)는 이 집계에
 * 아예 안 들어오는데, 그 사실을 말하는 각주는 화면 맨 아래라 요약을 먼저 읽은 사람은
 * 모수를 완전한 숫자로 믿게 된다 — 한정어가 그 오독을 그 자리에서 막는다(절대 규칙 3 결).
 */
function BizSummary({ floors }: { floors: FloorRow[] }) {
  const { top, etc } = topCategories(floors);
  if (top.length === 0) return null;

  return (
    <p className="stack__biz">
      <span className="stack__biz-key">많은 업종(층이 적힌 점포 기준):</span>
      {top.map(([cat, n]) => `${cat} ${n.toLocaleString('ko-KR')}곳`).join(' · ')}
      {etc > 0 && <span className="stack__biz-etc"> 외 {etc}종</span>}
    </p>
  );
}

/**
 * "실거래" 섹션 — Stage A(결정 0012).
 *
 * ⛔ 여기에 **추정값을 넣지 말 것.** Stage A 는 신고된 거래를 그대로 보여주거나 세는
 *    것만 한다(추정 밴드 Stage B 는 결정 0041 로 화면에서 내렸다). 사실과 추정을 가르는 것이
 *    이 화면의 신뢰이기 때문이다.
 *
 * 두 블록이 하는 말이 다르다:
 *  ① 이 땅의 이력 — 있는 건물에만 나온다(자기 거래가 있는 필지는 서울 1.8% 뿐이다).
 *  ② 구의 단가 분포 — 항상 나온다. ①이 비어 있어도 "이 동네가 어디쯤인지"는 말할 수 있다.
 */
function TransactionSection({
  txs,
  stats,
  plan = SECTION_PLAN.tx,
  bldId,
}: {
  txs: ParcelTransaction[] | null;
  stats: SigunguTxStat[] | null;
  plan?: SectionPlan;
  /** 거래 목록의 「전부 보기」를 건물마다 새로 세우는 열쇠(S2) — 같은 땅의 다른 동으로 넘어가도 처음 10건부터. */
  bldId: string;
}) {
  // 둘 다 아직 안 왔거나 못 읽었으면 섹션 자체를 그리지 않는다(빈 제목만 남기지 않는다).
  const hasHistory = txs !== null && txs.length > 0;
  const hasStats = stats !== null && stats.length > 0;
  if (!hasHistory && !hasStats) return null;

  // 접혀 있어도 보이는 한 줄 — **몇 건인지**와 **무엇이 들어 있는지**만 말한다.
  // ⚠️ 아래 블록 제목("이 땅에서 신고된 거래 N건" · "○○구 층대별 거래 단가")과 **같은
  //    글자를 쓰지 않는다.** 같은 말이 화면에 둘이 되면 사람은 두 번 세고, 이름으로 찾는
  //    시험은 어느 쪽을 잡았는지 모르게 된다.
  const guName = stats?.find((s) => s.sigungu_nm)?.sigungu_nm ?? null;
  const summary = [
    hasHistory ? `이 땅 거래 ${txs!.length.toLocaleString('ko-KR')}건` : null,
    hasStats ? `${guName ? `${guName} ` : ''}층대별 단가 (상가 거래 기준)` : null,
  ]
    .filter((s): s is string => s !== null)
    .join(' · ');

  return (
    <SectionCard plan={plan} className="tx" summary={summary}>
      {hasHistory && <ParcelTxList key={bldId} txs={txs!} />}
      {hasStats && <SigunguTxBands stats={stats!} />}
    </SectionCard>
  );
}

/** ① 이 땅에서 신고된 거래 목록. */
function ParcelTxList({ txs }: { txs: ParcelTransaction[] }) {
  // 지분 거래(2026-10-08a)는 지우지 않고 꼬리표를 단다. 설명 한 줄은 지분 행이 **하나라도
  // 있을 때만** — 없는 목록에 붙이면 읽을 이유가 없는 글이 된다. `=== true` 인 이유: 옛 서버는
  // 이 칸을 안 준다(undefined).
  const hasShare = txs.some((t) => t.is_share === true);
  // 처음 10건만 화면에(S2) — 펼침은 이 목록의 상태라 건물이 바뀌면(key) 다시 접힌다.
  const [all, setAll] = useState(false);
  // 설명 줄은 **화면에 보이는 줄**에 지분이 있을 때만 화면에 선다(👤 2026-10-16) — 숨은 줄에만 있으면
  // 줄은 그리되 숨은 줄과 같은 이름표를 달아 `@media screen` 에서만 숨긴다(종이에는 줄이 전부 나오니 설명도 늘).
  // 점그림(결정 0038 B · V2) — 목록의 거래가 5건 이상이고 찍을 점이 있을 때만. 그림이 서면 숨은 줄의 지분도 점(빈 꼴)으로
  // 화면에 보이므로 설명 줄은 **늘** 선다(위 `shownShare` 의 예외 · 지분이 0건이면 지금처럼 줄 자체가 없다).
  const plot = txPlot(txs);
  const shownShare =
    plot !== null || (all ? hasShare : txs.slice(0, LIST_FOLD_AT).some((t) => t.is_share === true));
  const listId = useId();
  return (
    <div className="tx__block">
      <h4 className="tx__sub">
        이 땅에서 신고된 거래 {txs.length.toLocaleString('ko-KR')}건
        {/* 서버가 끊는 건수다(한 필지에 852건인 곳이 실재한다). 잘렸으면 잘렸다고 말한다.
            숫자는 서버 짝(TX_LIST_CAP)에서 온다 — 화면에 따로 박으면 서버만 늘어난 날 거짓말이 된다. */}
        {txs.length >= TX_LIST_CAP && (
          <span className="tx__cap"> (최근 {TX_LIST_CAP}건까지)</span>
        )}
      </h4>
      {plot !== null && <TxDotPlot plot={plot} />}
      <ul className="tx__list" id={listId}>
        {txs.map((t, i) => (
          <li key={i} className={!all && i >= LIST_FOLD_AT ? 'list__folded' : undefined}>
            <span className="tx__floor">
              {t.floor_no === null ? '층 미상' : formatFloor(t.floor_no, null)}
            </span>
            <span className="tx__when">{formatYearMonth(t.contract_ym)}</span>
            <span className="tx__area">{formatArea(t.bld_area_m2)}</span>
            <span className="tx__price">{formatWon(t.price_won)}</span>
            <span className="tx__unit">
              {t.unit_price === null ? '㎡당 —' : `㎡당 ${formatManWon(t.unit_price)}`}
            </span>
            <span className="tx__kind">{t.tx_type || '거래유형 미상'}</span>
            {t.is_share === true && <span className="tx__share">지분</span>}
          </li>
        ))}
      </ul>
      {txs.length > LIST_FOLD_AT && (
        <ListFoldButton
          expanded={all}
          controls={listId}
          moreText={`거래 전부 보기 (${txs.length.toLocaleString('ko-KR')}건)`}
          lessText="거래 목록 접기"
          onToggle={setAll}
        />
      )}
      {hasShare && (
        <p className={`tx__note tx__share-note${shownShare ? '' : ' list__folded'}`}>
          지분 = 건물 일부 몫만 사고판 거래라 ㎡당 값이 낮게 나옵니다 — 층대별 단가 계산에서는 뺍니다.
        </p>
      )}
      <p className="tx__note">
        <strong>{TX_OPEN_SINCE_LABEL} 이후 계약분만 보입니다.</strong> 그 전 거래는 지번이
        가려져 이 땅에 붙일 수 없고, 건물 한 채를 통째로 사고파는 거래도 같은 이유로 빠집니다.{' '}
        {TX_BASEMENT_MISSING_SINCE}년부터는 층이 빈 값으로 오는 거래가 많아{' '}
        <strong>층 미상</strong>으로 남습니다.
      </p>
    </div>
  );
}

/**
 * ② 구의 층대별 단가 분포.
 *
 * 표본이 MIN_SAMPLE 건 미만인 층대는 수치를 적지 않는다 — 칸을 지우지는 않는다.
 * 칸이 사라지면 "그 층은 아예 안 판다"처럼 읽히지만, 실제로는 "셀 만큼 없다"가 사실이다.
 */
function SigunguTxBands({ stats }: { stats: SigunguTxStat[] }) {
  // 구 이름·집계 시작 달은 서버가 준 값을 그대로 쓴다 — 화면에 박으면 자료가 바뀌는 날
  // 코드를 한 줄도 안 고쳤는데 문구만 틀려진다(상권 출처 줄과 같은 원칙).
  const guName = stats.find((s) => s.sigungu_nm)?.sigungu_nm ?? null;
  const from = stats.find((s) => s.window_from)?.window_from ?? null;
  const total = stats.reduce((sum, s) => sum + (s.n ?? 0), 0);
  // 띠 축(결정 0038 B · V2) — 0 ~ 값을 내는 줄의 최댓값 올림. 값을 내는 줄이 없으면 띠·축 없이 지금 글만.
  const axisMax = txBandAxisMaxWon(stats);

  return (
    <div className="tx__block">
      {/* 상가(근생·판매) 거래만 센 표다(결정 0040 D3 · 서버 mv_sigungu_tx_stats 의 where) — 제목이 그 사실을 말한다. */}
      <h4 className="tx__sub">
        {guName ? `${guName} 층대별 거래 단가 (상가 거래 기준)` : '층대별 거래 단가 (상가 거래 기준)'}
      </h4>
      <ul className={`tx__bands${axisMax !== null ? ' tx__bands--viz' : ''}`}>
        {stats.map((s) => {
          const enough = s.n >= MIN_SAMPLE;
          return (
            <li key={s.floor_band}>
              <span className="tx__band">{s.floor_band}</span>
              {axisMax !== null && <TxBandViz mark={txBandMark(s, axisMax)} />}
              <span className={`tx__val${enough ? '' : ' tx__val--none'}`}>
                {enough ? (
                  <>
                    중앙값 ㎡당 {formatManWon(s.median_unit_price)}
                    <span className="tx__spread">
                      {' '}
                      (가운데 절반 {formatManWon(s.p25_unit_price)}~
                      {formatManWon(s.p75_unit_price)})
                    </span>
                  </>
                ) : (
                  '표본 부족'
                )}
              </span>
              <span className="tx__n">표본 {s.n.toLocaleString('ko-KR')}건</span>
            </li>
          );
        })}
      </ul>
      {axisMax !== null && (
        // 띠 축의 눈금 글 한 줄 — 그림 밖 HTML(§2-2) · 띠 칸과 같은 자리 · 띠와 함께 읽는 글이라 띠처럼 낭독기에서 뺀다.
        <div className="tx__axis" aria-hidden="true">
          <span className="tx__axis-scale">
            <span>0</span>
            <span>㎡당 {formatManWon(axisMax)}</span>
          </span>
        </div>
      )}
      <p className="grade">
        {/* 구 층대 가운데값 = 우리가 세어 낸 집계 — 세 잣대 칸·요약 타일과 같은 배지(결정 0041 보완 1차 · 꼬리말 약속). */}
        <span className="grade__badge">{TX_STAT_BADGE}</span>
        추정한 값이 아니라 <strong>신고된 거래를 그대로 센 값</strong>입니다. 표본이{' '}
        {MIN_SAMPLE}건 미만인 층대는 수치를 적지 않습니다 — 몇 건으로 낸 가운데값은 숫자
        모양만 통계이기 때문입니다.
      </p>
      <p className="tx__src">
        출처: 국토교통부 상업업무용 부동산 매매 실거래가 ·{' '}
        {guName ? `${guName} ` : ''}상가(근린생활·판매) 집합(구분소유) 거래
        {/* 날짜 말투는 카드 머리 날짜 줄과 같은 '2024년 10월'(F1 · 👤 2026-10-16 ④) — 못 읽으면 원본 그대로. */}
        {from ? ` ${formatMonthKo(from) ?? from} 이후 계약분` : ''} 집계 · 지분 거래 제외 · 전체 표본{' '}
        {total.toLocaleString('ko-KR')}건.
      </p>
    </div>
  );
}

/**
 * 구 층대 줄 하나의 띠(결정 0038 B · V2) — p25~p75 띠 + 가운데값 세로 눈금 · 축 = 0 ~ 블록 상한(㎡당).
 * 사실 색(호박) · 사분위가 없거나 폭 0 이면 눈금만 · 값을 안 내는 줄은 "–"(까닭 「표본 부족」은 옆 글에 그대로 · 0 으로 안 그린다).
 * 옆 글과 같은 내용이라 낭독기에서 뺀다(§2-1). 크기는 % 로만(§2-3 — DOM 을 재지 않는다).
 */
function TxBandViz({ mark }: { mark: TxBandMark }) {
  if (mark.kind === 'none') {
    return (
      <span className="tx__viz tx__viz--none" aria-hidden="true">
        –
      </span>
    );
  }
  return (
    <span className="tx__viz" aria-hidden="true">
      <span className="tx__track" style={{ background: cssVar(VIZ_TONES.fact.bg), borderColor: cssVar(VIZ_TONES.fact.line) }}>
        {mark.kind === 'band' && (
          <span
            className="tx__range"
            style={{ left: `${mark.left}%`, width: `${mark.width}%`, background: cssVar(VIZ_TONES.fact.steps[1]) }}
          />
        )}
        <span className="tx__tick" style={{ left: `${mark.x}%`, background: cssVar(VIZ_TONES.fact.steps[3]) }} />
      </span>
    </span>
  );
}

/**
 * 점 하나의 꼴(결정 0038 B) — ● 1층 · ■ 2층 · ▲ 3층 이상 · ◆ 지하 · 회색 ● 층 미상 · 지분은 같은 꼴의 빈 꼴.
 * SVG 에는 도형만(§2-2) · 고정 viewBox 라 칸이 줄어도 꼴이 찌그러지지 않는다(자리는 바깥 span 의 %).
 * 색은 styles.css 의 `.tx__shape` 규칙이 `data-shape`·`data-hollow` 로 칠한다(사실 호박 `--fact-3`·`--fact-4` · 층 미상 `--viz-na` ·
 * 빈 꼴 `--card`) — ⛔ SVG 속성(`fill="var(--…)"`)에 변수를 넣지 않는다(속성 값의 var() 는 브라우저마다 안 먹을 수 있다).
 */
function TxShapeIcon({ shape, hollow }: { shape: TxShape; hollow: boolean }) {
  return (
    <svg className="tx__shape" viewBox="0 0 10 10" data-shape={shape} data-hollow={hollow ? '1' : '0'} focusable="false">
      {shape === '2' ? (
        <rect x="1.4" y="1.4" width="7.2" height="7.2" />
      ) : shape === '3+' ? (
        <polygon points="5,0.9 9.3,8.9 0.7,8.9" />
      ) : shape === 'b' ? (
        <polygon points="5,0.6 9.4,5 5,9.4 0.6,5" />
      ) : (
        <circle cx="5" cy="5" r="4" />
      )}
    </svg>
  );
}

/**
 * 이 땅 거래 점그림(결정 0038 B · V2) — 세로 = ㎡당 단가(0 ~ 최댓값 올림) · 가로 = 계약 시기(가장 이른 달 ~ 가장 늦은 달).
 * 바로 아래 목록과 같은 거래라 그림·눈금·범례는 낭독기에서 뺀다(§2-1). 눈금·범례 글자는 SVG 밖 HTML(§2-2).
 * 점이 없는 거래(㎡당 값 없음 등)는 0 에 찍지 않고 그 수를 한 줄로 말한다(§2-4).
 */
function TxDotPlot({ plot }: { plot: TxPlot }) {
  const from = formatMonthKo(plot.fromYm) ?? plot.fromYm;
  const to = formatMonthKo(plot.toYm) ?? plot.toYm;
  // 세로 눈금 글(보완 1 F4) — 값만(맨 아래 「0」) · 단위 「㎡당」은 눈금 칸 위 한 줄(눈금 칸을 좁혀 점 칸을 넓힌다 — 휴대폰).
  const tickText = (k: number, won: number) => (k === 0 ? '0' : formatManWon(won));
  const top = tickText(plot.ticks.length - 1, plot.yMaxWon);
  return (
    <div className="tx__plot" aria-hidden="true">
      <div className="tx__plot-frame">
        <span className="tx__plot-unit">㎡당</span>
        <span className="tx__plot-y">
          {/* 칸 폭을 가장 긴 눈금 글로 잡는 빈 자리(눈금 글은 아래 % 자리에 겹쳐 선다 · DOM 을 재지 않는다). */}
          <span className="tx__plot-yw">{top}</span>
          <span className="tx__plot-yin">
            {plot.ticks.map((t, k) => (
              <span key={k} className="tx__tick-y" style={{ bottom: `${t.y}%` }}>
                {tickText(k, t.won)}
              </span>
            ))}
          </span>
        </span>
        <span className="tx__plot-area" style={{ background: cssVar(VIZ_TONES.fact.bg), borderColor: cssVar(VIZ_TONES.fact.line) }}>
          <span className="tx__plot-in">
            {plot.ticks.map((t, k) => (
              <span key={`g${k}`} className="tx__grid" style={{ bottom: `${t.y}%` }} />
            ))}
            {plot.points.map((p, i) => (
              <span key={i} className="tx__dot" style={{ left: `${p.x}%`, bottom: `${p.y}%` }}>
                <TxShapeIcon shape={p.shape} hollow={p.hollow} />
              </span>
            ))}
            {/* 점 금액 글자(보완 1 F1~F3) — 넓은 화면·종이용과 휴대폰용 두 벌 중 CSS 가 하나만 보인다(@media screen 720 묶음). */}
            {(['wide', 'narrow'] as const).map((kind) => (
              <span key={kind} className={`tx__labs tx__labs--${kind}`}>
                {plot.labels[kind].map((l, i) => (
                  <span
                    key={i}
                    className={`tx__lab tx__lab--${l.side}`}
                    // 칸 끝에 붙인 글자('L'·'R')는 칸 왼쪽·오른쪽 끝 기준 · 나머지는 제 점 자리 기준.
                    style={
                      l.side === 'L'
                        ? { left: 0, bottom: `${l.y}%` }
                        : l.side === 'R'
                          ? { right: 0, bottom: `${l.y}%` }
                          : { left: `${l.x}%`, bottom: `${l.y}%` }
                    }
                  >
                    {l.text}
                  </span>
                ))}
              </span>
            ))}
          </span>
        </span>
        <span className="tx__plot-x">
          <span>{from}</span>
          {to !== from && <span>{to}</span>}
        </span>
      </div>
      {/* 글자를 못 단 점이 있으면 한 줄(보완 3 G1) — 벌마다 따로(넓은 화면·종이 / 휴대폰 · 글자 벌과 같은 CSS 로 고른다). */}
      {(['wide', 'narrow'] as const).map((kind) =>
        plot.unlabeled[kind] > 0 ? (
          <p key={kind} className={`tx__plot-note tx__plot-note--${kind}`}>
            {/* 「거래 전부 보기」 포함 — 글자 없는 점의 거래가 접힌 10건 밖일 수 있다(보완 4 · 재검사 🟡). */}
            글자 자리가 없는 점 {plot.unlabeled[kind].toLocaleString('ko-KR')}개 — 금액은 아래 거래 목록(「거래 전부 보기」 포함)에 있습니다
          </p>
        ) : null,
      )}
      <p className="tx__keys">
        {plot.shapes.map((s) => (
          <span key={s} className="tx__key">
            <TxShapeIcon shape={s} hollow={false} />
            {TX_SHAPE_LABEL[s]}
          </span>
        ))}
        {plot.hasHollow && (
          <span className="tx__key">
            <TxShapeIcon shape="1" hollow />
            속이 빈 꼴 = 지분
          </span>
        )}
        {plot.skipped > 0 && (
          <span className="tx__key tx__key--skip">
            ㎡당 값이나 계약 달이 없는 거래 {plot.skipped.toLocaleString('ko-KR')}건은 점이 없습니다
          </span>
        )}
      </p>
    </div>
  );
}

/**
 * 호실 구성표 고르기로 받은 한 층의 호 목록(물결 1-C2) — 층 줄 아래, 화면·종이 같은 것.
 * 첫 쪽보다 많으면 남은 수를 한 줄로(👤 글자 · 종이에도). 받은 것이 0줄이면 아무것도 안 그린다.
 */
function PrintedUnitList({ printed }: { printed: PrintedUnits }) {
  if (printed.units.length === 0) return null;
  const rest = printed.total - printed.units.length;
  return (
    <div className="floor__unitprint">
      <ul className="floor__unitprint-list">
        {printed.units.map((u, i) => (
          <li key={i}>
            <span className="detail__name">{unitDisplayName(u.ho)}</span>{' '}
            <span className="detail__val">{formatUnitArea(u.excl_area_m2)}</span>
          </li>
        ))}
      </ul>
      {rest > 0 && <p className="floor__unitprint-more">{unitPrintMoreText(rest)}</p>}
    </div>
  );
}

function FloorDetail({
  floor,
  bldId,
  unitRow,
}: {
  floor: FloorRow;
  bldId: string;
  /** 그 층의 호실 요약(결정 0032). 없으면 셋째 칸을 아예 안 만든다. */
  unitRow?: UnitFloorSummary;
}) {
  const uses = floor.uses ?? [];
  const stores = floor.stores ?? [];
  // 셋째 칸은 목록 제공 층(목록) · 주거·오피스텔 층(안내 한 줄)에서만. 미상 층은 요약 줄의
  // "용도 미상"이 이미 말하므로 칸을 더 만들지 않는다.
  const unitCol =
    unitRow !== undefined &&
    (hasUnitList(unitRow.floor_kind) ||
      unitRow.floor_kind === 'residential' ||
      unitRow.floor_kind === 'officetel');

  return (
    <div className={`detail${unitCol ? ' detail--units' : ''}`}>
      <div className="detail__col">
        <h4 className="detail__h">용도별 구획 {uses.length > 0 && `(${uses.length})`}</h4>
        {uses.length === 0 ? (
          <p className="detail__none">구획 정보 없음</p>
        ) : (
          <ul className="detail__list">
            {uses.map((u, i) => (
              <li key={i}>
                <span className="detail__name">{u.use || '용도 미상'}</span>
                {u.detail && <span className="detail__sub">{u.detail}</span>}
                <span className="detail__val">{formatArea(u.area_m2)}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="detail__note">
          전체 면적 {formatArea(floor.floor_area_gross_m2)} 중 계단실·물탱크실 등을 뺀 값이
          위의 {formatArea(floor.floor_area_m2)}입니다.
        </p>
      </div>

      <div className="detail__col">
        <h4 className="detail__h">점포 {stores.length > 0 && `(${stores.length})`}</h4>
        {stores.length === 0 ? (
          <p className="detail__none">이 층에 등록된 점포가 없습니다</p>
        ) : (
          <ul className="detail__list">
            {stores.map((s, i) => (
              <li key={i}>
                <span className="detail__name">{s.name || '상호 미상'}</span>
                <span className="detail__sub">{s.cat || '업종 미상'}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {unitCol && unitRow && <FloorUnits bldId={bldId} unitRow={unitRow} />}
    </div>
  );
}

/**
 * 펼친 층의 셋째 칸 "호실"(결정 0032).
 *
 * - 목록 제공 층(commercial·mixed): 펼친 **그때** 그 층 목록을 50줄 부르고, 더 보기로 이어 붙인다.
 * - 주거·오피스텔 층: 목록을 **부르지 않는다** — 안내 한 줄만. 서버도 0줄을 주지만, 화면이
 *   요청조차 안 보내야 아파트 세대 목록을 묻는 요청이 아예 생기지 않는다.
 *
 * ⛔ 섞인 층 안내는 "대장 자료에 없습니다"라고 쓰지 않는다 — 원본 전유부에는 호마다 용도가
 *    있다. 우리가 아직 안 담은 것을 대장 탓으로 말하면 안 된다(결정 0032 `:147-148`).
 * ⛔ 사람이 눌러 연 칸이라, 불러오지 못하면 조용히 비우지 않고 그렇다고 적는다(0025 규칙).
 */
function FloorUnits({ bldId, unitRow }: { bldId: string; unitRow: UnitFloorSummary }) {
  const listed = hasUnitList(unitRow.floor_kind);
  const floorNo = unitRow.floor_no;
  const [units, setUnits] = useState<FloorUnit[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(listed);
  const [failed, setFailed] = useState(false);
  // 더 보기를 누를 때마다 1씩 올린다 — 0 이 첫 쪽이다.
  const [page, setPage] = useState(0);
  /** 다음 쪽이 0줄로 왔다 = 더 받을 것이 없다(더 보기를 거둔다). */
  const [ended, setEnded] = useState(false);

  useEffect(() => {
    if (!listed || floorNo === null) return;
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    supabase
      .rpc(FLOOR_UNITS_FN, {
        p_bld_id: bldId,
        p_floor_no: floorNo,
        p_limit: FLOOR_UNITS_PAGE,
        p_offset: page * FLOOR_UNITS_PAGE,
      })
      .then(({ data, error: err }) => {
        if (cancelled) return;
        const rows = err ? null : parseFloorUnits(data);
        if (rows === null) {
          console.warn('호 목록 조회 실패', err);
          setFailed(true);
        } else {
          setUnits((prev) => (page === 0 ? rows : [...prev, ...rows]));
          if (rows.length > 0) setTotal(rows[0].total_cnt);
          else if (page === 0) setTotal(0);
          // 다음 쪽이 0줄이면 끝이다 — 받은 수 < 전체 수라도 더 보기를 남기면 눌러도 안 느는
          // 버튼이 된다(그 사이 호실이 줄었거나 total_cnt 가 어긋난 경우).
          else setEnded(true);
        }
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [bldId, floorNo, listed, page]);

  const count = (total ?? unitRow.unit_cnt).toLocaleString('ko-KR');

  return (
    <div className="detail__col units">
      <h4 className="detail__h">
        호실 ({count}) <span className="units__src">— 건축물대장 기준</span>
      </h4>
      {!listed ? (
        <p className="detail__none">{UNIT_HOME_FLOOR_NOTE}</p>
      ) : (
        <>
          {unitRow.floor_kind === 'mixed' && (
            <p className="units__mixed">
              이 층은 상가와 주거·오피스텔이 섞여 있어 함께 나옵니다 — 호실마다의 용도는{' '}
              <strong>아직 담지 않았습니다</strong>.
            </p>
          )}
          {units.length > 0 && (
            <ul className="detail__list units__list">
              {units.map((u, i) => (
                <li key={i}>
                  <span className="detail__name">{unitDisplayName(u.ho)}</span>
                  <span className="detail__val">{formatUnitArea(u.excl_area_m2)}</span>
                </li>
              ))}
            </ul>
          )}
          {/* 첫 쪽을 받는 동안만 글줄로 알린다 — 더 보기를 받는 동안은 버튼 글자가 알린다. */}
          {loading && page === 0 && <p className="detail__none">호 목록을 불러오는 중…</p>}
          {failed && <p className="detail__none">호 목록을 불러오지 못했습니다.</p>}
          {!loading && !failed && total === 0 && (
            <p className="detail__none">이 층의 호 목록이 없습니다.</p>
          )}
          {/*
            ⓘ 받는 동안 버튼을 **지우지 않고** 글자만 바꿔 잠근다(상권 건물 목록·가게 검색과 같은 모양) —
              지웠다 다시 그리면 목록 아래가 덜컥거리고, 두 번 눌러 같은 쪽을 두 번 받는 길도 막힌다.
          */}
          {!failed && !ended && total !== null && units.length < total && (
            <button
              type="button"
              className="units__more"
              disabled={loading}
              onClick={() => setPage((n) => n + 1)}
            >
              {loading
                ? '불러오는 중…'
                : `더 보기 (${units.length.toLocaleString('ko-KR')} / ${total.toLocaleString('ko-KR')})`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
