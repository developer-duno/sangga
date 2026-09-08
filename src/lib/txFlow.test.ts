import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  barWidthPct,
  flowSummary,
  hasEnoughSample,
  isSigunguTxYearlyList,
  maxMedian,
  missingRatePct,
  partialYearLabel,
} from './txFlow';
import type { SigunguTxYearly } from '../types';

/**
 * 『동네 매매 단가 흐름』 카드의 **순수 계산**(결정 0027).
 *
 * 여기서 특히 지키는 것
 * ---------------------
 *  ① **모양을 본다** — 이 카드는 입구에 서므로, 뜻밖의 답이 렌더로 흘러 들어가 터지면
 *     검색창·지역 고르개까지 함께 사라진다.
 *  ② **해의 일부를 정직하게 적는다** — 첫 해와 올해는 자료가 몇 달치뿐인데 그냥 그리면
 *     "그 해에는 이만큼 팔렸다"로 읽힌다.
 *  ③ **표본이 적으면 값을 안 적는다** — 절대 규칙 3 의 미표시 원칙.
 *  ④ **숫자·금칙어를 화면 코드에 박지 않는다** — 자료 범위는 서버가 주는 값이다.
 */

function row(over: Partial<SigunguTxYearly> = {}): SigunguTxYearly {
  return {
    yr: '2015',
    n: 1550,
    n_all: 1600,
    median_unit_price: 21_171_384,
    p25_unit_price: 12_000_000,
    p75_unit_price: 33_000_000,
    floor_missing: 100,
    ym_cnt: 12,
    first_ym: '201501',
    last_ym: '201512',
    sigungu_nm: '강남구',
    ...over,
  };
}

describe('isSigunguTxYearlyList — 서버 답의 모양', () => {
  it('정상 세 줄은 통과한다', () => {
    expect(isSigunguTxYearlyList([row(), row({ yr: '2016' }), row({ yr: '2017' })])).toBe(true);
  });

  it('빈 배열도 모양으로는 정상이다 (있고 없고는 컴포넌트가 가른다)', () => {
    expect(isSigunguTxYearlyList([])).toBe(true);
  });

  it('연도가 숫자로 오면 거른다 (문자열 네 글자가 약속이다)', () => {
    expect(isSigunguTxYearlyList([{ ...row(), yr: 2015 }])).toBe(false);
  });

  it('건수가 문자열로 오면 거른다 (그대로 더하면 글자가 이어붙는다)', () => {
    expect(isSigunguTxYearlyList([{ ...row(), n: '1550' }])).toBe(false);
    expect(isSigunguTxYearlyList([{ ...row(), n_all: '1600' }])).toBe(false);
  });

  it('중앙값이 문자열로 오면 거른다 (막대 폭 계산이 조용히 0 이 된다)', () => {
    expect(isSigunguTxYearlyList([{ ...row(), median_unit_price: '21171384' }])).toBe(false);
  });

  it('중앙값·사분위·구 이름은 null 이어도 된다 (표본이 없는 해가 그렇다)', () => {
    expect(
      isSigunguTxYearlyList([
        row({ median_unit_price: null, p25_unit_price: null, p75_unit_price: null, sigungu_nm: null }),
      ]),
    ).toBe(true);
  });

  it('칸이 빠지면 거른다 — 층 미상이 없으면 비율을 못 낸다', () => {
    const { floor_missing: _drop, ...missing } = row();
    expect(isSigunguTxYearlyList([missing])).toBe(false);
  });

  it('배열도 객체도 아닌 답은 거른다', () => {
    expect(isSigunguTxYearlyList(null)).toBe(false);
    expect(isSigunguTxYearlyList({ yr: '2015' })).toBe(false);
    expect(isSigunguTxYearlyList(['2015'])).toBe(false);
  });
});

describe('flowSummary — 접혀 있어도 보이는 한 줄', () => {
  it('첫 달 ~ 끝 달 · 전체 건수 · 무엇을 재는지', () => {
    const rows = [
      row({ yr: '2006', first_ym: '200609', last_ym: '200612', n_all: 447, ym_cnt: 4 }),
      row({ yr: '2026', first_ym: '202601', last_ym: '202608', n_all: 415, ym_cnt: 8 }),
    ];
    expect(flowSummary(rows)).toBe(
      '2006년 9월 ~ 2026년 8월 · 집합상가 매매 862건 · 해마다 ㎡당 중앙값',
    );
  });

  it('자료가 짧으면 짧은 대로 적는다 (범위를 늘려 말하지 않는다)', () => {
    const rows = [row({ yr: '2026', first_ym: '202409', last_ym: '202608', n_all: 1200 })];
    expect(flowSummary(rows)).toContain('2024년 9월 ~ 2026년 8월');
    expect(flowSummary(rows)).toContain('1,200건');
  });

  it('첫 달·끝 달이 없으면 범위만 빠지고 나머지는 그대로 선다', () => {
    const rows = [row({ first_ym: null, last_ym: null, n_all: 10 })];
    expect(flowSummary(rows)).toBe('집합상가 매매 10건 · 해마다 ㎡당 중앙값');
  });

  it('달 표기가 깨져 있으면 지어내지 않는다 — 그 부분만 뺀다', () => {
    // `formatMonthKo` 는 읽을 수 없으면 null 을 준다('—'나 원본을 되돌려 주지 않는다).
    const rows = [row({ first_ym: '2006-09', last_ym: '202612' })];
    expect(flowSummary(rows)).not.toContain('2006');
    expect(flowSummary(rows)).toContain('집합상가 매매');
  });
});

describe('partialYearLabel — 해의 일부만 있는 해', () => {
  it('열두 달이 다 있으면 붙이지 않는다', () => {
    expect(partialYearLabel(row({ ym_cnt: 12 }))).toBeNull();
  });

  it('첫 해는 시작한 달부터 적는다', () => {
    expect(partialYearLabel(row({ first_ym: '200609', last_ym: '200612', ym_cnt: 4 }))).toBe(
      '9~12월분',
    );
  });

  it('올해는 지금까지의 달만 적는다', () => {
    expect(partialYearLabel(row({ first_ym: '202601', last_ym: '202608', ym_cnt: 8 }))).toBe(
      '1~8월분',
    );
  });

  it('한 달뿐이면 물결표를 안 쓴다', () => {
    expect(partialYearLabel(row({ first_ym: '200611', last_ym: '200611', ym_cnt: 1 }))).toBe(
      '11월분',
    );
  });

  it('달을 모르면 범위를 지어내지 않는다', () => {
    expect(partialYearLabel(row({ first_ym: null, last_ym: '200612', ym_cnt: 3 }))).toBeNull();
  });

  it('양 끝의 폭과 달수가 맞으면 두 달만 적는다 (빈틈이 없는 해)', () => {
    expect(partialYearLabel(row({ first_ym: '202603', last_ym: '202607', ym_cnt: 5 }))).toBe(
      '3~7월분',
    );
  });

  it('★ 가운데가 빈 해는 이어 붙이지 않는다 — 온전한 해와 글자가 같아지면 안 된다', () => {
    // 거래가 아예 없던 달은 서버가 주지 않는다. 1월과 12월이 있어도 열 달치일 수 있다.
    expect(partialYearLabel(row({ first_ym: '200601', last_ym: '200612', ym_cnt: 10 }))).toBe(
      '1~12월 중 10개월분',
    );
  });

  it('한 달로 적히는 것은 정말 한 달일 때뿐이다', () => {
    expect(partialYearLabel(row({ first_ym: '200611', last_ym: '200611', ym_cnt: 2 }))).toBe(
      '11~11월 중 2개월분',
    );
  });
});

describe('missingRatePct · hasEnoughSample — 얼마나 믿을 값인가', () => {
  it('층 미상 비율은 그 해 거래 전부를 분모로 센다', () => {
    expect(missingRatePct(row({ n_all: 447, floor_missing: 92 }))).toBe(21);
  });

  it('분모가 0 이면 비율이 없다 — 0% 라 적으면 "층이 다 있다"는 정반대 뜻이 된다', () => {
    expect(missingRatePct(row({ n_all: 0, floor_missing: 0 }))).toBeNull();
  });

  it('표본이 임계값 이상이면 값을 적고, 미만이면 안 적는다', () => {
    expect(hasEnoughSample(row({ n: 5 }))).toBe(true);
    expect(hasEnoughSample(row({ n: 4 }))).toBe(false);
  });

  it('★ 모자란지는 **단가가 있는 거래**로 가른다 — 그 해 거래 전부가 아니다', () => {
    // 지금은 둘이 같지만(면적이 빈 거래가 아직 없다) 갈리는 날이 오면, 40건을 놓고
    // "표본 부족"이라 적는 줄이 된다 — 그때 무엇으로 갈랐는지가 화면에 적혀야 한다.
    expect(hasEnoughSample(row({ n_all: 40, n: 3 }))).toBe(false);
    expect(hasEnoughSample(row({ n_all: 40, n: 5 }))).toBe(true);
  });
});

describe('maxMedian · barWidthPct — 막대 폭', () => {
  it('가장 큰 중앙값이 100% 가 된다', () => {
    const rows = [row({ median_unit_price: 5_000_000 }), row({ median_unit_price: 10_000_000 })];
    expect(maxMedian(rows)).toBe(10_000_000);
    expect(barWidthPct(rows[0], 10_000_000)).toBe(50);
    expect(barWidthPct(rows[1], 10_000_000)).toBe(100);
  });

  it('★ 표본이 모자란 해는 기준에서 뺀다 — 안 적을 값이 눈금을 정하면 안 된다', () => {
    const rows = [
      row({ n: 3, median_unit_price: 90_000_000 }),
      row({ n: 100, median_unit_price: 10_000_000 }),
    ];
    expect(maxMedian(rows)).toBe(10_000_000);
    // 그 해의 막대 자체도 안 그린다(값을 감추면서 막대만 남기면 값을 말한 것과 같다).
    expect(barWidthPct(rows[0], 10_000_000)).toBe(0);
  });

  it('잴 것이 없으면 0 이다 (0 으로 나누지 않는다)', () => {
    expect(maxMedian([row({ n: 1 })])).toBe(0);
    expect(barWidthPct(row(), 0)).toBe(0);
    expect(barWidthPct(row({ median_unit_price: null }), 10_000_000)).toBe(0);
  });
});

/**
 * ★ 이 파일에서 가장 중요한 시험.
 *
 * 이 카드의 자료 범위는 **서버가 주는 값**이다. 사람이 화면에 범위를 글자로 적어 넣으면
 * 그 순간에는 맞지만, 자료를 더 받은 날 **화면만** 옛 범위를 말한다 — 에러가 아니라서
 * 아무도 모른다(성적표 카드에서 쓰는 것과 같은 가드다).
 *
 * ⚠️ 주석도 함께 훑는다 — 주석에 박힌 연도는 다음 사람이 그대로 화면으로 옮긴다.
 * ⚠️ `?raw` import 를 쓰지 않는다 — 이 레포에서 vitest 의 `?raw` 가 빈 문자열을 돌려준
 *    적이 있어(가짜 초록), 파일을 `node:fs` 로 직접 읽는다.
 */
describe('★ 화면 코드에 연도·금칙어가 없다', () => {
  // ⚠️ 카드 컴포넌트도 함께 잰다 — 화면 문구가 실제로 박히는 자리는 그쪽이다.
  const files = ['./txFlow.ts', '../components/TxFlowSection.tsx'];
  const BANNED = ['적정가격', '적정가', '평가액', '감정가', '가치평가'];

  function sourceOf(rel: string): string {
    return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');
  }

  it.each(files)('%s 에 절대 규칙 2 의 금칙어가 없다', (rel) => {
    const text = sourceOf(rel);
    for (const banned of BANNED) {
      expect(text.includes(banned), banned).toBe(false);
    }
  });

  it.each(files)('%s 에 연도 리터럴이 없다 (자료 범위는 서버가 준다)', (rel) => {
    const found = sourceOf(rel).match(/20\d\d년/g);
    expect(found, `옮겨 적은 연도: ${found?.join(', ')}`).toBeNull();
  });

  it('가드가 늘 참인 시험이 아니다 — 있으면 실제로 잡는다', () => {
    // 이 문자열이 시험 대상 파일 안에 있었다면 위 두 시험이 빨간불이 됐어야 한다.
    const mutated = "const x = '2017년부터 감정가를 적습니다';";
    expect(mutated.match(/20\d\d년/g)).not.toBeNull();
    expect(BANNED.some((b) => mutated.includes(b))).toBe(true);
  });
});
