import { useId } from 'react';
import type { ViewerRole } from '../lib/sectionCards';

/**
 * 첫 방문 한 번 — 역할 고르기 큰 카드(결정 0039 Q3 · §4-10 · §4-14 · §7-4 · W3 · 👤 2026-10-17 시안 A 문구 그대로).
 *
 * 「무엇을 하러 오셨나요?」 + 카드 셋(이름 + 한 줄) + 「그냥 둘러보기」 + 안내 한 줄.
 * ⛔ **덮개(modal)가 아니다** — 입구 맨 위 제자리 카드라 아래 내용을 가리지 않는다(검색 봇·결정 0037 첫 HTML).
 * ⓘ 언제 서는지(이 기기 저장값 없음 · 건물 직행 링크 아님)와 저장은 위(App)가 정한다. 이 카드는 누른 것만 알린다 —
 *    카드 = 그 역할 · 「그냥 둘러보기」 = null.
 * ⓘ 한 줄 설명은 그 역할 화면이 실제로 먼저 펼치는 것과 맞춰 둔 글이다(`ROLE_SECTION_LAYOUT` · `entryBlockOrder` ·
 *    역할 요약 판) — 역할 화면을 바꾸면 이 글도 본다.
 * ⓘ 인쇄에서 빠진다(`styles.css` 의 `@media print` · 종이에서 못 누르는 조종 장치).
 */
const ROLE_CARDS: ReadonlyArray<{ role: ViewerRole; name: string; line: string }> = [
  { role: '투자자', name: '투자·매입하려고', line: '실거래·층별 공표값을 먼저 펼쳐 둡니다' },
  { role: '창업자', name: '가게를 열려고', line: '상권 지도·업종 분포를 먼저 보여 드립니다' },
  { role: '중개사', name: '중개하려고', line: '층별 호실·한 장으로 뽑기를 먼저 둡니다' },
];

type Props = {
  onPick: (role: ViewerRole | null) => void;
};

export function RoleCards({ onPick }: Props) {
  const qId = useId();
  return (
    <section className="rolecards" aria-labelledby={qId}>
      <p className="rolecards__q" id={qId}>
        무엇을 하러 오셨나요?
      </p>
      <ul className="rolecards__list">
        {ROLE_CARDS.map((c) => (
          <li key={c.role}>
            <button type="button" className="rolecards__card" onClick={() => onPick(c.role)}>
              <span className="rolecards__name">{c.name}</span>
              <span className="rolecards__line">{c.line}</span>
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="rolecards__browse" onClick={() => onPick(null)}>
        그냥 둘러보기
      </button>
      <p className="rolecards__note">이 기기에만 저장 · 나중에 위 「나는」에서 언제든 바꿀 수 있어요</p>
    </section>
  );
}
