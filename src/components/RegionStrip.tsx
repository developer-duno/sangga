/**
 * 휴대폰 「지도」 탭 위 한 줄 띠(👤 2026-10-19 W4b 1번 「안 A · 위 한 줄 띠 + 지도 가득」).
 *
 * 왼쪽 단추 「서울 강남구 ▾」를 누르면 지금 지역 고르개(`section.region` — 찾기 탭과 **같은 하나**, 다시 태어나지 않는다)가
 * 띠 아래로 펼쳐진다 — 고르는 방법은 그대로. 구를 고르거나 탭을 옮기면 닫힌다(App).
 * ⓘ 휴대폰 지도 탭에서만 그린다(넓은 화면 DOM 0 — App 이 정한다) · 모양은 styles.css 720 화면 묶음 · 종이에서 빠진다(`.rstrip`).
 */
type Props = {
  /** 시도 짧은 이름 + 구 이름(App 의 `placeLabel` 과 같은 글). 아직 모르면 빈 글. */
  place: string;
  open: boolean;
  /** 지역 고르개의 id(`aria-controls`). */
  controls: string;
  onToggle: () => void;
};

export function RegionStrip({ place, open, controls, onToggle }: Props) {
  return (
    <div className="rstrip">
      <button
        type="button"
        className="rstrip__btn"
        aria-expanded={open}
        aria-controls={controls}
        onClick={onToggle}
      >
        {place || '고른 지역'}
        <span aria-hidden="true"> ▾</span>
      </button>
      <span className="rstrip__note">상권 지도</span>
    </div>
  );
}
