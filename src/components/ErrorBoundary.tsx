import { Component, type ErrorInfo, type ReactNode } from 'react';

import { reportClientError } from '../lib/feedback';

/**
 * 그리다 터진 오류를 받아 내는 그물.
 *
 * ⛔ **없으면 화면이 통째로 하얘진다.** 리액트는 렌더 중에 예외가 나면 그 위 트리를 전부
 *    떼어 내는데, 받아 줄 그물이 없으면 `<div id="root">` 가 텅 비고 아무 말도 안 남는다.
 *    보는 사람은 "자료가 없는 건지 고장난 건지"조차 구분할 수 없고, 서버가 없는 이 앱에서는
 *    **우리도 그 일이 있었다는 사실을 영영 모른다.**
 *
 * ⚠️ 왜 이 레포에서 유일하게 클래스인가 — 리액트는 오류를 잡는 길을 아직 클래스에만
 *    열어 두었다(`getDerivedStateFromError`·`componentDidCatch`). 훅으로 옮길 수 없어서
 *    모양이 다른 것이지, 옛 코드가 남은 것이 아니다.
 *
 * ⚠️ 이 그물이 **못 잡는 것**도 분명히 해 둔다(있다고 안심하면 안 되는 자리):
 *    · 이벤트 처리 중에 난 오류(버튼 누름 등) — 리액트가 렌더 밖으로 보지 않는다
 *    · `await` 뒤에서 난 오류 — 이미 렌더가 끝난 뒤다
 *    · 서버 응답이 이상한 것 — 그건 각 섹션이 모양 검사로 따로 막는다(`isIndustryMix` 등)
 *    즉 이것은 마지막 그물이지 첫 방어선이 아니다.
 */

interface Props {
  children: ReactNode;
  /**
   * 어느 구역인가("층별 화면" 등). 창고에 남는 기록에 함께 실려 **어디가 죽었는지**를
   * 가른다. 화면에는 안 쓴다 — 보는 사람에게 내부 구역 이름은 뜻이 없다.
   */
  area: string;
  /**
   * 무엇을 보던 중이었나. 기록에 함께 실린다(건물·구 등). 없어도 된다.
   * ⚠️ 개인을 가리키는 값을 넣지 말 것 — 이 표는 개인정보를 안 받는다는 전제로 만들었다.
   */
  context?: Record<string, unknown>;
  /**
   * 이 그물이 **화면 전체**를 감싸고 있나(main.tsx 의 마지막 그물).
   *
   * ⛔ 안내 문구가 달라져야 한다. 안쪽 그물은 "다시 시도"가 뜻이 있다 — 다른 건물·다른 구를
   *    고르면 `key` 로 새로 그려지므로 빠져나갈 길이 실제로 있다. 그러나 바깥 그물이 뜬
   *    상황은 검색창까지 통째로 죽은 것이라, 같은 자리를 다시 그려 봐야 **똑같이 터진다.**
   *    거기서 "다시 시도"를 권하는 것은 될 리 없는 일을 시키는 것이다(2026-08-24 적대검증).
   */
  outermost?: boolean;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  /** 렌더를 대신할 것을 정한다. 여기서는 부수 효과를 내지 않는다(리액트가 두 번 부를 수 있다). */
  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  /** 기록은 여기서 남긴다. `reportClientError` 가 한 방문에 한 번만 실제로 보낸다. */
  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 콘솔에도 남긴다 — 개발 중에는 이쪽이 훨씬 빨리 눈에 띈다.
    console.error(`[${this.props.area}] 화면을 그리다 문제가 생겼습니다`, error, info);
    // 일부러 기다리지 않는다(void). 보고가 늦어도 안내는 즉시 떠야 한다.
    void reportClientError(error, {
      ...this.props.context,
      area: this.props.area,
      // 어느 컴포넌트 줄에서 터졌나. 스택만으로는 빌드된 이름이라 알아보기 어렵다.
      component_stack: info.componentStack ?? null,
    });
  }

  private handleRetry = (): void => {
    this.setState({ hasError: false });
  };

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;

    // 바깥 그물은 "다시 시도"를 권하지 않는다 — 같은 자리를 다시 그려 봐야 똑같이 터진다.
    // 될 리 없는 일을 시키느니, 무엇이 실제로 도움이 되는지를 말한다.
    if (this.props.outermost) {
      return (
        <div className="errbox" role="alert">
          <p className="errbox__title">화면을 여는 중에 문제가 생겼습니다.</p>
          <p className="errbox__body">
            보시려던 자료에 문제가 있는 것이 아니라 화면이 잘못 동작한 것입니다. 한 번
            새로고침해 보시고, <strong>그래도 같으면 저희 쪽 문제</strong>이니 잠시 뒤 다시
            들러 주세요.
          </p>
          <div className="errbox__acts">
            <button type="button" className="errbox__btn" onClick={() => location.reload()}>
              새로고침
            </button>
          </div>
        </div>
      );
    }

    return (
      // role="alert" — 화면을 읽어 주는 기기에 "지금 뭔가 달라졌다"를 알린다.
      <div className="errbox" role="alert">
        <p className="errbox__title">이 부분을 보여주다 문제가 생겼습니다.</p>
        <p className="errbox__body">
          자료가 없어서가 아니라 화면이 잘못 동작한 것입니다. 다시 시도해도 같으면{' '}
          <strong>다른 건물을 골라 보시고</strong>, 그래도 같으면 아래 의견함으로 알려 주시면
          고치겠습니다.
        </p>
        <div className="errbox__acts">
          <button type="button" className="errbox__btn" onClick={this.handleRetry}>
            다시 시도
          </button>
          <button
            type="button"
            className="errbox__btn errbox__btn--ghost"
            onClick={() => location.reload()}
          >
            새로고침
          </button>
        </div>
      </div>
    );
  }
}
