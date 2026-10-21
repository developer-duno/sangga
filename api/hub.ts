// 구 입구 주소(`/?sgg=<5자리>` · bld 없음)의 첫 HTML — 레포 루트 middleware.ts(Routing Middleware)가 여기로 보낸다(결정 0043).
// `/api/hub?sgg=…` 직접 호출도 같게 동작한다. 본체는 src/lib/hubHandler.ts(시험은 그쪽).
// 되돌리기 = middleware.ts 의 `?? hubRewriteTarget(…)` 를 지운다(이 파일은 남아도 안 불린다).
import { handleHub } from '../src/lib/hubHandler.js';

export default {
  fetch: (request: Request) => handleHub(request, { fetch: globalThis.fetch, env: process.env }),
};
