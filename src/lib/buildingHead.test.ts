import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  buildingFacts,
  isBldId,
  isNonResidential,
  MAX_INTRO_FLOORS,
  RESIDENTIAL_RE,
  renderBuildingHtml,
  SITE_NAME,
  SITE_ORIGIN,
  topicJosa,
  type BuildingRow,
} from './buildingHead';
import { buildingFromFloorRows } from './restoreBuilding';
import { SITE_NAME as SEO_SITE_NAME } from './seo';
import type { FloorRow } from '../types';

/*
  건물 주소의 첫 HTML(결정 0037) — 실제 `index.html` 을 그대로 읽어 치환한다.
  ⛔ 태그 개수는 글자 세기가 아니라 DOM 파서(jsdom)로 센다 — 봇이 읽는 방식과 같게.
*/

// ⚠️ `new URL('../../index.html', import.meta.url)` 은 jsdom 환경에서 http://localhost:3000/… 로 풀린다(실측) → 경로로 계산.
const HOME = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../index.html'), 'utf-8');

// 절대 규칙 2 금지어 — 정본은 tests/test_seo_head.py 의 BANNED_TERMS(같은 다섯 낱말).
const BANNED = ['적정가격', '적정가', '평가액', '감정가', '가치평가'];

const PNU = '1168010600109420015';
const BLD = `${PNU}_10241100257870`;

function row(floor_no: number | null, extra: Partial<BuildingRow> = {}): BuildingRow {
  return {
    bld_id: BLD,
    pnu: PNU,
    floor_no,
    floor_label: null,
    segment_cnt: 2,
    main_use: '제1종근린생활시설',
    uses: null,
    bld_nm: '디아이타워',
    road_addr: '서울특별시 강남구 테헤란로 123',
    ...extra,
  };
}

/** 지하 3 · 지상 1~12 · 옥탑 = 16층. */
function tower(extra: Partial<BuildingRow> = {}): BuildingRow[] {
  const floors = [99, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, -1, -2, -3];
  return floors.map((n) => row(n, extra));
}

function parse(html: string): Document {
  return new DOMParser().parseFromString(html, 'text/html');
}

function meta(doc: Document, sel: string): string[] {
  return Array.from(doc.querySelectorAll(sel)).map((el) => el.getAttribute('content') ?? el.getAttribute('href') ?? '');
}

function render(rows: BuildingRow[]): string {
  const html = renderBuildingHtml(HOME, rows);
  if (html === null) throw new Error('null');
  return html;
}

describe('isBldId', () => {
  it('urlState 의 BLD_RE 와 같은 꼴만 받는다', () => {
    expect(isBldId(BLD)).toBe(true);
    expect(isBldId(`${PNU}_1`)).toBe(true);
    expect(isBldId(PNU)).toBe(false);
    expect(isBldId(`${PNU}_`)).toBe(false);
    expect(isBldId(`${PNU}_${'1'.repeat(33)}`)).toBe(false);
    expect(isBldId(`x${BLD}`)).toBe(false);
    expect(isBldId(null)).toBe(false);
    expect(isBldId('')).toBe(false);
  });
});

describe('buildingFacts', () => {
  it('지상 최고층 · 지하 깊이 · 구간 합 · 옥탑은 층 범위에서 뺀다', () => {
    const f = buildingFacts(tower())!;
    expect(f.above).toBe(12);
    expect(f.below).toBe(3);
    expect(f.segments).toBe(32);
    expect(f.floors.map((x) => x.floorNo)).toEqual([-3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 99]);
  });

  it('층 불명(null)은 맨 뒤 · 구간이 빈 층은 0 으로 센다', () => {
    const f = buildingFacts([row(null), row(2, { segment_cnt: null }), row(1)])!;
    expect(f.floors.map((x) => x.floorNo)).toEqual([1, 2, null]);
    expect(f.floors[2].label).toBe('층 불명');
    expect(f.segments).toBe(4);
  });

  it('행이 없으면 null', () => {
    expect(buildingFacts([])).toBeNull();
  });

  it('층수 규칙이 restoreBuilding.ts(검색 서버와 같은 규칙)와 같다', () => {
    const cases: number[][] = [
      [99, 12, 1, -1, -3],
      [-5, -4, -1], // 지하만
      [3, 2, 1], // 지상만
      [99], // 옥탑만
      [2, 99, 7],
    ];
    for (const floors of cases) {
      const rs = floors.map((n) => row(n));
      // 층 규칙은 floor_no 만 본다 — 나머지 칸이 모자란 것은 이 대조와 무관하다.
      const hit = buildingFromFloorRows(rs as unknown as FloorRow[])!;
      const f = buildingFacts(rs)!;
      expect(f.above, String(floors)).toBe(hit.max_floor !== null && hit.max_floor > 0 ? hit.max_floor : 0);
      expect(f.below, String(floors)).toBe(hit.min_floor !== null && hit.min_floor < 0 ? -hit.min_floor : 0);
    }
  });
});

describe('topicJosa', () => {
  it('받침 있으면 은 · 없으면 는 · 한글 아니면 은(는)', () => {
    expect(topicJosa('디아이빌딩')).toBe('은');
    expect(topicJosa('디아이타워')).toBe('는');
    expect(topicJosa('KT')).toBe('은(는)');
    expect(topicJosa('타워2')).toBe('은(는)');
  });
});

describe('renderBuildingHtml — 실제 index.html', () => {
  const html = render(tower());
  const doc = parse(html);
  const canonical = `${SITE_ORIGIN}/?sgg=11680&bld=${BLD}`;
  const title = '디아이타워 — 강남구 테헤란로 123 | 상가 층별 스택뷰';

  it('바꾼 태그는 각각 정확히 1개', () => {
    for (const sel of [
      'title',
      'meta[name="description"]',
      'link[rel="canonical"]',
      'meta[property="og:title"]',
      'meta[property="og:description"]',
      'meta[property="og:url"]',
      'meta[name="twitter:title"]',
      'meta[name="twitter:description"]',
      'script[type="application/ld+json"]',
      'p.seo-intro',
    ]) {
      expect(doc.querySelectorAll(sel).length, sel).toBe(1);
    }
  });

  it('제목 · 설명 · 정식 주소가 그 건물 것', () => {
    expect(doc.title).toBe(title);
    expect(meta(doc, 'meta[property="og:title"]')).toEqual([title]);
    expect(meta(doc, 'meta[name="twitter:title"]')).toEqual([title]);
    const desc =
      '디아이타워(서울특별시 강남구 테헤란로 123)의 층별 용도·면적·점포를 건축물대장 층별개요로 쌓아 보여 줍니다. ' +
      '지상 12층·지하 3층, 층별개요 구간 32개. 실거래 기록, 둘레 업종 분포, 상권 임대 동향(공표값)까지 공공데이터로 봅니다. 무료 · 로그인 없음.';
    expect(meta(doc, 'meta[name="description"]')).toEqual([desc]);
    expect(meta(doc, 'meta[property="og:description"]')).toEqual([desc]);
    expect(meta(doc, 'meta[name="twitter:description"]')).toEqual([desc]);
    expect(meta(doc, 'link[rel="canonical"]')).toEqual([canonical]);
    expect(meta(doc, 'meta[property="og:url"]')).toEqual([canonical]);
  });

  it('HTML 속성 안의 & 는 &amp; 로 적힌다', () => {
    expect(html).toContain(`<link rel="canonical" href="${SITE_ORIGIN}/?sgg=11680&amp;bld=${BLD}"`);
    expect(html).toContain(`<meta property="og:url" content="${SITE_ORIGIN}/?sgg=11680&amp;bld=${BLD}"`);
    // JSON-LD 덩어리 안은 HTML 이 아니라 JSON 이라 맨 & 가 맞다 — 그 밖에서만 본다.
    const outsideLd = html.replace(/<script type="application\/ld\+json">[\s\S]*?<\/script>/, '');
    expect(outsideLd).not.toContain('?sgg=11680&bld=');
  });

  it('바꾸지 않는 태그(og:image·사이트 이름·소유 확인)는 첫 화면 그대로', () => {
    for (const sel of ['meta[property="og:image"]', 'meta[property="og:site_name"]', 'meta[name="google-site-verification"]']) {
      expect(meta(doc, sel)).toEqual(meta(parse(HOME), sel));
    }
  });

  it('JSON-LD 는 WebPage 한 덩어리 · 뷰에 있는 사실만 · 평점·가격 0', () => {
    const blocks = doc.querySelectorAll('script[type="application/ld+json"]');
    const ld = JSON.parse(blocks[0].textContent ?? '');
    expect(ld).toEqual({
      '@context': 'https://schema.org',
      '@type': 'WebPage',
      name: title,
      url: canonical,
      description: meta(doc, 'meta[name="description"]')[0],
      inLanguage: 'ko',
      isPartOf: { '@type': 'WebApplication', name: '상가 층별 스택뷰', url: `${SITE_ORIGIN}/` },
      about: {
        '@type': 'Place',
        name: '디아이타워',
        address: { '@type': 'PostalAddress', streetAddress: '서울특별시 강남구 테헤란로 123', addressCountry: 'KR' },
      },
    });
  });

  it(`소개문 — 조사 · 주소 · 층 목록 최대 ${MAX_INTRO_FLOORS}층 + 외 N층`, () => {
    const intro = doc.querySelector('p.seo-intro')!.textContent!;
    expect(intro.startsWith('디아이타워는 서울특별시 강남구 테헤란로 123에 있는 지상 12층·지하 3층 건물입니다. ')).toBe(true);
    expect(intro).toContain(
      '층별 구성: 지하3층 제1종근린생활시설(구간 2) · 지하2층 제1종근린생활시설(구간 2) · 지하1층 제1종근린생활시설(구간 2) · 1층 제1종근린생활시설(구간 2)',
    );
    expect(intro.endsWith('9층 제1종근린생활시설(구간 2) 외 4층.')).toBe(true);
    // 소개문은 #root 안에 그대로 있다(React 가 그리면 덮인다).
    expect(doc.querySelector('#root > p.seo-intro')).not.toBeNull();
  });

  it('금지어 0 — 제목·설명·소개문·JSON-LD', () => {
    const texts = [doc.title, ...meta(doc, 'meta[name="description"]'), doc.querySelector('p.seo-intro')!.textContent!, html];
    for (const t of texts) for (const w of BANNED) expect(t.includes(w), w).toBe(false);
  });
});

describe('renderBuildingHtml — 경계', () => {
  it('행 0 → null · 이름 null·빈칸 → null', () => {
    expect(renderBuildingHtml(HOME, [])).toBeNull();
    expect(renderBuildingHtml(HOME, tower({ bld_nm: null }))).toBeNull();
    expect(renderBuildingHtml(HOME, tower({ bld_nm: '   ' }))).toBeNull();
  });

  it('이름에 <script>·따옴표가 있어도 태그를 깨지 못한다', () => {
    const evil = `A"><script>alert('x')</script>&`;
    const html = render(tower({ bld_nm: evil }));
    const doc = parse(html);
    expect(html).not.toContain("<script>alert('x')");
    expect(html.toLowerCase().split('</script').length - 1).toBe(
      HOME.toLowerCase().split('</script').length - 1,
    );
    expect(doc.title.startsWith(evil)).toBe(true);
    expect(meta(doc, 'meta[name="description"]')[0].startsWith(`${evil}(`)).toBe(true);
    expect(doc.querySelector('p.seo-intro')!.textContent!.startsWith(`${evil}은(는) `)).toBe(true);
    const ld = JSON.parse(doc.querySelector('script[type="application/ld+json"]')!.textContent!);
    expect(ld.about.name).toBe(evil);
    expect(doc.querySelectorAll('script[type="application/ld+json"]').length).toBe(1);
  });

  it('이름 A$&B — 함수 치환이라 특수 패턴으로 안 읽힌다(모든 치환 자리)', () => {
    const html = render(tower({ bld_nm: 'A$&B' }));
    const doc = parse(html);
    expect(doc.title).toBe('A$&B — 강남구 테헤란로 123 | 상가 층별 스택뷰');
    expect(meta(doc, 'meta[property="og:title"]')).toEqual([doc.title]);
    expect(meta(doc, 'meta[name="description"]')[0].startsWith('A$&B(')).toBe(true);
    expect(doc.querySelector('p.seo-intro')!.textContent!.startsWith('A$&B은(는) ')).toBe(true);
    expect(JSON.parse(doc.querySelector('script[type="application/ld+json"]')!.textContent!).about.name).toBe('A$&B');
    // 문자열 치환이었다면 `$&` 가 '찾은 글자'(원래 태그)로 바뀌어 태그가 늘어난다.
    expect(doc.querySelectorAll('title').length).toBe(1);
  });

  it('치환 글자의 $& · $1 은 그대로 글자다', () => {
    const doc = parse(render(tower({ bld_nm: '$&$1빌딩' })));
    expect(doc.title.startsWith('$&$1빌딩 — ')).toBe(true);
  });

  it('도로명주소가 없으면 제목은 이름만 · 설명 괄호·소개 "에 있는"·JSON-LD address 를 뺀다', () => {
    const doc = parse(render(tower({ road_addr: null })));
    expect(doc.title).toBe('디아이타워 | 상가 층별 스택뷰');
    expect(meta(doc, 'meta[name="description"]')[0].startsWith('디아이타워의 층별 용도')).toBe(true);
    expect(doc.querySelector('p.seo-intro')!.textContent!.startsWith('디아이타워는 지상 12층·지하 3층 건물입니다.')).toBe(true);
    const ld = JSON.parse(doc.querySelector('script[type="application/ld+json"]')!.textContent!);
    expect('address' in ld.about).toBe(false);
  });

  it('지하가 없으면 "지하 m층" 을 빼고 · 층 이름표·옥탑·빈 용도를 그대로 따른다', () => {
    const rows = [
      row(1, { floor_label: '1층(필로티)', main_use: null }),
      row(2, { segment_cnt: null }),
      row(99, { main_use: '계단실' }),
    ];
    const doc = parse(render(rows));
    const desc = meta(doc, 'meta[name="description"]')[0];
    expect(desc).toContain('지상 2층, 층별개요 구간 4개.');
    expect(desc).not.toContain('지하');
    const intro = doc.querySelector('p.seo-intro')!.textContent!;
    expect(intro).toContain('지상 2층 건물입니다.');
    expect(intro.endsWith('층별 구성: 1층(필로티)(구간 2) · 2층 제1종근린생활시설 · 옥탑 계단실(구간 2).')).toBe(true);
    expect(intro).not.toContain(' 외 ');
  });

  it('도로명 한 낱말뿐이면 그대로 쓴다', () => {
    expect(parse(render(tower({ road_addr: '테헤란로' }))).title).toBe('디아이타워 — 테헤란로 | 상가 층별 스택뷰');
  });
});

describe('비주거 판정 · noindex(👤 2026-10-09 19:1x — 색인 대상 = 비주거 층 있는 건물)', () => {
  const NOINDEX = '<meta name="robots" content="noindex" />';
  const count = (html: string) => html.split(NOINDEX).length - 1;

  it('isNonResidential — main_use 와 uses[].use 를 쉼표·· 로 나눈 조각 하나라도 비주거면 true', () => {
    expect(isNonResidential([row(1)])).toBe(true); // 제1종근린생활시설
    expect(isNonResidential([row(1, { main_use: '공동주택', uses: [{ use: '공동주택·제2종근린생활시설' }] })])).toBe(true);
    expect(isNonResidential([row(1, { main_use: '아파트, 업무시설' })])).toBe(true);
    expect(isNonResidential([row(1, { main_use: '아파트', uses: [{ use: '아파트' }, { use: '주차장, 기계실' }] })])).toBe(false);
    // detail('84세대')은 안 본다 — 정규식에 안 걸리는 글이라 보면 아파트가 비주거로 둔갑한다.
    expect(isNonResidential([row(1, { main_use: '아파트', uses: [{ use: '아파트', detail: '84세대' }] })])).toBe(false);
    expect(isNonResidential([row(1, { main_use: null, uses: null }), row(2, { main_use: ' ', uses: [{ use: null }] })])).toBe(false);
  });

  it('구분자 넓힘 — / · 공백 · " 및 " 으로 붙은 근린생활시설도 비주거로 본다(noindex 0)', () => {
    for (const use of ['아파트/근린생활시설', '공동주택(아파트) 및 근린생활시설', '아파트 근린생활시설']) {
      expect(isNonResidential([row(1, { main_use: use, uses: [{ use }] })]), use).toBe(true);
      expect(count(render(tower({ main_use: use, uses: [{ use }] }))), use).toBe(0);
    }
  });

  it('연결어(및·외·등·기타)·한 글자 조각은 버린다 — 주거만 있으면 그대로 noindex', () => {
    for (const use of ['아파트 및 주차장', '공동주택 외', '아파트 등', '기타 아파트', '아파트 / 주차장', '아파트 A']) {
      expect(isNonResidential([row(1, { main_use: use, uses: [{ use }] })]), use).toBe(false);
    }
    // 창고시설만 있는 건물은 대상 밖(noindex) — 산업물류 축을 다룰 때 👤 재확인
    expect(count(render(tower({ main_use: '창고시설', uses: [{ use: '창고시설' }] })))).toBe(1);
  });

  it('아파트만 있는 건물 → 머리글은 건물 것 · noindex 정확히 1개(</head> 앞)', () => {
    const html = render(tower({ main_use: '아파트', uses: [{ use: '아파트' }] }));
    expect(count(html)).toBe(1);
    expect(html.indexOf(NOINDEX)).toBeLessThan(html.indexOf('</head>'));
    expect(parse(html).title).toBe('디아이타워 — 강남구 테헤란로 123 | 상가 층별 스택뷰');
  });

  it('근린생활시설 행이 있으면 noindex 0개', () => {
    expect(count(render(tower()))).toBe(0);
    const mixed = [...tower({ main_use: '아파트', uses: [{ use: '아파트' }] }).slice(1), row(1)];
    expect(count(render(mixed))).toBe(0);
  });

  it('정규식은 사이트맵 스크립트와 같은 목록(파이썬 쪽 대조는 tests/test_build_sitemap.py)', () => {
    expect(RESIDENTIAL_RE.source.startsWith('(주택|주거|아파트|')).toBe(true);
    expect(RESIDENTIAL_RE.flags).toBe('');
  });
});

describe('양성 대조 — 치환 가드가 실제로 잡는가', () => {
  it('<title> 이 둘인 HTML 은 throw', () => {
    const two = HOME.replace('</head>', '<title>둘째</title></head>');
    expect(() => renderBuildingHtml(two, tower())).toThrow(/<title> 개수가 2개/);
  });

  it('소개문·canonical·JSON-LD 가 없는 HTML 도 throw', () => {
    expect(() => renderBuildingHtml(HOME.replace('class="seo-intro"', 'class="x"'), tower())).toThrow(/소개문 개수가 0개/);
    expect(() => renderBuildingHtml(HOME.replace('rel="canonical"', 'rel="x"'), tower())).toThrow(/canonical 개수가 0개/);
    expect(() => renderBuildingHtml(HOME.replace('application/ld+json', 'x'), tower())).toThrow(/JSON-LD 개수가 0개/);
  });

  it('금지어 탐지가 실제로 잡는다', () => {
    const bad = render(tower({ bld_nm: '적정가격빌딩' }));
    expect(BANNED.some((w) => bad.includes(w))).toBe(true);
  });
});

describe('정본 대조', () => {
  it('사이트 이름은 seo.ts 와 같고 · 정식 주소는 index.html canonical 과 같다', () => {
    expect(SITE_NAME).toBe(SEO_SITE_NAME);
    expect(meta(parse(HOME), 'link[rel="canonical"]')).toEqual([`${SITE_ORIGIN}/`]);
  });
});
