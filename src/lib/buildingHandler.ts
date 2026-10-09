/*
  건물 주소 요청을 받아 첫 HTML 을 돌려주는 서버 조각의 본체(결정 0037 · `api/building.ts` 가 부른다).

  흐름: `/?sgg=&bld=` → 레포 루트 `middleware.ts`(Routing Middleware · bld 가 건물 번호 꼴일 때만 ·
        `/api/building?<원래 query>`) → 여기. 직접 불러도 똑같이 동작한다(bld 는 요청 주소의 query 에서 읽는다).
    ① 같은 배포의 `/index.html`(빌드 산출물) ② Supabase REST `api.v_floor_stack` 의 그 건물 행
       — 둘은 서로 기다릴 이유가 없어 함께 보낸다(각 3초 제한)
    ③ `renderBuildingHtml` 로 머리글·소개문만 바꾼다
  ⓐ bld 없음/꼴 틀림 → 첫 화면 그대로(하루 캐시)
  ⓑ 환경변수 없음·Supabase 실패 → **503 + Retry-After 120** + 첫 화면 HTML(no-store) —
     사람 화면은 그대로 뜨고(앱이 스스로 다시 읽는다), 봇은 '잠깐 실패'로 알고 나중에 다시 온다
  ⓒ 행 0 → 404 + noindex(앱은 "못 찾음"을 띄운다 · 구글이 쓰레기 주소를 색인하지 않게)
  ⓓ 이름 없음 → 첫 화면 그대로(지금처럼 첫 화면에 합쳐진다)
  ⓔ 이름 있음 → 그 건물의 HTML(하루 캐시 + 일주일 stale-while-revalidate) — 비주거 층이 없으면 noindex 한 줄 더
  ⓕ 첫 화면 HTML 을 못 받음 → 307 `/index.html?<원래 query>`(no-store) — 정적 파일로 앱을 띄운다

  ⛔ 사람·봇 모두 같은 HTML — User-Agent 로 가르지 않는다(구글: 동적 렌더링은 '우회책').
  ⛔ 들어온 요청의 cookie 는 **첫 화면 HTML fetch 에만** 넘긴다(미리보기 배포 보호 통과용) — Supabase 로는 안 보낸다.
  ⛔ 의존(fetch·env)은 주입받는다 — 시험은 가짜 fetch 로 외부 호출 0.
  ⛔ import 는 `.js` 확장자 — 함수 런타임(Node ESM)은 확장자 없는 상대 import 를 못 찾는다(tsconfig.api.json nodenext 가 잡는다).
*/
import { isBldId, renderBuildingHtml, withNoindex, type BuildingRow } from './buildingHead.js';

export type HandlerDeps = {
  fetch: (input: string, init?: RequestInit) => Promise<Response>;
  env: Record<string, string | undefined>;
};

export const CACHE_HOME = 'public, s-maxage=86400';
export const CACHE_BUILDING = 'public, s-maxage=86400, stale-while-revalidate=604800';
export const CACHE_NOT_FOUND = 'public, s-maxage=600';
export const CACHE_NONE = 'no-store';
export const RETRY_AFTER_S = '120';
export const FETCH_TIMEOUT_MS = 3000;

const SELECT = 'bld_id,pnu,floor_no,floor_label,segment_cnt,main_use,uses,bld_nm,road_addr';

function html(body: string, status: number, cache: string, extra: Record<string, string> = {}): Response {
  return new Response(body, {
    status,
    headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': cache, ...extra },
  });
}

function firstValue(v: string | null): string | null {
  const t = v?.split(',')[0]?.trim();
  return t ? t : null;
}

/** 같은 배포의 주소 — x-forwarded-proto + x-forwarded-host, 없으면 요청 주소의 origin. */
export function siteOrigin(request: Request): string {
  const proto = firstValue(request.headers.get('x-forwarded-proto'));
  const host = firstValue(request.headers.get('x-forwarded-host'));
  if (proto && host && /^https?$/.test(proto) && /^[a-z0-9.-]+(:\d+)?$/i.test(host)) {
    return `${proto}://${host}`;
  }
  return new URL(request.url).origin;
}

async function fetchHome(request: Request, deps: HandlerDeps): Promise<string | null> {
  const cookie = request.headers.get('cookie');
  try {
    const res = await deps.fetch(`${siteOrigin(request)}/index.html`, {
      headers: cookie ? { cookie } : {},
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    return res.status === 200 ? await res.text() : null;
  } catch {
    return null;
  }
}

async function fetchRows(bldId: string, base: string, key: string, deps: HandlerDeps): Promise<BuildingRow[] | null> {
  const url =
    `${base.replace(/\/+$/, '')}/rest/v1/v_floor_stack` +
    `?bld_id=eq.${encodeURIComponent(bldId)}&select=${SELECT}&order=floor_no.asc.nullslast`;
  try {
    const res = await deps.fetch(url, {
      headers: { apikey: key, Authorization: `Bearer ${key}`, 'Accept-Profile': 'api' },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (res.status !== 200) return null;
    const data: unknown = await res.json();
    return Array.isArray(data) ? (data as BuildingRow[]) : null;
  } catch {
    return null;
  }
}

export async function handleBuilding(request: Request, deps: HandlerDeps): Promise<Response> {
  const url = new URL(request.url);
  const bldParam = url.searchParams.get('bld')?.trim() ?? null;
  const wanted = isBldId(bldParam) ? (bldParam as string) : null;

  const base = deps.env.VITE_SUPABASE_URL;
  const key = deps.env.VITE_SUPABASE_ANON_KEY;
  const noEnv = wanted !== null && (!base || !key);
  if (noEnv) console.error('건물 첫 HTML: VITE_SUPABASE_URL·VITE_SUPABASE_ANON_KEY 가 함수 환경에 없습니다');

  const [home, rows] = await Promise.all([
    fetchHome(request, deps),
    wanted && !noEnv ? fetchRows(wanted, base as string, key as string, deps) : Promise.resolve(null),
  ]);

  if (home === null) {
    // ⓕ 첫 화면 HTML 조차 못 받으면 정적 파일로 보낸다 — 앱이 주소의 query 로 건물을 되살린다.
    return new Response(null, {
      status: 307,
      headers: { location: `/index.html${url.search}`, 'cache-control': CACHE_NONE },
    });
  }
  if (!wanted) return html(home, 200, CACHE_HOME); // ⓐ
  if (rows === null) return html(home, 503, CACHE_NONE, { 'retry-after': RETRY_AFTER_S }); // ⓑ
  if (rows.length === 0) return html(withNoindex(home), 404, CACHE_NOT_FOUND); // ⓒ
  let page: string | null;
  try {
    page = renderBuildingHtml(home, rows);
  } catch (e) {
    // 첫 화면 HTML 의 모양이 바뀌어 치환 가드에 걸렸다 — 첫 화면을 주되 굳히지 않는다.
    console.error('건물 머리글 치환 실패', e);
    return html(home, 200, CACHE_NONE);
  }
  if (page === null) return html(home, 200, CACHE_HOME); // ⓓ
  return html(page, 200, CACHE_BUILDING); // ⓔ
}
