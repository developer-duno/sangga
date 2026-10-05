# -*- coding: utf-8 -*-
"""scripts/collectors/load_seoul_openclose.py 단위 테스트 (결정 0033 · 적재기 1:1).

DB 없이 본다:
  1. 머리말 세 벌(한글 cp949 zip · 영문 소문자 zip · API 영문 대문자 + 실수 `3.0`)이 **같은 줄**이 된다
     · 매핑표 밖 칸은 시끄럽게 멈춘다
  2. 출처 고르기 — API 가 zip 을 이기고, 같은 종류는 가장 최근 받은 날짜
  3. 관문 ⒜~⒡ 양성·음성 짝 — 특히 ⒞ 는 '분모를 점포 수로 바꾼 변이'를 잡는다
  4. `--dry-run` 은 DB 도 파일도 안 쓴다(dbx 를 import 조차 안 한다) · `--skip-quarter`
  5. 적재 SQL — 한 트랜잭션 · 관문은 raise · ⒜ 확인 뒤에 분기 단위 교체
"""

import csv
import io
import json
import os
import sys
import zipfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COLLECTORS_DIR = os.path.join(_ROOT, "scripts", "collectors")
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import load_seoul_openclose as L  # noqa: E402

KOREAN_HEADER = ["기준_년분기_코드", "상권_구분_코드", "상권_구분_코드_명", "상권_코드", "상권_코드_명",
                 "서비스_업종_코드", "서비스_업종_코드_명", "점포_수", "유사_업종_점포_수", "개업_율",
                 "개업_점포_수", "폐업_률", "폐업_점포_수", "프랜차이즈_점포_수"]
LOWER_HEADER = list(L.CANON)

# 2021~2025 zip 실측 행 모양(값은 산식을 지키게 만든 것).
CELLS = [
    ["20241", "A", "골목상권", "3110001", "이북5도청사", "CS100001", "한식음식점", "10", "11", "9", "1", "0", "0", "1"],
    ["20241", "A", "골목상권", "3110001", "이북5도청사", "CS100002", "중식음식점", "3", "3", "0", "0", "33", "1", "0"],
    # similr = 0 인데 폐업 2 — 공표 비율은 0
    ["20241", "A", "골목상권", "3110001", "이북5도청사", "CS100003", "일식음식점", "0", "0", "0", "0", "0", "2", "0"],
]


def api_row(cells):
    """같은 행을 API 꼴(영문 대문자 · 숫자는 실수)로."""
    d = {}
    for c, v in zip(L.CANON, cells):
        d[c.upper()] = float(v) if c in L.COUNT_COLS + L.RATE_COLS else v
    return d


def make_zip(path, header, rows, encoding="cp949"):
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("서울시 상권분석서비스(점포-상권)_2024년.csv", buf.getvalue().encode(encoding))


def make_api(path, quarter, rows):
    with io.open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"quarter": quarter, "fetched_at": "x", "row": r}, ensure_ascii=False) + "\n")


def strip_source(rows):
    return [{k: v for k, v in r.items() if k != "source_nm"} for r in rows]


# ── 1. 머리말 세 벌 ──────────────────────────────────────────────────────────


def test_three_header_variants_give_the_same_rows(tmp_path):
    ko, en = tmp_path / "ko.zip", tmp_path / "en.zip"
    make_zip(ko, KOREAN_HEADER, CELLS)
    make_zip(en, LOWER_HEADER, CELLS)
    api = tmp_path / "20241_20261006.jsonl"
    make_api(api, "20241", [api_row(c) for c in CELLS])
    a = L.read_zip_file(str(ko), ["20241"])["20241"]
    b = L.read_zip_file(str(en), ["20241"])["20241"]
    c = L.read_api_file(str(api), "20241")
    assert strip_source(a) == strip_source(b) == strip_source(c)
    assert len(a) == 3
    assert a[0]["similr_induty_stor_co"] == 11 and isinstance(c[0]["stor_co"], int)
    assert str(c[1]["clsbiz_rt"]) == "33.00"


def test_korean_header_has_the_mixed_yul_ryul():
    """⚠️ 원본 한글 머리말은 '개업_율'·'폐업_률' — 맞춤법을 '고치면' 매핑이 깨진다."""
    assert L.HEADER_MAP["개업_율"] == "opbiz_rt"
    assert L.HEADER_MAP["폐업_률"] == "clsbiz_rt"


@pytest.mark.parametrize("header", [
    KOREAN_HEADER + ["새_칸"],                       # 표에 없는 칸
    KOREAN_HEADER[:-1],                              # 칸 빠짐
    KOREAN_HEADER[:-1] + ["점포_수"],                # 겹침
    [h.replace("개업_율", "개업_률") for h in KOREAN_HEADER],   # 맞춤법이 바뀐 날
])
def test_unknown_or_missing_columns_stop_loudly(header):
    with pytest.raises(L.GateError):
        L.map_header(header, "시험")


@pytest.mark.parametrize("value,ok", [("3", 3), ("3.0", 3), (3.0, 3), ("0", 0)])
def test_counts_accept_integral_floats(value, ok):
    assert L.to_int(value, "stor_co", "시험") == ok


@pytest.mark.parametrize("value", ["3.5", "-1", "", "abc", 2.25])
def test_counts_refuse_the_rest(value):
    with pytest.raises(L.GateError):
        L.to_int(value, "stor_co", "시험")


def test_api_file_with_other_quarter_stops(tmp_path):
    api = tmp_path / "20241_20261006.jsonl"
    make_api(api, "20242", [api_row(CELLS[0])])
    with pytest.raises(L.GateError):
        L.read_api_file(str(api), "20241")


# ── 2. 출처 고르기 ───────────────────────────────────────────────────────────


def test_api_beats_zip_and_newest_date_wins():
    api = [("20241", "20261001", "a_old"), ("20241", "20261006", "a_new"), ("20252", "20261006", "a2")]
    zips = [("2024", "20261005", "z24_old"), ("2024", "20261101", "z24_new"), ("2025", "20261005", "z25")]
    chosen, zip_years = L.pick_sources(api, zips)
    assert chosen == {"20241": ("api", "a_new"), "20252": ("api", "a2")}
    assert zip_years == {"z24_new": ["20242", "20243", "20244"],
                         "z25": ["20251", "20253", "20254"]}


def test_collect_reads_raw_folders_and_skips(tmp_path):
    (tmp_path / "zip").mkdir()
    (tmp_path / "api").mkdir()
    cells2 = [[("20242" if i == 0 else v) for i, v in enumerate(c)] for c in CELLS]
    make_zip(tmp_path / "zip" / "2024_20261005.zip", KOREAN_HEADER, CELLS + cells2)
    make_api(tmp_path / "api" / "20241_20261006.jsonl", "20241", [api_row(c) for c in CELLS])
    rows, src = L.collect(str(tmp_path))
    assert src == {"20241": "20241_20261006.jsonl", "20242": "2024_20261005.zip"}
    rows, src = L.collect(str(tmp_path), skip={"20242"})
    assert set(rows) == {"20241"}


# ── 3. 관문 ─────────────────────────────────────────────────────────────────


def norm_rows(quarter="20241", n=1000, district="3110001"):
    """산식을 지키는 n 행(업종 코드만 다르다)."""
    out = []
    for i in range(n):
        out.append({"quarter": quarter, "district_id": district, "svc_induty_cd": "CS{:06d}".format(i),
                    "svc_induty_cd_nm": "x", "stor_co": 9, "similr_induty_stor_co": 10, "frc_stor_co": 1,
                    "opbiz_stor_co": 1, "opbiz_rt": L.to_rate("10", "o", "t"),
                    "clsbiz_stor_co": 0, "clsbiz_rt": L.to_rate("0", "c", "t"), "source_nm": "t"})
    return out


@pytest.fixture
def small_bounds(monkeypatch):
    monkeypatch.setattr(L, "ROWS_PER_QUARTER", (1, 5000))


def test_gates_pass_on_clean_rows(small_bounds):
    assert L.gate_problems({"20241": norm_rows()}, {"3110001"}) == {}


def test_real_bounds_are_the_planned_ones():
    assert L.ROWS_PER_QUARTER == (70_000, 82_000)
    assert L.FORMULA_MAX_BAD_SHARE == 0.001 and L.FORMULA_TOLERANCE == 1


def test_gate_a_unknown_district(small_bounds):
    p = L.gate_problems({"20241": norm_rows()}, {"9999999"})
    assert any(m.startswith("⒜") for m in p["20241"])


def test_gate_b_quarter_shape(small_bounds):
    p = L.gate_problems({"2024Q1": norm_rows(quarter="2024Q1")}, None)
    assert any(m.startswith("⒝") for m in p["2024Q1"])


def test_gate_c_formula_threshold_is_0_1_percent(small_bounds):
    rows = norm_rows()
    rows[0]["opbiz_rt"] = L.to_rate("50", "o", "t")           # 1행 = 0.1% → 통과
    assert L.gate_problems({"20241": rows}, None) == {}
    rows[1]["clsbiz_rt"] = L.to_rate("50", "c", "t")          # 2행 = 0.2% → 걸림
    assert any(m.startswith("⒞") for m in L.gate_problems({"20241": rows}, None)["20241"])


def test_gate_c_allows_one_point_rounding(small_bounds):
    rows = norm_rows()
    for r in rows:
        r["opbiz_rt"] = L.to_rate("11", "o", "t")             # 1 ÷ 10 = 10 → 공표 11 은 1포인트
    assert L.gate_problems({"20241": rows}, None) == {}


def test_gate_c_similr_zero_expects_zero(small_bounds):
    rows = norm_rows()
    rows[0].update(similr_induty_stor_co=0, stor_co=0, frc_stor_co=0, clsbiz_stor_co=2,
                   opbiz_stor_co=0, opbiz_rt=L.to_rate("0", "o", "t"), clsbiz_rt=L.to_rate("0", "c", "t"))
    assert not L.formula_mismatch(rows[0])
    rows[0]["clsbiz_rt"] = L.to_rate("200", "c", "t")
    assert L.formula_mismatch(rows[0])


def test_mutation_stor_denominator_trips_gate_c(small_bounds):
    """분모를 점포 수(stor)로 잘못 잡으면 프랜차이즈가 있는 행이 줄줄이 걸린다."""
    rows = norm_rows()
    for i, r in enumerate(rows[:30]):
        r.update(stor_co=2, frc_stor_co=8, similr_induty_stor_co=10, opbiz_stor_co=1,
                 opbiz_rt=L.to_rate("10", "o", "t"))
    assert L.gate_problems({"20241": rows}, None) == {}
    bad = L.gate_problems({"20241": rows}, None, denominator="stor_co")
    assert any(m.startswith("⒞") for m in bad["20241"])


def test_gate_d_duplicates(small_bounds):
    rows = norm_rows()
    rows[1]["svc_induty_cd"] = rows[0]["svc_induty_cd"]
    assert any(m.startswith("⒟") for m in L.gate_problems({"20241": rows}, None)["20241"])


def test_gate_e_row_count():
    p = L.gate_problems({"20241": norm_rows(n=100)}, None)
    assert any(m.startswith("⒠") for m in p["20241"])


def test_gate_f_similr_is_stor_plus_frc(small_bounds):
    rows = norm_rows()
    rows[5]["frc_stor_co"] = 3
    assert any(m.startswith("⒡") for m in L.gate_problems({"20241": rows}, None)["20241"])


# ── 4. dry-run · skip ────────────────────────────────────────────────────────


def _raw_with_one_quarter(tmp_path):
    (tmp_path / "zip").mkdir()
    make_zip(tmp_path / "zip" / "2024_20261005.zip", KOREAN_HEADER, CELLS)
    return str(tmp_path)


def test_dry_run_writes_nothing(tmp_path, monkeypatch, small_bounds):
    raw = _raw_with_one_quarter(tmp_path)
    staging = tmp_path / "staging"
    monkeypatch.setattr(L, "seoul_district_ids", lambda: {"3110001"})
    monkeypatch.setitem(sys.modules, "dbx", None)    # import dbx 를 하면 ImportError
    rc = L.main(["--dry-run", "--raw-dir", raw, "--staging-dir", str(staging)])
    assert rc == 0
    assert not staging.exists()


def test_gate_failure_stops_before_db(tmp_path, monkeypatch, small_bounds):
    raw = _raw_with_one_quarter(tmp_path)
    monkeypatch.setattr(L, "seoul_district_ids", lambda: {"0000000"})   # ⒜ 에 걸리게
    monkeypatch.setitem(sys.modules, "dbx", None)
    assert L.main(["--raw-dir", raw, "--staging-dir", str(tmp_path / "s")]) == 1
    assert not (tmp_path / "s").exists()


def test_real_run_calls_dbx_once_with_the_sql(tmp_path, monkeypatch, small_bounds):
    raw = _raw_with_one_quarter(tmp_path)
    monkeypatch.setattr(L, "seoul_district_ids", lambda: {"3110001"})
    calls = []

    class FakeDbx:
        @staticmethod
        def run_sql(sql):
            calls.append(sql)
            return 0

    monkeypatch.setitem(sys.modules, "dbx", FakeDbx)
    assert L.main(["--raw-dir", raw, "--staging-dir", str(tmp_path / "s")]) == 0
    assert len(calls) == 1 and "delete from district_openclose where quarter in ('20241');" in calls[0]
    with io.open(tmp_path / "s" / "district_openclose.csv", encoding="utf-8") as f:
        assert len(f.read().splitlines()) == 3


def test_skip_quarter_shape_is_checked():
    assert L.parse_skip(["20261,20262", "20254"]) == {"20261", "20262", "20254"}
    with pytest.raises(ValueError):
        L.parse_skip(["2026Q1"])


# ── 5. 적재 SQL ──────────────────────────────────────────────────────────────


def test_sql_is_one_transaction_with_raising_gates():
    sql = L.build_sql("C:\\x\\a.csv", ["20262", "20261"], 151884)
    assert sql.startswith("begin;") and sql.rstrip().endswith("commit;")
    assert sql.count("raise exception") == 3
    assert "\\copy stage_openclose (" in sql and "'C:/x/a.csv'" in sql
    gate_a = sql.index("관문 ⒜")
    delete = sql.index("delete from district_openclose where quarter in ('20261', '20262');")
    insert = sql.index("insert into district_openclose (")
    assert gate_a < delete < insert
    assert "151884" in sql


# ── 6. 관문 ⒢ — 처음~끝 사이 빠진 분기 (2026-10-05 검사관 🟡4) ─────────────────


def test_missing_quarters_finds_holes_across_years():
    assert L.missing_quarters(["20243", "20244", "20252"]) == ["20251"]
    assert L.missing_quarters(["20244", "20251", "20252"]) == []
    assert L.missing_quarters(["20211", "20214"]) == ["20212", "20213"]
    assert L.missing_quarters([]) == []


def test_missing_quarters_respects_skip():
    assert L.missing_quarters(["20243", "20252"], skip={"20244", "20251"}) == []
    assert L.missing_quarters(["20243", "20252"], skip={"20244"}) == ["20251"]


def _zip_two_quarters(tmp_path, quarters):
    (tmp_path / "zip").mkdir()
    cells = [[(q if i == 0 else v) for i, v in enumerate(c)] for q in quarters for c in CELLS]
    make_zip(tmp_path / "zip" / "2024_20261005.zip", KOREAN_HEADER, cells)
    return str(tmp_path)


def test_gap_stops_the_load_before_db(tmp_path, monkeypatch, small_bounds, capsys):
    raw = _zip_two_quarters(tmp_path, ["20241", "20243"])
    monkeypatch.setattr(L, "seoul_district_ids", lambda: {"3110001"})
    monkeypatch.setitem(sys.modules, "dbx", None)
    assert L.main(["--dry-run", "--raw-dir", raw]) == 1
    out = capsys.readouterr()
    assert "빠진 분기(⒢): 20242" in out.out and "⒢" in out.err


def test_gap_closed_by_skip_quarter_passes(tmp_path, monkeypatch, small_bounds, capsys):
    raw = _zip_two_quarters(tmp_path, ["20241", "20242", "20243"])
    monkeypatch.setattr(L, "seoul_district_ids", lambda: {"3110001"})
    monkeypatch.setitem(sys.modules, "dbx", None)
    assert L.main(["--dry-run", "--raw-dir", raw, "--skip-quarter", "20242"]) == 0
    assert "빠진 분기(⒢): 없음" in capsys.readouterr().out
