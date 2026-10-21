import { useRef, useState, type PointerEvent, type ReactNode } from 'react';

/**
 * 끌어올리는 상권 판 — 휴대폰 「지도」 탭에서 지도 아래에 붙는다(👤 2026-10-19 W4b 2번 「가. 세 단계 · 지도를 누르면 반으로 저절로」).
 *
 * 단계 셋: 엿보기(손잡이 + 한 줄) ↔ 반(화면 절반) ↔ 가득(띠 바로 아래까지). 안에 드는 것은 지금 지도 카드 아래 것 그대로
 * (범례 → 누른 자리 상권 → 건물 목록 → 출처 — 부르는 쪽이 `children` 으로 준다). 새 글은 엿보기 한 줄(`head`)뿐.
 *
 * ⓘ 단계는 위(`DistrictMap`)가 쥔다 — 지도를 누르면 반으로 올리고 구가 바뀌면 엿보기로 돌리는 일이 거기 있다.
 * ⓘ 손잡이는 **단추**다(키보드·낭독기는 누르기만으로 셋을 돈다) · 손가락 끌기는 손잡이와 머리 줄에서만 —
 *   30px 넘게 움직이면 그 방향으로 한 단계. 끄는 **도중**에는 판만 따라 움직이고(높이는 안 바꿈) 손을 뗀 단계에서 한 번 바뀐다
 *   (지도 칸 높이도 그때 한 번 바뀌고 `relayout` 도 한 번 — `DistrictMap`).
 * ⛔ 모양 규칙은 전부 `@media screen and (max-width: 720px)` 묶음 안(styles.css) · 종이에서 빠진다(인쇄 감춤 `.dsheet`).
 * ⛔ 넓은 화면·중개사(카드 꼴)에서는 그리지 않는다(DOM 0 — 부르는 쪽이 정한다).
 */
export type SheetStage = 'peek' | 'half' | 'full';

const NEXT: Record<SheetStage, SheetStage> = { peek: 'half', half: 'full', full: 'peek' };
const UP: Record<SheetStage, SheetStage> = { peek: 'half', half: 'full', full: 'full' };
const DOWN: Record<SheetStage, SheetStage> = { peek: 'peek', half: 'peek', full: 'half' };
const HANDLE_LABEL: Record<SheetStage, string> = {
  peek: '상권 판 펼치기',
  half: '상권 판 더 펼치기',
  full: '상권 판 접기',
};
/** 이만큼(px) 넘게 끌어야 단계가 바뀐다 — 손가락이 조금 떨린 것은 누름으로 본다. */
const DRAG_PX = 30;

type Props = {
  stage: SheetStage;
  onStage: (next: SheetStage) => void;
  /** 머리 줄 글(엿보기에서도 보이는 한 줄). */
  head: ReactNode;
  children: ReactNode;
};

export function DistrictSheet({ stage, onStage, head, children }: Props) {
  const start = useRef<{ y: number; id: number } | null>(null);
  /** 방금 끌기로 단계를 바꿨다 — 손을 뗄 때 따라오는 click 이 한 번 더 돌리지 않게. */
  const dragged = useRef(false);
  const [dy, setDy] = useState(0);

  function down(e: PointerEvent<HTMLDivElement>) {
    start.current = { y: e.clientY, id: e.pointerId };
    dragged.current = false;
  }
  function move(e: PointerEvent<HTMLDivElement>) {
    if (start.current === null || start.current.id !== e.pointerId) return;
    const d = e.clientY - start.current.y;
    /*
      정말 끌기 시작했을 때만 손가락을 붙잡는다(pointer capture) — 누르자마자 붙잡으면 손을 뗄 때 click 이 손잡이 단추가 아니라
      이 줄(div)로 가서 단추 누르기가 안 먹는다(2026-10-19 E2E 휴대폰에서 실측).
    */
    if (Math.abs(d) > 8 && !e.currentTarget.hasPointerCapture?.(e.pointerId)) {
      e.currentTarget.setPointerCapture?.(e.pointerId);
    }
    setDy(d);
  }
  function up(e: PointerEvent<HTMLDivElement>) {
    if (start.current === null || start.current.id !== e.pointerId) return;
    const moved = e.clientY - start.current.y;
    start.current = null;
    setDy(0);
    if (Math.abs(moved) <= DRAG_PX) return;
    dragged.current = true;
    const next = moved < 0 ? UP[stage] : DOWN[stage];
    if (next !== stage) onStage(next);
  }
  function cancel() {
    start.current = null;
    setDy(0);
  }

  return (
    <div
      className={`dsheet dsheet--${stage}`}
      style={dy !== 0 ? { transform: `translateY(${dy}px)` } : undefined}
    >
      <div
        className="dsheet__bar"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={cancel}
      >
        <button
          type="button"
          className="dsheet__handle"
          aria-expanded={stage !== 'peek'}
          aria-controls="dsheet-body"
          aria-label={HANDLE_LABEL[stage]}
          onClick={() => {
            if (dragged.current) {
              dragged.current = false;
              return;
            }
            onStage(NEXT[stage]);
          }}
        >
          <span className="dsheet__grip" aria-hidden="true" />
        </button>
        <div className="dsheet__head">{head}</div>
        {stage !== 'peek' && (
          <button type="button" className="dsheet__fold" onClick={() => onStage('peek')}>
            접기
          </button>
        )}
      </div>
      <div className="dsheet__body" id="dsheet-body">
        {children}
      </div>
    </div>
  );
}
