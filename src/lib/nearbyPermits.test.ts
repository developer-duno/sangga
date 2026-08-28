import { describe, it, expect } from 'vitest';
import { toPermitLine } from './nearbyPermits';

/**
 * 둘레의 인허가 한 줄(순수 계산).
 *
 * 여기서 지키는 것 셋:
 *  ① **산수** — '허가만'은 전체에서 착공을 뺀 값이다. 이 뺄셈이 틀리면 화면의 두 수를
 *     더해도 전체가 안 나오는데, 사람은 그걸 "우리 자료가 이상하다"로 읽는다.
 *  ② **안 적는 경우** — 0동·모양 뜻밖·기준월 없음·쪼갤 수 없는 수. 전부 null 이어야
 *     화면이 그 줄만 조용히 뺀다("0동"이라 적으면 없는 사실이 생긴다).
 *  ③ **응답 껍데기** — 서버가 한 행짜리 목록으로 줄지 객체로 줄지는 함수를 어떻게 쓰느냐에
 *     달렸고 그 차이는 라이브에서만 드러난다. 둘 다 받는지 여기서 못 박는다.
 */

function row(over: Record<string, unknown> = {}) {
  return { total_cnt: 3, started_cnt: 2, base_ym: '202607', ...over };
}

describe('toPermitLine — 산수', () => {
  it("'허가만'은 전체에서 착공을 뺀 값이다", () => {
    expect(toPermitLine(row({ total_cnt: 7, started_cnt: 2 }))).toEqual({
      total: 7,
      started: 2,
      permitOnly: 5,
      baseLabel: '2026년 7월',
    });
  });

  it('전부 착공했으면 허가만은 0이다 (그래도 줄은 낸다)', () => {
    // 0 인 것은 '허가만' 칸뿐이고 전체는 5동이다 — 줄째로 버리면 있는 사실이 사라진다.
    expect(toPermitLine(row({ total_cnt: 5, started_cnt: 5 }))?.permitOnly).toBe(0);
  });

  it('아직 아무것도 착공 안 했으면 허가만이 전체와 같다', () => {
    expect(toPermitLine(row({ total_cnt: 4, started_cnt: 0 }))?.permitOnly).toBe(4);
  });

  it('기준월을 사람 말로 푼다 (화면이 연·월을 글자로 박지 않는다)', () => {
    expect(toPermitLine(row({ base_ym: '202601' }))?.baseLabel).toBe('2026년 1월');
    expect(toPermitLine(row({ base_ym: '202512' }))?.baseLabel).toBe('2025년 12월');
  });
});

describe('toPermitLine — 안 적는 경우', () => {
  it('0동이면 줄을 안 만든다 ("0동"이라 적으면 없는 사실이 생긴다)', () => {
    expect(toPermitLine(row({ total_cnt: 0, started_cnt: 0 }))).toBeNull();
  });

  it('함수가 아직 없을 때의 오류 객체를 그리지 않는다', () => {
    expect(toPermitLine({ code: 'PGRST202', message: 'function does not exist' })).toBeNull();
    expect(toPermitLine(null)).toBeNull();
    expect(toPermitLine(undefined)).toBeNull();
    expect(toPermitLine([])).toBeNull();
  });

  it('칸이 숫자가 아니면 그리지 않는다 (렌더 중에 터지면 화면이 하얘진다)', () => {
    expect(toPermitLine(row({ total_cnt: '3' }))).toBeNull();
    expect(toPermitLine(row({ started_cnt: null }))).toBeNull();
  });

  it('착공이 전체보다 크면 줄째로 버린다 (허가만 -1동을 적지 않는다)', () => {
    expect(toPermitLine(row({ total_cnt: 2, started_cnt: 3 }))).toBeNull();
    expect(toPermitLine(row({ total_cnt: 2, started_cnt: -1 }))).toBeNull();
  });

  it('기준월을 못 읽으면 개수도 안 적는다 (언제 것인지 모르는 수는 근거가 없다)', () => {
    expect(toPermitLine(row({ base_ym: '' }))).toBeNull();
    expect(toPermitLine(row({ base_ym: '2026-07' }))).toBeNull();
    expect(toPermitLine(row({ base_ym: '202613' }))).toBeNull();
    expect(toPermitLine(row({ base_ym: 202607 }))).toBeNull();
  });
});

describe('toPermitLine — 응답 껍데기', () => {
  it('한 행짜리 목록으로 와도 객체로 와도 같게 읽는다', () => {
    // returns table 이면 [{…}], returns json 이면 {…} 로 온다. 어느 쪽인지는 라이브에서만
    // 드러나므로 둘 다 받는다.
    expect(toPermitLine([row()])).toEqual(toPermitLine(row()));
  });
});
