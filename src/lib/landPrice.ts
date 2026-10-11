import type { ParcelLandPrice } from '../types';

/*
  개별공시지가 한 줄(결정 0036 결정 7 · 물결 1-C1).

  층별 화면 머리의 건물 기본 사양 아래에 배지 「A등급 · 공식 공시」 + `개별공시지가 땅 1㎡당 4,523만원 ·
  <공시 연도>년 공시 (이 건물이 선 땅 · 공시가격 — 시세가 아닙니다)` 한 줄을 그린다(👤 문구 · 결정 0036 결정 7 보완). 값은 브이월드 토지특성(`parcel.land_price` 원/㎡ · `land_price_year`)을
  함수 `get_parcel_land_price(p_pnu)` 로 받아 그대로 나른다.

  ⛔ 연도는 **서버 값**만 쓴다 — 이 파일·FloorStack 에 연도 글자를 박지 않는다(적재하는 순간 그 글자만 낡는다).
  ⛔ 실패·0줄·모양 이상은 전부 null — 화면은 **줄 자체를 안 그린다**. '자료 없음'이라 적지 않는다
     (함수가 없거나 실패한 것을 '없다'고 말하면 거짓이다 — 호실 구성표 결정 0032 와 같은 규칙).
  ⛔ 절대 규칙 2 의 금지어를 쓰지 않는다(`landPrice.test.ts` 가 글을 훑는다) — 공시가격이고 시세가 아님을 줄에 밝힌다.
*/

/** 줄 끝 꼬리말 — 이 건물이 선 땅의 값이고 공시가격이지 시세가 아니라는 **값의 성질**(신뢰도 변명이 아니다). */
export const LAND_PRICE_NOTE = '(이 건물이 선 땅 · 공시가격 — 시세가 아닙니다)';

/**
 * 줄 앞 배지(👤 결정 0036 결정 7 보완). 기준시가 줄의 `grade__badge` 「A등급 · 공식 고시」와 같은 꼴이다 —
 * 국세청 기준시가는 '고시', 개별공시지가는 '공시'(낱말이 다르다 — 바꾸지 않는다).
 */
export const LAND_PRICE_BADGE = 'A등급 · 공식 공시';

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
 * ㎡당 금액 글(👤 결정 0036 결정 7 보완).
 *
 * - 10만원 미만 = 원 단위 그대로 `14,999원`(만원으로 뭉개면 `1만원` 이 되어 값이 달라 보인다)
 * - 10만원 이상 = 만원 아래 반올림 `4,523만원`
 * - 반올림한 값이 1억원 이상 = `1억 8,840만원` · 만 자리가 0 이면 `2억원`
 * ⓘ 억으로 넘길지는 **만원으로 반올림한 뒤에** 정한다 — 99,995,000원을 만 단위로 두면 `10,000만원` 이 된다.
 */
export function formatLandPriceAmount(won: number): string {
  if (Math.abs(won) < 100_000) return `${Math.round(won).toLocaleString('ko-KR')}원`;
  const man = Math.round(won / 10_000);
  if (man < 10_000) return `${man.toLocaleString('ko-KR')}만원`;
  const eok = Math.floor(man / 10_000);
  const rest = man % 10_000;
  return rest === 0
    ? `${eok.toLocaleString('ko-KR')}억원`
    : `${eok.toLocaleString('ko-KR')}억 ${rest.toLocaleString('ko-KR')}만원`;
}

/** 화면에 그릴 한 줄(배지 `LAND_PRICE_BADGE` 는 따로 — 화면이 배지 꼴로 앞에 단다). */
export function landPriceText(v: ParcelLandPrice): string {
  return `개별공시지가 땅 1㎡당 ${formatLandPriceAmount(v.land_price)} · ${v.land_price_year}년 공시 ${LAND_PRICE_NOTE}`;
}
