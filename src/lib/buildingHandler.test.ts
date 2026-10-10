import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { withNoindex, type BuildingRow } from './buildingHead';
import {
  CACHE_BUILDING,
  CACHE_HOME,
  CACHE_NONE,
  CACHE_NOT_FOUND,
  FETCH_TIMEOUT_MS,
  RETRY_AFTER_S,
  handleBuilding,
  homeSource,
  type HandlerDeps,
} from './buildingHandler';

/*
  서버 조각 본체(결정 0037) — 가짜 fetch 로 ⓐ~ⓔ 를 하나씩. 외부 호출 0.
*/

// ⚠️ jsdom 환경에서 `new URL(상대, import.meta.url)` 은 http://localhost 로 풀린다(실측) → 경로로 계산.
const HOME = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../index.html'), 'utf-8');

const PNU = '1168010600109420015';
const BLD = `${PNU}_10241100257870`;
const ENV = { VITE_SUPABASE_URL: 'https://example.supabase.co/', VITE_SUPABASE_ANON_KEY: 'anon-test' };

function rows(name: string | null): BuildingRow[] {
  return [1, 2, -1].map((n) => ({
    bld_id: BLD,
    pnu: PNU,
    floor_no: n,
    floor_label: null,
    segment_cnt: 1,
    main_use: '업무시설',
    uses: [{ use: '업무시설' }],
    bld_nm: name,
    road_addr: '서울특별시 강남구 테헤란로 1',
  }));
}

type Call = { url: string; init?: RequestInit };

function fakeFetch(db: () => Response | Promise<Response>, home: () => Response = () => new Response(HOME)) {
  const calls: Call[] = [];
  const fn: HandlerDeps['fetch'] = async (url, init) => {
    calls.push({ url, init });
    if (url.endsWith('/index.html')) return home();
    return db();
  };
  return { fn, calls };
}

function req(query: string, headers: Record<string, string> = {}): Request {
  return new Request(`https://sangga-one.vercel.app/api/building${query}`, { headers });
}

async function run(query: string, db: () => Response | Promise<Response>, env: HandlerDeps['env'] = ENV) {
  const f = fakeFetch(db);
  const res = await handleBuilding(req(query), { fetch: f.fn, env });
  return { res, body: await res.text(), calls: f.calls };
}

function title(body: string): string {
  return new DOMParser().parseFromString(body, 'text/html').title;
}

const HOME_TITLE = title(HOME);

describe('handleBuilding', () => {
  it('ⓐ bld 가 없거나 꼴이 틀리면 첫 화면 그대로 · 하루 캐시 · DB 호출 0', async () => {
    for (const q of ['', '?sgg=11680', `?bld=${PNU}`, '?bld=abc']) {
      const { res, body, calls } = await run(q, () => new Response('[]'));
      expect(res.status, q).toBe(200);
      expect(res.headers.get('cache-control')).toBe(CACHE_HOME);
      expect(res.headers.get('content-type')).toBe('text/html; charset=utf-8');
      expect(body).toBe(HOME);
      expect(calls.filter((c) => c.url.includes('/rest/v1/'))).toEqual([]);
    }
  });

  it('ⓑ 환경변수가 없으면 503 + Retry-After + 첫 화면 · no-store · 오류 한 줄 · DB 호출 0', async () => {
    const err = console.error;
    const logged: unknown[][] = [];
    console.error = (...a: unknown[]) => void logged.push(a);
    try {
      for (const env of [{}, { VITE_SUPABASE_URL: ENV.VITE_SUPABASE_URL }, { VITE_SUPABASE_ANON_KEY: 'k' }]) {
        const { res, body, calls } = await run(`?sgg=11680&bld=${BLD}`, () => new Response('[]'), env);
        expect(res.status).toBe(503);
        expect(res.headers.get('retry-after')).toBe(RETRY_AFTER_S);
        expect(res.headers.get('cache-control')).toBe(CACHE_NONE);
        expect(body).toBe(HOME);
        expect(calls.filter((c) => c.url.includes('/rest/v1/'))).toEqual([]);
      }
    } finally {
      console.error = err;
    }
    expect(logged.length).toBe(3);
  });

  it('ⓑ Supabase 가 200 이 아니거나 · 네트워크 실패 · 배열 아님이면 503 + Retry-After + 첫 화면 · no-store', async () => {
    const fails: (() => Response | Promise<Response>)[] = [
      () => new Response('{"message":"x"}', { status: 500 }),
      () => new Response('[]', { status: 206 }),
      () => Promise.reject(new TypeError('network')),
      () => new Response('{"a":1}'),
      () => new Response('not json'),
    ];
    for (const db of fails) {
      const { res, body } = await run(`?bld=${BLD}`, db);
      expect(res.status).toBe(503);
      expect(res.headers.get('retry-after')).toBe(RETRY_AFTER_S);
      expect(res.headers.get('cache-control')).toBe(CACHE_NONE);
      expect(res.headers.get('content-type')).toBe('text/html; charset=utf-8');
      expect(body).toBe(HOME);
    }
  });

  it('ⓒ 행이 0 이면 404 + noindex 한 줄 · 10분 캐시', async () => {
    const { res, body } = await run(`?bld=${BLD}`, () => new Response('[]'));
    expect(res.status).toBe(404);
    expect(res.headers.get('cache-control')).toBe(CACHE_NOT_FOUND);
    expect(res.headers.get('content-type')).toBe('text/html; charset=utf-8');
    expect(body.split('<meta name="robots" content="noindex" />').length - 1).toBe(1);
    expect(body.indexOf('noindex')).toBeLessThan(body.indexOf('</head>'));
    expect(title(body)).toBe(HOME_TITLE);
    expect(body.replace(/\r?\n[ \t]*<meta name="robots" content="noindex" \/>/, '')).toBe(HOME);
  });

  it('noindex 줄은 LF·CRLF 어느 쪽 HTML 이든 그 줄바꿈을 따른다', () => {
    const lf = HOME.replace(/\r\n/g, '\n');
    const crlf = lf.replace(/\n/g, '\r\n');
    expect(withNoindex(lf)).toContain('\n    <meta name="robots" content="noindex" />\n  </head>');
    expect(withNoindex(lf)).not.toContain('\r');
    expect(withNoindex(crlf)).toContain('\r\n    <meta name="robots" content="noindex" />\r\n  </head>');
    expect(withNoindex('<head></head>')).toBe('<head><meta name="robots" content="noindex" /></head>');
  });

  it('ⓓ 이름이 없으면 첫 화면 그대로 · 하루 캐시', async () => {
    const { res, body } = await run(`?bld=${BLD}`, () => new Response(JSON.stringify(rows(null))));
    expect(res.status).toBe(200);
    expect(res.headers.get('cache-control')).toBe(CACHE_HOME);
    expect(body).toBe(HOME);
  });

  it('ⓔ 이름이 있으면 그 건물의 HTML · 하루 캐시 + stale-while-revalidate', async () => {
    const { res, body, calls } = await run(`?sgg=11680&bld=${BLD}`, () => new Response(JSON.stringify(rows('테헤란빌딩'))));
    expect(res.status).toBe(200);
    expect(res.headers.get('cache-control')).toBe(CACHE_BUILDING);
    expect(res.headers.get('content-type')).toBe('text/html; charset=utf-8');
    expect(title(body)).toBe('테헤란빌딩 — 강남구 테헤란로 1 | 상가 층별 스택뷰');
    expect(body).toContain(`?sgg=11680&amp;bld=${BLD}"`);

    // Supabase 요청 모양 — 화면과 같은 뷰 · api 스키마 · 공개키 · 시간 제한.
    const db = calls.find((c) => c.url.includes('/rest/v1/'))!;
    expect(db.url).toBe(
      'https://example.supabase.co/rest/v1/v_floor_stack' +
        `?bld_id=eq.${BLD}&select=bld_id,pnu,floor_no,floor_label,segment_cnt,main_use,uses,bld_nm,road_addr` +
        '&order=floor_no.asc.nullslast',
    );
    const h = db.init!.headers as Record<string, string>;
    expect(h).toEqual({ apikey: 'anon-test', Authorization: 'Bearer anon-test', 'Accept-Profile': 'api' });
    expect(db.init!.signal).toBeInstanceOf(AbortSignal);
    const home = calls.find((c) => c.url.endsWith('/index.html'))!;
    expect(home.url).toBe('https://sangga-one.vercel.app/index.html');
    expect(home.init!.signal).toBeInstanceOf(AbortSignal);
  });

  it('ⓔ 비주거 층이 없는 건물(아파트 동)은 건물 HTML + noindex 한 줄 · 같은 하루 캐시', async () => {
    const apt = rows('래미안').map((r) => ({ ...r, main_use: '아파트', uses: [{ use: '아파트' }] }));
    const { res, body } = await run(`?bld=${BLD}`, () => new Response(JSON.stringify(apt)));
    expect(res.status).toBe(200);
    expect(res.headers.get('cache-control')).toBe(CACHE_BUILDING);
    expect(title(body)).toBe('래미안 — 강남구 테헤란로 1 | 상가 층별 스택뷰');
    expect(body.split('<meta name="robots" content="noindex" />').length - 1).toBe(1);
  });

  it('사람·봇 같은 HTML — User-Agent 로 가르지 않는다', async () => {
    const f1 = fakeFetch(() => new Response(JSON.stringify(rows('테헤란빌딩'))));
    const f2 = fakeFetch(() => new Response(JSON.stringify(rows('테헤란빌딩'))));
    const a = await handleBuilding(req(`?bld=${BLD}`, { 'user-agent': 'Mozilla/5.0' }), { fetch: f1.fn, env: ENV });
    const b = await handleBuilding(req(`?bld=${BLD}`, { 'user-agent': 'Googlebot/2.1' }), { fetch: f2.fn, env: ENV });
    expect(await a.text()).toBe(await b.text());
  });

  it('ⓕ 첫 화면 HTML 이 200 이 아니거나 실패하면 307 /index.html?<원래 query> · no-store', async () => {
    const homes: (() => Response)[] = [
      () => new Response('x', { status: 401 }),
      () => new Response('x', { status: 404 }),
      () => {
        throw new TypeError('network');
      },
    ];
    for (const home of homes) {
      const f = fakeFetch(() => new Response(JSON.stringify(rows('테헤란빌딩'))), home);
      const res = await handleBuilding(req(`?sgg=11680&bld=${BLD}`), { fetch: f.fn, env: ENV });
      expect(res.status).toBe(307);
      expect(res.headers.get('location')).toBe(`/index.html?sgg=11680&bld=${BLD}`);
      expect(res.headers.get('cache-control')).toBe(CACHE_NONE);
    }
  });

  it('cookie 는 첫 화면 HTML fetch 에만 넘긴다(Supabase 로는 안 간다)', async () => {
    const f = fakeFetch(() => new Response(JSON.stringify(rows('테헤란빌딩'))));
    await handleBuilding(req(`?bld=${BLD}`, { cookie: '_vercel_jwt=abc' }), { fetch: f.fn, env: ENV });
    const home = f.calls.find((c) => c.url.endsWith('/index.html'))!;
    const db = f.calls.find((c) => c.url.includes('/rest/v1/'))!;
    expect(home.init!.headers).toEqual({ cookie: '_vercel_jwt=abc' });
    expect(JSON.stringify(db.init!.headers)).not.toContain('_vercel_jwt');
    // cookie 가 없으면 빈 머리
    const g = fakeFetch(() => new Response(JSON.stringify(rows('테헤란빌딩'))));
    await handleBuilding(req(`?bld=${BLD}`), { fetch: g.fn, env: ENV });
    expect(g.calls.find((c) => c.url.endsWith('/index.html'))!.init!.headers).toEqual({});
  });

  it('두 fetch 는 함께 나간다 — 하나가 끝나기 전에 둘 다 불린다 · 시간 제한 3초', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const calls: string[] = [];
    const fn: HandlerDeps['fetch'] = async (url) => {
      calls.push(url);
      await gate;
      return url.endsWith('/index.html') ? new Response(HOME) : new Response(JSON.stringify(rows('테헤란빌딩')));
    };
    const p = handleBuilding(req(`?bld=${BLD}`), { fetch: fn, env: ENV });
    await Promise.resolve();
    expect(calls.length).toBe(2);
    release();
    expect((await p).status).toBe(200);
    expect(FETCH_TIMEOUT_MS).toBe(3000);
  });

  it('/api/building?bld=… 를 직접 불러도 같은 결과(rewrite 를 안 거쳐도)', async () => {
    const via = async (u: string) => {
      const f = fakeFetch(() => new Response(JSON.stringify(rows('테헤란빌딩'))));
      const res = await handleBuilding(new Request(u), { fetch: f.fn, env: ENV });
      return [res.status, res.headers.get('cache-control'), await res.text()];
    };
    expect(await via(`https://sangga-one.vercel.app/api/building?bld=${BLD}`)).toEqual(
      await via(`https://sangga-one.vercel.app/?sgg=11680&bld=${BLD}`),
    );
  });

  it('첫 화면 HTML 모양이 바뀌어 치환 가드에 걸리면 첫 화면 · no-store', async () => {
    const broken = HOME.replace('</head>', '<title>둘째</title></head>');
    const f = fakeFetch(() => new Response(JSON.stringify(rows('테헤란빌딩'))), () => new Response(broken));
    const err = console.error;
    console.error = () => {};
    try {
      const res = await handleBuilding(req(`?bld=${BLD}`), { fetch: f.fn, env: ENV });
      expect(res.status).toBe(200);
      expect(res.headers.get('cache-control')).toBe(CACHE_NONE);
      expect(await res.text()).toBe(broken);
    } finally {
      console.error = err;
    }
  });
});

describe('허용 호스트 — 남의 호스트로 cookie 를 실어 요청하지 않는다(적대 검사 🔴 2026-10-09)', () => {
  const PREVIEW = { ...ENV, VERCEL_URL: 'sangga-abc123.vercel.app', VERCEL_BRANCH_URL: 'sangga-git-feat-x.vercel.app' };

  async function homeCall(headers: Record<string, string>, env: HandlerDeps['env'] = ENV, url = `https://sangga-one.vercel.app/api/building?bld=${BLD}`) {
    const f = fakeFetch(() => new Response(JSON.stringify(rows('테헤란빌딩'))));
    await handleBuilding(new Request(url, { headers }), { fetch: f.fn, env });
    return f.calls.find((c) => c.url.endsWith('/index.html'))!;
  }

  it('남의 호스트(x-forwarded-host) → 정식 주소로 요청 · cookie 헤더 없음', async () => {
    for (const host of ['evil.example.com', '169.254.169.254', 'localhost:6379', 'sangga-one.vercel.app.evil.com', 'SANGGA-ONE.vercel.app']) {
      const call = await homeCall({ 'x-forwarded-host': host, 'x-forwarded-proto': 'http', cookie: '_vercel_jwt=SECRET' }, PREVIEW);
      expect(call.url, host).toBe('https://sangga-one.vercel.app/index.html');
      expect(call.init!.headers, host).toEqual({});
    }
  });

  it('요청 주소의 host 가 남의 것이어도 같다(헤더가 없을 때)', async () => {
    const call = await homeCall({ cookie: 'a=1' }, ENV, `https://evil.example.com/api/building?bld=${BLD}`);
    expect(call.url).toBe('https://sangga-one.vercel.app/index.html');
    expect(call.init!.headers).toEqual({});
  });

  it('허용 호스트(정식 · VERCEL_URL · VERCEL_BRANCH_URL) → 그 배포에서 · cookie 전달 · 늘 https', async () => {
    for (const host of ['sangga-one.vercel.app', PREVIEW.VERCEL_URL, PREVIEW.VERCEL_BRANCH_URL]) {
      const call = await homeCall({ 'x-forwarded-host': host, 'x-forwarded-proto': 'http', cookie: '_vercel_jwt=abc' }, PREVIEW);
      expect(call.url, host).toBe(`https://${host}/index.html`);
      expect(call.init!.headers, host).toEqual({ cookie: '_vercel_jwt=abc' });
    }
  });

  it('VERCEL_URL 이 함수 환경에 없으면 미리보기 호스트도 남의 것으로 친다', async () => {
    const call = await homeCall({ 'x-forwarded-host': 'sangga-abc123.vercel.app', cookie: 'a=1' }, ENV);
    expect(call.url).toBe('https://sangga-one.vercel.app/index.html');
    expect(call.init!.headers).toEqual({});
  });

  it('homeSource — 여러 값이면 첫 값만 · 허용 여부를 함께 준다', () => {
    const r = (h: Record<string, string>) => new Request('https://sangga-one.vercel.app/', { headers: h });
    expect(homeSource(r({ 'x-forwarded-host': 'sangga-one.vercel.app, evil.com' }), ENV)).toEqual({ origin: 'https://sangga-one.vercel.app', trusted: true });
    expect(homeSource(r({ 'x-forwarded-host': 'evil.com, sangga-one.vercel.app' }), ENV)).toEqual({ origin: 'https://sangga-one.vercel.app', trusted: false });
    expect(homeSource(r({}), ENV)).toEqual({ origin: 'https://sangga-one.vercel.app', trusted: true });
  });
});
