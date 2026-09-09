import type { BuildingHit, StoreHit } from '../types';

/**
 * 상호명 검색(결정 0028)의 **순수 계산**만 모은다.
 *
 * 컴포넌트에서 빼 둔 이유는 `districtBuildings.ts`·`lhNotices.ts` 와 같다 — 여기 있는
 * 규칙들은 화면을 띄우지 않고도 시험할 수 있어야 하고, 실제로 틀리기 쉬운 곳이 전부
 * 여기다(서버 응답 모양 · 땅→건물 바꿔 담기 · "외 N곳" 세기 · 더 받을 것이 남았는지).
 */

function isNullableString(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'string';
}

function isNullableNumber(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'number';
}

function isNullableBoolean(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'boolean';
}

function isNullableStringArray(x: unknown): boolean {
  return (
    x === null || x === undefined || (Array.isArray(x) && x.every((v) => typeof v === 'string'))
  );
}

/**
 * 서버 응답의 **모양**을 본다.
 *
 * ⛔ **`total_*`·`too_broad` 말고는 전부 "있어도 되고 없어도 되는" 칸으로 잡는다**(`pnu` 는
 *    보통 줄에서만 필수 — 아래 참조).
 *    검색어가 너무 넓을 때 오는 `too_broad` 한 줄은 그 셋 말고 전부 비어 있고, 땅에 건물
 *    기록이 없으면 대표 동 칸들도 비어 있다. 이것들을 필수로 잡으면 **그런 줄 하나 때문에
 *    목록 전체가 거부된다** — LH 공고에서 실제로 났던 사고다(`.every()` 구조라 한 줄이
 *    통째를 날린다). 모양 검사는 "터지는 답을 막는" 그물이지 "자료 품질을 재는 자"가 아니다.
 */
export function isStoreHit(x: unknown): x is StoreHit {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    // ⛔ `too_broad` 를 **먼저** 본다 — 아래 pnu 검사가 이 값에 기대기 때문이다.
    typeof r.too_broad === 'boolean' &&
    /*
      ⛔ **너무 넓다 한 줄은 서버가 pnu 를 null 로 보낸다**(2026-09-09c 의 broad 가지:
         `null::char(19)`). 문자열만 받으면 그 한 줄 때문에 목록 전체가 거부돼 안내가
         사라진다(LH 사고와 같은 자리 — `.every()` 라 한 줄이 통째를 날린다).
      ⓘ 보통 줄의 pnu 는 **여전히 필수**다 — `key={s.pnu}` 와 `storeToHit` 이 그것에 기댄다.
    */
    (r.too_broad === true ? isNullableString(r.pnu) : typeof r.pnu === 'string') &&
    typeof r.total_parcel_cnt === 'number' &&
    typeof r.total_store_cnt === 'number' &&
    isNullableString(r.bld_id) &&
    isNullableString(r.bld_nm) &&
    isNullableString(r.road_addr) &&
    isNullableString(r.jibun_addr) &&
    isNullableString(r.store_snapshot_ym) &&
    isNullableNumber(r.lat) &&
    isNullableNumber(r.lng) &&
    isNullableNumber(r.bld_cnt_in_pnu) &&
    isNullableNumber(r.floor_cnt) &&
    isNullableNumber(r.min_floor) &&
    isNullableNumber(r.max_floor) &&
    isNullableNumber(r.match_store_cnt) &&
    isNullableBoolean(r.has_roof) &&
    isNullableStringArray(r.matched_names)
  );
}

/** ⓘ 빈 배열은 **정상**이다 — "그 이름의 가게가 이 구에 없다"는 답이다. */
export function isStoreHitList(x: unknown): x is StoreHit[] {
  return Array.isArray(x) && x.every(isStoreHit);
}

/** 서버 함수가 아직 라이브에 없다(마이그레이션 적용 전). PostgREST 가 404 로 이 코드를 준다. */
export function isMissingFunction(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    'code' in err &&
    String((err as { code: unknown }).code) === 'PGRST202'
  );
}

/**
 * 가게 이름 구역이 지금 무엇을 그려야 하는가.
 *
 * ⛔ 넷을 갈라 둔다 — **"안 보인다"에 서로 다른 두 뜻이 섞이면 안 된다.**
 *   · `hidden`  = 구역 자체가 없다(안 물었다 · 0건 · 서버에 함수가 아직 없다)
 *   · `failed`  = 물었는데 못 받았다 → **그렇다고 적는다**(0025 규칙: 사람이 누른 결과가
 *                 조용히 사라지면 안 된다). 함수 부재만 예외로 `hidden` 이다 — 배포 순서 탓에
 *                 잠깐 나는 정상 상태라 사용자가 할 수 있는 일이 없다.
 *   · `broad`   = 결과가 없는 게 아니라 **너무 많아** 서버가 끊었다
 *   · `done`    = 땅 목록
 */
export type StoreState =
  | { at: 'hidden' }
  | { at: 'failed' }
  | { at: 'broad'; word: string; count: number }
  | { at: 'done'; rows: StoreHit[] };

/** supabase-js 가 돌려주는 모양 중 여기서 보는 것만. */
export type RpcAnswer = { data: unknown; error: unknown };

/**
 * 서버 답 하나 → 구역 상태.
 *
 * ⚠️ 두 질의를 `Promise.allSettled` 로 나란히 보내므로 **거절(rejected)** 도 여기로 온다 —
 *    한쪽이 던져도 다른 쪽 결과는 살아야 한다는 것이 결정 0028 결정 4 의 요구다.
 */
export function readStoreAnswer(
  res: PromiseSettledResult<RpcAnswer>,
  word: string,
): StoreState {
  if (res.status === 'rejected') {
    console.warn('가게 이름 검색 실패', res.reason);
    return { at: 'failed' };
  }
  const { data, error } = res.value;
  if (error) {
    // 배포 순서 탓에 잠깐 나는 정상 상태다 — 구역만 조용히 빠진다.
    if (isMissingFunction(error)) return { at: 'hidden' };
    console.warn('가게 이름 검색 실패', error);
    return { at: 'failed' };
  }
  /*
    ⚠️ 모양까지 본다. 뜻밖의 답이 렌더로 흘러 들어가면 그 자리에서 터지는데, 이 구역은
       **검색창 안**에 있어 터지면 검색 자체가 함께 사라진다.
  */
  if (!isStoreHitList(data)) {
    console.warn('가게 이름 검색 실패 — 모양이 뜻밖입니다', data);
    return { at: 'failed' };
  }
  if (data.length === 0) return { at: 'hidden' };
  const broad = data.find((r) => r.too_broad);
  if (broad) return { at: 'broad', word, count: broad.total_store_cnt };
  return { at: 'done', rows: data };
}

/**
 * 땅 한 줄 → 검색 결과와 **같은 모양**(`BuildingHit`). 그 줄의 대표 동을 고른 셈이다.
 *
 * ⛔ 통째로 넘기지 않고 칸을 하나씩 옮겨 담는다(`landToHit` 과 같은 이유). 그대로 넘기면
 *    `match_store_cnt` 가 선택된 건물 상태에 얹혀 흘러다닌다 — 그 값은 "이 **땅**의 가게
 *    수"인데 이름만 보면 건물 것으로 읽히므로, 나중에 누군가 층별 화면에서 그것을 쓰는 날
 *    조용히 틀린다.
 * ⓘ 비어 있을 수 있는 칸에는 `BuildingHit` 이 요구하는 만큼만 기본값을 채운다 — `floor_cnt`
 *   0 은 화면이 이미 "층 정보 없음"으로 다루는 값이다(`describeRange`).
 */
export function storeToHit(s: StoreHit & { bld_id: string }): BuildingHit {
  return {
    bld_id: s.bld_id,
    pnu: s.pnu,
    bld_nm: s.bld_nm,
    road_addr: s.road_addr,
    jibun_addr: s.jibun_addr,
    lat: s.lat,
    lng: s.lng,
    bld_cnt_in_pnu: s.bld_cnt_in_pnu ?? 1,
    floor_cnt: s.floor_cnt ?? 0,
    min_floor: s.min_floor,
    max_floor: s.max_floor,
    has_roof: s.has_roof ?? false,
  };
}

/**
 * 줄에 적을 일치 상호 — "스타벅스 · 스타벅스강남 외 3곳". 적을 것이 없으면 null.
 *
 * ⓘ 서버가 상호를 **최대 3개**만 보낸다. 그보다 많이 걸렸으면 "외 N곳"으로 그 사실을
 *   적는다 — 안 적으면 3곳뿐인 것으로 읽힌다.
 * ⚠️ 뺄셈의 왼쪽은 **그 땅에서 걸린 가게 수**(`match_store_cnt`)이지 목록 길이가 아니다.
 */
export function matchedLabel(s: StoreHit): string | null {
  const names = (s.matched_names ?? []).filter((n) => n.trim() !== '');
  if (names.length === 0) return null;
  const rest = (s.match_store_cnt ?? 0) - names.length;
  const shown = names.join(' · ');
  return rest > 0 ? `${shown} 외 ${rest.toLocaleString('ko-KR')}곳` : shown;
}

/**
 * 더 받아 올 것이 남았는가.
 *
 * ⚠️ 서버가 준 전체 수와 **지금 손에 든 줄 수**를 견준다. 받아 온 쪽수를 세지 않는 이유는
 *    마지막 쪽이 딱 떨어지게 오는 경우("50곳을 받았는데 그게 전부")를 쪽수만으로는 못
 *    가리기 때문이다 — 그러면 '더 보기'가 남아 있다가 눌러도 아무 일이 없다.
 */
export function hasMoreStores(rows: readonly StoreHit[]): boolean {
  return rows.length > 0 && rows.length < rows[0].total_parcel_cnt;
}
