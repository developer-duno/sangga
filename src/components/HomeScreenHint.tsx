import { isStandalone, useInstallPrompt } from '../lib/installPrompt';

/*
  글 — 👤 2026-10-19 W4b 3번 「가. 기기별 한 줄 + 안드로이드는 단추」 결재 예시값 그대로(한 글자도 바꾸지 않는다 · 상수는 여기 한 곳).
  아이폰 글은 애플 iPhone 사용 설명서 「Add to Home Screen」, 안드로이드 글은 구글 크롬 고객센터 「설치 및 바로가기 만들기」를 따른다.
*/
const HOME_HINT_TITLE = '홈 화면에 두고 앱처럼 쓰기';
const HOME_HINT_IOS = '아이폰 Safari: 공유 단추 → 「홈 화면에 추가」';
const HOME_HINT_ANDROID_WITH_BTN = '안드로이드 크롬: 아래 단추를 누르거나 더보기(⋮) → 「설치 및 바로가기 만들기」';
const HOME_HINT_ANDROID = '안드로이드 크롬: 더보기(⋮) → 「설치 및 바로가기 만들기」';
const HOME_HINT_BTN = '홈 화면에 추가';

/**
 * 「더보기」 탭 안 작은 상자 — 홈 화면에 두고 앱처럼 쓰는 법(결정 0039 W4b · §6 「더보기 안 한 줄만」).
 *
 * ⓘ 휴대폰 꼬리말(`AppFooter` 의 `phoneOrder`)에서만 그린다 — 넓은 화면 DOM 0. 이미 홈 화면에서 연 창이면 아무것도 안 그린다.
 * ⓘ 단추는 크롬이 설치 창 이벤트를 줬을 때만(`beforeinstallprompt` — `lib/installPrompt.ts`) · 누르면 그 창 · 결과와 상관없이 단추만 사라진다.
 * ⛔ 팝업·덮개 없음(결정 0039 §8) · 종이에서 빠진다(인쇄 감춤 `.hshint`).
 */
export function HomeScreenHint() {
  const { canInstall, install } = useInstallPrompt();
  if (isStandalone()) return null;
  return (
    <section className="hshint" aria-label={HOME_HINT_TITLE}>
      <p className="hshint__h">{HOME_HINT_TITLE}</p>
      <ul className="hshint__list">
        <li>{HOME_HINT_IOS}</li>
        <li>{canInstall ? HOME_HINT_ANDROID_WITH_BTN : HOME_HINT_ANDROID}</li>
      </ul>
      {canInstall && (
        <button type="button" className="hshint__btn" onClick={install}>
          {HOME_HINT_BTN}
        </button>
      )}
    </section>
  );
}
