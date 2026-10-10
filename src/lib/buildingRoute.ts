/*
  middleware(Routing Middleware · 레포 루트 `middleware.ts`)의 순수 판정(결정 0037).

  왜 middleware 인가: `vercel.json` rewrite 는 `/` 에서 안 탄다 — Vercel 공식 vercel-json 문서
  "The source property should NOT be a file because precedence is given to the filesystem prior to
  rewrites" (`/` 는 index.html 파일이다). 공식 대안이 Routing Middleware(vercel.com/docs/routing-middleware/api).

  ⛔ 주소가 `/` 이고 `bld` 가 건물 번호 꼴일 때만 `/api/building?<원래 query 그대로>` 로 넘긴다.
     그 밖(다른 경로·정적 파일·bld 없음·꼴 틀림)은 null → 손대지 않는다(SPA 폴백이 아니다).
  ⛔ 함수 런타임에서 돈다 — import 는 `.js` 확장자 · 건물 번호 꼴은 buildingHead.ts 의 isBldId 하나.
*/
import { isBldId } from './buildingHead.js';

/**
 * 넘길 주소(절대 주소) 또는 null.
 * ⛔ `sgg`·`bld` 두 값만 다시 조립한다(sgg 먼저) — 낯선 인자(`&x=랜덤`)를
 *    그대로 넘기면 주소마다 CDN 캐시가 새로 생겨 함수·Supabase 호출이 한도를 쓴다(적대 검사 🟡 2026-10-09).
 * ⛔ sgg 는 받은 값이 아니라 bld 앞 5자리(pnu 의 시군구)로 채운다 — 처리 함수는 sgg 를 안 쓰고
 *    (정식 주소도 pnu 앞 5자리 · buildingHead.ts canonicalUrl), 받은 값을 넘기면 `sgg=00000`~`99999`
 *    만큼 같은 건물의 캐시 칸이 갈라진다(PR② 적대 검사 🟡 후속 · 2026-10-10).
 */
export function buildingRewriteTarget(input: string): string | null {
  const url = new URL(input);
  if (url.pathname !== '/') return null;
  const bld = url.searchParams.get('bld');
  if (!isBldId(bld)) return null;
  const q = new URLSearchParams();
  q.set('sgg', (bld as string).slice(0, 5));
  q.set('bld', bld as string);
  const dest = new URL('/api/building', url);
  dest.search = q.toString();
  return dest.href;
}
