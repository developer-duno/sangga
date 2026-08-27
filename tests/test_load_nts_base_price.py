# -*- coding: utf-8 -*-
"""
scripts/collectors/load_nts_base_price.py 단위 테스트

DB 없이·엑셀 없이 검증한다 (CI 에는 openpyxl 이 없다 — 그래서 엑셀을 아는 함수는
read_sheets 하나뿐이고 나머지는 전부 순수 함수다):

  1. zip 이름 되살리기   — ★ cp437 로 읽힌 cp949. 안 되살리면 "xlsx 가 없다"고 오판한다
  2. 층 변환             — ★ 지상·지하·**옥탑(14행뿐)**, 모르는 값·0·음수는 **멈춘다**
  3. 광주·전남 재코딩    — ★ 29·46 → 12. 모르는 시군구는 조용히 두지 않고 멈춘다
  4. PNU 조립            — 일반지번·산·**가지번(조립 불가가 정상)**, 채움, 형식 위반
  5. record_to_row       — ★ bjd_code_orig 는 **원본 그대로**(재코딩 전)여야 한다
  6. iter_records        — 시트마다 머리글, 빈 줄 건너뛰기, 열 순서가 달라도 이름으로 읽기
  7. 관문 4종            — ★ 실제로 **판별력이 있는가**(통과 사례와 걸리는 사례를 함께 본다)
  8. build_sql           — 한 트랜잭션, \\copy 열 순서 = CSV 열 순서, 관문은 raise exception
  9. transform           — CSV 열 순서·NULL 표기·--limit

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import csv
import io
import os
import sys
import zipfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COLLECTORS_DIR = os.path.join(_ROOT, "scripts", "collectors")
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import load_nts_base_price as L  # noqa: E402


HEADER = list(L.REQUIRED_COLUMNS)


def rec(**over):
    """실제 원본 한 줄(신부파스칼텔 101호)을 바탕으로 한 표본. 필요한 칸만 덮어쓴다."""
    base = {
        "상가건물번호": "1",
        "상가종류코드": "상가",
        "고시일자": "20260101",
        "법정동코드": "1123010600",
        "특수지코드": "일반지번",
        "번지": "0431",
        "호": "0005",
        "상가건물블록주소": "신부파스칼텔",
        "상가건물동주소": "1(단일)",
        "건물층구분코드": "지상층",
        "상가건물층주소": "1",
        "상가건물호주소": "101",
        "고시가격": "2905000",
        "전용면적": "28",
        "공유면적": "7.66",
    }
    base.update(over)
    return base


def row_of(d):
    """dict → 머리글 순서의 튜플 (엑셀 한 줄 흉내)."""
    return tuple(d[c] for c in HEADER)


# ── 1. ★ zip 이름 되살리기 ───────────────────────────────────────────────────


def test_recover_zip_name_restores_korean():
    """cp949 로 적힌 이름이 cp437 로 읽힌 상태를 되돌린다."""
    real = "상업용건물 및 오피스텔 기준시가(2026년 1월 1일 기준).xlsx"
    mojibake = real.encode("cp949").decode("cp437")
    assert mojibake != real                      # 정말로 깨져 있어야 시험이 의미가 있다
    assert L.recover_zip_name(mojibake) == real


def test_recover_zip_name_leaves_plain_ascii_alone():
    assert L.recover_zip_name("data.xlsx") == "data.xlsx"


def test_recover_zip_name_does_not_explode_on_utf8_names():
    """진짜 UTF-8 로 적힌 zip(되살릴 필요가 없는 것)에서 예외를 던지면 정상 zip 이 막힌다."""
    assert L.recover_zip_name("정상이름.xlsx") == "정상이름.xlsx"


def test_find_xlsx_entry_picks_the_broken_name():
    names = ["법정동전체자료.csv".encode("cp949").decode("cp437"),
             "기준시가.xlsx".encode("cp949").decode("cp437")]
    raw, nice = L.find_xlsx_entry(names)
    assert raw == names[1]
    assert nice == "기준시가.xlsx"


def test_find_xlsx_entry_rejects_none_and_many():
    with pytest.raises(ValueError) as e:
        L.find_xlsx_entry(["a.csv"])
    assert "xlsx" in str(e.value)
    with pytest.raises(ValueError):
        L.find_xlsx_entry(["a.xlsx", "b.xlsx"])


def test_ensure_xlsx_extracts_from_a_cp949_named_zip(tmp_path):
    """실제 zip 으로 끝까지 — 이름이 깨진 채로도 꺼내진다."""
    zip_path = str(tmp_path / "src.zip")
    inner = "기준시가.xlsx".encode("cp949").decode("cp437")
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr(inner, b"not-a-real-xlsx-but-bytes")
        z.writestr("법정동전체자료.csv".encode("cp949").decode("cp437"), b"x")
    out, nice = L.ensure_xlsx(zip_path, str(tmp_path / "staging"))
    assert nice == "기준시가.xlsx"
    assert os.path.basename(out) == "기준시가.xlsx"
    with open(out, "rb") as f:
        assert f.read() == b"not-a-real-xlsx-but-bytes"


# ── 2. ★ 층 변환 (절대 규칙 4) ───────────────────────────────────────────────


def test_floor_ground_and_basement():
    assert L.parse_floor("지상층", "1", "x") == 1
    assert L.parse_floor("지상층", "17", "x") == 17
    assert L.parse_floor("지하층", "1", "x") == -1
    assert L.parse_floor("지하층", "3", "x") == -3


def test_floor_rooftop_is_99_whatever_the_number():
    """★ 실측 14행뿐이라 놓치기 쉬운 값. 옥탑은 몇 층이든 99 다."""
    assert L.parse_floor("옥탑층", "1", "x") == L.ROOFTOP_FLOOR == 99
    assert L.parse_floor("옥탑층", "2", "x") == 99


def test_floor_unknown_kind_stops_instead_of_null():
    """★ 흘려보내면 그 행은 어느 층에도 안 쌓이는데 행 수는 맞아 아무도 못 찾는다."""
    with pytest.raises(ValueError) as e:
        L.parse_floor("중층", "1", "시트 1 5행")
    assert "시트 1 5행" in str(e.value)
    assert "옥탑층" in str(e.value)          # 아는 값을 알려 준다


def test_floor_zero_is_refused():
    with pytest.raises(ValueError) as e:
        L.parse_floor("지상층", "0", "x")
    assert "0" in str(e.value)


def test_floor_negative_address_is_refused_not_double_negated():
    """지하층 + '-1' 을 곱하면 +1 이 된다 — 조용히 지상으로 둔갑하는 것을 막는다."""
    with pytest.raises(ValueError):
        L.parse_floor("지하층", "-1", "x")


def test_floor_blank_and_non_integer_are_refused():
    with pytest.raises(ValueError):
        L.parse_floor("지상층", "", "x")
    with pytest.raises(ValueError):
        L.parse_floor("지상층", "1층", "x")


# ── 3. ★ 광주·전남 재코딩 ────────────────────────────────────────────────────


def test_remap_gwangju_and_jeonnam():
    """실증된 대응(bjd_code 실측): 시군구 코드만 바뀌고 읍면동은 그대로."""
    assert L.remap_bjd_code("2911010100", "x") == "1221010100"   # 광주 동구 대인동
    assert L.remap_bjd_code("4611010100", "x") == "1211010100"   # 전남 목포시 용당동


def test_remap_leaves_other_sido_alone():
    assert L.remap_bjd_code("1123010600", "x") == "1123010600"
    assert L.remap_bjd_code("3020010100", "x") == "3020010100"


def test_remap_unknown_sigungu_stops():
    """★ 조용히 두면 그 행들이 어느 필지에도 안 붙는데 행 수는 맞다."""
    with pytest.raises(ValueError) as e:
        L.remap_bjd_code("2999010100", "시트 3 7행")
    assert "시트 3 7행" in str(e.value)
    assert "BJD_SIGUNGU_REMAP" in str(e.value)


def test_remap_rejects_malformed_code():
    for bad in ("", "112301060", "11230106000", "11230106ab"):
        with pytest.raises(ValueError):
            L.remap_bjd_code(bad, "x")


def test_remap_table_is_one_to_one_and_targets_the_merged_sido():
    """표 자체의 모양을 지킨다 — 두 옛 시군구가 한 새 코드로 뭉개지면 조용한 오염이다."""
    assert len(L.BJD_SIGUNGU_REMAP) == 27
    assert len(set(L.BJD_SIGUNGU_REMAP.values())) == 27
    assert all(k[:2] in L.REMAP_SIDO for k in L.BJD_SIGUNGU_REMAP)
    assert all(v.startswith("12") and len(v) == 5 for v in L.BJD_SIGUNGU_REMAP.values())


# ── 4. PNU 조립 ──────────────────────────────────────────────────────────────


def test_pnu_general_jibun():
    assert L.assemble_pnu("1123010600", "일반지번", "0431", "0005", "x") == \
        "1123010600" + "1" + "0431" + "0005"


def test_pnu_mountain_gets_land_code_2():
    got = L.assemble_pnu("1123010600", "산", "0431", "0005", "x")
    assert got[10] == "2"


def test_pnu_provisional_jibun_is_none_not_an_error():
    """★ '가,확정예정지번' 11,008행 — 조립 불가가 **정상**이고 행은 버리지 않는다."""
    assert L.assemble_pnu("1123010600", "가,확정예정지번", "0431", "0005", "x") is None


def test_pnu_pads_short_numbers():
    assert L.assemble_pnu("1123010600", "일반지번", "7", "0", "x").endswith("00070000")


def test_pnu_applies_the_gwangju_remap():
    """★ 재코딩이 PNU 에 실제로 반영돼야 한다 — 아니면 68,021행이 조용히 안 붙는다."""
    assert L.assemble_pnu("2911010100", "일반지번", "0001", "0000", "x").startswith("1221010100")


def test_pnu_unknown_special_code_stops():
    with pytest.raises(ValueError) as e:
        L.assemble_pnu("1123010600", "블록지번", "0431", "0005", "시트 2 9행")
    assert "시트 2 9행" in str(e.value)


def test_pnu_refuses_oversized_or_non_numeric_bunji():
    with pytest.raises(ValueError):
        L.assemble_pnu("1123010600", "일반지번", "04311", "0005", "x")
    with pytest.raises(ValueError):
        L.assemble_pnu("1123010600", "일반지번", "43-1", "0005", "x")


# ── 5. record_to_row ─────────────────────────────────────────────────────────


def test_record_to_row_reads_every_column():
    r = L.record_to_row(rec(), "x")
    assert r["pnu"] == "1123010600104310005"
    assert r["bld_nm"] == "신부파스칼텔"
    assert r["dong_nm"] == "1(단일)"
    assert r["floor_no"] == 1
    assert r["ho"] == "101"
    assert r["area_m2"] == 28.0
    assert r["common_area_m2"] == 7.66
    assert r["price_per_m2"] == 2905000.0
    assert r["kind"] == "상가"
    assert r["notice_date"] == "2026-01-01"


def test_record_to_row_keeps_the_original_bjd_code():
    """★ pnu 는 재코딩된 값이지만 bjd_code_orig 는 **원본 그대로**여야 한다.

    원본을 잃으면 "우리가 바꾼 것"과 "원래 그랬던 것"을 다시 못 가린다.
    """
    r = L.record_to_row(rec(법정동코드="2911010100", 번지="0001", 호="0000"), "x")
    assert r["bjd_code_orig"] == "2911010100"
    assert r["pnu"].startswith("1221010100")


def test_record_to_row_blank_ho_becomes_none():
    """실측 22행이 비어 있다. 빈 문자열이 아니라 NULL 로 들어가야 한다."""
    assert L.record_to_row(rec(상가건물호주소=""), "x")["ho"] is None


def test_record_to_row_refuses_blank_kind():
    with pytest.raises(ValueError):
        L.record_to_row(rec(상가종류코드=""), "x")


def test_record_to_row_refuses_non_numeric_price():
    with pytest.raises(ValueError) as e:
        L.record_to_row(rec(고시가격="2,905,000"), "시트 1 3행")
    assert "고시가격" in str(e.value)


def test_notice_date_format():
    assert L.parse_notice_date("20260101", "x") == "2026-01-01"
    for bad in ("2026-01-01", "202601", ""):
        with pytest.raises(ValueError):
            L.parse_notice_date(bad, "x")


# ── 6. iter_records ──────────────────────────────────────────────────────────


def test_iter_records_walks_every_sheet_with_its_own_header():
    """시트가 5장이고 장마다 머리글이 따로 있다."""
    sheets = [("1", [tuple(HEADER), row_of(rec())]),
              ("2", [tuple(HEADER), row_of(rec(상가건물호주소="201"))])]
    got = list(L.iter_records(sheets))
    assert [w for w, _ in got] == ["시트 1 2행", "시트 2 2행"]
    assert got[1][1]["상가건물호주소"] == "201"


def test_iter_records_skips_blank_tail_rows():
    sheets = [("1", [tuple(HEADER), row_of(rec()), (None,) * len(HEADER), ("", "")])]
    assert len(list(L.iter_records(sheets))) == 1


def test_iter_records_reads_by_name_not_position():
    """열 순서가 바뀌어도 이름으로 읽어야 한다 — 위치로 읽으면 값이 옆 칸으로 들어간다."""
    shuffled = HEADER[::-1]
    d = rec(상가건물호주소="777")
    sheets = [("1", [tuple(shuffled), tuple(d[c] for c in shuffled)])]
    (_, got), = L.iter_records(sheets)
    assert got["상가건물호주소"] == "777"
    assert got["법정동코드"] == "1123010600"


def test_iter_records_stops_on_a_changed_header():
    sheets = [("1", [tuple(HEADER[:-1]), row_of(rec())])]
    with pytest.raises(ValueError) as e:
        list(L.iter_records(sheets))
    assert "공유면적" in str(e.value)


def test_iter_records_stops_on_an_empty_sheet():
    with pytest.raises(ValueError):
        list(L.iter_records([("1", [])]))


# ── 7. ★ 관문 4종 — 통과와 차단을 함께 본다 ──────────────────────────────────


def stats_from(records):
    s = L.Stats()
    for i, d in enumerate(records, start=2):
        s.add(d, L.record_to_row(d, "시트 1 {}행".format(i)))
    return s


def test_gates_pass_on_a_healthy_sample():
    assert L.assert_gates(stats_from([rec() for _ in range(10)])) is True


def test_gate_refuses_zero_rows():
    with pytest.raises(ValueError) as e:
        L.assert_gates(L.Stats())
    assert "0" in str(e.value)


def test_gate_refuses_a_low_pnu_assembly_rate():
    """조립률 관문에 **판별력이 있는지** — 억지로 낮춰 보고 걸리는지 본다."""
    s = stats_from([rec() for _ in range(10)])
    s.pnu_ok, s.pnu_blocked = 5, 0          # 절반만 조립된 것처럼
    with pytest.raises(ValueError) as e:
        L.assert_gates(s)
    assert "조립률" in str(e.value)


def test_provisional_jibun_does_not_drag_the_assembly_rate_down():
    """★ '가지번'은 조립 불가가 정상이라 분모에서 빠져야 한다 — 아니면 정상 자료가 막힌다."""
    s = stats_from([rec()] + [rec(특수지코드="가,확정예정지번") for _ in range(9)])
    assert s.pnu_blocked == 9
    assert L.assert_gates(s) is True


def test_gate_refuses_prices_that_look_like_totals():
    """★ 단위 검증. 고시가격이 총액으로 바뀌면 중앙값이 상식 범위를 벗어난다."""
    s = stats_from([rec(고시가격="850000000") for _ in range(5)])
    with pytest.raises(ValueError) as e:
        L.assert_gates(s)
    assert "중앙값" in str(e.value)


def test_gate_refuses_zero_floor_even_if_parse_floor_were_loosened():
    """parse_floor 를 나중에 누가 고쳐도 두 번째 눈이 남아 있어야 한다."""
    s = stats_from([rec() for _ in range(3)])
    s.floor_zero = 1
    with pytest.raises(ValueError) as e:
        L.assert_gates(s)
    assert "절대 규칙 4" in str(e.value)


def test_stats_counts_kinds_floors_and_remaps():
    s = stats_from([rec(), rec(상가종류코드="오피스텔", 건물층구분코드="지하층"),
                    rec(법정동코드="4611010100", 번지="0001", 호="0000")])
    assert s.by_kind == {"상가": 2, "오피스텔": 1}
    assert s.by_floor_kind == {"지상층": 2, "지하층": 1}
    assert s.remapped == 1
    assert s.remapped_codes == {"1211010100"}
    assert s.by_sido["11"] == 2 and s.by_sido["46"] == 1
    assert s.notice_dates == {"2026-01-01": 3}


def test_totals_include_common_area():
    """총액은 전용면적만이 아니라 (전용 + 공유)로 잰다 — 안 그러면 공용부만큼 적게 나온다."""
    s = stats_from([rec(고시가격="1000000", 전용면적="10", 공유면적="5")])
    assert s.totals == [15_000_000.0]


def test_percentile_handles_empty_and_edges():
    assert L.percentile([], 0.5) is None
    assert L.percentile([1, 2, 3, 4], 0.5) == 3
    assert L.percentile([1, 2, 3, 4], 0.99) == 4


# ── 8. build_sql ─────────────────────────────────────────────────────────────


def sql_of(**over):
    kw = {"csv_path": r"D:\sangga\data\staging\x.csv",
          "notice_dates": {"2026-01-01": 3},
          "expected_rows": 3}
    kw.update(over)
    return L.build_sql(**kw)


def test_sql_is_one_transaction():
    sql = sql_of()
    assert sql.startswith("begin;")
    assert sql.rstrip().endswith("commit;")


def test_sql_copy_columns_match_the_csv_writer():
    """★ 둘이 어긋나면 값이 옆 칸으로 들어가는데 에러가 안 난다."""
    sql = sql_of()
    assert "\\copy nts_base_price ({})".format(", ".join(L.CSV_COLUMNS)) in sql


def test_sql_path_uses_forward_slashes():
    """psql 에 윈도우 역슬래시를 그대로 주면 이스케이프로 먹힌다."""
    assert "'D:/sangga/data/staging/x.csv'" in sql_of()
    assert r"D:\sangga" not in sql_of()


def test_sql_deletes_the_same_notice_date_first():
    """연 1회 재적재를 여러 번 돌려도 겹치지 않아야 한다."""
    sql = sql_of()
    assert "delete from nts_base_price where notice_date in ('2026-01-01'::date);" in sql


def test_sql_gates_raise_instead_of_merely_counting():
    """★ psql 은 select 가 몇 줄을 돌려주든 종료코드 0 이다 — 세기만 하면 그대로 commit 된다."""
    sql = sql_of()
    assert sql.count("raise exception") == 3
    assert "cnt <> 3" in sql                     # 행수 대조
    assert "floor_no = 0" in sql                 # 층
    assert "from bjd_code b" in sql              # 재코딩이 실재하는 법정동을 가리키나


def test_sql_parcel_coverage_is_information_not_a_gate():
    """우리 필지 적재 범위는 이 자료의 결함이 아니다 — 막으면 정상 적재가 통째로 실패한다."""
    sql = sql_of()
    head, _, tail = sql.partition("우리 필지에 붙는 행")
    assert "raise exception" not in tail
    assert "from parcel p" in sql


def test_sql_refuses_when_no_notice_date_was_read():
    with pytest.raises(ValueError):
        sql_of(notice_dates={})


# ── 9. transform ─────────────────────────────────────────────────────────────


def read_csv_rows(path):
    with io.open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def test_transform_writes_columns_in_the_copy_order(tmp_path):
    out = str(tmp_path / "o.csv")
    sheets = [("1", [tuple(HEADER), row_of(rec())])]
    stats, written = L.transform(sheets, out)
    assert written == 1 and stats.total == 1
    (row,) = read_csv_rows(out)
    assert len(row) == len(L.CSV_COLUMNS)
    assert row[L.CSV_COLUMNS.index("pnu")] == "1123010600104310005"
    assert row[L.CSV_COLUMNS.index("floor_no")] == "1"
    assert row[L.CSV_COLUMNS.index("kind")] == "상가"
    assert row[L.CSV_COLUMNS.index("notice_date")] == "2026-01-01"


def test_transform_writes_empty_for_null_pnu(tmp_path):
    """'가지번' 행은 pnu 칸이 비어 COPY 가 NULL 로 읽는다 — 행 자체는 남는다."""
    out = str(tmp_path / "o.csv")
    sheets = [("1", [tuple(HEADER), row_of(rec(특수지코드="가,확정예정지번"))])]
    L.transform(sheets, out)
    (row,) = read_csv_rows(out)
    assert row[L.CSV_COLUMNS.index("pnu")] == ""
    assert row[L.CSV_COLUMNS.index("bjd_code_orig")] == "1123010600"


def test_transform_limit_stops_early(tmp_path):
    out = str(tmp_path / "o.csv")
    sheets = [("1", [tuple(HEADER)] + [row_of(rec()) for _ in range(5)])]
    _, written = L.transform(sheets, out, limit=2)
    assert written == 2
    assert len(read_csv_rows(out)) == 2


def test_transform_stops_on_a_bad_row_instead_of_skipping_it(tmp_path):
    """나머지를 넣고 "성공"이라 말하면 빠진 호실을 아무도 못 찾는다."""
    out = str(tmp_path / "o.csv")
    sheets = [("1", [tuple(HEADER), row_of(rec()), row_of(rec(건물층구분코드="중층"))])]
    with pytest.raises(ValueError):
        L.transform(sheets, out)
