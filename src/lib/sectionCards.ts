/**
 * 층별 화면의 "한 장 요약" 카드 배치 — 로드맵 Wave 2 『한 장 요약 접힘 틀』.
 *
 * 로드맵이 정한 규칙은 두 줄이다:
 *   · 섹션 표시 예산 — **첫 화면 펼침 상한 4개**, 나머지는 접힘
 *   · 새 카드에는 **역할 태그**(투자자/창업자/중개사)와 기본 접힘 여부를 처음부터 부여
 *
 * 그 둘을 **한 표**로 적어 둔 것이 이 파일이다. 카드마다 제 파일에서 따로 정하면
 * "지금 몇 개가 펼쳐져 있나"를 아무 데서도 셀 수 없어 상한이 조용히 깨진다
 * (`sectionCards.test.ts` 의 가드가 이 표를 센다).
 */

/**
 * 첫 화면에 **펼쳐 둘 수 있는 카드 수의 상한**(로드맵 Wave 2).
 *
 * 늘리려면 로드맵을 먼저 고친다 — 이 숫자만 올리면 화면이 로드맵과 다른 말을 하게 된다.
 */
export const SECTION_EXPAND_BUDGET = 4;

/**
 * 이 카드를 특히 누가 보는가.
 *
 * ⓘ `중개사` 는 지금 어느 카드에도 안 붙어 있다(현행 다섯 카드는 공통·창업자·투자자뿐).
 *    그래도 어휘에 남겨 둔다 — 역할 셋은 첫 화면 역할 선택(전략 메모)에서 온 고정 목록이라,
 *    새 카드가 생길 때 여기 없는 말을 즉석에서 지어내는 것을 막는 것이 이 타입의 일이다.
 */
export type SectionRole = '공통' | '투자자' | '창업자' | '중개사';

export type SectionPlan = {
  /** 카드 제목. 화면에 적히는 유일한 정본이라 컴포넌트 안에 또 적지 않는다. */
  readonly title: string;
  readonly role: SectionRole;
  /** 첫 화면에서 펼쳐 둘까. 합계는 SECTION_EXPAND_BUDGET 을 넘을 수 없다. */
  readonly defaultOpen: boolean;
};

/**
 * 층별 화면 카드(장수는 이 표가 정본이라 글로 적지 않는다). **순서는 역할을 고르기 전 화면에
 * 그리는 순서와 같다**(위 → 아래 · `sectionOrder(null)` 이 이 표의 순서를 그대로 쓴다).
 * 역할을 고르면 순서·펼침만 아래 `ROLE_SECTION_LAYOUT` 이 덮어쓴다(제목·역할 태그는 이 표 그대로).
 *
 * 무엇을 펼쳐 둘지는 자리가 아니라 **역할**로 정했다:
 *   · `공통` 은 누가 오든 먼저 봐야 하므로 전부 펼침 (속한 상권 · 층 목록)
 *   · 역할 전용 카드는 역할마다 **하나씩만** 펼침 (창업자 = 업종 분포, 투자자 = 실거래)
 *   · 그래서 투자자의 두 번째 카드인 『참고 매매 시세』가 접힌다. 접는 기준을 "맨 아래라서"가
 *     아니라 "**사실이 먼저, 추정은 펼쳐 봐야 보인다**"로 잡은 것이다 — 이 화면에서 사실과
 *     추정을 가르는 다른 장치들(카드 테두리·C등급 배지)과 같은 뜻이다.
 *   · 여섯째 『상권 임대 동향』도 접힌다. 이쪽은 추정이 아니라 조사값이지만 **이 건물이
 *     아닌 상권의 값**이라, 한정어 없이 먼저 눈에 들어오면 이 건물 임대료로 읽힌다.
 *
 * ⚠️ 접힘은 **숨김이 아니다.** 접힌 카드도 제목 + 핵심 한 줄(`summary`)은 그대로 보인다
 *    (`SectionCard`). 요약까지 감추면 "안 보여 준다"가 되어 정보 우선 방침과 어긋난다.
 */
export const SECTION_PLAN = {
  district: { title: '속한 상권', role: '공통', defaultOpen: true },
  floors: { title: '층 목록', role: '공통', defaultOpen: true },
  industry: { title: '둘레의 업종 분포', role: '창업자', defaultOpen: true },
  tx: { title: '실거래 기록', role: '투자자', defaultOpen: true },
  band: { title: '참고 매매 시세 (추정값)', role: '투자자', defaultOpen: false },
  /**
   * 상권 임대 동향(결정 0024). **접힌 채로 시작한다** — 펼침 상한이 이미 넷이라 그렇기도
   * 하지만, 그것 말고도 이 카드는 **이 건물의 임대료가 아니라 상권 조사값**이라 먼저
   * 눈에 들어오면 사람이 이 건물 값으로 읽는다. 요약 한 줄이 "무엇이 들어 있는지"만
   * 말하고, 값은 펼쳐서 그 한정어와 함께 읽게 한다.
   */
  rent: { title: '상권 임대 동향 (부동산원 조사)', role: '투자자', defaultOpen: false },
  /**
   * 상권 개업·폐업(결정 0033). **접힌 채로 시작한다** — 임대 동향과 같은 이유다. 이 카드의
   * 숫자는 **이 건물이 아니라 이 건물이 속한 서울시 상권 전체**의 공표값이라, 한정어 없이
   * 먼저 눈에 들어오면 이 건물의 개업·폐업으로 읽힌다. 그리고 첫 화면 펼침 상한(4장)은
   * 이미 공통 둘과 역할별 하나씩이 쓰고 있다 — 창업자 몫은 업종 분포가 펼쳐 둔다.
   */
  openclose: { title: '상권 개업·폐업 (서울시 공표)', role: '창업자', defaultOpen: false },
} as const satisfies Record<string, SectionPlan>;

export type SectionKey = keyof typeof SECTION_PLAN;

/**
 * 첫 화면 역할 단추로 **고를 수 있는** 역할(결정 0036 결정 18). `공통` 은 카드에 붙는 태그일 뿐
 * 사람이 고르는 역할이 아니라 뺀다.
 */
export type ViewerRole = Exclude<SectionRole, '공통'>;

/** 단추 차례 그대로. */
export const VIEWER_ROLES: readonly ViewerRole[] = ['투자자', '창업자', '중개사'];

export function isViewerRole(v: unknown): v is ViewerRole {
  return typeof v === 'string' && (VIEWER_ROLES as readonly string[]).includes(v);
}

/** 역할 한 벌 — 카드를 그릴 차례(전부 · 빠짐없이)와 펼쳐 둘 카드. */
export type RoleLayout = {
  readonly order: readonly SectionKey[];
  readonly open: readonly SectionKey[];
};

/**
 * 역할마다 카드 **순서·펼침**(👤 결정 0036 결정 18 ②). 자료는 한 벌이고 바뀌는 것은 이 둘뿐이다.
 *
 * ⛔ `order` 는 위 `SECTION_PLAN` 의 칸을 **전부 한 번씩** 담는다 — 빠뜨리면 그 역할에서 카드가
 *    조용히 사라진다(`sectionCards.test.ts` 가 지킨다). 펼침 수는 벌마다 `SECTION_EXPAND_BUDGET` 이하.
 * ⓘ 역할을 고르기 전에는 이 표를 안 쓴다 — `SECTION_PLAN` 의 순서·펼침 그대로다(결정 18 ①).
 */
export const ROLE_SECTION_LAYOUT = {
  투자자: {
    order: ['district', 'floors', 'tx', 'band', 'rent', 'industry', 'openclose'],
    open: ['district', 'floors', 'tx', 'band'],
  },
  창업자: {
    order: ['district', 'floors', 'industry', 'openclose', 'tx', 'band', 'rent'],
    open: ['district', 'floors', 'industry', 'openclose'],
  },
  중개사: {
    order: ['floors', 'tx', 'district', 'band', 'rent', 'industry', 'openclose'],
    open: ['floors', 'tx', 'district', 'band'],
  },
} as const satisfies Record<ViewerRole, RoleLayout>;

/** 한 벌의 펼침을 `SECTION_PLAN` 에 덮어쓴 카드 표(제목·역할 태그는 그대로). */
export function plansFromLayout(layout: RoleLayout): Record<SectionKey, SectionPlan> {
  const keys = Object.keys(SECTION_PLAN) as SectionKey[];
  return Object.fromEntries(
    keys.map((k) => [k, { ...SECTION_PLAN[k], defaultOpen: layout.open.includes(k) }]),
  ) as Record<SectionKey, SectionPlan>;
}

/**
 * ⛔ 역할마다 **한 번만** 만들어 둔다. `SectionCard` 는 받은 칸이 **다른 객체**로 바뀔 때 펼침을 새
 *    표대로 다시 세우는데, 부를 때마다 새 객체를 만들면 화면이 다시 그려질 때마다(자료가 도착할
 *    때마다) 사람이 연 카드가 도로 접힌다.
 */
const ROLE_PLANS = Object.fromEntries(
  VIEWER_ROLES.map((r) => [r, plansFromLayout(ROLE_SECTION_LAYOUT[r])]),
) as Record<ViewerRole, Record<SectionKey, SectionPlan>>;

/** 이 역할로 그릴 카드 표. 역할이 없으면 `SECTION_PLAN` 그 자체(지금 화면 그대로). */
export function sectionPlansFor(
  role: ViewerRole | null,
): Readonly<Record<SectionKey, SectionPlan>> {
  return role === null ? SECTION_PLAN : ROLE_PLANS[role];
}

/** 이 역할로 카드를 그릴 차례. 역할이 없으면 `SECTION_PLAN` 의 칸 순서. */
export function sectionOrder(role: ViewerRole | null): readonly SectionKey[] {
  return role === null
    ? (Object.keys(SECTION_PLAN) as SectionKey[])
    : ROLE_SECTION_LAYOUT[role].order;
}

/** 입구(지역 고르기 아래)의 두 덩어리 — 검색창과 상권 지도. */
export type EntryBlockKey = 'search' | 'map';

/**
 * 입구 두 덩어리를 그릴 차례(👤 결정 0036 결정 18 ④). **창업자만** 지도가 검색창 위다 — 창업자는
 * 건물 이름을 모르고 동네부터 본다. 다른 역할·역할 없음은 지금 차례 그대로(검색 → 지도).
 * ⓘ App 이 이름 key 를 단 배열로 그린다 — 차례가 바뀌어도 검색어·지도가 다시 태어나지 않는다.
 */
export function entryBlockOrder(role: ViewerRole | null): readonly EntryBlockKey[] {
  return role === '창업자' ? ['map', 'search'] : ['search', 'map'];
}

/**
 * **입구 화면**(구는 골랐고 건물은 아직 안 고른 상태)의 카드.
 *
 * ⚠️ 위 `SECTION_PLAN` 과 **일부러 갈라 둔다.** 저 표의 펼침 상한 4장은 "층별 화면 한
 *    벌을 스크롤할 때 몇 개가 펼쳐져 있는가"라는 예산이다. 다른 화면의 카드를 그 표에
 *    끼워 넣으면 한 예산이 두 화면에 걸쳐 나뉘어, 층별 화면에 카드를 하나 더 붙일 자리가
 *    이유 없이 줄어든다(그리고 그 줄어듦은 아무 시험도 안 깬 채 조용히 일어난다).
 *
 * ⛔ 입구 카드는 **접힌 채로 시작한다.** 입구에서 사람이 하려는 일은 건물을 찾는 것이라,
 *    그 앞을 목록으로 가로막지 않는다 — 제목과 한 줄 요약으로 "있다"만 알린다.
 *    (`entry-section-plan.test` 성격의 가드가 `sectionCards.test.ts` 에 있다.)
 */
export const ENTRY_SECTION_PLAN = {
  /**
   * LH 상가 분양·입점 공고.
   *
   * 역할을 `공통` 으로 둔 이유 — 분양 입찰은 투자자, 임대 추첨·입찰은 창업자가 보는
   * 것이라 한쪽으로 못 정한다. 역할 태그는 하나만 붙일 수 있으므로, 반쪽만 부르는
   * 대신 아무도 안 내치는 쪽을 골랐다.
   */
  lhNotice: { title: 'LH 상가 분양·입점 공고', role: '공통', defaultOpen: false },
  /**
   * 참고 시세 성적표(로드맵 Wave 4 — 성적표 공개 + 방법 공개).
   *
   * 역할을 `투자자` 로 둔 이유 — 이 카드가 말하는 것은 **참고 매매 시세가 얼마나 맞나**
   * 이고, 그 값을 보는 것은 층별 화면의 『참고 매매 시세』 카드를 여는 사람이다(그쪽도
   * 투자자다). 창업자에게 필요한 임대 이야기는 여기서 하지 않는다.
   *
   * ⛔ 요약 한 줄이 **고른 구의 판정**을 말한다 — 접힌 채로도 "우리 구는 받나 못 받나"는
   *    읽힌다. 접힘이 숨김이 아니라는 규칙(SectionCard)이 여기서 특히 중요하다.
   */
  scorecard: { title: '참고 시세는 얼마나 맞나', role: '투자자', defaultOpen: false },
  /**
   * 동네 매매 단가 흐름(결정 0027 · 로드맵 Wave 5).
   *
   * 역할을 `투자자` 로 둔 이유 — 이 카드가 답하는 것은 "이 동네 단가가 그동안 어떻게
   * 움직였나"이고, 그 흐름을 보는 것은 사고파는 쪽이다. 창업자에게 필요한 임대·업종
   * 이야기는 여기서 하지 않는다.
   *
   * ⛔ 제목에 자료 범위를 **숫자로 박지 않는다** — 백필이 더 들어오거나 새 해가 쌓이면
   *    제목만 옛말이 된다. 범위는 서버가 준 첫 달·끝 달로 요약 줄에 적는다.
   * ⛔ 접힌 채로 시작한다(입구 카드 규칙). 요약 한 줄이 **언제부터 언제까지 몇 건인지**를
   *    말하므로, 접혀 있어도 "볼 것이 있나 없나"는 읽힌다.
   */
  txFlow: { title: '동네 매매 단가 흐름 (실거래)', role: '투자자', defaultOpen: false },
} as const satisfies Record<string, SectionPlan>;

/** 첫 화면에 펼쳐지는 카드 수. 상한을 지키는지 세는 데 쓴다. */
export function countDefaultOpen(
  plan: Readonly<Record<string, SectionPlan>> = SECTION_PLAN,
): number {
  return Object.values(plan).filter((s) => s.defaultOpen).length;
}
