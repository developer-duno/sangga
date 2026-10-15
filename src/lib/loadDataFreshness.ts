import { DATA_FRESHNESS_FN } from './appConstants';
import { isDataFreshnessList } from './dataFreshness';
import { supabase } from './supabase';
import type { DataFreshnessRow } from '../types';

/**
 * "이 자료는 언제 것인가" 표를 받는 **단 하나의 창구**(S3 · 2026-10-16).
 *
 * 맨 아래 표(`DataFreshness`)와 카드마다의 날짜 줄(`SectionCard`)이 **같은 한 번의 요청**을 나눠 쓴다 —
 * 카드가 열한 장이라 저마다 부르면 같은 표를 열한 번 받는다.
 *
 * ⛔ 실패도 그 화면 동안 보관한다(null). 지우면 실패 뒤에 뜨는 카드마다 다시 불러 요청이 카드 수만큼 는다 —
 *    맨 아래 표도 예전부터 한 번만 불렀다(다시 시도 없음). 새로고침하면 다시 묻는다.
 * ⛔ supabase 요청 객체는 `.then()` 마다 새로 fetch 한다(`lib/sidePrefetch.ts` 머리말) — 그래서 여기서 **한 번만**
 *    `.then` 해 만든 진짜 Promise 를 나눠 준다.
 * ⓘ 이 파일이 `dataFreshness.ts` 와 따로인 이유 — 저쪽은 순수 계산만 있어 supabase 없이 시험한다.
 */
let cached: Promise<DataFreshnessRow[] | null> | null = null;

export function loadDataFreshness(): Promise<DataFreshnessRow[] | null> {
  if (!cached) {
    cached = Promise.resolve(supabase.rpc(DATA_FRESHNESS_FN)).then(
      ({ data, error }) => {
        // ⚠️ 모양까지 본다. 뜻밖의 답이 렌더로 흘러 들어가면 그 자리에서 터진다.
        if (error || !isDataFreshnessList(data)) {
          console.warn('자료 기준일 조회 실패 — 그 표와 카드 날짜 줄 없이 표시합니다', error ?? data);
          return null;
        }
        return data;
      },
      (err: unknown) => {
        console.warn('자료 기준일 조회 실패 — 그 표와 카드 날짜 줄 없이 표시합니다', err);
        return null;
      },
    );
  }
  return cached;
}

/** ⓘ 시험이 각 경우를 처음부터 다시 보게 하는 용도. 화면은 안 쓴다. */
export function resetDataFreshnessCache(): void {
  cached = null;
}
