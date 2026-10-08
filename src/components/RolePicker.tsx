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
};

export function RolePicker({ role, onChange }: Props) {
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
                onClick={() => onChange(on ? null : r)}
              >
                {r}
              </button>
            </li>
          );
        })}
      </ul>
      <p className="role__note">고르면 화면 순서가 맞춰집니다 · 이 기기에만 저장 · 다시 누르면 해제</p>
    </section>
  );
}
