/*
  구 입구 주소 요청을 받아 그 구의 허브 첫 HTML 을 돌려주는 서버 조각의 본체(결정 0043 · `api/hub.ts` 가 부른다).

  흐름: `/?sgg=<5자리>`(bld 없음) → 레포 루트 `middleware.ts`(판정 `buildingRoute.ts` 의 `hubRewriteTarget` ·
        `/api/hub?sgg=<sgg>`) → 여기. 직접 불러도 똑같이 동작한다.
    ① 같은 배포의 `/index.html` ② 같은 배포의 `/hub/<sgg>.json`(빌드 때 `scripts/build_sitemap.py` 가 굽는다 · 요청 때 DB 0)
       — 둘은 함께 보낸다(각 3초 · 허용 호스트 규칙 = 건물 쪽 `homeSource` 그대로)
    ③ `renderHubHtml` 로 머리글·h1·소개문·내부 링크·빵부스러기만 바꾼다
  ⓐ sgg 꼴 틀림 → 첫 화면 그대로(하루 캐시)
  ⓑ 첫 화면 HTML 을 못 받음 → 307 `/index.html?sgg=<sgg>`(no-store) — 정적 파일로 앱을 띄운다
  ⓒ 허브 파일 404(모르는 구 · 아직 안 구운 구) → 첫 화면 그대로(하루 캐시 — 지금과 같다)
  ⓓ 허브 파일 그 밖 실패(200·404 아닌 응답 · 네트워크 · 시간 초과) → **503 + Retry-After 120** + 첫 화면(no-store)
  ⓔ 허브 파일 모양 틀림 · 치환 실패 → 첫 화면 200(no-store) + console.error
  ⓕ 정상 → 허브 HTML(하루 캐시 + 일주일 stale-while-revalidate)

  ⛔ 사람·봇 모두 같은 HTML — User-Agent 로 가르지 않는다(건물 쪽과 같다).
  ⛔ 들어온 요청의 cookie 는 **첫 화면 HTML fetch 에만**(건물 쪽 `fetchHome` 그대로) — 허브 파일 fetch 에는 안 싣는다.
     ⓘ 그래서 배포 보호가 걸린 미리보기 배포에서는 허브 파일이 401 → ⓓ 503 이 된다(사람 화면은 그대로 뜬다 · 운영 정식 주소는 보호 없음).
  ⛔ 의존(fetch·env)은 주입받는다 — 시험은 가짜 fetch 로 외부 호출 0.
  ⛔ import 는 `.js` 확장자 — 함수 런타임(Node ESM).
*/
import { FETCH_TIMEOUT_MS, CACHE_HOME, CACHE_NONE, RETRY_AFTER_S, fetchHome, homeSource, type HandlerDeps } from './buildingHandler.js';
import { isHubData, isSgg, renderHubHtml } from './hubHead.js';

/** 허브 HTML — 하루 + 일주일 stale-while-revalidate(건물 쪽 `CACHE_BUILDING` 과 같은 값). */
export const CACHE_HUB = 'public, s-maxage=86400, stale-while-revalidate=604800';

type HubFetch = { kind: 'ok'; text: string } | { kind: 'missing' } | { kind: 'fail' };

function html(body: string, status: number, cache: string, extra: Record<string, string> = {}): Response {
  return new Response(body, {
    status,
    headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': cache, ...extra },
  });
}

/** 같은 배포의 `/hub/<sgg>.json` — 첫 화면과 같은 곳(허용 호스트면 그 배포 · 아니면 정식 주소) · cookie 0 · 3초. */
async function fetchHub(sgg: string, request: Request, deps: HandlerDeps): Promise<HubFetch> {
  const { origin } = homeSource(request, deps.env);
  try {
    const res = await deps.fetch(`${origin}/hub/${sgg}.json`, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) });
    if (res.status === 404) return { kind: 'missing' };
    if (res.status !== 200) return { kind: 'fail' };
    return { kind: 'ok', text: await res.text() };
  } catch {
    return { kind: 'fail' };
  }
}

export async function handleHub(request: Request, deps: HandlerDeps): Promise<Response> {
  const url = new URL(request.url);
  const param = url.searchParams.get('sgg');
  const sgg = isSgg(param) ? (param as string) : null;

  const [home, hub] = await Promise.all([
    fetchHome(request, deps),
    sgg ? fetchHub(sgg, request, deps) : Promise.resolve(null),
  ]);

  if (home === null) {
    // ⓑ 첫 화면 HTML 조차 못 받으면 정적 파일로 — 앱이 주소의 sgg 로 구 화면을 띄운다.
    return new Response(null, {
      status: 307,
      headers: { location: `/index.html${sgg ? `?sgg=${sgg}` : ''}`, 'cache-control': CACHE_NONE },
    });
  }
  if (!sgg || hub === null) return html(home, 200, CACHE_HOME); // ⓐ
  if (hub.kind === 'missing') return html(home, 200, CACHE_HOME); // ⓒ
  if (hub.kind === 'fail') return html(home, 503, CACHE_NONE, { 'retry-after': RETRY_AFTER_S }); // ⓓ

  let data: unknown;
  try {
    data = JSON.parse(hub.text);
  } catch (e) {
    console.error('구 허브 파일이 JSON 이 아닙니다', sgg, e);
    return html(home, 200, CACHE_NONE); // ⓔ
  }
  if (!isHubData(data, sgg)) {
    console.error('구 허브 파일 모양이 틀렸습니다', sgg);
    return html(home, 200, CACHE_NONE); // ⓔ
  }
  try {
    return html(renderHubHtml(home, data), 200, CACHE_HUB); // ⓕ
  } catch (e) {
    console.error('구 허브 머리글 치환 실패', sgg, e);
    return html(home, 200, CACHE_NONE); // ⓔ
  }
}
