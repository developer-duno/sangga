/**
 * 국세청 기준시가(층별)의 순수 짝짓기·거르기.
 *
 * ⛔ **시세가 아니다.** 세금 매길 때 쓰는 고시가격이고, 같은 카드에 있는 참고 시세 밴드
 *    (우리가 곁 거래로 어림한 추정)와는 **다른 자로 잰 다른 값**이다. 그래서 이 파일은
 *    `priceBand.ts` 와 갈라 둔다 — 한 파일에 두면 다음 사람이 두 값을 한 줄로 합치거나
 *    서로 견주는 계산을 얹게 된다(사람은 나란히 놓인 두 숫자를 자동으로 견준다).
 *
 * ⚠️ 여기서는 **계산을 하지 않는다.** 서버가 낸 가운데값을 그대로 나르고, 화면에 그리면
 *    안 되는 줄만 걸러 낸다. 평균을 다시 내거나 층끼리 더하는 코드를 여기 넣지 말 것.
 */

import type { BasePrice, FloorRow } from '../types';
import { formatFloor } from './format';

/** 화면에 그릴 기준시가 한 줄. `floors` 가 준 **표시 순서 그대로** 나온다. */
export type BasePriceRow = {
  /** 화면 키 + 테스트용 식별자. */
  key: string;
  /** '2층' · '지하 1층' · '옥탑'. */
  label: string;
  base: BasePrice;
};

/**
 * 값으로 적어도 되는 고시가격인가.
 *
 * ⛔ 0 이하·숫자가 아닌 값은 **줄째로 버린다.** '㎡당 0원'이라고 적으면 "이 층은 값이
 *    없는 층"이라는 없는 사실이 생긴다 — 빈 0원 표시 금지(절대 규칙 3의 결).
 * ⛔ **몇 호를 세어 낸 가운데값인지 모르면 값도 안 낸다.** 이 값은 층 하나의 고시가격이
 *    아니라 그 층 호실들의 가운데값이라, 표본을 못 적으면 근거 없는 숫자가 된다
 *    (절대 규칙 3 — 값과 근거는 한 몸. 밴드 쪽 `BandBody` 가 `n` 이 없을 때 값을 안 내는
 *    것과 같은 규칙이다).
 */
function isShowable(base: BasePrice): boolean {
  const v = base.median_price_per_m2;
  const ho = base.ho_cnt;
  if (typeof v !== 'number' || !Number.isFinite(v) || v <= 0) return false;
  return typeof ho === 'number' && Number.isFinite(ho) && ho > 0;
}

/**
 * 서버가 준 필지 전체의 기준시가를 **이 건물의 층**과 짝짓는다.
 *
 * ## 짝짓기 함정 (밴드와 같은 함정이다)
 *
 * 서버는 **필지**의 층을 주고 화면은 **이 건물**의 층을 그린다. 인덱스로 맞추면 층이
 * 어긋나고, 한 땅에 여러 동이 선 필지에서는 옆 동 층까지 섞인다 — 그래서 `floors` 를
 * 돌며 `floor_no` 로만 짝짓는다(이 건물에 없는 층은 저절로 빠진다).
 *
 * `rows` 가 null(아직 안 왔거나 못 읽음)이면 빈 목록이다 — 화면은 그때 줄을 아예 안 그린다.
 */
export function pairBasePrices(rows: BasePrice[] | null, floors: FloorRow[]): BasePriceRow[] {
  if (rows === null) return [];

  const byFloor = new Map<number, BasePrice>();
  for (const r of rows) {
    if (typeof r?.floor_no !== 'number') continue;
    if (!isShowable(r)) continue;
    byFloor.set(r.floor_no, r);
  }

  const out: BasePriceRow[] = [];
  for (const f of floors) {
    const base = byFloor.get(f.floor_no);
    if (base === undefined) continue;
    out.push({
      key: `base-${f.floor_no}`,
      label: formatFloor(f.floor_no, f.floor_label),
      base,
    });
  }
  return out;
}
