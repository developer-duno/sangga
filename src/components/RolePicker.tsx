import { useId } from 'react';
import { VIEWER_ROLES, type ViewerRole } from '../lib/sectionCards';

/**
 * 첫 화면 역할 단추 줄 — `나는 [투자자][창업자][중개사]`(👤 결정 0036 결정 18 ⑧).
 *
 * 고르면 층별 화면 카드의 **순서·펼침**만 그 역할에 맞춰진다(자료는 한 벌 — `ROLE_SECTION_LAYOUT`).
 * 고른 단추를 다시 누르면 해제된다 — 역할을 고르기 전 화면으로 돌아가고 저장도 지운다.
 *
 * ⓘ 상태는 위(App)가 쥔다. 이 줄은 누른 것을 알리기만 한다 — 층별 화면도 같은 값을 봐야 해서다.
 * ⓘ 인쇄에서 빠진다(`styles.css` 의 `@media print` · 종이에서 못 누르는 조종 장치).
 */
type Props = {
  role: ViewerRole | null;
  onChange: (role: ViewerRole | null) => void;
  /**
   * 안내 글을 눈에 보이는 줄 대신 단추 설명으로 — PC 두 칸 왼쪽 칸(👤 2026-10-23 D3 「위를 줄여 올리기」 — 「역할 줄 아래 안내 글을 두 칸에서는
   * 역할 단추에 마우스를 올리면 보이는 설명으로 넣습니다」). 단추마다 마우스를 올리면 보이는 `title` + 낭독기용 `aria-describedby`(숨은 같은 글).
   * ⓘ 글자는 그대로 · 휴대폰·한 열은 지금처럼 보이는 줄.
   */
  noteAsTip?: boolean;
};

/** 역할 안내 글 — 보이는 줄과 단추 설명이 같은 글(한 곳). */
export const ROLE_NOTE = '고르면 화면 순서가 맞춰집니다 · 이 기기에만 저장 · 다시 누르면 해제';

export function RolePicker({ role, onChange, noteAsTip = false }: Props) {
  const noteId = useId();
  return (
    <section className="role" aria-label="역할 고르기">
      <span className="role__lead">나는</span>
      <ul className="role__list">
        {VIEWER_ROLES.map((r) => {
          const on = r === role;
          return (
            <li key={r}>
              <button
                type="button"
                className={`role__chip${on ? ' role__chip--on' : ''}`}
                aria-pressed={on}
                title={noteAsTip ? ROLE_NOTE : undefined}
                aria-describedby={noteAsTip ? noteId : undefined}
                onClick={() => onChange(on ? null : r)}
              >
                {r}
              </button>
            </li>
          );
        })}
      </ul>
      {/* 두 칸이면 숨은 글 — 낭독기는 단추 설명(`aria-describedby`)으로 읽는다(숨은 요소도 설명으로 쓸 수 있다 · accname 규칙). */}
      <p className="role__note" id={noteId} hidden={noteAsTip}>
        {ROLE_NOTE}
      </p>
    </section>
  );
}
