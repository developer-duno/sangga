import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';
import {
  LAND_PRICE_BADGE,
  LAND_PRICE_NOTE,
  formatLandPriceAmount,
  landPriceText,
  parseLandPrice,
} from './landPrice';

describe('formatLandPriceAmount — ㎡당 금액', () => {
  // 👤 2026-10-11 — 10만원 미만 원 그대로 · 10만~1억 미만 만원 반올림 · 1억 이상 '1억 8,840만원'(만 자리 0 이면 '2억원').
  it.each([
    [0, '0원'], // 0 은 값이다
    [8_500, '8,500원'],
    [14_999, '14,999원'],
    [99_999, '99,999원'], // 10만원 미만 = 원 그대로
    [100_000, '10만원'], // 여기부터 만원
    [45_230_000, '4,523만원'],
    [45_235_000, '4,524만원'], // 만원 아래 반올림
    [99_994_999, '9,999만원'], // 반올림해도 1억 미만 — 만원 그대로
    [99_995_000, '1억원'], // 반올림하면 1억 — '10,000만원'이 되지 않게
    [100_000_000, '1억원'],
    [188_400_000, '1억 8,840만원'],
    [188_405_000, '1억 8,841만원'], // 억 위에서도 만원 아래 반올림
    [200_000_000, '2억원'], // 만 자리 0
    [1_234_567_890, '12억 3,457만원'],
  ])('%d → %s', (won, want) => {
    expect(formatLandPriceAmount(won)).toBe(want);
  });
});

describe('landPriceText — 한 줄', () => {
  it('★ 브리프의 글자 그대로', () => {
    expect(landPriceText({ land_price: 45_230_000, land_price_year: 2026 })).toBe(
      '개별공시지가 땅 1㎡당 4,523만원 · 2026년 공시 (이 건물이 선 땅 · 공시가격 — 시세가 아닙니다)',
    );
  });

  it('연도는 받은 값 그대로 — 화면이 연도를 지어내지 않는다', () => {
    expect(landPriceText({ land_price: 8_500, land_price_year: 2019 })).toBe(
      `개별공시지가 땅 1㎡당 8,500원 · 2019년 공시 ${LAND_PRICE_NOTE}`,
    );
  });

  it("배지 글자 — 기준시가는 '공식 고시', 이 줄은 '공식 공시'", () => {
    expect(LAND_PRICE_BADGE).toBe('A등급 · 공식 공시');
  });

  it('금지어가 없다(절대 규칙 2)', () => {
    const text = `${LAND_PRICE_BADGE} ${landPriceText({ land_price: 45_230_000, land_price_year: 2026 })}`;
    for (const w of ['적정가', '감정가', '평가액', '가치평가']) expect(text).not.toContain(w);
  });
});

describe('parseLandPrice — 모양 검증 (그릴 수 없으면 null = 줄 없음)', () => {
  it('한 줄이면 그 값', () => {
    expect(parseLandPrice([{ land_price: 45_230_000, land_price_year: 2026 }])).toEqual({
      land_price: 45_230_000,
      land_price_year: 2026,
    });
  });

  it('0원은 값이다(적재기가 원본 0 을 0 으로 담는다)', () => {
    expect(parseLandPrice([{ land_price: 0, land_price_year: 2025 }])).toEqual({
      land_price: 0,
      land_price_year: 2025,
    });
  });

  it.each([
    ['null', null],
    ['객체(배열 아님)', { land_price: 1, land_price_year: 2026 }],
    ['빈 배열(값 없는 필지)', []],
    ['두 줄(pnu 는 기본키 — 약속 위반)', [
      { land_price: 1, land_price_year: 2026 },
      { land_price: 2, land_price_year: 2026 },
    ]],
    ['줄이 null', [null]],
    ['값이 글자', [{ land_price: '45230000', land_price_year: 2026 }]],
    ['값이 소수', [{ land_price: 4.5, land_price_year: 2026 }]],
    ['값이 음수', [{ land_price: -1, land_price_year: 2026 }]],
    ['값이 NaN', [{ land_price: Number.NaN, land_price_year: 2026 }]],
    ['값이 null', [{ land_price: null, land_price_year: 2026 }]],
    ['연도가 null', [{ land_price: 1, land_price_year: null }]],
    ['연도가 글자', [{ land_price: 1, land_price_year: '2026' }]],
    ['연도가 소수', [{ land_price: 1, land_price_year: 2026.5 }]],
    ['연도가 0', [{ land_price: 1, land_price_year: 0 }]],
  ])('%s → null', (_label, data) => {
    expect(parseLandPrice(data)).toBeNull();
  });
});

describe('화면 코드에 연도 글자가 없다 — 연도는 서버 값 land_price_year 로만', () => {
  /** 원문에서 20XX 꼴 네 자리 연도를 찾는다. 가드 본체와 양성 대조가 같은 함수를 지난다.
   *  ⚠️ 못 보는 것: 19XX 꼴 · 쪼개 이은 꼴('20' + '26'). */
  function yearLiterals(src: string): string[] {
    return src.match(/(?<!\d)20\d{2}(?!\d)/g) ?? [];
  }

  it('landPrice.ts 원문', () => {
    // ⓘ 경로를 변수로 둔다 — 글자 그대로 `new URL('./…', import.meta.url)` 이면 vite 가 자산 주소로 바꿔 버린다.
    const rel = './landPrice.ts';
    const src = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');
    expect(yearLiterals(src)).toEqual([]);
  });

  it('양성 대조 — 연도를 박은 꼴(흔한 꼴 + 템플릿 안 꼴)을 잡는다', () => {
    expect(yearLiterals("const Y = '2026년 공시';")).toEqual(['2026']);
    expect(yearLiterals('`${a} · 2025년`')).toEqual(['2025']);
  });
});
