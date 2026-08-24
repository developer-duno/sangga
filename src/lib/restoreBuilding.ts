import type { BuildingHit, FloorRow } from '../types';

/**
 * 층 목록(`v_floor_stack` 행들)에서 **건물 한 채의 요약**을 되살린다.
 *
 * 왜 필요한가
 * -----------
 * 링크로 들어온 사람은 **검색을 거치지 않는다.** 지금 화면이 건물 정보(이름·주소·
 * 좌표·층 범위)를 얻는 길은 검색(`search_buildings`) 하나뿐이라, 주소에 건물 번호만
 * 있는 상태에서는 그 정보를 만들 수가 없다.
 *
 * 다행히 층 목록이 같은 값을 이미 갖고 있다. 새 서버 함수를 만들 필요 없이 층 행들을
 * 접어서 검색이 주는 것과 **같은 모양**을 만든다.
 *
 * ⛔ 층수 세는 규칙을 여기서 새로 정하면 안 된다
 * ---------------------------------------------
 * 검색 서버(`search_buildings`, schema.sql)가 쓰는 규칙을 **글자 그대로** 옮겼다:
 *
 *     floor_cnt  = 전체 층 행 수            ← 옥탑(99)도 **센다**
 *     min_floor  = min(floor_no) 단 99 제외 ← 옥탑은 "최고층"이 아니다
 *     max_floor  = max(floor_no) 단 99 제외
 *     has_roof   = 99 가 하나라도 있으면 참
 *
 * 규칙이 갈리면 **같은 건물인데 들어온 길에 따라 "지하2~15층"과 "지하2~99층"이 갈린다.**
 * 좌표를 geom 한 곳에서만 뽑기로 못박은 것과 정확히 같은 이유다(2026-08-25a).
 * ⚠️ 서버 쪽 규칙을 고치면 이 함수와 `restoreBuilding.test.ts` 를 같은 커밋에서 고친다.
 *
 * ⓘ 검색만 주는 칸(`jibun_addr`·`total_cnt`)은 층 목록에 없어 비워 둔다 — 둘 다 선택
 *    필드라 화면이 알아서 생략한다(지번은 검색 결과 목록에서만 쓰인다).
 */
export function buildingFromFloorRows(rows: FloorRow[]): BuildingHit | null {
  // 층이 한 줄도 없는 건물이 실재한다(239동, 2026-08-22 실측). 그런 건물은 링크로
  // 되살릴 수 없다 — 없는 것을 지어내지 않고 null 을 돌려준다(화면이 정직하게 안내한다).
  if (rows.length === 0) return null;

  const head = rows[0];

  // 옥탑(99)은 층 범위에서 뺀다. `절대 규칙 4` — 지상 n=n / 지하 n=-n / 옥탑=99.
  let min: number | null = null;
  let max: number | null = null;
  let hasRoof = false;
  for (const row of rows) {
    if (row.floor_no === 99) {
      hasRoof = true;
      continue;
    }
    if (min === null || row.floor_no < min) min = row.floor_no;
    if (max === null || row.floor_no > max) max = row.floor_no;
  }

  return {
    bld_id: head.bld_id,
    pnu: head.pnu,
    bld_nm: head.bld_nm,
    road_addr: head.road_addr,
    lat: head.lat ?? null,
    lng: head.lng ?? null,
    bld_cnt_in_pnu: head.bld_cnt_in_pnu,
    floor_cnt: rows.length,
    min_floor: min,
    max_floor: max,
    has_roof: hasRoof,
  };
}
