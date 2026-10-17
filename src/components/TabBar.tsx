import type { ReactNode } from 'react';
import { TAB_LABEL, type AppTab } from '../lib/appTabs';

/**
 * 휴대폰 아래 탭 막대(결정 0039 Q1 · W4a). App 이 휴대폰 꼴일 때만 그린다 — 넓은 화면 DOM 에는 없다.
 *
 * ⓘ ARIA tabs(화살표 키 의무) 대신 `nav` + 단추 + 고른 탭 `aria-current="page"`(메인 판단 ⑧).
 * ⓘ 그림은 직접 그린 선 그림(인라인 SVG · 스크립트 0 · 외부 아이콘 0 — 시안 3번 「가」) · 낭독기엔 글자만(`aria-hidden`).
 * ⓘ 「건물」은 건물을 안 골랐으면 흐리게(`tabbar__btn--dim`) 늘 그 자리 — 누르면 빈 안내(👤 1번 「가」).
 * ⛔ 종이에서 빠진다(인쇄 감춤 목록 `.tabbar`) · 글 입력칸에 커서가 있으면 숨는다(자판 · styles.css 720 묶음).
 */
const ICON: Record<AppTab, ReactNode> = {
  find: (
    <>
      <circle cx="11" cy="11" r="6" />
      <path d="M20 20l-4.5-4.5" />
    </>
  ),
  map: (
    <>
      <path d="M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z" />
      <path d="M9 4v14M15 6v14" />
    </>
  ),
  building: (
    <>
      <rect x="5" y="3" width="14" height="18" rx="1" />
      <path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2" />
    </>
  ),
  printed: (
    <>
      <path d="M7 9V3h10v6" />
      <rect x="4" y="9" width="16" height="8" rx="1" />
      <path d="M7 14h10v7H7z" />
    </>
  ),
  more: (
    <>
      <circle cx="5" cy="12" r="1.5" />
      <circle cx="12" cy="12" r="1.5" />
      <circle cx="19" cy="12" r="1.5" />
    </>
  ),
};

type Props = {
  tabs: readonly AppTab[];
  current: AppTab;
  /** 「건물」 탭을 흐리게(아직 고른 건물이 없다). */
  buildingDim: boolean;
  onPick: (tab: AppTab) => void;
};

export function TabBar({ tabs, current, buildingDim, onPick }: Props) {
  return (
    <nav className="tabbar" aria-label="화면 고르기">
      {tabs.map((t) => (
        <button
          key={t}
          type="button"
          className={`tabbar__btn${t === current ? ' tabbar__btn--on' : ''}${
            t === 'building' && buildingDim ? ' tabbar__btn--dim' : ''
          }`}
          aria-current={t === current ? 'page' : undefined}
          onClick={() => onPick(t)}
        >
          <svg className="tabbar__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            {ICON[t]}
          </svg>
          {TAB_LABEL[t]}
        </button>
      ))}
    </nav>
  );
}
