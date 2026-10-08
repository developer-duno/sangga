import { describe, it, expect } from 'vitest';
import {
  ENTRY_SECTION_PLAN,
  ROLE_SECTION_LAYOUT,
  SECTION_EXPAND_BUDGET,
  SECTION_PLAN,
  VIEWER_ROLES,
  countDefaultOpen,
  entryBlockOrder,
  isViewerRole,
  plansFromLayout,
  sectionOrder,
  sectionPlansFor,
  type RoleLayout,
  type SectionKey,
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
    // 일부러 카드를 전부 펼친 표를 만들어 본다. 이 줄이 통과해야 위 시험이
    // "무엇이든 통과하는 시험"이 아니라는 것이 증명된다.
    const overBudget: Record<string, SectionPlan> = Object.fromEntries(
      Object.entries(SECTION_PLAN).map(([k, v]) => [k, { ...v, defaultOpen: true }]),
    );
    expect(countDefaultOpen(overBudget)).toBeGreaterThan(SECTION_EXPAND_BUDGET);
  });

  it('접힌 카드가 적어도 한 장은 있다 (틀이 실제로 쓰이는지)', () => {
    // 카드가 전부 펼침이면 접힘 틀이 화면에서 한 번도 안 쓰인다 —
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

/**
 * 입구 화면의 배치표.
 *
 * 층별 화면 표와 **갈라 둔 것 자체**가 여기서 지키는 것이다 — 한 표에 섞으면 층별 화면의
 * 펼침 예산(4장)이 두 화면에 걸쳐 나뉘어, 층별 카드를 하나 더 붙일 자리가 이유 없이
 * 줄어든다. 그 줄어듦은 화면도 멀쩡하고 아무 시험도 안 깨진 채 조용히 일어난다.
 */
describe('ENTRY_SECTION_PLAN — 입구 카드', () => {
  it('입구 카드는 전부 접힌 채로 시작한다 (건물 찾는 길을 가로막지 않는다)', () => {
    expect(countDefaultOpen(ENTRY_SECTION_PLAN)).toBe(0);
  });

  it('★ 층별 화면 표와 섞여 있지 않다 (펼침 예산이 두 화면에 걸쳐 나뉘지 않게)', () => {
    for (const key of Object.keys(ENTRY_SECTION_PLAN)) {
      expect(Object.keys(SECTION_PLAN)).not.toContain(key);
    }
    // 층별 화면의 예산은 입구 카드가 늘어도 그대로다.
    expect(countDefaultOpen(SECTION_PLAN)).toBeLessThanOrEqual(SECTION_EXPAND_BUDGET);
  });

  it('역할 태그는 정해진 넷 중 하나다 (즉석에서 새 말을 지어내지 않는다)', () => {
    const allowed = ['공통', '투자자', '창업자', '중개사'];
    for (const [key, plan] of Object.entries(ENTRY_SECTION_PLAN)) {
      expect(allowed, `${key} 의 역할`).toContain(plan.role);
    }
  });

  it('제목에는 절대 규칙 2 의 금칙어가 없다', () => {
    for (const plan of Object.values(ENTRY_SECTION_PLAN)) {
      for (const banned of ['적정가격', '적정가', '평가액', '감정가', '가치평가']) {
        expect(plan.title.includes(banned)).toBe(false);
      }
    }
  });
});

/**
 * 역할별 카드 순서·펼침 세 벌(👤 결정 0036 결정 18).
 *
 * 한 벌이던 상한 가드를 **세 벌 각각**에 건다 — 한 벌만 세면 다른 벌이 5장을 펼쳐도 초록이다.
 * 순서가 카드를 **빠짐없이 한 번씩** 담는지도 본다 — 빠뜨리면 그 역할에서 카드가 조용히 사라진다.
 * 탐지는 아래 작은 함수 둘로 빼서, 가드 본체와 양성 대조가 같은 함수를 지나게 한다.
 */

/** 이 벌이 펼쳐 두는 카드 수. */
function openCount(layout: RoleLayout): number {
  return countDefaultOpen(plansFromLayout(layout));
}

/**
 * 순서가 층별 화면 카드를 빠짐없이 한 번씩 담나.
 * 못 보는 것: 차례가 결정 표와 같은지는 안 본다 — 그건 `FloorStack.test.tsx` 의 표 대조가 본다.
 */
function isFullOrder(order: readonly string[]): boolean {
  const all = Object.keys(SECTION_PLAN);
  return (
    order.length === all.length &&
    new Set(order).size === all.length &&
    all.every((k) => order.includes(k))
  );
}

describe('ROLE_SECTION_LAYOUT — 역할 세 벌', () => {
  for (const role of VIEWER_ROLES) {
    it(`${role} — 펼쳐 두는 카드가 상한(4장)을 넘지 않는다`, () => {
      expect(openCount(ROLE_SECTION_LAYOUT[role])).toBeLessThanOrEqual(SECTION_EXPAND_BUDGET);
      // sectionPlansFor 를 거쳐도 같은 수다(화면이 실제로 쓰는 길).
      expect(countDefaultOpen(sectionPlansFor(role))).toBe(openCount(ROLE_SECTION_LAYOUT[role]));
    });

    it(`${role} — 순서가 카드를 빠짐없이 한 번씩 담는다`, () => {
      expect(isFullOrder(ROLE_SECTION_LAYOUT[role].order)).toBe(true);
      expect(sectionOrder(role)).toEqual(ROLE_SECTION_LAYOUT[role].order);
    });
  }

  it('★ 양성 대조 — 한 벌을 5장 펼친 사본은 상한 가드에 걸린다', () => {
    const over: RoleLayout = {
      ...ROLE_SECTION_LAYOUT.창업자,
      open: [...ROLE_SECTION_LAYOUT.창업자.open, 'tx'],
    };
    expect(openCount(over)).toBe(SECTION_EXPAND_BUDGET + 1);
    expect(openCount(over)).toBeGreaterThan(SECTION_EXPAND_BUDGET);
  });

  it('★ 양성 대조 — 카드를 빠뜨리거나 겹친 순서는 걸린다', () => {
    const order = ROLE_SECTION_LAYOUT.투자자.order;
    expect(isFullOrder(order.slice(1))).toBe(false); // 하나 빠뜨림
    expect(isFullOrder([order[1], ...order.slice(1)])).toBe(false); // 같은 칸 두 번 + 하나 빠뜨림
  });

  it('역할을 고르기 전은 SECTION_PLAN 그대로다 (지금 화면 — 결정 18 ①)', () => {
    expect(sectionPlansFor(null)).toBe(SECTION_PLAN);
    expect(sectionOrder(null)).toEqual(Object.keys(SECTION_PLAN));
  });

  it('제목·역할 태그는 역할마다 안 바뀐다 (바뀌는 것은 순서·펼침뿐)', () => {
    for (const role of VIEWER_ROLES) {
      const plans = sectionPlansFor(role);
      for (const k of Object.keys(SECTION_PLAN) as SectionKey[]) {
        expect(plans[k].title).toBe(SECTION_PLAN[k].title);
        expect(plans[k].role).toBe(SECTION_PLAN[k].role);
      }
    }
  });

  it('★ 같은 역할이면 같은 객체를 돌려준다 (다시 그릴 때마다 사람이 연 카드가 접히지 않게)', () => {
    // SectionCard 는 받은 칸이 다른 객체가 되면 펼침을 새로 세운다 — 부를 때마다 새로 만들면
    // 자료가 도착해 다시 그려질 때마다 연 카드가 도로 접힌다.
    for (const role of VIEWER_ROLES) {
      expect(sectionPlansFor(role)).toBe(sectionPlansFor(role));
      expect(sectionPlansFor(role).floors).toBe(sectionPlansFor(role).floors);
    }
    // 역할이 다르면 카드마다 다른 객체다 — 그래야 바꿀 때 펼침이 새 표대로 선다.
    expect(sectionPlansFor('투자자').district).not.toBe(sectionPlansFor('창업자').district);
    expect(sectionPlansFor('투자자').district).not.toBe(SECTION_PLAN.district);
  });

  it('고를 수 있는 역할은 셋이다 (공통은 카드 태그일 뿐)', () => {
    expect(VIEWER_ROLES).toEqual(['투자자', '창업자', '중개사']);
    expect(isViewerRole('공통')).toBe(false);
    expect(isViewerRole('창업자')).toBe(true);
    expect(isViewerRole(null)).toBe(false);
  });
});

/**
 * 입구 두 덩어리(검색창·상권 지도)의 차례(👤 결정 0036 결정 18 ④). 창업자만 지도가 위다.
 * 다른 역할·역할 없음은 지금 차례 그대로(검색 → 지도) — 양성 대조로 창업자와 짝지어 본다.
 */
describe('entryBlockOrder — 입구 차례', () => {
  it('창업자 = 지도 → 검색', () => {
    expect([...entryBlockOrder('창업자')]).toEqual(['map', 'search']);
  });
  it('투자자·중개사·역할 없음 = 검색 → 지도(지금 그대로)', () => {
    for (const role of ['투자자', '중개사', null] as const) {
      expect([...entryBlockOrder(role)]).toEqual(['search', 'map']);
    }
  });
});
