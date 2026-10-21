import { describe, it, expect } from 'vitest';
import { firstTab, historyMarkOf, tabAfterRoleChange, tabsFor, TAB_LABEL, HISTORY_KEY } from './appTabs';

describe('휴대폰 아래 탭(결정 0039 W4a) — 고르기 규칙', () => {
  it('탭 넷 — 중개사만 지도 자리가 「뽑은 건물」(👤 2번 「가」)', () => {
    const labels = (r: Parameters<typeof tabsFor>[0]) => tabsFor(r).map((t) => TAB_LABEL[t]);
    expect(labels(null)).toEqual(['찾기', '지도', '건물', '더보기']);
    expect(labels('투자자')).toEqual(['찾기', '지도', '건물', '더보기']);
    expect(labels('창업자')).toEqual(['찾기', '지도', '건물', '더보기']);
    expect(labels('중개사')).toEqual(['찾기', '건물', '뽑은 건물', '더보기']);
  });

  it('첫 탭 — 건물 직행 링크 = 건물 · 창업자 = 지도(0036 ④) · 나머지 = 찾기', () => {
    expect(firstTab(null, false)).toBe('find');
    expect(firstTab('투자자', false)).toBe('find');
    expect(firstTab('중개사', false)).toBe('find');
    expect(firstTab('창업자', false)).toBe('map');
    for (const r of [null, '투자자', '창업자', '중개사'] as const) expect(firstTab(r, true)).toBe('building');
  });

  it('역할이 바뀌어 그 탭이 사라지면 찾기 · 있으면 그대로', () => {
    expect(tabAfterRoleChange('map', '중개사')).toBe('find');
    expect(tabAfterRoleChange('printed', '투자자')).toBe('find');
    expect(tabAfterRoleChange('printed', null)).toBe('find');
    expect(tabAfterRoleChange('building', '중개사')).toBe('building');
    expect(tabAfterRoleChange('more', '창업자')).toBe('more');
    expect(tabAfterRoleChange('map', '창업자')).toBe('map');
  });

  it('뒤로가기 표식 — 우리 꼴만 읽고 나머지는 null(양성 대조 포함)', () => {
    expect(historyMarkOf({ [HISTORY_KEY]: 'bld' })).toBe('bld');
    expect(historyMarkOf({ [HISTORY_KEY]: 'base', other: 1 })).toBe('base');
    expect(historyMarkOf(null)).toBeNull();
    expect(historyMarkOf(undefined)).toBeNull();
    expect(historyMarkOf('bld')).toBeNull();
    expect(historyMarkOf({ [HISTORY_KEY]: 'x' })).toBeNull();
    expect(historyMarkOf({})).toBeNull();
  });
});
