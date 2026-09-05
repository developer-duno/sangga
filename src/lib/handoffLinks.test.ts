import { describe, it, expect } from 'vitest';

import { GUIDE_LINES, HANDOFF_GROUPS, ROLE_STARTS } from './handoffLinks';
import { SECTION_PLAN } from './sectionCards';

/**
 * 넘기기 링크 목록과 안내 문장의 **가드**.
 *
 * 조용히 틀리기 쉬운 자리 넷:
 *  ① 주소가 `http:` 이거나 상대 주소로 바뀌는 것 — 새 창으로 열리는 링크라 눈에 안 띈다.
 *  ② 카드를 새로 붙이면서 안내 한 줄을 빠뜨리는 것 — 화면은 멀쩡하고 그 카드만 설명이
 *     없다(타입이 1차로 막지만, 시험은 타입 검사 없이도 도는 자리라 한 번 더 본다).
 *  ③ 안내에 숫자를 적는 것 — "카드 여섯 장"처럼 적으면 카드가 느는 날 이 문장만 옛말이
 *     된다. 장수·반경·건수는 전부 화면이 자료에서 읽는 값이다.
 *  ④ 절대 규칙 2 의 금칙어가 안내 문장에 섞이는 것.
 */

/** 절대 규칙 2 — 감정평가는 감정평가사 독점 업무라 이 말들을 어디에도 쓰지 않는다. */
const BANNED = ['적정가격', '적정가', '평가액', '감정가', '가치평가'];

/** 화면에 글자로 나가는 모든 문장(그룹 이름·설명·링크 이름·역할·안내 줄). */
function allText(): string[] {
  return [
    ...HANDOFF_GROUPS.flatMap((g) => [g.need, g.what, ...g.links.map((l) => l.label)]),
    ...ROLE_STARTS.flatMap((r) => [r.role, r.how]),
    ...Object.values(GUIDE_LINES),
  ];
}

describe('HANDOFF_GROUPS — 넘기는 곳 목록', () => {
  it('묶음이 넷이다 (결정 0014 §1 의 매물·분석·매출·지도)', () => {
    expect(HANDOFF_GROUPS).toHaveLength(4);
  });

  it('묶음마다 링크가 적어도 하나 있다 (이름만 있고 갈 곳 없는 줄을 안 만든다)', () => {
    for (const g of HANDOFF_GROUPS) {
      expect(g.links.length, `${g.need} 의 링크 수`).toBeGreaterThan(0);
    }
  });

  it('주소는 전부 https:// 로 시작한다', () => {
    for (const g of HANDOFF_GROUPS) {
      for (const l of g.links) {
        expect(l.href.startsWith('https://'), `${l.label} 의 주소: ${l.href}`).toBe(true);
      }
    }
  });

  it('같은 주소를 두 번 적지 않는다', () => {
    const hrefs = HANDOFF_GROUPS.flatMap((g) => g.links.map((l) => l.href));
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it('묶음 id 가 서로 다르다 (그리는 쪽의 key 가 겹치지 않게)', () => {
    const ids = HANDOFF_GROUPS.map((g) => g.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe('GUIDE_LINES — 카드마다 무엇에 답하나', () => {
  it('★ SECTION_PLAN 의 모든 칸에 한 줄씩 있다 (카드만 늘고 안내가 안 느는 것을 막는다)', () => {
    for (const key of Object.keys(SECTION_PLAN)) {
      expect(GUIDE_LINES, `${key} 의 안내 줄`).toHaveProperty(key);
      expect((GUIDE_LINES as Record<string, string>)[key]?.length ?? 0).toBeGreaterThan(0);
    }
  });

  it('없는 카드를 설명하지 않는다 (카드가 사라졌는데 안내만 남는 것도 드리프트다)', () => {
    for (const key of Object.keys(GUIDE_LINES)) {
      expect(Object.keys(SECTION_PLAN), `안내에만 있는 칸: ${key}`).toContain(key);
    }
  });

  it('⛔ 안내 문장에 숫자가 없다 (장수·반경·건수를 글자로 박으면 그날부터 옛말이 된다)', () => {
    for (const [key, line] of Object.entries(GUIDE_LINES)) {
      expect(/[0-9]/.test(line), `${key}: ${line}`).toBe(false);
    }
  });

  it('제목을 여기 또 적지 않는다 (정본은 SECTION_PLAN 하나뿐)', () => {
    // 안내 줄이 제목을 통째로 품고 있으면 화면에 같은 말이 두 번 나오고, 제목이 바뀌는 날
    // 한쪽만 따라간다. 그리는 쪽은 `SECTION_PLAN[key].title` 을 붙여서 쓴다.
    for (const [key, line] of Object.entries(GUIDE_LINES)) {
      const title = SECTION_PLAN[key as keyof typeof SECTION_PLAN].title;
      expect(line.includes(title), `${key} 의 안내가 제목을 그대로 품었다`).toBe(false);
    }
  });
});

describe('절대 규칙 2 — 금칙어', () => {
  it('화면에 나가는 어떤 문장에도 금칙어가 없다', () => {
    for (const text of allText()) {
      for (const banned of BANNED) {
        expect(text.includes(banned), `"${text}" 안의 "${banned}"`).toBe(false);
      }
    }
  });
});

describe('ROLE_STARTS — 역할별 시작점', () => {
  it('역할 셋을 전부 적는다 (결정 0014 §3 의 고정 목록)', () => {
    expect(ROLE_STARTS.map((r) => r.role)).toEqual(['창업자', '투자자', '중개사']);
  });
});
