import { supabase } from './supabase';
import { INDUSTRY_MIX_FN, NEARBY_PERMITS_FN, OPEN_CLOSE_FN, RENT_STATS_FN } from './appConstants';

/**
 * 층별 화면의 곁 카드(둘레의 업종 분포 · 둘레 인허가 한 줄 · 상권 임대 동향 · 상권 개업·폐업) 요청을
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
 * ⛔ 보관 열쇠 = 함수 이름 + pnu(네 함수의 인자는 `p_pnu` 하나뿐이라 이것이 인자 전부다).
 *    pnu 가 다르면 절대 내주지 않는다 — 건물 A 의 늦은 답이 건물 B 카드에 붙으면 그 순간이
 *    그대로 틀린 정보다. 보관은 **지금 건물 것 한 벌뿐**(부모가 건물이 바뀌면 통째로 갈아 끼운다).
 */

/** 카드들이 쓰는 모양 그대로 — 카드가 `data`·`error` 를 스스로 검사한다. */
export type RpcResult = { data: unknown; error: unknown };

/** 미리 보내는 함수들. 넷 다 인자가 `{ p_pnu }` 하나다. */
export const SIDE_PREFETCH_FNS = [
  INDUSTRY_MIX_FN,
  NEARBY_PERMITS_FN,
  RENT_STATS_FN,
  OPEN_CLOSE_FN,
] as const;

export type SidePrefetch = {
  pnu: string;
  results: ReadonlyMap<string, Promise<RpcResult>>;
};

export function startSidePrefetch(pnu: string): SidePrefetch {
  const results = new Map<string, Promise<RpcResult>>();
  for (const fn of SIDE_PREFETCH_FNS) {
    // `.then` 을 **지금 한 번** 불러 요청을 출발시킨다(`Promise.resolve(빌더)` 는 다음
    // 틱에야 부른다). 라이브러리 타입이 PromiseLike 라 Promise.resolve 로 감싼다 — 진짜
    // Promise 를 받으면 그대로 돌려줄 뿐 요청을 더 만들지 않는다.
    const p = Promise.resolve(supabase.rpc(fn, { p_pnu: pnu }).then((r): RpcResult => r));
    // 층 정보가 0건·오류인 건물에서는 카드가 안 떠서 아무도 이 결과를 안 받는다. 그때
    // 거부된 Promise 가 "처리 안 된 거부"로 콘솔을 어지럽히지 않게 빈 처리만 붙인다
    // (카드가 받는 `p` 자체는 그대로라 카드 쪽 동작은 지금과 같다).
    p.catch(() => {});
    results.set(fn, p);
  }
  return { pnu, results };
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
