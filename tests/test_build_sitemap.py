# -*- coding: utf-8 -*-
"""
scripts/build_sitemap.py 가드(결정 0037) — DB 없이 순수 함수만 본다(fetch_rows 는 부르지 않는다).

- 파일당 50,000 경계(구글 상한) · 넘으면 다음 파일
- XML 안 `&` → `&amp;` · loc 은 전부 정식 주소로 시작
- 색인(sitemapindex)이 파일을 전부 · 차례대로 나열 · home 먼저
- 빈 목록이면 home 하나만
- 커밋된 public/sitemap*.xml 이 스크립트 출력과 같다(손으로 고쳐 갈라지면 빨강)
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_sitemap as bs  # noqa: E402

NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
SITE = "https://sangga-one.vercel.app/"


def fake_rows(n):
    """n 개의 (bld_id, pnu) — 거꾸로 넣어 정렬을 시험한다."""
    rows = []
    for i in range(n):
        pnu = "11680" + "{:014d}".format(i)
        rows.append(("{}_{}".format(pnu, i), pnu))
    return list(reversed(rows))


def locs(xml_text, path):
    return [el.text for el in ET.fromstring(xml_text.encode("utf-8")).findall(path, NS)]


def test_chunk_boundary_50000():
    assert bs.CHUNK_SIZE == 50000
    assert [len(c) for c in bs.chunk(list(range(50000)))] == [50000]
    assert [len(c) for c in bs.chunk(list(range(50001)))] == [50000, 1]
    assert [len(c) for c in bs.chunk(list(range(100000)))] == [50000, 50000]
    assert bs.chunk([]) == []


def test_build_files_splits_at_50000_and_index_lists_all_in_order():
    files = bs.build_files(fake_rows(50001))
    assert sorted(files) == ["sitemap-buildings-1.xml", "sitemap-buildings-2.xml", "sitemap-home.xml", "sitemap.xml"]
    one = locs(files["sitemap-buildings-1.xml"], "s:url/s:loc")
    two = locs(files["sitemap-buildings-2.xml"], "s:url/s:loc")
    assert (len(one), len(two)) == (50000, 1)
    # 정렬 — bld_id 차례 · 파일을 넘어가도 이어진다.
    assert one == sorted(one) and one[-1] < two[0]
    assert locs(files["sitemap.xml"], "s:sitemap/s:loc") == [
        SITE + "sitemap-home.xml",
        SITE + "sitemap-buildings-1.xml",
        SITE + "sitemap-buildings-2.xml",
    ]


def test_empty_rows_give_home_only():
    files = bs.build_files([])
    assert sorted(files) == ["sitemap-home.xml", "sitemap.xml"]
    assert locs(files["sitemap-home.xml"], "s:url/s:loc") == [SITE]
    assert locs(files["sitemap.xml"], "s:sitemap/s:loc") == [SITE + "sitemap-home.xml"]


def test_ampersand_is_escaped_and_locs_are_canonical():
    pnu = "1168010600109420015"
    bld = pnu + "_10241100257870"
    files = bs.build_files([(bld, pnu)])
    text = files["sitemap-buildings-1.xml"]
    assert "?sgg=11680&amp;bld={}</loc>".format(bld) in text
    assert "&bld=" not in text
    assert locs(text, "s:url/s:loc") == ["{}?sgg=11680&bld={}".format(SITE, bld)]
    for name, body in files.items():
        for loc in locs(body, "s:url/s:loc") + locs(body, "s:sitemap/s:loc"):
            assert loc.startswith(SITE), (name, loc)
        assert "lastmod" not in body
        assert "\r" not in body


@pytest.mark.parametrize("bld,pnu", [
    ("abc", "1168010600109420015"),
    ("1168010600109420015_1", "11680"),
    ("1168010600109420015_", "1168010600109420015"),
])
def test_bad_ids_are_refused(bld, pnu):
    with pytest.raises(ValueError):
        bs.build_files([(bld, pnu)])


def test_parse_rows_reads_psql_output():
    out = "1168010600109420015_1|1168010600109420015\n\n 3020010100100010000_2|3020010100100010000 \n"
    assert bs.parse_rows(out) == [
        ("1168010600109420015_1", "1168010600109420015"),
        ("3020010100100010000_2", "3020010100100010000"),
    ]
    with pytest.raises(ValueError):
        bs.parse_rows("a|b|c\n")


def test_target_sql_matches_decision():
    """👤 2026-10-09 19:1x — 이름 있음 + 층 행 있음 + 비주거 호실 하나라도."""
    sql = bs.TARGET_SQL
    assert bs.TARGET_WHERE in sql
    assert "display_nm is not null" in bs.TARGET_WHERE
    # 층 행이 0 인 건물은 함수가 404 를 주므로 사이트맵에 싣지 않는다.
    assert "exists (select 1 from v_building_floor_stack s where s.bld_id = b.bld_id)" in bs.TARGET_WHERE
    assert (
        "exists (select 1 from unit u where u.bld_id = b.bld_id "
        "and u.floor_use is not null and u.floor_use !~ '" + bs.RESIDENTIAL_RE + "')"
    ) in bs.TARGET_WHERE
    assert "'" not in bs.RESIDENTIAL_RE  # SQL 따옴표를 깨지 않는다
    assert sql.startswith("select b.bld_id, b.pnu from building b where ")
    assert sql.endswith("order by b.bld_id")


def ts_residential_re(text):
    """buildingHead.ts 원문에서 `export const RESIDENTIAL_RE = /…/;` 의 정규식 본문을 꺼낸다(없으면 None)."""
    m = re.search(r"^export const RESIDENTIAL_RE = /(.*)/;\s*$", text, re.M)
    return m.group(1) if m else None


def test_residential_re_matches_building_head_ts():
    """파이썬 상수 == 함수 쪽 상수 — 갈라지면 사이트맵 대상과 noindex 판정이 어긋난다."""
    ts = os.path.join(ROOT, "src", "lib", "buildingHead.ts")
    with open(ts, encoding="utf-8") as f:
        assert ts_residential_re(f.read()) == bs.RESIDENTIAL_RE


def test_control_residential_re_drift_is_caught():
    """양성 대조 — 한 낱말만 달라도 다르게 읽힌다 · 상수가 없으면 None."""
    good = "export const RESIDENTIAL_RE = /" + bs.RESIDENTIAL_RE + "/;\n"
    assert ts_residential_re(good) == bs.RESIDENTIAL_RE
    drift = good.replace("|창고", "")
    assert ts_residential_re(drift) != bs.RESIDENTIAL_RE
    assert ts_residential_re("const X = /a/;\n") is None


def test_fetch_rows_sends_sql_by_file_not_dash_c():
    """한글 정규식이 든 SQL 을 psql -c 로 보내면 윈도우에서 cp949 로 깨진다 — 파일(-f)로 보내야 한다."""
    import inspect

    src = inspect.getsource(bs.fetch_rows)
    assert '"-f"' in src
    assert '"-c"' not in src


def test_write_files_removes_old_building_files(tmp_path):
    for n in (1, 2, 3):
        (tmp_path / "sitemap-buildings-{}.xml".format(n)).write_text("old", encoding="utf-8")
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")
    bs.write_files(bs.build_files(fake_rows(2)), str(tmp_path))
    assert sorted(os.listdir(tmp_path)) == ["keep.txt", "sitemap-buildings-1.xml", "sitemap-home.xml", "sitemap.xml"]
    assert b"\r" not in (tmp_path / "sitemap.xml").read_bytes()


def test_existing_building_files_sorted_numerically(tmp_path):
    for n in (10, 2, 1):
        (tmp_path / "sitemap-buildings-{}.xml".format(n)).write_text("x", encoding="utf-8")
    assert bs.existing_building_files(str(tmp_path)) == [
        "sitemap-buildings-1.xml", "sitemap-buildings-2.xml", "sitemap-buildings-10.xml",
    ]


def test_committed_sitemaps_equal_script_output():
    """커밋된 sitemap.xml·sitemap-home.xml 이 스크립트가 같은 건물 파일 목록으로 낼 내용과 같다."""
    public = os.path.join(ROOT, "public")
    names = bs.existing_building_files(public)

    def read(name):
        with open(os.path.join(public, name), encoding="utf-8") as f:
            return f.read()

    assert read("sitemap-home.xml") == bs.render_urlset([SITE])
    assert read("sitemap.xml") == bs.render_index(["sitemap-home.xml"] + names)
