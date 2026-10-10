import type { BuildingHit } from '../types';

/**
 * 중개사 「최근 뽑은 건물」을 **이 기기에만** 적어 두는 부품(결정 0036 결정 18 ⑥⑩ · 「이 기기 저장」).
 *
 * ⛔ 적는 때는 **인쇄 단추를 누른 순간** 하나뿐이다(App → `PrintButton` 의 `onBeforePrint`).
 *    Ctrl+P·브라우저 메뉴로 뽑은 것은 못 잡고, 잡으려 하지 않는다(`beforeprint` 같은 엿보기 금지).
 * ⛔ 주소(결정 0019)·의견함(결정 0034)에 이 목록을 싣지 않는다 — 서버는 누가 무엇을 뽑았는지 모른다.
 * ⛔ **저장이 막힌 창**에서는 읽기·쓰기·지우기·저장소 접근 예외를 전부 여기서 삼킨다. 뽑기·인쇄는
 *    그대로 되고 목록만 안 남는다(`recordPrinted` 가 적은 뒤 **다시 읽어** 돌려주므로, 못 적었으면
 *    화면 목록도 비어 있다 — 저장 안 된 목록을 '이 기기에 저장'이라며 보여 주지 않는다).
 * ⛔ 읽을 때 **한 줄씩** 모양을 본다 — 틀린 줄만 버리고 나머지는 산다(LH `.every()` 사고의 교훈:
 *    한 줄 때문에 목록 전체가 사라지면 안 된다). 저장 꼴이 바뀌어도 화면이 죽지 않는다.
 * ⓘ 담는 것 = 검색 결과 한 줄(`BuildingHit`)에서 `total_cnt` 만 뺀 것 — 누르면 검색을 다시 거치지
 *   않고 그 건물 층별 화면으로 바로 간다(층별 화면은 열 때 자료를 새로 받는다).
 */
export const RECENT_PRINTED_STORAGE_KEY = 'sangga.recentPrinted';

/** 남겨 두는 건물 수(👤 결정 0036 결정 18 ⑥). 넘으면 가장 오래된 것부터 빠진다. */
export const RECENT_PRINTED_MAX = 10;

export type RecentPrinted = Omit<BuildingHit, 'total_cnt'>;

type ListStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function browserStorage(): ListStorage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const isStr = (x: unknown): x is string => typeof x === 'string';
const isNullableStr = (x: unknown) => x === null || typeof x === 'string';
const isNum = (x: unknown) => typeof x === 'number' && Number.isFinite(x);
const isNullableNum = (x: unknown) => x === null || isNum(x);
/** 선택 칸 — 아예 없으면(옛 서버에서 받은 줄) 그대로 둔다. 있으면 모양이 맞아야 한다. */
const optional = (x: unknown, ok: (v: unknown) => boolean) => x === undefined || ok(x);

/**
 * 한 줄의 모양. pnu 는 19자리 숫자여야 한다 — 앞 5자리가 곧 '누르면 갈 구'다.
 * ⛔ bld_id 는 `<pnu 19자리>_<숫자>` 꼴이고 **앞 19자리가 그 줄의 pnu 와 같아야** 한다(실제 예
 *    1168010600109420015_10241100257870) — 손댄 줄에서 구(pnu)와 건물(bld_id)이 갈리면 다른 구의
 *    건물을 엉뚱한 구 화면에 여는 틈이 생긴다.
 */
function isRecentPrinted(x: unknown): x is RecentPrinted {
  if (typeof x !== 'object' || x === null || Array.isArray(x)) return false;
  const r = x as Record<string, unknown>;
  return (
    isStr(r.pnu) &&
    /^\d{19}$/.test(r.pnu) &&
    isStr(r.bld_id) &&
    /^\d{19}_\d{1,32}$/.test(r.bld_id) &&
    r.bld_id.slice(0, 19) === r.pnu &&
    isNullableStr(r.bld_nm) &&
    isNullableStr(r.road_addr) &&
    isNum(r.bld_cnt_in_pnu) &&
    isNum(r.floor_cnt) &&
    isNullableNum(r.min_floor) &&
    isNullableNum(r.max_floor) &&
    typeof r.has_roof === 'boolean' &&
    optional(r.jibun_addr, isNullableStr) &&
    optional(r.lat, isNullableNum) &&
    optional(r.lng, isNullableNum) &&
    optional(r.is_jiphap, (v) => v === null || typeof v === 'boolean') &&
    optional(r.approve_date, isNullableStr) &&
    optional(r.parking_cnt, isNullableNum)
  );
}

/** 적어 둔 목록(최근 것이 앞). 없거나 깨졌거나 못 읽으면 빈 목록. 이상한 줄은 그 줄만 빠진다. */
export function loadRecentPrinted(storage: ListStorage | null = browserStorage()): RecentPrinted[] {
  if (!storage) return [];
  let raw: string | null;
  try {
    raw = storage.getItem(RECENT_PRINTED_STORAGE_KEY);
  } catch {
    return [];
  }
  if (raw === null) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  const seen = new Set<string>();
  const out: RecentPrinted[] = [];
  for (const row of parsed) {
    if (!isRecentPrinted(row) || seen.has(row.bld_id)) continue;
    seen.add(row.bld_id);
    out.push(row);
    if (out.length >= RECENT_PRINTED_MAX) break;
  }
  return out;
}

/** 검색 결과 한 줄에서 담을 칸만 고른다(`total_cnt` 는 '그 검색의 전체 건수'라 건물의 사실이 아니다). */
function toEntry(hit: BuildingHit): RecentPrinted {
  const { total_cnt: _drop, ...rest } = hit;
  void _drop;
  return rest;
}

/**
 * 뽑은 건물 하나를 맨 앞에 적는다. 같은 건물(bld_id)이 있으면 맨 앞으로 옮기고(중복 0),
 * 상한을 넘으면 가장 오래된 것이 빠진다. 돌려주는 것은 **적은 뒤 다시 읽은** 목록이다.
 */
export function recordPrinted(
  hit: BuildingHit,
  storage: ListStorage | null = browserStorage(),
): RecentPrinted[] {
  if (!storage) return [];
  const entry = toEntry(hit);
  const next = [entry, ...loadRecentPrinted(storage).filter((r) => r.bld_id !== entry.bld_id)].slice(
    0,
    RECENT_PRINTED_MAX,
  );
  try {
    storage.setItem(RECENT_PRINTED_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // 저장이 막힌 창 — 인쇄는 그대로 되고 목록만 안 남는다(위 머리말).
  }
  return loadRecentPrinted(storage);
}

/** 목록 전체를 지운다(「지우기」 단추). 돌려주는 것은 지운 뒤 다시 읽은 목록(보통 빈 목록). */
export function clearRecentPrinted(
  storage: ListStorage | null = browserStorage(),
): RecentPrinted[] {
  if (!storage) return [];
  try {
    storage.removeItem(RECENT_PRINTED_STORAGE_KEY);
  } catch {
    // 막힌 창 — 애초에 적힌 것도 없다.
  }
  return loadRecentPrinted(storage);
}
