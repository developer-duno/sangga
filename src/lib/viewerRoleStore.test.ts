import { afterEach, describe, expect, it, vi } from 'vitest';
import { VIEWER_ROLE_STORAGE_KEY, loadViewerRole, saveViewerRole } from './viewerRoleStore';

/**
 * 역할 저장(결정 0036 결정 11·18 · 「지키는 것」 이 기기 저장 ①②⑤).
 *
 * 지키는 것: ① 저장이 막힌 창에서도 죽지 않는다(예외를 삼킨다) ② 이상한 값은 무시한다
 * ③ null 을 저장하면 지운다 ④ 저장하는 것은 역할 하나뿐이다.
 */

/** 시험용 저장소 — 무엇이 적혔는지 들여다볼 수 있게. */
function memoryStorage() {
  const map = new Map<string, string>();
  return {
    map,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
  };
}

/** 저장이 막힌 창 흉내 — 읽기·쓰기·지우기가 모두 예외를 던진다. */
function blockedStorage() {
  const boom = () => {
    throw new DOMException('The operation is insecure.', 'SecurityError');
  };
  return { getItem: boom, setItem: boom, removeItem: boom };
}

afterEach(() => {
  window.localStorage.clear();
});

describe('viewerRoleStore', () => {
  it('저장한 역할을 다시 읽는다', () => {
    const st = memoryStorage();
    saveViewerRole('창업자', st);
    expect(loadViewerRole(st)).toBe('창업자');
    // 담는 것은 역할 하나뿐이다.
    expect([...st.map.entries()]).toEqual([[VIEWER_ROLE_STORAGE_KEY, '창업자']]);
  });

  it('null 을 저장하면 지운다 (고른 단추를 다시 눌러 해제)', () => {
    const st = memoryStorage();
    saveViewerRole('중개사', st);
    saveViewerRole(null, st);
    expect(st.map.size).toBe(0);
    expect(loadViewerRole(st)).toBeNull();
  });

  it('세 역할이 아닌 값은 무시한다 (역할을 고르기 전 화면)', () => {
    const st = memoryStorage();
    for (const bad of ['공통', 'investor', '', ' 투자자', '투자자 ']) {
      st.map.set(VIEWER_ROLE_STORAGE_KEY, bad);
      expect(loadViewerRole(st), JSON.stringify(bad)).toBeNull();
    }
  });

  it('★ 저장이 막힌 창 — 읽기·쓰기·지우기 예외를 삼키고 null 로 선다', () => {
    const st = blockedStorage();
    // 양성 대조: 이 가짜는 정말로 던진다(삼키는 쪽이 없으면 시험이 빨개진다).
    expect(() => st.getItem()).toThrow();
    expect(() => saveViewerRole('투자자', st)).not.toThrow();
    expect(() => saveViewerRole(null, st)).not.toThrow();
    expect(loadViewerRole(st)).toBeNull();
  });

  it('저장소가 아예 없으면(null) 아무 일도 안 한다', () => {
    expect(() => saveViewerRole('투자자', null)).not.toThrow();
    expect(loadViewerRole(null)).toBeNull();
  });

  it('인자를 안 주면 브라우저 저장소를 쓴다', () => {
    saveViewerRole('투자자');
    expect(window.localStorage.getItem(VIEWER_ROLE_STORAGE_KEY)).toBe('투자자');
    expect(loadViewerRole()).toBe('투자자');
    saveViewerRole(null);
    expect(window.localStorage.getItem(VIEWER_ROLE_STORAGE_KEY)).toBeNull();
  });

  it('window.localStorage 에 손대는 것만으로 예외가 나는 창에서도 죽지 않는다', () => {
    // 사이트 자료를 막은 창은 저장소 **접근 자체**가 SecurityError 를 던진다(읽기·쓰기 전에).
    const spy = vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('막힌 창', 'SecurityError');
    });
    try {
      expect(() => saveViewerRole('투자자')).not.toThrow();
      expect(() => saveViewerRole(null)).not.toThrow();
      expect(loadViewerRole()).toBeNull();
      expect(spy).toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });
});
