import type { LhNotice } from '../types';

/**
 * LH 상가 분양·입점 공고 카드의 **순수 계산**만 모은다.
 *
 * 컴포넌트에서 빼 둔 이유는 `industryMix.ts`·`priceBand.ts` 와 같다 — 여기 있는 규칙들은
 * 화면을 띄우지 않고도 시험할 수 있어야 하고, 실제로 틀리기 쉬운 곳이 전부 여기다
 * (시도 코드 자르기 · 시간대 · 서버 응답 모양 · 링크 주소).
 */

/**
 * 고른 구 코드에서 **시도 코드 두 자리**를 뽑는다('11680' → '11').
 *
 * 서버 함수 `list_lh_notices(p_sido)` 가 받는 것이 이 두 자리다.
 *
 * ⓘ 서버도 5자리를 받으면 앞 2자리만 보게 막아 두었다 — 두 겹이지만 겹치는 것이 낫다.
 *   기대는 계약대로 두 자리를 보내는 것이고, 어느 한쪽이 사라져도 화면이 조용히 빈손이
 *   되지 않는다. 목(mock)은 인자 값을 안 보므로 화면 쪽이 무너지면 시험은 전부 초록인 채
 *   라이브만 달라진다 — 그래서 자르는 규칙을 여기 한 곳에 두고 시험으로 못 박는다.
 *
 * ⚠️ 다섯 자리 숫자가 아니면 **null 을 준다.** 아무 문자열이나 앞 두 글자를 잘라 보내면
 *    서버가 뜻 모를 값을 받게 되고, 그때 돌아오는 빈손을 화면은 "공고 없음"으로 읽는다.
 */
export function sidoOf(sigungu: string | null | undefined): string | null {
  if (!sigungu) return null;
  const s = sigungu.trim();
  return /^\d{5}$/.test(s) ? s.slice(0, 2) : null;
}

/**
 * (내부) 날짜를 연·월·일로. 시각이 붙은 값은 보는 사람의 시계로, 날짜만 있는 값은 적힌
 * 그대로 — `monthDay` 가 쓰던 규칙 그대로다.
 *
 * ⛔ 이 해석을 두 벌로 복제하지 않는다. 마감일에 연도를 붙이려면 연도도 같은 규칙으로
 *    읽어야 하는데, 규칙이 두 군데면 한쪽만 고쳐지는 날 월·일과 연도가 서로 다른 시계를
 *    말하게 된다(자정 언저리에 "2026년 1월 1일"이 아니라 "2025년 1월 1일"이 된다).
 */
function parseDate(
  value: string | null | undefined,
): { year: number; month: number; day: number } | null {
  if (!value) return null;
  const s = value.trim();
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (!m) return null;
  if (s.includes('T')) {
    const at = new Date(s);
    if (!Number.isNaN(at.getTime()))
      return { year: at.getFullYear(), month: at.getMonth() + 1, day: at.getDate() };
    // 시각이 붙어 있는데 못 읽었으면 날짜 부분만이라도 살린다(아래로 떨어진다).
  }
  return { year: Number(m[1]), month: Number(m[2]), day: Number(m[3]) };
}

/**
 * 날짜를 '9월 17일'로. 읽을 수 없으면 **null**(빈 글자도 '—'도 아니다).
 *
 * 왜 `format.ts` 가 아닌가 — 저기 함수들은 못 읽으면 '—' 를 준다. 여기서는 값이 없을 때
 * 문장이 통째로 달라진다("~9월 17일" ↔ "마감일 미정"), 그래서 부르는 쪽이 갈라 쓸 수
 * 있도록 null 을 준다.
 *
 * ⚠️ **시각이 붙은 값(timestamptz)과 날짜만 있는 값을 갈라 다룬다.**
 *  · 시각이 있으면 보는 사람의 시계로 옮겨 적는다 — 자정 언저리에 수집한 것이 UTC 기준
 *    그대로면 하루 전으로 보인다.
 *  · 날짜만 있으면 **적힌 그대로** 쓴다. `new Date('2026-09-17')` 은 UTC 자정으로 읽혀,
 *    한국보다 뒤진 시간대에서는 16일로 밀린다(마감일이 하루 당겨져 보인다).
 */
export function monthDay(value: string | null | undefined): string | null {
  const d = parseDate(value);
  return d ? `${d.month}월 ${d.day}일` : null;
}

/**
 * 받아 둔 시각 중 **가장 최신**의 원본 문자열. 하나도 못 읽으면 null.
 *
 * ⚠️ 글자끼리 비교하지 않는다 — 같은 시각이라도 시간대 표기가 다르면('…Z' vs '…+09:00')
 *    글자 순서와 실제 앞뒤가 어긋난다. 시각으로 바꿔 비교하되 **돌려주는 것은 원본**이라
 *    표기 방식을 우리가 바꾸지 않는다.
 */
export function latestCollectedAt(notices: readonly LhNotice[]): string | null {
  let best: string | null = null;
  let bestMs = Number.NEGATIVE_INFINITY;
  for (const n of notices) {
    const ms = Date.parse(n.collected_at);
    if (Number.isNaN(ms)) continue;
    if (ms > bestMs) {
      bestMs = ms;
      best = n.collected_at;
    }
  }
  return best;
}

/**
 * 목록을 **그 지역 공고**와 **LH 가 '전국'이라 적은 공고**로 가른다(결정 0026).
 *
 * ⛔ `is_nationwide` 는 '지역 칸이 비었다'가 아니라 **LH 가 '전국'이라 적었다**는 뜻이다
 *    (수집기 `map_sido`: 빈 칸은 false). 그런데 그렇게 적힌 공고의 제목은 대개 특정
 *    도시라(2026-09-05 실측 서울 39줄 중 35줄) 그대로 섞어 두면 "이 지역 공고"라 해 놓고
 *    남의 도시를 보여 주게 된다.
 * ⛔ **제목에서 도시를 뽑아 옮기지 않는다.** 지명이 안 든 제목·같은 이름의 다른 동네에서
 *    조용히 틀리는데, 틀린 지역표는 없는 것보다 나쁘다(사용자가 믿고 헛걸음한다).
 * ⓘ `true` 인 것만 접는다 — 값이 없거나(05c 이전 라이브) null 이면 전부 regional 로 가므로
 *   화면이 지금까지와 **똑같이** 동작한다.
 */
export function splitByRegion(notices: readonly LhNotice[]): {
  regional: LhNotice[];
  nationwide: LhNotice[];
} {
  const regional: LhNotice[] = [];
  const nationwide: LhNotice[] = [];
  for (const n of notices) (n.is_nationwide === true ? nationwide : regional).push(n);
  return { regional, nationwide };
}

/**
 * 접혀 있어도 보이는 한 줄 — "3건 · 8월 27일 수집 기준",
 * 접힌 묶음이 있으면 "4건 · 전국 표시 35건 · 9월 1일 수집 기준".
 *
 * ⛔ **수집 시각을 감추지 않는다.** 공고는 마감이 있는 자료라 "언제 받아 둔 것인가"가
 *    건수만큼 중요하다. 다만 그 시각을 못 읽으면 없는 날짜를 지어내지 않고 그 조각만 뺀다.
 * ⚠️ **0 인 조각은 뺀다.** "0건 · 전국 표시 35건"이라 적으면 접힌 것만 있는 지역에서 카드가
 *    비어 보인다. 반대로 접힌 것이 없으면 예전과 글자 하나까지 같은 한 줄이 된다.
 */
export function lhSummary(notices: readonly LhNotice[]): string {
  const { regional, nationwide } = splitByRegion(notices);
  const pieces: string[] = [];
  if (regional.length > 0 || nationwide.length === 0)
    pieces.push(`${regional.length.toLocaleString('ko-KR')}건`);
  if (nationwide.length > 0)
    pieces.push(`전국 표시 ${nationwide.length.toLocaleString('ko-KR')}건`);
  const day = monthDay(latestCollectedAt(notices));
  if (day) pieces.push(`${day} 수집 기준`);
  return pieces.join(' · ');
}

/**
 * "정정·재게시 N회" — 같은 공고가 여러 번 올라온 줄에만 붙는 꼬리표. 아니면 null.
 *
 * ⚠️ **정수이고 0보다 클 때만** 적는다. 05c 이전 라이브는 이 값을 안 주고(undefined·null),
 *    0 은 "재게시 없음"이며, 음수·NaN 은 서버가 뜻밖의 값을 준 경우다 — 어느 쪽이든
 *    "0회"·"NaN회" 같은 말을 지어내지 않고 그 자리를 비운다.
 */
export function dupText(n: LhNotice): string | null {
  const c = n.dup_cnt;
  if (typeof c !== 'number' || !Number.isInteger(c) || c <= 0) return null;
  return `정정·재게시 ${c.toLocaleString('ko-KR')}회`;
}

/**
 * 마감일 한 조각 — 올해 마감이면 '~9월 17일', 다른 해면 '~2027년 6월 30일'. 없으면
 * '마감일 미정'.
 *
 * ⚠️ **올해가 아닐 때만 연도를 적는다.** 올해 마감에 연도는 소음이지만, 내년 마감을 연도
 *    없이 적으면 **이미 지난 날짜처럼 읽힌다** — 2026-08-30 라이브 실측: 마감이
 *    2027-06-30 인 청주모충2 공고가 "~6월 30일"로 보여 두 달 전에 끝난 공고로 오해됐다.
 *    지난 해도 같다(낡은 공고가 올해 것처럼 보이면 안 된다).
 *
 * ⛔ 지금 시각을 **인자로 받지 않는다.** 시계를 주입받게 만들면 시험만 가짜 시계를 믿게
 *    되고, 정작 실제 시계로 그리는 화면은 아무도 안 보게 된다(글로벌 시간대 규칙의 실사고).
 */
export function closeText(closeDate: string | null | undefined): string {
  const d = parseDate(closeDate);
  if (!d) return '마감일 미정';
  const head = d.year === new Date().getFullYear() ? '' : `${d.year}년 `;
  return `~${head}${d.month}월 ${d.day}일`;
}

/**
 * 링크로 만들어도 되는 주소인가.
 *
 * 서버가 준 값이라도 화면이 `href` 로 그대로 넘기기 전에 한 번 본다 — `javascript:` 같은
 * 주소가 섞여 들어오면 누르는 순간 남의 코드가 우리 화면에서 돈다. 우리가 모은 자료라
 * 그럴 일이 없다고 **믿는 대신**, 믿지 않아도 되게 한 줄로 막는다.
 */
export function isHttpUrl(url: string | null | undefined): url is string {
  return typeof url === 'string' && /^https?:\/\//i.test(url.trim());
}

function isNullableString(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'string';
}

/**
 * 05c 로 늘어난 칸들처럼 **있을 수도 없을 수도 있는** 값. 없으면 통과, 있으면 그 종류여야
 * 한다 — 없는 것(옛 라이브)과 **틀린 것**(다른 함수의 응답)은 다르게 다뤄야 하기 때문이다.
 *
 * ⚠️ **`null` 도 통과시킨다** — `pan_ss`·`dtl_url` 과 같은 태도다. 이 목록 검증은 `.every()`
 *    라서 한 줄만 거절해도 **카드가 통째로 사라지는데**, 서버가 어떤 이유로든 이 칸에 null 을
 *    실어 보내는 날 그 대가가 너무 크다. null 이면 `splitByRegion` 은 지역 공고로,
 *    `dupText` 는 꼬리표 없음으로 다룬다(둘 다 아래에서 값의 종류를 다시 본다).
 */
function isOptional(x: unknown, kind: 'boolean' | 'number'): boolean {
  return x === undefined || x === null || typeof x === kind;
}

/**
 * 서버 응답의 **모양**을 본다.
 *
 * 타입 단언(`as LhNotice[]`)은 컴파일 때만 사는 약속이라 런타임에는 아무것도 막아 주지
 * 않는다. 뜻밖의 답(마이그레이션 전 라이브의 오류 객체, 다른 함수의 응답)이 그대로
 * 렌더로 흘러 들어가면 그 자리에서 터지는데, 이 카드는 **입구**에 있어 터지면 검색창까지
 * 함께 사라진다 — 곁다리 하나 때문에 본체를 잃지 않는다.
 */
export function isLhNotice(x: unknown): x is LhNotice {
  if (typeof x !== 'object' || x === null) return false;
  const n = x as Record<string, unknown>;
  return (
    typeof n.pan_id === 'string' &&
    typeof n.pan_nm === 'string' &&
    typeof n.kind_nm === 'string' &&
    // ⚠️ pan_ss·dtl_url 은 DB 에서 nullable(text, NOT NULL 없음)이고 적재기
    //    (collect_lh_notices.py 의 record_to_row)가 실제로 NULL 을 쓴다. 문자열만
    //    통과시키면 그 값 하나 때문에 이 함수가 전체 목록을 거절하고(.every), 카드가
    //    통째로 사라진다 — notice_date·close_date 에 이미 쓰는 것과 같은 규칙으로 맞춘다.
    isNullableString(n.pan_ss) &&
    isNullableString(n.dtl_url) &&
    typeof n.collected_at === 'string' &&
    isNullableString(n.notice_date) &&
    isNullableString(n.close_date) &&
    // ⚠️ 05c 로 늘어난 두 칸은 **없어도 통과**시킨다 — 마이그레이션 전 라이브는 안 주는데,
    //    여기서 필수로 받으면 그 순간 목록 전체가 거절돼 카드가 통째로 사라진다(.every 구조).
    //    다만 **있는데 종류가 틀린 것**(다른 함수의 응답 등)은 거른다.
    isOptional(n.is_nationwide, 'boolean') &&
    isOptional(n.dup_cnt, 'number')
  );
}

/** ⓘ 빈 배열은 **정상**이다 — "지금 열린 공고가 없다"는 뜻이고, 그때 화면은 카드를 생략한다. */
export function isLhNoticeList(x: unknown): x is LhNotice[] {
  return Array.isArray(x) && x.every(isLhNotice);
}
