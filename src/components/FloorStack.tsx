import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import {
  FLOOR_STACK_VIEW,
  COVERAGE_STATS_VIEW,
  BUILDING_DISTRICTS_FN,
  PARCEL_TX_FN,
  SIGUNGU_TX_STATS_FN,
  PRICE_BANDS_FN,
  TX_LIST_CAP,
  TX_OPEN_SINCE_LABEL,
  TX_BASEMENT_MISSING_SINCE,
} from '../lib/appConstants';
import type {
  BuildingDistricts,
  BuildingHit,
  CoverageStats,
  FloorRow,
  ParcelTransaction,
  PriceBand,
  SigunguTxStat,
} from '../types';
import {
  formatArea,
  formatApproveDate,
  formatFloor,
  formatManWon,
  formatQuarter,
  formatWon,
  formatYearMonth,
  oneInEvery,
} from '../lib/format';
import { KNOWN_BAND_STATUS } from '../lib/priceBand';
import { SECTION_PLAN } from '../lib/sectionCards';
import { PriceBandSection } from './PriceBandSection';
import { IndustryMixSection } from './IndustryMixSection';
import { SectionCard } from './SectionCard';

/**
 * 구 단가에서 수치를 보여줄 최소 표본 수(결정 0012).
 *
 * 이보다 적으면 중앙값·사분위를 **적지 않는다.** 3건으로 낸 중앙값은 숫자 모양만
 * 통계일 뿐이고, 화면에 적히는 순간 사람은 그걸 근거로 쓴다 — 검증 규칙의 미표시 원칙이다.
 */
const MIN_SAMPLE = 5;

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
 * 건물 스펙 4칸(연면적·용적률·건폐율·주차)에서 **값 대신 적는 말**.
 *
 * ⛔ 여기서 "0" 을 그대로 적으면 안 된다. 건축물대장은 안 적은 칸을 '0' 으로 준다 —
 *    롯데월드타워가 주차 0·건폐율 0 으로 들어와 있어 "정말 0" 과 "안 적힘" 을 값으로는
 *    갈라낼 수 없다. 갈라낼 수 없으면 둘 중 하나로 단정하지 않는 것이 맞다
 *    (로드맵 Wave 2 PR-B).
 * ⓘ "NULL 은 0행" 은 **현재 적재분(서울·대전 30개 구)의 관찰값**이지 구조적 보장이
 *    아니다 — 적재기는 결측을 NULL 로 쓴다(load_building_ledger.py 의 `_to_float`·
 *    `sum_parking`). [C] 전국 적재 뒤에는 다시 세어 볼 것. `describeSpec` 은 0 과 null 을
 *    **같은 말**로 돌려주므로, 어느 쪽이 오더라도 이 화면은 그대로 맞다.
 */
const UNKNOWN_SPEC = '미상';

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

/** 주차 표기. */
function formatParking(n: number): string {
  return `${n.toLocaleString('ko-KR')}대`;
}

/**
 * 건물 스펙 한 칸을 사람이 읽는 말로. 값이 아니면 무조건 "미상"이다.
 *
 * "값이 아닌 것" 셋을 **같은 말로** 돌려준다 — 없음(null)·미기재(0 이하)·오류(상한 초과).
 * 셋을 갈라 적으면 화면이 우리도 모르는 것을 아는 척하게 된다(예: 상한을 넘은 79,095%를
 * "이상값"이라 적으면, 그 건물의 건폐율이 아주 크다는 뜻으로 읽힌다).
 */
function describeSpec(
  value: number | null | undefined,
  format: (n: number) => string,
  max?: number,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return UNKNOWN_SPEC;
  if (value <= 0) return UNKNOWN_SPEC;
  if (max !== undefined && value > max) return UNKNOWN_SPEC;
  return format(value);
}

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
 *    추정은 아래 참고 시세 섹션(`PriceBandSection`)이 카드를 갈라 따로 낸다. 공실 이력은
 *    Phase 5 산출물이라 아직 없다(빈칸을 그럴듯하게 채우면 없는 근거를 있는 것처럼
 *    보이게 만든다).
 */

type Props = { building: BuildingHit };

export function FloorStack({ building }: Props) {
  const [floors, setFloors] = useState<FloorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openFloor, setOpenFloor] = useState<number | null>(null);
  /** 각주에 쓸 집계. 건물과 무관하므로 처음 한 번만 읽는다. */
  const [stats, setStats] = useState<CoverageStats | null>(null);
  /** 이 건물이 속한 상권. 못 읽으면 null로 남고, 그때는 그 줄을 아예 그리지 않는다. */
  const [districts, setDistricts] = useState<BuildingDistricts | null>(null);
  /** 이 땅에서 신고된 실거래(Stage A). 대부분의 건물에서 빈 배열이 정상이다. */
  const [txs, setTxs] = useState<ParcelTransaction[] | null>(null);
  /** 이 구의 층대별 단가 분포(Stage A). 못 읽으면 null로 남고 그 블록만 안 그린다. */
  const [txStats, setTxStats] = useState<SigunguTxStat[] | null>(null);
  /** 이 필지의 층별 참고 시세(Stage B · 결정 0013). null = 아직 안 옴. */
  const [bands, setBands] = useState<PriceBand[] | null>(null);
  /** 못 읽었나. 못 읽었으면 그 섹션을 아예 안 그린다(모르는 것을 없다고 말하지 않는다). */
  const [bandsFailed, setBandsFailed] = useState(false);
  /**
   * 층 목록 카드를 **펼치라고 부르는 신호**. 참고 시세 줄을 누를 때마다 1씩 올린다.
   *
   * ⛔ 이게 없으면 사용자가 층 목록을 접어 둔 상태에서 시세 줄을 눌렀을 때 **아무 일도
   *    안 일어난다** — 층은 펼쳐졌는데 그 층이 접힌 카드 안에 있기 때문이다. 눌렀는데
   *    화면이 안 변하면 사람은 고장 났다고 읽는다.
   */
  const [floorsOpenSignal, setFloorsOpenSignal] = useState(0);
  /**
   * 층 목록 카드가 지금 펼쳐져 있나(카드가 알려 준다).
   *
   * 참고 시세 줄이 `aria-expanded` 로 "그 층이 펼쳐져 있다"고 말하는데, 정작 층 목록이
   * 접혀 있으면 그 말이 거짓이 된다 — 그래서 접혀 있는 동안에는 시세 쪽에 "펼쳐진 층
   * 없음"으로 넘긴다. 카드의 상태를 위로 끌어올린 것이 아니라 **알림만** 받는다.
   */
  // ⚠️ `<boolean>` 을 명시한다. `SECTION_PLAN` 이 `as const` 라 `defaultOpen` 의 타입이
  //    `true`(값 하나짜리 타입)라서, 안 적으면 "true 만 담는 상태"가 되어 접힐 수가 없다.
  const [floorsCardOpen, setFloorsCardOpen] = useState<boolean>(SECTION_PLAN.floors.defaultOpen);

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
    setBands(null);
    setBandsFailed(false);

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

    // ── 참고 매매 시세 밴드 (Stage B · 결정 0013) ──────────────────────────
    //
    // ⚠️ 인자 이름이 이 함수만 `p_pnu` 다(형제 셋은 bld_id·pnu·sigungu). 습관대로
    //    `{ pnu: … }` 로 부르면 목(mock)은 인자 이름을 안 보므로 vitest·E2E 가 전부
    //    초록인 채 **라이브에서만** PGRST202 가 난다.
    supabase.rpc(PRICE_BANDS_FN, { p_pnu: building.pnu }).then(({ data, error: err }) => {
      if (cancelled) return;
      if (err || !data) {
        // 못 읽었으면 "참고 시세 없음"이라고 적지 않는다 — 없는 것과 모르는 것은 다르다.
        console.warn('참고 시세 조회 실패 — 그 섹션 없이 표시합니다', err);
        setBandsFailed(true);
        return;
      }
      const rows = data as PriceBand[];
      // 서버가 여섯 번째 status 를 늘리면 화면은 그 층을 조용히 안 그린다(뜻을 지어내지
      // 않는다). 눈에 안 띄므로 콘솔에는 반드시 남긴다 — status 를 늘리는 날 화면도 같은
      // 커밋에서 고쳐야 한다는 신호다.
      const unknown = [...new Set(rows.map((b) => b.status))].filter(
        (s) => !KNOWN_BAND_STATUS.has(s),
      );
      if (unknown.length > 0) console.warn('모르는 status 라 그 층은 그리지 않습니다', unknown);
      setBands(rows);
    });

    return () => {
      cancelled = true;
    };
  }, [building.pnu]);

  if (loading) return <p className="msg msg--loading">층 정보를 불러오는 중…</p>;
  if (error) return <p className="msg msg--error">{error}</p>;
  if (floors.length === 0) return <p className="msg">이 건물에는 층 정보가 없습니다.</p>;

  const head = floors[0];
  const roadContact = displayRoadContact(head.road_contact);
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

  // 각주 숫자는 DB에서 계산해 온다. 못 불러왔으면 숫자를 빼고 경고만 남긴다
  // — 옛 숫자로 되돌리면 이 코드가 고치려던 문제(화면만 틀려지는 것)가 그대로 살아난다.
  const missingEvery = stats ? oneInEvery(stats.floor_missing_pct) : null;
  const missingPhrase =
    stats && missingEvery
      ? `약 ${missingEvery}곳 중 1곳(${stats.floor_missing_pct}%)`
      : '적지 않은 수';
  // "서비스 지역"을 밝히는 이유: 뷰가 세는 범위가 **지금 볼 수 있는 구**뿐이다(2026-08-22a).
  // 예전에는 전국을 세서, 화면이 보여주지도 않는 지역까지 섞인 숫자를 각주가 말했다.
  const basisPhrase = stats
    ? `근거: ${formatQuarter(stats.snapshot_ym)} 상권정보 중 서비스 지역(지금 볼 수 있는 구) ${stats.store_cnt.toLocaleString('ko-KR')}곳 기준.`
    : '근거: 서비스 지역(지금 볼 수 있는 구)의 상권정보 최신 분기 기준.';

  return (
    <section className="stack">
      <header className="stack__head">
        <h2 className="stack__title">{head.bld_nm || '(이름 없는 건물)'}</h2>
        <p className="stack__addr">{head.road_addr || '주소 없음'}</p>
        <dl className="stack__facts">
          <div>
            <dt>사용승인</dt>
            <dd>{formatApproveDate(head.approve_date)}</dd>
          </div>
          <div>
            <dt>건물 종류</dt>
            <dd>{head.is_jiphap ? '집합건물' : '일반건물'}</dd>
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
        </dl>
      </header>

      {/*
        여기부터 아래가 **카드 다섯 장**이다(로드맵 Wave 2 『한 장 요약 접힘 틀』).
        제목·역할 태그·기본 펼침은 전부 `SECTION_PLAN` 한 표에서 온다 — 카드마다 따로
        정하면 "첫 화면에 몇 장이 펼쳐져 있나"를 아무 데서도 셀 수 없어 상한(4장)이
        조용히 깨진다.
      */}
      <DistrictCard info={districts} />

      <SectionCard
        plan={SECTION_PLAN.floors}
        className="card--floors"
        summary={`층 ${floors.length}개 · 점포 ${totalStores.toLocaleString('ko-KR')}곳`}
        openSignal={floorsOpenSignal}
        onToggle={setFloorsCardOpen}
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

        <ol className="floors">
          {floors.map((f) => {
            // 면적이 아예 없는 층(그 층이 전부 연면적 제외분 — 전체의 약 3%)에는 막대를
            // 그리지 않는다. 최소 폭 2%를 강제하면 "면적 미상"이 "아주 좁은 층"처럼 보인다.
            const hasArea = f.floor_area_m2 != null;
            const ratio = hasArea ? f.floor_area_m2! / maxArea : 0;
            const isOpen = openFloor === f.floor_no;
            const txCount = txCountByFloor.get(f.floor_no) ?? 0;
            return (
              // 옥탑도 지하와 같은 "근거 없는 층"이라 색으로 갈라 둔다(결정 0001 가드 4).
              // id 는 참고 시세 줄에서 이 층으로 스크롤할 때 쓴다.
              <li
                key={f.floor_no}
                id={`floor-${f.floor_no}`}
                className={`floor${
                  f.floor_no < 0 ? ' floor--under' : f.floor_no === 99 ? ' floor--roof' : ''
                }`}
              >
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

                {isOpen && <FloorDetail floor={f} />}
              </li>
            );
          })}
        </ol>
      </SectionCard>

      {/*
        둘레의 업종 분포(결정 0014). 자기가 알아서 묻고, 못 읽으면 스스로 사라진다
        — 마이그레이션 적용 전 라이브에서는 함수가 없어(PGRST202) 그 상태가 된다.

        ⚠️ 여기 숫자는 **이 건물만의 점포가 아니다** — 이 땅 둘레(속한 상권 · 반경 500m)의
           이웃 가게까지 센 것이고 이 건물 것도 그 안에 포함된다. 바로 위 층 목록의 점포
           칸과 세는 대상이 다르므로 두 숫자를 견주면 안 된다.
        ⓘ 실제로 층 목록 **바로 아래**에 붙어 있어 눈으로는 이어져 보인다. 그래서 갈라
           놓는 일은 자리가 아니라 **말**이 한다 — 섹션 제목("둘레의")과 첫 줄("이 건물만이
           아니라…")이 그 장치다. 자리를 옮겨 해결한 것이 아니니 그 문구를 지우지 말 것.
      */}
      <IndustryMixSection pnu={building.pnu} />

      <TransactionSection txs={txs} stats={txStats} />

      <PriceBandSection
        bands={bands}
        failed={bandsFailed}
        floors={floors}
        hasTxStats={txStats !== null && txStats.length > 0}
        // 층 목록이 접혀 있으면 "펼쳐진 층"이 없는 것이다 — 접힌 카드 속의 층을 두고
        // 시세 줄이 "펼쳐져 있음"이라 말하면 그 말이 그대로 거짓이 된다.
        openFloor={floorsCardOpen ? openFloor : null}
        onPickFloor={(no) => {
          setOpenFloor(no);
          // 층 목록을 접어 뒀더라도 다시 펼친다 — 안 그러면 눌러도 화면이 안 변한다.
          setFloorsOpenSignal((n) => n + 1);
          // ⚠️ 스크롤은 **다음 그림이 그려진 뒤**로 미룬다. 카드가 접혀 있었다면 이 순간
          //    그 층은 아직 화면에 없어서, 지금 찾으면 못 찾는다.
          // ⚠️ getElementById 로 찾는다 — 지하 층의 id 는 "floor--1" 이라
          //    querySelector('#floor--1') 는 잘못된 선택자로 예외가 난다.
          //    jsdom 에는 scrollIntoView 가 없어 `?.` 를 반드시 붙인다.
          const paint =
            typeof requestAnimationFrame === 'function'
              ? requestAnimationFrame
              : (cb: () => void) => setTimeout(cb, 0);
          paint(() => {
            document.getElementById(`floor-${no}`)?.scrollIntoView?.({ block: 'nearest' });
          });
        }}
      />

      <p className="grade">
        <span className="grade__badge">D등급 · 간접 추론</span>
        점포 목록은 호수가 아니라 <strong>“땅 + 층”</strong>으로 맞춘 값입니다. 어느 호실인지까지는
        알 수 없습니다. 면적·용도와 위 건물 스펙(연면적·용적률·건폐율·주차)은 건축물대장{' '}
        <strong>실측(A등급)</strong>입니다. 대장에 안 적힌 칸은 “미상”으로 둡니다 — 원본이
        미기재를 <strong>0</strong>으로 주기 때문에 0을 값으로 적으면 없는 사실이 생깁니다.
      </p>
      <p className="grade grade--sub">
        <strong>점포 수는 실제와 다를 수 있습니다.</strong> ① <strong>빠짐</strong> — 상권정보에 층이
        적히지 않은 점포가 <strong>{missingPhrase}</strong>인데, 이런 점포는 어느 층에도 붙지
        않아 목록에서 통째로 빠집니다. ② <strong>겹침</strong> — 한 주소를 여러 점포가 나눠 쓰는
        공유오피스나 같은 땅의 옆 동 점포가 함께 잡혀 실제보다 많아 보일 수 있습니다.
        <br />
        {/*
          이 숫자들은 뷰 v_coverage_stats에서 읽어 온다. v_floor_stack의 점포가
          `snapshot_ym = (select max(snapshot_ym) from unit_business)`로 최신 분기를 자동
          추종하므로, 각주도 같은 기준으로 따라가야 새 분기 적재 때 화면만 틀려지지 않는다.
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
function DistrictCard({ info }: { info: BuildingDistricts | null }) {
  // 아직 안 왔거나 못 읽었으면 카드 자체를 안 그린다(위 useEffect에서 콘솔 경고만 남긴다).
  if (!info) return null;

  return (
    <SectionCard
      plan={SECTION_PLAN.district}
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
 *    것만 한다. 추정 밴드(Stage B)는 결정 0013 으로 결재됐고, 기준을 넘은 구 × 2층·3층+
 *    에서만 아래 `PriceBandSection` 이 카드를 갈라 낸다 — **이 블록에는 여전히 넣지 않는다.**
 *    사실과 추정을 가르는 것이 이 화면의 신뢰이기 때문이다.
 *
 * 두 블록이 하는 말이 다르다:
 *  ① 이 땅의 이력 — 있는 건물에만 나온다(자기 거래가 있는 필지는 서울 1.8% 뿐이다).
 *  ② 구의 단가 분포 — 항상 나온다. ①이 비어 있어도 "이 동네가 어디쯤인지"는 말할 수 있다.
 */
function TransactionSection({
  txs,
  stats,
}: {
  txs: ParcelTransaction[] | null;
  stats: SigunguTxStat[] | null;
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
    hasStats ? `${guName ? `${guName} ` : ''}층대별 단가` : null,
  ]
    .filter((s): s is string => s !== null)
    .join(' · ');

  return (
    <SectionCard plan={SECTION_PLAN.tx} className="tx" summary={summary}>
      {hasHistory && <ParcelTxList txs={txs!} />}
      {hasStats && <SigunguTxBands stats={stats!} />}
    </SectionCard>
  );
}

/** ① 이 땅에서 신고된 거래 목록. */
function ParcelTxList({ txs }: { txs: ParcelTransaction[] }) {
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
      <ul className="tx__list">
        {txs.map((t, i) => (
          <li key={i}>
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
          </li>
        ))}
      </ul>
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

  return (
    <div className="tx__block">
      <h4 className="tx__sub">{guName ? `${guName} 층대별 거래 단가` : '층대별 거래 단가'}</h4>
      <ul className="tx__bands">
        {stats.map((s) => {
          const enough = s.n >= MIN_SAMPLE;
          return (
            <li key={s.floor_band}>
              <span className="tx__band">{s.floor_band}</span>
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
      <p className="grade">
        <span className="grade__badge">A등급 · 실거래</span>
        추정한 값이 아니라 <strong>신고된 거래를 그대로 센 값</strong>입니다. 표본이{' '}
        {MIN_SAMPLE}건 미만인 층대는 수치를 적지 않습니다 — 몇 건으로 낸 가운데값은 숫자
        모양만 통계이기 때문입니다.
      </p>
      <p className="tx__src">
        출처: 국토교통부 상업업무용 부동산 매매 실거래가 ·{' '}
        {guName ? `${guName} ` : ''}집합(구분소유) 거래
        {from ? ` ${formatYearMonth(from)} 이후 계약분` : ''} 집계 · 전체 표본{' '}
        {total.toLocaleString('ko-KR')}건.
      </p>
    </div>
  );
}

function FloorDetail({ floor }: { floor: FloorRow }) {
  const uses = floor.uses ?? [];
  const stores = floor.stores ?? [];

  return (
    <div className="detail">
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
    </div>
  );
}
