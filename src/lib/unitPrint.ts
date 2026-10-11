import type { UnitFloorSummary } from '../types';
import { hasUnitList } from './unitTable';

/**
 * 호실 구성표 고르기(결정 0036 결정 8 · 물결 1-C2 · 👤 2026-10-11) — **누구에게나** 인쇄 단추 옆에 서고,
 * 고르면 화면에서도 그 층들의 호 목록을 층 줄 아래에 펼친다(그래서 Ctrl+P 로 뽑아도 같은 종이 —
 * 결정 0020 원칙). 저장하지 않고, 건물이 바뀌면 '넣지 않음'으로 돌아간다(App 이 건물 번호로 묶는다).
 *
 * ⛔ **호 목록이 있는 층(`hasUnitList` — 상가·섞인 층)만** 부른다. 주거·오피스텔·미상 층은 요청조차 안
 *    보낸다(결정 0032 — 층을 펼칠 때와 같은 규칙).
 * ⛔ 층마다 첫 쪽(50호 = `FLOOR_UNITS_PAGE`, offset 0)만 · 동시에 4개까지 · 전부 = 아래층부터 30개 층까지.
 */
export type UnitPrintMode = 'none' | 'low' | 'all';

/** 고르기 단추 차례와 글자(👤 결정 글자 그대로). */
export const UNIT_PRINT_OPTIONS: ReadonlyArray<readonly [UnitPrintMode, string]> = [
  ['none', '넣지 않음'],
  ['low', '지하~3층'],
  ['all', '전부'],
];

/** '전부'일 때 넣는 층 수 상한(아래층부터). 큰 건물에서 요청이 수백 번 나가지 않게. */
export const UNIT_PRINT_FLOOR_CAP = 30;

/** 동시에 보내는 호 목록 요청 수 상한. */
export const UNIT_PRINT_CONCURRENCY = 4;

export type UnitPrintPlan = {
  /** 호 목록을 부를 층(아래층부터). */
  floors: number[];
  /** 이 건물에서 호 목록이 있는 층 수(상한 안내에 쓴다). */
  listedCount: number;
  /** '전부'인데 상한에 걸려 위쪽 층을 뺐나. */
  capped: boolean;
};

const EMPTY: UnitPrintPlan = { floors: [], listedCount: 0, capped: false };

/**
 * 고른 값으로 부를 층을 정한다. 층 목록 카드에 줄이 있는 층(`floorNos`)만 — 줄 아래에 붙여야 하므로.
 * 요약(`summary`)이 아직 없거나 못 읽었으면 아무 층도 안 부른다(층 종류를 모르면 주거 층을 물을 수 있다).
 */
export function unitPrintPlan(
  summary: readonly UnitFloorSummary[] | null,
  floorNos: readonly number[],
  mode: UnitPrintMode,
): UnitPrintPlan {
  if (mode === 'none' || summary === null) return EMPTY;
  const onStack = new Set(floorNos);
  const listed = summary
    .filter((u): u is UnitFloorSummary & { floor_no: number } => u.floor_no !== null)
    .filter((u) => onStack.has(u.floor_no) && hasUnitList(u.floor_kind))
    .map((u) => u.floor_no)
    .sort((a, b) => a - b);
  if (mode === 'low') {
    return { floors: listed.filter((f) => f < 0 || (f >= 1 && f <= 3)), listedCount: listed.length, capped: false };
  }
  return {
    floors: listed.slice(0, UNIT_PRINT_FLOOR_CAP),
    listedCount: listed.length,
    capped: listed.length > UNIT_PRINT_FLOOR_CAP,
  };
}

/** 상한 안내(👤 글자). */
export function unitPrintCapText(listedCount: number): string {
  return `호실 목록이 있는 층이 ${listedCount.toLocaleString('ko-KR')}개라 아래쪽 ${UNIT_PRINT_FLOOR_CAP}개 층만 넣었습니다`;
}

/** 첫 쪽보다 많을 때의 한 줄(👤 글자 · 종이에도). */
export function unitPrintMoreText(rest: number): string {
  return `이 층은 ${rest.toLocaleString('ko-KR')}호 더 있습니다`;
}

/**
 * `items` 를 `limit` 개씩 동시에 돌린다(앞에서부터 순서대로 꺼낸다). `stopped()` 가 참이면 새 일을 안 꺼낸다.
 * 한 일이 던져도 다른 일은 계속한다(실패한 층은 그 층만 빠진다).
 */
export async function runLimited<T>(
  items: readonly T[],
  limit: number,
  fn: (item: T) => Promise<void>,
  stopped: () => boolean = () => false,
): Promise<void> {
  let next = 0;
  async function worker() {
    while (next < items.length && !stopped()) {
      const item = items[next++];
      try {
        await fn(item);
      } catch (e) {
        console.warn('호 목록 요청 하나가 실패했습니다 — 그 층만 뺍니다', e);
      }
    }
  }
  await Promise.all(Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, worker));
}
