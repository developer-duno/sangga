import type { ParcelLandPrice } from '../types';
import { formatManWon } from './format';

/*
  개별공시지가 한 줄(결정 0036 결정 7 · 물결 1-C1).

  층별 화면 머리의 건물 기본 사양 아래에 `개별공시지가 ㎡당 4,523만원 · <공시 연도>년 공시 (땅값만 · 공시가격 —
  시세가 아닙니다)` 한 줄을 그린다. 값은 브이월드 토지특성(`parcel.land_price` 원/㎡ · `land_price_year`)을
  함수 `get_parcel_land_price(p_pnu)` 로 받아 그대로 나른다.

  ⛔ 연도는 **서버 값**만 쓴다 — 이 파일·FloorStack 에 연도 글자를 박지 않는다(적재하는 순간 그 글자만 낡는다).
  ⛔ 실패·0줄·모양 이상은 전부 null — 화면은 **줄 자체를 안 그린다**. '자료 없음'이라 적지 않는다
     (함수가 없거나 실패한 것을 '없다'고 말하면 거짓이다 — 호실 구성표 결정 0032 와 같은 규칙).
  ⛔ 절대 규칙 2 의 금지어를 쓰지 않는다(`landPrice.test.ts` 가 글을 훑는다) — 공시가격이고 시세가 아님을 줄에 밝힌다.
*/

/** 줄 끝 꼬리말 — 땅값만이고 공시가격이지 시세가 아니라는 **값의 성질**(신뢰도 변명이 아니다). */
export const LAND_PRICE_NOTE = '(땅값만 · 공시가격 — 시세가 아닙니다)';

/**
 * `get_parcel_land_price` 응답 → 한 줄 값. 그릴 수 없으면 null.
 *
 * - 배열이 아니면(오류 응답·이상한 모양) null
 * - 0줄 = 값이 없는 필지 → null(줄 없음)
 * - 2줄 이상 = 서버가 약속한 모양이 아니다(pnu 는 기본키) → null
 * - 값이 음수·소수·숫자 아님, 연도가 양의 정수가 아님 → null
 * ⓘ 0원은 값이다(적재기가 원본 '0' 을 0 으로 담는다) — 거르지 않는다.
 */
export function parseLandPrice(data: unknown): ParcelLandPrice | null {
  if (!Array.isArray(data) || data.length !== 1) return null;
  const row: unknown = data[0];
  if (typeof row !== 'object' || row === null) return null;
  const { land_price: price, land_price_year: year } = row as Record<string, unknown>;
  if (typeof price !== 'number' || !Number.isSafeInteger(price) || price < 0) return null;
  if (typeof year !== 'number' || !Number.isInteger(year) || year <= 0) return null;
  return { land_price: price, land_price_year: year };
}

/**
 * ㎡당 금액 글. 1만원 이상은 만원 단위 반올림(`4,523만원`), 미만은 원 그대로(`8,500원`).
 *
 * ⓘ `formatManWon` 과 같은 자다 — 다만 그 함수는 '원' 을 1만원 미만에만 붙이므로 여기서 맞춘다.
 */
export function formatLandPriceAmount(won: number): string {
  if (Math.abs(won) < 10_000) return `${Math.round(won).toLocaleString('ko-KR')}원`;
  return `${formatManWon(won)}원`;
}

/** 화면에 그릴 한 줄 전체. */
export function landPriceText(v: ParcelLandPrice): string {
  return `개별공시지가 ㎡당 ${formatLandPriceAmount(v.land_price)} · ${v.land_price_year}년 공시 ${LAND_PRICE_NOTE}`;
}
