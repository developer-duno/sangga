import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { SCORECARD_URL } from './appConstants';
import {
  GATE_MDAPE_LIMIT,
  coverageNote,
  formatPercent,
  gateLine,
  isPriceGateList,
  isScorecard,
  loadScorecard,
  pickGate,
  resetScorecardCache,
  stageDistribution,
  stampDate,
} from './scorecard';
import type { PriceGateRow, Scorecard, ScorecardOpsMode } from '../types';

/**
 * 성적표 카드의 순수 계산.
 *
 * 여기서 특히 지키는 것
 * ---------------------
 *  ① **화면 코드에 통계 수치가 없다** — 로드맵 Wave 4 의 "숫자 복사 금지". 한 번 옮겨
 *     적으면 성적표를 다시 뽑는 날 화면만 옛 성적을 말한다(에러가 아니라 조용한 거짓말).
 *  ② **폴백 단계가 맨 앞** — 제일 정확한 단계를 먼저 보이면 사람은 그 성적을 서비스의
 *     성적으로 읽는데, 실제로 가장 자주 만나는 것은 맨 아래 폴백이다.
 *  ③ **왜 떨어졌는지 갈라 말한다** — "자료가 없어서"와 "구 평균만 못해서"는 다른 말이다.
 *  ④ **못 읽은 것을 0 으로 만들지 않는다** — 추정을 못 낸 자리의 오차는 0%가 아니라 없다.
 */

function ops(over: Partial<ScorecardOpsMode> = {}): ScorecardOpsMode {
  return {
    kind: '채택단계',
    axis_value: 'L2',
    axis_name: 'L2',
    n_verified: 100,
    n_estimated: 100,
    coverage: 1,
    mdape: 0.2,
    mape: 0.3,
    hit20: 0.5,
    ...over,
  };
}

function card(over: Partial<Scorecard> = {}): Scorecard {
  return {
    version: 'v1',
    generated_at: '2026-08-15T23:44:00+09:00',
    sources: { '통과구.csv': 'a'.repeat(64) },
    stages: [],
    ops_modes: [
      ops({ kind: '전체', axis_value: '전체', axis_name: '전체', n_verified: 1000, coverage: 0.9 }),
      ops({ axis_value: 'L2', axis_name: 'L2', n_verified: 300, mdape: 0.13 }),
      ops({ axis_value: 'L6', axis_name: 'L6', n_verified: 600, mdape: 0.4 }),
      ops({ axis_value: 'no_estimate', axis_name: 'no_estimate', n_verified: 100, mdape: null }),
    ],
    ...over,
  };
}

function gate(over: Partial<PriceGateRow> = {}): PriceGateRow {
  return {
    sigungu_code: '11680',
    sigungu_nm: '강남구',
    n_paired: 262,
    ladder_mdape: 0.28,
    base_mdape: 0.49,
    gate_pass: true,
    loaded_at: '2026-08-16T10:00:00+09:00',
    ...over,
  };
}

describe('formatPercent — 비율을 사람 말로', () => {
  it('소수 첫째 자리까지 적는다', () => {
    expect(formatPercent(0.29056)).toBe('29.1%');
  });

  it('자릿수를 줄여 적을 수 있다 (기준선처럼 딱 떨어지는 값)', () => {
    expect(formatPercent(GATE_MDAPE_LIMIT, 0)).toBe('30%');
  });

  it('값이 아니면 null 이다 — 0% 로 만들지 않는다', () => {
    expect(formatPercent(null)).toBeNull();
    expect(formatPercent(undefined)).toBeNull();
    expect(formatPercent(Number.NaN)).toBeNull();
  });
});

describe('gateLine — 이 구는 참고 시세를 받나', () => {
  it('통과한 구에는 오차와 표본 수를 함께 적는다 (절대 규칙 3)', () => {
    const line = gateLine(gate());
    expect(line).toContain('참고 시세 제공');
    expect(line).toContain('28.0%');
    expect(line).toContain('262건');
  });

  it('★ 오차는 기준선 안인데 구 평균에 진 구는 그 사실을 적는다 (결정 0013 §2 조건 ②)', () => {
    // 이 경우가 이 카드의 존재 이유다 — 자료가 없어서가 아니라 **이미 화면에 있는 값보다
    // 못해서** 안 내는 것이라, 그렇게 말하지 않으면 사람은 자료가 없는 줄 안다.
    const line = gateLine(gate({ ladder_mdape: 0.26, base_mdape: 0.176, gate_pass: false }));
    expect(line).toContain('구평균');
    expect(line).toContain('못 이깁니다');
    expect(line).toContain('17.6%');
    expect(line).not.toContain('기준선');
  });

  it('기준선을 넘긴 구에는 기준선을 넘었다고 적는다', () => {
    const line = gateLine(gate({ ladder_mdape: 0.335, base_mdape: 0.44, gate_pass: false }));
    expect(line).toContain('기준선');
    expect(line).toContain('33.5%');
    expect(line).not.toContain('못 이깁니다');
  });

  it('둘 다 못 넘긴 구에는 둘 다 적되 오차를 두 번 되풀이하지 않는다', () => {
    const line = gateLine(gate({ ladder_mdape: 0.453, base_mdape: 0.398, gate_pass: false }));
    expect(line).toContain('기준선');
    expect(line).toContain('보다도 큽니다');
    expect(line.match(/45\.3%/g)?.length).toBe(1);
  });

  it('근거 값을 못 읽으면 이유를 지어내지 않는다', () => {
    const line = gateLine(gate({ ladder_mdape: null, base_mdape: null, gate_pass: false }));
    expect(line).toBe('참고 시세를 제공하지 않습니다');
  });

  it('채점하지 않은 지역은 "없다"가 아니라 "아직 안 냈다"로 적는다', () => {
    expect(gateLine(null)).toContain('아직');
  });
});

describe('pickGate — 고른 구 줄 고르기', () => {
  it('코드가 같은 줄을 고른다', () => {
    const rows = [gate({ sigungu_code: '11110' }), gate({ sigungu_code: '11680' })];
    expect(pickGate(rows, '11680')?.sigungu_code).toBe('11680');
  });

  it('없거나 안 골랐으면 null 이다', () => {
    expect(pickGate([gate()], '30110')).toBeNull();
    expect(pickGate([gate()], null)).toBeNull();
  });
});

describe('stageDistribution — 화면에서 체감하는 분포', () => {
  it('★ 가장 자주 걸리는 자리(폴백)가 맨 앞에 온다 — 로드맵 Wave 4', () => {
    expect(stageDistribution(card()).map((s) => s.code)).toEqual([
      'L6',
      'L2',
      'no_estimate',
    ]);
  });

  it('순서를 코드에 못 박지 않았다 — 자료가 바뀌면 순서도 따라 바뀐다', () => {
    // 폴백이 맨 앞인 것은 "지금 그것이 가장 흔해서"이지 목록에 그렇게 적어 뒀기
    // 때문이 아니다. L2 가 더 흔한 자료를 주면 L2 가 먼저 와야 한다.
    const flipped = card({
      ops_modes: [
        ops({ kind: '전체', axis_value: '전체', n_verified: 1000 }),
        ops({ axis_value: 'L2', n_verified: 700 }),
        ops({ axis_value: 'L6', n_verified: 300 }),
      ],
    });
    expect(stageDistribution(flipped).map((s) => s.code)).toEqual(['L2', 'L6']);
  });

  it('비중은 전체 검증 거래를 나눠 낸다', () => {
    const l6 = stageDistribution(card())[0];
    expect(l6.share).toBeCloseTo(0.6, 6);
    expect(l6.n).toBe(600);
  });

  it('단계 코드에 사람 말 설명이 붙는다 (성적표 §1 의 단계 정의)', () => {
    const byCode = Object.fromEntries(stageDistribution(card()).map((s) => [s.code, s.note]));
    expect(byCode.L2).toContain('같은 건물');
    expect(byCode.no_estimate).toContain('못 냄');
  });

  it('모르는 코드는 설명을 지어내지 않는다', () => {
    const odd = card({
      ops_modes: [
        ops({ kind: '전체', axis_value: '전체', n_verified: 10 }),
        ops({ axis_value: 'L9', n_verified: 10 }),
      ],
    });
    expect(stageDistribution(odd)[0].note).toBe('');
    expect(stageDistribution(odd)[0].code).toBe('L9');
  });

  it('⛔ 값을 못 낸 자리의 오차는 null 로 남는다 (0% 로 만들지 않는다)', () => {
    const none = stageDistribution(card()).find((s) => s.code === 'no_estimate');
    expect(none?.mdape).toBeNull();
  });

  it('전체 줄이 없으면 채택단계 합으로 비중을 낸다 (0 으로 나누지 않는다)', () => {
    const noTotal = card({
      ops_modes: [ops({ axis_value: 'L2', n_verified: 1 }), ops({ axis_value: 'L6', n_verified: 3 })],
    });
    expect(stageDistribution(noTotal)[0].share).toBeCloseTo(0.75, 6);
  });

  it('채택단계 줄이 없으면 빈 목록이다 (다른 줄을 대신 쓰지 않는다)', () => {
    const onlyTotal = card({ ops_modes: [ops({ kind: '전체', axis_value: '전체', n_verified: 5 })] });
    expect(stageDistribution(onlyTotal)).toEqual([]);
  });
});

describe('coverageNote — 유리한 숫자라고 밝히기 (결정 0013 §3)', () => {
  it('커버리지를 적되 그것이 유리한 숫자라고 함께 말한다', () => {
    const note = coverageNote(card());
    expect(note).toContain('90.0%');
    expect(note).toContain('유리');
  });

  it('못 읽으면 문장 자체를 안 만든다 — 지어내지 않는다', () => {
    expect(coverageNote(card({ ops_modes: [ops({ kind: '전체', coverage: null })] }))).toBeNull();
    expect(coverageNote(card({ ops_modes: [] }))).toBeNull();
  });
});

describe('stampDate — 언제 뽑은 성적인가', () => {
  it('날짜까지만 적는다 (분 단위는 정확해 보이기만 한다)', () => {
    expect(stampDate('2026-08-15T23:44:00+09:00')).toBe('2026년 8월 15일');
  });

  it('읽을 수 없으면 null 이다', () => {
    expect(stampDate('어제')).toBeNull();
    expect(stampDate(null)).toBeNull();
  });
});

describe('검증기 — 뜻밖의 답이 렌더로 흘러들지 않게', () => {
  it('게이트 줄의 모양을 본다', () => {
    expect(isPriceGateList([gate()])).toBe(true);
    expect(isPriceGateList([{ ...gate(), gate_pass: 'true' }])).toBe(false);
    expect(isPriceGateList({ code: 'PGRST202' })).toBe(false);
  });

  it('통과 여부가 빠진 줄은 거부한다 — 그 칸이 이 카드의 본론이다', () => {
    const { gate_pass: _omit, ...rest } = gate();
    expect(isPriceGateList([rest])).toBe(false);
  });

  it('성적표 파일의 모양을 본다', () => {
    expect(isScorecard(card())).toBe(true);
    expect(isScorecard({ version: 'v1' })).toBe(false);
    expect(isScorecard(card({ ops_modes: [{ kind: 1 } as unknown as ScorecardOpsMode] }))).toBe(
      false,
    );
  });
});

describe('loadScorecard — 파일 한 번만 받기', () => {
  beforeEach(() => resetScorecardCache());
  afterEach(() => {
    vi.unstubAllGlobals();
    resetScorecardCache();
  });

  it('두 번 불러도 왕복은 한 번이다', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(card()) }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const [a, b] = await Promise.all([loadScorecard(), loadScorecard()]);
    expect(a).toBe(b);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // ⚠️ 주소를 여기서 다시 적는 것이 아니라 **상수와 같은 값인지** 본다 — 판이 올라가면
    //    (v2) 상수가 바뀌므로, 글자를 박아 두면 그때 시험이 옛 주소를 요구하게 된다.
    expect(fetchMock).toHaveBeenCalledWith(SCORECARD_URL);
  });

  it('⛔ 실패는 캐시하지 않는다 — 잠깐 끊긴 한 번이 영영이 되면 안 된다', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 500, json: () => Promise.resolve({}) })
      .mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve(card()) });
    vi.stubGlobal('fetch', fetchMock);

    await expect(loadScorecard()).rejects.toThrow();
    await expect(loadScorecard()).resolves.toMatchObject({ version: 'v1' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('모양이 다른 파일은 받아들이지 않는다 — 반쪽 파일이 그럴듯하게 틀린 값을 만든다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ hello: 1 }) }),
      ),
    );
    await expect(loadScorecard()).rejects.toThrow(/모양/);
  });
});

/**
 * ★ 이 파일에서 가장 중요한 시험.
 *
 * 로드맵 Wave 4 는 "숫자 복사 금지 — 서버/CSV 에서 읽고 버전 스탬프"라고 정했다. 사람이
 * 성적표를 보며 화면에 `53.4%` 를 적어 넣으면 그 순간에는 맞지만, 성적표를 다시 뽑는 날
 * **화면만** 옛 숫자를 말한다. 에러가 아니라서 아무도 모른다.
 *
 * ⚠️ `?raw` import 를 쓰지 않는다 — 이 레포에서 vitest 의 `?raw` 가 빈 문자열을 돌려준
 *    적이 있어(가짜 초록), 파일을 `node:fs` 로 직접 읽는다.
 */
describe('★ 숫자 복사 금지 — 화면 코드에 통계 수치가 없다', () => {
  const files = ['./scorecard.ts', '../components/ScorecardSection.tsx'];

  function sourceOf(rel: string): string {
    return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');
  }

  it.each(files)('%s 에 백분율 리터럴이 없다', (rel) => {
    const found = sourceOf(rel).match(/\d+\.\d+\s?%/g);
    expect(found, `옮겨 적은 수치: ${found?.join(', ')}`).toBeNull();
  });

  it.each(files)('%s 에 성적표의 대표 수치(53.4·93.5)가 없다', (rel) => {
    const found = sourceOf(rel).match(/\b(53|93)\.\d/g);
    expect(found, `옮겨 적은 수치: ${found?.join(', ')}`).toBeNull();
  });

  it('가드가 늘 참인 시험이 아니다 — 리터럴이 있으면 실제로 잡는다', () => {
    // 이 문자열이 시험 대상 파일 안에 있었다면 위 두 시험이 빨간불이 됐어야 한다.
    const mutated = "const x = '오차 중앙값 53.4% 입니다';";
    expect(mutated.match(/\d+\.\d+\s?%/g)).not.toBeNull();
    expect(mutated.match(/\b(53|93)\.\d/g)).not.toBeNull();
  });
});
