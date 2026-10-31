import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  HISTORY_BADGE,
  HISTORY_BADGE_NOTE,
  HISTORY_CHIP,
  HISTORY_CURRENT_HEAD,
  HISTORY_GONE_HEAD,
  HISTORY_GONE_HEAD_NOTE,
  HISTORY_GONE_NOTE,
  HISTORY_LEAD_BOLD,
  HISTORY_LEAD_MID,
  HISTORY_LEAD_STRONG,
  floorText,
  groupCounts,
  historyNotes,
  historySummary,
  isStoreHistoryList,
  lagText,
  moreText,
  quartersBetween,
  rowText,
} from './storeHistory';
import type { DataFreshnessRow, StoreHistoryRow } from '../types';

/**
 * 「이 자리 가게 이력 (점포 자료 누적)」 순수 계산 — 결정 0045 PR④.
 *
 * 여기서 특히 지키는 것
 *  ① 모양 검사 — 하나라도 어긋나면 카드째 숨김(no_data 는 한 줄뿐 · 줄끼리 total·current·표지 값이 같음)
 *  ② 분기 글·분기 수는 서버 값으로만(첫·마지막 분기를 바꾸면 글이 따라 바뀐다)
 *  ③ 줄 글 네 갈래 · 어긋남 줄은 신선도 표 점포 줄과 다를 때만(표를 못 받았으면 줄 없음)
 *  ④ 가드: 분기·연도 글자 0 · 비율 0 · 판단 낱말 0 · 금지어 0 · 「폐업」은 각주 둘째 문장 한 곳 · 「영업 기간」은 부정문 안에만
 */

function okRow(over: Partial<StoreHistoryRow> = {}): StoreHistoryRow {
  return {
    status: 'ok',
    floor_no: 1,
    biz_name: '한솔마트',
    first_ym: '202003',
    last_ym: '202606',
    seen_cnt: 26,
    is_current: true,
    truncated: false,
    total_cnt: 3,
    current_cnt: 2,
    history_first_ym: '201712',
    history_last_ym: '202606',
    ...over,
  };
}

const NO_DATA: StoreHistoryRow = {
  status: 'no_data',
  floor_no: null,
  biz_name: null,
  first_ym: null,
  last_ym: null,
  seen_cnt: null,
  is_current: null,
  truncated: null,
  total_cnt: 0,
  current_cnt: 0,
  history_first_ym: '201712',
  history_last_ym: '202606',
};

const THREE = [
  okRow({ biz_name: '한솔마트', first_ym: '201712', seen_cnt: 35, truncated: true }),
  okRow({ biz_name: '청춘분식', first_ym: '202606', seen_cnt: 1 }),
  okRow({ biz_name: '옛날통닭', first_ym: '201903', last_ym: '202312', seen_cnt: 20, is_current: false }),
];

function fresh(basis: string | null, src = '점포·업종 (상권정보)'): DataFreshnessRow[] {
  return [{ src, basis_kind: '분기', basis, next_expected: null, cadence: '분기마다' }];
}

describe('isStoreHistoryList — 모양 검사(어긋나면 카드째 숨김)', () => {
  it('정상 ok 줄들 · no_data 한 줄은 받는다', () => {
    expect(isStoreHistoryList(THREE)).toBe(true);
    expect(isStoreHistoryList([NO_DATA])).toBe(true);
    expect(isStoreHistoryList([okRow({ floor_no: null }), okRow({ floor_no: -2 }), okRow({ floor_no: 99 })])).toBe(true);
  });

  it.each([
    ['배열 아님', { status: 'ok' }],
    ['빈 배열', []],
    ['null', null],
    ['ok·no_data 섞임', [okRow(), NO_DATA]],
    ['no_data 두 줄', [NO_DATA, NO_DATA]],
    ['no_data 인데 total 1', [{ ...NO_DATA, total_cnt: 1 }]],
    ['줄끼리 total 다름', [okRow(), okRow({ total_cnt: 4 })]],
    ['줄끼리 current 다름', [okRow(), okRow({ current_cnt: 1 })]],
    ['줄끼리 표지 분기 다름', [okRow(), okRow({ history_last_ym: '202603' })]],
    ['current > total', [okRow({ current_cnt: 4 })]],
    ['total < 받은 줄 수', [okRow({ total_cnt: 1 }), okRow({ total_cnt: 1 })]],
    ['분기 꼴 아님', [okRow({ first_ym: '201711' })]],
    ['처음 > 마지막', [okRow({ first_ym: '202606', last_ym: '202603' })]],
    ['seen_cnt 0', [okRow({ seen_cnt: 0 })]],
    ['층 0', [okRow({ floor_no: 0 })]],
    ['층 소수', [okRow({ floor_no: 1.5 })]],
    ['상호 빈 글', [okRow({ biz_name: ' ' })]],
    ['is_current 가 글자', [okRow({ is_current: 't' as unknown as boolean })]],
    ['표지 첫 분기 꼴 아님', [okRow({ history_first_ym: '2017Q4' })]],
  ])('%s → false', (_label, x) => {
    expect(isStoreHistoryList(x)).toBe(false);
  });
});

describe('분기 · 층 글', () => {
  it('quartersBetween — 양끝 포함 · 꼴이 아니거나 거꾸로면 null', () => {
    expect(quartersBetween('201712', '202606')).toBe(35);
    expect(quartersBetween('202606', '202606')).toBe(1);
    expect(quartersBetween('202606', '201712')).toBeNull();
    expect(quartersBetween('201711', '202606')).toBeNull();
  });

  it('floorText — 층 목록과 같은 표기 · 모름·0 은 「층 모름」', () => {
    expect(floorText(1)).toBe('1층');
    expect(floorText(-1)).toBe('지하 1층');
    expect(floorText(-40)).toBe('지하 40층');
    expect(floorText(99)).toBe('옥탑');
    expect(floorText(null)).toBe('층 모름');
    expect(floorText(0)).toBe('층 모름');
  });
});

describe('historySummary — 접힌 요약(서버 값만 · 비율·판단 0)', () => {
  it('지금 · 전에 · 첫 분기 · 분기 수', () => {
    expect(historySummary(THREE)).toBe('지금 보이는 가게 2곳 · 전에 보였던 가게 1곳 · 2017년 4분기부터 점포 자료 35분기');
  });

  it('전에 보였던 가게 0 이면 그 조각을 뺀다', () => {
    expect(historySummary([okRow({ total_cnt: 2, current_cnt: 2 })])).toBe(
      '지금 보이는 가게 2곳 · 2017년 4분기부터 점포 자료 35분기',
    );
  });

  it('no_data — 첫 분기 이후 보이지 않는다', () => {
    expect(historySummary([NO_DATA])).toBe('2017년 4분기 이후 점포 자료에 이 땅의 가게가 보이지 않습니다');
  });

  it('★ 분기 글은 서버 표지 값이다 — 첫·마지막 분기를 바꾸면 글이 따라 바뀐다', () => {
    const rows = [okRow({ history_first_ym: '201812', history_last_ym: '202603', first_ym: '202003', last_ym: '202603' })];
    expect(historySummary(rows)).toBe('지금 보이는 가게 2곳 · 전에 보였던 가게 1곳 · 2018년 4분기부터 점포 자료 30분기');
  });
});

describe('rowText — 줄 글 네 갈래', () => {
  it('지금 보임 + 첫 분기부터 → 「N분기 이상」 · 자료 시작부터 계속', () => {
    expect(rowText(THREE[0])).toEqual({ pre: '자료에 ', bold: '35분기 이상', post: ' 보임 · 자료 시작(2017년 4분기)부터 계속' });
  });
  it('지금 보임 → N분기 · ○년 ○분기부터', () => {
    expect(rowText(okRow())).toEqual({ pre: '자료에 ', bold: '26분기', post: ' 보임 · 2020년 1분기부터' });
  });
  it('지금 보임 · 1분기 → ○년 ○분기에 처음', () => {
    expect(rowText(THREE[1])).toEqual({ pre: '자료에 ', bold: '1분기', post: ' 보임 · 2026년 2분기에 처음' });
  });
  it('안 보임 → 처음 ~ 마지막 보임 · N분기(첫 분기부터면 「이상」)', () => {
    expect(rowText(THREE[2])).toEqual({ pre: '2019년 1분기 ~ 2023년 4분기 보임 · ', bold: '', post: '20분기' });
    expect(rowText(okRow({ first_ym: '201712', last_ym: '202106', seen_cnt: 15, is_current: false, truncated: true }))).toEqual({
      pre: '2017년 4분기 ~ 2021년 2분기 보임 · ',
      bold: '',
      post: '15분기 이상',
    });
  });
});

describe('lagText — 어긋남 줄(신선도 표 점포 줄과 다를 때만)', () => {
  it('다르면 「이 이력은 ○까지입니다 (점포 자료는 ○)」', () => {
    const rows = [okRow({ history_last_ym: '202603', last_ym: '202603' })];
    expect(lagText(rows, fresh('202606'))).toEqual({
      pre: '이 이력은 ',
      bold: '2026년 1분기',
      post: '까지입니다 (점포 자료는 2026년 2분기)',
    });
  });
  it('같거나 · 표를 못 받았거나 · 그 줄이 없거나 · 꼴이 아니면 줄 없음(거짓 경고 0)', () => {
    expect(lagText(THREE, fresh('202606'))).toBeNull();
    expect(lagText(THREE, null)).toBeNull();
    expect(lagText(THREE, fresh('202603', '실거래 (매매)'))).toBeNull();
    expect(lagText(THREE, fresh(null))).toBeNull();
    expect(lagText(THREE, fresh('2026Q1'))).toBeNull();
  });
});

describe('각주 · 묶음 · 단추', () => {
  it('각주 셋 — 첫째는 서버 분기로 만든다 · 둘째 굵은 문장 = 👤 원문', () => {
    const n = historyNotes(THREE);
    expect(n.source).toBe(
      '출처: 소상공인시장진흥공단 「상가(상권)정보」 분기 자료 2017년 4분기~2026년 2분기(35분기) — 상가업소번호로 잇고, ' +
        '번호가 바뀐 가게는 같은 땅·층·상호가 정확히 하나일 때만 이었습니다. 그 전 분기는 번호 체계가 달라 쓰지 않습니다.',
    );
    expect(n.gone[0]).toBe('자료에서 안 보이는 것은 폐업이 아닐 수 있습니다.');
    expect(n.gone[1]).toBe(' 자료에 빠졌다 돌아오는 가게가 흔하고, 그때는 새 줄로 셉니다 — 보인 분기 수는 영업 기간이 아닙니다.');
    expect(n.name).toBe(
      '상호는 자료의 마지막 값입니다 — 옛 분기의 이름이 그 시절 간판이라는 뜻은 아닙니다. 땅 번호가 바뀐 땅(분할·합병)은 옛 줄이 이 땅에 붙지 않습니다.',
    );
    const other = historyNotes([okRow({ history_first_ym: '201812', history_last_ym: '202603', last_ym: '202603' })]);
    expect(other.source).toContain('2018년 4분기~2026년 1분기(30분기)');
  });

  it('묶음 머리 수는 그 땅 전체(받은 줄 수가 아니다) · 단추 글은 남은 수', () => {
    expect(groupCounts([okRow({ total_cnt: 23, current_cnt: 6 })])).toEqual({ current: 6, gone: 17 });
    expect(moreText(20, 23)).toBe('더 보기 (남은 3곳)');
  });
});

// ── 가드 ───────────────────────────────────────────────────────────────────

/** ⓐ 분기·연도 글자(형제 카드 가드와 같은 꼴). 못 보는 것: 숫자를 쪼개 이은 꼴 · 계산으로 만든 연도. */
function findQuarterOrYearLiterals(src: string): string[] {
  return src.match(/(?<![\d])20\d{2}(?:[1-4](?!\d)|년|Q[1-4]|-\d{2}|0[3-9]|1[0-2])/g) ?? [];
}

/** ⓑ 비율 글자 — `%`·`％`·'퍼센트'·숫자 뒤 '배'. 못 보는 것: 나누기 기호로 적은 식 · 글자로 쓴 비교('절반'). */
function hasRatio(text: string): boolean {
  return /[%％]|퍼센트|\d\s*배/.test(text);
}

/** ⓒ 판단 낱말(형제 목록 + 이 카드에서 새기 쉬운 넷). 못 보는 것: 띄어 쓴 변형 · 목록 밖 낱말. */
const JUDGMENT = ['많', '적습', '적다', '적은 편', '좋', '나쁘', '유망', '추천', '괜찮', '충분', '부족', '활발', '위험',
  '높습', '높은', '낮습', '낮은', '인기', '늘었', '줄었', '오래', '짧게', '오랫', '장수', '단명', '자주 바뀌'];
function judgmentWords(text: string): string[] {
  return JUDGMENT.filter((w) => text.includes(w));
}

/** ⓓ 금지어(절대 규칙 2) — 공백을 지운 글로도 본다. */
const FORBIDDEN = ['적정가격', '적정가', '평가액', '감정가', '가치평가'];
function forbiddenWords(text: string): string[] {
  const t = text.replace(/\s+/g, '');
  return FORBIDDEN.filter((w) => t.includes(w));
}

/** ⓔ 「폐업」 — 허용 문장(각주 둘째 문장) 하나를 지운 글에 남은 개수. 못 보는 것: 띄어 쓴 「폐 업」. */
function closureWordsOutside(text: string, allowed: string): number {
  return text.split(allowed).join('').split('폐업').length - 1;
}

/** ⓕ 「영업 기간」이 부정문(「…이 아니」) 밖에 나온 곳. 못 보는 것: 「영업기간」처럼 붙여 쓴 꼴. */
function businessPeriodOutsideNegation(text: string): string[] {
  return text.match(/영업 기간(?!이 아(?:니|닙))/g) ?? [];
}

function source(f: string): string {
  return readFileSync(fileURLToPath(new URL(f, import.meta.url)), 'utf-8');
}

const FILES = ['./storeHistory.ts', '../components/HistorySection.tsx'];

/** 이 lib 가 만드는 글 전부(대표 입력으로). */
function allTexts(): string[] {
  const n = historyNotes(THREE);
  const lag = lagText([okRow({ history_last_ym: '202603', last_ym: '202603' })], fresh('202606'))!;
  return [
    historySummary(THREE),
    historySummary([NO_DATA]),
    ...THREE.flatMap((r) => Object.values(rowText(r))),
    ...Object.values(lag),
    n.source,
    ...n.gone,
    n.name,
    moreText(20, 23),
    HISTORY_LEAD_STRONG,
    HISTORY_LEAD_MID,
    HISTORY_LEAD_BOLD,
    HISTORY_BADGE,
    HISTORY_BADGE_NOTE,
    HISTORY_CHIP,
    HISTORY_CURRENT_HEAD,
    HISTORY_GONE_HEAD,
    HISTORY_GONE_HEAD_NOTE,
  ];
}

describe('⛔ 가드 — 분기·연도 글자 · 비율 · 판단 낱말 · 금지어 · 「폐업」 한 문장 · 「영업 기간」 부정문', () => {
  it('양성 대조 — 탐지 함수가 흔한 꼴과 변형 꼴을 실제로 잡는다', () => {
    expect(findQuarterOrYearLiterals("const x = '201712';")).toEqual(['201712']);
    expect(findQuarterOrYearLiterals('// 2017년 4분기부터')).toEqual(['2017년']);
    expect(findQuarterOrYearLiterals('20분기 · 35분기 · 100곳')).toEqual([]);
    expect(hasRatio('가게의 18%')).toBe(true);
    expect(hasRatio('1.8배')).toBe(true);
    expect(judgmentWords('오래 있던 가게')).toEqual(['오래']);
    expect(forbiddenWords('적정 가격')).toEqual(['적정가격', '적정가']);
    expect(closureWordsOutside(`${HISTORY_GONE_NOTE} 다른 줄 폐업 표시`, HISTORY_GONE_NOTE)).toBe(1);
    expect(closureWordsOutside(HISTORY_GONE_NOTE, HISTORY_GONE_NOTE)).toBe(0);
    expect(businessPeriodOutsideNegation('보인 분기 수가 곧 영업 기간입니다')).toEqual(['영업 기간']);
    expect(businessPeriodOutsideNegation('영업 기간이 아닙니다')).toEqual([]);
  });

  it('ⓐ·ⓓ·ⓔ·ⓕ 카드·도우미 원문(주석 포함)', () => {
    for (const f of FILES) {
      const src = source(f);
      expect(findQuarterOrYearLiterals(src), f).toEqual([]);
      expect(forbiddenWords(src), f).toEqual([]);
      expect(closureWordsOutside(src, HISTORY_GONE_NOTE), f).toBe(0);
      expect(businessPeriodOutsideNegation(src), f).toEqual([]);
    }
    // 허용 문장은 lib 에 정확히 한 번 있다(컴포넌트는 그 상수를 가져다 쓴다).
    expect(source('./storeHistory.ts').split(HISTORY_GONE_NOTE).length - 1).toBe(1);
  });

  it('ⓑ·ⓒ·ⓓ·ⓔ·ⓕ 만드는 글', () => {
    const texts = allTexts();
    for (const t of texts) {
      expect(hasRatio(t), t).toBe(false);
      expect(judgmentWords(t), t).toEqual([]);
      expect(forbiddenWords(t), t).toEqual([]);
      expect(businessPeriodOutsideNegation(t), t).toEqual([]);
    }
    const joined = texts.join('\n');
    expect(closureWordsOutside(joined, HISTORY_GONE_NOTE)).toBe(0);
    expect(joined).toContain(HISTORY_GONE_NOTE);
  });
});
