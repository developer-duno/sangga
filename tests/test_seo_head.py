# -*- coding: utf-8 -*-
"""
검색·AI 노출 머리글 가드 — `index.html` 머리글 · `public/robots.txt` · `public/sitemap.xml` ·
`public/og-image.png` · `src/lib/seo.ts` (👤 2026-10-09 결정 넷 · docs/PROGRESS.md 「2026-10-09 (6)」).

왜 이게 필요한가
----------------
첫 HTML 에 제목 한 줄뿐이었고 robots.txt·sitemap.xml 은 404 였다. 카카오톡·대부분의 AI 봇은
JS 를 안 돌리므로 **첫 HTML 의 글자**만 본다 — 여기가 틀리면 화면은 멀쩡해도 밖에서는 틀린 말이
보이고, 그것은 에러가 아니라 조용한 거짓말이다. 그래서:

- 태그가 **두 번** 들면 봇마다 아무거나 고른다 → 각 태그 정확히 1개.
- 주소가 localhost·미리보기 주소로 새면 검색이 엉뚱한 곳을 정본으로 잡는다 → 전부 정식 주소.
- 설명 글에 금지어(절대 규칙 2)가 들면 그대로 검색 결과에 실린다.
- robots.txt 에 Disallow 가 생기면 사장님 결정(전부 허용)이 조용히 뒤집힌다.
- 탭 제목 정본(`seo.ts`)과 첫 HTML 제목이 갈리면 같은 페이지가 두 이름을 갖는다.

⛔ 탐지는 아래 작은 함수들로 빼서, 가드 본체와 양성 대조(가짜 HTML)가 같은 함수를 지난다.
⛔ Pillow 를 쓰지 않는다(pyproject 에 없다) — PNG 크기는 IHDR 바이트로 읽는다.
"""

import json
import re
import struct
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "index.html"
ROBOTS = ROOT / "public" / "robots.txt"
SITEMAP = ROOT / "public" / "sitemap.xml"
OG_IMAGE = ROOT / "public" / "og-image.png"
SEO_TS = ROOT / "src" / "lib" / "seo.ts"

CANONICAL = "https://sangga-one.vercel.app/"
TITLE = "상가 층별 스택뷰 — 서울·대전 상가 건물 층별 공공데이터"
DESCRIPTION = (
    "서울·대전 상가 건물을 찾으면 층마다 용도·면적·점포를 쌓아 보여 주고, "
    "실거래·참고 시세, 둘레의 업종 분포와 개업·폐업, 임대 동향까지 공공데이터로 봅니다. "
    "무료 · 로그인 없음."
)

# 절대 규칙 2 금지어 — 정본은 tests/test_backtest_price.py(import 하지 않고 같은 다섯 낱말을 적는다).
BANNED_TERMS = ("적정가격", "적정가", "평가액", "감정가", "가치평가")
BANNED_SPACED = (("적정", "가격"), ("가치", "평가"))

# 각각 정확히 1개여야 하는 머리글 열쇠(승인 표 A~D).
SINGLE_KEYS = (
    "title",
    "meta:description",
    "link:canonical",
    "og:type",
    "og:site_name",
    "og:locale",
    "og:title",
    "og:description",
    "og:url",
    "og:image",
    "og:image:width",
    "og:image:height",
    "og:image:alt",
    "twitter:card",
    "twitter:title",
    "twitter:description",
    "twitter:image",
)
# 정식 주소로 시작해야 하는 열쇠.
URL_KEYS = ("link:canonical", "og:url", "og:image", "twitter:image")
# 금지어를 보는 열쇠.
TEXT_KEYS = ("title", "meta:description", "og:title", "og:description", "og:image:alt")


class _HeadParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []  # (열쇠, 값)
        self.ld_json = []
        self._in = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in, self._buf = "title", []
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in, self._buf = "ld", []
        elif tag == "meta":
            prop = a.get("property") or a.get("name")
            if prop in ("description",):
                self.items.append(("meta:description", a.get("content", "")))
            elif prop and (prop.startswith("og:") or prop.startswith("twitter:")):
                self.items.append((prop, a.get("content", "")))
        elif tag == "link" and a.get("rel") == "canonical":
            self.items.append(("link:canonical", a.get("href", "")))

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "title" and self._in == "title":
            self.items.append(("title", "".join(self._buf)))
            self._in = None
        elif tag == "script" and self._in == "ld":
            self.ld_json.append("".join(self._buf))
            self._in = None


def parse_head(html):
    """머리글을 (열쇠, 값) 목록과 JSON-LD 덩어리 목록으로 읽는다."""
    p = _HeadParser()
    p.feed(html)
    p.close()
    return p.items, p.ld_json


def banned_hits(text):
    """금지어를 찾는다 — 두 낱말짜리는 띄어 쓴 꼴(`적정 가격`)까지.
    ⚠️ 못 보는 것: 짧은 셋을 띄어 쓴 꼴(`감정 가`) · 낱말 사이에 다른 글자를 끼운 꼴."""
    hits = [t for t in BANNED_TERMS if t in text]
    for head, tail in BANNED_SPACED:
        hits += re.findall(head + r"[ \t]+" + tail, text)
    return hits


def is_canonical_url(url):
    """정식 주소로 시작하나 — localhost·미리보기(*.vercel.app 다른 이름)·http 를 거른다."""
    return url.startswith(CANONICAL)


def head_problems(html):
    """머리글의 문제를 글 목록으로 낸다(빈 목록 = 정상).
    ⚠️ 못 보는 것: 주석 안 태그(파서가 건너뛴다 — 봇도 같다) · 값의 뜻이 맞는지(글자만 본다)."""
    items, _ = parse_head(html)
    problems = []
    for key in SINGLE_KEYS:
        n = sum(1 for k, _ in items if k == key)
        if n != 1:
            problems.append(f"{key} 개수 {n}")
    for key, value in items:
        if key in URL_KEYS and not is_canonical_url(value):
            problems.append(f"{key} 주소가 정식 주소 아님: {value}")
        if key in TEXT_KEYS and banned_hits(value):
            problems.append(f"{key} 금지어: {banned_hits(value)}")
    return problems


def robots_problems(text):
    """robots.txt 의 문제 — Disallow 가 하나라도 있거나 Sitemap 줄이 정식 주소가 아니면."""
    problems = []
    lines = [ln.strip() for ln in text.splitlines()]
    if "User-agent: *" not in lines:
        problems.append("User-agent: * 없음")
    if any(re.match(r"(?i)disallow\s*:", ln) for ln in lines):
        problems.append("Disallow 있음")
    sitemaps = [ln for ln in lines if re.match(r"(?i)sitemap\s*:", ln)]
    if sitemaps != [f"Sitemap: {CANONICAL}sitemap.xml"]:
        problems.append(f"Sitemap 줄: {sitemaps}")
    return problems


def png_size(data):
    """PNG 머리(IHDR)에서 (가로, 세로)를 읽는다 — Pillow 없이."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "PNG 서명이 아님"
    assert data[12:16] == b"IHDR", "첫 덩어리가 IHDR 이 아님"
    return struct.unpack(">II", data[16:24])


def _index():
    return INDEX_HTML.read_text(encoding="utf-8")


# ── 실제 파일 ────────────────────────────────────────────────────────────────


def test_index_head_has_no_problems():
    assert head_problems(_index()) == []


def test_index_title_and_description_exact():
    items = dict(parse_head(_index())[0])
    assert items["title"] == TITLE
    assert items["meta:description"] == DESCRIPTION
    assert items["link:canonical"] == CANONICAL
    assert items["og:url"] == CANONICAL
    assert items["og:image"] == CANONICAL + "og-image.png"
    assert items["og:title"] == items["twitter:title"] == TITLE
    assert items["og:description"] == items["twitter:description"] == DESCRIPTION
    assert items["twitter:image"] == items["og:image"]
    assert (items["og:image:width"], items["og:image:height"]) == ("1200", "630")
    assert items["twitter:card"] == "summary_large_image"


def test_index_json_ld_is_one_block_with_visible_facts_only():
    _, blocks = parse_head(_index())
    assert len(blocks) == 1
    ld = json.loads(blocks[0])
    assert ld == {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": "상가 층별 스택뷰",
        "url": CANONICAL,
        "description": DESCRIPTION,
        "inLanguage": "ko",
        "isAccessibleForFree": True,
        "applicationCategory": "BusinessApplication",
        "operatingSystem": "Any",
    }


def test_robots_allows_all_and_points_to_sitemap():
    assert robots_problems(ROBOTS.read_text(encoding="utf-8")) == []


_SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_SM_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_BUILDING_SITEMAP_RE = re.compile(r"^sitemap-buildings-\d+\.xml$")


def sitemap_problems(public_dir):
    """`sitemap.xml`(색인) 과 그것이 나열한 파일들의 문제를 글 목록으로 낸다(빈 목록 = 정상 · 결정 0037).
    ⚠️ 못 보는 것: 건물 주소가 실제로 있는 건물인지(DB 를 안 본다 — scripts/build_sitemap.py 가 고른다) ·
       색인에 안 실린 채 public/ 에 남은 다른 이름의 xml."""
    problems = []
    index = ET.parse(public_dir / "sitemap.xml").getroot()
    if index.tag != _SM + "sitemapindex":
        return ["sitemap.xml 이 sitemapindex 가 아님: {}".format(index.tag)]
    listed = [el.text or "" for el in index.findall("s:sitemap/s:loc", _SM_NS)]
    if not listed or listed[0] != CANONICAL + "sitemap-home.xml":
        problems.append("색인 첫 줄이 sitemap-home.xml 이 아님: {}".format(listed[:1]))
    if index.findall("s:sitemap/s:lastmod", _SM_NS):
        problems.append("색인에 lastmod 있음")
    names = []
    for loc in listed:
        if not loc.startswith(CANONICAL):
            problems.append("색인 주소가 정식 주소 아님: {}".format(loc))
            continue
        name = loc[len(CANONICAL):]
        names.append(name)
        if not (public_dir / name).is_file():
            problems.append("색인이 나열한 파일이 public/ 에 없음: {}".format(name))
    on_disk = sorted(p.name for p in public_dir.iterdir() if _BUILDING_SITEMAP_RE.match(p.name))
    for name in on_disk:
        if name not in names:
            problems.append("색인에 안 실린 건물 사이트맵: {}".format(name))
    for name in names:
        path = public_dir / name
        if not path.is_file():
            continue
        root = ET.parse(path).getroot()
        if root.tag != _SM + "urlset":
            problems.append("{} 이 urlset 이 아님".format(name))
            continue
        locs = [el.text or "" for el in root.findall("s:url/s:loc", _SM_NS)]
        if root.findall("s:url/s:lastmod", _SM_NS):
            problems.append("{} 에 lastmod 있음".format(name))
        if name == "sitemap-home.xml" and locs != [CANONICAL]:
            problems.append("sitemap-home.xml 의 loc 이 첫 화면 하나가 아님: {}".format(locs))
        if _BUILDING_SITEMAP_RE.match(name):
            if len(locs) > 50000:
                problems.append("{} 주소 {}개 — 50,000 초과".format(name, len(locs)))
            bad = [loc for loc in locs if not loc.startswith(CANONICAL + "?sgg=")]
            if bad:
                problems.append("{} 에 정식 건물 주소가 아닌 loc: {}".format(name, bad[:3]))
    return problems


def test_sitemap_index_and_listed_files():
    assert sitemap_problems(SITEMAP.parent) == []


def test_og_image_is_1200x630_and_small():
    data = OG_IMAGE.read_bytes()
    assert png_size(data) == (1200, 630)
    assert len(data) <= 200 * 1024


def test_seo_ts_home_title_matches_index_title():
    m_html = re.search(r"<title>(.*?)</title>", _index(), re.S)
    m_ts = re.search(r"export const HOME_TITLE = '([^']*)';", SEO_TS.read_text(encoding="utf-8"))
    assert m_html and m_ts
    assert m_ts.group(1) == m_html.group(1) == TITLE


# ── 양성 대조 — 탐지 함수가 실제로 잡는지 ─────────────────────────────────────


def _fake(replace_from, replace_to):
    html = _index()
    assert replace_from in html
    return html.replace(replace_from, replace_to, 1)


def test_control_banned_word_in_description_is_caught():
    bad = _fake('<meta name="description" content="', '<meta name="description" content="적정가격 ')
    assert any("meta:description 금지어" in p for p in head_problems(bad))
    spaced = _fake('<meta name="description" content="', '<meta name="description" content="적정 가격 ')
    assert any("meta:description 금지어" in p for p in head_problems(spaced))


def test_control_localhost_canonical_is_caught():
    bad = _fake(f'<link rel="canonical" href="{CANONICAL}"', '<link rel="canonical" href="http://localhost:5173/"')
    assert any("link:canonical 주소가" in p for p in head_problems(bad))
    preview = _fake(f'<meta property="og:url" content="{CANONICAL}"', '<meta property="og:url" content="https://sangga-git-x.vercel.app/"')
    assert any("og:url 주소가" in p for p in head_problems(preview))


def test_control_duplicate_og_title_is_caught():
    bad = _fake("<meta property=\"og:title\"", '<meta property="og:title" content="둘째" />\n    <meta property="og:title"')
    assert "og:title 개수 2" in head_problems(bad)


def test_control_robots_disallow_and_wrong_sitemap_are_caught():
    good = ROBOTS.read_text(encoding="utf-8")
    assert "Disallow 있음" in robots_problems(good + "\nUser-agent: GPTBot\nDisallow: /\n")
    assert "Disallow 있음" in robots_problems(good.replace("Allow: /", "disallow : /"))
    bad_map = good.replace(CANONICAL, "http://localhost:5173/")
    assert any(p.startswith("Sitemap 줄") for p in robots_problems(bad_map))


def _copy_public_sitemaps(tmp_path):
    for p in SITEMAP.parent.iterdir():
        if p.name.startswith("sitemap") and p.suffix == ".xml":
            (tmp_path / p.name).write_bytes(p.read_bytes())
    return tmp_path


def test_control_sitemap_index_listing_missing_file_is_caught(tmp_path):
    d = _copy_public_sitemaps(tmp_path)
    text = (d / "sitemap.xml").read_text(encoding="utf-8")
    extra = "  <sitemap><loc>{}sitemap-buildings-9.xml</loc></sitemap>\n</sitemapindex>".format(CANONICAL)
    (d / "sitemap.xml").write_text(text.replace("</sitemapindex>", extra), encoding="utf-8")
    assert any("public/ 에 없음: sitemap-buildings-9.xml" in p for p in sitemap_problems(d))


def test_control_sitemap_urlset_index_and_bad_building_loc_are_caught(tmp_path):
    d = _copy_public_sitemaps(tmp_path)
    old = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>{}</loc></url>\n</urlset>\n'.format(CANONICAL)
    (d / "sitemap.xml").write_text(old, encoding="utf-8")
    assert any("sitemapindex 가 아님" in p for p in sitemap_problems(d))

    d2 = tmp_path / "b"
    d2.mkdir()
    _copy_public_sitemaps(d2)
    bad = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>http://localhost:5173/?sgg=1&amp;bld=2</loc><lastmod>2026-01-01</lastmod></url>\n</urlset>\n'
    (d2 / "sitemap-buildings-1.xml").write_text(bad, encoding="utf-8")
    problems = sitemap_problems(d2)
    assert any("색인에 안 실린 건물 사이트맵" in p for p in problems)
    idx = (d2 / "sitemap.xml").read_text(encoding="utf-8")
    (d2 / "sitemap.xml").write_text(
        idx.replace("</sitemapindex>", "  <sitemap><loc>{}sitemap-buildings-1.xml</loc></sitemap>\n</sitemapindex>".format(CANONICAL)),
        encoding="utf-8",
    )
    problems = sitemap_problems(d2)
    assert any("정식 건물 주소가 아닌 loc" in p for p in problems)
    assert any("lastmod 있음" in p for p in problems)


def test_control_png_size_reads_ihdr():
    fake = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 640, 480) + b"\x08\x02\x00\x00\x00"
    assert png_size(fake) == (640, 480)

# ── 정적 소개문(👤 2026-10-09 초안 B) — JS 를 안 돌리는 봇이 읽는 본문 ────────────────────

INTRO_FIRST = "상가 층별 스택뷰는 서울·대전의 상가 건물을 찾으면"
INTRO_LAST = "로그인 없이 바로 쓸 수 있습니다."
_ROOT_RE = re.compile(r'<div id="root">(.*?)</div>', re.S)
_INTRO_RE = re.compile(r'<p class="seo-intro">(.*?)</p>', re.S)


def intro_problems(html):
    """`#root` 안 정적 소개문의 문제를 글 목록으로 낸다(빈 목록 = 정상).
    ⚠️ 못 보는 것: `#root` 안에 중첩 div 가 생기면 첫 `</div>` 에서 끊긴다 · 문장 뜻(글자만 본다)."""
    problems = []
    root = _ROOT_RE.search(html)
    if not root:
        return ["#root 없음"]
    intros = _INTRO_RE.findall(root.group(1))
    if len(intros) != 1:
        problems.append(f"#root 안 seo-intro 개수 {len(intros)}")
        return problems
    text = intros[0].strip()
    if not text.startswith(INTRO_FIRST):
        problems.append("소개문 첫 문장이 다름")
    if not text.endswith(INTRO_LAST):
        problems.append("소개문 끝 문장이 다름")
    if banned_hits(text):
        problems.append(f"소개문 금지어: {banned_hits(text)}")
    if len(_INTRO_RE.findall(html)) != 1:
        problems.append("seo-intro 가 #root 밖에도 있음")
    return problems


def test_index_root_has_static_intro():
    assert intro_problems(_index()) == []


def test_control_intro_missing_banned_and_outside_are_caught():
    gone = _fake('<p class="seo-intro">', '<p class="seo-intro-x">')
    assert any("개수 0" in p for p in intro_problems(gone))
    banned = _fake('<p class="seo-intro">상가 층별 스택뷰는', '<p class="seo-intro">상가 층별 스택뷰는 감정가 ')
    assert any("금지어" in p for p in intro_problems(banned))
    outside = _fake("</body>", '<p class="seo-intro">x</p></body>')
    assert any("밖에도" in p for p in intro_problems(outside))

