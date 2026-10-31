import { SECTION_PLAN, type SectionPlan } from '../lib/sectionCards';
import { emptyCardText, type EmptyCardKey } from '../lib/emptyCards';
import { SectionCard } from './SectionCard';

/**
 * 빈 카드 하나 — 빈 카드 둘(서울 밖 업종별 추정매출 · 유동인구 — 결정 0036 결정 2 · 물결 1-B · 가게 이력은 2026-11-01 부터 제 카드).
 *
 * ⛔ **아무것도 부르지 않는다**(서버 함수 0 · `sidePrefetch` 0) — 글은 `lib/emptyCards.ts` 가 pnu 로 고른다.
 * ⛔ **종이에서는 빠진다**(👤 2026-10-11) — `card--empty` 를 단 동안만 `styles.css` 의 `@media print` 가
 *    뺀다. 자료가 차서 이 카드가 제 컴포넌트로 바뀌면 그 이름표가 없으니 그때부터 종이에 나온다.
 *    ⓘ 그래서 이 이름표는 **빈 상태일 때만** 붙인다 — 자료가 든 카드에 옮겨 붙이지 않는다.
 */
type Props = {
  kind: EmptyCardKey;
  /** 이 필지 — 앞 두 자리로 서울 건물인지 고른다(개업·폐업 카드와 같은 길). */
  pnu: string;
  /** 이 카드의 배치. 안 주면 `SECTION_PLAN[kind]` — 역할을 고르기 전 화면 그대로. */
  plan?: SectionPlan;
};

export function EmptySection({ kind, pnu, plan = SECTION_PLAN[kind] }: Props) {
  const { summary, body } = emptyCardText(kind, pnu);
  // ⛔ 빈 카드에는 날짜 줄이 없다(S3 · 👤 결정 ②) — sales·pop 칸은 서울 카드(결정 0045 PR③)가 쓰는 `sources` 를 가지므로
  //    서울 밖 건물의 빈 카드에 서울시 자료 날짜가 새지 않게 여기서 뺀다.
  const emptyPlan: SectionPlan = { ...plan, sources: undefined };
  return (
    <SectionCard plan={emptyPlan} className={`card--empty card--${kind}`} summary={summary}>
      <p className="empty__body">{body}</p>
    </SectionCard>
  );
}
