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

/** 첫 화면에 펼쳐지는 카드 수. 상한을 지키는지 세는 데 쓴다. */
export function countDefaultOpen(
  plan: Readonly<Record<string, SectionPlan>> = SECTION_PLAN,
): number {
  return Object.values(plan).filter((s) => s.defaultOpen).length;
}
