/** 화면 표시용 변환 모음. 계산은 하지 않고 보기 좋게만 바꾼다. */

import type { BuildingHit } from '../types';

const M2_PER_PYEONG = 3.305785;

/** 면적을 "520.3㎡ (157평)"으로. 값이 없으면 '—'. */
export function formatArea(m2: number | null | undefined): string {
  if (m2 === null || m2 === undefined || Number.isNaN(m2)) return '—';
  const pyeong = Math.round(m2 / M2_PER_PYEONG);
  return `${m2.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}㎡ (${pyeong.toLocaleString('ko-KR')}평)`;
}

/**
 * 층 번호를 사람이 읽는 표기로. DB 표기 규칙은 지상 n=n / 지하 n=-n / 옥탑=99이고
 * 0은 제약으로 존재하지 않는다(지하와 결측이 섞이는 것을 막기 위해).
 *
 * 원본 이름표(`floor_label`)가 있으면 그걸 우선한다 — 대장에 적힌 그대로가 제일 정확하다.
 */
export function formatFloor(floorNo: number, label: string | null): string {
  if (label && label.trim()) return label.trim();
  if (floorNo === 99) return '옥탑';
  if (floorNo < 0) return `지하 ${Math.abs(floorNo)}층`;
  return `${floorNo}층`;
}

/**
 * 분기 스냅샷 키 '202603' → '2026년 1분기'.
 *
 * 상권정보는 분기말 기준으로 배포된다(3·6·9·12월). 형식이 다르면 억지로 해석하지 않고
 * 원본을 그대로 보여준다 — 틀린 분기를 말하는 것보다 낫다.
 */
export function formatQuarter(ym: string | null | undefined): string {
  if (!ym) return '—';
  const s = ym.trim();
  const m = /^(\d{4})(\d{2})$/.exec(s);
  if (!m) return s;
  const month = Number(m[2]);
  if (month < 1 || month > 12) return s;
  return `${m[1]}년 ${Math.ceil(month / 3)}분기`;
}

/**
 * 비율(%)을 "N곳 중 1곳"의 N으로. 32.9 → 3.
 *
 * 비율이 0 이하이거나 숫자가 아니면 null을 준다 — 그 경우 화면은 "N곳 중 1곳" 문구
 * 자체를 만들지 않는다(1/0으로 만든 무한대를 화면에 내보내지 않기 위해).
 */
export function oneInEvery(pct: number | null | undefined): number | null {
  if (pct === null || pct === undefined || !Number.isFinite(pct) || pct <= 0) return null;
  return Math.round(100 / pct);
}

/**
 * 층 결측 비율 → 「약 3곳 중 1곳(32.9%)」(층별 화면 각주와 역할 요약 판의 1층 칸이 함께 쓴다 — 결정 0039 W2,
 * 2026-10-17 `FloorStack` 에서 옮김 · 글자 그대로). 비율이 값이 아니면 null(부르는 쪽이 문구를 정한다).
 * ⓘ 이 비율은 **서비스 지역 전체**(뷰 `v_coverage_stats`)의 값이다 — 이 건물의 층 미상 점포 수가 아니다.
 */
export function floorMissingPhrase(pct: number | null | undefined): string | null {
  const every = oneInEvery(pct);
  return every === null ? null : `약 ${every}곳 중 1곳(${pct}%)`;
}

/**
 * 금액(원)을 "3억 2,000만"으로. 값이 없으면 '—'.
 *
 * 실거래 금액은 억 단위가 흔해서 `320000000원`으로 찍으면 자릿수를 세게 된다.
 * 만원 미만은 버리지 않고 그대로 '원'으로 적는다 — 억·만이 모두 0인 소액 거래에서
 * 빈 문자열이 나오면 "금액 없음"처럼 보이기 때문이다.
 */
export function formatWon(won: number | null | undefined): string {
  if (won === null || won === undefined || !Number.isFinite(won)) return '—';
  const eok = Math.floor(won / 100_000_000);
  const man = Math.floor((won % 100_000_000) / 10_000);
  const parts: string[] = [];
  if (eok > 0) parts.push(`${eok.toLocaleString('ko-KR')}억`);
  if (man > 0) parts.push(`${man.toLocaleString('ko-KR')}만`);
  if (parts.length === 0) return `${Math.round(won).toLocaleString('ko-KR')}원`;
  return parts.join(' ');
}

/**
 * 단가(원)를 만원 단위로 반올림해 "380만"으로. 값이 없으면 '—'.
 *
 * ㎡당 단가는 백만 원대라 원 단위까지 적으면 읽히지 않는다. 1만 원 미만이면 반올림이
 * "0만"이 되어 값이 없는 것처럼 보이므로 그때만 원 단위로 적는다.
 */
export function formatManWon(won: number | null | undefined): string {
  if (won === null || won === undefined || !Number.isFinite(won)) return '—';
  if (Math.abs(won) < 10_000) return `${Math.round(won).toLocaleString('ko-KR')}원`;
  return `${Math.round(won / 10_000).toLocaleString('ko-KR')}만`;
}

// ── 추정 밴드의 금액 표기 (Stage B · 결정 0013) ─────────────────────────────
//
// `formatWon`(사실 표기)과 일부러 다른 자를 쓴다. 신고된 거래는 '2억 4,486만'처럼
// 적힌 그대로가 사실이지만, 추정값은 30% 언저리로 빗나가는 값이라 만원 자리까지 적으면
// 없는 정밀도를 주장하게 된다. 그래서 억은 소수 한 자리(1천만원 눈금)까지만 적는다.

const EOK = 100_000_000;

/** 1천만원 미만은 만원 눈금 그대로, 그 위는 백만원 눈금으로 뭉갠다. */
function manText(won: number): string {
  if (Math.abs(won) < 10_000_000) return formatManWon(won);
  return `${(Math.round(won / 1_000_000) * 100).toLocaleString('ko-KR')}만`;
}

/**
 * 억 단위 표기. 100억 이상은 소수를 떼고 적는다(그 자리에서 1천만원은 의미가 없다).
 *
 * ⛔ `toFixed()` 를 쓰지 않는다 — 천 단위 구분이 안 붙고 반올림 규칙도 다르다
 *    (`(1.005).toFixed(2) === '1.00'`). 이 파일의 다른 함수와 같이 toLocaleString 을 쓴다.
 */
function eokText(won: number): string {
  const e = won / EOK;
  return Math.abs(e) >= 100
    ? `${Math.round(e).toLocaleString('ko-KR')}억`
    : `${e.toLocaleString('ko-KR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}억`;
}

/**
 * 억으로 적을 크기인가.
 *
 * ⚠️ 단위는 **백만원으로 반올림한 뒤에** 정한다. 99,999,999원을 "억이 아니다"라고 보고
 *    만 단위로 뭉개면 `'10,000만'` 이라는 아무도 안 쓰는 표기가 나온다.
 */
function isEokScale(won: number): boolean {
  return Math.round(Math.abs(won) / 1_000_000) >= 100;
}

/**
 * 추정 총액의 폭을 '2.4억~6.2억'으로. 한쪽이라도 없으면 '—'(반쪽 밴드를 내지 않는다).
 *
 * ⚠️ 단위는 **큰 쪽이 정하고 두 끝에 똑같이** 적용한다. '9,800만~1.2억'처럼 섞으면
 *    눈으로 견줄 수가 없고, 표에서 `tabular-nums` 로도 세로줄이 안 맞는다.
 */
export function formatEokBand(
  low: number | null | undefined,
  high: number | null | undefined,
): string {
  if (low === null || low === undefined || !Number.isFinite(low)) return '—';
  if (high === null || high === undefined || !Number.isFinite(high)) return '—';
  const lo = Math.min(low, high);
  const hi = Math.max(low, high);
  const render = isEokScale(hi) ? eokText : manText;
  const a = render(lo);
  const b = render(hi);
  // 반올림하고 나면 두 끝이 같아지는 일이 흔하다(폭이 1천만원 안쪽). '2.4억~2.4억'은
  // 사람이 "아주 정확하다"로 읽으므로 그렇게 적지 않는다.
  return a === b ? `${a} 안팎` : `${a}~${b}`;
}

/** ㎡당 단가의 폭을 '747만~1,905만'으로. 한쪽이라도 없으면 '—'. */
export function formatManWonBand(
  low: number | null | undefined,
  high: number | null | undefined,
): string {
  if (low === null || low === undefined || !Number.isFinite(low)) return '—';
  if (high === null || high === undefined || !Number.isFinite(high)) return '—';
  const a = formatManWon(Math.min(low, high));
  const b = formatManWon(Math.max(low, high));
  return a === b ? `${a} 안팎` : `${a}~${b}`;
}

/**
 * 계약 시점 '202605' → '2026-05'. 형식이 다르면 원본을 그대로 준다.
 *
 * `formatQuarter`와 달리 분기로 뭉치지 않는다 — 실거래는 계약이 일어난 **그 달**이
 * 사실이고, 분기로 바꾸면 없는 정보를 더하거나(분기 경계) 있는 정보를 지운다.
 */
export function formatYearMonth(ym: string | null | undefined): string {
  if (!ym) return '—';
  const s = ym.trim();
  const m = /^(\d{4})(\d{2})$/.exec(s);
  if (!m) return s;
  const month = Number(m[2]);
  if (month < 1 || month > 12) return s;
  return `${m[1]}-${m[2]}`;
}

/**
 * 기준월 '202607' → '2026년 7월'. **읽을 수 없으면 null** 이다.
 *
 * ⚠️ 이 파일의 형제들(`formatQuarter`·`formatYearMonth`)과 달리 '—'나 원본을 되돌려 주지
 *    않는다. 이 값은 "언제 것인가"를 말하는 자리에만 쓰이는데, 그 자리에 '—'나 '202607'이
 *    박히면 문장이 "(— 인허가 기준)"이 되어 **읽는 사람에게 아무 뜻도 못 준다**. 부르는
 *    쪽이 null 을 보고 그 문구 자체를 안 만들 수 있게 갈라 준다(`oneInEvery` 와 같은 결).
 */
export function formatMonthKo(ym: string | null | undefined): string | null {
  if (!ym) return null;
  const m = /^(\d{4})(\d{2})$/.exec(ym.trim());
  if (!m) return null;
  const month = Number(m[2]);
  if (month < 1 || month > 12) return null;
  return `${m[1]}년 ${month}월`;
}

/**
 * 날짜 '2026-01-01' → '2026년 1월 1일'. **읽을 수 없으면 null**(`formatMonthKo` 와 같은 결 — 부르는 쪽이 원본을
 * 쓸지 문구를 뺄지 고른다). ⛔ `new Date()` 로 읽지 않는다 — UTC 자정으로 읽혀 뒤진 시간대에서 하루 밀린다.
 */
export function formatDayKo(date: string | null | undefined): string | null {
  if (!date) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date.trim());
  if (!m) return null;
  const month = Number(m[2]);
  const day = Number(m[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return `${m[1]}년 ${month}월 ${day}일`;
}

/** 사용승인일 '2003-05-14' → '2003년 5월'. 없으면 '—'. */
export function formatApproveDate(date: string | null): string {
  if (!date) return '—';
  const m = /^(\d{4})-(\d{2})/.exec(date);
  if (!m) return date;
  return `${m[1]}년 ${Number(m[2])}월`;
}

/**
 * 건물 스펙(연면적·용적률·건폐율·주차 · 건물 종류)에서 **값 대신 적는 말**.
 *
 * ⛔ 여기서 "0" 을 그대로 적으면 안 된다. 건축물대장은 안 적은 칸을 '0' 으로 준다 —
 *    롯데월드타워가 주차 0·건폐율 0 으로 들어와 있어 "정말 0" 과 "안 적힘" 을 값으로는
 *    갈라낼 수 없다. 갈라낼 수 없으면 둘 중 하나로 단정하지 않는 것이 맞다
 *    (로드맵 Wave 2 PR-B).
 * ⓘ "NULL 은 0행" 은 **현재 적재분(서울·대전 30개 구)의 관찰값**이지 구조적 보장이
 *    아니다 — 적재기는 결측을 NULL 로 쓴다(load_building_ledger.py 의 `_to_float`·
 *    `sum_parking`). [C] 전국 적재 뒤에는 다시 세어 볼 것. `describeSpec` 은 0 과 null 을
 *    **같은 말**로 돌려주므로, 어느 쪽이 오더라도 이 화면은 그대로 맞다.
 * ⓘ 층별 화면(FloorStack)과 중개사 검색 결과의 소유 구조 줄(`describeOwnership`)이 함께 쓴다
 *   (2026-10-11 FloorStack 에서 옮김) — 두 곳이 '미상'을 다르게 판정하면 같은 건물이 두 말을 한다.
 */
export const UNKNOWN_SPEC = '미상';

/** 주차 표기. */
export function formatParking(n: number): string {
  return `${n.toLocaleString('ko-KR')}대`;
}

/**
 * 건물 스펙 한 칸을 사람이 읽는 말로. 값이 아니면 무조건 "미상"이다.
 *
 * "값이 아닌 것" 셋을 **같은 말로** 돌려준다 — 없음(null)·미기재(0 이하)·오류(상한 초과).
 * 셋을 갈라 적으면 화면이 우리도 모르는 것을 아는 척하게 된다(예: 상한을 넘은 79,095%를
 * "이상값"이라 적으면, 그 건물의 건폐율이 아주 크다는 뜻으로 읽힌다).
 */
export function describeSpec(
  value: number | null | undefined,
  format: (n: number) => string,
  max?: number,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return UNKNOWN_SPEC;
  if (value <= 0) return UNKNOWN_SPEC;
  if (max !== undefined && value > max) return UNKNOWN_SPEC;
  return format(value);
}

/**
 * 건물 종류 — true '집합건물' · false '일반건물'(👤 2026-10-11 — '통건물' 쓰지 않음) · 그 밖은 null.
 * ⛔ null 을 '일반건물'로 읽지 않는다(결정 0036 결정 18 ⑦) — 모르는 것은 부르는 쪽이 '미상'으로 적는다.
 */
export function formatJiphap(v: boolean | null | undefined): '집합건물' | '일반건물' | null {
  if (v === true) return '집합건물';
  if (v === false) return '일반건물';
  return null;
}

/**
 * 승강기 대수 — **승용 + 비상용의 합**(물결 2-1 · 👤 2026-10-12). 층별 화면 머리 「승강기」 칸과
 * 중개사 소유 구조 줄이 함께 쓴다(두 곳이 다르게 세면 같은 건물이 두 말을 한다).
 *
 * ⛔ 둘은 **따로 세는 칸**이다 — 원본에 비상용이 승용보다 많은 건물이 있다(비상용이 승용의 일부가 아니다).
 *    하나만 null 이면 있는 것만 더한다.
 * ⛔ **합이 0 이거나 둘 다 null 이면 지상 최고층(`topFloor` — 옥탑 제외)으로 가른다**(👤 2026-10-12 결정 A
 *    「5층 이하는 숨김, 6층 이상은 미상」): `ELEVATOR_UNKNOWN_MIN_FLOOR`(6) 이상이면 '미상'(그 높이에 승강기가
 *    없을 리 없으니 대장 미기재로 본다), 5층 이하이거나 최고층을 모르면 **null = 칸·조각 없음**(작은 건물은
 *    정말 없는 경우가 흔해 '미상'이 오히려 틀린 말이 된다 · '0대'라고도 적지 않는다).
 * ⛔ **둘 다 undefined(칸이 아예 안 옴 — 마이그레이션 2026-10-11c 전 서버)면 null** = 칸·조각 없음.
 * ⓘ `withEmgen` 이면 비상용이 1대 이상일 때 뒤에 「(비상용 M대 포함)」(층별 화면 머리만 — 검색 줄은 짧게).
 * ⓘ 최고층은 화면이 이미 쓰는 값이다 — 층별 화면은 층 행에서 `buildingFromFloorRows` 규칙으로(옥탑 99 제외),
 *   검색 줄은 `BuildingHit.max_floor`(서버의 같은 규칙). `floor_cnt`(옥탑까지 센 행 수)를 쓰지 않는다.
 */
export const ELEVATOR_UNKNOWN_MIN_FLOOR = 6;

export function describeElevator(
  ride: number | null | undefined,
  emgen: number | null | undefined,
  withEmgen: boolean,
  topFloor: number | null | undefined,
): string | null {
  if (ride === undefined && emgen === undefined) return null;
  const isCount = (v: number | null | undefined): v is number =>
    typeof v === 'number' && Number.isFinite(v);
  const total = (isCount(ride) ? ride : 0) + (isCount(emgen) ? emgen : 0);
  if (total <= 0) {
    return isCount(topFloor) && topFloor >= ELEVATOR_UNKNOWN_MIN_FLOOR ? UNKNOWN_SPEC : null;
  }
  const base = `${total.toLocaleString('ko-KR')}대`;
  if (withEmgen && isCount(emgen) && emgen >= 1) {
    return `${base} (비상용 ${emgen.toLocaleString('ko-KR')}대 포함)`;
  }
  return base;
}

/**
 * 구조 이름(물결 2-1) — 대장 글자 그대로(「철근콘크리트구조」). null·빈 글자는 '미상'(같은 머리 다른 칸과 같은 말) ·
 * **undefined(칸이 아예 안 옴 — 옛 서버)면 null** = 칸 없음.
 */
export function describeStructure(v: string | null | undefined): string | null {
  if (v === undefined) return null;
  if (v === null || v.trim() === '') return UNKNOWN_SPEC;
  return v;
}

/**
 * 대장 호수 — 「48호」(물결 2-1 · 👤 그림 ⑥ 「가」). **집합건물이고 1호 이상일 때만** 글자, 그 밖은 null = 칸 없음.
 *
 * ⛔ 0 은 '미상'도 '기재 없음'도 아니고 **칸을 안 그린다** — 호수 0 은 대부분 호실이 없는 일반건물의 정상값이다.
 * ⛔ 일반건물·null·undefined 도 칸 없음(일반건물에 호수가 적혀 있어도 안 보인다).
 * ⛔ **건물 주용도(`mainUse` = `bld_main_use`)가 주거(공동주택·단독주택)면 칸 없음**(👤 2026-10-12 결정 B
 *    「아파트는 숨기기」 — 아파트의 호수는 세대 수라 상가 호실로 읽힌다) · 주용도를 모르면(null·undefined)도
 *    칸 없음(모르면 안 보인다). 이름은 건축물대장 원문 `mainPurpsCdNm` 철자 그대로(`RESIDENTIAL_MAIN_USES`).
 * ⓘ 이름표는 꼭 '대장 호수' — 층 목록의 「호실 N칸」(우리 호실 표로 센 것)과 세는 대상이 다르다.
 */
export const RESIDENTIAL_MAIN_USES: readonly string[] = ['공동주택', '단독주택'];

export function describeHoCnt(
  isJiphap: boolean | null | undefined,
  hoCnt: number | null | undefined,
  mainUse: string | null | undefined,
): string | null {
  if (isJiphap !== true) return null;
  if (typeof mainUse !== 'string' || mainUse.trim() === '') return null;
  if (RESIDENTIAL_MAIN_USES.includes(mainUse.trim())) return null;
  if (typeof hoCnt !== 'number' || !Number.isFinite(hoCnt) || hoCnt <= 0) return null;
  return `${hoCnt.toLocaleString('ko-KR')}호`;
}

/**
 * 중개사 검색 결과의 **소유 구조 줄**(결정 0036 결정 5·18 ⑦⑩) — 「집합건물 · 사용승인 2003년 5월 · 주차 120대」.
 *
 * ⛔ null 은 '미상', **undefined(칸이 아예 안 옴 — 옛 서버)는 줄 없음**(null 을 돌려준다). 둘을 섞지 않는다 —
 *    세 칸 모두 undefined 일 때만 줄을 안 그린다(하나라도 오면 오지 않은 칸도 '미상').
 * ⓘ 층수는 같은 결과 줄의 `hit__meta` 에 이미 있어 다시 적지 않는다.
 * ⓘ 물결 2-1(2026-10-12): 뒤에 「· 승강기 3대」(합 · 비상용 괄호 없이 · 합 0 이면 `max_floor` 6층 이상만
 *   「승강기 미상」 · 두 칸 다 안 오면 조각 없음)와 「· 대장 호수 48호」(`describeHoCnt` 가 글자를 줄 때만 —
 *   주거 주용도면 없음)를 붙인다. 줄을 세울지는 여전히 옛 세 칸만 본다.
 */
export function describeOwnership(h: BuildingHit): string | null {
  if (h.is_jiphap === undefined && h.approve_date === undefined && h.parking_cnt === undefined) {
    return null;
  }
  const kind = formatJiphap(h.is_jiphap) ?? `건물 종류 ${UNKNOWN_SPEC}`;
  const approve = h.approve_date ? formatApproveDate(h.approve_date) : UNKNOWN_SPEC;
  const parking = describeSpec(h.parking_cnt, formatParking);
  const parts = [kind, `사용승인 ${approve}`, `주차 ${parking}`];
  const elevator = describeElevator(h.elevator_ride, h.elevator_emgen, false, h.max_floor);
  if (elevator !== null) parts.push(`승강기 ${elevator}`);
  const ho = describeHoCnt(h.is_jiphap, h.ho_cnt, h.bld_main_use);
  if (ho !== null) parts.push(`대장 호수 ${ho}`);
  return parts.join(' · ');
}

/**
 * 서버 오류 원문 대신 사람이 읽을 문구로 바꾼다.
 *
 * 원문에는 `permission denied for table building_floor`처럼 내부 표 이름이 섞여 나올 수
 * 있어 그대로 화면에 띄우지 않는다. 단 "함수가 아직 DB에 없다"(PGRST202)는 원인이
 * 분명하고 조치가 정해져 있으므로 그대로 안내한다.
 */
export function describeError(ex: unknown): string {
  const code =
    typeof ex === 'object' && ex !== null && 'code' in ex
      ? String((ex as { code: unknown }).code)
      : '';
  if (code === 'PGRST202') {
    return (
      '검색 기능이 아직 DB에 적용되지 않았습니다. ' +
      'supabase/migrations/2026-08-08b_search_buildings.sql을 Supabase SQL Editor에서 실행해 주세요.'
    );
  }
  // 57014 = statement_timeout. 고장이 아니라 **검색어가 너무 넓어서** 나는 것이다.
  // 2026-08-11 실측: '동'·'1'·'서울' 은 수십만 건과 맞아 정확한 건수를 세는 데
  // 3초를 넘긴다('서울'은 서울 건물 17만 개 전부와 매칭). "실패했습니다"로 뭉뚱그리면
  // 사용자가 고장인 줄 알고 같은 검색을 반복한다 — 무엇을 하면 되는지 알려준다.
  // ⛔ 결과를 임의로 잘라 보여주지 않는다(사장님 판단, 2026-08-11): 16,267건인데
  //    "1,000개 이상"이라고 적는 것은 정보를 자르는 것이다.
  if (code === '57014') {
    return (
      '검색어가 너무 넓어 결과를 다 세지 못했습니다. ' +
      '동 이름이나 건물 이름을 조금 더 자세히 넣어 주세요 (예: "명동" → "명동길", "서울" → "서울역").'
    );
  }
  return '검색에 실패했습니다. 잠시 후 다시 시도해 주세요.';
}

/**
 * "지하 2층 ~ 15층 + 옥탑"처럼 층 범위를 한 줄로.
 *
 * 부호 처리를 직접 하지 않고 `formatFloor`를 재사용한다 — 예전엔 아래쪽만 음수를
 * 처리하고 위쪽은 그대로 찍어서, 지하만 있는 건물이 "지하 5층 ~ -1층"으로 보였다
 * (2026-08-08 실측: 강남에 지하층만 있는 건물 213개).
 */
export function describeRange(h: BuildingHit): string {
  if (h.min_floor === null || h.max_floor === null) {
    return h.has_roof ? '옥탑만' : '층 정보 없음';
  }
  const bottom = formatFloor(h.min_floor, null);
  const top = formatFloor(h.max_floor, null);
  const range = bottom === top ? bottom : `${bottom} ~ ${top}`;
  return h.has_roof ? `${range} + 옥탑` : range;
}
