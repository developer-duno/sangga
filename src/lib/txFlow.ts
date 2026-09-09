import { TX_MIN_SAMPLE } from './appConstants';
import { formatMonthKo } from './format';
import type { SigunguTxYearly } from '../types';

/**
 * 『동네 매매 단가 흐름』 카드의 **순수 계산**만 모은다(결정 0027).
 *
 * ⛔ **자료 범위를 글자로 박지 않는다.** 첫 달·끝 달·건수는 전부 서버가 주는 값이다.
 *    한 번 옮겨 적으면 자료를 더 받은 날 화면만 옛 범위를 말하는데, 그것은 에러가 아니라
 *    **조용한 거짓말**이다. 그 사실을 `txFlow.test.ts` 가 정규식으로 지킨다(주석까지 훑는다 —
 *    주석에 박힌 연도는 다음 사람이 그대로 화면으로 옮긴다). 자료가 시작되는 시점·지번이
 *    열린 시점을 말해야 하면 상수 이름(`TX_BASEMENT_MISSING_SINCE`·`TX_OPEN_SINCE_LABEL`)
 *    으로만 말한다.
 *
 * ⛔ **없는 해를 만들지 않는다.** 서버는 자료가 있는 해만 주고, 화면도 그대로 그린다.
 *    빈 해를 0 으로 채우면 "그 해에는 한 건도 안 팔렸다"가 되는데, 실제로는 우리 창고에
 *    그 해 자료가 없는 것뿐이다.
 */

/* ── 서버 답의 모양 ──────────────────────────────────────────────────────── */

function isNullableNumber(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'number';
}

function isNullableString(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'string';
}

/**
 * 한 줄의 **모양**을 본다.
 *
 * 타입 단언(`as SigunguTxYearly[]`)은 컴파일 때만 사는 약속이라 런타임에는 아무것도 막아
 * 주지 않는다. 뜻밖의 답이 렌더로 흘러 들어가면 그 자리에서 터지는데, 이 카드는 **입구**에
 * 있어 터지면 검색창·지역 고르개까지 함께 사라진다(성적표 카드와 같은 이유).
 */
export function isSigunguTxYearlyRow(x: unknown): x is SigunguTxYearly {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.yr === 'string' &&
    typeof r.n === 'number' &&
    typeof r.n_all === 'number' &&
    isNullableNumber(r.median_unit_price) &&
    isNullableNumber(r.p25_unit_price) &&
    isNullableNumber(r.p75_unit_price) &&
    // ⚠️ 선택 칸이다 — 없어도(undefined) 통과한다. 마이그레이션 적용 전 라이브의 함수가
    //    그 상태라, 여기서 필수로 두면 그날 카드가 통째로 사라진다.
    isNullableNumber(r.median_area_m2) &&
    typeof r.floor_missing === 'number' &&
    typeof r.ym_cnt === 'number' &&
    isNullableString(r.first_ym) &&
    isNullableString(r.last_ym) &&
    isNullableString(r.sigungu_nm)
  );
}

/** ⓘ 빈 배열은 모양으로는 정상이다 — "그 구 자료가 아직 없다"는 뜻이라 화면이 가른다. */
export function isSigunguTxYearlyList(x: unknown): x is SigunguTxYearly[] {
  return Array.isArray(x) && x.every(isSigunguTxYearlyRow);
}

/* ── 한 줄을 어떻게 읽을 것인가 ──────────────────────────────────────────── */

/** 값을 적어도 되는 해인가(절대 규칙 3 의 미표시 원칙). */
export function hasEnoughSample(r: SigunguTxYearly): boolean {
  return r.n >= TX_MIN_SAMPLE;
}

/**
 * 층이 빈 거래의 비율(%). 분모가 0 이면 **null** 이다.
 *
 * ⛔ 분모가 없을 때 0 을 돌려주면 안 된다 — "층이 다 있다"는 정반대 뜻이 된다.
 */
export function missingRatePct(r: SigunguTxYearly): number | null {
  return r.n_all > 0 ? Math.round((r.floor_missing / r.n_all) * 100) : null;
}

/**
 * 그 해 단가의 근거가 된 거래 **한 건의 크기**('40㎡'). 적을 수 없으면 null.
 *
 * 왜 이 칸을 나란히 적나
 * ----------------------
 * 어떤 해는 ㎡당 가운데값이 앞뒤 해의 두세 배로 튀는데, 시세가 그만큼 오른 것이 아니라
 * **초소형 구획이 무더기로 거래된 해**여서 그렇다(작은 칸일수록 ㎡당 단가가 높다). 면적
 * 중앙값을 나란히 적으면 기준선을 하나도 안 긋고 그 사실이 눈에 보인다 — 옆에 이미 있는
 * '층 미상 %'와 같은 방식이다.
 *
 * ⛔ **없으면 지어내지 않는다.** 서버가 이 칸을 안 주는 판(마이그레이션 전)이 있고, 그때는
 *    이 조각만 빠지고 줄은 그대로 선다.
 * ⛔ **0㎡ 라고 적지 않는다.** 반올림해서 0 이 되는 값은 면적이 아니라 자료의 고장이고,
 *    '0㎡ 짜리 거래'라고 적으면 없는 사실을 말하게 된다.
 */
export function medianAreaText(r: SigunguTxYearly): string | null {
  const v = r.median_area_m2;
  if (v === null || v === undefined || !Number.isFinite(v)) return null;
  const m2 = Math.round(v);
  return m2 >= 1 ? `${m2.toLocaleString('ko-KR')}㎡` : null;
}

/**
 * 해의 일부만 있는 해에 붙이는 꼬리표('9~12월분'). 온전한 해면 null.
 *
 * 첫 해와 올해는 자료가 몇 달치뿐인데 그냥 그리면 "그 해에는 이만큼 팔렸다"로 읽힌다 —
 * 다른 해와 나란히 서는 자리라 특히 그렇다.
 *
 * ⛔ **가운데가 비어 있는 해를 이어 붙이지 않는다.** 첫 달 1월·끝 달 12월인데 실제로는
 *    열 달치뿐인 해가 있다(거래가 아예 없던 달은 서버가 주지 않는다). 그걸 '1~12월분'이라
 *    적으면 열두 달이 다 있는 해와 글자가 똑같아져, 꼬리표를 붙인 이유가 사라진다.
 *    양 끝의 폭과 실제 달수가 다르면 **둘 다** 적는다 — '1~12월 중 10개월분'.
 */
export function partialYearLabel(r: SigunguTxYearly): string | null {
  if (r.ym_cnt >= 12 || !r.first_ym || !r.last_ym) return null;
  const a = Number(r.first_ym.slice(4, 6));
  const b = Number(r.last_ym.slice(4, 6));
  if (!Number.isFinite(a) || !Number.isFinite(b) || a < 1 || b < 1) return null;
  if (b - a + 1 !== r.ym_cnt) return `${a}~${b}월 중 ${r.ym_cnt}개월분`;
  return a === b ? `${a}월분` : `${a}~${b}월분`;
}

/* ── 막대 ────────────────────────────────────────────────────────────────── */

/**
 * 막대의 눈금이 될 가장 큰 중앙값. 잴 것이 없으면 0.
 *
 * ⛔ **표본이 모자란 해는 기준에서 뺀다.** 안 적을 값이 눈금을 정하면, 화면에 수치가
 *    안 보이는 해가 다른 모든 해의 막대를 조용히 짓눌러 그림을 통째로 왜곡한다.
 */
export function maxMedian(rows: readonly SigunguTxYearly[]): number {
  let max = 0;
  for (const r of rows) {
    if (!hasEnoughSample(r)) continue;
    const v = r.median_unit_price;
    if (v !== null && Number.isFinite(v) && v > max) max = v;
  }
  return max;
}

/**
 * 막대 폭(%). 값을 안 적는 해는 **0** 이다 — 값을 감추면서 막대만 남기면 값을 말한 것과 같다.
 */
export function barWidthPct(r: SigunguTxYearly, max: number): number {
  if (max <= 0 || !hasEnoughSample(r)) return 0;
  const v = r.median_unit_price;
  if (v === null || !Number.isFinite(v)) return 0;
  return Math.round((v / max) * 100);
}

/* ── 접혀 있어도 보이는 한 줄 ────────────────────────────────────────────── */

/**
 * 요약 한 줄 — "언제부터 언제까지 · 몇 건 · 무엇을 잰 값인가".
 *
 * 범위는 **서버가 준 첫 달·끝 달**로 적는다. 달 표기를 읽을 수 없으면(`formatMonthKo` 가
 * null 을 준다) 그 부분만 빼고 나머지를 세운다 — 지어내지 않고, 그렇다고 줄 전체를
 * 버리지도 않는다.
 */
export function flowSummary(rows: readonly SigunguTxYearly[]): string {
  const from = formatMonthKo(rows[0]?.first_ym ?? null);
  const to = formatMonthKo(rows[rows.length - 1]?.last_ym ?? null);
  const total = rows.reduce((sum, r) => sum + r.n_all, 0);
  const range = from !== null && to !== null ? `${from} ~ ${to}` : null;
  return [range, `집합상가 매매 ${total.toLocaleString('ko-KR')}건`, '해마다 ㎡당 중앙값']
    .filter((s): s is string => s !== null)
    .join(' · ');
}
