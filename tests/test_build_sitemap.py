# -*- coding: utf-8 -*-
"""
scripts/build_sitemap.py 가드(결정 0037) — DB 없이 순수 함수만 본다(fetch_rows 는 부르지 않는다).

- 파일당 50,000 경계(구글 상한) · 넘으면 다음 파일
- XML 안 `&` → `&amp;` · loc 은 전부 정식 주소로 시작
- 색인(sitemapindex)이 파일을 전부 · 차례대로 나열 · home 먼저
- 빈 목록이면 home 하나만
- 커밋된 public/sitemap*.xml 이 스크립트 출력과 같다(손으로 고쳐 갈라지면 빨강)
- 결정 0043 구 허브: 열린 구만 · 대상 건물 1동 이상 · 허브 건물 집합 = 사이트맵 건물 집합 · 결정적 바이트 ·
  옛 허브 파일 지우기 · sitemap-hubs.xml 이 색인의 home 다음 · 대상 SQL 을 로컬 PostgreSQL 에서 실제로 돌려 본다
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
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


def fake_materials(rows, open_sggs=("11680",), cnt=None):
    """(bld_id, pnu) 목록 → fetch_rows 가 돌려주는 꼴(건물 줄, 구 줄). 이름은 bld_id 끝 번호."""
    buildings = [
        {"k": "b", "bld_id": b, "pnu": p, "bld_nm": "건물{}".format(b.split("_")[1]),
         "road_addr": "도 시군구 길 {}".format(b.split("_")[1]), "bld_cnt": (cnt or {}).get(p, 1), "sib": None}
        for b, p in rows
    ]
    gus = [{"k": "g", "sgg": s, "sido": s[:2], "nm": "구{}".format(s)} for s in open_sggs]
    return buildings, gus


def locs(xml_text, path):
    return [el.text for el in ET.fromstring(xml_text.encode("utf-8")).findall(path, NS)]


def test_chunk_boundary_50000():
    assert bs.CHUNK_SIZE == 50000
    assert [len(c) for c in bs.chunk(list(range(49999)))] == [49999]
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
    out = (
        '{"k": "b", "bld_id": "1168010600109420015_1", "pnu": "1168010600109420015", "bld_nm": "가|나"}\n\n'
        ' {"k": "g", "sgg": "11680", "sido": "11", "nm": "강남구"} \n'
    )
    buildings, gus = bs.parse_rows(out)
    assert [b["bld_id"] for b in buildings] == ["1168010600109420015_1"]
    assert buildings[0]["bld_nm"] == "가|나"  # 이름 속 '|' 에 안 갈린다(옛 'a|b' 줄 꼴이 아니다)
    assert gus == [{"k": "g", "sgg": "11680", "sido": "11", "nm": "강남구"}]
    for bad in ("a|b|c\n", '{"k": "x"}\n', "[1, 2]\n"):
        with pytest.raises(ValueError):
            bs.parse_rows(bad)


def test_target_sql_matches_decision():
    """👤 2026-10-09 19:1x — 이름 있음 + 층 행 있음 + 비주거 호실 하나라도 · 허브 재료는 같은 질의(결정 0043)."""
    sql = bs.TARGET_SQL
    assert bs.TARGET_WHERE in sql
    assert sql.count(bs.TARGET_WHERE) == 1  # 대상 고르기는 한 번(찬 캐시 약 10분)
    assert "display_nm is not null" in bs.TARGET_WHERE
    # 층 행이 0 인 건물은 함수가 404 를 주므로 사이트맵에 싣지 않는다.
    assert "exists (select 1 from v_building_floor_stack s where s.bld_id = b.bld_id)" in bs.TARGET_WHERE
    assert (
        "exists (select 1 from unit u where u.bld_id = b.bld_id "
        "and u.floor_use is not null and u.floor_use !~ '" + bs.RESIDENTIAL_RE + "')"
    ) in bs.TARGET_WHERE
    assert "'" not in bs.RESIDENTIAL_RE  # SQL 따옴표를 깨지 않는다
    assert sql.startswith("with t as (select b.bld_id, b.pnu, b.display_nm from building b where ")
    # 같은 땅 동 목록은 서버 조각이 부르는 그 함수 그대로(새 함수 정의 0) · 줄바꿈 넣는 json_agg 금지.
    assert "list_parcel_buildings(m.pnu) with ordinality" in sql
    assert "json_agg" not in sql.replace("jsonb_agg", "")
    assert "from mv_open_sigungu m" in sql
    assert "create " not in sql.lower()


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


def test_main_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    """--dry-run 은 DB 를 읽고 개수만 말한다 — public/ 흉내 폴더에 파일이 하나도 안 생긴다."""
    public = tmp_path / "public"
    public.mkdir()
    monkeypatch.setattr(bs, "PUBLIC_DIR", str(public))
    monkeypatch.setattr(bs, "fetch_rows", lambda: fake_materials(fake_rows(3)))
    assert bs.main(["--dry-run"]) == 0
    assert os.listdir(public) == []
    out = capsys.readouterr().out
    assert "대상 건물 3동" in out and "구 허브 1개" in out


def test_control_main_without_dry_run_does_write(tmp_path, monkeypatch):
    """양성 대조 — 같은 흉내로 --dry-run 없이 돌리면 파일이 생긴다(위 시험이 '아무것도 안 하는 main' 을 놓치지 않게)."""
    public = tmp_path / "public"
    public.mkdir()
    monkeypatch.setattr(bs, "PUBLIC_DIR", str(public))
    monkeypatch.setattr(bs, "fetch_rows", lambda: fake_materials(fake_rows(3)))
    assert bs.main([]) == 0
    assert sorted(os.listdir(public)) == [
        "hub", "sitemap-buildings-1.xml", "sitemap-home.xml", "sitemap-hubs.xml", "sitemap.xml",
    ]
    assert os.listdir(public / "hub") == ["11680.json"]


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
    # 결정 0043 — 허브 사이트맵은 home 다음(허브 파일이 있는 구만 싣는다 — 아래 시험이 대조).
    assert read("sitemap.xml") == bs.render_index(["sitemap-home.xml", "sitemap-hubs.xml"] + names)


# ── 결정 0043 구 입구 허브 ──────────────────────────────────────────────────────

def _two_gu_rows():
    """서로 다른 두 구 + 열린 구 밖 하나 — 차례를 섞어 넣는다."""
    rows = []
    for sgg, n in (("11680", 3), ("30140", 2), ("99999", 1)):
        for i in range(n):
            pnu = sgg + "{:014d}".format(i)
            rows.append(("{}_{}".format(pnu, 10 - i), pnu))
    return list(reversed(rows))


def test_build_hubs_open_gu_only_and_counts_outside():
    rows = _two_gu_rows()
    hubs, outside = bs.build_hubs(*fake_materials(rows, open_sggs=("11680", "30140", "11110")))
    # 대상이 0동인 열린 구(11110)는 허브를 안 만든다 · 열린 구 밖(99999)은 빠지고 개수로 알린다.
    assert sorted(hubs) == ["11680", "30140"]
    assert outside == 1
    gangnam = hubs["11680"]
    assert (gangnam["sgg"], gangnam["sido_code"], gangnam["sigungu_nm"]) == ("11680", "11", "구11680")
    ids = [b["bld_id"] for b in gangnam["buildings"]]
    assert ids == sorted(ids) and len(ids) == 3
    assert set(gangnam["buildings"][0]) == {"bld_id", "pnu", "bld_nm", "road_addr", "bld_cnt"}
    assert gangnam["parcels"] == {}


def test_control_open_gu_filter_is_real():
    """양성 대조 — 같은 행이라도 99999 를 열면 허브가 셋이 되고 밖은 0."""
    hubs, outside = bs.build_hubs(*fake_materials(_two_gu_rows(), open_sggs=("11680", "30140", "99999")))
    assert sorted(hubs) == ["11680", "30140", "99999"] and outside == 0


def test_hub_buildings_equal_sitemap_buildings():
    """사이트맵에 있는 건물 = 허브에 있는 건물(열린 구가 다 열려 있을 때) — 주소 글자까지."""
    rows = _two_gu_rows()
    hubs, outside = bs.build_hubs(*fake_materials(rows, open_sggs=("11680", "30140", "99999")))
    files = bs.build_files(rows, hubs.keys())
    sitemap = set(locs(files["sitemap-buildings-1.xml"], "s:url/s:loc"))
    from_hubs = {bs.building_loc(b["bld_id"], b["pnu"]) for h in hubs.values() for b in h["buildings"]}
    assert outside == 0 and from_hubs == sitemap


def test_parcels_only_for_multi_dong_in_function_order():
    pnu = "1168010600109420015"
    rows = [(pnu + "_1", pnu), (pnu + "_2", pnu)]
    buildings, gus = fake_materials(rows, cnt={pnu: 3})
    sib = [{"bld_id": pnu + "_2", "bld_nm": "가", "dong_nm": "B동"}, {"bld_id": pnu + "_1", "bld_nm": "가", "dong_nm": None}]
    for b in buildings:
        b["sib"] = sib
    hubs, _ = bs.build_hubs(buildings, gus)
    # 함수 차례(연면적 큰 순)를 그대로 — 파이썬이 다시 정렬하지 않는다 · 땅마다 한 번.
    assert hubs["11680"]["parcels"] == {pnu: sib}
    assert [b["bld_cnt"] for b in hubs["11680"]["buildings"]] == [3, 3]
    # 동 하나뿐인 땅은 sib 이 와도 싣지 않는다(서버 조각도 bld_cnt_in_pnu > 1 일 때만 부른다).
    one, _ = bs.build_hubs(*fake_materials(rows[:1]))
    assert one["11680"]["parcels"] == {}


@pytest.mark.parametrize("patch", [
    {"bld_id": "abc"},
    {"pnu": "11680"},
    {"bld_cnt": 0},
    {"bld_cnt": None},
    {"bld_nm": 3},
    {"sib": [{"bld_id": "x", "bld_nm": None, "dong_nm": None}], "bld_cnt": 2},
    {"sib": "x", "bld_cnt": 2},
])
def test_bad_building_materials_are_refused(patch):
    buildings, gus = fake_materials(fake_rows(1))
    buildings[0].update(patch)
    with pytest.raises(ValueError):
        bs.build_hubs(buildings, gus)


@pytest.mark.parametrize("gu", [
    {"sgg": "1168", "sido": "11", "nm": "가"},
    {"sgg": "11680", "sido": "30", "nm": "가"},
    {"sgg": "11680", "sido": "11", "nm": " "},
    {"sgg": "11680", "sido": "11", "nm": None},
])
def test_bad_gu_rows_are_refused(gu):
    buildings, _ = fake_materials(fake_rows(1))
    with pytest.raises(ValueError):
        bs.build_hubs(buildings, [gu])


def test_hub_files_are_deterministic_lf_utf8():
    rows = _two_gu_rows()
    a = bs.build_hub_files(bs.build_hubs(*fake_materials(rows, open_sggs=("11680", "30140")))[0])
    b = bs.build_hub_files(bs.build_hubs(*fake_materials(list(reversed(rows)), open_sggs=("30140", "11680")))[0])
    assert a == b
    assert sorted(a) == ["hub/11680.json", "hub/30140.json"]
    for text in a.values():
        assert text.endswith("}\n") and "\r" not in text and text.count("\n") == 1
        assert json.loads(text)["buildings"]
    one = bs.render_hub({"sgg": "11680", "sigungu_nm": "강남구"})
    assert "강남구" in one and "\\u" not in one  # 한글 그대로


def test_build_files_lists_hubs_after_home():
    rows = fake_rows(2)
    files = bs.build_files(rows, ["30140", "11680"])
    assert locs(files["sitemap.xml"], "s:sitemap/s:loc") == [
        SITE + "sitemap-home.xml", SITE + "sitemap-hubs.xml", SITE + "sitemap-buildings-1.xml",
    ]
    assert locs(files["sitemap-hubs.xml"], "s:url/s:loc") == [SITE + "?sgg=11680", SITE + "?sgg=30140"]
    assert "lastmod" not in files["sitemap-hubs.xml"]
    with pytest.raises(ValueError):
        bs.build_files(rows, ["1168"])


def test_control_no_hubs_means_no_hub_sitemap():
    """양성 대조 — 허브가 없으면 허브 사이트맵도 색인 줄도 없다(위 시험이 '늘 싣는 것'을 놓치지 않게)."""
    files = bs.build_files(fake_rows(2))
    assert "sitemap-hubs.xml" not in files
    assert SITE + "sitemap-hubs.xml" not in locs(files["sitemap.xml"], "s:sitemap/s:loc")


def test_write_files_replaces_old_hub_files(tmp_path):
    hub = tmp_path / "hub"
    hub.mkdir()
    for name in ("11110.json", "11680.json"):
        (hub / name).write_text("old", encoding="utf-8")
    (hub / "keep.txt").write_text("x", encoding="utf-8")
    rows = fake_rows(2)
    hubs, _ = bs.build_hubs(*fake_materials(rows))
    bs.write_files(bs.build_files(rows, hubs.keys()), str(tmp_path), bs.build_hub_files(hubs))
    assert sorted(os.listdir(hub)) == ["11680.json", "keep.txt"]
    raw = (hub / "11680.json").read_bytes()
    assert b"\r" not in raw and raw.decode("utf-8") == bs.render_hub(hubs["11680"])
    # hub_files 를 안 주면 허브 폴더는 그대로(옛 호출과 같은 동작).
    bs.write_files(bs.build_files(rows), str(tmp_path))
    assert sorted(os.listdir(hub)) == ["11680.json", "keep.txt"]


def test_zero_hubs_bake_removes_old_hub_sitemap(tmp_path):
    """허브가 0개가 되는 굽기면 옛 sitemap-hubs.xml·hub/*.json 이 남지 않는다(색인에는 이미 안 실린다)."""
    rows = fake_rows(2)
    hubs, _ = bs.build_hubs(*fake_materials(rows))
    bs.write_files(bs.build_files(rows, hubs.keys()), str(tmp_path), bs.build_hub_files(hubs))
    assert (tmp_path / "sitemap-hubs.xml").is_file()
    none, _ = bs.build_hubs(*fake_materials(rows, open_sggs=()))
    assert none == {}
    bs.write_files(bs.build_files(rows, none.keys()), str(tmp_path), bs.build_hub_files(none))
    assert not (tmp_path / "sitemap-hubs.xml").exists()
    assert os.listdir(tmp_path / "hub") == []
    assert SITE + "sitemap-hubs.xml" not in locs((tmp_path / "sitemap.xml").read_text(encoding="utf-8"), "s:sitemap/s:loc")


def test_control_hub_sitemap_kept_when_hubs_remain_or_hub_files_none(tmp_path):
    """양성 대조 — 허브가 남으면 그대로 · hub_files 를 안 준 옛 호출은 허브 사이트맵을 건드리지 않는다."""
    rows = fake_rows(2)
    hubs, _ = bs.build_hubs(*fake_materials(rows))
    bs.write_files(bs.build_files(rows, hubs.keys()), str(tmp_path), bs.build_hub_files(hubs))
    bs.write_files(bs.build_files(rows, hubs.keys()), str(tmp_path), bs.build_hub_files(hubs))
    assert (tmp_path / "sitemap-hubs.xml").is_file()
    bs.write_files(bs.build_files(rows), str(tmp_path))
    assert (tmp_path / "sitemap-hubs.xml").is_file()


def _committed_hubs():
    d = os.path.join(ROOT, "public", "hub")
    names = bs.existing_hub_files(os.path.join(ROOT, "public"))
    out = {}
    for n in names:
        with open(os.path.join(d, n), encoding="utf-8") as f:
            out[n[:5]] = f.read()
    return out


def test_committed_hub_files_match_hub_sitemap_and_buildings():
    """커밋된 허브 파일 ↔ sitemap-hubs.xml ↔ 건물 사이트맵 — 허브 건물 집합 = 사이트맵 건물 집합(주소 글자까지)."""
    public = os.path.join(ROOT, "public")
    hubs = _committed_hubs()
    assert hubs, "public/hub/*.json 이 없다 — python scripts/build_sitemap.py 로 굽고 커밋"
    with open(os.path.join(public, "sitemap-hubs.xml"), encoding="utf-8") as f:
        hub_xml = f.read()
    assert hub_xml == bs.render_urlset([bs.hub_loc(s) for s in sorted(hubs)])
    building_locs = set()
    for name in bs.existing_building_files(public):
        with open(os.path.join(public, name), encoding="utf-8") as f:
            building_locs |= set(locs(f.read(), "s:url/s:loc"))
    from_hubs = set()
    for sgg, text in hubs.items():
        data = json.loads(text)
        assert text == bs.render_hub(data), sgg  # 손으로 고친 흔적 없음(결정적 꼴)
        assert data["sgg"] == sgg and data["buildings"]
        from_hubs |= {bs.building_loc(b["bld_id"], b["pnu"]) for b in data["buildings"]}
    assert from_hubs == building_locs


# ── 대상 SQL 을 로컬 PostgreSQL 에서 실제로 돌린다(문법·jsonb 한 줄·함수 차례) ─────────

SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")


def _list_parcel_buildings_def():
    with open(SCHEMA, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"create or replace function list_parcel_buildings\(p_pnu text\).*?\$\$;", text, re.S)
    assert m, "schema.sql 에서 list_parcel_buildings 정의를 못 찾았다"
    return m.group(0)


SHIM = """
create table building (bld_id text primary key, pnu char(19), display_nm text, dong_nm text, total_area_m2 numeric);
create table v_building_floor_stack (bld_id text, floor_no smallint);
create table building_floor (bld_id text, floor_no smallint);
create table unit (bld_id text, floor_use text);
create table parcel (pnu char(19) primary key, road_addr text);
create table mv_open_sigungu (sido_code char(2), sido_nm text, sigungu_code char(5), sigungu_nm text, building_cnt int);
create function mask_person_name(t text) returns text language sql immutable as 'select t';
"""

P1 = "1168010100100010000"   # 동 셋(그중 하나는 대상 밖 — 주거 호실만)
P2 = "1168010100100020000"   # 동 하나
P3 = "3014010100100010000"   # 대전 쪽 땅
P4 = "2611010100100010000"   # 열린 구 밖

SEED = """
insert into building values
  ('{p1}_1', '{p1}', '큰 상가', '가동', 300), ('{p1}_2', '{p1}', '큰 상가', '나동', 900),
  ('{p1}_3', '{p1}', '큰 상가', '다동', 500),
  ('{p2}_1', '{p2}', '줄|바꿈' || chr(10) || '이름', null, 10),
  ('{p3}_1', '{p3}', '중구 상가', null, 50), ('{p4}_1', '{p4}', '밖 상가', null, 50);
insert into v_building_floor_stack select bld_id, 1 from building;
insert into building_floor select bld_id, 1 from building;
insert into unit values ('{p1}_1', '근린생활시설'), ('{p1}_2', '판매시설'), ('{p1}_3', '아파트'),
  ('{p2}_1', '업무시설'), ('{p3}_1', '근린생활시설'), ('{p4}_1', '근린생활시설');
insert into parcel values ('{p1}', '서울특별시 강남구 가길 1'), ('{p3}', '대전광역시 중구 나길 2');
insert into mv_open_sigungu values ('11', '서울특별시', '11680', '강남구', 4), ('30', '대전광역시', '30140', '중구', 1);
""".format(p1=P1, p2=P2, p3=P3, p4=P4)


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl = shutil.which("initdb"), shutil.which("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl)이 없다 — CI 는 순수 함수 시험만 본다")
    data = str(tmp_path_factory.mktemp("pgdata"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    subprocess.run([initdb, "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8",
                    "--no-locale"], check=True, capture_output=True)
    log = os.path.join(data, "log.txt")
    # ⛔ capture_output 금지 — 서버 자식이 파이프를 물려받아 run() 이 끝없이 기다린다(Windows 실측).
    subprocess.run([pg_ctl, "-D", data, "-l", log, "-w", "-t", "60", "-o",
                    "-p {} -c listen_addresses=127.0.0.1".format(port), "start"],
                   check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)
    try:
        conn = None
        for _ in range(30):
            try:
                conn = psycopg2.connect(host="127.0.0.1", port=port, user="postgres", dbname="postgres")
                break
            except psycopg2.OperationalError:
                time.sleep(0.5)
        assert conn is not None, "로컬 PostgreSQL 에 못 붙었다"
        conn.autocommit = True
        yield conn
        conn.close()
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


def test_target_sql_runs_on_local_postgres(pg):
    c = pg.cursor()
    c.execute("drop schema if exists public cascade; create schema public;")
    c.execute(SHIM)
    c.execute(_list_parcel_buildings_def())
    c.execute(SEED)
    c.execute(bs.TARGET_SQL)
    lines = [r[0] for r in c.fetchall()]
    assert all("\n" not in ln for ln in lines)  # 한 행 = 한 줄(이름 속 줄바꿈도 이스케이프)
    buildings, gus = bs.parse_rows("\n".join(lines) + "\n")
    # 대상 = 이름 + 층 행 + 비주거 호실 — P1 의 다동(아파트만)은 빠진다.
    assert sorted(b["bld_id"] for b in buildings) == sorted([P1 + "_1", P1 + "_2", P2 + "_1", P3 + "_1", P4 + "_1"])
    by = {b["bld_id"]: b for b in buildings}
    assert by[P1 + "_1"]["bld_cnt"] == 3  # 대상 밖 동까지 센다(뷰 bld_cnt_in_pnu 와 같은 셈)
    assert by[P1 + "_1"]["road_addr"] == "서울특별시 강남구 가길 1"
    assert by[P2 + "_1"]["road_addr"] is None and by[P2 + "_1"]["sib"] is None
    assert by[P2 + "_1"]["bld_nm"] == "줄|바꿈\n이름"
    # 같은 땅 동 목록 = 함수 그대로(연면적 큰 순 · 대상 밖 동도 함수가 주면 그대로 · dong_nm 원문).
    assert [s["bld_id"] for s in by[P1 + "_1"]["sib"]] == [P1 + "_2", P1 + "_3", P1 + "_1"]
    assert [s["dong_nm"] for s in by[P1 + "_1"]["sib"]] == ["나동", "다동", "가동"]
    assert sorted(g["sgg"] for g in gus) == ["11680", "30140"]
    hubs, outside = bs.build_hubs(buildings, gus)
    assert sorted(hubs) == ["11680", "30140"] and outside == 1
    assert list(hubs["11680"]["parcels"]) == [P1]
