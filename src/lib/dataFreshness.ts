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

/**
 * '2026Q2' — 부동산원 분기 표기. '20262'(Q 없는 다섯 자리) — 서울시 상권분석서비스 분기 표기
 * (결정 0033 · 개업·폐업). 둘은 같은 분기라 **같은 글**로 적는다. 여섯 자리('202606')는
 * 마지막 자리가 1~4 앞에 한 자리가 더 있어 여기 안 걸리고 아래 RE_YM 으로 간다.
 */
const RE_QUARTER = /^(\d{4})Q?([1-4])$/;
/** '202606' — 상권정보 분기(분기말 달)·실거래 계약월·인허가 기준월이 다 이 모양이다. */
const RE_YM = /^(\d{4})(\d{2})$/;
/** '2026-08-27' — 적재일·계산일·수집일·고시일. */
const RE_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
/** '2026' — 필지 개별공시지가의 공시 연도(2026-10-12b · 서버가 smallint 를 글자로 준다). */
const RE_YEAR = /^(\d{4})$/;

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
 * ⛔ 모양이 넷(분기·여섯 자리·날짜·네 자리 연도) 중 어느 것도 아니면 **원본을 그대로** 적는다. 억지로 해석해 틀린 분기를
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

  const y = RE_YEAR.exec(raw);
  if (y) return `${y[1]}년`;

  return raw;
}

/**
 * 다음 갱신 예정을 사람이 읽는 글자로.
 *
 * ⛔ 값이 없으면 **'정해진 주기 없음'** 이다. 상권 경계·LH 는 정해진 주기가 없어
 *    서버가 일부러 null 을 준다(필지는 2026-10-12b · 실거래·건축물대장은 2026-10-15a 부터 서버가
 *    규칙으로 날짜를 준다) — 여기에 아무 날짜나 적으면 "늦었다"는 거짓 신호가 화면에 뜬다.
 *
 * ⚠️ **'무렵'을 붙인다.** 이 값은 규칙으로 계산한 예정일이지 약속된 날이 아니다. 자료가
 *    하루 이틀 늦게 올라오는 일이 흔한데, 딱 떨어지는 날짜로 적으면 그날 안 바뀐 것이
 *    고장처럼 보인다.
 *
 * ⛔ **예정일이 지났으면 지났다고 적는다**(👤 사장님 결정 2026-10-01). 지난 날짜를 그대로
 *    '무렵'으로 두면 지나간 날을 앞날처럼 말하게 된다. 날짜를 새로 지어내지도, 줄을 숨기지도
 *    않고 사실만 덧붙인다 — 칸 머리글이 이미 "다음 갱신 예정"이라 '예정'은 다시 안 적는다.
 *    예정일 **당일**은 아직 안 지났다(그날 안에 올라올 수 있다).
 *
 * ⚠️ **오늘은 밖에서 받는다**(`today` = 한국 날짜 'YYYY-MM-DD', `seoulToday()` 가 만든다).
 *    여기서 `new Date()` 를 부르면 시험이 실제 날짜에 묶여 날이 흐르면 저절로 빨개진다.
 *    둘 중 하나라도 'YYYY-MM-DD' 모양이 아니면 지남 판정을 하지 않는다 — 같은 모양일 때만
 *    글자 비교가 날짜 비교와 같다.
 */
export function nextText(row: DataFreshnessRow, today: string): string {
  const raw = row.next_expected?.trim();
  if (!raw) return '정해진 주기 없음';

  const d = RE_DATE.exec(raw);
  if (!d) return raw;
  const month = Number(d[2]);
  const day = Number(d[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return raw;
  const text = `${d[1]}년 ${month}월 ${day}일 무렵`;
  // ⛔ '갱신'과 '전' 사이는 줄바꿈 없는 공백(U+00A0) — 보통 공백이면 휴대폰 폭에서
  //    '전' 한 글자만 다음 줄로 넘어간다(word-break: keep-all 은 공백에서만 끊는다).
  return RE_DATE.test(today) && raw < today ? `${text} — 지났습니다, 갱신\u00a0전` : text;
}

/**
 * **한국 날짜**의 오늘('YYYY-MM-DD').
 *
 * ⛔ 로컬 시각대에 기대지 않는다 — 이 PC 는 한국 시각이지만 CI 는 UTC 라, `toISOString()`
 *    이나 `getDate()` 로 자르면 한국 새벽 0~9시에 어제가 된다(서버 쪽도 같은 이유로
 *    `Asia/Seoul` 로 옮겨 자른다). 시각대를 못 박아 조각으로 받아 잇는다.
 */
export function seoulToday(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
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

/* ── 카드마다 '자료 이름 + 날짜' 한 줄 (S3 · 👤 2026-10-16) ─────────────────────────────── */

/**
 * 카드 제목 아래 한 줄이 가리키는 자료 갈래. 서버 표의 한 줄(`src`)과 짝이다.
 *
 * ⛔ 날짜·분기·판은 여기 없다 — 이름과 끝말만 있다. 값은 서버 줄의 `basis` 를 `basisText` 로 읽는다.
 * ⛔ 서버 줄을 **자료 이름 글자(`src`)로** 찾는다 — 서버(`get_data_freshness`)에서 이름을 바꾸면 그 조각이
 *    에러 없이 말없이 빠진다. 지키는 것은 `dataFreshness.test.ts` 의 정본(schema.sql) 이름 대조 시험이다.
 * ⓘ 필지(토지 특성)는 어느 카드에도 안 붙어 여기 없다(개별공시지가는 카드가 아니라 건물 머리 한 줄이다).
 *   LH 공고도 없다 — 날짜 줄을 빼기로 했다(👤 2026-10-16 B2 · 함께 뺀 참고 시세 성적표는 결정 0041 로 카드째 내렸다).
 */
export const CARD_SOURCES = {
  sangkwon: { src: '점포·업종 (상권정보)', label: '상권정보', ending: '' },
  // 👤 2026-10-16 B1 — 최근 두 달은 신고(30일)가 덜 끝난 채 들어 있다는 것을 끝말에 밝힌다(맨 아래 표 글은 그대로).
  tx: { src: '실거래 (매매)', label: '국토부 실거래', ending: ' 계약분까지 (최근 두 달은 신고 중)' },
  ledger: { src: '건축물대장', label: '건축물대장', ending: ' 판' },
  district: { src: '상권 경계', label: '상권 경계', ending: ' 계산' },
  permit: { src: '건축 인허가', label: '건축 인허가', ending: ' 기준' },
  nts: { src: '국세청 기준시가', label: '국세청 기준시가', ending: ' 고시' },
  rone: { src: '상권 임대 동향 (부동산원)', label: '부동산원', ending: ' 조사' },
  openclose: { src: '상권 개업·폐업 (서울시)', label: '서울시 상권분석서비스', ending: '' },
  // 결정 0044 — 대전 건물의 개업·폐업 카드 자리(「동네 폐업 (대전시 공표)」)만 이 갈래를 쓴다(`SECTION_PLAN` 에는 없다 —
  // 카드가 대전 답을 받았을 때 plan 을 바꿔 끼운다). 기준 = 사람이 대전시 사이트에서 받은 날.
  daejeon_closure: { src: '동네 폐업 (대전시)', label: '대전시 상권분석 서비스', ending: ' 받음' },
  // 결정 0045 PR② — 서울 상권 4종. 카드(PR③)가 아직 없어 지금은 어느 `SECTION_PLAN` 에도 안 붙는다.
  //   상주·직장 줄의 기준은 「상주 2023년 4분기, 직장 2024년 4분기」 같은 글이라 `basisText` 가 원본 그대로 적는다.
  sales: { src: '상권 추정매출 (서울시)', label: '서울시 상권분석서비스', ending: '' },
  pop_flow: { src: '상권 길단위인구 (서울시)', label: '서울시 상권분석서비스', ending: '' },
  // label 에 「상주」를 또 쓰면 기준 글(「상주 …, 직장 …」)과 겹쳐 두 번 나온다 — 출처 이름만.
  pop_people: { src: '상권 상주·직장인구 (서울시)', label: '서울시 상권분석서비스', ending: ' 값' },
} as const satisfies Record<string, { src: string; label: string; ending: string }>;

export type CardSourceKey = keyof typeof CARD_SOURCES;

/**
 * 카드 한 장의 날짜 줄 — '자료: 건축물대장 2026년 8월 판 · 상권정보 2026년 2분기'.
 *
 * ⛔ 표를 못 받았으면(null) **줄이 없다**(null). 모르는 것을 '자료 없음'이라 적지 않는다 — 맨 아래 표가
 *    이미 그 경우 통째로 빠진다(같은 규칙).
 * ⛔ 서버 표에 그 자료 줄이 없으면 **그 조각만** 뺀다. 조각이 하나도 안 남으면 줄이 없다.
 * ⓘ 줄은 있는데 기준값이 비었으면 맨 아래 표처럼 '자료 없음'(끝말은 안 붙인다 — '자료 없음 판'이 된다).
 */
export function cardSourceLine(
  keys: readonly CardSourceKey[] | undefined,
  rows: readonly DataFreshnessRow[] | null,
): string | null {
  if (!keys || keys.length === 0 || rows === null) return null;
  const pieces: string[] = [];
  for (const key of keys) {
    const s = CARD_SOURCES[key];
    const row = rows.find((r) => r.src === s.src);
    if (!row) continue;
    const has = Boolean(row.basis?.trim());
    pieces.push(`${s.label} ${basisText(row)}${has ? s.ending : ''}`);
  }
  return pieces.length > 0 ? `자료: ${pieces.join(' · ')}` : null;
}
