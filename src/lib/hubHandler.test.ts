import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { CACHE_HOME, CACHE_NONE, FETCH_TIMEOUT_MS, RETRY_AFTER_S, type HandlerDeps } from './buildingHandler';
import { CACHE_HUB, handleHub } from './hubHandler';
import { renderHubHtml, type HubData } from './hubHead';

/*
  구 허브 서버 조각 본체(결정 0043) — 가짜 fetch 로 ⓐ~ⓕ 를 하나씩. 외부 호출 0.
  렌더는 진짜(renderHubHtml) · 가짜는 가장 낮은 fetch 하나뿐.
*/

// ⚠️ jsdom 환경에서 `new URL(상대, import.meta.url)` 은 http://localhost 로 풀린다(실측) → 경로로 계산.
const HOME = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../index.html'), 'utf-8');

const SGG = '11680';
const PNU = '1168010100100010000';
const HUB: HubData = {
  sgg: SGG,
  sido_code: '11',
  sigungu_nm: '강남구',
  buildings: [{ bld_id: `${PNU}_1`, pnu: PNU, bld_nm: '가나 빌딩', road_addr: '서울특별시 강남구 테헤란로 1', bld_cnt: 1 }],
  parcels: {},
};

type Call = { url: string; init?: RequestInit };

function fakeFetch(hub: () => Response | Promise<Response>, home: () => Response | Promise<Response> = () => new Response(HOME)) {
  const calls: Call[] = [];
  const fn: HandlerDeps['fetch'] = async (url, init) => {
    calls.push({ url, init });
    if (url.endsWith('/index.html')) return home();
    if (/\/hub\/\d{5}\.json$/.test(url)) return hub();
    throw new Error(`예상 밖 fetch: ${url}`);
  };
  return { fn, calls };
}

function req(query: string, headers: Record<string, string> = {}, host = 'sangga-one.vercel.app'): Request {
  return new Request(`https://${host}/api/hub${query}`, { headers });
}

async function run(
  query: string,
  hub: () => Response | Promise<Response>,
  opts: { home?: () => Response | Promise<Response>; headers?: Record<string, string>; env?: HandlerDeps['env']; host?: string } = {},
) {
  const f = fakeFetch(hub, opts.home);
  const res = await handleHub(req(query, opts.headers, opts.host), { fetch: f.fn, env: opts.env ?? {} });
  return { res, body: await res.text(), calls: f.calls };
}

const okHub = () => new Response(JSON.stringify(HUB));

async function quietly<T>(fn: () => Promise<T>): Promise<{ out: T; logged: unknown[][] }> {
  const err = console.error;
  const logged: unknown[][] = [];
  console.error = (...a: unknown[]) => void logged.push(a);
  try {
    return { out: await fn(), logged };
  } finally {
    console.error = err;
  }
}

describe('handleHub', () => {
  it('ⓕ 정상 — 진짜 렌더 결과 그대로 · 200 · 하루 + 일주일 SWR · html', async () => {
    const { res, body, calls } = await run(`?sgg=${SGG}`, okHub);
    expect(res.status).toBe(200);
    expect(res.headers.get('cache-control')).toBe(CACHE_HUB);
    expect(CACHE_HUB).toBe('public, s-maxage=86400, stale-while-revalidate=604800');
    expect(res.headers.get('content-type')).toBe('text/html; charset=utf-8');
    expect(body).toBe(renderHubHtml(HOME, HUB));
    expect(body).toContain('<h1 class="seo-title">서울 강남구 상가 건물 층별 보기</h1>');
    expect(calls.map((c) => c.url).sort()).toEqual(['https://sangga-one.vercel.app/hub/11680.json', 'https://sangga-one.vercel.app/index.html']);
  });

  it('ⓐ sgg 꼴이 틀리거나 없으면 첫 화면 그대로 · 하루 캐시 · 허브 fetch 0', async () => {
    for (const q of ['', '?sgg=1168', '?sgg=abcde', '?sgg=116800']) {
      const { res, body, calls } = await run(q, okHub);
      expect(res.status, q).toBe(200);
      expect(res.headers.get('cache-control')).toBe(CACHE_HOME);
      expect(body).toBe(HOME);
      expect(calls.filter((c) => c.url.includes('/hub/'))).toEqual([]);
    }
  });

  it('ⓑ 첫 화면 HTML 을 못 받으면 307 /index.html?sgg= · no-store', async () => {
    for (const home of [() => new Response('x', { status: 500 }), () => Promise.reject(new TypeError('network'))]) {
      const { res, body } = await run(`?sgg=${SGG}&x=1`, okHub, { home });
      expect(res.status).toBe(307);
      expect(res.headers.get('location')).toBe('/index.html?sgg=11680');
      expect(res.headers.get('cache-control')).toBe(CACHE_NONE);
      expect(body).toBe('');
    }
  });

  it('ⓒ 허브 파일 404(모르는 구) → 첫 화면 그대로 200 · 하루 캐시', async () => {
    const { res, body } = await run('?sgg=99999', () => new Response('nope', { status: 404 }));
    expect(res.status).toBe(200);
    expect(res.headers.get('cache-control')).toBe(CACHE_HOME);
    expect(res.headers.get('retry-after')).toBeNull();
    expect(body).toBe(HOME);
  });

  it('ⓓ 허브 파일 그 밖 실패(500·401·206·네트워크) → 503 + Retry-After 120 + 첫 화면 · no-store', async () => {
    const fails: (() => Response | Promise<Response>)[] = [
      () => new Response('x', { status: 500 }),
      () => new Response('x', { status: 401 }),
      () => new Response('{}', { status: 206 }),
      () => Promise.reject(new TypeError('network')),
    ];
    for (const hub of fails) {
      const { res, body } = await run(`?sgg=${SGG}`, hub);
      expect(res.status).toBe(503);
      expect(res.headers.get('retry-after')).toBe(RETRY_AFTER_S);
      expect(RETRY_AFTER_S).toBe('120');
      expect(res.headers.get('cache-control')).toBe(CACHE_NONE);
      expect(body).toBe(HOME);
    }
  });

  it('양성 대조 — 404 와 500 은 다르게 간다(404 를 503 으로 뭉치면 잡힌다)', async () => {
    const a = await run(`?sgg=${SGG}`, () => new Response('', { status: 404 }));
    const b = await run(`?sgg=${SGG}`, () => new Response('', { status: 500 }));
    expect([a.res.status, b.res.status]).toEqual([200, 503]);
  });

  it('ⓔ 모양 틀림(JSON 아님 · 다른 구 파일 · 건물 0동) → 첫 화면 200 · no-store · console.error', async () => {
    const bads = [
      () => new Response('not json'),
      () => new Response(JSON.stringify({ ...HUB, sgg: '30140' })),
      () => new Response(JSON.stringify({ ...HUB, buildings: [] })),
      () => new Response('[]'),
    ];
    for (const hub of bads) {
      const { out, logged } = await quietly(() => run(`?sgg=${SGG}`, hub));
      expect(out.res.status).toBe(200);
      expect(out.res.headers.get('cache-control')).toBe(CACHE_NONE);
      expect(out.body).toBe(HOME);
      expect(logged.length).toBe(1);
    }
  });

  it('ⓔ 치환 실패(첫 화면 모양이 바뀜 · 시·도 이름표 없음) → 첫 화면 200 · no-store · console.error', async () => {
    const broken = HOME.replace(/<h1 class="seo-title">[^<]*<\/h1>/, '');
    const a = await quietly(() => run(`?sgg=${SGG}`, okHub, { home: () => new Response(broken) }));
    expect([a.out.res.status, a.out.res.headers.get('cache-control'), a.out.body]).toEqual([200, CACHE_NONE, broken]);
    expect(a.logged.length).toBe(1);
    const odd = { ...HUB, sgg: '99000', sido_code: '99', buildings: [{ ...HUB.buildings[0], bld_id: '9900010100100010000_1', pnu: '9900010100100010000' }] };
    const b = await quietly(() => run('?sgg=99000', () => new Response(JSON.stringify(odd))));
    expect([b.out.res.status, b.out.res.headers.get('cache-control'), b.out.body]).toEqual([200, CACHE_NONE, HOME]);
    expect(b.logged.length).toBe(1);
  });

  it('허용 호스트 — 미리보기 배포는 그 배포에서 · 남의 호스트는 정식 주소 고정(두 fetch 모두)', async () => {
    const env = { VERCEL_URL: 'sangga-abc.vercel.app' };
    const a = await run(`?sgg=${SGG}`, okHub, { env, host: 'sangga-abc.vercel.app' });
    expect(a.calls.map((c) => c.url).sort()).toEqual(['https://sangga-abc.vercel.app/hub/11680.json', 'https://sangga-abc.vercel.app/index.html']);
    const b = await run(`?sgg=${SGG}`, okHub, { env, headers: { 'x-forwarded-host': 'evil.example.com', cookie: 'k=v' } });
    expect(b.calls.map((c) => c.url).sort()).toEqual(['https://sangga-one.vercel.app/hub/11680.json', 'https://sangga-one.vercel.app/index.html']);
    for (const c of b.calls) expect(new Headers(c.init?.headers).get('cookie')).toBeNull();
  });

  it('cookie 는 첫 화면 fetch 에만 · 허브 fetch 에는 0 · 둘 다 3초 제한', async () => {
    const { calls } = await run(`?sgg=${SGG}`, okHub, { headers: { cookie: '_vercel_jwt=abc' } });
    const home = calls.find((c) => c.url.endsWith('/index.html'));
    const hub = calls.find((c) => c.url.includes('/hub/'));
    expect(new Headers(home?.init?.headers).get('cookie')).toBe('_vercel_jwt=abc');
    expect(new Headers(hub?.init?.headers).get('cookie')).toBeNull();
    expect(hub?.init?.signal).toBeInstanceOf(AbortSignal);
    expect(home?.init?.signal).toBeInstanceOf(AbortSignal);
    expect(FETCH_TIMEOUT_MS).toBe(3000);
  });

  it('두 fetch 는 함께 보낸다(허브가 첫 화면을 기다리지 않는다)', async () => {
    const order: string[] = [];
    let releaseHome: (r: Response) => void = () => {};
    const home = () => {
      order.push('home');
      return new Promise<Response>((r) => (releaseHome = r));
    };
    const hub = () => {
      order.push('hub');
      return new Response(JSON.stringify(HUB));
    };
    const f = fakeFetch(hub, home);
    const p = handleHub(req(`?sgg=${SGG}`), { fetch: f.fn, env: {} });
    await new Promise((r) => setTimeout(r, 0));
    expect(order.sort()).toEqual(['home', 'hub']);
    releaseHome(new Response(HOME));
    expect((await p).status).toBe(200);
  });

  it('사람·봇 같은 HTML — User-Agent 로 가르지 않는다', async () => {
    const a = await run(`?sgg=${SGG}`, okHub, { headers: { 'user-agent': 'Googlebot/2.1' } });
    const b = await run(`?sgg=${SGG}`, okHub, { headers: { 'user-agent': 'Mozilla/5.0 (iPhone)' } });
    expect(a.body).toBe(b.body);
  });

  it('api/hub.ts 는 이 본체를 .js 확장자로 부른다', () => {
    const src = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../api/hub.ts'), 'utf-8');
    expect(src).toContain("from '../src/lib/hubHandler.js'");
    expect(src).toContain('handleHub(request, { fetch: globalThis.fetch, env: process.env })');
  });
});
