import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { NearbySubway, NearbySubwayBins } from '../types';
import {
  SUBWAY_BADGE,
  SUBWAY_CHUNK_TITLE,
  SUBWAY_NONE_TEXT,
  SUBWAY_NOTES,
  SUBWAY_NO_STATION_TEXT,
  isNearbySubwayList,
  subwayBars,
  subwayNoStationText,
  subwayNumbers,
  subwayShows,
  subwayStationLine,
  subwaySummaryTail,
} from './subwayNearby';

/**
 * 지하철 승하차 덩이의 순수 계산(결정 0045 PR⑥ · 👤 11-02 Q1 가 · Q2 가 · Q3 가 · Q4 나).
 *
 * 여기서 특히 지키는 것
 *  ① 모양 검사 — 빈 배열·섞인 답·bins 열쇠 빠짐·dist 501·lines_with_data ⊄ lines·has_data 인데 숫자 null → 거부(양성 대조 짝)
 *  ② 호선 글(3·4호선 · 자료 없음 꼬리 · 전부 없음) · 숫자 글(12개월 · 8개월 · 창 글은 서버 값) · 막대(높이만 비례)
 *  ③ 500m 안 역 0 글 · 요약 꼬리(역 수만 — 승하차 값 0)
 *  ④ 글 가드 — 원문·만드는 글에 달·연도 글자 0 · 「유동인구」 0 · 금지어 0 · % 0 · 「하루 평균」은 숫자 줄·scale 에만
 */

const BINS: NearbySubwayBins = {
  h04_07: { on: 1200, off: 900 },
  h07_10: { on: 9000, off: 8000 },
  h10_14: { on: 5000, off: 6000 },
  h14_17: { on: 4000, off: 4300 },
  h17_21: { on: 10000, off: 11000 },
  h21_04: { on: 2400, off: 2000 },
};

function okRow(over: Partial<NearbySubway> = {}): NearbySubway {
  return {
    status: 'ok',
    group_id: 101,
    station_nm: '충무로',
    lines: ['3호선', '4호선'],
    lines_with_data: ['3호선', '4호선'],
    dist_m: 180,
    has_data: true,
    window_from: '202510',
    window_to: '202609',
    months_n: 12,
    on_daily: 31600,
    off_daily: 32300,
    bins: BINS,
    nearest_nm: null,
    nearest_lines: null,
    nearest_dist_m: null,
    ...over,
  };
}

function noDataLineRow(over: Partial<NearbySubway> = {}): NearbySubway {
  return okRow({
    group_id: 202,
    station_nm: '양재시민의숲',
    lines: ['신분당선'],
    lines_with_data: null,
    dist_m: 320,
    has_data: false,
    months_n: 0,
    on_daily: null,
    off_daily: null,
    bins: null,
    ...over,
  });
}

function headRow(status: NearbySubway['status'], over: Partial<NearbySubway> = {}): NearbySubway {
  return {
    status,
    group_id: null,
    station_nm: null,
    lines: null,
    lines_with_data: null,
    dist_m: null,
    has_data: null,
    window_from: null,
    window_to: null,
    months_n: null,
    on_daily: null,
    off_daily: null,
    bins: null,
    nearest_nm: null,
    nearest_lines: null,
    nearest_dist_m: null,
    ...over,
  };
}

const NO_STATION = headRow('no_station', { nearest_nm: '수유', nearest_lines: ['4호선'], nearest_dist_m: 820 });

describe('isNearbySubwayList — 모양 검사', () => {
  it('받는 꼴 — ok 줄들(자료 있음·자료 없는 노선) · no_station(가장 가까운 역 있음/없음) · 빈 상태 셋', () => {
    expect(isNearbySubwayList([okRow(), noDataLineRow()])).toBe(true);
    expect(isNearbySubwayList([NO_STATION])).toBe(true);
    expect(isNearbySubwayList([headRow('no_station')])).toBe(true);
    for (const s of ['no_coord', 'not_seoul', 'no_data'] as const) expect(isNearbySubwayList([headRow(s)]), s).toBe(true);
    // 경계 — dist 0·500 · months 1·12.
    expect(isNearbySubwayList([okRow({ dist_m: 0 }), okRow({ dist_m: 500, months_n: 1 })])).toBe(true);
  });

  it('⛔ 빈 배열 · 배열 아님 · 모르는 상태 → 거부', () => {
    expect(isNearbySubwayList([])).toBe(false);
    expect(isNearbySubwayList(null)).toBe(false);
    expect(isNearbySubwayList({ status: 'ok' })).toBe(false);
    expect(isNearbySubwayList([{ ...okRow(), status: 'nearby' }])).toBe(false);
  });

  it('⛔ 섞인 답 — ok + 빈 상태 · 빈 상태 둘 · 정상 + 이상한 줄 하나 → 통째로 거부(양성 대조: 따로면 받는다)', () => {
    expect(isNearbySubwayList([okRow(), NO_STATION])).toBe(false);
    expect(isNearbySubwayList([NO_STATION, headRow('no_data')])).toBe(false);
    expect(isNearbySubwayList([okRow(), okRow({ on_daily: 1.5 })])).toBe(false);
    expect(isNearbySubwayList([okRow()])).toBe(true);
  });

  it('⛔ bins — 열쇠 하나 빠짐 · 값이 음수·소수 · on/off 빠짐 → 거부', () => {
    const { h21_04: _drop, ...five } = BINS;
    void _drop;
    expect(isNearbySubwayList([okRow({ bins: five as unknown as NearbySubwayBins })])).toBe(false);
    expect(isNearbySubwayList([okRow({ bins: { ...BINS, h04_07: { on: -1, off: 0 } } })])).toBe(false);
    expect(isNearbySubwayList([okRow({ bins: { ...BINS, h07_10: { on: 1.5, off: 0 } } })])).toBe(false);
    expect(
      isNearbySubwayList([okRow({ bins: { ...BINS, h10_14: { on: 3 } as unknown as { on: number; off: number } } })]),
    ).toBe(false);
  });

  it('⛔ dist 501·음수·소수 · lines 비었음 · lines_with_data ⊄ lines → 거부', () => {
    expect(isNearbySubwayList([okRow({ dist_m: 501 })])).toBe(false);
    expect(isNearbySubwayList([okRow({ dist_m: -1 })])).toBe(false);
    expect(isNearbySubwayList([okRow({ dist_m: 12.5 })])).toBe(false);
    expect(isNearbySubwayList([okRow({ lines: [] })])).toBe(false);
    expect(isNearbySubwayList([okRow({ lines_with_data: ['3호선', '9호선'] })])).toBe(false);
    // 양성 대조 — 일부만 자료 있음은 받는다.
    expect(isNearbySubwayList([okRow({ lines_with_data: ['4호선'] })])).toBe(true);
  });

  it('⛔ has_data 인데 숫자 null · months 0·13 · 창 모양 틀림 / has_data 아닌데 숫자 있음 → 거부', () => {
    expect(isNearbySubwayList([okRow({ on_daily: null })])).toBe(false);
    expect(isNearbySubwayList([okRow({ bins: null })])).toBe(false);
    expect(isNearbySubwayList([okRow({ lines_with_data: null })])).toBe(false);
    expect(isNearbySubwayList([okRow({ months_n: 0 })])).toBe(false);
    expect(isNearbySubwayList([okRow({ months_n: 13 })])).toBe(false);
    expect(isNearbySubwayList([okRow({ window_to: '202613' })])).toBe(false);
    expect(isNearbySubwayList([okRow({ window_from: '2025-10' })])).toBe(false);
    expect(isNearbySubwayList([okRow({ has_data: null })])).toBe(false);
    expect(isNearbySubwayList([noDataLineRow({ bins: BINS })])).toBe(false);
    expect(isNearbySubwayList([noDataLineRow({ on_daily: 10 })])).toBe(false);
    expect(isNearbySubwayList([noDataLineRow({ lines_with_data: ['신분당선'] })])).toBe(false);
  });

  it('⛔ no_station — 가장 가까운 역 셋이 일부만 · 거리 500 이하·1,501 이상 → 거부', () => {
    expect(isNearbySubwayList([headRow('no_station', { nearest_nm: '수유' })])).toBe(false);
    expect(isNearbySubwayList([{ ...NO_STATION, nearest_dist_m: 500 }])).toBe(false);
    expect(isNearbySubwayList([{ ...NO_STATION, nearest_dist_m: 1501 }])).toBe(false);
    expect(isNearbySubwayList([{ ...NO_STATION, nearest_lines: [] }])).toBe(false);
    expect(isNearbySubwayList([{ ...NO_STATION, nearest_dist_m: 1500 }])).toBe(true);
  });
});

describe('subwayShows — 덩이를 그리는 답', () => {
  it('ok 줄 · no_station 은 그린다 · no_data·no_coord·not_seoul·null 은 안 그린다', () => {
    expect(subwayShows([okRow()])).toBe(true);
    expect(subwayShows([NO_STATION])).toBe(true);
    for (const s of ['no_data', 'no_coord', 'not_seoul'] as const) expect(subwayShows([headRow(s)]), s).toBe(false);
    expect(subwayShows(null)).toBe(false);
    expect(subwayShows([])).toBe(false);
  });
});

describe('subwayStationLine — 역 이름 + 호선 · 거리', () => {
  it('「N호선」은 숫자만 모은다 — 3·4호선 · 180m', () => {
    expect(subwayStationLine(okRow())).toEqual({ name: '충무로', sub: '3·4호선 · 180m' });
  });

  it('숫자는 크기 차례 · 그 밖 노선은 이름 그대로 뒤에', () => {
    const r = okRow({ lines: ['10호선', '2호선', '경의중앙선', '9호선'], lines_with_data: ['10호선', '2호선', '경의중앙선', '9호선'] });
    expect(subwayStationLine(r).sub).toBe('2·9·10호선 · 경의중앙선 · 180m');
  });

  it('자료 없는 호선은 「(자료 없음)」 꼬리 — 2호선 · 신분당선(자료 없음) · 410m', () => {
    const r = okRow({ station_nm: '강남', lines: ['2호선', '신분당선'], lines_with_data: ['2호선'], dist_m: 410 });
    expect(subwayStationLine(r)).toEqual({ name: '강남', sub: '2호선 · 신분당선(자료 없음) · 410m' });
  });

  it('전부 자료 없음(has_data false)이면 꼬리 없이 이름만 — 신분당선 · 320m', () => {
    expect(subwayStationLine(noDataLineRow())).toEqual({ name: '양재시민의숲', sub: '신분당선 · 320m' });
  });
});

describe('subwayNumbers — 숫자 줄', () => {
  it('자료 있음 · 12개월 — 승차·하차 나란히 + 「하루 평균」 + 「최근 12개월(…~…) 평균」', () => {
    expect(subwayNumbers(okRow())).toEqual({
      on: '승차 31,600',
      off: '하차 32,300',
      tail: '하루 평균',
      period: '최근 12개월(2025년 10월~2026년 9월) 평균',
    });
  });

  it('모자라면 「8개월 평균(… 중 자료 있는 달)」 · 달 글은 서버 창에서(다른 창이면 다른 글)', () => {
    expect(subwayNumbers(okRow({ months_n: 8 }))).toMatchObject({
      period: '8개월 평균(2025년 10월~2026년 9월 중 자료 있는 달)',
    });
    expect(subwayNumbers(okRow({ window_from: '202401', window_to: '202412' }))).toMatchObject({
      period: '최근 12개월(2024년 1월~2024년 12월) 평균',
    });
  });

  it('자료 없는 노선 — 「승하차 자료 없음 — 서울시 자료 밖 노선」', () => {
    expect(subwayNumbers(noDataLineRow())).toEqual({ none: '승하차 자료 없음 — 서울시 자료 밖 노선' });
  });
});

describe('subwayBars — 시간대 막대 여섯', () => {
  it('눈금 여섯 · 높이 = (승차+하차) ÷ 여섯 칸 최댓값 · 가장 큰 칸 100 · scale · 읽어 주기 글', () => {
    const b = subwayBars(okRow())!;
    expect(b.bars.map((x) => x.tick)).toEqual(['4~7', '7~10', '10~14', '14~17', '17~21', '21~']);
    expect(b.max).toBe(21000);
    expect(b.bars[4].h).toBe(100);
    expect(b.bars[0].h).toBeCloseTo((2100 / 21000) * 100, 6);
    expect(b.bars[1].h).toBeCloseTo((17000 / 21000) * 100, 6);
    expect(b.scale).toBe('꽉 차면 21,000명(하루 평균 승하차)');
    expect(b.bars[0].label).toBe('4~7 승차 1,200 · 하차 900');
  });

  it('자료 없는 노선 → null · 여섯 칸 다 0 → 높이 0 · scale 없음', () => {
    expect(subwayBars(noDataLineRow())).toBeNull();
    const zero = Object.fromEntries(Object.keys(BINS).map((k) => [k, { on: 0, off: 0 }])) as NearbySubwayBins;
    const b = subwayBars(okRow({ bins: zero }))!;
    expect(b.bars.every((x) => x.h === 0)).toBe(true);
    expect(b.scale).toBeNull();
  });
});

describe('subwayNoStationText · subwaySummaryTail', () => {
  it('500m 안 역 0 — 가장 가까운 역이 있으면 둘째 줄 · 없으면(1.5km 밖) 첫 줄만', () => {
    expect(subwayNoStationText(NO_STATION)).toEqual({
      main: '500m 안에 지하철역이 없습니다',
      nearest: '가장 가까운 역: 수유 (4호선) · 820m',
    });
    expect(subwayNoStationText({ ...NO_STATION, nearest_lines: ['4호선', '1호선'], nearest_dist_m: 1200 }).nearest).toBe(
      '가장 가까운 역: 수유 (1·4호선) · 1,200m',
    );
    expect(subwayNoStationText(headRow('no_station'))).toEqual({ main: '500m 안에 지하철역이 없습니다', nearest: null });
  });

  it('요약 꼬리 — 역 수만(숫자 뒤 「명」 0 · 승하차 값 0) · no_station 「없음」 · 덩이 없는 답 null', () => {
    const t = subwaySummaryTail([okRow(), noDataLineRow()]);
    expect(t).toBe('500m 안 지하철역 2곳');
    expect(t).not.toMatch(/명|31,600|32,300/);
    expect(subwaySummaryTail([NO_STATION])).toBe('500m 안 지하철역 없음');
    expect(subwaySummaryTail([headRow('no_data')])).toBeNull();
    expect(subwaySummaryTail(null)).toBeNull();
  });
});

// ── 글 가드 ─────────────────────────────────────────────────────────────────

/** 분기·연도 꼴(districtPop.test 와 같은 꼴) + 'YYYYMM' 여섯 자리 달 꼴(그쪽 꼴은 이것을 못 본다). 못 보는 것: 쪼개 이은 꼴. */
function findDateLiterals(src: string): string[] {
  const quarterOrYear = src.match(/(?<![\d])20\d{2}(?:[1-4](?!\d)|년|Q[1-4]|-\d{2})/g) ?? [];
  const ym = src.match(/(?<![\d])20\d{2}(?:0[1-9]|1[0-2])(?!\d)/g) ?? [];
  return [...quarterOrYear, ...ym];
}
function hasRatio(text: string): boolean {
  return /[%％]|퍼센트|\d\s*배/.test(text);
}
const FORBIDDEN = ['적정가격', '적정가', '평가액', '감정가', '가치평가'];
const FLOW_WORD = '유동인구';
const DAILY = '하루 평균';

function allSubwayTexts(): { text: string; daily: boolean }[] {
  const ok = okRow();
  const n = subwayNumbers(ok) as { on: string; off: string; tail: string; period: string };
  const b = subwayBars(ok)!;
  const st = subwayStationLine(okRow({ lines: ['2호선', '신분당선'], lines_with_data: ['2호선'] }));
  const none = subwayNumbers(noDataLineRow()) as { none: string };
  const ns = subwayNoStationText(NO_STATION);
  const plain = [
    SUBWAY_CHUNK_TITLE,
    SUBWAY_BADGE,
    SUBWAY_NONE_TEXT,
    SUBWAY_NO_STATION_TEXT,
    SUBWAY_NOTES.source,
    ...SUBWAY_NOTES.count,
    SUBWAY_NOTES.transfer,
    SUBWAY_NOTES.notBuilding,
    st.name,
    st.sub,
    n.on,
    n.off,
    n.period,
    none.none,
    ns.main,
    ns.nearest ?? '',
    ...b.bars.map((x) => x.label ?? ''),
    subwaySummaryTail([ok]) ?? '',
    subwaySummaryTail([NO_STATION]) ?? '',
  ];
  return [...plain.map((text) => ({ text, daily: false })), { text: n.tail, daily: true }, { text: b.scale!, daily: true }];
}

describe('⛔ 글 가드 — 달·연도 글자 · 「유동인구」 · 금지어 · % · 「하루 평균」 자리', () => {
  it('양성 대조 — 탐지가 실제로 잡는다', () => {
    expect(findDateLiterals("'202609'")).toEqual(['202609']);
    expect(findDateLiterals('2026년 9월')).toEqual(['2026년']);
    expect(findDateLiterals("'20262'")).toEqual(['20262']);
    expect(findDateLiterals("/^\\d{6}$/ · 'h04_07' · 500m")).toEqual([]);
    expect(hasRatio('승차 46%')).toBe(true);
    expect('역 앞 유동인구'.includes(FLOW_WORD)).toBe(true);
    expect(allSubwayTexts().filter((t) => t.text.includes(DAILY)).length).toBeGreaterThan(0); // 헛돌지 않는다
  });

  it('ⓐ lib·컴포넌트 원문에 달·연도 글자 · 「유동인구」 · 금지어가 없다', () => {
    for (const f of ['./subwayNearby.ts', '../components/PopSection.tsx']) {
      const src = readFileSync(fileURLToPath(new URL(f, import.meta.url)), 'utf-8');
      expect(findDateLiterals(src), f).toEqual([]);
      expect(src.includes(FLOW_WORD), `${f} ${FLOW_WORD}`).toBe(false);
      for (const w of FORBIDDEN) expect(src.includes(w), `${f} ${w}`).toBe(false);
    }
  });

  it('ⓑ 만드는 글 — 「유동인구」 0 · 금지어 0 · % 0 · 「하루 평균」은 숫자 줄 꼬리·scale 에만', () => {
    for (const { text, daily } of allSubwayTexts()) {
      expect(text.includes(FLOW_WORD), text).toBe(false);
      expect(hasRatio(text), text).toBe(false);
      expect(FORBIDDEN.filter((w) => text.replace(/\s+/g, '').includes(w)), text).toEqual([]);
      expect(text.includes(DAILY), `${daily ? '있어야' : '없어야'} · ${text}`).toBe(daily);
    }
  });

  it('ⓒ 시안 글자 그대로 — 제목 · 배지 · 발 넷', () => {
    expect(SUBWAY_CHUNK_TITLE).toBe('가까운 지하철역 승하차 인원 (카드 기준 · 건물 500m 안)');
    expect(SUBWAY_BADGE).toBe('A등급 · 카드 실측 집계');
    expect(SUBWAY_NOTES.source).toBe(
      '출처: 서울시 「지하철 호선별 역별 시간대별 승하차 인원」·「역사마스터」(열린데이터광장 · 공공누리 1유형).',
    );
    expect(SUBWAY_NOTES.count.join('')).toBe(
      '교통카드(1회용 포함)를 찍은 승차 수와 하차 수입니다 — 한 사람이 타고 내리면 승차 1·하차 1로 셉니다.',
    );
    expect(SUBWAY_NOTES.notBuilding).toBe('역 승하차 수이지 이 건물 앞을 지나는 사람 수가 아니고, 이 건물의 값이 아닙니다.');
  });
});
