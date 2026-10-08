import { describe, it, expect } from 'vitest';
import { FOUNDER_CHIPS, FOUNDER_CHIP_ALL, CHIP_MATCH, chipMatch } from './founderChips';

/**
 * 창업자 업종 칩의 짝짓기 표(👤 결정 0036 결정 1·18 ⑤⑨ · ⑫~⑭).
 *
 * 이 표 하나를 업종 분포 카드(소진공 분류)와 개업·폐업 카드(서울시 100업종)가 함께 본다 —
 * 짝이 어긋나면 에러 없이 엉뚱한 줄이 굵어지므로 값을 글자 그대로 못 박는다.
 */
describe('founderChips — 칩 여섯 개', () => {
  it('차례는 카페·한식·미용·학원·편의점·전체 이고 처음 값은 전체다', () => {
    expect([...FOUNDER_CHIPS]).toEqual(['카페', '한식', '미용', '학원', '편의점', '전체']);
    expect(FOUNDER_CHIP_ALL).toBe('전체');
  });

  it('전체는 짝이 없다(효과 없음) — 나머지 다섯은 짝이 있다(양성 대조)', () => {
    expect(chipMatch('전체')).toBeNull();
    for (const c of FOUNDER_CHIPS.filter((x) => x !== '전체')) {
      expect(chipMatch(c)).not.toBeNull();
    }
  });
});

describe('founderChips — 짝짓기 표(실측 10-09 · 👤 ⑫~⑭)', () => {
  it('칩마다 소진공 대분류 · 강조할 중분류 · 서울 업종 코드', () => {
    const pick = (k: keyof typeof CHIP_MATCH) => {
      const m = CHIP_MATCH[k];
      return { catL: m.catL, catM: [...m.catM], seoul: [...m.seoul] };
    };
    expect(pick('카페')).toEqual({ catL: 'I2', catM: ['I212'], seoul: ['CS100010'] });
    expect(pick('한식')).toEqual({ catL: 'I2', catM: ['I201'], seoul: ['CS100001'] });
    // ⑫ 미용 = 미용실·네일·피부 셋
    expect(pick('미용')).toEqual({
      catL: 'S2',
      catM: ['S207'],
      seoul: ['CS200028', 'CS200029', 'CS200030'],
    });
    // ⑬ 학원 = 두 줄(입시·교과 + 기타 교육)
    expect(pick('학원')).toEqual({
      catL: 'P1',
      catM: ['P105', 'P106'],
      seoul: ['CS200001', 'CS200002', 'CS200003', 'CS200004', 'CS200005'],
    });
    expect(pick('편의점')).toEqual({ catL: 'G2', catM: ['G204'], seoul: ['CS300002'] });
  });

  it('중분류는 그 대분류 아래 코드이고 서울 코드는 CS 여섯 자리다', () => {
    for (const m of Object.values(CHIP_MATCH)) {
      // 대분류 'I2' 의 중분류는 'I2xx' — 짝이 다른 대분류로 새면 엉뚱한 줄이 굵어진다.
      for (const cd of m.catM) expect(cd.startsWith(m.catL)).toBe(true);
      for (const cd of m.seoul) expect(cd).toMatch(/^CS\d{6}$/);
    }
    // 양성 대조 — 위 검사가 실제로 잡는 꼴인지.
    expect('S207'.startsWith('I2')).toBe(false);
    expect('CS10001').not.toMatch(/^CS\d{6}$/);
  });

  it('⑭ 편의점에만 설명 한 줄 — 그 문구 그대로 · 다른 칩은 없다(양성 대조)', () => {
    expect(CHIP_MATCH['편의점'].note).toBe('종합 소매에는 편의점과 슈퍼마켓이 함께 들어 있습니다');
    for (const k of ['카페', '한식', '미용', '학원'] as const) {
      expect(CHIP_MATCH[k].note).toBeUndefined();
    }
  });
});

describe('founderChips — 서울 업종 이름 (F5)', () => {
  it('서울 코드마다 이름이 있다(DB 실측 이름)', () => {
    expect(CHIP_MATCH['학원'].seoulNm).toEqual({
      CS200001: '일반교습학원',
      CS200002: '외국어학원',
      CS200003: '예술학원',
      CS200004: '컴퓨터학원',
      CS200005: '스포츠 강습',
    });
    expect(CHIP_MATCH['미용'].seoulNm).toEqual({ CS200028: '미용실', CS200029: '네일숍', CS200030: '피부관리실' });
    for (const m of Object.values(CHIP_MATCH)) {
      expect(Object.keys(m.seoulNm).sort()).toEqual([...m.seoul].sort());
    }
  });

  it('빠진 것 한 줄이 생길 수 있는 칩(서울 코드 둘 이상)의 이름은 모두 받침으로 끝난다 — 조사 "은" 고정', () => {
    const hasBatchim = (w: string) => {
      const c = w.charCodeAt(w.length - 1) - 0xac00;
      return c >= 0 && c <= 11171 && c % 28 !== 0;
    };
    for (const m of Object.values(CHIP_MATCH)) {
      if (m.seoul.length < 2) continue;
      for (const nm of Object.values(m.seoulNm)) expect(hasBatchim(nm)).toBe(true);
    }
    // 양성 대조 — 받침 없는 이름은 걸린다('커피-음료' — 코드가 하나라 그 줄이 생기지 않는다).
    expect(hasBatchim('커피-음료')).toBe(false);
  });
});
