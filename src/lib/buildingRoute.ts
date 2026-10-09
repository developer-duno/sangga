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

/** 넘길 주소(절대 주소) 또는 null. */
export function buildingRewriteTarget(input: string): string | null {
  const url = new URL(input);
  if (url.pathname !== '/') return null;
  if (!isBldId(url.searchParams.get('bld'))) return null;
  const dest = new URL('/api/building', url);
  dest.search = url.search; // ?sgg=…&bld=… 그대로
  return dest.href;
}
