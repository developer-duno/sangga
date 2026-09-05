/**
 * 둘레의 **새로 올라오는 상가 건물** 한 줄의 순수 계산.
 *
 * ⛔ **업종 분포와 같은 카드에 서지만 다른 자료다.** 저쪽은 지금 장사 중인 가게 수(점포),
 *    이쪽은 아직 다 안 지어진 건물 수(동)다. 그래서 `industryMix.ts` 에 섞지 않고 갈라 둔다
 *    — `basePrice.ts` 를 `priceBand.ts` 와 갈라 둔 것과 같은 이유다(한 파일에 두면 다음
 *    사람이 두 숫자를 더하거나 견주는 계산을 얹게 된다).
 *
 * ⚠️ 여기서는 **어림하지 않는다.** 공식 인허가 기록을 그대로 나르고, 화면에 적으면 안 되는
 *    경우만 걸러 낸다. "곧 완공"·"예정" 같은 앞일 단정을 이 파일이나 화면에 넣지 말 것 —
 *    허가를 받고도 안 짓거나 용도가 바뀌는 일이 흔하다.
 */

import type { NearbyPermits } from '../types';
import { formatMonthKo } from './format';

/** 화면에 그릴 한 줄. 여기 있는 값은 전부 **그대로 적어도 되는** 것만 남은 상태다. */
export type NearbyPermitLine = {
  /** 미준공 상업 계열 인허가 건물 수(동). */
  total: number;
  /** 그중 실착공까지 간 것. */
  started: number;
  /** 허가만 받고 아직 안 판 것 = `total - started`. */
  permitOnly: number;
  /**
   * 그중 **기준월 말일 기준으로 허가 후 2년 넘게 착공 기록이 없는** 것. 못 적을 때는 `null`.
   *
   * ⛔ **"실효됐다"가 아니다.** 원본에 실효 칸이 없어, 아는 것은 "착공 기록이 없다"까지다.
   * ⚠️ `null` 이 되는 두 경우 — ①서버가 아직 그 칸을 안 준다(2026-09-05b 이전 라이브)
   *    ②값이 말이 안 된다(음수·`permitOnly` 초과). 둘 다 **그 문장만** 빠지고 줄은 그대로
   *    선다 — 있는 사실(전체·착공)까지 같이 버릴 이유가 없다.
   */
  stale: number | null;
  /** '2026년 7월'. 이 값이 없으면 줄을 아예 안 만든다(아래 참조). */
  baseLabel: string;
};

function isNearbyPermits(x: unknown): x is NearbyPermits {
  if (typeof x !== 'object' || x === null) return false;
  const p = x as Record<string, unknown>;
  return (
    typeof p.total_cnt === 'number' &&
    typeof p.started_cnt === 'number' &&
    typeof p.base_ym === 'string'
  );
}

/**
 * 서버 응답 한 덩어리를 화면 한 줄로. **적으면 안 되는 경우는 전부 null** 이고,
 * null 이면 화면은 그 줄만 조용히 뺀다(카드의 나머지는 그대로 선다).
 *
 * 왜 `unknown` 을 받나 — 이 한 함수가 **모양 검사까지** 맡기 때문이다. 서버가 이 값을
 * 한 행짜리 목록(`[{…}]`)으로 줄지 객체 하나로 줄지는 함수를 `returns table` 로 쓰느냐
 * `returns json` 으로 쓰느냐에 달렸는데, 그 차이는 **라이브에서만** 드러난다(목은 우리가
 * 적어 준 모양을 그대로 돌려주므로 어느 쪽으로 틀려도 시험은 초록이다). 그래서 둘 다 받는다.
 *
 * 안 적는 경우 넷:
 *  · 0동 — 셀 것이 없다. "0동"이라 적으면 "이 둘레는 아무것도 안 짓는 곳"이라는 없는
 *    사실이 생긴다(빈 0 표시 금지 — 절대 규칙 3의 결).
 *  · 모양이 뜻밖 — 함수가 아직 없거나 옛 판 응답이다.
 *  · 착공 수가 전체보다 크거나 음수 — 쪼갤 수 없는 수를 억지로 쪼개면 '허가만 -3동'이 나온다.
 *  · 기준월을 못 읽음 — **언제 것인지 모르는 개수는 적지 않는다.** 인허가는 시간이 갈수록
 *    쌓이고 준공되면 빠지는 값이라, 기준 시점이 빠지면 숫자만 남아 근거가 사라진다
 *    (절대 규칙 3 — 값과 근거는 한 몸).
 */
export function toPermitLine(data: unknown): NearbyPermitLine | null {
  const row = Array.isArray(data) ? (data.length > 0 ? data[0] : null) : data;
  if (!isNearbyPermits(row)) return null;

  const total = row.total_cnt;
  const started = row.started_cnt;
  if (!Number.isFinite(total) || total <= 0) return null;
  if (!Number.isFinite(started) || started < 0 || started > total) return null;

  const baseLabel = formatMonthKo(row.base_ym);
  if (baseLabel === null) return null;

  const permitOnly = total - started;
  return { total, started, permitOnly, stale: toStale(row.stale_cnt, permitOnly), baseLabel };
}

/**
 * '오래 멈춰 있는 것'의 수. **줄 전체를 버리지 않는다** — 못 믿을 때는 이 조각만 `null` 이다.
 *
 * 위쪽 검사들과 다루는 태도가 다른 이유: 전체·착공은 **문장의 뼈대**라 어긋나면 문장이
 * 통째로 거짓이 되지만, 이 수는 **덧붙이는 한 문장**이라 빼도 남는 말이 여전히 참이다.
 *
 * 안 적는 경우 셋:
 *  · 서버가 안 준다 — 2026-09-05b 이전 라이브. 옛 응답이 새 화면을 깨뜨리면 안 된다.
 *  · 숫자가 아니거나 음수 — '-3동이 멈춰 있다'는 말은 없다.
 *  · `permitOnly`(= 전체 − 착공)보다 크다 — 착공한 것은 세지 않는 수라 그럴 수 없다.
 *    그런데도 크게 왔다면 서버와 화면이 다른 것을 세고 있는 것이니 적지 않는다.
 */
function toStale(raw: unknown, permitOnly: number): number | null {
  if (typeof raw !== 'number' || !Number.isFinite(raw)) return null;
  if (raw < 0 || raw > permitOnly) return null;
  return raw;
}
