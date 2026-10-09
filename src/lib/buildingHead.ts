/*
  건물 주소(`/?sgg=&bld=`)의 첫 HTML 머리글·소개문을 그 건물 것으로 바꾸는 순수 함수(결정 0037).

  왜 필요한가
  -----------
  건물 주소를 열어도 첫 HTML 은 첫 화면과 같아서(제목·설명·canonical 전부 첫 화면) 구글이 건물
  페이지를 전부 첫 화면 하나로 합쳤다. 카카오톡·AI 봇은 JS 를 안 돌려 화면이 바꾼 제목도 못 본다.
  그래서 서버 조각(`api/building.ts` → `buildingHandler.ts`)이 같은 index.html 을 가져와 이 함수로
  **머리글과 소개문만** 바꿔 돌려준다. 사람·봇 모두 같은 HTML 이다(봇 전용 분기 금지 — 구글 '우회책').

  ⛔ 이 파일은 함수 런타임에서도 돈다 — React·import.meta·다른 모듈 import 0(혼자 선다).
  ⛔ 뷰(`api.v_floor_stack`)에 있는 사실만 쓴다 — 지어낸 숫자·금지어(절대 규칙 2) 0.
  ⛔ 치환은 태그마다 **정확히 1번** — 첫 HTML 에 같은 태그가 0개·2개면 throw(봇마다 아무거나 고른다).
  ⓘ 사이트 이름·정식 주소는 `seo.ts`·`index.html` 과 같은 글자다(시험이 대조한다).
*/

export const SITE_ORIGIN = 'https://sangga-one.vercel.app';
export const SITE_NAME = '상가 층별 스택뷰';

/** 소개문 층 목록에 싣는 최대 층 수. 넘으면 끝에 ` 외 N층`. */
export const MAX_INTRO_FLOORS = 12;

/** 주소의 `bld` 꼴 — `src/lib/urlState.ts` 의 BLD_RE 와 같다. */
const BLD_RE = /^\d{19}_\d{1,32}$/;

/**
 * 주거·부속 용도 이름(👤 2026-10-09 19:1x 재결정 — 색인 대상 = 비주거 층이 하나라도 있는 건물).
 * ⛔ `scripts/build_sitemap.py` 의 RESIDENTIAL_RE 와 **글자까지 같아야** 한다(tests/test_build_sitemap.py 가 대조).
 */
export const RESIDENTIAL_RE = /(주택|주거|아파트|다세대|연립|기숙사|주차|기계|전기|계단|승강|옥탑|부속|창고|관리|경비|대피|물탱크|펌프|발전|보일러|쓰레기|분리수거)/;

const NOINDEX = '<meta name="robots" content="noindex" />';

/** 서버 조각이 뷰에서 받아 오는 칸(`select=` 와 같은 목록). */
export type BuildingRow = {
  bld_id: string;
  pnu: string;
  /** 지상 n=n / 지하 n=-n / 옥탑=99 / 불명=null. */
  floor_no: number | null;
  floor_label: string | null;
  segment_cnt: number | null;
  main_use: string | null;
  /** 그 층의 용도 구획들(면적 큰 순). 비주거 판정에 `use` 만 본다(`detail` 은 '84세대' 같은 글이라 안 본다). */
  uses: { use: string | null; detail?: string | null; area_m2?: number | null }[] | null;
  /** 화면에 보일 이름(display_nm — 개인 성명 가려짐). */
  bld_nm: string | null;
  road_addr: string | null;
};

export type FloorFact = {
  floorNo: number | null;
  label: string;
  use: string | null;
  segments: number | null;
};

export type BuildingFacts = {
  bldId: string;
  pnu: string;
  name: string | null;
  roadAddr: string | null;
  /** 지상 최고층(옥탑 99 제외). 지상층이 없으면 0. */
  above: number;
  /** 지하 최저층의 깊이(양수). 지하층이 없으면 0. */
  below: number;
  /** 층별개요 구간 수의 합(빈 값은 0 으로 센다). */
  segments: number;
  /** floor_no 오름차순(불명은 맨 뒤). */
  floors: FloorFact[];
};

export function isBldId(s: string | null | undefined): boolean {
  return typeof s === 'string' && BLD_RE.test(s);
}

/**
 * 비주거 층이 하나라도 있나 — 행의 `main_use` 와 `uses[].use` 를 쉼표·'·' 로 나눈 조각 가운데
 * 비어 있지 않고 RESIDENTIAL_RE 에 안 걸리는 것이 하나라도 있으면 true.
 * false 면 머리글은 그 건물 것으로 바꾸되 noindex(카카오톡 미리보기는 건물 것 · 구글은 안 담는다).
 */
export function isNonResidential(rows: BuildingRow[]): boolean {
  for (const r of rows) {
    const names = [r.main_use, ...(r.uses ?? []).map((u) => u?.use ?? null)];
    for (const name of names) {
      if (!name) continue;
      for (const piece of name.split(/[,·]/)) {
        const t = piece.trim();
        if (t && !RESIDENTIAL_RE.test(t)) return true;
      }
    }
  }
  return false;
}

/** `</head>` 앞에 noindex 한 줄 — 앞 줄의 줄바꿈(LF·CRLF)과 들여쓰기를 따른다. */
export function withNoindex(html: string): string {
  if (/(\r?\n)([ \t]*)<\/head>/.test(html)) {
    return html.replace(/(\r?\n)([ \t]*)<\/head>/, (_m, nl: string, ind: string) => `${nl}${ind}  ${NOINDEX}${nl}${ind}</head>`);
  }
  return html.replace('</head>', () => `${NOINDEX}</head>`);
}

function clean(s: string | null | undefined): string | null {
  if (typeof s !== 'string') return null;
  const t = s.trim();
  return t ? t : null;
}

function floorName(floorNo: number | null, label: string | null): string {
  const l = clean(label);
  if (l) return l;
  if (floorNo === null) return '층 불명';
  if (floorNo === 99) return '옥탑';
  if (floorNo < 0) return `지하${-floorNo}층`;
  return `${floorNo}층`;
}

/** 층 행들을 건물 한 채의 사실로 접는다. 행이 없으면 null. */
export function buildingFacts(rows: BuildingRow[]): BuildingFacts | null {
  if (rows.length === 0) return null;
  const head = rows[0];
  // ⛔ 층수 규칙은 `restoreBuilding.ts`(= 검색 서버 search_buildings) 그대로 — 옥탑 99 를 뺀 min/max.
  //    지상 n = max(>0 일 때) · 지하 m = -min(<0 일 때). 새 규칙을 만들지 않는다(시험이 두 함수를 대조한다).
  //    ⓘ 그 파일을 import 하지 않는 것은 이 파일이 함수 런타임에서 혼자 서야 해서다.
  let min: number | null = null;
  let max: number | null = null;
  let segments = 0;
  for (const r of rows) {
    segments += r.segment_cnt ?? 0;
    if (r.floor_no === null || r.floor_no === 99) continue;
    if (min === null || r.floor_no < min) min = r.floor_no;
    if (max === null || r.floor_no > max) max = r.floor_no;
  }
  const above = max !== null && max > 0 ? max : 0;
  const below = min !== null && min < 0 ? -min : 0;
  const sorted = rows
    .map((r, i) => ({ r, i }))
    .sort((a, b) => {
      const x = a.r.floor_no;
      const y = b.r.floor_no;
      if (x === null && y === null) return a.i - b.i;
      if (x === null) return 1;
      if (y === null) return -1;
      return x - y || a.i - b.i;
    });
  return {
    bldId: head.bld_id,
    pnu: head.pnu,
    name: clean(head.bld_nm),
    roadAddr: clean(head.road_addr),
    above,
    below,
    segments,
    floors: sorted.map(({ r }) => ({
      floorNo: r.floor_no,
      label: floorName(r.floor_no, r.floor_label),
      use: clean(r.main_use),
      segments: r.segment_cnt,
    })),
  };
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** 정식 주소(이스케이프 전) — `?sgg=<pnu 앞 5자리>&bld=<id>`. */
export function buildingCanonical(pnu: string, bldId: string): string {
  return `${SITE_ORIGIN}/?sgg=${pnu.slice(0, 5)}&bld=${bldId}`;
}

/** 도로명주소에서 첫 낱말(시·도)만 뗀다. 한 낱말뿐이면 그대로. */
export function shortAddr(roadAddr: string): string {
  const parts = roadAddr.trim().split(/\s+/);
  return parts.length > 1 ? parts.slice(1).join(' ') : parts[0];
}

/** 받침이 있으면 '은', 없으면 '는', 한글이 아니면 '은(는)'. */
export function topicJosa(word: string): string {
  const code = word.charCodeAt(word.length - 1);
  if (code >= 0xac00 && code <= 0xd7a3) return (code - 0xac00) % 28 === 0 ? '는' : '은';
  return '은(는)';
}

function floorsPhrase(f: BuildingFacts): string {
  const parts: string[] = [];
  if (f.above > 0) parts.push(`지상 ${f.above}층`);
  if (f.below > 0) parts.push(`지하 ${f.below}층`);
  return parts.join('·');
}

export function buildingTitle(f: BuildingFacts & { name: string }): string {
  return f.roadAddr
    ? `${f.name} — ${shortAddr(f.roadAddr)} | ${SITE_NAME}`
    : `${f.name} | ${SITE_NAME}`;
}

export function buildingDescription(f: BuildingFacts & { name: string }): string {
  const who = f.roadAddr ? `${f.name}(${f.roadAddr})` : f.name;
  const phrase = floorsPhrase(f);
  const shape = phrase ? `${phrase}, 층별개요 구간 ${f.segments}개.` : `층별개요 구간 ${f.segments}개.`;
  return (
    `${who}의 층별 용도·면적·점포를 건축물대장 층별개요로 쌓아 보여 줍니다. ${shape} ` +
    '실거래 기록, 둘레 업종 분포, 상권 임대 동향(공표값)까지 공공데이터로 봅니다. 무료 · 로그인 없음.'
  );
}

export function buildingIntro(f: BuildingFacts & { name: string }): string {
  const phrase = floorsPhrase(f);
  const where = f.roadAddr ? ` ${f.roadAddr}에 있는` : '';
  const shape = phrase ? ` ${phrase}` : '';
  const shown = f.floors.slice(0, MAX_INTRO_FLOORS).map((x) => {
    const use = x.use ? ` ${x.use}` : '';
    const seg = x.segments !== null ? `(구간 ${x.segments})` : '';
    return `${x.label}${use}${seg}`;
  });
  const rest = f.floors.length - shown.length;
  const list = shown.join(' · ') + (rest > 0 ? ` 외 ${rest}층` : '');
  return (
    `${f.name}${topicJosa(f.name)}${where}${shape} 건물입니다. ` +
    `${SITE_NAME}는 이 건물의 층마다 용도·면적·점포를 건축물대장 층별개요로 쌓아 보여 주고, ` +
    '실거래 기록, 둘레 500m 와 속한 상권의 업종 분포, 부동산원이 조사한 상권 임대료(조사 대상 상권인 건물만), ' +
    `서울시가 공표한 상권 개업·폐업(서울만)을 함께 봅니다. 층별 구성: ${list}.`
  );
}

export function buildingJsonLd(f: BuildingFacts & { name: string }): string {
  const url = buildingCanonical(f.pnu, f.bldId);
  const place: Record<string, unknown> = { '@type': 'Place', name: f.name };
  if (f.roadAddr) {
    place.address = { '@type': 'PostalAddress', streetAddress: f.roadAddr, addressCountry: 'KR' };
  }
  const ld = {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: buildingTitle(f),
    url,
    description: buildingDescription(f),
    inLanguage: 'ko',
    isPartOf: { '@type': 'WebApplication', name: SITE_NAME, url: `${SITE_ORIGIN}/` },
    about: place,
  };
  // `</script>` 로 덩어리를 빠져나가지 못하게 `<` 를 JSON 이스케이프로 바꾼다.
  return JSON.stringify(ld).replace(/</g, '\\u003c');
}

/**
 * `pattern`(g 플래그)이 html 에 **정확히 1번** 나올 때만 바꾼다. 0번·2번+ 이면 throw.
 * 치환 글자는 함수로 넘긴다 — 문자열로 넘기면 `$&`·`$1` 이 특수 패턴으로 읽힌다.
 */
export function replaceExactlyOnce(html: string, pattern: RegExp, replacement: string, what: string): string {
  const n = html.match(pattern)?.length ?? 0;
  if (n !== 1) throw new Error(`첫 HTML 의 ${what} 개수가 ${n}개 — 정확히 1개여야 바꿀 수 있습니다`);
  return html.replace(pattern, () => replacement);
}

function metaPattern(attr: 'name' | 'property', key: string): RegExp {
  return new RegExp(`<meta ${attr}="${key}" content="[^"]*"`, 'g');
}

/**
 * 첫 화면 HTML 의 머리글·소개문을 그 건물 것으로 바꾼다.
 * 행이 없거나 이름이 없으면 null(호출부가 첫 화면 HTML 을 그대로 쓴다).
 * 바꿀 태그가 정확히 1개가 아니면 throw.
 * 비주거 층이 없으면(`isNonResidential` false) `</head>` 앞에 noindex 한 줄을 더한다.
 */
export function renderBuildingHtml(homeHtml: string, rows: BuildingRow[]): string | null {
  const facts = buildingFacts(rows);
  if (!facts || !facts.name) return null;
  const f = { ...facts, name: facts.name };

  const title = escapeHtml(buildingTitle(f));
  const desc = escapeHtml(buildingDescription(f));
  const url = escapeHtml(buildingCanonical(f.pnu, f.bldId));
  const intro = escapeHtml(buildingIntro(f));

  let html = homeHtml;
  html = replaceExactlyOnce(html, /<title>[^<]*<\/title>/g, `<title>${title}</title>`, '<title>');
  html = replaceExactlyOnce(html, metaPattern('name', 'description'), `<meta name="description" content="${desc}"`, 'description');
  html = replaceExactlyOnce(html, /<link rel="canonical" href="[^"]*"/g, `<link rel="canonical" href="${url}"`, 'canonical');
  html = replaceExactlyOnce(html, metaPattern('property', 'og:title'), `<meta property="og:title" content="${title}"`, 'og:title');
  html = replaceExactlyOnce(html, metaPattern('property', 'og:description'), `<meta property="og:description" content="${desc}"`, 'og:description');
  html = replaceExactlyOnce(html, metaPattern('property', 'og:url'), `<meta property="og:url" content="${url}"`, 'og:url');
  html = replaceExactlyOnce(html, metaPattern('name', 'twitter:title'), `<meta name="twitter:title" content="${title}"`, 'twitter:title');
  html = replaceExactlyOnce(html, metaPattern('name', 'twitter:description'), `<meta name="twitter:description" content="${desc}"`, 'twitter:description');
  html = replaceExactlyOnce(
    html,
    /<script type="application\/ld\+json">[\s\S]*?<\/script>/g,
    `<script type="application/ld+json">${buildingJsonLd(f)}</script>`,
    'JSON-LD',
  );
  html = replaceExactlyOnce(html, /<p class="seo-intro">[\s\S]*?<\/p>/g, `<p class="seo-intro">${intro}</p>`, '소개문');
  // 비주거 층이 없는 건물(아파트 동 등) — 미리보기는 건물 것이되 검색 색인에는 안 담는다.
  return isNonResidential(rows) ? html : withNoindex(html);
}
