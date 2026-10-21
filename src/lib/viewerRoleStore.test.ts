import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  BROWSE_ROLE,
  VIEWER_ROLE_STORAGE_KEY,
  loadStoredRole,
  saveStoredRole,
  viewerRoleOf,
} from './viewerRoleStore';

/**
 * 역할 저장(결정 0036 결정 11·18 · 「지키는 것」 이 기기 저장 ①⑤ · 결정 0039 Q3·§7-4).
 *
 * 지키는 것: ① 저장이 막힌 창에서도 죽지 않는다(예외를 삼킨다) ② 모르는 값은 '안 물어봄'(null)으로 본다
 * ③ 해제·둘러보기는 지우지 않고 `둘러보기` 로 적는다(다시 안 묻는다) ④ 저장하는 것은 값 하나뿐이다.
 */

/** 시험용 저장소 — 무엇이 적혔는지 들여다볼 수 있게. */
function memoryStorage() {
  const map = new Map<string, string>();
  return {
    map,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
  };
}

/** 저장이 막힌 창 흉내 — 읽기·쓰기가 모두 예외를 던진다. */
function blockedStorage() {
  const boom = () => {
    throw new DOMException('The operation is insecure.', 'SecurityError');
  };
  return { getItem: boom, setItem: boom };
}

afterEach(() => {
  window.localStorage.clear();
});

describe('viewerRoleStore', () => {
  it('저장한 역할을 다시 읽는다', () => {
    const st = memoryStorage();
    saveStoredRole('창업자', st);
    expect(loadStoredRole(st)).toBe('창업자');
    // 담는 것은 값 하나뿐이다.
    expect([...st.map.entries()]).toEqual([[VIEWER_ROLE_STORAGE_KEY, '창업자']]);
  });

  it('★ 둘러보기도 같은 열쇠 하나에 적고 다시 읽는다 (결정 0039 §7-4)', () => {
    const st = memoryStorage();
    saveStoredRole('중개사', st);
    saveStoredRole(BROWSE_ROLE, st);
    expect(BROWSE_ROLE).toBe('둘러보기');
    expect([...st.map.entries()]).toEqual([[VIEWER_ROLE_STORAGE_KEY, '둘러보기']]);
    expect(loadStoredRole(st)).toBe('둘러보기');
  });

  it('아무것도 안 적혀 있으면 null (= 아직 안 물어봤다)', () => {
    expect(loadStoredRole(memoryStorage())).toBeNull();
  });

  it('세 역할·둘러보기가 아닌 값은 null (안 물어본 것으로 본다)', () => {
    const st = memoryStorage();
    for (const bad of ['공통', 'investor', '', ' 투자자', '투자자 ', '둘러보기 ', 'browse']) {
      st.map.set(VIEWER_ROLE_STORAGE_KEY, bad);
      expect(loadStoredRole(st), JSON.stringify(bad)).toBeNull();
    }
  });

  it('화면 역할 — 세 역할은 그대로, 둘러보기·없음은 null', () => {
    expect(viewerRoleOf('투자자')).toBe('투자자');
    expect(viewerRoleOf('중개사')).toBe('중개사');
    expect(viewerRoleOf(BROWSE_ROLE)).toBeNull();
    expect(viewerRoleOf(null)).toBeNull();
  });

  it('★ 저장이 막힌 창 — 읽기·쓰기 예외를 삼키고 null 로 선다', () => {
    const st = blockedStorage();
    // 양성 대조: 이 가짜는 정말로 던진다(삼키는 쪽이 없으면 시험이 빨개진다).
    expect(() => st.getItem()).toThrow();
    expect(() => saveStoredRole('투자자', st)).not.toThrow();
    expect(() => saveStoredRole(BROWSE_ROLE, st)).not.toThrow();
    expect(loadStoredRole(st)).toBeNull();
  });

  it('저장소가 아예 없으면(null) 아무 일도 안 한다', () => {
    expect(() => saveStoredRole('투자자', null)).not.toThrow();
    expect(loadStoredRole(null)).toBeNull();
  });

  it('인자를 안 주면 브라우저 저장소를 쓴다', () => {
    saveStoredRole('투자자');
    expect(window.localStorage.getItem(VIEWER_ROLE_STORAGE_KEY)).toBe('투자자');
    expect(loadStoredRole()).toBe('투자자');
    saveStoredRole(BROWSE_ROLE);
    expect(window.localStorage.getItem(VIEWER_ROLE_STORAGE_KEY)).toBe('둘러보기');
  });

  it('window.localStorage 에 손대는 것만으로 예외가 나는 창에서도 죽지 않는다', () => {
    // 사이트 자료를 막은 창은 저장소 **접근 자체**가 SecurityError 를 던진다(읽기·쓰기 전에).
    const spy = vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('막힌 창', 'SecurityError');
    });
    try {
      expect(() => saveStoredRole('투자자')).not.toThrow();
      expect(() => saveStoredRole(BROWSE_ROLE)).not.toThrow();
      expect(loadStoredRole()).toBeNull();
      expect(spy).toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });
});
