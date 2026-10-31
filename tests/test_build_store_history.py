# -*- coding: utf-8 -*-
"""scripts/build_store_history.py 단위 테스트 (결정 0045 PR④ · 빌드 1:1).

원본 zip 없이 tmp_path 에 작은 zip 을 만들어 본다(겹zip · cp949 · cp437 이름 포함):
  1. 분기 코드 · zip 차례(이름순 ≠ 날짜순) · 201709 늘 뺌 · 빠진 분기면 멈춤
  2. zip 안 csv 고르기 — cp437 이름 되돌리기 · 시·도 csv 0개·2개면 멈춤 · 머리줄 칸 없음이면 멈춤 · 인코딩 둘
  3. 상호 정규화(규칙 ④)
  4. 사슬 규칙 ①~⑥ · ⓒ(끝난 사슬도 정확히 하나) · 같은 간판 둘 · 깃발
  5. 결과 csv 칸 차례 · meta 칸 · 중복 번호 · 나쁜 pnu · --limit-quarters partial · --reproduce-c 는 파일 0
  6. 재현 판정 경계값 · import 때 부수효과 0
"""

import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import build_store_history as B  # noqa: E402

P1 = "3017010100100010000"
P2 = "3017010100100020000"
PS = "1168010100100010000"
HEAD = ("상가업소번호", "상호명", "지점명", "지번코드", "층정보")


def R(biz, name="김밥", pnu=P1, floor=1):
    """사슬 장부에 넣는 줄 — (biz_no, pnu, floor_no, name_raw, name_norm)."""
    return (biz, pnu, floor, name, B.normalize_name(name))


def csv_bytes(rows, enc="utf-8-sig", head=HEAD):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(head)
    w.writerows(rows)
    return buf.getvalue().encode(enc)


def make_zip(path, members, nested=None):
    """members = {이름: 바이트} · nested = 안쪽 zip 이름(있으면 members 를 그 안에 넣는다)."""
    if nested:
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as z:
            for n, b in members.items():
                z.writestr(n, b)
        members = {nested: inner.getvalue()}
    with zipfile.ZipFile(path, "w") as z:
        for n, b in members.items():
            z.writestr(n, b)
    return str(path)


def opener_of(data):
    return lambda: io.BytesIO(data)


# ── 1. 분기 · 차례 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("name, ym", [
    ("소상공인시장진흥공단_상가(상권)정보_20251030.zip", "202509"),
    ("상가(상권)정보_20260630.zip", "202606"),
    ("상가(상권)정보_20151231.zip", "201512"),
    ("상가(상권)정보_20170930.zip", "201709"),
    ("x_20180215.zip", "201712"),
])
def test_zip_quarter(name, ym):
    assert B.zip_quarter(name) == ym


def test_zip_quarter_without_date_is_none():
    assert B.zip_quarter("상가(상권)정보.zip") is None


def test_zips_sorted_by_date_not_name(tmp_path):
    # 이름순이면 '상가…20260630' 이 '소상공인…20260331' 보다 앞이다
    make_zip(tmp_path / "상가(상권)정보_20260630.zip", {})
    make_zip(tmp_path / "소상공인시장진흥공단_상가(상권)정보_20260331.zip", {})
    (tmp_path / "요약_20171120.csv").write_text("x", encoding="utf-8")
    assert sorted(os.listdir(tmp_path))[0].startswith("상가")
    assert [ym for ym, _p in B.list_quarter_zips(str(tmp_path))] == ["202603", "202606"]


def test_same_quarter_twice_stops(tmp_path):
    make_zip(tmp_path / "a_20250930.zip", {})
    make_zip(tmp_path / "b_20251030.zip", {})
    with pytest.raises(B.BuildError, match="같은 분기"):
        B.list_quarter_zips(str(tmp_path))


def test_201709_is_never_read_and_is_the_only_allowed_gap():
    zips = [(ym, ym) for ym in ("201706", "201709", "201712", "201803")]
    assert [ym for ym, _ in B.select_quarters(zips, B.DEFAULT_START_YM, "201803")] == ["201712", "201803"]
    assert [ym for ym, _ in B.select_quarters(zips, B.REPRO_START_YM, "201803")] == ["201706", "201712", "201803"]


def test_missing_quarter_stops():
    zips = [(ym, ym) for ym in ("201712", "201806")]
    with pytest.raises(B.BuildError, match="빠졌습니다"):
        B.select_quarters(zips, "201712", "201806")


def test_end_ym_cuts_later_zips():
    zips = [(ym, ym) for ym in ("201712", "201803", "201806")]
    assert [ym for ym, _ in B.select_quarters(zips, "201712", "201803")] == ["201712", "201803"]


# ── 2. zip 안 csv ────────────────────────────────────────────────────────────


def test_cp437_name_is_restored(tmp_path):
    mangled = "소상공인_서울_202306.csv".encode("cp949").decode("cp437")
    path = make_zip(tmp_path / "x_20230630.zip", {mangled: csv_bytes([])})
    with zipfile.ZipFile(path) as zf:
        names = [n for n, _o in B.list_csv_members(zf)]
    assert names == ["소상공인_서울_202306.csv"]


def test_nested_zip_one_level(tmp_path):
    path = make_zip(tmp_path / "x_20190331.zip", {"a_서울_201903.csv": csv_bytes([]), "필독.txt": b"x"},
                    nested="inner_201903.zip")
    with zipfile.ZipFile(path) as zf:
        names = [n for n, _o in B.list_csv_members(zf)]
    assert names == ["inner_201903.zip>a_서울_201903.csv"]


@pytest.mark.parametrize("names", [["a_대전.csv"], ["a_서울.csv", "b_서울.csv"]])
def test_sido_csv_must_be_exactly_one(names):
    members = [(n, None) for n in names] + [("서울_필독.csv", None)]
    with pytest.raises(B.BuildError, match="정확히 1개"):
        B.pick_sido_csv(members, "서울", "201712")


def test_missing_column_stops():
    data = csv_bytes([], head=("상가업소번호", "상호명", "지번코드"))
    with pytest.raises(B.BuildError, match="층정보"):
        B.read_quarter_rows(opener_of(data), "x")


@pytest.mark.parametrize("enc", ["utf-8-sig", "cp949"])
def test_encoding_is_picked_from_first_line(enc):
    data = csv_bytes([("A1", "김밥천국", "", P1, "1층")], enc=enc)
    rows, counts = B.read_quarter_rows(opener_of(data), "x")
    assert rows == [("A1", P1, 1, "김밥천국", "김밥천국")]
    assert counts["read"] == 1


def test_dup_biz_first_row_only_and_bad_pnu_and_short_rows_are_counted():
    data = csv_bytes([
        ("A1", "첫줄", "", P1, "1"),
        ("A1", "둘째줄", "", P1, "2"),
        ("A2", "땅번호틀림", "", "301701010010001000", "1"),
        ("A3", "짧은줄"),
    ])
    rows, counts = B.read_quarter_rows(opener_of(data), "x")
    assert [r[3] for r in rows] == ["첫줄"]
    assert counts == {"read": 4, "short": 1, "bad_pnu": 1, "dup_biz_no": 1}


# ── 3. 상호 정규화 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw, norm", [
    ("스타벅스 (강남점)", "스타벅스(강남점)"),
    ("ＡＢＣ\u3000마트", "ABC마트"),
    ("Abc(가)-점", "Abc(가)-점"),
])
def test_normalize_name(raw, norm):
    assert B.normalize_name(raw) == norm


# ── 4. 사슬 규칙 ─────────────────────────────────────────────────────────────


def run_book(quarters, link=True):
    book = B.ChainBook(link=link)
    for ym, rows in quarters:
        book.step(ym, rows)
    return book


def by_first(book):
    return sorted(((c.first_ym, c.biz_no_last), c) for c in book.chains)


def test_rule1_same_number_continues():
    book = run_book([("201712", [R("A")]), ("201803", [R("A")])])
    (c,) = book.chains
    assert (c.seen_cnt, c.n_links, c.first_ym, c.last_ym) == (2, 0, "201712", "201803")


def test_rule2_one_ended_one_new_same_key_links():
    book = run_book([("201712", [R("A")]), ("201803", [R("B")])])
    (c,) = book.chains
    assert (c.biz_no_last, c.n_links, c.first_ym, c.seen_cnt) == ("B", 1, "201712", 2)


def test_rule2_two_new_same_key_do_not_link():
    book = run_book([("201712", [R("A")]), ("201803", [R("B"), R("C")])])
    assert len(book.chains) == 3
    assert sum(c.n_links for c in book.chains) == 0


def test_rule2_two_ended_one_new_do_not_link():
    """ⓒ — 끝난 사슬 쪽이 둘이면 어느 사슬인지 고를 근거가 없다."""
    book = run_book([("201712", [R("A"), R("A2")]), ("201803", [R("B")])])
    assert len(book.chains) == 3
    assert sum(c.n_links for c in book.chains) == 0


@pytest.mark.parametrize("old_floor, new_floor", [(None, None), (None, 1), (1, None)])
def test_rule3_unknown_floor_never_links(old_floor, new_floor):
    book = run_book([("201712", [R("A", floor=old_floor)]), ("201803", [R("B", floor=new_floor)])])
    assert len(book.chains) == 2
    assert sum(c.n_links for c in book.chains) == 0


def test_rule4_space_and_fullwidth_only_difference_links():
    book = run_book([("201712", [R("A", "ＧＳ25 강남점")]), ("201803", [R("B", "GS25\u3000강남점")])])
    (c,) = book.chains
    assert c.n_links == 1


def test_rule5_values_are_from_last_quarter():
    book = run_book([("201712", [R("A", "옛이름", floor=1)]), ("201803", [R("A", "새이름", floor=2)])])
    (c,) = book.chains
    assert (c.name_raw, c.floor_no) == ("새이름", 2)
    rows = B.out_rows(book.chains, "201712", "201803")
    assert rows[0][2] == "새이름"


def test_pnu_change_follows_last_value_and_is_counted():
    book = run_book([("201712", [R("A", pnu=P1)]), ("201803", [R("A", pnu=P2)])])
    (c,) = book.chains
    assert c.pnu == P2 and book.pnu_changed == 1


@pytest.mark.parametrize("old, new, lvl", [
    (P1, P1, 0), (P1, P2, 1), (P1, "3020010100100010000", 2), (P1, PS, 3),
])
def test_pnu_change_level(old, new, lvl):
    assert B.pnu_change_level(old, new) == lvl


def test_pnu_change_stats_counts_widest_move_once():
    """한 사슬이 같은 시군구 → 다른 시·도로 두 번 바뀌면 다른 시·도 하나로만 센다(바뀜 횟수는 따로 2)."""
    book = run_book([
        ("201712", [R("A", pnu=P1), R("K", "그대로", pnu=P1), R("G", "갔다", pnu=P1)]),
        ("201803", [R("A", pnu=P2), R("K", "그대로", pnu=P1)]),
        ("201806", [R("A", pnu=PS), R("K", "그대로", pnu=P1)]),
    ])
    stats, far = B.pnu_change_stats(book.chains, "201806")
    assert book.pnu_changed == 2
    assert {k: v["chains"] for k, v in stats.items()} == {"same_sgg": 0, "other_sgg": 0, "other_sido": 1}
    assert stats["other_sido"]["current"] == 1
    assert stats["other_sido"]["seen_pct"] == pytest.approx(3 / 6 * 100)    # A 3 · K 3 (G 는 끝남)
    assert far == [("김밥", P2, PS, "201712", "201806", 3)]


def test_rule6_missing_one_quarter_starts_new_chain():
    book = run_book([
        ("201712", [R("A", "김밥"), R("X", "다른가게")]),
        ("201803", [R("X", "다른가게")]),
        ("201806", [R("A", "김밥"), R("X", "다른가게")]),
    ])
    a_chains = [c for c in book.chains if c.biz_no_last == "A"]
    assert sorted((c.first_ym, c.last_ym) for c in a_chains) == [("201712", "201712"), ("201806", "201806")]
    rows = {(r[3], r[4]): r for r in B.out_rows(book.chains, "201712", "201806")}
    assert rows[("A", "201712")][7] is False and rows[("A", "201806")][7] is True


def test_two_identical_signs_alive_together_stay_two_chains():
    q = [R("A"), R("B")]
    book = run_book([("201712", q), ("201803", q)])
    assert sorted((c.biz_no_last, c.seen_cnt, c.n_links) for c in book.chains) == [("A", 2, 0), ("B", 2, 0)]


def test_number_only_mode_never_links():
    book = run_book([("201712", [R("A")]), ("201803", [R("B")])], link=False)
    assert len(book.chains) == 2


def test_flags_truncated_and_is_current():
    book = run_book([("201712", [R("A"), R("Z", "가")]), ("201803", [R("A"), R("N", "나")])])
    rows = {r[3]: r for r in B.out_rows(book.chains, "201712", "201803")}
    assert (rows["A"][7], rows["A"][9]) == (True, True)
    assert (rows["Z"][7], rows["Z"][9]) == (False, True)
    assert (rows["N"][7], rows["N"][9]) == (True, False)


def test_out_rows_order():
    book = run_book([
        ("201712", [R("A", "가", floor=2), R("Old", "옛", floor=1)]),
        ("201803", [R("A", "가", floor=2), R("C", "다", floor=None), R("D", "라", floor=-1)]),
    ])
    order = [r[3] for r in B.out_rows(book.chains, "201712", "201803")]
    assert order == ["A", "D", "C", "Old"]


# ── 5. 결과 파일 ─────────────────────────────────────────────────────────────


def two_quarter_zips(tmp_path):
    d = tmp_path / "zips"
    d.mkdir()
    make_zip(d / "상가(상권)정보_20171231.zip", {
        "a_서울_201712.csv": csv_bytes([("S1", "서울가게", "", PS, "1층")]),
        "a_대전_201712.csv": csv_bytes([("D1", "대전 가게", "", P1, "2"), ("D2", "옛가게", "", P1, "B1")]),
    })
    make_zip(d / "상가(상권)정보_20180331.zip", {
        "a_서울_201803.csv": csv_bytes([("S1", "서울가게", "", PS, "1층")], enc="cp949"),
        "a_대전_201803.csv": csv_bytes([("D9", "대전가게", "", P1, "2")], enc="cp949"),
        "필독_대전.csv": b"x",
    }, nested="inner.zip")
    return str(d)


META_KEYS = {"built_on", "start_ym", "end_ym", "sido", "quarters", "rows", "current_rows", "n_links",
             "pnu_changed", "pnu_changed_same_sgg", "pnu_changed_other_sgg", "pnu_changed_other_sido",
             "dup_biz_no", "bad_pnu", "partial", "sha256"}


def test_build_writes_csv_and_meta(tmp_path):
    import datetime
    zips = B.list_quarter_zips(two_quarter_zips(tmp_path))
    out = str(tmp_path / "derived" / "20261101.csv")
    meta = B.build(zips, ("11", "30"), "201712", "201803", 0, out, datetime.date(2026, 11, 1), log=lambda *a: None)
    with io.open(out, encoding="utf-8", newline="") as f:
        lines = list(csv.reader(f))
    assert tuple(lines[0]) == B.OUT_COLUMNS
    assert lines[0] == ["pnu", "floor_no", "biz_name", "biz_no_last", "first_ym", "last_ym",
                        "seen_cnt", "is_current", "n_links", "truncated"]
    body = {r[3]: r for r in lines[1:]}
    assert body["D9"] == [P1, "2", "대전가게", "D9", "201712", "201803", "2", "t", "1", "t"]
    assert body["D2"] == [P1, "-1", "옛가게", "D2", "201712", "201712", "1", "f", "0", "t"]
    assert body["S1"][6:8] == ["2", "t"]
    assert meta["rows"] == 3
    with open(B.meta_path_for(out), encoding="utf-8") as f:
        on_disk = json.load(f)
    assert set(on_disk) == META_KEYS
    assert on_disk["sha256"] == hashlib.sha256(open(out, "rb").read()).hexdigest()
    assert (on_disk["rows"], on_disk["current_rows"], on_disk["n_links"]) == (3, 2, 1)
    assert (on_disk["quarters"], on_disk["partial"], on_disk["sido"]) == (2, False, ["11", "30"])
    assert (on_disk["start_ym"], on_disk["end_ym"], on_disk["built_on"]) == ("201712", "201803", "2026-11-01")
    assert B.meta_path_for(out).endswith("20261101.meta.json")


def test_limit_quarters_marks_partial(tmp_path):
    import datetime
    zips = B.list_quarter_zips(two_quarter_zips(tmp_path))
    out = str(tmp_path / "p.csv")
    meta = B.build(zips, ("30",), "201712", "201803", 1, out, datetime.date(2026, 11, 1), log=lambda *a: None)
    assert meta["partial"] is True and meta["quarters"] == 1 and meta["end_ym"] == "201712"


def test_reproduce_c_writes_no_files_and_fails_on_tiny_data(tmp_path, capsys):
    zip_dir = two_quarter_zips(tmp_path)
    before = sorted(os.listdir(tmp_path))
    rc = B.main(["--reproduce-c", "--zip-dir", zip_dir])
    assert rc == 1
    assert sorted(os.listdir(tmp_path)) == before
    out = capsys.readouterr().out
    assert "번호만" in out and "판정: 실패" in out


def test_main_build_exit_0(tmp_path):
    zip_dir = two_quarter_zips(tmp_path)
    out = str(tmp_path / "o" / "x.csv")
    assert B.main(["--zip-dir", zip_dir, "--out", out]) == 0
    assert os.path.exists(out) and os.path.exists(B.meta_path_for(out))


# ── 6. 재현 판정 · import ────────────────────────────────────────────────────


def stats(median, pct8):
    return {"n": 1, "median": median, "pct8": pct8, "pct1": 0.0, "pct_full": 0.0}


@pytest.mark.parametrize("k1, rule, ok", [
    (stats(19, 65.6), stats(21, 67.9), True),
    (stats(19, 65.3), stats(19, 65.9), True),
    (stats(19, 65.9), stats(23, 69.9), True),
    (stats(19, 65.29), stats(21, 67.9), False),
    (stats(20, 65.6), stats(21, 67.9), False),
    (stats(19, 65.6), stats(24, 67.9), False),
    (stats(19, 65.6), stats(18, 67.9), False),
    (stats(19, 65.6), stats(21, 65.8), False),
    (stats(19, 65.6), stats(21, 70.0), False),
])
def test_judge_reproduction_bounds(k1, rule, ok):
    assert B.judge_reproduction(k1, rule)[0] is ok


def test_import_has_no_side_effects(tmp_path):
    code = ("import csv, sys; sys.path.insert(0, {!r}); before = csv.field_size_limit(); "
            "import build_store_history; assert csv.field_size_limit() == before").format(_SCRIPTS_DIR)
    subprocess.run([sys.executable, "-B", "-c", code], cwd=str(tmp_path), check=True, timeout=60)
    assert os.listdir(tmp_path) == []
