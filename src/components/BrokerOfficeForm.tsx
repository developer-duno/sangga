import {
  BROKER_OFFICE_FIELDS,
  BROKER_OFFICE_MAX,
  clampOfficeField,
  officeToggleText,
  type BrokerOffice,
} from '../lib/brokerOfficeStore';

/**
 * 「종이에 찍을 내 사무소 정보」 접힌 줄(결정 0036 결정 3 · 물결 1-C2 · 「이 기기 저장」 ②③④).
 *
 * App 이 역할 = 중개사일 때만 인쇄 단추 옆(`.takeout`)에 넣는다. 채운 칸만 종이 머리 오른쪽에 찍힌다
 * (`PrintHeader`). ⛔ 이 칸 자체는 종이에서 빠진다(`.office` · `.takeout` — styles.css 인쇄 블록).
 * ⓘ 값·저장·지우기의 주인은 App 이다 — 이 부품은 그리기만 한다.
 */
type Props = {
  value: BrokerOffice;
  onChange: (next: BrokerOffice) => void;
  onClear: () => void;
};

export function BrokerOfficeForm({ value, onChange, onClear }: Props) {
  return (
    <details className="office">
      <summary className="office__toggle">{officeToggleText(value)}</summary>
      <p className="office__note">이 기기에만 저장 · 서버로 보내지 않음</p>
      <div className="office__fields">
        {BROKER_OFFICE_FIELDS.map(([k, label]) => {
          const id = `office-${k}`;
          const common = {
            id,
            value: value[k],
            maxLength: BROKER_OFFICE_MAX[k],
            onChange: (e: { target: { value: string } }) =>
              onChange({ ...value, [k]: clampOfficeField(k, e.target.value) }),
          };
          return (
            <label key={k} className={`office__field office__field--${k}`} htmlFor={id}>
              <span>{label}</span>
              {k === 'memo' ? <textarea rows={3} {...common} /> : <input type="text" {...common} />}
            </label>
          );
        })}
      </div>
      <p className="office__note">여럿이 함께 쓰는 컴퓨터라면 다 쓴 뒤 지우기를 눌러 주세요</p>
      <button type="button" className="office__clear" onClick={onClear}>
        지우기
      </button>
    </details>
  );
}
