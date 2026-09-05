import { useId, useState } from 'react';

import { GUIDE_LINES, HANDOFF_GROUPS, ROLE_STARTS } from '../lib/handoffLinks';
import { SECTION_PLAN } from '../lib/sectionCards';

/**
 * 화면 맨 아래 **"더 필요하면 여기서"** — 넘기는 곳 목록 + 접힌 "어디서 뭐를 보나".
 *
 * 왜 여기인가 (결정 0014 §5)
 * -------------------------
 * 항목 카드마다 배지를 다는 안은 **기각**됐다. 카드와 서비스를 짝지어 보니 "임대 사정"
 * 카드에 매출·유동인구 서비스가 붙는 오매칭이 났고, 역할 셋 × 카드 여섯으로 판단이 갈려
 * 위험이 구조적이었다. **페이지 끝 한 구역**이면 인쇄할 때 그 구역만 빼면 된다
 * (`@media print` 의 `.links` 한 줄이 그 일을 한다 — 종이에서는 아무 데도 못 누른다).
 *
 * 왜 별도 페이지가 아닌가
 * ----------------------
 * 이 앱에는 라우터가 없다(주소는 `?sgg=&bld=` 물음표 방식뿐). 안내 하나 때문에 라우팅을
 * 새로 들이면 구조 변경이고, 그 구조는 상권 지도 파일까지 첫 화면으로 바꿔칠 위험을 함께
 * 진다(결정 0019). 다 보고 난 사람이 찾는 자리는 어차피 화면 끝이라 여기가 제자리다.
 *
 * ⛔ 안내 문구에 '적정가격·감정가·평가액·가치평가' 를 쓰지 않는다(절대 규칙 2).
 * ⛔ 카드 **장수를 글자로 적지 않는다.** 아래 목록은 `SECTION_PLAN` 을 그대로 돌려서
 *    만든다 — 카드가 늘면 안내도 저절로 는다. 손으로 적으면 그날부터 옛말이 된다.
 */
export function HandoffLinks() {
  const headingId = useId();
  const guideId = useId();
  const [open, setOpen] = useState(false);

  // `Object.keys` 는 타입이 `string[]` 이라 그대로는 `GUIDE_LINES` 를 못 켠다. 표 자체가
  // `as const` 라 키 목록은 컴파일 시점에 고정돼 있고, 빠진 칸은 `GUIDE_LINES` 의 타입
  // (`Record<keyof typeof SECTION_PLAN, string>`)이 막는다.
  const cardKeys = Object.keys(SECTION_PLAN) as (keyof typeof SECTION_PLAN)[];

  return (
    <section className="links" aria-labelledby={headingId}>
      <h2 className="links__h" id={headingId}>
        더 필요하면 여기서
      </h2>
      <p className="links__lead">
        우리는 <strong>그 건물이 어떤 건물인지 알려주는 곳</strong>입니다. 매물과 상담, 더 깊은
        분석은 그 일을 잘하는 곳으로 넘깁니다.
      </p>

      <ul className="links__groups">
        {HANDOFF_GROUPS.map((g) => (
          <li className="links__group" key={g.id}>
            <span className="links__need">{g.need}</span>
            <span className="links__what">{g.what}</span>
            <span className="links__sites">
              {g.links.map((l) => (
                // ⚠️ 새 창으로 열되 `rel` 을 함께 준다 — 없으면 열린 쪽이 우리 창을 되돌려
                //    다른 주소로 보낼 수 있다(LH 카드의 링크와 같은 규칙).
                <a
                  className="links__a"
                  href={l.href}
                  key={l.href}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  {l.label}
                </a>
              ))}
            </span>
          </li>
        ))}
      </ul>

      <div className="links__guide">
        {/*
          접힘 틀은 `SectionCard` 와 같은 모양이다 — 버튼 시맨틱(`aria-expanded`·
          `aria-controls`)이라 키보드·읽어 주는 기기에서도 눌린다. 본문은 접혀 있어도
          자리에 두고 `hidden` 으로만 감춘다(그래야 가리킬 곳이 늘 있다).
          ⓘ 카드 틀(`SectionCard`)을 그대로 쓰지 않은 이유 — 저 틀은 `SECTION_PLAN` 한 칸을
            받아야 하는데, 이건 층별 화면 카드가 아니라 푸터 안내라 그 표에 낄 자리가 없다.
            억지로 끼우면 첫 화면 펼침 예산(4장)이 다른 화면에 걸쳐 나뉜다.
        */}
        <button
          aria-controls={guideId}
          aria-expanded={open}
          className="links__guide-btn"
          onClick={() => setOpen((v) => !v)}
          type="button"
        >
          어디서 뭐를 보나
          <span aria-hidden="true">{open ? ' ▲' : ' ▼'}</span>
        </button>

        <div className="links__guide-body" hidden={!open} id={guideId}>
          <p className="links__guide-h">무엇을 찾는 사람인가에 따라 시작점이 다릅니다</p>
          <ul className="links__roles">
            {ROLE_STARTS.map((r) => (
              <li key={r.role}>
                <strong>{r.role}</strong> — {r.how}
              </li>
            ))}
          </ul>

          <p className="links__guide-h">건물을 고르면 나오는 칸들이 답하는 질문</p>
          <ul className="links__cards">
            {cardKeys.map((key) => (
              <li key={key}>
                <strong>{SECTION_PLAN[key].title}</strong> — {GUIDE_LINES[key]}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
