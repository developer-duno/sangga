import { isViewerRole, type ViewerRole } from './sectionCards';

/**
 * 첫 화면에서 고른 역할을 **이 기기에만** 적어 두는 부품(결정 0036 결정 11·18).
 *
 * ⛔ 담는 것은 역할 **하나**뿐이다. 주소(결정 0019)·의견함(결정 0034)에는 싣지 않는다 —
 *    링크를 받은 사람은 자기 역할로 보고, 서버는 누가 어떤 역할인지 모른다.
 * ⛔ **저장이 막힌 창**(사생활 보호 창·사이트 자료 차단)에서는 브라우저 저장소가 읽기·쓰기
 *    에서 예외를 던진다 — 그 예외를 여기서 삼킨다. 화면은 고른 역할대로 서고, 다음 방문에
 *    기억하지 못할 뿐이다(저장 실패로 화면이 죽으면 안 된다).
 * ⓘ 저장소를 인자로 받는 이유 — 시험이 "예외를 던지는 저장소"를 넣어 위 약속을 확인한다.
 *    `window.localStorage` 에 손을 대는 것만으로도 예외가 나는 창이 있어 그 접근도 감싼다.
 */
export const VIEWER_ROLE_STORAGE_KEY = 'sangga.viewerRole';

type RoleStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function browserStorage(): RoleStorage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** 적어 둔 역할. 없거나 세 역할이 아닌 값이거나 못 읽으면 null(= 역할을 고르기 전 화면). */
export function loadViewerRole(storage: RoleStorage | null = browserStorage()): ViewerRole | null {
  if (!storage) return null;
  try {
    const v = storage.getItem(VIEWER_ROLE_STORAGE_KEY);
    return isViewerRole(v) ? v : null;
  } catch {
    return null;
  }
}

/** 역할을 적는다. null = 지운다(고른 단추를 다시 눌러 해제했을 때). 실패는 조용히 넘긴다. */
export function saveViewerRole(
  role: ViewerRole | null,
  storage: RoleStorage | null = browserStorage(),
): void {
  if (!storage) return;
  try {
    if (role === null) storage.removeItem(VIEWER_ROLE_STORAGE_KEY);
    else storage.setItem(VIEWER_ROLE_STORAGE_KEY, role);
  } catch {
    // 저장이 막힌 창 — 화면은 고른 역할대로 서고 기억만 못 한다(위 머리말).
  }
}
