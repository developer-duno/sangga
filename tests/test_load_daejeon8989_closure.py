# -*- coding: utf-8 -*-
"""scripts/collectors/load_daejeon8989_closure.py 단위 테스트 (결정 0044 · 적재기 1:1).

DB 없이·엑셀 없이 본다(CI 에는 openpyxl 이 없다 — 엑셀을 아는 함수는 read_xlsx_rows 하나뿐이고,
나머지는 튜플 목록만 받는다 · 실제 xlsx 왕복은 openpyxl 이 있을 때만 한 번):
  1. 씨앗 — 83종 · 가게 y 33종이 결정 원문 목록 그대로 · 모양 검사
  2. 관문 다섯(⒜ 파일 0 · ⒝ 머리줄 · ⒞ 씨앗에 없는 업종 · ⒟ 지도에 없는 동 · ⒠ 달 어긋남) 각각 + 개수·중복
  3. 넣는 줄 = 가게 업종 · 2025-01 이후
  4. 창(#4) — 받은 날 − 6개월 · 세 달이 다 든 분기만 · 최근 8분기 · 업종 표 = 최근 4분기
  5. 땅 → 동 지도 ⓐ(점포 많은 동 · 동점이면 뺌) ⓑ(법정동이 동 하나로만 이어질 때만)
  6. --dry-run 은 DB 도 파일도 안 쓴다(dbx 를 import 조차 안 한다) · 적재 SQL 모양
"""

import datetime
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COLLECTORS_DIR = os.path.join(_ROOT, "scripts", "collectors")
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import load_daejeon8989_closure as L  # noqa: E402

# 👤 결정 0044 ② 원문(지시서) — 손님을 받는 가게 업종 33종, 글자 그대로.
STORE_33 = (
    "음식점업", "주점 및 비알코올 음료점업", "종합 소매업", "음ㆍ식료품 및 담배 소매업",
    "섬유, 의복, 신발 및 가죽제품 소매업", "기타 상품 전문 소매업", "기타 생활용품 소매업",
    "가전제품 및 정보 통신장비 소매업", "문화, 오락 및 여가 용품 소매업", "연료 소매업",
    "자동차 및 모터사이클 수리업", "자동차 부품 및 내장품 판매업", "자동차 판매업", "모터사이클 및 부품 판매업",
    "미용, 욕탕 및 유사 서비스업", "그 외 기타 개인 서비스업", "개인 및 가정용품 수리업",
    "컴퓨터 및 통신장비 수리업", "일반 교습학원", "기타 교육기관", "스포츠 서비스업",
    "유원지 및 기타 오락관련 서비스업", "의원", "병원", "수의업", "사진 촬영 및 처리업",
    "일반 및 생활 숙박시설 운영업", "기타 숙박업", "부동산관련 서비스업", "여행사 및 기타 여행 보조 서비스업",
    "개인 및 가정용품 임대업", "기타 보건업", "도서관, 사적지 및 유사 여가관련 서비스업",
)

HEAD = ("행정동 명", "업종분류명(소분류)", "폐업 년월", "폐업 개수", None)   # 원본처럼 끝에 빈 칸
SEED = {"음식점업": True, "무점포 소매업": False, "부동산 임대 및 공급업": False}
DONGS = {"둔산2동", "가수원동"}


def month(ym, *rows):
    """한 달 파일의 줄(머리 + 데이터) — 원본처럼 값은 글자, 끝 칸은 None."""
    return [HEAD] + [(d, i, ym, str(n), None) for d, i, n in rows]


# ── 1. 씨앗 ──────────────────────────────────────────────────────────────────


def test_seed_is_83_with_the_decided_33_stores():
    seed = L.read_seed()
    assert len(seed) == 83
    assert sorted(k for k, v in seed.items() if v) == sorted(STORE_33)
    assert sum(1 for v in seed.values() if not v) == 50


@pytest.mark.parametrize("text", [
    "induty_nm,kind\n음식점업,y\n",          # 머리줄
    "induty_nm,store\n음식점업,Y\n",         # y/n 밖
    "induty_nm,store\n음식점업,y\n음식점업,n\n",  # 중복
    "induty_nm,store\n,y\n",                 # 빈 이름
])
def test_seed_shape_errors_stop(tmp_path, text):
    p = tmp_path / "seed.csv"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(L.GateError):
        L.read_seed(str(p))


# ── 2. 관문 ──────────────────────────────────────────────────────────────────


def test_gate_a_zero_files(tmp_path):
    (tmp_path / L.MONTHLY_DIR).mkdir()
    (tmp_path / L.MONTHLY_DIR / "다른파일.xlsx").write_bytes(b"")
    with pytest.raises(L.GateError, match="⒜"):
        L.collect(str(tmp_path), reader=lambda p: [])


def test_gate_a_missing_folder(tmp_path):
    with pytest.raises(L.GateError, match="⒜"):
        L.collect(str(tmp_path), reader=lambda p: [])


@pytest.mark.parametrize("head", [
    ("행정동명", "업종분류명(소분류)", "폐업 년월", "폐업 개수", None),     # 띄어쓰기가 바뀐 날
    ("행정동 명", "업종분류명(소분류)", "폐업 년월", "폐업 개수", "비고"),   # 칸이 더 생김
    ("행정동 명", "업종분류명(소분류)", "폐업 년월"),                       # 칸이 빠짐
])
def test_gate_b_header(head):
    with pytest.raises(L.GateError, match="⒝"):
        L.parse_month([head], "202501", "시험")


def test_gate_b_header_accepts_trailing_blanks_only():
    L.check_header(HEAD, "시험")
    L.check_header(HEAD[:4], "시험")
    L.check_header(HEAD[:4] + ("", None, "  "), "시험")


def test_gate_b_empty_file():
    with pytest.raises(L.GateError, match="⒝"):
        L.parse_month([], "202501", "시험")


def test_gate_c_unknown_industry():
    rows = L.parse_month(month("202501", ("둔산2동", "새 업종", 1)), "202501", "시험")
    problems = L.gate_problems(rows, SEED, DONGS)
    assert len(problems) == 1 and problems[0].startswith("⒞") and "새 업종" in problems[0]


def test_gate_c_catches_a_store_name_that_drifted_by_one_character():
    """'음식점업' → '음식점 업' — '가게 아님'으로 조용히 새지 않고 멈춘다."""
    rows = L.parse_month(month("202501", ("둔산2동", "음식점 업", 3)), "202501", "시험")
    assert [p[0] for p in L.gate_problems(rows, SEED, DONGS)] == ["⒞"]


def test_gate_d_unknown_dong():
    rows = L.parse_month(month("202501", ("둔산4동", "음식점업", 1)), "202501", "시험")
    problems = L.gate_problems(rows, SEED, DONGS)
    assert len(problems) == 1 and problems[0].startswith("⒟") and "둔산4동" in problems[0]


def test_gate_e_month_differs_from_file_name():
    with pytest.raises(L.GateError, match="⒠"):
        L.parse_month(month("202502", ("둔산2동", "음식점업", 1)), "202501", "시험")


def test_gates_pass_on_clean_rows():
    rows = L.parse_month(month("202501", ("둔산2동", "음식점업", 2), ("가수원동", "무점포 소매업", 1)),
                         "202501", "시험")
    assert L.gate_problems(rows, SEED, DONGS) == []
    assert rows == [("202501", "둔산2동", "음식점업", 2), ("202501", "가수원동", "무점포 소매업", 1)]


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "", "x", None])
def test_count_must_be_positive_integer(value):
    with pytest.raises(L.GateError):
        L.to_count(value, "시험")


@pytest.mark.parametrize("value,ok", [("1", 1), (3, 3), ("2.0", 2), (" 4 ", 4)])
def test_count_accepts(value, ok):
    assert L.to_count(value, "시험") == ok


def test_duplicate_key_stops():
    rows = [("202501", "둔산2동", "음식점업", 1), ("202501", "둔산2동", "음식점업", 2)]
    assert [p[:2] for p in L.gate_problems(rows, SEED, DONGS)] == ["같은"]


def test_blank_rows_are_skipped():
    rows = L.parse_month([HEAD, (None, None, None, None, None), ("둔산2동", "음식점업", "202501", "1", None)],
                         "202501", "시험")
    assert len(rows) == 1


# ── 3. 넣는 줄 ───────────────────────────────────────────────────────────────


def test_rows_to_load_keeps_store_industries_from_2025_only():
    rows = [("202412", "둔산2동", "음식점업", 5), ("202501", "둔산2동", "음식점업", 1),
            ("202501", "둔산2동", "무점포 소매업", 9), ("202609", "가수원동", "음식점업", 2)]
    assert L.rows_to_load(rows, SEED) == [("202501", "둔산2동", "음식점업", 1), ("202609", "가수원동", "음식점업", 2)]


# ── 4. 창 ────────────────────────────────────────────────────────────────────


def test_window_example_from_the_brief():
    q = L.window_quarters(datetime.date(2026, 10, 28))
    assert q == ["20251", "20252", "20253", "20254", "20261"]
    assert q[-L.SUM_QUARTERS:] == ["20252", "20253", "20254", "20261"]


@pytest.mark.parametrize("day,last", [
    ((2026, 11, 30), "20261"),   # M = 202605 — 2분기의 6월이 아직 M 밖
    ((2026, 12, 1), "20262"),    # M = 202606 — 세 달이 다 들어 2분기가 선다
    ((2026, 10, 1), "20261"),
])
def test_window_takes_a_quarter_only_when_all_three_months_are_in(day, last):
    assert L.window_quarters(datetime.date(*day))[-1] == last


def test_window_is_capped_at_eight_most_recent():
    q = L.window_quarters(datetime.date(2029, 1, 15))   # M = 202807 → 2025Q1~2028Q2 (14분기)
    assert q == ["20263", "20264", "20271", "20272", "20273", "20274", "20281", "20282"]


def test_window_boundary_first_quarter():
    assert L.window_quarters(datetime.date(2025, 10, 1)) == ["20251"]       # M = 202504
    assert L.window_quarters(datetime.date(2025, 9, 1)) == ["20251"]        # M = 202503
    assert L.window_quarters(datetime.date(2025, 8, 31)) == []              # M = 202502


def test_dong_summary_counts_window_and_recent_four():
    rows = [("202501", "둔산2동", "음식점업", 2), ("202503", "둔산2동", "의원", 1),
            ("202504", "둔산2동", "음식점업", 4), ("202601", "둔산2동", "의원", 5),
            ("202604", "둔산2동", "음식점업", 9),     # 창 밖(M 의 분기 2분기는 아직 다 안 찼다)
            ("202601", "가수원동", "음식점업", 7)]    # 다른 동
    per_q, total, top = L.dong_summary(rows, "둔산2동", L.window_quarters(datetime.date(2026, 10, 28)))
    assert per_q == [3, 4, 0, 0, 5]       # 빈 분기도 0 으로
    assert total == 9                      # 최근 4분기(20252~20261) = 4 + 5
    assert top == [("의원", 5), ("음식점업", 4)]


# ── 5. 땅 → 동 지도 ──────────────────────────────────────────────────────────

P1, P2, P3 = "3017010100100010000", "3017010100100020000", "3017010200100030000"


def test_map_a_majority_dong_and_ties_are_dropped():
    store = [(P1, "둔산1동"), (P1, "둔산1동"), (P1, "둔산2동"),     # 2:1 → 둔산1동
             (P2, "둔산1동"), (P2, "둔산2동"),                      # 1:1 동점 → 뺌
             (P3, "가수원동")]
    pnu_map, bjd_map, st = L.build_dong_map(store)
    assert pnu_map == {P1: "둔산1동", P3: "가수원동"}
    assert (st["pnu_all"], st["pnu_multi"], st["pnu_ties"], st["pnu_map"]) == (3, 2, 1, 2)
    # ⓑ 3017010100 은 동 둘 → 지도에 없음 · 3017010200 은 동 하나 → 있음
    assert bjd_map == {"3017010200": "가수원동"}
    assert (st["bjd_all"], st["bjd_map"]) == (2, 1)


def test_map_drops_codes_that_are_not_19_digits():
    pnu_map, bjd_map, st = L.build_dong_map([("301701030010000", "도마2동"), ("", "도마2동"), (P1, "")])
    assert pnu_map == {} and bjd_map == {} and st["dropped"] == 3


def test_map_dongs_is_the_union_of_both_maps():
    assert L.map_dongs({P1: "a"}, {"x": "b"}) == {"a", "b"}


# ── 6. 받은 날 · dry-run · SQL ───────────────────────────────────────────────


@pytest.mark.parametrize("name", ["2026-10-28", "20261328", "latest"])
def test_received_date_must_be_a_real_yyyymmdd_folder(tmp_path, name):
    with pytest.raises(L.GateError):
        L.received_date(str(tmp_path / name))


def test_received_date_reads_the_folder_name(tmp_path):
    assert L.received_date(str(tmp_path / "20261028")) == datetime.date(2026, 10, 28)
    assert L.received_date(str(tmp_path / "20261028") + os.sep) == datetime.date(2026, 10, 28)


def _all_months(last="202609"):
    out, ym = [], L.START_YM
    while ym <= last:
        out.append(ym)
        ym = L.ym_add(ym, 1)
    return out


def _raw(tmp_path, months=None, name="20261028"):
    """받은 날 폴더 — 달 파일을 안 주면 2025-01 부터 받은 날의 지난달까지 전부(관문 ⒡ 를 지나는 꼴)."""
    raw = tmp_path / name
    d = raw / L.MONTHLY_DIR
    d.mkdir(parents=True)
    for ym in (months if months is not None else _all_months(L.ym_add(name[:6], -1))):
        (d / "daejeon8989_adstrd_clsbiz_{}.xlsx".format(ym)).write_bytes(b"")
    return raw


def _store_csv(tmp_path):
    p = tmp_path / "store.csv"
    p.write_text("지번코드,행정동명,행정동코드\n{},둔산2동,30170660\n{},가수원동,30170510\n".format(P1, P3),
                 encoding="utf-8-sig")
    return p


def _fake_reader(files):
    """없는 달은 머리줄만 든 파일(대전시는 폐업이 없는 달도 그런 파일을 낸다)."""
    return lambda path: files.get(os.path.basename(path), [HEAD])


def test_dry_run_writes_nothing_and_does_not_import_dbx(tmp_path, monkeypatch, capsys):
    raw = _raw(tmp_path)
    monkeypatch.setattr(L, "read_xlsx_rows", _fake_reader({
        "daejeon8989_adstrd_clsbiz_202501.xlsx": month("202501", ("둔산2동", "음식점업", 2)),
        "daejeon8989_adstrd_clsbiz_202502.xlsx": month("202502", ("가수원동", "무점포 소매업", 1)),
    }))
    sys.modules.pop("dbx", None)
    staging = tmp_path / "staging"
    rc = L.main(["--raw-dir", str(raw), "--store-csv", str(_store_csv(tmp_path)), "--dry-run",
                 "--staging-dir", str(staging)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dbx" not in sys.modules
    assert not staging.exists()
    assert "넣을 줄(가게 업종 · 202501 이후) 1 · 폐업 2건" in out
    assert "관문 통과" in out


def test_gate_failure_exits_1_without_dbx(tmp_path, monkeypatch, capsys):
    raw = _raw(tmp_path)
    monkeypatch.setattr(L, "read_xlsx_rows", _fake_reader({
        "daejeon8989_adstrd_clsbiz_202501.xlsx": month("202501", ("둔산2동", "새로 생긴 업종", 2)),
    }))
    sys.modules.pop("dbx", None)
    rc = L.main(["--raw-dir", str(raw), "--store-csv", str(_store_csv(tmp_path))])   # 실적재여도
    assert rc == 1
    assert "dbx" not in sys.modules
    assert "⒞" in capsys.readouterr().err


def test_month_mismatch_exits_1(tmp_path, monkeypatch):
    raw = _raw(tmp_path)
    monkeypatch.setattr(L, "read_xlsx_rows", _fake_reader({
        "daejeon8989_adstrd_clsbiz_202501.xlsx": month("202412", ("둔산2동", "음식점업", 2)),
    }))
    assert L.main(["--raw-dir", str(raw), "--store-csv", str(_store_csv(tmp_path)), "--dry-run"]) == 1


# ── 보완 1 — ⒡ 달 파일 연속 · ⒢ 반대 방향 동 · 받은 날 앞으로만 ───────────────────


def _main_ok_files():
    return {
        "daejeon8989_adstrd_clsbiz_202501.xlsx": month("202501", ("둔산2동", "음식점업", 2)),
        "daejeon8989_adstrd_clsbiz_202502.xlsx": month("202502", ("가수원동", "무점포 소매업", 1)),
    }


def test_f1_three_files_only_stops(tmp_path, monkeypatch, capsys):
    """검사관 재현 1 — 3파일 폴더(202501~202503)로 실적재하면 나머지 달이 DB 에서 사라진다 → exit 1 · dbx 0."""
    raw = _raw(tmp_path, ["202501", "202502", "202503"])
    monkeypatch.setattr(L, "read_xlsx_rows", _fake_reader(_main_ok_files()))
    sys.modules.pop("dbx", None)
    assert L.main(["--raw-dir", str(raw), "--store-csv", str(_store_csv(tmp_path))]) == 1
    err = capsys.readouterr().err
    assert "⒡ 빠진 달 파일 18개" in err and "202504" in err and "202609" in err
    assert "dbx" not in sys.modules


def test_f1_future_folder_stops(tmp_path, monkeypatch, capsys):
    """검사관 재현 2 — 폴더 이름 20271028(오늘보다 뒤) → exit 1(달 파일이 다 있어도)."""
    raw = _raw(tmp_path, name="20271028")
    monkeypatch.setattr(L, "read_xlsx_rows", _fake_reader(_main_ok_files()))
    assert L.main(["--raw-dir", str(raw), "--store-csv", str(_store_csv(tmp_path)), "--dry-run"]) == 1
    assert "오늘" in capsys.readouterr().err


def test_f1_full_months_pass(tmp_path, monkeypatch):
    raw = _raw(tmp_path)
    monkeypatch.setattr(L, "read_xlsx_rows", _fake_reader(_main_ok_files()))
    assert L.main(["--raw-dir", str(raw), "--store-csv", str(_store_csv(tmp_path)), "--dry-run"]) == 0


def test_month_gaps_and_today_boundary():
    d = datetime.date(2026, 10, 28)
    assert L.month_gaps(_all_months("202609"), d) == []
    assert L.month_gaps([m for m in _all_months("202609") if m != "202512"], d) == ["202512"]
    assert L.month_gaps(_all_months("202608"), d) == ["202609"]           # 지난달이 빠짐
    assert L.month_gaps(_all_months("202609") + ["201405"], d) == []      # 옛 달 파일은 상관없다
    assert L.file_problems(_all_months("202609"), d, d) == []              # 받은 날 = 오늘 은 된다
    assert L.file_problems(_all_months("202609"), d, datetime.date(2026, 10, 27))[0].startswith("⒡ 받은 날")


def test_f_latest_file_month_after_received():
    """⒡ 폴더 이름을 과거로 잘못 적은 날(20251028 ← 20261028) — 파일 중 가장 늦은 달이 받은 날의 달보다 뒤면 멈춘다."""
    wrong = datetime.date(2025, 10, 28)
    bad = L.file_problems(_all_months("202609"), wrong, wrong)
    assert len(bad) == 1 and bad[0].startswith("⒡") and "202609" in bad[0] and "2025-10-28" in bad[0]
    assert "폴더 이름(받은 날)을 확인하세요" in bad[0]
    d = datetime.date(2026, 10, 28)
    assert L.file_problems(_all_months("202609"), d, d) == []                 # 지금 운영 판
    assert L.file_problems(_all_months("202609") + ["202610"], d, d) == []    # 이번 달 파일이 섞여도 같은 달은 허용
    empty = L.file_problems([], d, d)                                          # 파일 0개 — 터지지 않는다(⒜ 몫)
    assert not any("가장 늦은 달" in m for m in empty)


def test_f2_reverse_dong_problems():
    store = [(P1, "둔산2동", "30170660"), (P3, "가수원동", "30170510")]
    assert L.reverse_dong_problems({"둔산2동", "가수원동"}, {"둔산2동", "가수원동", "온천1동"}, store) == []
    lost = L.reverse_dong_problems({"둔산2동", "둔산4동"}, {"둔산2동"}, store)
    assert len(lost) == 1 and lost[0].startswith("⒢") and "둔산4동" in lost[0]
    split = L.reverse_dong_problems({"둔산2동"}, {"둔산2동"}, store + [(P2, "둔산2동", "30170661")])
    assert len(split) == 1 and "30170661" in split[0]


def test_f2_map_dong_missing_from_raw_stops_main(tmp_path, monkeypatch, capsys):
    """지도에는 가수원동이 있는데 원본 어느 달에도 없다 → ⒢ · exit 1."""
    raw = _raw(tmp_path)
    monkeypatch.setattr(L, "read_xlsx_rows", _fake_reader({
        "daejeon8989_adstrd_clsbiz_202501.xlsx": month("202501", ("둔산2동", "음식점업", 2)),
    }))
    assert L.main(["--raw-dir", str(raw), "--store-csv", str(_store_csv(tmp_path)), "--dry-run"]) == 1
    assert "⒢" in capsys.readouterr().err


def test_f3_month_totals_and_dry_run_prints_them(tmp_path, monkeypatch, capsys):
    assert L.month_totals([("202502", "a", "x", 2), ("202501", "b", "y", 1), ("202502", "c", "z", 3)]) == {
        "202501": 1, "202502": 5}
    raw = _raw(tmp_path)
    monkeypatch.setattr(L, "read_xlsx_rows", _fake_reader(_main_ok_files()))
    L.main(["--raw-dir", str(raw), "--store-csv", str(_store_csv(tmp_path)), "--dry-run"])
    assert "달별 폐업(가게 업종 · 202501 이후) {'202501': 2}" in capsys.readouterr().out


def test_f3_sql_refuses_an_older_received_date_before_replacing():
    sql = L.build_sql({"closure": "c.csv", "pnu": "p.csv", "bjd": "b.csv"},
                      {"closure": 1, "pnu": 1, "bjd": 1}, datetime.date(2026, 10, 28))
    guard = "where received_on > date '2026-10-28'"
    assert guard in sql
    assert sql.index(guard) < sql.index("delete from daejeon_dong_closure;")


def test_sql_is_one_transaction_with_checks_before_replacing():
    sql = L.build_sql({"closure": "C:\\a\\c.csv", "pnu": "p.csv", "bjd": "b.csv"},
                      {"closure": 7, "pnu": 5, "bjd": 3}, datetime.date(2026, 10, 28))
    assert sql.count("begin;") == 1 and sql.count("commit;") == 1
    assert sql.index("<> 7") < sql.index("delete from daejeon_dong_closure;")
    assert "from 'C:/a/c.csv'" in sql
    assert "date '2026-10-28'" in sql
    assert "on conflict (id) do update set received_on = excluded.received_on" in sql
    for t in ("daejeon_dong_closure", "daejeon_pnu_dong", "daejeon_bjd_dong"):
        assert "delete from {};".format(t) in sql


def test_real_xlsx_round_trip(tmp_path):
    """openpyxl 이 있을 때만 — 실제 엑셀 한 장을 써서 읽는 함수까지 지난다(CI 는 건너뛴다)."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in month("202501", ("둔산2동", "음식점업", 2)):
        ws.append(list(r))
    p = tmp_path / "x.xlsx"
    wb.save(str(p))
    assert L.parse_month(L.read_xlsx_rows(str(p)), "202501", "x") == [("202501", "둔산2동", "음식점업", 2)]
