import { supabase } from './supabase';
import {
  DAEJEON_CLOSURE_FN,
  DISTRICT_CENSUS_POP_FN,
  DISTRICT_POP_FN,
  DISTRICT_SALES_FN,
  FLOOR_INDUSTRY_FN,
  INDUSTRY_MEDIAN_FN,
  INDUSTRY_MIX_FN,
  NEARBY_PERMITS_FN,
  OPEN_CLOSE_FN,
  RENT_HISTORY_FN,
  RENT_STATS_FN,
  STORE_HISTORY_FN,
} from './appConstants';
import { isDaejeonPnu } from './daejeonClosure';
import { isSeoulPnu } from './openClose';

/**
 * 층별 화면의 곁 카드(둘레의 업종 분포 · 그 비교 글(물결 2-3) · 둘레 인허가 한 줄 · 상권 임대 동향 · 상권 개업·폐업 ·
 * 층 목록의 업종 띠(결정 0038 V4) · 임대 동향의 8분기 흐름(결정 0038 V5) · 이 자리 가게 이력(결정 0045 PR④)) 요청을
 * **건물을 고른 순간** 먼저 출발시킨다(로드맵 속도 P3 — 사장님 결재 2026-09-27 "① 요청만 먼저").
 *
 * 왜: 그 카드들은 층 목록이 온 뒤에야 마운트된다(`FloorStack` 의 `if (loading) return …`).
 *    그래서 자기 요청도 층 목록 응답만큼 늦게 출발했다(라이브 실측 +351~357ms). 카드 자리·
 *    생김새는 그대로 두고, **요청만** 부모가 먼저 보내 두면 카드는 마운트될 때 그 결과를 받는다.
 *
 * ⛔ supabase 요청 객체는 `.then()` 을 부를 때마다 **새로 fetch 한다**
 *    (postgrest-js `then()` 안에서 매번 `executeWithRetry()` 를 실행). 요청 객체를 그대로
 *    저장해 부모·자식이 각각 `.then` 하면 두 번 나간다 — 목(mock)은 이걸 못 잡는다.
 *    그래서 여기서 **한 번만** `.then` 해 만든 진짜 Promise 를 나눠 쓴다.
 * ⛔ 보관 열쇠 = 함수 이름 + pnu(여덟 함수 — 서울 필지는 열 · 대전 필지는 아홉 — 의 인자는 `p_pnu` 하나뿐이라
 *    이것이 인자 전부다).
 *    pnu 가 다르면 절대 내주지 않는다 — 건물 A 의 늦은 답이 건물 B 카드에 붙으면 그 순간이
 *    그대로 틀린 정보다. 보관은 **지금 건물 것 한 벌뿐**(부모가 건물이 바뀌면 통째로 갈아 끼운다).
 */

/** 카드들이 쓰는 모양 그대로 — 카드가 `data`·`error` 를 스스로 검사한다. */
export type RpcResult = { data: unknown; error: unknown };

/**
 * 미리 보내는 함수들. 여덟 다 인자가 `{ p_pnu }` 하나다(다섯째 업종 가운데값은 2026-10-12 · 물결 2-3 ·
 * 여섯째 층 목록 업종 띠는 2026-10-24 · 결정 0038 V4 — 받는 쪽은 카드가 아니라 `FloorStack` 자신이다 ·
 * 일곱째 임대 동향의 8분기 흐름은 2026-10-24 · 결정 0038 V5 — 받는 쪽은 임대 카드 ·
 * 여덟째 가게 이력은 2026-11-01 · 결정 0045 PR④ — 모든 필지 · 첫 쪽(함수 기본값 20·0) · 받는 쪽은 이력 카드).
 */
export const SIDE_PREFETCH_FNS = [
  INDUSTRY_MIX_FN,
  NEARBY_PERMITS_FN,
  RENT_STATS_FN,
  OPEN_CLOSE_FN,
  INDUSTRY_MEDIAN_FN,
  FLOOR_INDUSTRY_FN,
  RENT_HISTORY_FN,
  STORE_HISTORY_FN,
] as const;

/**
 * 대전 필지(pnu 앞 두 자리 30)일 때만 더 보내는 함수 둘 — 「동네 폐업 (대전시 공표)」(결정 0044) ·
 * 「상권 인구 (통계청 집계구)」(결정 0045 PR⑤) · 인자 `{ p_pnu }`. 받는 쪽은 개업·폐업 카드(대전 자리)와 역할 요약 판 ·
 * 상권 인구 카드(대전 자리). 서울 건물에는 보내지 않는다(요청 0).
 */
export const DAEJEON_PREFETCH_FNS = [DAEJEON_CLOSURE_FN, DISTRICT_CENSUS_POP_FN] as const;

/**
 * 서울 필지(pnu 앞 두 자리 11)일 때만 더 보내는 함수 둘 — 「업종별 추정매출 (서울시 추정)」·「상권 인구 (서울시 공표)」
 * (결정 0045 PR③ · 인자 `{ p_pnu }`). 받는 쪽은 그 두 카드. 서울 밖 건물에는 보내지 않는다(요청 0 — 그 자리는 빈 카드).
 */
export const SEOUL_PREFETCH_FNS = [DISTRICT_SALES_FN, DISTRICT_POP_FN] as const;

export type SidePrefetch = {
  pnu: string;
  results: ReadonlyMap<string, Promise<RpcResult>>;
  /**
   * 출발 시각(`Date.now()` ms)과 함수마다 답(성공·실패)이 온 시각 — 역할 요약 판이 대전 답의 기다림 상한을
   * **출발부터** 재는 데 쓴다(결정 0044 후속 ⓑ · `settledWithin`). 카드가 받는 `results` 는 그대로다.
   * 시험이 손으로 만든 판에는 없다(그땐 `settledWithin` 이 false).
   */
  startedAt?: number;
  settledAt?: ReadonlyMap<string, number>;
};

export function startSidePrefetch(pnu: string): SidePrefetch {
  const results = new Map<string, Promise<RpcResult>>();
  const startedAt = Date.now();
  const settledAt = new Map<string, number>();
  const fns: readonly string[] = isDaejeonPnu(pnu)
    ? [...SIDE_PREFETCH_FNS, ...DAEJEON_PREFETCH_FNS]
    : isSeoulPnu(pnu)
      ? [...SIDE_PREFETCH_FNS, ...SEOUL_PREFETCH_FNS]
      : SIDE_PREFETCH_FNS;
  for (const fn of fns) {
    // `.then` 을 **지금 한 번** 불러 요청을 출발시킨다(`Promise.resolve(빌더)` 는 다음
    // 틱에야 부른다). 라이브러리 타입이 PromiseLike 라 Promise.resolve 로 감싼다 — 진짜
    // Promise 를 받으면 그대로 돌려줄 뿐 요청을 더 만들지 않는다.
    const p = Promise.resolve(supabase.rpc(fn, { p_pnu: pnu }).then((r): RpcResult => r));
    // 층 정보가 0건·오류인 건물에서는 카드가 안 떠서 아무도 이 결과를 안 받는다. 그때
    // 거부된 Promise 가 "처리 안 된 거부"로 콘솔을 어지럽히지 않게 빈 처리만 붙인다
    // (카드가 받는 `p` 자체는 그대로라 카드 쪽 동작은 지금과 같다).
    p.catch(() => {});
    // 답이 온 시각 — 받는 쪽보다 **먼저** 붙여 두어 받는 쪽 콜백이 돌 때는 이미 적혀 있다(같은 Promise 의 반응은 붙인 순서대로).
    const mark = () => {
      settledAt.set(fn, Date.now());
    };
    p.then(mark, mark);
    results.set(fn, p);
  }
  return { pnu, results, startedAt, settledAt };
}

/**
 * 이 필지·이 함수의 미리 보낸 답이 **출발 뒤 waitMs 안에** 왔나(결정 0044 후속 ⓑ). 답을 받은 콜백 안에서 부른다
 * — 아직 안 왔거나, 다른 필지 것이거나, 시각 기록이 없는 판이면 false.
 */
export function settledWithin(
  prefetch: SidePrefetch | null | undefined,
  fn: string,
  pnu: string,
  waitMs: number,
): boolean {
  if (!prefetch || prefetch.pnu !== pnu || prefetch.startedAt === undefined) return false;
  const at = prefetch.settledAt?.get(fn);
  return at !== undefined && at - prefetch.startedAt < waitMs;
}

/** 이 함수·이 필지의 미리 보낸 결과. 없거나 다른 필지 것이면 null(그때 카드는 스스로 묻는다). */
export function takePrefetched(
  prefetch: SidePrefetch | null | undefined,
  fn: string,
  pnu: string,
): Promise<RpcResult> | null {
  if (!prefetch || prefetch.pnu !== pnu) return null;
  return prefetch.results.get(fn) ?? null;
}
