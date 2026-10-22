/**
 * PC 두 칸 오른쪽 목록 표의 머리 줄(👤 2026-10-22 방법 나 R4).
 *
 * 검색 결과·가게 이름 결과·상권 건물 목록이 같은 부품을 쓴다(칸 차례가 갈리지 않게 한 곳). 표마다 칸이 다르다:
 * - `building` 건물 검색 결과 = 이름 · 길 주소 · 층(👤 2026-10-22 「검색 결과는 세 칸」 — 서버가 점포 수를 안 준다 · 점포 칸 자체를 뺀다)
 * - `store` 가게 이름 결과 = 이름 · 길 주소 · 일치 가게(👤 2026-10-23 D4 「빈 층 칸을 빼고 이름·길 주소·일치 가게 세 칸」)
 * - `district` 상권 건물 목록 = 이름 · 길 주소 · 층 · 점포(네 칸 그대로)
 * ⓘ 눈으로 보는 머리일 뿐이다 — 줄마다 단추가 제 글을 다 들고 있어 낭독기는 머리 없이도 다 읽는다(`aria-hidden`).
 * ⓘ 줄의 칸은 같은 이름표(`rcell--name`·`--addr`·`--floor`·`--store`)를 쓰고, 칸 폭은 CSS 한 곳이 정한다(세 칸 = `.rtable__head--3`).
 */
export function ListTableHead({ kind }: { kind: 'building' | 'store' | 'district' }) {
  return (
    <div className={`rtable__head${kind === 'district' ? '' : ' rtable__head--3'}`} aria-hidden="true">
      <span className="rcell rcell--name">이름</span>
      <span className="rcell rcell--addr">길 주소</span>
      {kind !== 'store' && <span className="rcell rcell--floor">층</span>}
      {kind === 'store' && <span className="rcell rcell--store">일치 가게</span>}
      {kind === 'district' && <span className="rcell rcell--store">점포</span>}
    </div>
  );
}
