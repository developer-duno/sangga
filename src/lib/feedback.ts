/**
 * 화면에서 창고로 **짧은 글 한 통**을 보내는 길. 2026-08-24b.
 *
 * 두 가지가 이 길을 함께 쓴다:
 *  · `opinion` — 사람이 아래쪽 의견함에 쓴 글
 *  · `error`   — 화면이 죽으며 안전망(ErrorBoundary)이 자동으로 남긴 것
 *
 * 길을 두 번 뚫지 않는 이유는 필요한 것이 같기 때문이다("밖에서 안으로 짧은 글 넣기").
 * 서버 쪽 구조는 `supabase/migrations/2026-08-24b_app_feedback.sql` 참조 —
 * 표는 통째로 잠겨 있고 **넣기 전용 함수 하나**만 열려 있다.
 *
 * ⛔ 이 파일의 어떤 함수도 **예외를 밖으로 던지지 않는다.**
 *    `error` 경로는 이미 무언가 터진 뒤에 불린다. 거기서 또 터지면 오류를 알리려다
 *    화면을 두 번 죽이는 꼴이 된다. 그래서 전부 잡아서 `false` 로 돌려준다.
 */

import { SUBMIT_FEEDBACK_FN } from './appConstants';
import { supabase } from './supabase';

/** 편지의 종류. 서버 CHECK 제약과 같은 두 값뿐이다. */
export type FeedbackKind = 'opinion' | 'error';

/** 무엇을 보던 중이었나. 모양을 강제하지 않는다(서버 컬럼이 jsonb). */
export type FeedbackContext = Record<string, unknown>;

/**
 * 편지 한 통을 보낸다.
 *
 * @returns 창고가 받았으면 `true`. 모양이 아니거나·분당 상한에 걸렸거나·
 *          네트워크가 끊겼으면 `false`. **던지지 않는다.**
 */
export async function submitFeedback(
  kind: FeedbackKind,
  body: string,
  context?: FeedbackContext,
): Promise<boolean> {
  try {
    const { data, error } = await supabase.rpc(SUBMIT_FEEDBACK_FN, {
      p_kind: kind,
      p_body: body,
      p_context: context ?? null,
    });
    // 서버는 boolean 하나를 준다. 그 외의 것이 오면(마이그레이션 적용 전이라 함수가
    // 없으면 PGRST202) 받지 못한 것으로 본다 — "보냈습니다"라는 거짓 안심을 만들지 않는다.
    return !error && data === true;
  } catch {
    // 네트워크 두절·클라이언트 예외. 부르는 쪽이 안내를 띄울 수 있게 false 로만 알린다.
    return false;
  }
}

/**
 * 한 번 열어 둔 화면에서 오류 보고를 이미 보냈나.
 *
 * ⛔ 이 빗장이 없으면 **오류가 창고를 채운다.** 렌더 중에 터지는 오류는 리액트가 다시
 *    그리려 할 때마다 되풀이되므로, 한 번의 사고가 초당 수십 통이 된다. 서버에도 분당
 *    상한이 있지만 그건 마지막 방어선이고, 애초에 안 보내는 것이 맞다.
 *
 * ⚠️ 모듈 수준 변수라 새로고침하면 풀린다 — 그것이 의도다("한 방문에 한 번").
 *    테스트에서 되돌리려면 `vi.resetModules()` 로 모듈을 다시 읽는다.
 */
let errorAlreadyReported = false;

/**
 * 화면이 죽었다는 사실을 창고에 남긴다. 한 방문에 **한 번만** 보낸다.
 *
 * @returns 실제로 보냈으면 `true`. 이미 보냈거나 실패했으면 `false`. **던지지 않는다.**
 */
export async function reportClientError(
  error: unknown,
  context?: FeedbackContext,
): Promise<boolean> {
  if (errorAlreadyReported) return false;

  try {
    // ⚠️ 빗장보다 **먼저** 본문을 만든다. 순서가 반대면, 남길 것이 없는 오류(빈 문자열
    //    하나가 던져진 경우) 하나가 빗장만 걸어 놓고 물러나 **그 뒤의 진짜 오류를 영영
    //    못 보내게** 만든다. 아무것도 안 보냈으면 빗장도 안 걸려 있어야 한다.
    const body = describeError(error);
    if (!body) return false;

    // 보내기 **전에** 빗장을 건다. 보낸 뒤에 걸면 답을 기다리는 사이 되풀이된 오류가
    // 전부 빠져나간다(await 한 번이면 렌더가 여러 번 돈다).
    errorAlreadyReported = true;

    return await submitFeedback('error', body, {
      ...context,
      // 어느 브라우저에서 터졌나 — 같은 오류가 한 종류에서만 나는지 가르는 데 쓴다.
      // 개인을 가리키는 값이 아니고, 이것 없이는 재현이 사실상 불가능하다.
      ua: typeof navigator === 'undefined' ? null : navigator.userAgent,
      // 어느 주소에서 터졌나. 지금은 화면이 하나뿐이지만 주소에 상태를 담게 되면
      // (공유 링크) 이 한 칸이 재현의 열쇠가 된다.
      url: typeof location === 'undefined' ? null : location.href,
    });
  } catch {
    return false;
  }
}

/**
 * 오류를 사람이 읽을 수 있는 한 덩어리 글로 바꾼다.
 *
 * ⚠️ `Error` 가 아닌 것도 던져질 수 있다(문자열·객체·undefined). 그래서 `err.message` 를
 *    믿고 읽지 않는다 — 그 한 줄이 오류 보고 자체를 터뜨리는 자리다.
 */
export function describeError(error: unknown): string {
  if (error instanceof Error) {
    // 스택은 어디서 터졌는지 알려주는 유일한 단서다. 다만 서버가 2,000자에서 자르므로
    // 이름·메시지를 **앞**에 둔다(잘려도 무엇이 터졌는지는 남는다).
    const head = `${error.name}: ${error.message}`;
    return error.stack ? `${head}\n${error.stack}` : head;
  }
  if (typeof error === 'string') return error;
  try {
    return JSON.stringify(error) ?? String(error);
  } catch {
    // 순환 참조 등으로 JSON 이 안 되는 값. 그래도 무언가는 남긴다.
    return String(error);
  }
}
