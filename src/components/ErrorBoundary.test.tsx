import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

/**
 * 안전망(ErrorBoundary) 테스트.
 *
 * 이 그물이 없던 시절의 증상은 **아무 증상도 없는 것**이었다 — 화면이 통째로 하얘지고,
 * 오류는 콘솔에만 남고, 서버가 없어 우리는 그런 일이 있었다는 사실조차 몰랐다.
 * 그래서 여기서 지키는 것은 셋이다:
 *  ① 터져도 화면에 **말이 남는가**(하얀 화면이 아닌가)
 *  ② 그 사실이 **창고로 가는가**(우리가 알 수 있는가)
 *  ③ 다시 시도로 **빠져나갈 길이 있는가**
 */

const reported: Array<{ error: unknown; context: unknown }> = [];

vi.mock('../lib/feedback', () => ({
  reportClientError: (error: unknown, context: unknown) => {
    reported.push({ error, context });
    return Promise.resolve(true);
  },
}));

const { ErrorBoundary } = await import('./ErrorBoundary');

/** 스위치를 켜면 렌더 도중에 터지는 자식. */
function Boom({ explode }: { explode: boolean }) {
  if (explode) throw new Error('렌더 중 폭발');
  return <p>정상 내용</p>;
}

let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  reported.length = 0;
  // 리액트는 잡힌 오류도 콘솔에 크게 찍는다 — 테스트 출력이 오류로 뒤덮이지 않게 가린다.
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  consoleError.mockRestore();
  cleanup();
});

describe('ErrorBoundary', () => {
  it('아무 일 없으면 자식을 그대로 보여준다', () => {
    render(
      <ErrorBoundary area="시험">
        <Boom explode={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText('정상 내용')).toBeTruthy();
  });

  it('자식이 터지면 하얀 화면 대신 안내가 남는다', () => {
    render(
      <ErrorBoundary area="시험">
        <Boom explode />
      </ErrorBoundary>,
    );

    // 화면을 읽어 주는 기기에도 알려야 하므로 role=alert 여야 한다.
    const box = screen.getByRole('alert');
    expect(box.textContent).toContain('문제가 생겼습니다');
    // ⛔ "자료가 없다"로 읽히면 안 된다 — 있는데 못 그린 것이다.
    expect(box.textContent).toContain('자료가 없어서가 아니라');
  });

  it('터진 사실이 창고로 간다 — 서버가 없는 이 앱에서 우리가 알 수 있는 유일한 길', () => {
    render(
      <ErrorBoundary area="층별 화면" context={{ bld_id: 'B1' }}>
        <Boom explode />
      </ErrorBoundary>,
    );

    expect(reported).toHaveLength(1);
    expect((reported[0].error as Error).message).toBe('렌더 중 폭발');

    const ctx = reported[0].context as Record<string, unknown>;
    expect(ctx.area).toBe('층별 화면');
    expect(ctx.bld_id).toBe('B1');
    // 어느 컴포넌트에서 터졌나 — 빌드된 스택만으로는 알아보기 어렵다.
    expect(ctx.component_stack).toBeTruthy();
  });

  it('다시 시도를 누르면 다시 그려 본다 — 막다른 길로 두지 않는다', () => {
    // ⚠️ "스스로 한 번만 터지는" 자식으로는 이 검사를 못 만든다 — 리액트는 오류를 잡은
    //    직후 한 번 더 그려 보므로, 자식이 스스로 낫는 종류면 그 재시도에서 이미 회복돼
    //    안내가 아예 안 뜬다(실제로 그렇게 실패했다). 그래서 **밖에서** 스위치를 쥔다.
    let explode = true;
    function Flaky() {
      if (explode) throw new Error('고쳐질 때까지 터짐');
      return <p>되살아난 내용</p>;
    }

    render(
      <ErrorBoundary area="시험">
        <Flaky />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeTruthy();

    // 원인이 사라진 뒤에 다시 시도해야 빠져나간다.
    explode = false;
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(screen.getByText('되살아난 내용')).toBeTruthy();
  });

  it('새로고침 길도 함께 준다', () => {
    render(
      <ErrorBoundary area="시험">
        <Boom explode />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('button', { name: '새로고침' })).toBeTruthy();
  });

  it('⛔ 맨 바깥 그물은 "다시 시도"를 권하지 않는다 — 같은 자리를 다시 그려도 똑같이 터진다', () => {
    // 2026-08-24 적대검증 지적. 바깥 그물이 뜬 상황은 검색창까지 통째로 죽은 것이라
    // 안쪽처럼 "다른 건물을 골라 본다"는 빠져나갈 길이 없다. 될 리 없는 일을 시키지 않는다.
    render(
      <ErrorBoundary area="앱 전체" outermost>
        <Boom explode />
      </ErrorBoundary>,
    );

    const box = screen.getByRole('alert');
    expect(screen.queryByRole('button', { name: '다시 시도' })).toBeNull();
    expect(screen.getByRole('button', { name: '새로고침' })).toBeTruthy();
    // 기대치를 정직하게 맞춰 준다 — "고쳐질 것"처럼 말하지 않는다.
    expect(box.textContent).toContain('저희 쪽 문제');
    expect(box.textContent).toContain('잠시 뒤 다시');
  });

  it('안쪽 그물은 빠져나갈 길(다른 건물)을 알려 준다', () => {
    render(
      <ErrorBoundary area="층별 화면">
        <Boom explode />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert').textContent).toContain('다른 건물을 골라');
  });
});
