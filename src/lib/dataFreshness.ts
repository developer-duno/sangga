import type { DataFreshnessRow } from '../types';

/**
 * 화면 아래 "이 자료는 언제 것인가" 표의 **순수 계산**만 모은다. 2026-09-05d.
 *
 * ⛔ **이 파일에 날짜도 분기도 주기도 적혀 있지 않다.** 여기서 하는 일은 서버가 준 값을
 *    사람이 읽는 모양으로 바꾸는 것뿐이다. 신선도를 글자로 박아 두면 적재하는 순간부터
 *    그 글자만 거짓말을 한다 — 이 표가 존재하는 이유가 바로 그것을 없애는 것이다.
 *
 * ⛔ **`new Date()` 로 날짜 문자열을 읽지 않는다.** `new Date('2026-08-27')` 은 UTC 자정으로
 *    읽혀, 한국보다 뒤진 시간대에서는 26일로 밀린다(`lhNotices.ts` 가 같은 이유로 같은
 *    수법을 쓴다). 적힌 그대로를 적는다.
 */

/** '2026Q2' — 부동산원 분기 표기. */
const RE_QUARTER = /^(\d{4})Q([1-4])$/;
/** '202606' — 상권정보 분기(분기말 달)·실거래 계약월·인허가 기준월이 다 이 모양이다. */
const RE_YM = /^(\d{4})(\d{2})$/;
/** '2026-08-27' — 적재일·계산일·수집일·고시일·갱신일. */
const RE_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * 기준값을 사람이 읽는 글자로.
 *
 * 값이 없으면 **'자료 없음'** 이다 — 그 자료가 아직 한 행도 없다는 뜻이고, 줄을 빼는 대신
 * 그렇게 적는다(빼면 "그런 자료를 안 쓴다"로 읽힌다).
 *
 * ⚠️ **모양으로 먼저 가르고, 여섯 자리일 때만 종류를 본다.** '202606' 하나가 상권정보에서는
 *    분기(2026년 2분기)이고 실거래에서는 달(2026년 6월)이라, 그 한 자리에서만 `basis_kind`
 *    가 필요하다. 종류 목록을 여기에 죽 적어 두면 서버가 종류를 하나 늘리는 날 화면만
 *    옛 목록을 말한다.
 *
 * ⛔ 모양이 셋 중 어느 것도 아니면 **원본을 그대로** 적는다. 억지로 해석해 틀린 분기를
 *    말하는 것보다 낫다(`format.ts` 의 `formatQuarter` 와 같은 원칙).
 */
export function basisText(row: DataFreshnessRow): string {
  const raw = row.basis?.trim();
  if (!raw) return '자료 없음';

  const q = RE_QUARTER.exec(raw);
  if (q) return `${q[1]}년 ${Number(q[2])}분기`;

  const ym = RE_YM.exec(raw);
  if (ym) {
    const month = Number(ym[2]);
    if (month < 1 || month > 12) return raw;
    return row.basis_kind === '분기'
      ? `${ym[1]}년 ${Math.ceil(month / 3)}분기`
      : `${ym[1]}년 ${month}월`;
  }

  const d = RE_DATE.exec(raw);
  if (d) {
    const month = Number(d[2]);
    const day = Number(d[3]);
    if (month < 1 || month > 12 || day < 1 || day > 31) return raw;
    return `${d[1]}년 ${month}월 ${day}일`;
  }

  return raw;
}

/**
 * 다음 갱신 예정을 사람이 읽는 글자로.
 *
 * ⛔ 값이 없으면 **'정해진 주기 없음'** 이다. 실거래·건축물대장·상권 경계·LH·성적표·필지는
 *    정해진 주기가 없어 서버가 일부러 null 을 준다 — 여기에 아무 날짜나 적으면 "늦었다"는
 *    거짓 신호가 화면에 뜬다.
 *
 * ⚠️ **'무렵'을 붙인다.** 이 값은 규칙으로 계산한 예정일이지 약속된 날이 아니다. 자료가
 *    하루 이틀 늦게 올라오는 일이 흔한데, 딱 떨어지는 날짜로 적으면 그날 안 바뀐 것이
 *    고장처럼 보인다.
 */
export function nextText(row: DataFreshnessRow): string {
  const raw = row.next_expected?.trim();
  if (!raw) return '정해진 주기 없음';

  const d = RE_DATE.exec(raw);
  if (!d) return raw;
  const month = Number(d[2]);
  const day = Number(d[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return raw;
  return `${d[1]}년 ${month}월 ${day}일 무렵`;
}

function isNullableString(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'string';
}

/**
 * 서버 응답의 **모양**을 본다.
 *
 * 타입 단언(`as DataFreshnessRow[]`)은 컴파일 때만 사는 약속이라 런타임에는 아무것도 막아
 * 주지 않는다. 뜻밖의 답(마이그레이션 전 라이브의 오류 객체, 다른 함수의 응답)이 그대로
 * 렌더로 흘러 들어가면 그 자리에서 터지는데, 이 표는 **화면 맨 아래**에 있어 터지면
 * 면책 안내와 의견함까지 함께 사라진다.
 *
 * ⚠️ `basis`·`next_expected` 는 **null 이 정상**이다(자료가 0행인 갈래 · 주기가 없는 갈래).
 *    문자열만 통과시키면 그 한 줄 때문에 표 전체가 거부돼 통째로 사라진다 —
 *    `isLhNotice` 가 `pan_ss` 로 실제로 겪은 일이다.
 */
export function isDataFreshnessRow(x: unknown): x is DataFreshnessRow {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.src === 'string' &&
    typeof r.basis_kind === 'string' &&
    typeof r.cadence === 'string' &&
    isNullableString(r.basis) &&
    isNullableString(r.next_expected)
  );
}

/** ⓘ 빈 배열도 모양으로는 맞다 — 그때 화면은 표를 통째로 생략한다(빈 표는 소음이다). */
export function isDataFreshnessList(x: unknown): x is DataFreshnessRow[] {
  return Array.isArray(x) && x.every(isDataFreshnessRow);
}
