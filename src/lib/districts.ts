import type { DistrictGeoJson } from '../types';

/**
 * 상권 경계 정적 파일 하나만 읽는 창구.
 *
 * 이 파일은 `public/` 에 있어 번들에 들어가지 않는다 — 첫 화면이 1.13MB를 지고
 * 시작하지 않게 하려는 것이다(지도를 펴는 사람만 받는다).
 *
 * 한 번 받으면 세션 내내 다시 받지 않는다. 구를 바꿀 때마다 다시 받으면 같은
 * 1.13MB를 계속 나른다 — 파일 하나에 1,687개가 전부 들어 있고 구별로 걸러 쓰기만 하면 된다.
 */
export const DISTRICT_GEOJSON_URL = '/districts.geojson';

/** 진행 중인 요청까지 함께 잡아 둔다 — 두 곳에서 동시에 불러도 왕복은 한 번이다. */
let cached: Promise<DistrictGeoJson> | null = null;

export function loadDistricts(): Promise<DistrictGeoJson> {
  if (!cached) {
    cached = fetch(DISTRICT_GEOJSON_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`상권 경계 파일 응답이 ${res.status} 입니다`);
        return res.json() as Promise<DistrictGeoJson>;
      })
      .catch((err) => {
        // ⚠️ 실패는 캐시하지 않는다. 여기서 지우지 않으면 잠깐 끊겼던 한 번 때문에
        //    새로고침 전까지 지도가 영영 안 뜬다(다시 시도할 길이 막힌다).
        cached = null;
        throw err;
      });
  }
  return cached;
}
