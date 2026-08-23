import { Children, useEffect, useId, useState, type ReactNode } from 'react';
import type { SectionPlan } from '../lib/sectionCards';

/**
 * 층별 화면 섹션을 감싸는 **공통 카드 틀** — 로드맵 Wave 2 『한 장 요약 접힘 틀』.
 *
 * 하는 일은 셋뿐이다(더 늘리지 말 것):
 *  ① 제목 + 역할 태그를 한 줄로 얹는다
 *  ② 접기/펼치기 — 버튼 시맨틱(`aria-expanded`·`aria-controls`)이라 키보드·읽어 주는
 *     기기에서도 눌린다
 *  ③ **접혀 있어도 핵심 한 줄(`summary`)은 그대로 보인다**
 *
 * ⚠️ ③이 이 틀의 존재 이유다. 접힘이 "숨김"이 되면 한 장 요약이 아니라 그냥 잠긴 서랍이
 *    된다 — 접힌 카드에서도 "몇 건인지 · 무엇이 있는지"는 읽을 수 있어야 한다.
 * ⚠️ **본문이 없으면 버튼을 만들지 않는다**(아래 `hasBody`). 눌러도 아무 일도 안 하는데
 *    "펼칠 수 있음"이라고 말하는 버튼은, 눈으로 보는 사람에게는 그냥 안 열리는 화살표지만
 *    읽어 주는 기기를 쓰는 사람에게는 **없는 내용을 찾아 헤매게 만드는 거짓말**이다.
 *    발동 지점은 로딩 카드 둘(업종 분포·참고 시세의 "불러오는 중…")이다.
 * ⓘ 상태는 **이 카드 안의 `useState` 하나**다. 위에서 내려 주는 전역 상태로 만들면 카드
 *    다섯 장이 한 덩어리가 되고, 카드를 하나 더 붙일 때마다 부모를 고쳐야 한다.
 */
type Props = {
  /** `SECTION_PLAN` 의 한 칸. 제목·역할·기본 펼침이 전부 거기서 온다(정본 한 곳). */
  plan: SectionPlan;
  /** 겉 `<section>` 에 함께 붙일 class. 기존 스타일·시험이 이 이름으로 카드를 찾는다. */
  className: string;
  /** 접혀 있어도 항상 보이는 핵심 한 줄. 없으면(null) 요약 줄 자체를 안 그린다. */
  summary: ReactNode;
  /** 펼쳤을 때 나오는 본문. 없으면 본문 칸도 접기 버튼도 안 만든다. */
  children?: ReactNode;
  /**
   * **밖에서 이 카드를 펼치라고 부르는 신호.** 값이 바뀔 때마다(보통 1씩 올린다) 펼친다.
   *
   * 왜 boolean 이 아니라 **바뀌는 숫자**인가 — "펼쳐라"는 명령은 같은 요청이 여러 번 올 수
   * 있는데(시세 줄을 두 번 누르는 등), boolean 은 이미 true 면 아무 일도 안 일어난다.
   *
   * ⚠️ 값이 정해져 있으면 **첫 렌더에도 한 번 펼친다.** 그래서 이 prop 은 `defaultOpen`
   *    이 참인 카드에만 준다(지금은 층 목록 하나). 접힌 채로 시작해야 하는 카드에 주면
   *    첫 화면 펼침 상한이 조용히 깨진다.
   */
  openSignal?: number;
  /**
   * 펼침/접힘이 바뀔 때 밖에 알린다.
   *
   * 이 카드 안의 내용을 **가리키는 다른 카드**가 있을 때만 쓴다 — 참고 시세 줄이
   * `aria-expanded` 로 "그 층이 펼쳐져 있다"고 말하는데, 정작 층 목록 카드가 접혀 있으면
   * 그 말이 거짓이 된다. 상태를 위로 끌어올리지 않고 **알려 주기만** 한다.
   */
  onToggle?: (open: boolean) => void;
};

export function SectionCard({
  plan,
  className,
  summary,
  children,
  openSignal,
  onToggle,
}: Props) {
  const [open, setOpen] = useState(plan.defaultOpen);
  const bodyId = useId();

  // ⚠️ `Children.count` 를 쓰면 안 된다 — `false`·`null` 같은 "안 그리는 것"도 하나로 센다
  //    (`{cond && <p/>}` 가 거짓일 때가 정확히 그 경우다). `toArray` 는 그것들을 걸러 낸다.
  const hasBody = Children.toArray(children).length > 0;

  useEffect(() => {
    if (openSignal !== undefined) setOpen(true);
  }, [openSignal]);

  useEffect(() => {
    onToggle?.(open);
  }, [open, onToggle]);

  // 본문이 없으면 접힌 것이 아니라 **접을 것이 없는** 상태다. 표시용 class 도 안 붙인다.
  const collapsed = hasBody && !open;

  return (
    <section className={`card ${className}${collapsed ? ' card--closed' : ''}`}>
      {/*
        WAI-ARIA 아코디언 표준형: 제목(h3) 안에 버튼 하나. 버튼을 h3 밖에 두면 제목이
        목차에서 사라지고, 반대로 h3 를 버튼 안에 넣으면 문법에 어긋난다(button 안에는
        문단 요소를 못 넣는다).
      */}
      <h3 className="card__h">
        {hasBody ? (
          <button
            type="button"
            className="card__toggle"
            aria-expanded={open}
            // 접혀 있을 때는 본문 자체를 안 그리므로 가리킬 곳이 없다 — 없는 id 를
            // 가리키면 읽어 주는 기기가 빈 곳을 찾아간다.
            aria-controls={open ? bodyId : undefined}
            onClick={() => setOpen((v) => !v)}
          >
            <span className="card__title">{plan.title}</span>
            <span className="card__role">{plan.role}</span>
            {/* 화살표는 상태를 눈으로 보여줄 뿐이다 — 읽어 주는 기기에는 aria-expanded 가
                이미 같은 말을 하므로 겹쳐 읽히지 않게 감춘다. */}
            <span className="card__caret" aria-hidden="true">
              {open ? '▲' : '▼'}
            </span>
          </button>
        ) : (
          <span className="card__head">
            <span className="card__title">{plan.title}</span>
            <span className="card__role">{plan.role}</span>
          </span>
        )}
      </h3>

      {summary !== null && summary !== undefined && <p className="card__summary">{summary}</p>}

      {open && hasBody && (
        <div className="card__body" id={bodyId}>
          {children}
        </div>
      )}
    </section>
  );
}
