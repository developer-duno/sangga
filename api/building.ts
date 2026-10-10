// 건물 주소(`/?sgg=&bld=`)의 첫 HTML — 레포 루트 middleware.ts(Routing Middleware · bld 가 건물 번호 꼴일 때만)가
// 여기로 보낸다(결정 0037). `/api/building?sgg=…&bld=…` 직접 호출도 같게 동작한다.
// 본체는 src/lib/buildingHandler.ts(시험은 그쪽). 되돌리기 = middleware.ts 를 지운다(이 파일은 남아도 안 불린다).
import { handleBuilding } from '../src/lib/buildingHandler.js';

export default {
  fetch: (request: Request) => handleBuilding(request, { fetch: globalThis.fetch, env: process.env }),
};
