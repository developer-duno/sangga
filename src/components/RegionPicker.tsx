import { useEffect, useRef, useState } from 'react';
import { SIDOS, isOpenSido, openRegionLabel, type Sido } from '../lib/regions';

/**
 * 전국 17개 시도를 **전부** 보여주되, 자료가 들어온 곳만 열어 둔다 (결정 0006).
 *
 * 왜 잠긴 지역도 보여주나: 목록에서 아예 빼면 "우리 지역은 영영 안 되나?"가 되고,
 * 열린 지역만 두면 이 서비스가 전국을 향한다는 사실이 안 보인다. 보이되 눌렀을 때
 * **왜 아직 안 되는지·언제 되는지**를 말해 주는 쪽이 정직하다.
 *
 * ⛔ 이 컴포넌트는 검색을 지역으로 **좁히지 않는다.** 지금 검색은 담긴 자료 전체에서
 *    이뤄지고, 여기서 지역을 고르는 것은 안내일 뿐이다(결정 0006 "서버는 안 건드린다").
 *    지역별 검색 한정은 여러 시도에 건물이 실제로 들어온 뒤에 붙인다.
 */
export function RegionPicker() {
  const [picked, setPicked] = useState<Sido | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Esc 로 닫기 — 팝업을 띄워 놓고 빠져나갈 길이 없으면 안 된다.
  useEffect(() => {
    if (!picked) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPicked(null);
    };
    window.addEventListener('keydown', onKey);
    closeRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [picked]);

  return (
    <section className="region">
      <p className="region__lead">
        지금 보실 수 있는 지역은 <strong>{openRegionLabel()}</strong>입니다.
        다른 지역은 준비 중이에요.
      </p>

      <ul className="region__list">
        {SIDOS.map((s) => {
          const open = isOpenSido(s.code);
          return (
            <li key={s.code}>
              <button
                type="button"
                className={`region__chip${open ? ' region__chip--on' : ' region__chip--off'}`}
                aria-disabled={!open}
                onClick={() => setPicked(s)}
              >
                {!open && <span aria-hidden="true">🔒 </span>}
                {s.name}
              </button>
            </li>
          );
        })}
      </ul>

      {picked && (
        <div
          className="modal__back"
          onClick={() => setPicked(null)}
          role="presentation"
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="region-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="modal__title" id="region-modal-title">
              {isOpenSido(picked.code)
                ? `${picked.fullName}은(는) 지금 보실 수 있어요`
                : `${picked.fullName}은(는) 아직 준비 중입니다`}
            </h2>
            <p className="modal__body">
              {isOpenSido(picked.code) ? (
                <>
                  위 검색창에 <strong>건물 이름</strong>이나 <strong>주소</strong>를 넣어 찾아보세요.
                </>
              ) : (
                <>
                  자료를 모으는 중입니다. 지금은 <strong>{openRegionLabel()}</strong>을(를)
                  보실 수 있어요.
                </>
              )}
            </p>
            <button
              type="button"
              className="modal__close"
              ref={closeRef}
              onClick={() => setPicked(null)}
            >
              닫기
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
