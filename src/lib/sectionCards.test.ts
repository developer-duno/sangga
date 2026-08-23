import { describe, it, expect } from 'vitest';
import {
  SECTION_EXPAND_BUDGET,
  SECTION_PLAN,
  countDefaultOpen,
  type SectionPlan,
} from './sectionCards';

/**
 * 카드 배치표의 **가드**.
 *
 * 로드맵 Wave 2 가 정한 것은 "첫 화면 펼침 상한 4개"다. 카드를 하나 더 붙이면서 무심코
 * `defaultOpen: true` 로 두면 화면은 멀쩡히 그려지고 아무 시험도 안 깨진 채 상한만
 * 조용히 넘어간다 — 그 조용한 종류를 여기서 잡는다.
 */
describe('SECTION_PLAN — 첫 화면 펼침 상한', () => {
  it('펼쳐 두는 카드가 상한(4장)을 넘지 않는다', () => {
    expect(countDefaultOpen()).toBeLessThanOrEqual(SECTION_EXPAND_BUDGET);
  });

  it('상한을 넘기면 가드가 실제로 잡는다 (가드가 늘 참인 시험이 아니다)', () => {
    // 일부러 다섯 장을 전부 펼친 표를 만들어 본다. 이 줄이 통과해야 위 시험이
    // "무엇이든 통과하는 시험"이 아니라는 것이 증명된다.
    const overBudget: Record<string, SectionPlan> = Object.fromEntries(
      Object.entries(SECTION_PLAN).map(([k, v]) => [k, { ...v, defaultOpen: true }]),
    );
    expect(countDefaultOpen(overBudget)).toBeGreaterThan(SECTION_EXPAND_BUDGET);
  });

  it('접힌 카드가 적어도 한 장은 있다 (틀이 실제로 쓰이는지)', () => {
    // 다섯 장이 전부 펼침이면 접힘 틀이 화면에서 한 번도 안 쓰인다 —
    // 코드는 남아 있는데 아무 일도 안 하는 상태가 된다.
    expect(countDefaultOpen()).toBeLessThan(Object.keys(SECTION_PLAN).length);
  });

  it('역할 태그는 정해진 넷 중 하나다 (즉석에서 새 말을 지어내지 않는다)', () => {
    const allowed = ['공통', '투자자', '창업자', '중개사'];
    for (const [key, plan] of Object.entries(SECTION_PLAN)) {
      expect(allowed, `${key} 의 역할`).toContain(plan.role);
    }
  });

  it('제목에는 절대 규칙 2 의 금칙어가 없다', () => {
    // '참고 매매 시세'는 허용 대체어라 금칙어 목록에 넣지 않는다(절대 규칙 2 의 표).
    for (const plan of Object.values(SECTION_PLAN)) {
      for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) {
        expect(plan.title.includes(banned)).toBe(false);
      }
    }
  });
});
