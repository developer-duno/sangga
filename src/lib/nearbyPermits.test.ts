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
      // 서버가 stale_cnt 를 안 주는 응답이다(2026-09-05b 이전 라이브) — 그 조각만 비운다.
      stale: null,
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

describe('toPermitLine — 오래 멈춰 있는 것 (2026-09-05b)', () => {
  /**
   * 이 조각은 **줄 전체와 운명을 같이하지 않는다.** 전체·착공은 문장의 뼈대라 어긋나면
   * 문장이 통째로 거짓이 되지만, 이 수는 덧붙이는 한 문장이라 빼도 남는 말이 참이다.
   */
  it('서버가 주면 그대로 나른다', () => {
    expect(toPermitLine(row({ total_cnt: 7, started_cnt: 2, stale_cnt: 3 }))?.stale).toBe(3);
    // 0 도 값이다 — '멈춘 것이 없다'는 사실이라 화면이 그 문장만 안 적는다.
    expect(toPermitLine(row({ total_cnt: 7, started_cnt: 2, stale_cnt: 0 }))?.stale).toBe(0);
  });

  it('서버가 그 칸을 안 주면 null 이다 (옛 라이브가 새 화면을 안 깨뜨린다)', () => {
    // 2026-09-05b 를 아직 안 올린 DB 의 응답이다. 나머지 줄은 그대로 서야 한다.
    const line = toPermitLine(row({ total_cnt: 7, started_cnt: 2 }));
    expect(line?.stale).toBeNull();
    expect(line?.permitOnly).toBe(5);
  });

  it("'허가만'보다 크거나 음수면 그 조각만 버린다 (줄은 그대로 선다)", () => {
    // 착공한 것은 안 세는 수라 permitOnly(=5)를 넘을 수 없다. 넘게 왔다면 서버와 화면이
    // 서로 다른 것을 세고 있다는 뜻이므로 적지 않는다 — 그래도 전체·착공은 사실이다.
    const over = toPermitLine(row({ total_cnt: 7, started_cnt: 2, stale_cnt: 6 }));
    expect(over?.stale).toBeNull();
    expect(over?.total).toBe(7);
    expect(toPermitLine(row({ stale_cnt: -1 }))?.stale).toBeNull();
    expect(toPermitLine(row({ stale_cnt: '1' }))?.stale).toBeNull();
  });

  it('전체가 음수면 줄째로 버린다 (조각만 비우는 것으로 넘어가지 않는다)', () => {
    // ⛔ 위 세 경우와 갈리는 자리다. 뼈대가 틀리면 덧붙이는 문장만 빼서 될 일이 아니다.
    expect(toPermitLine(row({ total_cnt: -3, started_cnt: 0 }))).toBeNull();
    expect(toPermitLine(row({ total_cnt: -3, started_cnt: 0, stale_cnt: 0 }))).toBeNull();
  });
});

describe('toPermitLine — 응답 껍데기', () => {
  it('한 행짜리 목록으로 와도 객체로 와도 같게 읽는다', () => {
    // returns table 이면 [{…}], returns json 이면 {…} 로 온다. 어느 쪽인지는 라이브에서만
    // 드러나므로 둘 다 받는다.
    expect(toPermitLine([row()])).toEqual(toPermitLine(row()));
  });
});
