import type { BuildingHit, DistrictLand, ParcelBuilding } from '../types';
import { chipMatch, type FounderChip } from './founderChips';

/**
 * 상권 → 건물 목록의 **순수 계산**만 모은다.
 *
 * 컴포넌트에서 빼 둔 이유는 `lhNotices.ts`·`industryMix.ts` 와 같다 — 여기 있는 규칙들은
 * 화면을 띄우지 않고도 시험할 수 있어야 하고, 실제로 틀리기 쉬운 곳이 전부 여기다
 * (서버 응답 모양 · 땅↔건물 바꿔 담기 · "몇 곳 중 몇 곳" 세기 · 더 받을 것이 남았는지).
 */

function isNullableString(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'string';
}

function isNullableNumber(x: unknown): boolean {
  return x === null || x === undefined || typeof x === 'number';
}

/** 없거나 null 이거나 0 이상의 정수(개수 칸). */
function isOptionalCount(x: unknown): boolean {
  return x === null || x === undefined || (Number.isInteger(x) && (x as number) >= 0);
}

/**
 * 서버 응답의 **모양**을 본다.
 *
 * 타입 단언(`as DistrictLand[]`)은 컴파일 때만 사는 약속이라 런타임에는 아무것도 막아
 * 주지 않는다. 뜻밖의 답(마이그레이션 전 라이브의 오류 객체, 다른 함수의 응답)이 그대로
 * 렌더로 흘러 들어가면 그 자리에서 터지는데, 이 목록은 **지도 안**에 있어 터지면 지도까지
 * 함께 사라진다 — 곁다리 하나 때문에 본체를 잃지 않는다.
 */
export function isDistrictLand(x: unknown): x is DistrictLand {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.pnu === 'string' &&
    typeof r.store_cnt === 'number' &&
    typeof r.bld_cnt_in_pnu === 'number' &&
    typeof r.bld_id === 'string' &&
    typeof r.floor_cnt === 'number' &&
    typeof r.has_roof === 'boolean' &&
    typeof r.total_parcel_cnt === 'number' &&
    typeof r.total_bld_cnt === 'number' &&
    isNullableString(r.bld_nm) &&
    isNullableString(r.road_addr) &&
    isNullableString(r.jibun_addr) &&
    isNullableNumber(r.lat) &&
    isNullableNumber(r.lng) &&
    isNullableNumber(r.min_floor) &&
    isNullableNumber(r.max_floor)
    // ⓘ 업종 칩 점포 수(cat_store_cnt · 2026-10-11a)는 여기서 안 본다 — 선택 칸이라 이상한 값이어도
    //   그 줄·그 목록을 버리지 않고 `toDistrictLands` 가 그 칸만 지운다(임대 floor_rent·LH 교훈).
  );
}

/** ⓘ 빈 배열은 **정상**이다 — 상권 1,687곳 중 10곳은 건물이 한 동도 없다(라이브 실측). */
export function isDistrictLandList(x: unknown): x is DistrictLand[] {
  return Array.isArray(x) && x.every(isDistrictLand);
}

/**
 * 서버 답 → 화면이 쓸 목록. 모양이 틀리면 null(목록째 실패 — 지금 규칙 그대로).
 *
 * ⛔ 선택 칸 `cat_store_cnt`(고른 업종 점포 수)만은 이상한 값(음수·소수·글자)이어도 목록을 버리지 않는다 —
 *    **그 칸만 지운다**. 그러면 그 줄은 `점포 N곳` 꼴로 물러선다(`landStoreText`). 곁 칸 하나 때문에 목록이
 *    '불러오지 못했습니다'가 되면 안 된다(임대 카드 floor_rent · LH `.every()` 교훈).
 */
export function toDistrictLands(x: unknown): DistrictLand[] | null {
  if (!isDistrictLandList(x)) return null;
  return x.map((land) => {
    if (isOptionalCount(land.cat_store_cnt)) return land;
    const { cat_store_cnt: _bad, ...rest } = land;
    return rest;
  });
}

export function isParcelBuilding(x: unknown): x is ParcelBuilding {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.bld_id === 'string' &&
    typeof r.floor_cnt === 'number' &&
    typeof r.has_roof === 'boolean' &&
    isNullableString(r.bld_nm) &&
    isNullableString(r.dong_nm) &&
    isNullableNumber(r.total_area_m2) &&
    isNullableNumber(r.min_floor) &&
    isNullableNumber(r.max_floor)
  );
}

export function isParcelBuildingList(x: unknown): x is ParcelBuilding[] {
  return Array.isArray(x) && x.every(isParcelBuilding);
}

/**
 * 땅 한 줄 → 검색 결과와 **같은 모양**(`BuildingHit`). 그 줄의 대표 동을 고른 셈이다.
 *
 * ⛔ 통째로 넘기지 않고 칸을 하나씩 옮겨 담는다. `DistrictLand` 는 구조상 `BuildingHit`
 *    을 이미 만족하지만(타입스크립트는 모양만 본다), 그대로 넘기면 **`store_cnt` 가
 *    선택된 건물 상태에 얹혀 흘러다닌다.** 그 값은 "이 **땅**의 점포 수"인데 이름만 보면
 *    건물 것으로 읽히므로, 나중에 누군가 층별 화면에서 그것을 쓰는 날 조용히 틀린다.
 * ⓘ `total_cnt` 는 담지 않는다 — 그건 "검색어에 걸린 전체 건물 수"라 여기서는 뜻이 없다.
 *   비워 두면 화면이 알아서 생략한다(선택 필드).
 */
export function landToHit(land: DistrictLand): BuildingHit {
  return {
    bld_id: land.bld_id,
    pnu: land.pnu,
    bld_nm: land.bld_nm,
    road_addr: land.road_addr,
    jibun_addr: land.jibun_addr,
    lat: land.lat,
    lng: land.lng,
    bld_cnt_in_pnu: land.bld_cnt_in_pnu,
    floor_cnt: land.floor_cnt,
    min_floor: land.min_floor,
    max_floor: land.max_floor,
    has_roof: land.has_roof,
  };
}

/**
 * 펼친 동 하나 → `BuildingHit`.
 *
 * ⓘ 주소·좌표는 **그 땅**의 것이다(동 목록 함수는 주소를 주지 않는다 — 같은 땅이므로
 *   똑같은 값을 동 수만큼 실어 보낼 이유가 없다). 검색이 주는 좌표도 필지 좌표라
 *   여기서만 다른 규칙을 쓰는 것이 아니다(`types.ts` 의 `lat` 주석).
 */
export function parcelBuildingToHit(land: DistrictLand, b: ParcelBuilding): BuildingHit {
  return {
    bld_id: b.bld_id,
    pnu: land.pnu,
    bld_nm: b.bld_nm,
    road_addr: land.road_addr,
    jibun_addr: land.jibun_addr,
    lat: land.lat,
    lng: land.lng,
    bld_cnt_in_pnu: land.bld_cnt_in_pnu,
    floor_cnt: b.floor_cnt,
    min_floor: b.min_floor,
    max_floor: b.max_floor,
    has_roof: b.has_roof,
  };
}

/**
 * 목록 머리에 적을 한 줄 — "이 상권에 955곳 · 1,098동 · 이 중 50곳".
 *
 * ⛔ **잘렸다는 사실을 감추지 않는다.** 50곳만 보여 주면서 전체를 안 적으면 "이 상권엔
 *    50곳뿐"으로 읽힌다(검색이 "이 중 N개만 보여드립니다"를 적는 것과 같은 이유).
 * ⓘ 땅 수와 동 수를 **둘 다** 적는다. 한 줄이 땅 하나라 세로줄 수는 땅 수인데, 사람이
 *   세고 싶은 것은 대개 건물 수다 — 둘이 다르다는 사실(955곳에 1,098동)을 숨기면
 *   "왜 1,098동이라더니 955줄이지?" 가 된다.
 */
export function landsSummary(lands: readonly DistrictLand[]): string {
  if (lands.length === 0) return '';
  const { total_parcel_cnt: parcels, total_bld_cnt: blds } = lands[0];
  const head = `${parcels.toLocaleString('ko-KR')}곳 · 건물 ${blds.toLocaleString('ko-KR')}동`;
  return lands.length < parcels ? `${head} · 이 중 ${lands.length}곳` : head;
}

/**
 * 더 받아 올 것이 남았는가.
 *
 * ⚠️ 서버가 준 전체 수(`total_parcel_cnt`)와 **지금 손에 든 줄 수**를 견준다. 받아 온
 *    쪽수를 세지 않는 이유는, 마지막 쪽이 딱 떨어지게 오는 경우("50곳을 받았는데 그게
 *    전부") 를 쪽수만으로는 못 가리기 때문이다 — 그러면 '더 보기'가 남아 있다가 눌러도
 *    아무 일이 없다.
 */
export function hasMore(lands: readonly DistrictLand[]): boolean {
  return lands.length > 0 && lands.length < lands[0].total_parcel_cnt;
}

// ── 창업자 업종 칩(2026-10-11a · 물결 2-2b · 결정 0036 결정 18 ⑨·㉒) ─────────────────

/**
 * 목록 함수에 보낼 인자. 칩을 골랐으면 그 칩의 짝 중분류 코드(`CHIP_MATCH[칩].catM`)를 `p_cat_m` 으로.
 *
 * ⛔ 칩 '전체'면 `p_cat_m` 을 **아예 안 넣는다**(null 도 안 보낸다) — 마이그레이션 전 라이브(인자 셋짜리
 *    함수)에서도 칩 없는 손님의 목록이 그대로 서게. '더 보기'도 같은 인자로 부른다.
 */
export function districtLandsArgs(
  districtId: string,
  limit: number,
  offset: number,
  chip: FounderChip,
): Record<string, unknown> {
  const args: Record<string, unknown> = { p_district_id: districtId, p_limit: limit, p_offset: offset };
  const match = chipMatch(chip);
  if (match) args.p_cat_m = [...match.catM];
  return args;
}

/**
 * 한 줄의 점포 숫자. 칩을 골랐고 서버가 그 수를 줬으면 **둘 다**(👤 2026-10-11):
 * `고른 업종(카페) 3곳 · 전체 점포 25곳`. 아니면 지금 글 그대로 `점포 25곳`.
 * ⓘ '고른 업종(…)' 은 업종 분포·개업·폐업 카드와 같은 말이다('칩'은 손님 말이 아니다).
 */
export function landStoreText(land: DistrictLand, chip: FounderChip): string {
  const all = land.store_cnt.toLocaleString('ko-KR');
  if (chipMatch(chip) && typeof land.cat_store_cnt === 'number') {
    return `고른 업종(${chip}) ${land.cat_store_cnt.toLocaleString('ko-KR')}곳 · 전체 점포 ${all}곳`;
  }
  return `점포 ${all}곳`;
}

/**
 * 낱말 + 받침에 맞는 '이'/'가'(`카페가` · `학원이`). 칩 이름은 전부 한글로 끝난다(`founderChips` 표).
 * ⓘ 빈 상태 글(`noLandText`)과 목록 머릿글이 같은 함수를 쓴다 — 두 곳이 다른 조사를 쓰지 않게.
 */
export function withSubjectParticle(word: string): string {
  const code = word.charCodeAt(word.length - 1);
  return word + ((code - 0xac00) % 28 === 0 ? '가' : '이');
}

/**
 * 칩을 골랐는데 그 업종 점포가 있는 땅이 하나도 없을 때. 코드가 둘인 칩(학원)도 칩 이름 하나로 말한다.
 * 칩 '전체'면 null — 그때는 지금 글('아직 건물 자료가 없습니다') 그대로다.
 */
export function noLandText(chip: FounderChip): string | null {
  if (!chipMatch(chip)) return null;
  return `이 상권에는 ${withSubjectParticle(chip)} 있는 땅이 없습니다.`;
}
