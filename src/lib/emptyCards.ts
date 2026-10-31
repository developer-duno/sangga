import { topicJosa } from './buildingHead';
import { sidoNameOfPnu } from './openClose';

/**
 * 빈 카드 셋(업종별 추정매출 · 유동인구 · 이 자리 가게 이력)의 **글**만 모은다(결정 0036 결정 2 ·
 * 물결 1-B · 👤 2026-10-11 문구 그대로).
 *
 * ⛔ **아무것도 부르지 않는다** — 자료가 아직 없으니 물을 곳도 없다. 서버 함수·`sidePrefetch` 0.
 *    자료가 들어오면(물결 2-5 가게 이력 · 3-1 서울 매출·유동인구 · 3-6 상주 인구) 그 카드가 제 컴포넌트로
 *    바뀌고 이 글은 그 카드에서 빠진다.
 * ⓘ 서울 건물의 sales·pop 은 2026-10-31 부터 제 컴포넌트(PR③ · `SalesSection`·`PopSection`) — 이 글은 서울 밖 건물과 가게 이력만.
 * ⛔ **'공식 자료가 없다'고 쓰지 않는다**(결정 0036 표 1-B) — 대전에도 SGIS·소상공인365 같은 길이 있다.
 *    아는 것은 "서울시 자료는 서울만이고, 그 지역은 아직 우리가 안 받았다"까지다.
 * ⛔ 지역 이름을 박지 않는다 — 개업·폐업 카드와 같은 길(pnu 앞 두 자리 → `regions.ts` 의 `SIDOS`).
 */

/** 빈 카드 셋의 열쇠(= `SECTION_PLAN` 의 칸 이름). */
export type EmptyCardKey = 'sales' | 'pop' | 'history';

/** 접힌 요약(앞)과 펼친 본문(뒤). */
export type EmptyCardText = { summary: string; body: string };

/** 셋 공통 접힌 요약. */
export const EMPTY_SUMMARY = '지금은 비어 있음';

/** 서울 건물 · 지역과 무관한 카드의 본문(👤 2026-10-11 글자 그대로). */
const BODY: Record<EmptyCardKey, string> = {
  sales: `${EMPTY_SUMMARY} — 서울시가 상권마다 공표하는 업종별 추정매출을 받으면 이 자리에 그대로 싣습니다`,
  pop: `${EMPTY_SUMMARY} — 상권 유동인구와 상권 안 상주 인구를 받으면 따로 줄로 싣습니다`,
  history: `${EMPTY_SUMMARY} — 분기마다 받는 점포 자료가 쌓이면 이 땅에 어떤 가게가 몇 분기 있었는지 보여 줍니다`,
};

/**
 * 서울시 자료로만 채울 카드. 가게 이력은 전국 점포 분기 자료로 채우므로 지역과 무관하다.
 * ⓘ 유동인구 카드의 상주 인구(SGIS)는 대전 먼저지만(결정 0036 표 3-6) 지금은 아무것도 안 받았다 —
 *   대전 글은 결정 0036 표 1-B 그대로 매출·유동인구 둘에 같다.
 */
const SEOUL_ONLY: readonly EmptyCardKey[] = ['sales', 'pop'];

/**
 * 서울시 자료가 다루는 시·도의 짧은 이름 — pnu 앞 두 자리 `11` 을 개업·폐업 카드와 같은
 * `sidoNameOfPnu` 로 읽어 `SIDOS` 표에서 고른다(이름을 여기 적지 않는다).
 */
const SEOUL_NAME = sidoNameOfPnu('11');

/**
 * 이 카드·이 필지의 글. 서울 건물이거나 지역과 무관한 카드면 "지금은 비어 있음 — …",
 * 서울 밖 건물의 매출·유동인구면 "서울시 자료는 서울만 — ○○은 아직 받지 않았습니다".
 * ⓘ 표에 없는 지역(코드 모름)은 이름 대신 '이 지역'.
 */
export function emptyCardText(key: EmptyCardKey, pnu: string): EmptyCardText {
  const sido = sidoNameOfPnu(pnu);
  if (!SEOUL_ONLY.includes(key) || (sido !== null && sido === SEOUL_NAME)) {
    return { summary: EMPTY_SUMMARY, body: BODY[key] };
  }
  const who = sido ?? '이 지역';
  const tail = `${who}${topicJosa(who)} 아직 받지 않았습니다`;
  return { summary: tail, body: `서울시 자료는 서울만 — ${tail}` };
}
