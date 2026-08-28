# -*- coding: utf-8 -*-
"""scripts/collectors/load_arch_permits.py 단위 테스트 (DB·네트워크 없음).

여기서 막는 것은 **에러 없이 조용히 틀리는** 종류의 실수다:
  1. 열 순서가 밀려 값이 옆 칸으로 들어가는 것
  2. 날짜를 글자로 비교해 1990년대 쓰레기 행이 "최근 허가"로 딸려 오는 것
  3. 대지구분 코드를 그대로 붙여 PNU 가 통째로 남의 필지를 가리키는 것
  4. 사용승인이 난 건물이 "곧 올라온다"고 화면에 뜨는 것
  5. CSV 열 순서와 `\\copy` 열 목록이 어긋나 값이 한 칸씩 밀리는 것
"""

import datetime
import io
import os
import sys

import pytest

_COLLECTORS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "collectors",
)
_SCRIPTS_DIR = os.path.dirname(_COLLECTORS_DIR)
for _p in (_SCRIPTS_DIR, _COLLECTORS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import convert_bldrgst_bulk as bulk  # noqa: E402
import load_arch_permits as target  # noqa: E402


# ── 픽스처 ────────────────────────────────────────────────────────────────────

# 2026-07 판 실제 첫 줄들의 모양(41칸 · `|` 구분 · 머리글 없음).
REAL_LINE = (
    "1000000000000000252035|서울특별시 강남구 대치동 900-16번지|대치빌딩|11680|10600|0|0900|0016|"
    "|||대|제3종일반주거지역|||08|UQA113|||0100|신축|"
    "264.7|132.16|49.92|1274.57|199.4|75.33|1|0|"
    "04000|제2종근린생활시설|0|0|1|4|"
    "||20230405|20230317|20240610|20260107"
)


def line_of(**over):
    """REAL_LINE 을 바탕으로 칸 몇 개만 바꾼 줄을 만든다."""
    cells = REAL_LINE.split("|")
    for name, value in over.items():
        cells[target.PERMIT_COLS.index(name)] = value
    return "|".join(cells)


def item_of(**over):
    return target.make_item(line_of(**over).split("|"))


# ── 1. 열 구성 ────────────────────────────────────────────────────────────────


class TestColumns:
    def test_the_file_has_fortyone_columns(self):
        """건축HUB 설명 팝업(opnTaskCd=0101)의 colSn 개수와 같아야 한다."""
        assert len(target.PERMIT_COLS) == 41
        assert len(REAL_LINE.split("|")) == 41

    def test_no_column_name_is_repeated(self):
        """같은 이름이 두 번 있으면 뒤엣것이 앞엣것을 덮어 한 칸이 통째로 사라진다."""
        assert len(set(target.PERMIT_COLS)) == len(target.PERMIT_COLS)

    def test_the_key_columns_sit_where_we_think(self):
        """⛔ 여기가 틀리면 모든 판단이 엉뚱한 칸을 본다 — 실제 줄로 못 박아 둔다."""
        it = target.make_item(REAL_LINE.split("|"))
        assert it["mgmPmsrgstPk"] == "1000000000000000252035"
        assert it["sigunguCd"] == "11680"
        assert it["mainPurpsCd"] == "04000"
        assert it["mainPurpsCdNm"] == "제2종근린생활시설"
        assert it["totArea"] == "1274.57"
        assert it["archPmsDay"] == "20230317"
        assert it["realStcnsDay"] == "20230405"
        assert it["useAprDay"] == "20240610"
        assert it["crtnDay"] == "20260107"

    def test_pnu_fields_are_named_like_the_ledger_converter(self):
        """PNU 조립을 사본 없이 그대로 물려받으려면 이름이 같아야 한다."""
        for name in bulk.PNU_PARTS:
            assert name in target.PERMIT_COLS

    def test_wrong_column_count_is_rejected(self):
        assert target.make_item(["a", "b"]) is None
        assert target.make_item(REAL_LINE.split("|") + ["extra"]) is None

    def test_values_are_stripped(self):
        it = target.make_item((REAL_LINE + " ").replace("|서울", "|  서울").split("|"))
        assert it["platPlc"].startswith("서울")


# ── 2. 날짜 읽기 ──────────────────────────────────────────────────────────────


class TestParseDay:
    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_blank(self, raw):
        assert target.parse_day(raw) == (None, "blank")

    def test_ok(self):
        assert target.parse_day("20230317") == (datetime.date(2023, 3, 17), "ok")

    @pytest.mark.parametrize("raw", [
        "1999", "1995 530", "199301", "2001 4 6", "97  ", "2026-01-01", "abcdefgh",
    ])
    def test_bad_shapes_seen_in_the_real_file(self, raw):
        """원본에 실제로 들어 있는 모양들이다(2026-07 판 실측)."""
        assert target.parse_day(raw)[1] == "bad"

    def test_calendar_impossible_day_is_bad(self):
        """⛔ 20230230 은 자릿수는 맞다 — 여기서 안 걸면 \\copy 가 통째로 실패한다."""
        assert target.parse_day("20230230")[1] == "bad"


# ── 3. 무엇을 담을 것인가 ─────────────────────────────────────────────────────


class TestIsTarget:
    def test_not_approved_and_recent_is_kept(self):
        ok, reason = target.is_target(item_of(useAprDay="", archPmsDay="20230317"))
        assert (ok, reason) == (True, None)

    def test_already_approved_is_skipped(self):
        assert target.is_target(item_of(useAprDay="20240101"))[1] == "use_approved"

    def test_approved_with_a_broken_date_is_still_skipped(self):
        """⛔ '지어졌는데 날짜를 모른다'와 '아직 안 지어졌다'는 다른 말이다.

        뭉개면 이미 다 지은 건물이 "곧 올라온다"고 화면에 뜬다.
        """
        assert target.is_target(item_of(useAprDay="2000"))[1] == "use_approved"

    def test_old_permit_is_skipped(self):
        assert target.is_target(
            item_of(useAprDay="", archPmsDay="20221231"))[1] == "permit_day_old"

    def test_blank_permit_day_is_skipped(self):
        assert target.is_target(item_of(useAprDay="", archPmsDay=""))[1] == "permit_day_old"

    @pytest.mark.parametrize("junk", ["9902", "9830", "97  ", "621"])
    def test_junk_permit_day_does_not_sneak_in_as_recent(self, junk):
        """⛔ 글자로 비교하면 `'9902' >= '20230101'` 이 참이라 1990년대 행이 딸려 온다.

        실측: 글자 비교로 세면 24행이 더 붙었다. 날짜로 바꿔 본 뒤 비교해야 한다.
        """
        assert junk >= "20230101"          # 글자로는 '최근'이다 (함정 재현)
        ok, reason = target.is_target(item_of(useAprDay="", archPmsDay=junk))
        assert (ok, reason) == (False, "permit_day_bad")

    def test_the_boundary_day_itself_is_kept(self):
        assert target.is_target(item_of(useAprDay="", archPmsDay="20230101"))[0] is True


# ── 4. PNU 조립 (대장 변환기의 매핑을 그대로 쓴다) ────────────────────────────


class TestPnu:
    def test_uses_the_shared_mapping_not_a_copy(self):
        """⛔ 사본을 만들면 언젠가 한쪽만 고쳐진다 — 빌려 쓰는 것이지 베낀 것이 아니어야 한다."""
        assert target.make_pnu is bulk.make_pnu
        assert target.PLAT_GB_BLOCK is bulk.PLAT_GB_BLOCK
        # 자기 몫의 대지구분 표를 따로 들고 있으면 안 된다(그 순간 둘로 갈라진다).
        assert not hasattr(target, "PLAT_GB_TO_PNU")

    def test_daeji_becomes_one(self):
        """파일의 '0'(대지)은 PNU 에서 '1' 이다 — 그대로 붙이면 남의 필지를 가리킨다."""
        pnu = target.make_row(item_of(platGbCd="0"), "202607")["pnu"]
        assert pnu == "1168010600" + "1" + "0900" + "0016"
        assert len(pnu) == 19

    def test_san_becomes_two(self):
        assert target.make_row(item_of(platGbCd="1"), "202607")["pnu"][10] == "2"

    @pytest.mark.parametrize("gb", ["2", "", "3", "5"])
    def test_unknown_land_kinds_leave_pnu_empty_instead_of_guessing(self, gb):
        """실측 분포에 '2'(블록·특수지번)·빈값·'3'·'5' 가 있다. 지어내지 않고 비운다."""
        assert target.make_row(item_of(platGbCd=gb), "202607")["pnu"] is None


# ── 5. 한 줄 → 적재용 값 ─────────────────────────────────────────────────────


class TestMakeRow:
    def test_dates_become_iso(self):
        row = target.make_row(item_of(useAprDay=""), "202607")
        assert row["arch_pms_day"] == "2023-03-17"
        assert row["real_stcns_day"] == "2023-04-05"
        assert row["use_apr_day"] is None
        assert row["crtn_day"] == "2026-01-07"

    def test_broken_dates_become_null_not_garbage(self):
        row = target.make_row(item_of(realStcnsDay="1999"), "202607")
        assert row["real_stcns_day"] is None      # 관문 ③ 이 이 행을 따로 잡는다

    def test_area_and_names(self):
        row = target.make_row(item_of(), "202607")
        assert row["tot_area"] == 1274.57
        assert row["arch_gb_nm"] == "신축"
        assert row["main_purps_cd"] == "04000"
        assert row["sigungu_cd"] == "11680"
        assert row["loaded_ym"] == "202607"

    def test_empty_strings_become_null(self):
        row = target.make_row(item_of(mainPurpsCd="", totArea=""), "202607")
        assert row["main_purps_cd"] is None
        assert row["tot_area"] is None

    def test_every_csv_column_is_produced(self):
        """⛔ 빠진 칸이 있으면 transform 이 KeyError 로 죽는다(적재 도중이 아니라 여기서 잡는다)."""
        row = target.make_row(item_of(), "202607")
        assert set(row) == set(target.CSV_COLUMNS)


# ── 6. 기준월 ─────────────────────────────────────────────────────────────────


class TestLoadedYm:
    def test_read_from_the_folder_name(self):
        assert target.loaded_ym_of(os.path.join("data", "raw", "arch_permit",
                                                "202607", "x.zip")) == "202607"

    @pytest.mark.parametrize("folder", ["arch_permit", "2026-07", "20260"])
    def test_refuses_a_folder_that_is_not_a_month(self, folder):
        with pytest.raises(ValueError):
            target.loaded_ym_of(os.path.join("data", folder, "x.zip"))


class TestMonthEnd:
    @pytest.mark.parametrize("ym,expected", [
        ("202607", datetime.date(2026, 7, 31)),
        ("202602", datetime.date(2026, 2, 28)),   # 평년
        ("202402", datetime.date(2024, 2, 29)),   # 윤년
        ("202612", datetime.date(2026, 12, 31)),  # 12월은 다음 달 계산이 다르다
    ])
    def test_last_day_of_the_month(self, ym, expected):
        assert target.month_end(ym) == expected

    def test_uses_the_file_not_today(self):
        """⛔ '오늘'로 재면 돌리는 날마다 같은 파일에서 다른 리포트가 나온다."""
        assert target.month_end("202607") < datetime.date.today()
        with pytest.raises(ValueError):
            target.month_end("2026-07")


class TestFuturePermitDays:
    def test_typo_dates_are_reported_but_not_dropped(self, tmp_path):
        """3000-01-01 같은 허가일이 71행 있다(실측). 날짜만 오타일 뿐 **실재하는 미준공
        허가**라 버리면 진짜 건물이 사라진다 — 담되 몇 행인지 보여 준다."""
        lines = [line_of(useAprDay="", archPmsDay="30000101"),
                 line_of(useAprDay="", archPmsDay="20230317")]
        stats, written, _ = stats_from(lines, tmp_path)
        assert written == 2                       # 버리지 않았다
        assert stats.future_permit == 1
        assert "기준월 이후 허가일 1행" in target.format_report(stats)
        assert target.assert_gates(stats) is True  # 막지는 않는다

    def test_a_normal_batch_says_nothing_about_it(self, tmp_path):
        stats, _, _ = stats_from([line_of(useAprDay="")], tmp_path)
        assert stats.future_permit == 0
        assert "기준월 이후" not in target.format_report(stats)


# ── 7. 관문 ───────────────────────────────────────────────────────────────────


def stats_from(lines, tmp_path, ym="202607"):
    out = str(tmp_path / "out.csv")
    return target.transform(lines, out, ym) + (out,)


class TestGates:
    def test_a_clean_batch_passes(self, tmp_path):
        stats, written, _ = stats_from([line_of(useAprDay="")] * 3, tmp_path)
        assert written == 3
        assert target.assert_gates(stats) is True

    def test_zero_rows_is_a_format_change(self, tmp_path):
        stats, _, _ = stats_from([], tmp_path)
        with pytest.raises(ValueError, match="0"):
            target.assert_gates(stats)

    def test_nothing_kept_is_a_format_change(self, tmp_path):
        """열이 밀리면 사용승인일 칸이 엉뚱한 값이 되어 통과 행이 0 이 된다."""
        stats, written, _ = stats_from([line_of(useAprDay="20240101")] * 5, tmp_path)
        assert written == 0
        with pytest.raises(ValueError, match="담을 행이 0"):
            target.assert_gates(stats)

    def test_column_count_change_stops_the_load(self, tmp_path):
        lines = [line_of(useAprDay="")] * 3 + [REAL_LINE + "|extra"]
        stats, _, _ = stats_from(lines, tmp_path)
        assert stats.col_mismatch == 1
        with pytest.raises(ValueError, match="칸 수"):
            target.assert_gates(stats)

    def test_a_broken_date_inside_the_batch_stops_the_load(self, tmp_path):
        """범위 밖 행의 쓰레기 날짜는 봐주지만, **담기로 한 행 안**은 봐주지 않는다."""
        stats, _, _ = stats_from(
            [line_of(useAprDay="", realStcnsDay="1995 530")], tmp_path)
        assert dict(stats.bad_days) == {"realStcnsDay": 1}
        with pytest.raises(ValueError, match="날짜 형식이 이상"):
            target.assert_gates(stats)

    def test_a_broken_area_stops_the_load(self, tmp_path):
        stats, _, _ = stats_from([line_of(useAprDay="", totArea="약 300")], tmp_path)
        with pytest.raises(ValueError, match="연면적"):
            target.assert_gates(stats)

    def test_low_pnu_assembly_rate_stops_the_load(self, tmp_path):
        """대지구분 체계가 바뀌면 조립률이 무너진다 — 그때 조용히 넣으면 안 된다."""
        lines = [line_of(useAprDay="", platGbCd="9")] * 10 + [line_of(useAprDay="")]
        stats, _, _ = stats_from(lines, tmp_path)
        assert stats.pnu_rate < target.MIN_PNU_ASSEMBLY_RATE
        with pytest.raises(ValueError, match="조립률"):
            target.assert_gates(stats)

    def test_block_jibun_does_not_count_against_the_rate(self, tmp_path):
        """블록·특수지번은 지번이 없어 조립 불가가 **정상**이다(분모에서 뺀다)."""
        lines = [line_of(useAprDay="", platGbCd=bulk.PLAT_GB_BLOCK)] * 10 + [
            line_of(useAprDay="")]
        stats, _, _ = stats_from(lines, tmp_path)
        assert stats.pnu_block == 10
        assert stats.pnu_rate == 1.0
        assert target.assert_gates(stats) is True


# ── 8. 훑어 읽기 전체 ─────────────────────────────────────────────────────────


class TestTransform:
    def test_counts_every_reason_separately(self, tmp_path):
        lines = [
            line_of(useAprDay="", archPmsDay="20230317"),   # 담는다
            line_of(useAprDay="20240101"),                  # 이미 지어짐
            line_of(useAprDay="", archPmsDay="9902"),       # 허가일 형식 이상
            line_of(useAprDay="", archPmsDay="20220101"),   # 옛 허가
            "",                                             # 빈 줄
        ]
        stats, written, _ = stats_from(lines, tmp_path)
        assert written == 1
        assert stats.rows == 5
        assert dict(stats.skipped) == {
            "use_approved": 1, "permit_day_bad": 1, "permit_day_old": 1}

    def test_csv_row_order_matches_the_copy_column_list(self, tmp_path):
        """⛔ 여기가 어긋나면 값이 한 칸씩 밀려 들어간다 — 에러 없이."""
        _, _, out = stats_from([line_of(useAprDay="")], tmp_path)
        with io.open(out, encoding="utf-8") as f:
            cells = f.read().rstrip("\n").split(",")
        got = dict(zip(target.CSV_COLUMNS, cells))
        assert got["mgm_pmsrgst_pk"] == "1000000000000000252035"
        assert got["pnu"] == "1168010600109000016"
        assert got["arch_pms_day"] == "2023-03-17"
        assert got["loaded_ym"] == "202607"
        assert got["use_apr_day"] == ""          # 빈 칸 = \copy 에서 NULL

    def test_counts_started_buildings(self, tmp_path):
        lines = [line_of(useAprDay="", realStcnsDay="20230405"),
                 line_of(useAprDay="", realStcnsDay="")]
        stats, _, _ = stats_from(lines, tmp_path)
        assert stats.kept == 2
        assert stats.started == 1

    def test_report_shows_the_source_total_not_just_the_kept_rows(self, tmp_path):
        """⛔ 통과 행수만 보여 주면 원본이 반쯤 잘려도 그럴듯해 보인다."""
        stats, _, _ = stats_from(
            [line_of(useAprDay="")] + [line_of(useAprDay="20240101")] * 4, tmp_path)
        report = target.format_report(stats)
        assert "원본 전체" in report and "5행" in report
        assert "적재 대상" in report


# ── 9. 적재 SQL ───────────────────────────────────────────────────────────────


class TestBuildSql:
    @pytest.fixture
    def sql(self):
        return target.build_sql("/tmp/arch_permit.csv", "202607", 556527)

    def test_one_transaction(self, sql):
        assert sql.lstrip().startswith("begin;")
        assert sql.rstrip().endswith("vacuum (analyze) arch_permit;")
        assert "commit;" in sql

    def test_reload_deletes_only_that_month(self, sql):
        """⛔ 달 전체를 지우면 지난달 자료가 사라지고, 안 지우면 PK 충돌로 통째로 실패한다."""
        assert "delete from arch_permit where loaded_ym = '202607';" in sql
        assert "delete from arch_permit;" not in sql
        assert "truncate" not in sql.lower()

    def test_copy_column_list_matches_the_csv(self, sql):
        assert "\\copy arch_permit ({})".format(", ".join(target.CSV_COLUMNS)) in sql

    def test_gates_raise_instead_of_just_printing(self, sql):
        """⛔ psql 은 select 가 몇 줄을 돌려주든 종료코드 0 이다 — 세어서 보여 주기만 하면
        그대로 commit 된다. 관문은 반드시 예외를 던져야 한다."""
        assert sql.count("raise exception") == 2
        assert "count(*) into cnt from arch_permit where loaded_ym = '202607';" in sql
        assert "use_apr_day is not null" in sql

    def test_row_count_is_checked_against_the_source(self, sql):
        assert "556527" in sql

    def test_windows_path_is_rewritten_for_psql(self):
        got = target.build_sql("D:\\sangga\\data\\staging\\a.csv", "202607", 1)
        assert "D:/sangga/data/staging/a.csv" in got

    @pytest.mark.parametrize("ym", ["2026-07", "20260", "abcdef", ""])
    def test_refuses_a_bad_month(self, ym):
        with pytest.raises(ValueError):
            target.build_sql("/tmp/a.csv", ym, 1)

    def test_refuses_an_empty_batch(self):
        with pytest.raises(ValueError):
            target.build_sql("/tmp/a.csv", "202607", 0)
