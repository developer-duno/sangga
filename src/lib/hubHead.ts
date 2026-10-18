/*
  구 입구 주소(`/?sgg=<5자리>` · bld 없음)의 첫 HTML 을 그 구의 허브로 바꾸는 순수 함수(결정 0043).

  왜 필요한가
  -----------
  건물 첫 HTML(결정 0037·0042)은 생겼지만 건물마다 **들어오는 내부 링크가 0** 이었다(사이트맵뿐).
  구 입구 주소는 이미 건물 쪽 빵부스러기·「○○구 상가 건물 찾기」가 가리키는 자리라, 그 첫 HTML 에
  그 구의 건물 링크 전부를 실으면 건물마다 들어오는 링크가 1 이 된다. 사람 화면은 지금처럼 구 화면이다
  (React 가 그리면 `#root` 가 덮인다 — 건물 쪽과 같은 방식).

  재료 = `scripts/build_sitemap.py` 가 빌드 때 굽는 `public/hub/<sgg>.json`(사이트맵과 같은 대상 · 요청 때 DB 0).
  이름 글은 건물 쪽 h1 과 **같은 함수·같은 재료**로 만든다(`dongSuffix` — 같은 땅 여러 동이면 동 구분).

  ⛔ 이 파일은 함수 런타임에서도 돈다 — React·import.meta 0 · import 는 `.js` 확장자(buildingHead·regions 는 혼자 서는 파일).
  ⛔ 재료(허브 파일)에 있는 사실만 쓴다 — 지어낸 숫자·금지어(절대 규칙 2)·판단 낱말 0 · 지역 이름은 `SIDOS` 와 구운 구 이름만.
  ⛔ 치환은 태그마다 **정확히 1번**(buildingHead.ts 의 `replaceExactlyOnce`) — 0개·2개면 throw(핸들러가 첫 화면을 no-store 로).
*/
import {
  SITE_NAME,
  SITE_ORIGIN,
  dongSuffix,
  escapeHtml,
  isBldId,
  replaceExactlyOnce,
  shortAddr,
  type ParcelSibling,
} from './buildingHead.js';
import { SIDOS } from './regions.js';

/** 허브 파일의 건물 한 줄(뷰 `api.v_floor_stack` 과 같은 칸 — `bld_cnt` = 뷰 `bld_cnt_in_pnu`). */
export type HubBuilding = {
  bld_id: string;
  pnu: string;
  bld_nm: string | null;
  road_addr: string | null;
  bld_cnt: number;
};

/** `public/hub/<sgg>.json` 의 모양(`build_sitemap.py` 의 `build_hubs`). */
export type HubData = {
  sgg: string;
  sido_code: string;
  sigungu_nm: string;
  buildings: HubBuilding[];
  /** 같은 땅 2동 이상인 땅만 — `list_parcel_buildings(pnu)` 의 (bld_id, bld_nm, dong_nm) 을 함수 차례 그대로. */
  parcels: Record<string, ParcelSibling[]>;
};

export type HubEntry = { href: string; text: string; bldId: string };

const SGG_RE = /^\d{5}$/;
const SIDO_RE = /^\d{2}$/;
const PNU_RE = /^\d{19}$/;

export function isSgg(s: string | null | undefined): boolean {
  return typeof s === 'string' && SGG_RE.test(s);
}

function optStr(v: unknown): boolean {
  return v === null || v === undefined || typeof v === 'string';
}

function isSiblingRow(x: unknown): x is ParcelSibling {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return typeof r.bld_id === 'string' && isBldId(r.bld_id) && optStr(r.bld_nm) && optStr(r.dong_nm);
}

function isHubBuilding(x: unknown, sgg: string): x is HubBuilding {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.bld_id === 'string' &&
    isBldId(r.bld_id) &&
    typeof r.pnu === 'string' &&
    PNU_RE.test(r.pnu) &&
    r.pnu.slice(0, 5) === sgg &&
    optStr(r.bld_nm) &&
    optStr(r.road_addr) &&
    typeof r.bld_cnt === 'number' &&
    Number.isInteger(r.bld_cnt) &&
    r.bld_cnt >= 1
  );
}

/** 허브 파일 모양 확인 — 요청한 구의 파일이고 건물이 1동 이상이며 칸이 전부 제 꼴일 때만 true. */
export function isHubData(x: unknown, sgg: string): x is HubData {
  if (typeof x !== 'object' || x === null) return false;
  const r = x as Record<string, unknown>;
  if (r.sgg !== sgg || !isSgg(sgg)) return false;
  if (typeof r.sido_code !== 'string' || !SIDO_RE.test(r.sido_code) || r.sido_code !== sgg.slice(0, 2)) return false;
  if (typeof r.sigungu_nm !== 'string' || r.sigungu_nm.trim() === '') return false;
  if (!Array.isArray(r.buildings) || r.buildings.length === 0) return false;
  if (!r.buildings.every((b) => isHubBuilding(b, sgg))) return false;
  if (typeof r.parcels !== 'object' || r.parcels === null || Array.isArray(r.parcels)) return false;
  return Object.values(r.parcels as Record<string, unknown>).every((v) => Array.isArray(v) && v.every(isSiblingRow));
}

function clean(s: string | null | undefined): string | null {
  if (typeof s !== 'string') return null;
  const t = s.trim();
  return t ? t : null;
}

/**
 * 허브에 적는 곳 이름 — 시·도 짧은 이름표(`SIDOS` · 👤 「모든 구에 시 이름 붙임」) + 구운 구 이름.
 * 시·도 코드가 표에 없으면 null(지어내지 않는다 — 렌더가 throw 해 핸들러가 첫 화면을 준다).
 */
export function hubPlace(data: Pick<HubData, 'sido_code' | 'sigungu_nm'>): string | null {
  const sido = SIDOS.find((s) => s.code === data.sido_code);
  const gu = clean(data.sigungu_nm);
  return sido && gu ? `${sido.name} ${gu}` : null;
}

/**
 * 건물 이름 — 그 건물 쪽 첫 HTML 의 h1 글자와 같다(결정 0043 H10).
 * 건물 쪽 규칙 그대로: 이름(앞뒤 공백 뗌) + 같은 땅 2동 이상이고 이름이 있으면 `dongSuffix`(같은 재료 — 동 목록 · 동 수).
 * 이름이 없으면 화면과 같은 「(이름 없는 건물)」(대상은 이름 있음이 조건이라 실제로는 안 나온다).
 */
export function hubBuildingName(b: HubBuilding, parcels: HubData['parcels']): string {
  const name = clean(b.bld_nm);
  if (!name) return '(이름 없는 건물)';
  const siblings = b.bld_cnt > 1 ? (parcels[b.pnu] ?? null) : null;
  const suffix = dongSuffix(b.bld_id, siblings, b.bld_cnt);
  return suffix ? `${name} ${suffix}` : name;
}

/** 허브 한 줄(👤 「이름 + 도로명」) = `<이름> · <짧은 도로명>` — 도로명이 없으면 이름만. */
export function hubLine(b: HubBuilding, parcels: HubData['parcels']): string {
  const name = hubBuildingName(b, parcels);
  const road = clean(b.road_addr);
  return road ? `${name} · ${shortAddr(road)}` : name;
}

/**
 * 차례 무리(👤 재확인 2026-10-18 「한글 먼저, 나머지 뒤로」) — 첫 글자가 한글 음절(가~힣) 0 · 영문 1 · 숫자 2 · 그 밖(기호 등) 3.
 */
export function sortGroup(text: string): number {
  const c = text.charAt(0);
  if (c >= '가' && c <= '힣') return 0;
  if (/[A-Za-z]/.test(c)) return 1;
  if (/[0-9]/.test(c)) return 2;
  return 3;
}

/**
 * 링크 목록(이스케이프 전) — 👤 「가나다순」 + 재확인 「한글 먼저, 나머지 뒤로」: 무리(`sortGroup` — 한글 → 영문 → 숫자 → 기호)
 * 차례 → 무리 안은 `Intl.Collator('ko')`(영문은 대소문자 섞어 ABC순) → 같으면 bld_id.
 * 주소 = 사이트맵 `building_loc` 과 같은 꼴(`/?sgg=<pnu 앞 5자리>&bld=<id>` · 상대).
 */
export function hubEntries(data: HubData): HubEntry[] {
  // 함수 안에서 만든다 — 맨 위에 두면 화면 묶음(App 이 이 파일의 제목 함수만 쓴다)에도 남는다.
  const KO = new Intl.Collator('ko');
  return data.buildings
    .map((b) => ({ href: `/?sgg=${b.pnu.slice(0, 5)}&bld=${b.bld_id}`, text: hubLine(b, data.parcels), bldId: b.bld_id }))
    .sort(
      (a, b) =>
        sortGroup(a.text) - sortGroup(b.text) ||
        KO.compare(a.text, b.text) ||
        (a.bldId < b.bldId ? -1 : a.bldId > b.bldId ? 1 : 0),
    );
}

/** 정식 주소(이스케이프 전) — 지금 구 입구 주소 그대로(👤 「지금 구 입구 주소」). */
export function hubCanonical(sgg: string): string {
  return `${SITE_ORIGIN}/?sgg=${sgg}`;
}

/** h1 = 「<곳> 상가 건물 층별 보기」(👤 제목 결정). */
export function hubHeading(place: string): string {
  return `${place} 상가 건물 층별 보기`;
}

export function hubTitle(place: string): string {
  return `${hubHeading(place)} — ${SITE_NAME}`;
}

function groupDigits(n: number): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** 소개문 = 설명 글(👤 시안 글 그대로 + 시 이름) — n = 그 허브에 실은 건물 수. */
export function hubIntro(place: string, n: number): string {
  return `${place}에서 층별 화면을 볼 수 있는 상가 건물 ${groupDigits(n)}곳입니다.`;
}

/** 빵부스러기 JSON-LD — 첫 화면 → <곳>(건물 쪽 `breadcrumbJsonLd` 꼴). */
export function hubBreadcrumbJsonLd(place: string, sgg: string): string {
  const items = [
    { name: SITE_NAME, item: `${SITE_ORIGIN}/` },
    { name: place, item: hubCanonical(sgg) },
  ];
  const ld = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((x, i) => ({ '@type': 'ListItem', position: i + 1, name: x.name, item: x.item })),
  };
  return JSON.stringify(ld).replace(/</g, '\\u003c');
}

const LD_RE = /<script type="application\/ld\+json">([\s\S]*?)<\/script>/g;

/**
 * 첫 화면 JSON-LD 를 읽어 이름·설명·주소만 허브 값으로 바꾼 글(종류·나머지 칸은 첫 화면 그대로 — 새 사실 0).
 * 덩어리가 정확히 1개가 아니거나 JSON 이 아니면 throw.
 */
export function hubJsonLd(homeHtml: string, name: string, description: string, url: string): string {
  const found = [...homeHtml.matchAll(LD_RE)];
  if (found.length !== 1) throw new Error(`첫 HTML 의 JSON-LD 개수가 ${found.length}개 — 정확히 1개여야 바꿀 수 있습니다`);
  const ld: unknown = JSON.parse(found[0][1]);
  if (typeof ld !== 'object' || ld === null || Array.isArray(ld)) throw new Error('첫 HTML 의 JSON-LD 가 객체가 아닙니다');
  const out = { ...(ld as Record<string, unknown>), name, url, description };
  return JSON.stringify(out).replace(/</g, '\\u003c');
}

function metaPattern(attr: 'name' | 'property', key: string): RegExp {
  return new RegExp(`<meta ${attr}="${key}" content="[^"]*"`, 'g');
}

/**
 * 첫 화면 HTML 의 머리글·h1·소개문·내부 링크·빵부스러기를 그 구의 허브로 바꾼다.
 * 곳 이름을 못 만들거나(시·도 코드가 표에 없음) 바꿀 태그가 정확히 1개가 아니면 throw.
 * ⓘ 모양 확인(`isHubData`)은 호출부가 먼저 한다.
 */
export function renderHubHtml(homeHtml: string, data: HubData): string {
  const place = hubPlace(data);
  if (!place) throw new Error(`시·도 코드 ${data.sido_code} 의 이름표가 없습니다`);
  const titleRaw = hubTitle(place);
  const introRaw = hubIntro(place, data.buildings.length);
  const urlRaw = hubCanonical(data.sgg);
  const title = escapeHtml(titleRaw);
  const desc = escapeHtml(introRaw);
  const url = escapeHtml(urlRaw);
  const items = hubEntries(data)
    .map((e) => `<li><a href="${escapeHtml(e.href)}">${escapeHtml(e.text)}</a></li>`)
    .join('');
  const links = `<ul>${items}</ul><p><a href="/">첫 화면</a></p>`;

  let html = homeHtml;
  const ld = hubJsonLd(html, titleRaw, introRaw, urlRaw);
  html = replaceExactlyOnce(html, /<title>[^<]*<\/title>/g, `<title>${title}</title>`, '<title>');
  html = replaceExactlyOnce(html, metaPattern('name', 'description'), `<meta name="description" content="${desc}"`, 'description');
  html = replaceExactlyOnce(html, /<link rel="canonical" href="[^"]*"/g, `<link rel="canonical" href="${url}"`, 'canonical');
  html = replaceExactlyOnce(html, metaPattern('property', 'og:title'), `<meta property="og:title" content="${title}"`, 'og:title');
  html = replaceExactlyOnce(html, metaPattern('property', 'og:description'), `<meta property="og:description" content="${desc}"`, 'og:description');
  html = replaceExactlyOnce(html, metaPattern('property', 'og:url'), `<meta property="og:url" content="${url}"`, 'og:url');
  html = replaceExactlyOnce(html, metaPattern('name', 'twitter:title'), `<meta name="twitter:title" content="${title}"`, 'twitter:title');
  html = replaceExactlyOnce(html, metaPattern('name', 'twitter:description'), `<meta name="twitter:description" content="${desc}"`, 'twitter:description');
  html = replaceExactlyOnce(html, LD_RE, `<script type="application/ld+json">${ld}</script>`, 'JSON-LD');
  // 빵부스러기 — 위 JSON-LD 치환 **뒤에**(앞에서 바꾸면 덩어리가 둘이라 위 가드가 throw · 건물 쪽과 같은 차례).
  html = replaceExactlyOnce(
    html,
    /<!--seo-breadcrumb-->/g,
    `<script type="application/ld+json">${hubBreadcrumbJsonLd(place, data.sgg)}</script>`,
    '빵부스러기 자리',
  );
  html = replaceExactlyOnce(html, /<h1 class="seo-title">[^<]*<\/h1>/g, `<h1 class="seo-title">${escapeHtml(hubHeading(place))}</h1>`, 'h1');
  html = replaceExactlyOnce(html, /<p class="seo-intro">[\s\S]*?<\/p>/g, `<p class="seo-intro">${desc}</p>`, '소개문');
  html = replaceExactlyOnce(
    html,
    /<nav class="seo-links"[^>]*>[\s\S]*?<\/nav>/g,
    `<nav class="seo-links" aria-label="관련 페이지">${links}</nav>`,
    '내부 링크 자리',
  );
  return html;
}
