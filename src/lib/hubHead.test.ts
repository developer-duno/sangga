import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { SITE_NAME, SITE_ORIGIN, renderBuildingHtml, type BuildingRow, type ParcelSibling } from './buildingHead';
import {
  hubBuildingName,
  hubCanonical,
  hubEntries,
  hubLine,
  hubPlace,
  isHubData,
  renderHubHtml,
  type HubBuilding,
  type HubData,
} from './hubHead';
import { SIDOS } from './regions';

/*
  구 입구 허브 첫 HTML(결정 0043) — 실제 `index.html` 을 그대로 읽어 치환한다.
*/

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '../..');
// ⚠️ jsdom 환경에서 `new URL(상대, import.meta.url)` 은 http://localhost 로 풀린다(실측) → 경로로 계산.
const HOME = readFileSync(resolve(ROOT, 'index.html'), 'utf-8');

const SGG = '11680';
const P1 = '1168010100100010000';
const P2 = '1168010100100020000';
const P3 = '1168010100100030000';

function b(id: string, pnu: string, nm: string | null, road: string | null, cnt = 1): HubBuilding {
  return { bld_id: `${pnu}_${id}`, pnu, bld_nm: nm, road_addr: road, bld_cnt: cnt };
}

/** 고정물 — 차례를 섞어 넣는다. P1 = 이름 같은 3동(동명칭 둘은 하나뿐 · 하나는 비었음) · P3 = 동명칭 겹침. */
function data(over: Partial<HubData> = {}): HubData {
  const parcels: Record<string, ParcelSibling[]> = {
    [P1]: [
      { bld_id: `${P1}_2`, bld_nm: '롯데 상가', dong_nm: 'B동' },
      { bld_id: `${P1}_1`, bld_nm: '롯데 상가', dong_nm: 'A동' },
      { bld_id: `${P1}_3`, bld_nm: '롯데 상가', dong_nm: null },
    ],
    [P3]: [
      { bld_id: `${P3}_1`, bld_nm: '쌍둥이', dong_nm: '본동' },
      { bld_id: `${P3}_2`, bld_nm: '쌍둥이', dong_nm: '본동' },
    ],
  };
  return {
    sgg: SGG,
    sido_code: '11',
    sigungu_nm: '강남구',
    buildings: [
      b('9', P2, '다빈치 <타워> & "몰"', '서울특별시 강남구 테헤란로 9'),
      b('1', P1, '롯데 상가', '서울특별시 강남구 올림픽로 240', 4),
      b('2', P1, '롯데 상가', '서울특별시 강남구 올림픽로 240', 4),
      b('3', P1, '롯데 상가', '서울특별시 강남구 올림픽로 240', 4),
      b('1', P3, '쌍둥이', null, 2),
      b('2', P3, '쌍둥이', null, 2),
      b('8', P2, '가나 빌딩', '서울특별시 강남구 테헤란로 9'),
    ],
    parcels,
    ...over,
  };
}

const doc = (html: string) => new DOMParser().parseFromString(html, 'text/html');
const count = (html: string, s: string) => html.split(s).length - 1;

describe('hubPlace · 이름 · 한 줄 · 차례', () => {
  it('곳 이름 = SIDOS 짧은 이름표 + 구 이름 · 같은 이름 구도 시 이름으로 갈린다', () => {
    expect(hubPlace({ sido_code: '11', sigungu_nm: '중구' })).toBe(`${SIDOS.find((s) => s.code === '11')?.name} 중구`);
    expect(hubPlace({ sido_code: '30', sigungu_nm: '중구' })).toBe(`${SIDOS.find((s) => s.code === '30')?.name} 중구`);
    expect(hubPlace({ sido_code: '11', sigungu_nm: '중구' })).not.toBe(hubPlace({ sido_code: '30', sigungu_nm: '중구' }));
    expect(hubPlace({ sido_code: '99', sigungu_nm: '중구' })).toBeNull();
    expect(hubPlace({ sido_code: '11', sigungu_nm: '  ' })).toBeNull();
  });

  it('한 줄 = 이름 · 짧은 도로명(시·도 낱말 뗌) · 도로명이 없으면 이름만', () => {
    const d = data();
    expect(hubLine(d.buildings[6], d.parcels)).toBe('가나 빌딩 · 강남구 테헤란로 9');
    expect(hubLine(d.buildings[4], d.parcels)).toBe('쌍둥이 (같은 땅 2동 중 1번째)');
  });

  it('같은 땅 여러 동 — dongSuffix 그대로(하나뿐인 동명칭 · 빈 동명칭은 차례 · 동 수는 bld_cnt)', () => {
    const d = data();
    expect(hubBuildingName(d.buildings[1], d.parcels)).toBe('롯데 상가 A동');
    expect(hubBuildingName(d.buildings[2], d.parcels)).toBe('롯데 상가 B동');
    expect(hubBuildingName(d.buildings[3], d.parcels)).toBe('롯데 상가 (같은 땅 4동 중 3번째)');
    // 동이 하나뿐인 땅이면 목록이 있어도 붙이지 않는다(서버 조각도 bld_cnt_in_pnu > 1 일 때만 부른다).
    expect(hubBuildingName({ ...d.buildings[1], bld_cnt: 1 }, d.parcels)).toBe('롯데 상가');
    // 동 목록이 없으면(함수가 0줄) 구분 없이.
    expect(hubBuildingName(d.buildings[1], {})).toBe('롯데 상가');
  });

  it('한글 먼저(가나다) → 영문(대소문자 섞어 ABC) → 숫자 → 기호 · 같으면 bld_id — 넣은 차례와 무관', () => {
    const names = ['---------', 'Zeta', '(주)세곡드림시티', 'abc빌딩', '1', 'ASTY 논현', '효성빌딩', '가나빌딩'];
    const mixed: HubData = { ...data(), buildings: names.map((n, i) => b(String(i + 1), P2, n, null)), parcels: {} };
    // ⓘ 무리 안은 Intl.Collator('ko') 그대로 — 영문 abc… 가 AS… 보다 앞(대소문자 섞어 ABC) · 기호끼리는 '-' 가 '(' 보다 앞.
    const want = ['가나빌딩', '효성빌딩', 'abc빌딩', 'ASTY 논현', 'Zeta', '1', '---------', '(주)세곡드림시티'];
    expect(hubEntries(mixed).map((e) => e.text)).toEqual(want);
    // 양성 대조 — 옛 차례(글자 부호 그대로)라면 영문 대문자가 소문자보다 앞(「Zeta 다음 abc」)이고 한글이 맨 뒤다.
    const codeUnit = [...names].sort((x, y) => (x < y ? -1 : x > y ? 1 : 0));
    expect(codeUnit.indexOf('Zeta')).toBeLessThan(codeUnit.indexOf('abc빌딩'));
    expect(codeUnit).not.toEqual(want);
    const d = data();
    const texts = hubEntries(d).map((e) => e.text);
    expect(texts[0]).toBe('가나 빌딩 · 강남구 테헤란로 9');
    const rev = hubEntries({ ...d, buildings: [...d.buildings].reverse() });
    expect(rev).toEqual(hubEntries(d));
    // 글자가 같으면 bld_id 차례
    const same = hubEntries({ ...d, buildings: [b('7', P2, '같은 이름', null), b('5', P2, '같은 이름', null)], parcels: {} });
    expect(same.map((e) => e.bldId)).toEqual([`${P2}_5`, `${P2}_7`]);
  });

  it('주소 꼴 = 사이트맵 building_loc 과 같은 꼴(?sgg=<pnu 앞 5자리>&bld=<id>)', () => {
    for (const e of hubEntries(data())) {
      expect(`${SITE_ORIGIN}${e.href}`).toBe(`${SITE_ORIGIN}/?sgg=${e.bldId.slice(0, 5)}&bld=${e.bldId}`);
    }
    expect(hubCanonical(SGG)).toBe('https://sangga-one.vercel.app/?sgg=11680');
  });
});

/** 건물 쪽 첫 HTML 의 h1 글자(같은 재료로 renderBuildingHtml). */
function buildingH1(h: HubBuilding, parcels: HubData['parcels']): string {
  const rows: BuildingRow[] = [
    {
      bld_id: h.bld_id,
      pnu: h.pnu,
      floor_no: 1,
      floor_label: null,
      segment_cnt: 1,
      main_use: '판매시설',
      uses: [{ use: '판매시설' }],
      bld_nm: h.bld_nm,
      road_addr: h.road_addr,
      bld_cnt_in_pnu: h.bld_cnt,
    },
  ];
  // 서버 조각과 같은 조건 — 같은 땅 2동 이상 + 이름 있음이면 동 목록(= 그 땅의 함수 결과 · 0줄이면 빈 배열).
  const wants = h.bld_cnt > 1 && typeof h.bld_nm === 'string' && h.bld_nm.trim() !== '';
  const page = renderBuildingHtml(HOME, rows, wants ? (parcels[h.pnu] ?? []) : null);
  return doc(page as string).querySelector('h1.seo-title')?.textContent ?? '';
}

describe('H10 짝 시험 — 허브 줄의 이름 = 그 건물 첫 HTML 의 h1', () => {
  it('고정물 건물 전부(한 동 · 하나뿐인 동명칭 · 빈 동명칭 · 겹친 동명칭 · 이스케이프 · 앞뒤 공백)', () => {
    const d = data();
    const extra = [b('4', P2, '  공백 이름  ', '서울특별시 강남구 가길 4'), b('4', P1, '롯데 상가 B동', null, 4)];
    const all = [...d.buildings, ...extra];
    for (const h of all) {
      expect(hubBuildingName(h, d.parcels), h.bld_id).toBe(buildingH1(h, d.parcels));
    }
    // 허브 HTML 의 링크 글자도 같은 이름으로 시작한다.
    const page = doc(renderHubHtml(HOME, { ...d, buildings: all }));
    const anchors = [...page.querySelectorAll('nav.seo-links li a')];
    expect(anchors.length).toBe(all.length);
    for (const a of anchors) {
      const id = new URLSearchParams((a.getAttribute('href') ?? '').slice(1)).get('bld') as string;
      const h = all.find((x) => x.bld_id === id) as HubBuilding;
      const text = a.textContent ?? '';
      expect(text === buildingH1(h, d.parcels) || text.startsWith(`${buildingH1(h, d.parcels)} · `), text).toBe(true);
    }
  });

  it('양성 대조 — 동 구분을 뺀 이름은 h1 과 다르다(짝 시험이 그 빠짐을 잡는다)', () => {
    const d = data();
    const h = d.buildings[1];
    expect(h.bld_nm).not.toBe(buildingH1(h, d.parcels));
  });
});

describe('renderHubHtml — 실제 index.html', () => {
  const d = data();
  const html = renderHubHtml(HOME, d);
  const page = doc(html);
  const place = hubPlace(d) as string;

  it('제목 · h1 · 소개문 · 설명 · og · twitter · canonical', () => {
    expect(place).toBe('서울 강남구');
    const title = `${place} 상가 건물 층별 보기 — ${SITE_NAME}`;
    const intro = `${place}에서 층별 화면을 볼 수 있는 상가 건물 ${d.buildings.length}곳입니다.`;
    expect(page.title).toBe(title);
    expect(page.querySelector('h1.seo-title')?.textContent).toBe(`${place} 상가 건물 층별 보기`);
    expect(page.querySelector('p.seo-intro')?.textContent).toBe(intro);
    const meta = (sel: string) => page.querySelector(sel)?.getAttribute('content');
    expect(meta('meta[name="description"]')).toBe(intro);
    expect(meta('meta[property="og:description"]')).toBe(intro);
    expect(meta('meta[name="twitter:description"]')).toBe(intro);
    expect(meta('meta[property="og:title"]')).toBe(title);
    expect(meta('meta[name="twitter:title"]')).toBe(title);
    expect(meta('meta[property="og:url"]')).toBe('https://sangga-one.vercel.app/?sgg=11680');
    expect(page.querySelector('link[rel="canonical"]')?.getAttribute('href')).toBe('https://sangga-one.vercel.app/?sgg=11680');
  });

  it('대전 중구는 서울 중구와 다른 제목', () => {
    const dj = renderHubHtml(HOME, { ...d, sgg: '30140', sido_code: '30', sigungu_nm: '중구', buildings: [b('1', '3014010100100010000', '가', null)], parcels: {} });
    const se = renderHubHtml(HOME, { ...d, sigungu_nm: '중구' });
    expect(doc(dj).title).toBe(`대전 중구 상가 건물 층별 보기 — ${SITE_NAME}`);
    expect(doc(dj).title).not.toBe(doc(se).title);
  });

  it('머리글 태그마다 정확히 1번 · JSON-LD 2덩어리(본 + 빵부스러기) · 빈 자리 주석은 사라짐', () => {
    for (const tag of [
      '<title>',
      '<meta name="description"',
      '<link rel="canonical"',
      '<meta property="og:title"',
      '<meta property="og:description"',
      '<meta property="og:url"',
      '<meta name="twitter:title"',
      '<meta name="twitter:description"',
      '<h1 class="seo-title">',
      '<p class="seo-intro">',
      '<nav class="seo-links"',
    ]) {
      expect(count(html, tag), tag).toBe(1);
    }
    expect(count(html, '<script type="application/ld+json">')).toBe(2);
    expect(html).not.toContain('<!--seo-breadcrumb-->');
    expect(html).not.toContain('noindex');
  });

  it('JSON-LD = 첫 화면 것에서 이름·설명·주소만 허브 값(나머지 칸·종류는 그대로) · 빵부스러기 = 첫 화면 → 곳', () => {
    const blocks = [...page.querySelectorAll('script[type="application/ld+json"]')].map((s) => JSON.parse(s.textContent ?? ''));
    const homeLd = JSON.parse(doc(HOME).querySelector('script[type="application/ld+json"]')?.textContent ?? '');
    const main = blocks[0];
    expect(main.name).toBe(page.title);
    expect(main.url).toBe('https://sangga-one.vercel.app/?sgg=11680');
    expect(main.description).toBe(page.querySelector('p.seo-intro')?.textContent);
    expect({ ...main, name: homeLd.name, url: homeLd.url, description: homeLd.description }).toEqual(homeLd);
    expect(blocks[1]).toEqual({
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: SITE_NAME, item: `${SITE_ORIGIN}/` },
        { '@type': 'ListItem', position: 2, name: '서울 강남구', item: 'https://sangga-one.vercel.app/?sgg=11680' },
      ],
    });
  });

  it('nav.seo-links = 건물 링크 전부(가나다) + 「첫 화면」 / · 이스케이프(&amp;·&lt;·&quot;)', () => {
    const anchors = [...page.querySelectorAll('nav.seo-links a')];
    expect(anchors.length).toBe(d.buildings.length + 1);
    const last = anchors[anchors.length - 1];
    expect([last.getAttribute('href'), last.textContent]).toEqual(['/', '첫 화면']);
    const items = anchors.slice(0, -1);
    expect(items.map((a) => a.textContent)).toEqual(hubEntries(d).map((e) => e.text));
    expect(items.map((a) => a.getAttribute('href'))).toEqual(hubEntries(d).map((e) => e.href));
    expect(html).toContain('href="/?sgg=11680&amp;bld=');
    expect(html).toContain('다빈치 &lt;타워&gt; &amp; &quot;몰&quot;');
    expect(html).not.toContain('다빈치 <타워>');
  });

  it('구 이름에 </script> 가 끼어도 JSON-LD 덩어리를 빠져나가지 못한다(< 를 \\u003c 로)', () => {
    const evil = '</script><script>x</script>';
    const out = renderHubHtml(HOME, { ...d, sigungu_nm: evil });
    // 바꾼 뒤 </script> 수 = 첫 화면 수 + 1(빵부스러기 덩어리 하나만 늘었다 — 이름 속 것은 글로 남는다).
    expect(count(out, '</script>')).toBe(count(HOME, '</script>') + 1);
    const blocks = [...doc(out).querySelectorAll('script[type="application/ld+json"]')];
    expect(blocks.length).toBe(2);
    for (const s of blocks) expect(() => JSON.parse(s.textContent ?? '')).not.toThrow();
    expect(JSON.parse(blocks[1].textContent ?? '').itemListElement[1].name).toBe(`서울 ${evil}`);
  });

  it('치환 글자의 $& · $1 이 특수 패턴으로 안 읽힌다(함수 치환)', () => {
    const odd = renderHubHtml(HOME, { ...d, buildings: [b('1', P2, '$& $1 $`', null)], parcels: {} });
    expect(doc(odd).querySelector('nav.seo-links li a')?.textContent).toBe('$& $1 $`');
  });

  it('대상 칸 밖의 사실 0 — 허브 HTML 의 글은 곳 이름·건물 수·건물 이름·짧은 도로명·정한 틀뿐', () => {
    const nav = page.querySelector('nav.seo-links')?.textContent ?? '';
    // 고정물에 없는 숫자(면적·가격 등)가 끼지 않았다 — 숫자는 도로명 번지와 동 차례뿐.
    const nums = nav.match(/\d+/g) ?? [];
    expect(new Set(nums)).toEqual(new Set(['9', '240', '4', '1', '3', '2']));
  });
});

/* ── H12 가드 — 금지어 · 판단 낱말 · 코드 속 지역 이름 ─────────────────────── */

const BANNED = ['적정가격', '적정가', '감정가', '평가액', '가치평가'];
const JUDGMENT = ['추천', '유망', '저평가', '고평가', '최고', '최적', '투자가치', '좋은'];

/** 글에서 금지어·판단 낱말을 찾는다(가드 본체와 양성 대조가 같은 함수를 지난다). 못 보는 것: 띄어 쓴 꼴(「적정 가격」). */
function bannedIn(text: string): string[] {
  return [...BANNED, ...JUDGMENT].filter((w) => text.includes(w));
}

/** 소스에서 지역 이름(SIDOS 의 짧은 이름·공식 이름)을 찾는다. 못 보는 것: 구 이름(「강남구」) — 구 이름은 표가 없다. */
function regionWordsIn(src: string): string[] {
  return SIDOS.flatMap((s) => [s.name, s.fullName]).filter((w) => src.includes(w));
}

describe('H12 가드', () => {
  it('허브 HTML 의 바꾼 자리에 금지어·판단 낱말 0', () => {
    const page = doc(renderHubHtml(HOME, data()));
    const changed = [
      page.title,
      page.querySelector('meta[name="description"]')?.getAttribute('content') ?? '',
      page.querySelector('h1.seo-title')?.textContent ?? '',
      page.querySelector('nav.seo-links')?.textContent ?? '',
      ...[...page.querySelectorAll('script[type="application/ld+json"]')].map((s) => s.textContent ?? ''),
    ].join(' ');
    expect(bannedIn(changed)).toEqual([]);
  });

  it('양성 대조 — 재료에 금지어·판단 낱말이 끼면 같은 함수가 잡는다(흔한 꼴 + 다른 낱말)', () => {
    const page = renderHubHtml(HOME, { ...data(), sigungu_nm: '추천구', buildings: [b('1', P2, '감정가 빌딩', null)], parcels: {} });
    expect(bannedIn(page)).toEqual(expect.arrayContaining(['감정가', '추천']));
  });

  it('허브 코드(TS·파이썬)에 지역 이름을 박지 않는다', () => {
    for (const f of ['src/lib/hubHead.ts', 'src/lib/hubHandler.ts', 'api/hub.ts', 'src/lib/buildingRoute.ts', 'scripts/build_sitemap.py']) {
      expect(regionWordsIn(readFileSync(resolve(ROOT, f), 'utf-8')), f).toEqual([]);
    }
  });

  it('양성 대조 — 지역 이름이 든 소스는 잡힌다(짧은 이름 · 공식 이름)', () => {
    expect(regionWordsIn("const X = '서울 강남구';")).toContain('서울');
    expect(regionWordsIn('// 대전광역시')).toEqual(expect.arrayContaining(['대전', '대전광역시']));
  });
});

describe('치환 가드 — 정확히 1번(0개·2개면 throw)', () => {
  const d = data();
  it.each([
    ['<title> 0개', HOME.replace(/<title>[^<]*<\/title>/, '')],
    ['<title> 2개', HOME.replace('</head>', '<title>x</title></head>')],
    ['h1 0개', HOME.replace(/<h1 class="seo-title">[^<]*<\/h1>/, '')],
    ['nav 2개', HOME.replace('</body>', '<nav class="seo-links"></nav></body>')],
    ['빵부스러기 자리 0개', HOME.replace('<!--seo-breadcrumb-->', '')],
    ['JSON-LD 2개', HOME.replace('</head>', '<script type="application/ld+json">{}</script></head>')],
    ['JSON-LD 가 JSON 아님', HOME.replace(/(<script type="application\/ld\+json">)[\s\S]*?(<\/script>)/, '$1{x$2')],
  ])('%s', (_name, home) => {
    expect(() => renderHubHtml(home, d)).toThrow();
  });

  it('양성 대조 — 같은 고정물이 원래 index.html 로는 throw 하지 않는다', () => {
    expect(() => renderHubHtml(HOME, d)).not.toThrow();
  });

  it('시·도 코드가 표에 없으면 throw(지어내지 않는다)', () => {
    expect(() => renderHubHtml(HOME, { ...d, sido_code: '99' })).toThrow();
  });
});

describe('isHubData — 모양 확인', () => {
  it('정상 고정물은 true', () => {
    expect(isHubData(data(), SGG)).toBe(true);
  });
  it.each([
    ['다른 구 파일', { ...data(), sgg: '30140' }],
    ['시·도 코드가 sgg 와 다름', { ...data(), sido_code: '30' }],
    ['구 이름 빔', { ...data(), sigungu_nm: ' ' }],
    ['건물 0동', { ...data(), buildings: [] }],
    ['건물 pnu 가 다른 구', { ...data(), buildings: [b('1', '3014010100100010000', '가', null)] }],
    ['bld_id 꼴 틀림', { ...data(), buildings: [{ ...b('1', P2, '가', null), bld_id: 'x' }] }],
    ['bld_cnt 0', { ...data(), buildings: [b('1', P2, '가', null, 0)] }],
    ['이름이 숫자', { ...data(), buildings: [{ ...b('1', P2, '가', null), bld_nm: 3 }] }],
    ['parcels 가 배열', { ...data(), parcels: [] }],
    ['동 줄 꼴 틀림', { ...data(), parcels: { [P1]: [{ bld_id: 'x', bld_nm: null, dong_nm: null }] } }],
  ])('%s → false', (_n, x) => {
    expect(isHubData(x, SGG)).toBe(false);
  });
});

/* ── 커밋된 허브 파일 ↔ 사이트맵(굽기 뒤 · H8) ─────────────────────────────── */

function sitemapLocs(): Set<string> {
  const out = new Set<string>();
  for (const f of readdirSync(resolve(ROOT, 'public')).filter((n) => /^sitemap-buildings-\d+\.xml$/.test(n))) {
    for (const m of readFileSync(resolve(ROOT, 'public', f), 'utf-8').matchAll(/<loc>([^<]*)<\/loc>/g)) {
      out.add(m[1].replace(/&amp;/g, '&'));
    }
  }
  return out;
}

describe('커밋된 public/hub/*.json — 실제 index.html 로 굽고 사이트맵 주소 집합과 대조', () => {
  it('허브 링크 주소 집합 = 건물 사이트맵 주소 집합(글자까지) · 파일마다 모양 맞음 · 치환 성공', () => {
    const dir = resolve(ROOT, 'public', 'hub');
    expect(existsSync(dir), 'public/hub 가 없다 — python scripts/build_sitemap.py 로 굽고 커밋').toBe(true);
    const files = readdirSync(dir).filter((n) => /^\d{5}\.json$/.test(n));
    expect(files.length).toBeGreaterThan(0);
    const hrefs = new Set<string>();
    for (const f of files) {
      const sgg = f.slice(0, 5);
      const x: unknown = JSON.parse(readFileSync(resolve(dir, f), 'utf-8'));
      expect(isHubData(x, sgg), f).toBe(true);
      const page = doc(renderHubHtml(HOME, x as HubData));
      const links = [...page.querySelectorAll('nav.seo-links li a')].map((a) => a.getAttribute('href') ?? '');
      expect(links.length, f).toBe((x as HubData).buildings.length);
      for (const h of links) hrefs.add(`${SITE_ORIGIN}${h}`);
    }
    expect(hrefs).toEqual(sitemapLocs());
  });
});
