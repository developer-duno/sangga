import { describe, it, expect } from 'vitest';
import { EMPTY_SUMMARY, emptyCardText } from './emptyCards';

/**
 * 빈 카드 셋의 글(결정 0036 결정 2 · 물결 1-B · 👤 문구 그대로).
 *
 * 여기서 특히 지키는 것
 *  ① 서울 건물은 셋 다 "지금은 비어 있음 — …" (👤 글자 그대로)
 *  ② 서울 밖 건물의 매출·유동인구는 "서울시 자료는 서울만 — ○○은 아직 받지 않았습니다" — 지역 이름은 표에서
 *  ③ 가게 이력은 지역과 무관하다(전국 점포 분기 자료로 채운다)
 *  ④ '공식 자료가 없다'류 말을 쓰지 않는다(결정 0036 표 1-B)
 */

const SEOUL = '1168010500101590000';
const DAEJEON = '3011010700108770000';
const DAEGU = '2711010700108770000';
const UNKNOWN = '9911010700108770000';

describe('emptyCardText — 서울 건물', () => {
  it('★ 셋 다 "지금은 비어 있음" 요약 + 👤 본문 글자 그대로', () => {
    expect(emptyCardText('sales', SEOUL)).toEqual({
      summary: '지금은 비어 있음',
      body: '지금은 비어 있음 — 서울시가 상권마다 공표하는 업종별 추정매출을 받으면 이 자리에 그대로 싣습니다',
    });
    expect(emptyCardText('pop', SEOUL)).toEqual({
      summary: '지금은 비어 있음',
      body: '지금은 비어 있음 — 상권 유동인구와 상권 안 상주 인구를 받으면 따로 줄로 싣습니다',
    });
    expect(emptyCardText('history', SEOUL)).toEqual({
      summary: '지금은 비어 있음',
      body: '지금은 비어 있음 — 분기마다 받는 점포 자료가 쌓이면 이 땅에 어떤 가게가 몇 분기 있었는지 보여 줍니다',
    });
  });
});

describe('emptyCardText — 서울 밖 건물', () => {
  it('★ 대전 매출·유동인구 = 결정 0036 표 1-B 글 · 요약은 그 뒷부분', () => {
    for (const key of ['sales', 'pop'] as const) {
      expect(emptyCardText(key, DAEJEON)).toEqual({
        summary: '대전은 아직 받지 않았습니다',
        body: '서울시 자료는 서울만 — 대전은 아직 받지 않았습니다',
      });
    }
  });

  it('★ 가게 이력은 대전도 서울과 같은 글(지역과 무관)', () => {
    expect(emptyCardText('history', DAEJEON)).toEqual(emptyCardText('history', SEOUL));
  });

  it('지역 이름은 표에서 고르고 조사는 받침대로 — 대구는 · 표에 없으면 이 지역은', () => {
    expect(emptyCardText('sales', DAEGU).summary).toBe('대구는 아직 받지 않았습니다');
    expect(emptyCardText('pop', UNKNOWN).body).toBe('서울시 자료는 서울만 — 이 지역은 아직 받지 않았습니다');
  });

  it('⛔ "공식 자료가 없다"류 단정을 쓰지 않는다 · 서울 밖 글에 "비어 있음"을 섞지 않는다', () => {
    for (const pnu of [SEOUL, DAEJEON, UNKNOWN]) {
      for (const key of ['sales', 'pop', 'history'] as const) {
        const { summary, body } = emptyCardText(key, pnu);
        for (const banned of ['공식 자료가 없', '자료가 존재하지', '정확하지 않을 수', '참고용']) {
          expect(`${summary} ${body}`).not.toContain(banned);
        }
      }
    }
    expect(emptyCardText('sales', DAEJEON).body).not.toContain(EMPTY_SUMMARY);
  });
});
