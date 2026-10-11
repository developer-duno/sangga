import { useId } from 'react';
import { UNIT_PRINT_OPTIONS, type UnitPrintMode } from '../lib/unitPrint';

/**
 * 「호실 구성표(종이·화면)」 고르기(결정 0036 결정 8 · 물결 1-C2) — 누구에게나 인쇄 단추 옆에 선다.
 * 고르면 층별 화면이 그 층들의 호 목록을 층 줄 아래에 펼친다(`FloorStack` · `lib/unitPrint.ts`).
 * ⛔ 저장하지 않는다 · 이 고르기 자체는 종이에서 빠진다(`.unitpick` · `.takeout`).
 */
type Props = {
  mode: UnitPrintMode;
  onChange: (mode: UnitPrintMode) => void;
};

export function UnitPrintPicker({ mode, onChange }: Props) {
  const name = useId();
  return (
    <div className="unitpick" role="radiogroup" aria-label="호실 구성표(종이·화면)">
      <span className="unitpick__lead">호실 구성표(종이·화면):</span>
      {UNIT_PRINT_OPTIONS.map(([m, label]) => (
        <label key={m} className="unitpick__opt">
          <input
            type="radio"
            name={name}
            value={m}
            checked={mode === m}
            onChange={() => onChange(m)}
          />
          {label}
        </label>
      ))}
    </div>
  );
}
