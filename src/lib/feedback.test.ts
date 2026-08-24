import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * 창고로 짧은 글 한 통을 보내는 길 테스트(2026-08-24b).
 *
 * 이 길에서 조용히 틀리기 쉬운 것 셋을 특히 지킨다:
 *  ① **인자 이름**을 `p_kind`·`p_body`·`p_context` 로 보내는가 — 흉내(mock)는 인자 이름을
 *     안 보므로 `{ kind: … }` 로 잘못 불러도 여기는 초록이고 **라이브에서만** PGRST202 가
 *     난다. 그래서 이름을 눈으로 확인하는 검사를 따로 둔다.
 *  ② 실패를 성공이라 말하지 않는가 — `data === true` 가 아니면 전부 실패다. 서버가 함수를
 *     못 찾아도(마이그레이션 전) 화면은 "보냈습니다"를 띄우면 안 된다.
 *  ③ 오류 보고가 **한 방문에 한 번**인가 — 렌더 중 오류는 되풀이되므로 빗장이 없으면
 *     한 번의 사고가 창고를 채운다.
 */

const rpcCalls: Array<{ fn: string; args: unknown }> = [];
const response = { data: null as unknown, error: null as unknown };
/** true 면 rpc 가 아예 던진다 — 네트워크 두절을 흉내 낸다. */
let rpcThrows = false;

vi.mock('./supabase', () => ({
  supabase: {
    rpc: (fn: string, args?: unknown) => {
      rpcCalls.push({ fn, args });
      if (rpcThrows) return Promise.reject(new Error('네트워크 없음'));
      return Promise.resolve(response);
    },
  },
}));

beforeEach(() => {
  rpcCalls.length = 0;
  response.data = true;
  response.error = null;
  rpcThrows = false;
  // 모듈 수준 빗장(errorAlreadyReported)을 되돌린다 — 테스트마다 새 방문이어야 한다.
  vi.resetModules();
});

describe('submitFeedback', () => {
  it('서버 인자 이름을 p_kind·p_body·p_context 로 보낸다', async () => {
    const { submitFeedback } = await import('./feedback');
    await submitFeedback('opinion', '3층이 안 보여요', { bld_id: 'B1' });

    expect(rpcCalls).toHaveLength(1);
    expect(rpcCalls[0].fn).toBe('submit_feedback');
    // ⚠️ 이름을 하나하나 본다. 이 줄이 라이브 PGRST202 를 막는 유일한 자리다.
    expect(rpcCalls[0].args).toEqual({
      p_kind: 'opinion',
      p_body: '3층이 안 보여요',
      p_context: { bld_id: 'B1' },
    });
  });

  it('딸림 정보가 없으면 p_context 로 null 을 보낸다', async () => {
    const { submitFeedback } = await import('./feedback');
    await submitFeedback('opinion', '한마디');
    expect((rpcCalls[0].args as Record<string, unknown>).p_context).toBeNull();
  });

  it('서버가 true 를 주면 true', async () => {
    const { submitFeedback } = await import('./feedback');
    response.data = true;
    await expect(submitFeedback('opinion', '한마디')).resolves.toBe(true);
  });

  it('서버가 false 를 주면(상한·모양 불일치) false', async () => {
    const { submitFeedback } = await import('./feedback');
    response.data = false;
    await expect(submitFeedback('opinion', '한마디')).resolves.toBe(false);
  });

  it('서버가 오류를 주면 false — 함수가 없을 때(PGRST202) 성공이라 말하지 않는다', async () => {
    const { submitFeedback } = await import('./feedback');
    response.data = null;
    response.error = { code: 'PGRST202', message: 'function not found' };
    await expect(submitFeedback('opinion', '한마디')).resolves.toBe(false);
  });

  it('true 가 아닌 뜻밖의 값이 와도 false — 참 같은 값을 참으로 읽지 않는다', async () => {
    const { submitFeedback } = await import('./feedback');
    response.data = 'ok';
    await expect(submitFeedback('opinion', '한마디')).resolves.toBe(false);
  });

  it('네트워크가 끊겨도 던지지 않고 false', async () => {
    const { submitFeedback } = await import('./feedback');
    rpcThrows = true;
    await expect(submitFeedback('opinion', '한마디')).resolves.toBe(false);
  });
});

describe('reportClientError', () => {
  it('한 방문에 한 번만 보낸다 — 되풀이되는 렌더 오류가 창고를 채우지 않게', async () => {
    const { reportClientError } = await import('./feedback');

    await expect(reportClientError(new Error('첫 번째'))).resolves.toBe(true);
    await expect(reportClientError(new Error('두 번째'))).resolves.toBe(false);
    await expect(reportClientError(new Error('세 번째'))).resolves.toBe(false);

    expect(rpcCalls).toHaveLength(1);
  });

  it('보내기가 실패해도 빗장은 걸린 채다 — 실패가 되풀이되면 그것대로 폭주한다', async () => {
    const { reportClientError } = await import('./feedback');
    rpcThrows = true;

    await expect(reportClientError(new Error('첫 번째'))).resolves.toBe(false);
    rpcThrows = false;
    await expect(reportClientError(new Error('두 번째'))).resolves.toBe(false);

    // 두 번째는 아예 보내지도 않았다.
    expect(rpcCalls).toHaveLength(1);
  });

  it('kind 는 error 로, 브라우저·주소를 함께 담는다', async () => {
    const { reportClientError } = await import('./feedback');
    await reportClientError(new Error('터짐'), { area: '층별 화면' });

    const args = rpcCalls[0].args as Record<string, unknown>;
    expect(args.p_kind).toBe('error');
    expect(String(args.p_body)).toContain('터짐');

    const ctx = args.p_context as Record<string, unknown>;
    expect(ctx.area).toBe('층별 화면');
    expect(ctx.ua).toEqual(expect.any(String));
    expect(ctx.url).toEqual(expect.any(String));
  });

  it('던져진 것이 Error 가 아니어도 보고가 터지지 않는다', async () => {
    const { reportClientError } = await import('./feedback');
    await expect(reportClientError({ weird: true })).resolves.toBe(true);
    expect(String((rpcCalls[0].args as Record<string, unknown>).p_body)).toContain('weird');
  });

  it('본문이 빈 것은 보내지 않고, 빗장도 걸지 않는다', async () => {
    const { reportClientError } = await import('./feedback');

    await expect(reportClientError('')).resolves.toBe(false);
    expect(rpcCalls).toHaveLength(0);

    // ⛔ 여기가 핵심 — 남길 것이 없는 오류 하나가 빗장만 걸어 놓고 물러나면
    //    그 뒤의 **진짜 오류를 영영 못 보내게** 된다.
    await expect(reportClientError(new Error('진짜 오류'))).resolves.toBe(true);
    expect(rpcCalls).toHaveLength(1);
  });
});

describe('describeError', () => {
  it('Error 는 이름·메시지를 앞에 둔다 — 서버가 2,000자에서 잘라도 무엇이 터졌는지는 남는다', async () => {
    const { describeError } = await import('./feedback');
    const out = describeError(new TypeError('x is not a function'));
    expect(out.startsWith('TypeError: x is not a function')).toBe(true);
  });

  it('문자열은 그대로', async () => {
    const { describeError } = await import('./feedback');
    expect(describeError('그냥 문자열')).toBe('그냥 문자열');
  });

  it('순환 참조가 있어도 던지지 않는다', async () => {
    const { describeError } = await import('./feedback');
    const circular: Record<string, unknown> = {};
    circular.self = circular;
    expect(() => describeError(circular)).not.toThrow();
    expect(describeError(circular)).toEqual(expect.any(String));
  });

  it('undefined 도 무언가는 남긴다', async () => {
    const { describeError } = await import('./feedback');
    expect(describeError(undefined)).toEqual(expect.any(String));
  });
});
