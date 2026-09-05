# -*- coding: utf-8 -*-
"""scripts/build_scorecard_json.py 1:1 단위 테스트.

여기서 지키는 것은 **에러 없이 화면만 반쪽이 되는** 종류다:
  1) BOM 을 못 걷어 첫 칸 이름이 `\\ufeff단계` 가 됨 → "칸이 없습니다"로 굽기가 통째로 실패
  2) 빈 칸(`no_estimate` 의 MdAPE)을 0 으로 메움 → "오차 0%"라는 정반대의 뜻이 된다
  3) 운영모드 표에서 '채택단계' 줄이 사라짐 → 화면의 단계 분포가 **조용히** 빈다
  4) 표에 없는 칸이 새어 들어옴 → 개별 거래가 공개 파일로 나가는 길이 열린다
  5) `--dry-run` 인데 파일을 씀 → 미리보기라는 말이 거짓이 된다
  6) `generated_at` 이 구운 시각이 됨 → 자료가 그대로인데 다시 구울 때마다 git diff

DB 없이 돈다 — 전부 순수 함수만 본다(tests/test_build_district_geojson.py 와 같은 방식).
"""

import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_scorecard_json as bsj  # noqa: E402

BOM = "﻿"

STAGE_CSV_TEXT = (
    "단계,축,축값,축값이름,검증거래수,추정성립수,커버리지,MdAPE,MAPE,적중률20\n"
    "L2,전체,전체,전체,2986,848,0.283992,0.132748,0.33529,0.629717\n"
    "L6,구,11680,강남구,262,240,0.916,0.28,0.4,0.38\n"
)

OPS_CSV_TEXT = (
    "구분,축값,축값이름,검증거래수,추정성립수,커버리지,MdAPE,MAPE,적중률20\n"
    "전체,전체,전체,2986,2791,0.934695,0.29056,0.501468,0.389824\n"
    "채택단계,L6,L6,1596,1596,1.0,0.402497,0.570269,0.289474\n"
    # ⚠️ 빈 칸이 **정상인** 줄이다 — 추정을 아예 못 낸 거래에는 오차가 없다.
    "채택단계,no_estimate,no_estimate,195,0,0.0,,,\n"
)

GATE_CSV_TEXT = (
    "sigungu_code,sigungu_nm,n_paired,ladder_mdape,base_mdape,gate_pass\n"
    "11680,강남구,262,0.283166,0.491653,true\n"
    "11545,금천구,99,0.259708,0.175917,false\n"
)

DOC_TEXT = "# 성적표 v1\n\n> 생성: 2026-08-15 23:44 (KST) · 스크립트: backtest_price.py\n"


def write_fixture_dir(tmp_path):
    """진짜와 같은 이름·같은 BOM 으로 CSV 3종 + 성적표 문서를 깐다."""
    d = tmp_path / "backtest"
    d.mkdir()
    for name, text in (
        (bsj.STAGE_CSV, STAGE_CSV_TEXT),
        (bsj.OPS_CSV, OPS_CSV_TEXT),
        (bsj.GATE_CSV, GATE_CSV_TEXT),
    ):
        with io.open(str(d / name), "w", encoding="utf-8", newline="\n") as f:
            f.write(BOM + text)          # ⚠️ 진짜 파일처럼 BOM 을 달아 둔다
    doc = d / "성적표-v1.md"
    with io.open(str(doc), "w", encoding="utf-8", newline="\n") as f:
        f.write(DOC_TEXT)
    return str(d), str(doc)


@pytest.fixture()
def built(tmp_path):
    d, doc = write_fixture_dir(tmp_path)
    return bsj.build(backtest_dir=d, doc_path=doc)


# ── 1. CSV 읽기 ──────────────────────────────────────────────────────────────


class TestParsing:
    def test_bom_is_stripped_from_the_header(self):
        """⛔ 없으면 첫 칸 이름이 `\\ufeff단계` 가 되어 굽기가 통째로 실패한다.

        이 CSV 들은 엑셀에서 열리라고 BOM 을 달고 쓰였다 — 진짜 파일이 그렇다.
        """
        rows = bsj.parse_csv(BOM + STAGE_CSV_TEXT, bsj.STAGE_COLUMNS)
        assert rows[0]["stage"] == "L2"

    def test_reads_the_same_without_a_bom(self):
        assert bsj.parse_csv(STAGE_CSV_TEXT, bsj.STAGE_COLUMNS) == bsj.parse_csv(
            BOM + STAGE_CSV_TEXT, bsj.STAGE_COLUMNS)

    def test_numbers_become_numbers_and_text_stays_text(self):
        row = bsj.parse_csv(STAGE_CSV_TEXT, bsj.STAGE_COLUMNS)[0]
        assert row["n_verified"] == 2986 and isinstance(row["n_verified"], int)
        assert row["mdape"] == pytest.approx(0.132748)
        assert row["axis_name"] == "전체"

    def test_empty_cells_stay_empty_instead_of_becoming_zero(self):
        """⛔ `no_estimate` 의 오차는 **없는 것**이지 0 이 아니다.

        0 으로 메우면 "추정을 못 낸 거래의 오차가 0%"라는 정반대의 뜻이 된다.
        """
        rows = bsj.parse_csv(OPS_CSV_TEXT, bsj.OPS_COLUMNS)
        none_row = [r for r in rows if r["axis_value"] == "no_estimate"][0]
        assert none_row["mdape"] is None and none_row["mape"] is None
        assert none_row["n_estimated"] == 0        # 이쪽은 진짜 0 이다

    def test_gate_pass_becomes_a_real_boolean(self):
        rows = bsj.parse_csv(GATE_CSV_TEXT, bsj.GATE_COLUMNS)
        assert rows[0]["gate_pass"] is True and rows[1]["gate_pass"] is False

    def test_a_missing_column_is_loud(self):
        """성적표 형식이 바뀌면 조용히 빈 칸을 만들지 않고 멈춘다."""
        with pytest.raises(KeyError):
            bsj.parse_csv("단계,축\nL2,전체\n", bsj.STAGE_COLUMNS)

    def test_extra_columns_are_dropped(self):
        """⛔ 표에 없는 칸은 안 싣는다 — 새 칸이 공개 파일로 조용히 새어 나가지 않게."""
        rows = bsj.parse_csv(
            "sigungu_code,sigungu_nm,n_paired,ladder_mdape,base_mdape,gate_pass,비고\n"
            "11680,강남구,262,0.28,0.49,true,내부메모\n",
            bsj.GATE_COLUMNS,
        )
        assert set(rows[0]) == {j for _, j, _ in bsj.GATE_COLUMNS}


# ── 2. 생성 시각 도장 ────────────────────────────────────────────────────────


class TestGeneratedAt:
    def test_comes_from_the_scorecard_not_from_the_clock(self, built):
        """⛔ **구운 시각이 아니다.** 구운 시각을 적으면 자료가 그대로인데 다시 구울
        때마다 파일이 달라져 git diff 가 매번 지저분해진다."""
        assert built["generated_at"] == "2026-08-15T23:44:00+09:00"

    def test_carries_the_korean_offset(self):
        """시간대를 안 적으면 브라우저가 제 시간대로 읽어 날짜가 하루 밀린다."""
        assert bsj.parse_generated_at(DOC_TEXT).endswith("+09:00")

    def test_a_missing_stamp_stops_the_build(self):
        """⛔ 못 찾았을 때 지금 시각으로 때우면, 화면의 '생성 …' 이 성적과 상관없는
        값이 되고 그 거짓말은 아무 에러도 안 낸다."""
        with pytest.raises(ValueError):
            bsj.parse_generated_at("# 성적표\n\n> 스크립트: backtest_price.py\n")

    def test_building_twice_gives_the_same_bytes(self, tmp_path):
        """자료가 그대로면 다시 구워도 파일이 **한 바이트도** 안 바뀐다."""
        d, doc = write_fixture_dir(tmp_path)
        first = bsj.dumps_compact(bsj.build(backtest_dir=d, doc_path=doc))
        second = bsj.dumps_compact(bsj.build(backtest_dir=d, doc_path=doc))
        assert first == second


# ── 3. 원본 지문 ────────────────────────────────────────────────────────────


class TestSourceHashes:
    def test_every_source_csv_is_stamped(self, built):
        assert set(built["sources"]) == set(bsj.CSV_SOURCES)
        for digest in built["sources"].values():
            assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")

    def test_the_stamp_follows_the_file(self, tmp_path):
        """한 글자만 바뀌어도 지문이 달라져야 '굽는 것을 잊었다'를 나중에 대조할 수 있다."""
        d, doc = write_fixture_dir(tmp_path)
        before = bsj.build(backtest_dir=d, doc_path=doc)["sources"][bsj.GATE_CSV]
        with io.open(os.path.join(d, bsj.GATE_CSV), "a", encoding="utf-8", newline="\n") as f:
            f.write("11110,종로구,91,0.453239,0.398287,false\n")
        after = bsj.build(backtest_dir=d, doc_path=doc)["sources"][bsj.GATE_CSV]
        assert before != after

    def test_the_raw_transaction_file_is_never_read(self):
        """⛔ `검증거래별원자료.csv` 는 개별 실거래(필지·층·단가)다 — 굽는 입력에 없다.

        같은 폴더에 **실제로 있는** 파일이라 "실수로 못 넣었다"가 아니라 "일부러 뺐다"를
        지키는 시험이다. 내보내려면 별건 판단이 필요하다.
        """
        assert os.path.exists(os.path.join(bsj.BACKTEST_DIR, "검증거래별원자료.csv"))
        assert "검증거래별원자료.csv" not in bsj.CSV_SOURCES
        assert "검증거래별원자료.csv" not in bsj.build()["sources"]


# ── 4. 문서 모양 ────────────────────────────────────────────────────────────


class TestDocumentShape:
    def test_has_the_three_blocks_and_the_version(self, built):
        assert built["version"] == "v1"
        assert [r["stage"] for r in built["stages"]] == ["L2", "L6"]
        assert [r["kind"] for r in built["ops_modes"]][0] == "전체"
        assert [r["sigungu_code"] for r in built["gate"]] == ["11680", "11545"]

    def test_check_passes_on_a_good_document(self, built):
        assert bsj.check_document(built) == []

    def test_check_catches_a_missing_adopted_stage_block(self, built):
        """⛔ 이 줄들이 사라지면 화면의 '체감 단계 분포'가 **조용히** 빈다."""
        built["ops_modes"] = [r for r in built["ops_modes"] if r["kind"] != "채택단계"]
        assert any("채택단계" in p for p in bsj.check_document(built))

    def test_check_catches_a_missing_overall_row(self, built):
        """전체 줄이 없으면 커버리지 정직 공지가 사라진다."""
        built["ops_modes"] = [r for r in built["ops_modes"] if r["kind"] != "전체"]
        assert any("전체" in p for p in bsj.check_document(built))

    def test_check_catches_a_leaked_column(self, built):
        """⛔ 표에 없는 칸이 끼면 잡는다 — 개별 거래가 나가는 길은 여기서 막힌다."""
        built["gate"][0]["contract_price"] = 123456789
        assert any("gate" in p for p in bsj.check_document(built))

    def test_check_catches_a_clock_shaped_stamp(self, built):
        built["generated_at"] = "2026-08-15 23:44"
        assert any("generated_at" in p for p in bsj.check_document(built))

    def test_check_catches_a_wrong_source_set(self, built):
        del built["sources"][bsj.GATE_CSV]
        assert any("sources" in p for p in bsj.check_document(built))

    def test_korean_stays_korean_in_the_output(self, built):
        """`ensure_ascii=True` 면 '강남구'가 `\\uac15…` 로 부풀어 파일이 커지고 못 읽는다."""
        assert "강남구" in bsj.dumps_compact(built)


# ── 5. 실제로 굽기 (--dry-run 포함) ─────────────────────────────────────────


class TestMain:
    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch, capsys):
        out = tmp_path / "scorecard-v1.json"
        monkeypatch.setattr(bsj, "OUT_PATH", str(out))
        assert bsj.main(["--dry-run"]) == 0
        assert not out.exists()
        assert "미리보기" in capsys.readouterr().out

    def test_a_real_run_writes_a_readable_document(self, tmp_path, monkeypatch):
        out = tmp_path / "scorecard-v1.json"
        monkeypatch.setattr(bsj, "OUT_PATH", str(out))
        assert bsj.main([]) == 0
        with io.open(str(out), encoding="utf-8") as f:
            doc = json.load(f)
        assert bsj.check_document(doc) == []

    def test_the_committed_file_matches_the_current_csvs(self):
        """⛔ **굽는 것을 잊었으면 여기서 잡는다.**

        CSV 를 다시 뽑아 놓고 이 파일을 안 구우면 화면만 옛 성적을 계속 말한다 —
        에러가 아니라 조용한 거짓말이라 아무도 모른다(districts.geojson 의 신선도
        등식과 같은 정신).
        """
        with io.open(bsj.OUT_PATH, encoding="utf-8") as f:
            committed = json.load(f)
        assert committed == bsj.build()
