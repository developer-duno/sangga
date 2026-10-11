import { describe, expect, it } from 'vitest';
import {
  BROKER_OFFICE_MAX,
  BROKER_OFFICE_STORAGE_KEY,
  EMPTY_BROKER_OFFICE,
  clearBrokerOffice,
  hasBrokerOffice,
  loadBrokerOffice,
  saveBrokerOffice,
} from './brokerOfficeStore';

/**
 * 중개사 사무소 칸 저장(결정 0036 결정 3 · 「이 기기 저장」 ①②).
 * 지키는 것: ① 막힌 창은 읽기·쓰기·지우기 예외를 삼킨다 ② 칸마다 모양 검사(틀린 칸만 버림)
 * ③ 상한으로 자른다 ④ 지우기 = 열쇠째.
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

const FULL = { name: '역삼공인중개사', rep: '홍길동', regNo: '11680-2020-00001', phone: '02-0000-0000', memo: '평일\n9시~6시' };

describe('brokerOfficeStore', () => {
  it('적은 것을 다시 읽는다 · 열쇠는 sangga.brokerOffice 하나', () => {
    const st = memoryStorage();
    saveBrokerOffice(FULL, st);
    expect(loadBrokerOffice(st)).toEqual(FULL);
    expect([...st.map.keys()]).toEqual([BROKER_OFFICE_STORAGE_KEY]);
    expect(BROKER_OFFICE_STORAGE_KEY).toBe('sangga.brokerOffice');
  });

  it('칸마다 모양을 본다 — 글자가 아니거나 상한을 넘는 칸만 버리고 나머지는 산다', () => {
    const st = memoryStorage();
    st.map.set(
      BROKER_OFFICE_STORAGE_KEY,
      JSON.stringify({ name: '역삼', rep: 7, regNo: 'x'.repeat(BROKER_OFFICE_MAX.regNo + 1), phone: null, memo: '메모' }),
    );
    expect(loadBrokerOffice(st)).toEqual({ ...EMPTY_BROKER_OFFICE, name: '역삼', memo: '메모' });
  });

  it('깨진 글·배열·없는 열쇠는 빈 칸들', () => {
    const st = memoryStorage();
    expect(loadBrokerOffice(st)).toEqual(EMPTY_BROKER_OFFICE);
    for (const bad of ['{', '[]', '"글"', 'null']) {
      st.map.set(BROKER_OFFICE_STORAGE_KEY, bad);
      expect(loadBrokerOffice(st), bad).toEqual(EMPTY_BROKER_OFFICE);
    }
  });

  it('상한을 넘겨 적으면 잘라서 적는다(이름류 60 · 메모 200)', () => {
    const st = memoryStorage();
    saveBrokerOffice({ ...FULL, name: '가'.repeat(80), memo: '나'.repeat(250) }, st);
    const got = loadBrokerOffice(st);
    expect(got.name).toHaveLength(60);
    expect(got.memo).toHaveLength(200);
    expect(BROKER_OFFICE_MAX).toEqual({ name: 60, rep: 60, regNo: 60, phone: 60, memo: 200 });
  });

  it('칸이 전부 비면 열쇠를 지운다 · 지우기는 열쇠째', () => {
    const st = memoryStorage();
    saveBrokerOffice(FULL, st);
    saveBrokerOffice({ ...EMPTY_BROKER_OFFICE, rep: '  ' }, st);
    expect(st.map.size).toBe(0);
    saveBrokerOffice(FULL, st);
    expect(clearBrokerOffice(st)).toEqual(EMPTY_BROKER_OFFICE);
    expect(st.map.size).toBe(0);
  });

  it('★ 저장이 막힌 창 — 읽기·쓰기·지우기 예외를 삼키고 빈 칸들로 선다', () => {
    const st = blockedStorage();
    expect(() => saveBrokerOffice(FULL, st)).not.toThrow();
    expect(loadBrokerOffice(st)).toEqual(EMPTY_BROKER_OFFICE);
    expect(clearBrokerOffice(st)).toEqual(EMPTY_BROKER_OFFICE);
  });

  it('hasBrokerOffice — 공백만이면 빈 칸 · 한 칸이라도 채우면 참', () => {
    expect(hasBrokerOffice(null)).toBe(false);
    expect(hasBrokerOffice({ ...EMPTY_BROKER_OFFICE, memo: ' \n ' })).toBe(false);
    expect(hasBrokerOffice({ ...EMPTY_BROKER_OFFICE, phone: '02' })).toBe(true);
  });
});
