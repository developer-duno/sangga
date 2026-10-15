/**
 * 상권 지도에서 누른 것의 기억(👤 2026-10-15 G1 「다시 펴면 그대로 되살리기」).
 *
 * 입구가 접히면(S1) 지도는 아예 안 그려진다. 다시 그릴 때 아까 누른 상권과 펼친 건물 목록이 그대로 서도록
 * 지도 바깥(App)이 이 값을 쥐고 `DistrictMap` 에 넘긴다.
 *
 * 상권 **번호**만 쥔다 — 경계 도형은 지도가 받아 둔 파일에서 다시 찾는다.
 * - `sigungu` = 어느 구에서 누른 것인가(다른 구 지도에는 안 쓴다)
 * - `pickedIds` = 누른 자리에 걸친 상권(null = 아직 안 누름)
 * - `openId` = 건물 목록을 펼친 상권
 *
 * ⛔ 화면 상태만 — 이 기기 저장·주소·의견함에 싣지 않는다 · 구가 바뀌면 비운다.
 */
export type DistrictMapPick = { sigungu: string | null; pickedIds: string[] | null; openId: string | null };

export const EMPTY_MAP_PICK: DistrictMapPick = { sigungu: null, pickedIds: null, openId: null };
