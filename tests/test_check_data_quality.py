# -*- coding: utf-8 -*-
"""
scripts/check_data_quality.py 1:1 단위 테스트.

전부 로컬 임시 CSV 픽스처(tmp_path)로만 검증한다. 공용 설정 파일(conftest.py 등)
없이 이 파일 안에서 import 경로를 직접 해결한다.
"""

import csv
import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import check_data_quality as cdq  # noqa: E402


HEADER = ["층정보", "호정보", "지번코드", "법정동코드"]

# 픽스처 행 설계 (모두 4개 필요 컬럼만 사용 — 실제 파일은 39컬럼이지만
# 이 스크립트는 이름으로 컬럼을 찾으므로 단위 테스트엔 4컬럼이면 충분하다):
#   1) 정상, 마포구, 층='1'
#   2) 정상, 강남구, 층='0'            -> 절대규칙 4 위반 후보('0')
#   3) 층/호 결측 + PNU 형식 불량
#   4) 컬럼 수 부족(2개)                -> f_skipped_short
#   5) 컬럼 수 초과(5개)                -> f_skipped_over
#   6) 정상, 마포구, 층='지하1'          -> 정규화 가능
#   7) 정상, 강남구, 층='abc'            -> 정규화 불가 후보
FIXTURE_ROWS = [
    ["1", "101", "1" * 19, "1144000000"],
    ["0", "102", "2" * 19, "1168000000"],
    ["", "", "bad_pnu", "9999900000"],
    ["2", "103"],
    ["3", "104", "3" * 19, "1144000000", "extra"],
    ["지하1", "105", "4" * 19, "1144012345"],
    ["abc", "106", "5" * 19, "1168012345"],
]


def _write_csv(path, rows, header=None, encoding="utf-8-sig"):
    header = HEADER if header is None else header
    with open(path, "w", encoding=encoding, newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


# ── collect_csv_files (os.walk 재귀) ──────────────────────────────────────────


def test_collect_csv_files_recurses_into_subfolders(tmp_path):
    (tmp_path / "flat.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    sub = tmp_path / "2018년2분기"
    sub.mkdir()
    (sub / "nested.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    deeper = sub / "inner"
    deeper.mkdir()
    (deeper / "deep.CSV").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("무시되어야 함", encoding="utf-8")

    found = cdq.collect_csv_files(str(tmp_path))
    found_names = sorted(os.path.relpath(p, str(tmp_path)) for p in found)

    assert found_names == sorted([
        "flat.csv",
        os.path.join("2018년2분기", "nested.csv"),
        os.path.join("2018년2분기", "inner", "deep.CSV"),
    ])


def test_collect_csv_files_empty_dir_returns_empty_list(tmp_path):
    assert cdq.collect_csv_files(str(tmp_path)) == []


# ── _process_file_with_encoding / process_file: 집계 로직 ────────────────────


def test_process_file_with_encoding_counts_correctly(tmp_path):
    path = tmp_path / "fixture.csv"
    _write_csv(path, FIXTURE_ROWS)

    encoding_used, result = cdq.process_file(str(path))

    assert encoding_used == "utf-8-sig"
    assert result["f_rows"] == 5  # 행 4, 5는 컬럼 수 불일치로 제외
    assert result["f_skipped_short"] == 1
    assert result["f_skipped_over"] == 1
    assert result["floor_missing"] == 1
    assert result["unit_missing"] == 1
    assert result["pnu_valid"] == 4  # 1,2,6,7행 유효 / 3행("bad_pnu")만 무효
    assert result["gu_counts"]["11440"] == 2  # 1, 6행
    assert result["gu_counts"]["11680"] == 2  # 2, 7행
    assert result["floor_counter"]["0"] == 1
    assert result["floor_counter"]["1"] == 1
    assert result["floor_counter"]["지하1"] == 1
    assert result["floor_counter"]["abc"] == 1


def test_process_file_real_cp949_file_falls_back(tmp_path):
    path = tmp_path / "legacy.csv"
    _write_csv(path, FIXTURE_ROWS, encoding="cp949")

    encoding_used, result = cdq.process_file(str(path))

    assert encoding_used == "cp949"
    assert result["f_rows"] == 5


def test_process_file_empty_file_raises(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8-sig")
    with pytest.raises(cdq._EmptyFileError):
        cdq.process_file(str(path))


def test_process_file_missing_columns_raises(tmp_path):
    path = tmp_path / "missing_col.csv"
    _write_csv(path, [["1", "1234567890123456789", "1144000000"]],
               header=["층정보", "지번코드", "법정동코드"])  # 호정보 없음
    with pytest.raises(cdq._MissingColumnsError) as exc_info:
        cdq.process_file(str(path))
    assert "호정보" in exc_info.value.missing_cols


def test_process_file_encoding_fallback_order(monkeypatch):
    """utf-8-sig가 실패하면 cp949로 재시도하고, 둘 다 실패하면 예외를 전파한다."""
    attempts = []

    def fake(path, encoding):
        attempts.append(encoding)
        if encoding == "utf-8-sig":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "위조된 실패")
        return {"f_rows": 0}

    monkeypatch.setattr(cdq, "_process_file_with_encoding", fake)
    encoding_used, result = cdq.process_file("dummy.csv")

    assert attempts == ["utf-8-sig", "cp949"]
    assert encoding_used == "cp949"


def test_process_file_raises_when_all_encodings_fail(monkeypatch):
    def fake(path, encoding):
        raise UnicodeDecodeError(encoding, b"\xff", 0, 1, "위조된 실패")

    monkeypatch.setattr(cdq, "_process_file_with_encoding", fake)
    with pytest.raises(UnicodeDecodeError):
        cdq.process_file("dummy.csv")


# ── main(): 파일 단위 예외 처리 + 종료코드 반영 ───────────────────────────────


def test_main_all_valid_returns_zero_and_reports_correct_totals(tmp_path, monkeypatch, capsys):
    _write_csv(tmp_path / "a.csv", FIXTURE_ROWS)

    monkeypatch.setattr(sys, "argv", ["check_data_quality.py", "--dir", str(tmp_path)])
    rc = cdq.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "전체 행 수(정상 파싱) : 5건" in out
    assert "'0' 값 건수            : 1건" in out
    # MEDIUM 1: 정규화 불가 후보는 이제 normalize_floor(v) is None 기준.
    # floor_counter = {'1':1, '0':1, '지하1':1, 'abc':1} 중 '0'(절대금지)과
    # 'abc'(패턴 자체가 없음) 둘 다 None → 2건 ('지하1'은 -1로 정규화되어 제외).
    assert "정규화 불가 후보 건수  : 2건" in out
    assert "스킵된 파일 없음" in out
    assert "실패한 파일 없음" in out


def test_main_missing_columns_file_causes_skip_and_nonzero_exit(tmp_path, monkeypatch):
    _write_csv(tmp_path / "bad_header.csv",
               [["1", "1234567890123456789", "1144000000"]],
               header=["층정보", "지번코드", "법정동코드"])
    monkeypatch.setattr(sys, "argv", ["check_data_quality.py", "--dir", str(tmp_path)])
    assert cdq.main() == 1


def test_main_no_csv_files_returns_one(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["check_data_quality.py", "--dir", str(tmp_path)])
    assert cdq.main() == 1


def test_main_missing_dir_arg_value_returns_two(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["check_data_quality.py", "--dir"])
    assert cdq.main() == 2


def test_parse_args_defaults_and_overrides():
    assert cdq.parse_args([]) == cdq.DEFAULT_DATA_DIR
    assert cdq.parse_args(["--dir", "X"]) == "X"


def test_parse_args_missing_value():
    with pytest.raises(ValueError, match="뒤에"):
        cdq.parse_args(["--dir"])


def test_parse_args_rejects_unknown_flag_like_help():
    """--help 를 조용히 무시하면 안 된다(다른 수집기들과 동일한 실사고 방지, 2026-08-08)."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        cdq.parse_args(["--help"])


def test_parse_args_rejects_typo_flag():
    """--diir(오타)를 무시하면 의도한 폴더가 아니라 기본 폴더가 조용히 쓰인다."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        cdq.parse_args(["--diir", "X"])


def test_main_nonexistent_dir_returns_one(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["check_data_quality.py", "--dir", str(tmp_path / "no_such_dir")])
    assert cdq.main() == 1


def test_main_one_file_fails_does_not_wipe_other_files_aggregation(tmp_path, monkeypatch, capsys):
    """한 파일이 처리 중 예외를 던져도 나머지 파일 집계는 살아남아야 한다 (항목 3)."""
    good = tmp_path / "good.csv"
    _write_csv(good, FIXTURE_ROWS)
    bad = tmp_path / "bad.csv"
    _write_csv(bad, FIXTURE_ROWS)

    real_process_file = cdq.process_file

    def flaky_process_file(path):
        if os.path.basename(path) == "bad.csv":
            raise OSError("디스크 읽기 실패(시뮬레이션)")
        return real_process_file(path)

    monkeypatch.setattr(cdq, "process_file", flaky_process_file)
    monkeypatch.setattr(sys, "argv", ["check_data_quality.py", "--dir", str(tmp_path)])

    rc = cdq.main()
    out = capsys.readouterr().out

    assert rc == 1  # 실패 파일 1개 있으므로 비정상 종료
    assert "전체 행 수(정상 파싱) : 5건" in out  # good.csv 집계는 살아있음
    assert "실패한 파일 (1개)" in out
    assert "bad.csv" in out
