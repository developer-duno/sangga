import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * 대전 「동네 폐업 (대전시 공표)」의 순수 계산·글(결정 0044) + 미리 부르기가 대전 필지에만 그 함수를 보내는지.
 *
 * 여기서 지키는 것
 *  ① 모양 검사 — 숫자끼리 다른 말을 하는 답(분기 합 ≠ 큰 숫자 ≠ 업종 합 · 차례 어긋남)은 통째로 버린다(→ 옛 대전 화면).
 *  ② 글 — 이름 줄 · 큰 숫자 · 기간 · 업종 표 5줄 + 그 밖 · 접힌 요약(값 0) · 역할 요약 칸 · 발 문구 다섯(👤 원문).
 *  ③ 서울 건물에는 대전 함수 요청 0.
 */

const rpcCalls: string[] = [];
vi.mock('./supabase', () => ({
  supabase: {
    rpc: (fn: string) => {
      rpcCalls.push(fn);
      return Promise.resolve({ data: null, error: null });
    },
  },
}));

const {
  DAEJEON_CLOSURE_NOTES,
  closureBigText,
  daejeonBars,
  daejeonSummary,
  daejeonTileLines,
  dongLine,
  industryTable,
  isDaejeonPnu,
  parseDaejeonClosure,
  quarterRangeText,
  restText,
} = await import('./daejeonClosure');
const { startSidePrefetch, SIDE_PREFETCH_FNS } = await import('./sidePrefetch');

function ok(over: Record<string, unknown> = {}) {
  return {
    status: 'ok',
    dong_nm: '둔산2동',
    received_on: '2026-10-28',
    quarters: [
      { quarter: '20251', clsbiz_co: 95 },
      { quarter: '20252', clsbiz_co: 100 },
      { quarter: '20253', clsbiz_co: 80 },
      { quarter: '20254', clsbiz_co: 103 },
      { quarter: '20261', clsbiz_co: 95 },
    ],
    sum_quarters: ['20252', '20253', '20254', '20261'],
    clsbiz_sum: 378,
    industries: [
      { induty_nm: '음식점업', clsbiz_co: 111 },
      { induty_nm: '주점 및 비알코올 음료점업', clsbiz_co: 35 },
      { induty_nm: '섬유, 의복, 신발 및 가죽제품 소매업', clsbiz_co: 32 },
      { induty_nm: '미용, 욕탕 및 유사 서비스업', clsbiz_co: 26 },
      { induty_nm: '유원지 및 기타 오락관련 서비스업', clsbiz_co: 21 },
      { induty_nm: '기타 상품 전문 소매업', clsbiz_co: 19 },
      { induty_nm: '의원', clsbiz_co: 134 },
    ].sort((a, b) => b.clsbiz_co - a.clsbiz_co),
    ...over,
  };
}

describe('parseDaejeonClosure — 모양 검사', () => {
  it('ok 를 그대로 받는다 · no_dong 은 숫자 칸 null', () => {
    const r = parseDaejeonClosure([ok()]);
    expect(r?.status).toBe('ok');
    expect(r?.clsbiz_sum).toBe(378);
    const n = parseDaejeonClosure([{ status: 'no_dong', dong_nm: null, received_on: '2026-10-28' }]);
    expect(n).toEqual({
      status: 'no_dong',
      dong_nm: null,
      received_on: '2026-10-28',
      quarters: null,
      sum_quarters: null,
      clsbiz_sum: null,
      industries: null,
    });
  });

  it.each([
    ['배열 아님', ok()],
    ['0줄', []],
    ['두 줄', [ok(), ok()]],
    ['not_daejeon', [{ status: 'not_daejeon' }]],
    ['모르는 상태', [{ ...ok(), status: 'closed' }]],
    ['동 이름 빔', [ok({ dong_nm: ' ' })]],
    ['분기 0칸', [ok({ quarters: [], sum_quarters: [] })]],
    ['분기 꼴', [ok({ quarters: [{ quarter: '2025Q1', clsbiz_co: 1 }] })]],
    ['분기 차례 뒤집힘', [ok({ quarters: [...ok().quarters].reverse() })]],
    ['음수', [ok({ quarters: [{ quarter: '20261', clsbiz_co: -1 }] })]],
    ['소수', [ok({ clsbiz_sum: 378.5 })]],
    ['더한 분기가 창 끝이 아님', [ok({ sum_quarters: ['20251', '20252', '20253', '20254'] })]],
    ['더한 분기가 창보다 김', [ok({ quarters: [{ quarter: '20261', clsbiz_co: 378 }] })]],
    ['큰 숫자 ≠ 분기 합', [ok({ clsbiz_sum: 377 })]],
    ['업종 합 ≠ 큰 숫자', [ok({ industries: ok().industries.slice(1) })]],
    ['업종 많은 순 아님', [ok({ industries: [...ok().industries].reverse() })]],
    ['업종 0 건 줄', [ok({ industries: [...ok().industries, { induty_nm: '병원', clsbiz_co: 0 }] })]],
    ['업종 이름 빔', [ok({ industries: [{ induty_nm: '', clsbiz_co: 378 }] })]],
  ])('%s → null(옛 대전 화면)', (_n, data) => {
    expect(parseDaejeonClosure(data)).toBeNull();
  });
});

describe('글', () => {
  it('이름 줄 · 큰 숫자 · 기간 · 요약(값 0) · 역할 칸', () => {
    const r = parseDaejeonClosure([ok()])!;
    expect(dongLine('둔산2동')).toBe('둔산2동 · 가게 업종');
    expect(closureBigText(1234)).toBe('폐업 1,234건');
    expect(quarterRangeText(r.sum_quarters!)).toBe('2025년 2분기~2026년 1분기');
    expect(quarterRangeText(['20261'])).toBe('2026년 1분기');
    expect(quarterRangeText([])).toBeNull();
    expect(daejeonSummary(r)).toBe('둔산2동 · 2026년 1분기까지 대전시 공표');
    expect(daejeonSummary(r)).not.toMatch(/\d건/);
    expect(daejeonTileLines(r)).toEqual({ line: '폐업 378건 · 최근 4분기(가게 업종)', basis: '둔산2동 · 대전시 공표' });
    const nd = parseDaejeonClosure([{ status: 'no_dong' }])!;
    expect(daejeonTileLines(nd)).toBeNull();
  });

  it('업종 표 — 위 다섯 + 그 밖 N종 M건 · 다섯 이하면 그 밖 없음', () => {
    const { top, rest } = industryTable(parseDaejeonClosure([ok()])!.industries!);
    expect(top.map((x) => x.induty_nm)).toEqual([
      '의원',
      '음식점업',
      '주점 및 비알코올 음료점업',
      '섬유, 의복, 신발 및 가죽제품 소매업',
      '미용, 욕탕 및 유사 서비스업',
    ]);
    expect(rest && restText(rest)).toBe('그 밖 2종 40건');
    expect(industryTable([{ induty_nm: '의원', clsbiz_co: 3 }]).rest).toBeNull();
  });

  it('막대 — 창 안 최댓값 기준 % · 0 은 0', () => {
    const bars = daejeonBars([
      { quarter: '20254', clsbiz_co: 0 },
      { quarter: '20261', clsbiz_co: 4 },
      { quarter: '20262', clsbiz_co: 2 },
    ]);
    expect(bars.map((b) => b.h)).toEqual([0, 100, 50]);
    expect(bars[0]).toMatchObject({ label: '2025년 4분기', year: '2025', q: '4', count: 0 });
    expect(daejeonBars([{ quarter: '20261', clsbiz_co: 0 }])[0].h).toBe(0);
  });

  it('발 문구 다섯 — 👤 지시서 원문 그대로 · 차례 그대로 · 폐업률·적정가 낱말 없음', () => {
    expect(DAEJEON_CLOSURE_NOTES).toEqual([
      '출처: 대전광역시 상권분석 서비스(8989.daejeon.go.kr)',
      '동네(행정동) 전체 값이며 이 건물의 값이 아닙니다.',
      '대전시는 개업 수를 내지 않아 폐업만 싣습니다.',
      '손님을 받는 가게 업종 33종만 셉니다(부동산 임대·인터넷 판매·도매·사무실 업종 등은 뺍니다).',
      '2024년까지는 대전시 집계 방식이 달라 보이고 최근 6개월은 아직 덜 들어와, 둘 다 싣지 않습니다.',
    ]);
    for (const t of DAEJEON_CLOSURE_NOTES) expect(t).not.toMatch(/폐업률|적정가|감정가|평가액/);
  });

  it('대전 필지 판정은 pnu 앞 두 자리 30', () => {
    expect(isDaejeonPnu('3017010100100010000')).toBe(true);
    expect(isDaejeonPnu('1168010100100010000')).toBe(false);
    expect(isDaejeonPnu('1130010100100010000')).toBe(false);
  });
});

describe('미리 부르기 — 대전 필지에만 대전 함수(결정 0044)', () => {
  beforeEach(() => {
    rpcCalls.length = 0;
  });

  it('★ 대전 필지면 일곱 + 대전 함수 · 서울 필지면 일곱 그대로(요청 0 더함)', () => {
    const dj = startSidePrefetch('3017010100100010000');
    expect([...dj.results.keys()]).toEqual([...SIDE_PREFETCH_FNS, 'get_daejeon_dong_closure']);
    expect(rpcCalls).toEqual([...SIDE_PREFETCH_FNS, 'get_daejeon_dong_closure']);
    rpcCalls.length = 0;
    const se = startSidePrefetch('1168010100100010000');
    expect([...se.results.keys()]).toEqual([...SIDE_PREFETCH_FNS]);
    expect(rpcCalls).not.toContain('get_daejeon_dong_closure');
  });
});
