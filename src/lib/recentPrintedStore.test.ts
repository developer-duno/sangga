import { afterEach, describe, expect, it, vi } from 'vitest';
import type { BuildingHit } from '../types';
import {
  RECENT_PRINTED_MAX,
  RECENT_PRINTED_STORAGE_KEY,
  clearRecentPrinted,
  loadRecentPrinted,
  recordPrinted,
} from './recentPrintedStore';

/**
 * 중개사 「최근 뽑은 건물」 저장(결정 0036 결정 18 ⑥ · 「이 기기 저장」 ①②⑤).
 *
 * 지키는 것: ① 저장이 막힌 창에서도 죽지 않는다(예외를 삼킨다) ② 최근 10개 · 같은 건물은 맨 앞으로
 * ③ 깨진 값은 빈 목록 · 이상한 줄은 그 줄만 빠진다 ④ 지우기 = 전체 ⑤ `total_cnt` 는 안 담는다.
 */

function memoryStorage() {
  const map = new Map<string, string>();
  return {
    map,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
  };
}

function blockedStorage() {
  const boom = () => {
    throw new DOMException('The operation is insecure.', 'SecurityError');
  };
  return { getItem: boom, setItem: boom, removeItem: boom };
}

function hit(n: number, over: Partial<BuildingHit> = {}): BuildingHit {
  return {
    bld_id: `1168010100100010000_${n}`,
    pnu: '1168010100100010000',
    bld_nm: `빌딩${n}`,
    road_addr: `서울 강남구 테헤란로 ${n}`,
    bld_cnt_in_pnu: 1,
    floor_cnt: 3,
    min_floor: 1,
    max_floor: 3,
    has_roof: false,
    total_cnt: 42,
    ...over,
  };
}

afterEach(() => window.localStorage.clear());

describe('recentPrintedStore', () => {
  it('적은 건물을 다시 읽는다 · total_cnt 는 안 담는다 · 선택 칸은 그대로', () => {
    const st = memoryStorage();
    const list = recordPrinted(hit(1, { is_jiphap: null, approve_date: '2003-05-14', parking_cnt: 0 }), st);
    expect(list.map((r) => r.bld_id)).toEqual([hit(1).bld_id]);
    expect('total_cnt' in list[0]).toBe(false);
    // 양성 대조: 담는 것에는 칸이 실제로 있다(위 false 가 '아무것도 안 담음'이 아니다).
    expect(list[0].bld_nm).toBe('빌딩1');
    expect(list[0].is_jiphap).toBeNull();
    expect(list[0].parking_cnt).toBe(0);
    expect([...st.map.keys()]).toEqual([RECENT_PRINTED_STORAGE_KEY]);
  });

  it('최근 것이 앞 · 같은 건물을 다시 뽑으면 맨 앞으로 옮기고 중복 0', () => {
    const st = memoryStorage();
    recordPrinted(hit(1), st);
    recordPrinted(hit(2), st);
    recordPrinted(hit(3), st);
    const list = recordPrinted(hit(1), st);
    expect(list.map((r) => r.bld_nm)).toEqual(['빌딩1', '빌딩3', '빌딩2']);
  });

  it(`${RECENT_PRINTED_MAX}개 상한 — 넘으면 가장 오래된 것이 빠진다`, () => {
    const st = memoryStorage();
    for (let i = 1; i <= RECENT_PRINTED_MAX; i++) recordPrinted(hit(i), st);
    expect(loadRecentPrinted(st)).toHaveLength(RECENT_PRINTED_MAX);
    const list = recordPrinted(hit(99), st);
    expect(list).toHaveLength(RECENT_PRINTED_MAX);
    expect(list[0].bld_nm).toBe('빌딩99');
    expect(list.map((r) => r.bld_nm)).not.toContain('빌딩1'); // 가장 오래된 것
    expect(list.map((r) => r.bld_nm)).toContain('빌딩2'); // 양성 대조: 그다음 것은 남는다
    expect(RECENT_PRINTED_MAX).toBe(10);
  });

  it('지우기는 목록 전체를 저장소에서도 지운다', () => {
    const st = memoryStorage();
    recordPrinted(hit(1), st);
    recordPrinted(hit(2), st);
    expect(st.map.size).toBe(1); // 양성 대조: 지우기 전엔 있다
    expect(clearRecentPrinted(st)).toEqual([]);
    expect(st.map.size).toBe(0);
    expect(loadRecentPrinted(st)).toEqual([]);
  });

  it('깨진 JSON · 배열이 아닌 값 → 빈 목록', () => {
    const st = memoryStorage();
    for (const bad of ['{', 'null', '"x"', '{"a":1}', '42']) {
      st.map.set(RECENT_PRINTED_STORAGE_KEY, bad);
      expect(loadRecentPrinted(st), bad).toEqual([]);
    }
  });

  it('★ 한 줄만 이상하면 그 줄만 빠지고 나머지는 산다 (통째로 버리지 않는다)', () => {
    const st = memoryStorage();
    const good1 = { ...hit(1) } as Record<string, unknown>;
    delete good1.total_cnt;
    const good2 = { ...hit(2) } as Record<string, unknown>;
    delete good2.total_cnt;
    const rows = [
      good1,
      // ⓘ 아래 셋의 bld_id 는 꼴이 맞다 — 각 줄이 **제 결함 하나로만** 빠지는지 본다.
      { ...good1, bld_id: '1168010100100010000_901', pnu: '11680' }, // pnu 가 19자리가 아니다
      { ...good1, bld_id: '1168010100100010000_902', floor_cnt: '3' }, // 숫자가 글자
      { ...good1, bld_id: '1168010100100010000_903', is_jiphap: 'Y' }, // 선택 칸이 있는데 모양이 틀림
      null,
      '빌딩',
      good1, // 같은 건물 두 번 — 첫 줄만
      good2,
    ];
    st.map.set(RECENT_PRINTED_STORAGE_KEY, JSON.stringify(rows));
    expect(loadRecentPrinted(st).map((r) => r.bld_nm)).toEqual(['빌딩1', '빌딩2']);
  });

  it('물결 2-1 세 칸(대장 호수·승강기) — 옛 줄(칸 없음)·새 줄은 산다 · 모양이 틀린 줄만 빠진다', () => {
    const st = memoryStorage();
    const old = { ...hit(1) } as Record<string, unknown>;
    delete old.total_cnt; // 새 칸이 아예 없는 옛 저장분
    const fresh = {
      ...old,
      bld_id: '1168010100100010000_2',
      bld_nm: '새줄',
      ho_cnt: 48,
      elevator_ride: 2,
      elevator_emgen: 1,
      bld_main_use: '판매시설',
    };
    const nulls = {
      ...old,
      bld_id: '1168010100100010000_3',
      bld_nm: '빈값',
      ho_cnt: null,
      elevator_ride: null,
      elevator_emgen: 0,
      bld_main_use: null,
    };
    const rows = [
      old,
      fresh,
      nulls,
      { ...fresh, bld_id: '1168010100100010000_901', bld_nm: '호수글자', ho_cnt: '48' },
      { ...fresh, bld_id: '1168010100100010000_902', bld_nm: '승용글자', elevator_ride: '2' },
      { ...fresh, bld_id: '1168010100100010000_903', bld_nm: '비상참', elevator_emgen: true },
      { ...fresh, bld_id: '1168010100100010000_904', bld_nm: '용도숫자', bld_main_use: 2 },
    ];
    st.map.set(RECENT_PRINTED_STORAGE_KEY, JSON.stringify(rows));
    const list = loadRecentPrinted(st);
    expect(list.map((r) => r.bld_nm)).toEqual(['빌딩1', '새줄', '빈값']);
    expect('ho_cnt' in list[0]).toBe(false); // 옛 줄에 칸을 지어 넣지 않는다
    expect(list[1]).toMatchObject({ ho_cnt: 48, elevator_ride: 2, elevator_emgen: 1, bld_main_use: '판매시설' });
    expect(list[2]).toMatchObject({ ho_cnt: null, elevator_ride: null, elevator_emgen: 0, bld_main_use: null });
  });

  it('★ bld_id 는 `<pnu>_<숫자>` 꼴이고 앞 19자리가 그 줄의 pnu 와 같아야 한다 (구·건물이 갈린 줄은 빠진다)', () => {
    const st = memoryStorage();
    const base = { ...hit(1) } as Record<string, unknown>;
    delete base.total_cnt;
    const real = { ...base, bld_id: '1168010600109420015_10241100257870', pnu: '1168010600109420015', bld_nm: '진짜' };
    const rows = [
      real, // 양성 대조: 실제 꼴은 산다
      { ...real, bld_id: '3017010100100010000_5', bld_nm: '갈림' }, // 앞 19자리 ≠ pnu
      { ...real, bld_id: '1168010600109420015', bld_nm: '밑줄없음' },
      { ...real, bld_id: '1168010600109420015_', bld_nm: '꼬리없음' },
      { ...real, bld_id: '1168010600109420015_12a', bld_nm: '글자꼬리' },
      { ...real, bld_id: '1168010600109420015_' + '1'.repeat(33), bld_nm: '너무긴꼬리' },
      { ...real, bld_id: 'x1168010600109420015_1', bld_nm: '앞에글자' },
    ];
    st.map.set(RECENT_PRINTED_STORAGE_KEY, JSON.stringify(rows));
    expect(loadRecentPrinted(st).map((r) => r.bld_nm)).toEqual(['진짜']);
  });

  it('선택 칸(좌표·소유 구조)이 아예 없는 줄도 받는다 — undefined 는 undefined 그대로', () => {
    const st = memoryStorage();
    const list = recordPrinted(hit(1), st);
    expect(list).toHaveLength(1);
    expect(list[0].lat).toBeUndefined();
    expect(list[0].is_jiphap).toBeUndefined();
  });

  it('★ 저장이 막힌 창 — 예외를 삼키고 빈 목록으로 선다', () => {
    const st = blockedStorage();
    expect(() => st.getItem()).toThrow(); // 양성 대조: 이 가짜는 정말로 던진다
    expect(() => recordPrinted(hit(1), st)).not.toThrow();
    expect(recordPrinted(hit(1), st)).toEqual([]);
    expect(clearRecentPrinted(st)).toEqual([]);
    expect(loadRecentPrinted(st)).toEqual([]);
  });

  it('읽기는 되는데 쓰기만 막히면 — 돌려주는 목록은 실제로 적힌 것(빈 목록)', () => {
    const st = memoryStorage();
    const ro = {
      ...st,
      setItem: () => {
        throw new DOMException('quota', 'QuotaExceededError');
      },
    };
    expect(recordPrinted(hit(1), ro)).toEqual([]);
    // 양성 대조: 쓰기가 되는 저장소면 같은 호출이 한 줄을 돌려준다.
    expect(recordPrinted(hit(1), st)).toHaveLength(1);
  });

  it('저장소가 아예 없으면(null) 아무 일도 안 한다', () => {
    expect(recordPrinted(hit(1), null)).toEqual([]);
    expect(clearRecentPrinted(null)).toEqual([]);
    expect(loadRecentPrinted(null)).toEqual([]);
  });

  it('인자를 안 주면 브라우저 저장소를 쓴다 · 저장소 접근 자체가 던져도 죽지 않는다', () => {
    recordPrinted(hit(1));
    expect(window.localStorage.getItem(RECENT_PRINTED_STORAGE_KEY)).not.toBeNull();
    expect(loadRecentPrinted()).toHaveLength(1);
    clearRecentPrinted();
    expect(window.localStorage.getItem(RECENT_PRINTED_STORAGE_KEY)).toBeNull();

    const spy = vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => {
      throw new DOMException('막힌 창', 'SecurityError');
    });
    try {
      expect(() => recordPrinted(hit(1))).not.toThrow();
      expect(loadRecentPrinted()).toEqual([]);
      expect(clearRecentPrinted()).toEqual([]);
      expect(spy).toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });
});
