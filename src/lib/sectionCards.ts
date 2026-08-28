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
 * 층별 화면 카드 다섯 장. **순서는 화면에 그리는 순서와 같다**(위 → 아래).
 *
 * 무엇을 펼쳐 둘지는 자리가 아니라 **역할**로 정했다:
 *   · `공통` 은 누가 오든 먼저 봐야 하므로 전부 펼침 (속한 상권 · 층 목록)
 *   · 역할 전용 카드는 역할마다 **하나씩만** 펼침 (창업자 = 업종 분포, 투자자 = 실거래)
 *   · 그래서 투자자의 두 번째 카드인 『참고 매매 시세』가 접힌다. 접는 기준을 "맨 아래라서"가
 *     아니라 "**사실이 먼저, 추정은 펼쳐 봐야 보인다**"로 잡은 것이다 — 이 화면에서 사실과
 *     추정을 가르는 다른 장치들(카드 테두리·C등급 배지)과 같은 뜻이다.
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
} as const satisfies Record<string, SectionPlan>;

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
} as const satisfies Record<string, SectionPlan>;

/** 첫 화면에 펼쳐지는 카드 수. 상한을 지키는지 세는 데 쓴다. */
export function countDefaultOpen(
  plan: Readonly<Record<string, SectionPlan>> = SECTION_PLAN,
): number {
  return Object.values(plan).filter((s) => s.defaultOpen).length;
}
