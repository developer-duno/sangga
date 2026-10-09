// 건물 주소(`/?sgg=&bld=`)만 서버 조각 함수로 넘긴다(결정 0037 · Routing Middleware).
// 판정은 src/lib/buildingRoute.ts(시험은 그쪽). 되돌리기 = 이 파일을 지운다.
import { next, rewrite } from '@vercel/functions';
import { buildingRewriteTarget } from './src/lib/buildingRoute.js';

export const config = { matcher: '/', runtime: 'nodejs' };

export default function middleware(request: Request) {
  const dest = buildingRewriteTarget(request.url);
  return dest ? rewrite(new URL(dest)) : next();
}
