import { describe, it, expect } from 'vitest';

import {
  basisText,
  isDataFreshnessList,
  isDataFreshnessRow,
  nextText,
  seoulToday,
} from './dataFreshness';
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
