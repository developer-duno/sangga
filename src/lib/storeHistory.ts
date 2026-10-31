import { CARD_SOURCES } from './dataFreshness';
import { formatFloor, formatQuarter } from './format';
import type { DataFreshnessRow, StoreHistoryRow } from '../types';

/**
 * 「이 자리 가게 이력 (점포 자료 누적)」 카드의 순수 계산 — 결정 0045 PR④ · 시안 「후」 그대로(👤 10-31 「진행」).
 *
 * ⛔ **그 땅(필지)의 점포 줄**이다 — 건물 값이 아니다. 소진공 분기 자료를 우리가 가게마다 이어 붙인 사슬(D등급)이고,
 *    「보인 분기 수」는 자료에 보인 분기 수일 뿐 영업 기간이 아니다(첫 줄·각주가 같은 말을 한다).
 * ⛔ **분기·연도 글자를 박지 않는다** — 분기 글은 전부 서버 값(`history_first_ym`·`history_last_ym`·`first_ym`·`last_ym`)을
 *    `formatQuarter` 로 읽어 만든다(시험이 이 파일과 컴포넌트 원문을 훑는다).
 * ⛔ 화면은 줄을 다시 세우지 않는다 — 서버 차례(지금 보임 → 보인 분기 수 ↓ → 층)를 그대로 쓰고 묶음은 `is_current` 로만 가른다.
 * ⛔ 「문을 닫았다」는 낱말은 각주 둘째 문장(`HISTORY_GONE_NOTE`) 한 곳뿐이다(👤 10-31 「원문 그대로 · 그 문장만 예외」 ·
 *    시험이 이 파일·컴포넌트 원문에서 그 문장을 뺀 나머지를 훑는다).
 */

/** 분기 꼴 — 'YYYYMM' 분기말 달(3·6·9·12). */
const RE_YM = /^\d{4}(03|06|09|12)$/;

/** 각주 둘째 문장(👤 원문) — 「문을 닫았다」는 낱말이 화면에 나오는 **유일한** 자리. */
export const HISTORY_GONE_NOTE = '자료에서 안 보이는 것은 폐업이 아닐 수 있습니다.';

export const HISTORY_LEAD_STRONG = '이 땅(필지)의 점포 자료에 보인 가게들입니다';
export const HISTORY_LEAD_MID = ' — 소상공인시장진흥공단 분기 자료를 가게마다 이어 붙인 것이고, ';
export const HISTORY_LEAD_BOLD = '보인 분기 수는 영업 기간이 아닙니다.';
export const HISTORY_BADGE = 'D등급 · 간접추론';
export const HISTORY_BADGE_NOTE = '상가업소번호 + 같은 땅·층·상호로 이어 붙임 · 우리 계산';
export const HISTORY_CHIP = '지금은 안 보임';
export const HISTORY_CURRENT_HEAD = '지금 자료에 보이는 가게';
export const HISTORY_GONE_HEAD = '전에 보였던 가게';
export const HISTORY_GONE_HEAD_NOTE = '· 지금은 자료에 안 보임';

/** 굵은 조각이 하나 낀 글 — 컴포넌트가 `bold` 만 `<b>` 로 감싼다(빈 글이면 감싸지 않는다). */
export type BoldText = { pre: string; bold: string; post: string };

function isYm(v: unknown): v is string {
  return typeof v === 'string' && RE_YM.test(v);
}

/** 숫자 글 — 천 단위 쉼표(형제 `openClose.ts` 와 같은 `toLocaleString('ko-KR')` · 보완 1 F-3). */
export function countText(n: number): string {
  return n.toLocaleString('ko-KR');
}

function isNonNegInt(v: unknown): v is number {
  return typeof v === 'number' && Number.isInteger(v) && v >= 0;
}

/**
 * 모양 검사 — 하나라도 어긋나면 false(카드째 숨김 · 「자료 없음」이라 적지 않는다).
 * 배열 · 비어 있지 않음 · ok/no_data 가 섞이지 않음 · no_data 면 한 줄뿐이고 total·current 0 · ok 줄의 칸 꼴 ·
 * 모든 줄의 total·current·history_* 가 같음 · total ≥ 줄 수 · current ≤ total.
 */
export function isStoreHistoryList(x: unknown): x is StoreHistoryRow[] {
  if (!Array.isArray(x) || x.length === 0) return false;
  const first = x[0] as Record<string, unknown> | null;
  if (!first || typeof first !== 'object') return false;
  const { total_cnt: total, current_cnt: cur, history_first_ym: hf, history_last_ym: hl } = first;
  if (!isNonNegInt(total) || !isNonNegInt(cur) || cur > total || !isYm(hf) || !isYm(hl) || hf > hl) return false;
  const status = first.status;
  if (status === 'no_data') {
    return x.length === 1 && total === 0 && cur === 0;
  }
  if (status !== 'ok' || total < x.length) return false;
  return x.every((raw) => {
    const r = raw as Record<string, unknown> | null;
    if (!r || typeof r !== 'object' || r.status !== 'ok') return false;
    if (r.total_cnt !== total || r.current_cnt !== cur || r.history_first_ym !== hf || r.history_last_ym !== hl) {
      return false;
    }
    if (typeof r.biz_name !== 'string' || r.biz_name.trim() === '') return false;
    const f = r.floor_no;
    if (f !== null && !(typeof f === 'number' && Number.isInteger(f) && f !== 0)) return false;
    if (!isYm(r.first_ym) || !isYm(r.last_ym) || r.first_ym > r.last_ym) return false;
    if (!(typeof r.seen_cnt === 'number' && Number.isInteger(r.seen_cnt) && r.seen_cnt >= 1)) return false;
    return typeof r.is_current === 'boolean' && typeof r.truncated === 'boolean';
  });
}

/** 두 분기 사이 분기 수(양끝 포함). 꼴이 아니거나 거꾸로면 null. */
export function quartersBetween(a: string, b: string): number | null {
  if (!isYm(a) || !isYm(b) || a > b) return null;
  const idx = (ym: string) => Number(ym.slice(0, 4)) * 4 + Number(ym.slice(4)) / 3;
  return idx(b) - idx(a) + 1;
}

/** 층 칸 글 — 층 목록과 같은 도우미(`formatFloor`) · 모름(null)·0 은 「층 모름」(절대 규칙 4). */
export function floorText(floorNo: number | null): string {
  if (floorNo === null || floorNo === 0) return '층 모름';
  return formatFloor(floorNo, null);
}

/** 접힌 요약 — 값은 서버 칸(current_cnt · total_cnt · history_first_ym · history_last_ym)뿐 · 비율·판단 낱말 0. */
export function historySummary(rows: StoreHistoryRow[]): string {
  const head = rows[0];
  const start = formatQuarter(head.history_first_ym);
  if (head.status === 'no_data') {
    return `${start} 이후 점포 자료에 이 땅의 가게가 보이지 않습니다`;
  }
  const gone = head.total_cnt - head.current_cnt;
  const k = quartersBetween(head.history_first_ym, head.history_last_ym);
  const parts = [`지금 보이는 가게 ${countText(head.current_cnt)}곳`];
  if (gone > 0) parts.push(`전에 보였던 가게 ${countText(gone)}곳`);
  parts.push(`${start}부터 점포 자료 ${k}분기`);
  return parts.join(' · ');
}

/** 줄 설명 글(네 갈래) — 굵은 조각은 「N분기」(지금 보이는 줄만 · 시안 그대로). */
export function rowText(row: StoreHistoryRow): BoldText {
  const seen = row.seen_cnt ?? 0;
  const span = row.truncated ? `${seen}분기 이상` : `${seen}분기`;
  if (row.is_current) {
    if (row.truncated) {
      return { pre: '자료에 ', bold: span, post: ` 보임 · 자료 시작(${formatQuarter(row.history_first_ym)})부터 계속` };
    }
    if (seen === 1) {
      return { pre: '자료에 ', bold: span, post: ` 보임 · ${formatQuarter(row.first_ym)}에 처음` };
    }
    return { pre: '자료에 ', bold: span, post: ` 보임 · ${formatQuarter(row.first_ym)}부터` };
  }
  // 한 분기만 보인 지난 줄은 「○년 ○분기에만 보임」(지금 보이는 1분기 줄의 「○년 ○분기에 처음」과 짝 · 보완 1 F-4).
  if (row.first_ym === row.last_ym && !row.truncated) {
    return { pre: `${formatQuarter(row.first_ym)}에만 보임`, bold: '', post: '' };
  }
  return { pre: `${formatQuarter(row.first_ym)} ~ ${formatQuarter(row.last_ym)} 보임 · `, bold: '', post: span };
}

/**
 * 어긋남 줄 — 이력의 마지막 분기가 신선도 표 「점포·업종 (상권정보)」 줄의 기준 분기(보여 주는 분기)와 다를 때만
 * (결정 0045 「표지의 예외」 3 · 숨기지 않는다). 표를 못 받았거나 그 줄이 없거나 꼴이 아니면 null(거짓 경고 0).
 * ⓘ 방향을 가른다(보완 1 F-5) — 이력이 **뒤**면 「이 이력은 ○까지입니다」, 이력이 **앞**이면(이력 적재 ~ post_load
 *    사이 몇 분 · 다른 카드가 아직 옛 분기) 「점포 자료가 갱신되는 중입니다 — …」.
 */
export function lagText(rows: StoreHistoryRow[], freshness: DataFreshnessRow[] | null): BoldText | null {
  if (!freshness || rows.length === 0) return null;
  const store = freshness.find((f) => f.src === CARD_SOURCES.sangkwon.src);
  const basis = store?.basis ?? null;
  const last = rows[0].history_last_ym;
  if (!isYm(basis) || basis === last) return null;
  if (last > basis) {
    return {
      pre: '점포 자료가 갱신되는 중입니다 — 이 이력은 ',
      bold: formatQuarter(last),
      post: `까지 들어 있습니다 (다른 카드는 ${formatQuarter(basis)})`,
    };
  }
  return { pre: '이 이력은 ', bold: formatQuarter(last), post: `까지입니다 (점포 자료는 ${formatQuarter(basis)})` };
}

/** 각주 셋(👤 시안 · 분기 글·분기 수는 서버 값). 둘째는 굵은 첫 문장(`HISTORY_GONE_NOTE`) + 나머지. */
export function historyNotes(rows: StoreHistoryRow[]): { source: string; gone: [string, string]; name: string } {
  const head = rows[0];
  const k = quartersBetween(head.history_first_ym, head.history_last_ym);
  return {
    source:
      `출처: 소상공인시장진흥공단 「상가(상권)정보」 분기 자료 ${formatQuarter(head.history_first_ym)}~` +
      `${formatQuarter(head.history_last_ym)}(${k}분기) — 상가업소번호로 잇고, 번호가 바뀐 가게는 같은 땅·층·상호가 ` +
      '정확히 하나일 때만 이었습니다. 그 전 분기는 번호 체계가 달라 쓰지 않습니다.',
    gone: [
      HISTORY_GONE_NOTE,
      ' 자료에 빠졌다 돌아오는 가게가 흔하고, 그때는 새 줄로 셉니다 — 보인 분기 수는 영업 기간이 아닙니다.',
    ],
    name:
      '상호는 자료의 마지막 값입니다 — 옛 분기의 이름이 그 시절 간판이라는 뜻은 아닙니다. ' +
      '땅 번호가 바뀐 땅(분할·합병)은 옛 줄이 이 땅에 붙지 않습니다.',
  };
}

/** 묶음 머리의 수 — 그 땅 전체(서버 current_cnt · total − current)이지 지금까지 받은 줄 수가 아니다. */
export function groupCounts(rows: StoreHistoryRow[]): { current: number; gone: number } {
  const head = rows[0];
  return { current: head.current_cnt, gone: head.total_cnt - head.current_cnt };
}

/** 「더 보기」 단추 글 — 남은 수 = 그 땅 전체 − 받은 줄 수. */
export function moreText(received: number, total: number): string {
  return `더 보기 (남은 ${countText(total - received)}곳)`;
}
