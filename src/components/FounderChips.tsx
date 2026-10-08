import { FOUNDER_CHIPS, type FounderChip } from '../lib/founderChips';

/**
 * 창업자 업종 칩 줄 — 상권 지도 제목 줄에 선다(👤 결정 0036 결정 18 ④⑤).
 *
 * 고르면 건물을 열었을 때 둘레 업종 분포 카드가 그 업종을 미리 고르고, 개업·폐업 카드가 짝 업종 줄을
 * 굵게 한다(짝은 `lib/founderChips.ts` 의 표 한 곳). 하나만 고른다 — 고른 칩을 다시 눌러도 풀리지
 * 않고, 되돌리기는 '전체' 칩이다.
 *
 * ⓘ 상태는 위(App)가 쥔다 — 이 줄은 누른 것을 알리기만 한다.
 * ⛔ 저장하지 않는다(새로고침 = 전체) · 창업자에게만 그린다(App 이 정한다).
 * ⓘ 인쇄에서 빠진다(`styles.css` 의 `@media print` · 종이에서 못 누르는 조종 장치).
 */
type Props = {
  chip: FounderChip;
  onChange: (chip: FounderChip) => void;
};

export function FounderChips({ chip, onChange }: Props) {
  return (
    <div className="chips" role="group" aria-label="업종 고르기">
      <span className="chips__lead">업종</span>
      <ul className="chips__list">
        {FOUNDER_CHIPS.map((c) => {
          const on = c === chip;
          return (
            <li key={c}>
              <button
                type="button"
                className={`chips__chip${on ? ' chips__chip--on' : ''}`}
                aria-pressed={on}
                onClick={() => {
                  if (!on) onChange(c);
                }}
              >
                {c}
              </button>
            </li>
          );
        })}
      </ul>
      {/* 👤 F4 — 칩이 무엇을 바꾸는지 곁에 적는다(지도는 거르지 않으므로 누르고 아무 일도 없어 보인다). */}
      <p className="chips__note">건물을 열면 업종 분포·개업·폐업 카드에 반영됩니다</p>
    </div>
  );
}
