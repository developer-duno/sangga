import type { Ref } from 'react';

/**
 * PC 두 칸의 접힌 왼쪽 칸 — 56px 세로 띠(👤 2026-10-21 W5 「가 · 세로 띠 56px 로 접힘」 · 결정 0039 §7-11).
 * 위에서부터 펼치기 단추(44px) · 지금 구 이름 세로 글 · 「지도」 작은 단추(펼치고 지도로 커서).
 * ⓘ 왼쪽 칸(`#entry-panel`)은 접혀도 언마운트하지 않는다 — App 이 CSS 로 숨기고 `inert` 를 건다(검색어·지도 그대로).
 * ⓘ 그리기는 App 이 두 칸·접힘일 때만 · 종이에서 빠진다(`.lrail` · 누르는 장치).
 */
type Props = {
  /** 「서울 강남구」 꼴(바의 `placeLabel` 과 같은 값) — 비면 세로 글 없음. */
  place: string;
  /** 구를 골랐나 — 지도가 있을 때만 「지도」 단추. */
  hasMap: boolean;
  onExpand: (target: 'fold' | 'map') => void;
  expandRef?: Ref<HTMLButtonElement>;
};

export function LeftRail({ place, hasMap, onExpand, expandRef }: Props) {
  return (
    <div className="lrail">
      <button
        type="button"
        className="lrail__btn"
        ref={expandRef}
        aria-expanded={false}
        aria-controls="entry-panel"
        aria-label="왼쪽 칸 펼치기"
        onClick={() => onExpand('fold')}
      >
        <span aria-hidden="true">›</span>
      </button>
      {place && <span className="lrail__place">{place}</span>}
      {hasMap && (
        <button
          type="button"
          className="lrail__btn lrail__map"
          aria-expanded={false}
          aria-controls="entry-panel"
          onClick={() => onExpand('map')}
        >
          지도
        </button>
      )}
    </div>
  );
}
