import { describe, it, expect } from 'vitest';

import { readFileSync } from 'node:fs';

import {
  basisText,
  CARD_SOURCES,
  cardSourceLine,
  isDataFreshnessList,
  isDataFreshnessRow,
  nextText,
  seoulToday,
} from './dataFreshness';
import { ENTRY_SECTION_PLAN, SECTION_PLAN, type SectionPlan } from './sectionCards';
import type { DataFreshnessRow } from '../types';

/**
 * 화면 아래 신선도 표의 순수 계산.
 *
 * 여기서 특히 지키는 것
 * ---------------------
 *  ① **여섯 자리 하나가 두 가지 뜻이다** — '202606' 은 상권정보에서 분기(2026년 2분기)이고
 *     실거래에서는 달(2026년 6월)이다. 이걸 한 가지로 읽으면 화면이 조용히 틀린다.
 *  ② **값이 없는 것과 주기가 없는 것을 갈라 말한다** — '자료 없음' ↔ '정해진 주기 없음'.
 *     둘을 뭉치면 "아직 안 들어온 자료"와 "주기가 없는 자료"가 같아 보인다.
 *  ③ **검증기가 null 을 통과시킨다** — 문자열만 받으면 그 한 줄 때문에 표가 통째로
 *     사라진다(`isLhNotice` 가 `pan_ss` 로 실제로 겪은 일이다).
 */

function row(over: Partial<DataFreshnessRow> = {}): DataFreshnessRow {
  return {
    src: '점포·업종 (상권정보)',
    basis_kind: '분기',
    basis: '202606',
    next_expected: '2026-10-31',
    cadence: '분기마다 (다음 분기 자료가 공개되면 사람이 적재)',
    ...over,
  };
}

describe('basisText — 기준값을 사람이 읽는 글자로', () => {
  it("분기 종류의 '202606' 은 분기로 읽는다", () => {
    expect(basisText(row({ basis_kind: '분기', basis: '202606' }))).toBe('2026년 2분기');
    expect(basisText(row({ basis_kind: '분기', basis: '202609' }))).toBe('2026년 3분기');
    expect(basisText(row({ basis_kind: '분기', basis: '202601' }))).toBe('2026년 1분기');
    expect(basisText(row({ basis_kind: '분기', basis: '202612' }))).toBe('2026년 4분기');
  });

  it("⛔ 같은 '202606' 이라도 계약월·기준월이면 **달**이다", () => {
    expect(basisText(row({ basis_kind: '계약월', basis: '202608' }))).toBe('2026년 8월');
    expect(basisText(row({ basis_kind: '기준월', basis: '202607' }))).toBe('2026년 7월');
    // 같은 값, 다른 종류 — 이 둘이 같아지면 화면이 조용히 틀린다.
    expect(basisText(row({ basis_kind: '계약월', basis: '202606' }))).toBe('2026년 6월');
    expect(basisText(row({ basis_kind: '분기', basis: '202606' }))).toBe('2026년 2분기');
  });

  it("부동산원 분기 표기 '2026Q2' 도 읽는다 — 종류를 안 봐도 모양이 분기다", () => {
    expect(basisText(row({ basis_kind: '분기', basis: '2026Q2' }))).toBe('2026년 2분기');
    expect(basisText(row({ basis_kind: '분기', basis: '2026Q4' }))).toBe('2026년 4분기');
  });

  it("서울시 분기 표기 '20262'(Q 없는 다섯 자리)는 '2026Q2' 와 **같은 글**이다 (결정 0033)", () => {
    for (const q of ['1', '2', '3', '4']) {
      expect(basisText(row({ basis_kind: '분기', basis: `2026${q}` }))).toBe(
        basisText(row({ basis_kind: '분기', basis: `2026Q${q}` })),
      );
    }
    expect(basisText(row({ basis_kind: '분기', basis: '20262' }))).toBe('2026년 2분기');
  });

  it("⛔ 여섯 자리 '202606' 은 다섯 자리 분기 갈래에 안 걸린다 — 계약월은 여전히 달이다", () => {
    expect(basisText(row({ basis_kind: '계약월', basis: '202603' }))).toBe('2026년 3월');
    expect(basisText(row({ basis_kind: '기준월', basis: '202601' }))).toBe('2026년 1월');
    // 분기 숫자가 1~4 밖인 다섯 자리는 해석하지 않는다.
    expect(basisText(row({ basis_kind: '분기', basis: '20265' }))).toBe('20265');
  });

  it('날짜는 연·월·일로 적는다 — 0 을 떼고 사람 말로', () => {
    expect(basisText(row({ basis_kind: '고시일', basis: '2026-01-01' }))).toBe('2026년 1월 1일');
    expect(basisText(row({ basis_kind: '수집일', basis: '2026-08-27' }))).toBe('2026년 8월 27일');
    expect(basisText(row({ basis_kind: '적재일', basis: '2026-12-31' }))).toBe('2026년 12월 31일');
  });

  it('⛔ 값이 없으면 "자료 없음" — 줄을 빼지 않는다', () => {
    expect(basisText(row({ basis: null }))).toBe('자료 없음');
    expect(basisText(row({ basis: '' }))).toBe('자료 없음');
    expect(basisText(row({ basis: '   ' }))).toBe('자료 없음');
  });

  it('⛔ 모양이 낯설면 원본을 그대로 적는다 — 틀린 분기를 말하는 것보다 낫다', () => {
    expect(basisText(row({ basis_kind: '분기', basis: '알 수 없음' }))).toBe('알 수 없음');
    // 달이 13 이면 해석하지 않는다(잘못된 값을 그럴듯하게 만들지 않는다).
    expect(basisText(row({ basis_kind: '계약월', basis: '202613' }))).toBe('202613');
    expect(basisText(row({ basis_kind: '고시일', basis: '2026-13-01' }))).toBe('2026-13-01');
  });

  it('앞뒤 공백은 털어낸다 — 서버가 char 칸을 그대로 주면 공백이 붙는다', () => {
    expect(basisText(row({ basis_kind: '분기', basis: ' 202606 ' }))).toBe('2026년 2분기');
  });

  it("필지 공시 연도 '2026'(네 자리)은 '2026년'으로 적는다 (2026-10-12b)", () => {
    expect(basisText(row({ basis_kind: '공시 연도', basis: '2026' }))).toBe('2026년');
    expect(basisText(row({ basis_kind: '공시 연도', basis: '2018' }))).toBe('2018년');
    // 종류와 무관하게 모양으로 가른다 — 네 자리 연도는 다른 갈래와 겹치지 않는다.
    expect(basisText(row({ basis_kind: '분기', basis: '2026' }))).toBe('2026년');
  });

  it('⛔ 네 자리가 아닌 숫자는 연도 갈래에 안 걸린다 — 원본 그대로이거나 원래 갈래 그대로', () => {
    expect(basisText(row({ basis_kind: '공시 연도', basis: '26' }))).toBe('26');
    expect(basisText(row({ basis_kind: '공시 연도', basis: '202' }))).toBe('202');
    expect(basisText(row({ basis_kind: '공시 연도', basis: '2026년' }))).toBe('2026년');
    expect(basisText(row({ basis_kind: '공시 연도', basis: '02026' }))).toBe('02026');
    // 기존 꼴(분기·달·날짜)은 결과가 그대로다.
    expect(basisText(row({ basis_kind: '분기', basis: '20262' }))).toBe('2026년 2분기');
    expect(basisText(row({ basis_kind: '계약월', basis: '202606' }))).toBe('2026년 6월');
    expect(basisText(row({ basis_kind: '고시일', basis: '2026-01-01' }))).toBe('2026년 1월 1일');
  });
});

describe('nextText — 다음 갱신 예정', () => {
  /**
   * ⛔ 오늘은 늘 **못 박아** 넣는다. 실제 오늘에 기대면 날이 흐르는 것만으로 시험이 빨개진다
   *    (2026-10-31 이 지나는 순간 '무렵'만 기대하던 단언이 깨진다).
   */
  const TODAY = '2026-10-01';

  it("날짜가 있으면 '무렵'을 붙인다 — 약속된 날이 아니라 계산한 예정일이다", () => {
    expect(nextText(row({ next_expected: '2026-10-31' }), TODAY)).toBe('2026년 10월 31일 무렵');
    expect(nextText(row({ next_expected: '2027-03-31' }), TODAY)).toBe('2027년 3월 31일 무렵');
  });

  it('⛔ 예정일이 지났으면 지났다고 적는다 — 날짜는 그대로, 사실만 덧붙인다', () => {
    expect(nextText(row({ next_expected: '2026-10-31' }), '2026-11-01')).toBe(
      '2026년 10월 31일 무렵 — 지났습니다, 갱신\u00a0전',
    );
    // 해를 넘겨도 같다(글자 비교가 날짜 비교와 같은 모양일 때만 비교한다).
    expect(nextText(row({ next_expected: '2026-12-31' }), '2027-01-01')).toBe(
      '2026년 12월 31일 무렵 — 지났습니다, 갱신\u00a0전',
    );
  });

  it('경계 — 전날·당일은 안 지났고, 다음 날부터 지났다', () => {
    const r = row({ next_expected: '2026-10-31' });
    expect(nextText(r, '2026-10-30')).toBe('2026년 10월 31일 무렵');
    // 당일은 아직이다 — 그날 안에 올라올 수 있다.
    expect(nextText(r, '2026-10-31')).toBe('2026년 10월 31일 무렵');
    expect(nextText(r, '2026-11-01')).toBe('2026년 10월 31일 무렵 — 지났습니다, 갱신\u00a0전');
  });

  it('⛔ 없으면 "정해진 주기 없음" — 아무 날짜나 적으면 "늦었다"는 거짓 신호가 뜬다', () => {
    expect(nextText(row({ next_expected: null }), TODAY)).toBe('정해진 주기 없음');
    expect(nextText(row({ next_expected: '' }), TODAY)).toBe('정해진 주기 없음');
    // 아주 먼 미래의 오늘이어도 '지났다'를 붙이지 않는다 — 비교할 날짜가 없다.
    expect(nextText(row({ next_expected: null }), '2099-12-31')).toBe('정해진 주기 없음');
  });

  it('모양이 낯설면 원본 그대로 — 지남 판정도 하지 않는다', () => {
    expect(nextText(row({ next_expected: '언젠가' }), TODAY)).toBe('언젠가');
    expect(nextText(row({ next_expected: '2026-10-99' }), TODAY)).toBe('2026-10-99');
    // 글자로는 '오늘'보다 앞서지만 날짜가 아니므로 '지났다'를 붙이지 않는다.
    expect(nextText(row({ next_expected: '2000-13-01' }), TODAY)).toBe('2000-13-01');
  });

  it('오늘이 날짜 모양이 아니면 지남 판정을 하지 않는다', () => {
    expect(nextText(row({ next_expected: '2026-08-31' }), '')).toBe('2026년 8월 31일 무렵');
    expect(nextText(row({ next_expected: '2026-08-31' }), '20261001')).toBe(
      '2026년 8월 31일 무렵',
    );
  });
});

describe('seoulToday — 한국 날짜의 오늘', () => {
  it('⛔ UTC 15:00 이 한국 다음 날 0시다 — 로컬 시각대가 아니라 한국 날짜로 자른다', () => {
    expect(seoulToday(new Date('2026-10-31T14:59:59Z'))).toBe('2026-10-31');
    expect(seoulToday(new Date('2026-10-31T15:00:00Z'))).toBe('2026-11-01');
  });

  it('한국 새벽(UTC 전날 밤)에 어제가 되지 않는다', () => {
    // 한국 2026-11-01 08:59 = UTC 2026-10-31 23:59 — UTC 로 자르면 31일이 된다.
    expect(seoulToday(new Date('2026-10-31T23:59:00Z'))).toBe('2026-11-01');
  });

  it("'YYYY-MM-DD' 모양으로 0 을 채운다 — nextText 가 글자로 비교하는 전제다", () => {
    expect(seoulToday(new Date('2026-01-04T03:00:00Z'))).toBe('2026-01-04');
    expect(seoulToday(new Date('2026-12-31T15:00:00Z'))).toBe('2027-01-01');
  });
});

describe('isDataFreshnessList — 서버 응답의 모양', () => {
  it('제대로 된 목록은 통과한다', () => {
    expect(isDataFreshnessList([row(), row({ src: '실거래 (매매)' })])).toBe(true);
  });

  it('⛔ basis·next_expected 가 null 인 줄도 통과한다 — 둘 다 정상값이다', () => {
    expect(isDataFreshnessList([row({ basis: null, next_expected: null })])).toBe(true);
    expect(isDataFreshnessRow(row({ basis: null }))).toBe(true);
  });

  it('빈 배열도 모양으로는 맞다(그때 화면이 표를 생략한다)', () => {
    expect(isDataFreshnessList([])).toBe(true);
  });

  it('엉뚱한 답은 거절한다 — 마이그레이션 전 라이브의 오류 객체가 이 모양이다', () => {
    expect(isDataFreshnessList({ code: 'PGRST202', message: 'function does not exist' })).toBe(
      false,
    );
    expect(isDataFreshnessList(null)).toBe(false);
    expect(isDataFreshnessList([null])).toBe(false);
    expect(isDataFreshnessList(['점포'])).toBe(false);
    // 있어야 할 칸이 빠진 줄 — 하나라도 빠지면 렌더에서 터진다.
    expect(isDataFreshnessList([{ src: '점포', basis_kind: '분기' }])).toBe(false);
    // 종류가 숫자로 오면 화면이 그대로 그리다 이상해진다.
    expect(isDataFreshnessList([{ ...row(), basis_kind: 2 }])).toBe(false);
    expect(isDataFreshnessList([{ ...row(), basis: 202606 }])).toBe(false);
    expect(isDataFreshnessList([{ ...row(), cadence: null }])).toBe(false);
  });
});

/* ── 카드마다 '자료 이름 + 날짜' 한 줄 (S3 · 👤 2026-10-16) ─────────────────────────────── */

/** 2026-10-16 운영 `get_data_freshness` 의 줄(기준값만 — 날짜 줄은 next_expected·cadence 를 안 쓴다) · 결정 0041 로 성적표 줄을 뺀 열 줄. */
function rows1016(): DataFreshnessRow[] {
  const r = (src: string, basis_kind: string, basis: string | null) =>
    row({ src, basis_kind, basis, next_expected: null, cadence: '-' });
  return [
    r('점포·업종 (상권정보)', '분기', '202606'),
    r('실거래 (매매)', '계약월', '202610'),
    r('건축물대장', '판', '202608'),
    r('상권 경계', '계산일', '2026-09-08'),
    r('LH 상가 공고', '수집일', '2026-10-12'),
    r('건축 인허가', '기준월', '202608'),
    r('국세청 기준시가', '고시일', '2026-01-01'),
    r('상권 임대 동향 (부동산원)', '분기', '2026Q2'),
    r('필지 (토지 특성)', '공시 연도', '2026'),
    r('상권 개업·폐업 (서울시)', '분기', '20262'),
    // 결정 0045 — 서울 상권 4종 세 줄(정본 get_data_freshness 13~15번 줄의 글 꼴 그대로).
    r('상권 추정매출 (서울시)', '분기', '20262'),
    r('상권 길단위인구 (서울시)', '분기', '20262'),
    r('상권 상주·직장인구 (서울시)', '값이 바뀐 분기', '상주 2023년 4분기, 직장 2024년 4분기'),
  ];
}

/**
 * 카드마다 기대하는 한 줄 — 👤 시안(SFpojgaYvHEdRnbx8ZTfQM)의 예시값(10-16 운영 값일 때) + 👤 10-16 보완 결정
 * B1(실거래 끝말 「(최근 두 달은 신고 중)」) · B3(층 목록에 실거래).
 * ⛔ 줄이 없는 카드 둘 — 빈 카드 이 자리 가게 이력(결정 ②) + LH 공고(B2). 업종별 추정매출·상권 인구는 결정 0045 PR③ 부터
 *    서울시 자료 줄이 선다(서울 밖 건물의 빈 카드는 `EmptySection` 이 줄을 빼 그린다).
 */
const TX_PIECE = '국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중)';

const EXPECTED_LINES: Record<string, string | null> = {
  district: '자료: 상권 경계 2026년 9월 8일 계산',
  floors: '자료: 건축물대장 2026년 8월 판 · 상권정보 2026년 2분기 · 국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중)',
  industry: '자료: 상권정보 2026년 2분기 · 건축 인허가 2026년 8월 기준',
  tx: '자료: 국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중)',
  floorgap:
    '자료: 국세청 기준시가 2026년 1월 1일 고시 · 국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중) · 부동산원 2026년 2분기 조사',
  rent: '자료: 부동산원 2026년 2분기 조사',
  openclose: '자료: 서울시 상권분석서비스 2026년 2분기',
  sales: '자료: 서울시 상권분석서비스 2026년 2분기',
  pop: '자료: 서울시 상권분석서비스 2026년 2분기 · 서울시 상주·직장인구 상주 2023년 4분기, 직장 2024년 4분기 값',
  history: null,
  lhNotice: null,
  txFlow: '자료: 국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중)',
};

describe('cardSourceLine — 카드 제목 아래 날짜 줄 (S3)', () => {
  const ALL_PLANS: Record<string, SectionPlan> = { ...SECTION_PLAN, ...ENTRY_SECTION_PLAN };

  it('카드 열두 장 전부 — 날짜 줄 카드 열 장은 결정 글 그대로, 둘(빈 카드 가게 이력 · LH)은 줄이 없다', () => {
    // 표가 카드를 빠짐없이 덮는다(카드가 새로 생기면 여기 기대 줄을 먼저 정한다).
    expect(Object.keys(EXPECTED_LINES).sort()).toEqual(Object.keys(ALL_PLANS).sort());
    for (const [key, plan] of Object.entries(ALL_PLANS)) {
      expect(cardSourceLine(plan.sources, rows1016()), key).toBe(EXPECTED_LINES[key]);
    }
    const withLine = Object.values(ALL_PLANS).filter((p) => cardSourceLine(p.sources, rows1016()));
    expect(withLine).toHaveLength(10);
  });

  it('종류별 끝말 — 판·계약분까지(최근 두 달은 신고 중)·계산·기준·고시·조사, 상권정보·서울시 분기는 끝말 없음', () => {
    const one = (k: keyof typeof CARD_SOURCES) => cardSourceLine([k], rows1016());
    expect(one('ledger')).toBe('자료: 건축물대장 2026년 8월 판');
    expect(one('tx')).toBe('자료: 국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중)');
    expect(one('district')).toBe('자료: 상권 경계 2026년 9월 8일 계산');
    expect(one('permit')).toBe('자료: 건축 인허가 2026년 8월 기준');
    expect(one('nts')).toBe('자료: 국세청 기준시가 2026년 1월 1일 고시');
    expect(one('rone')).toBe('자료: 부동산원 2026년 2분기 조사');
    expect(one('sangkwon')).toBe('자료: 상권정보 2026년 2분기');
    expect(one('openclose')).toBe('자료: 서울시 상권분석서비스 2026년 2분기');
  });

  it('⛔ 날짜는 서버 값에서만 — 새 판이 들어오면 줄이 저절로 바뀐다', () => {
    const next = rows1016().map((r) => (r.src === '건축물대장' ? { ...r, basis: '202609' } : r));
    expect(cardSourceLine(SECTION_PLAN.floors.sources, next)).toBe(
      '자료: 건축물대장 2026년 9월 판 · 상권정보 2026년 2분기 · 국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중)',
    );
  });

  it('⛔ 표를 못 받았으면(null) 줄이 없다 — 모르는 것을 \'자료 없음\'이라 적지 않는다', () => {
    expect(cardSourceLine(SECTION_PLAN.floors.sources, null)).toBeNull();
    // 양성 대조 — 같은 카드가 표를 받으면 줄이 있다(위 null 이 '늘 null' 이라서가 아니다).
    expect(cardSourceLine(SECTION_PLAN.floors.sources, rows1016())).not.toBeNull();
  });

  it('⛔ 서버 표에 그 자료 줄이 없으면 그 조각만 빠지고, 하나도 안 남으면 줄이 없다', () => {
    const noLedger = rows1016().filter((r) => r.src !== '건축물대장');
    expect(cardSourceLine(SECTION_PLAN.floors.sources, noLedger)).toBe(
      '자료: 상권정보 2026년 2분기 · 국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중)',
    );
    expect(cardSourceLine(SECTION_PLAN.district.sources, noLedger)).toBe(
      '자료: 상권 경계 2026년 9월 8일 계산',
    );
    expect(cardSourceLine(SECTION_PLAN.floors.sources, [])).toBeNull();
  });

  it('줄은 있는데 기준값이 비었으면 맨 아래 표처럼 \'자료 없음\'(끝말은 안 붙인다)', () => {
    const empty = rows1016().map((r) => (r.src === '건축물대장' ? { ...r, basis: null } : r));
    expect(cardSourceLine(SECTION_PLAN.floors.sources, empty)).toBe(
      '자료: 건축물대장 자료 없음 · 상권정보 2026년 2분기 · 국토부 실거래 2026년 10월 계약분까지 (최근 두 달은 신고 중)',
    );
  });

  it('빈 카드 가게 이력(결정 ②)과 LH 공고(B2)는 자료 칸이 아예 없다', () => {
    const none: SectionPlan[] = [SECTION_PLAN.history, ENTRY_SECTION_PLAN.lhNotice];
    for (const plan of none) {
      expect(plan, plan.title).not.toHaveProperty('sources');
      expect(cardSourceLine(plan.sources, rows1016())).toBeNull();
    }
  });

  it('업종별 추정매출·상권 인구(결정 0045 PR③)는 서울시 자료 세 줄을 쓴다 — 서버 src 글자로 찾는다', () => {
    expect(SECTION_PLAN.sales.sources).toEqual(['sales']);
    expect(SECTION_PLAN.pop.sources).toEqual(['pop_flow', 'pop_people']);
    expect(CARD_SOURCES.sales.src).toBe('상권 추정매출 (서울시)');
    expect(CARD_SOURCES.pop_flow.src).toBe('상권 길단위인구 (서울시)');
    expect(CARD_SOURCES.pop_people.src).toBe('상권 상주·직장인구 (서울시)');
    // ⛔ 날짜 줄에 출처 이름이 두 번 나오지 않는다(길단위인구 조각 label 과 다른 이름 · 메인 PR③ 결정).
    expect(CARD_SOURCES.pop_people.label).not.toBe(CARD_SOURCES.pop_flow.label);
    const line = cardSourceLine(SECTION_PLAN.pop.sources, rows1016()) ?? '';
    expect(line.split('서울시 상권분석서비스').length - 1).toBe(1);
    // 양성 대조 — 서버 표에 그 줄이 없으면 그 조각만 빠진다(상주·직장 줄만 빠진 표).
    const noPeople = rows1016().filter((r) => r.src !== '상권 상주·직장인구 (서울시)');
    expect(cardSourceLine(SECTION_PLAN.pop.sources, noPeople)).toBe('자료: 서울시 상권분석서비스 2026년 2분기');
  });

  it('실거래 조각은 어느 카드에서나 같은 글이다(B1 · 실거래 기록·층별 공표값·동네 흐름·층 목록)', () => {
    const plans: SectionPlan[] = [
      SECTION_PLAN.tx,
      SECTION_PLAN.floorgap,
      SECTION_PLAN.floors,
      ENTRY_SECTION_PLAN.txFlow,
    ];
    for (const plan of plans) expect(cardSourceLine(plan.sources, rows1016()), plan.title).toContain(TX_PIECE);
    // 맨 아래 표 글은 그대로(B1) — 끝말은 카드 줄에만 붙는다.
    expect(basisText(rows1016()[1])).toBe('2026년 10월');
  });
});

/**
 * 정본 `supabase/schema.sql` 의 `get_data_freshness()` 본문에서 **select 문 안의 자료 이름**(둘째 칸 글자)만 뽑는다.
 *
 * ⛔ `--` 주석을 먼저 지운다 — 주석에 같은 글자가 남아 있어도 통과하면 정본이 바뀐 것을 못 본다(#309 교훈).
 * 못 보는 것: 자료 이름을 문자열 잇기·함수 호출로 만드는 꼴(지금 정본에는 없다) · 글자 안의 `--`.
 */
function serverSrcLabels(sql: string): string[] {
  const start = sql.indexOf('create or replace function get_data_freshness()');
  if (start < 0) return [];
  const end = sql.indexOf('$$;', start);
  const body = sql
    .slice(start, end < 0 ? undefined : end)
    .split('\n')
    .map((line) => line.replace(/--.*$/, ''))
    .join('\n');
  return [...body.matchAll(/\bselect\s+\d+\s*(?:as\s+ord\s*)?,\s*'([^']+)'/gi)].map((m) => m[1]);
}

describe('카드 자료 이름 ↔ 정본 서버 함수의 자료 이름 (S3)', () => {
  it('양성 대조 — 흔한 꼴·변형 꼴은 잡고, 주석에만 있는 글자는 안 잡는다', () => {
    const sample = [
      'create or replace function get_data_freshness()',
      'as $$',
      "  select 1 as ord,",
      "         '가짜 자료'::text as src,",
      "  union all select 2, '두번째 자료', '계약월'",
      "  -- select 3, '주석 자료', '판'",
      "  union all select 4 , '넷째 자료' -- 끝 주석 '꼬리'",
      '$$;',
      "select 5, '함수 밖 자료'",
    ].join('\n');
    expect(serverSrcLabels(sample)).toEqual(['가짜 자료', '두번째 자료', '넷째 자료']);
    expect(serverSrcLabels("select 1, '함수 없음'")).toEqual([]);
  });

  it('정본의 자료 이름 열다섯 개 = 카드 자료 표 열셋 + 카드에 안 붙는 둘(필지 · LH) — 성적표 줄은 결정 0041 로 뺐고 대전시 동네 폐업은 결정 0044, 서울 상권 4종 세 줄은 결정 0045, 가게 이력 줄은 결정 0045 PR④ 로 더했다', () => {
    const sql = readFileSync('supabase/schema.sql', 'utf8');
    const server = serverSrcLabels(sql);
    expect(server).toHaveLength(15);
    expect(server).not.toContain('참고 시세 성적표');
    const ours = [
      ...Object.values(CARD_SOURCES).map((s) => s.src),
      '필지 (토지 특성)',
      'LH 상가 공고',
    ];
    expect([...server].sort()).toEqual([...ours].sort());
  });
});
