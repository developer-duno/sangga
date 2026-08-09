# -*- coding: utf-8 -*-
"""
scripts/collectors/load_vworld_bulk.py 단위 테스트

네트워크·Supabase 없이 순수 로직만 검증한다:
  1. build_col_index        — 필요한 컬럼 누락 감지 / BOM 제거
  2. build_parcel_update    — CSV 컬럼 → parcel 컬럼 매핑, 빈 값도 키는 유지
  3. discover_zip_files     — AL_D195_*.zip 만, 정렬해서
  4. scan_zip_file          — ★ 특수 블록 지번 스킵 / parcel 미보유 스킵 /
                               파일 내 중복 PNU 마지막 승 / 빈 값 None
  5. main()                 — dry-run 은 upsert 를 한 번도 부르지 않는다

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import csv
import io
import os
import sys
import zipfile

import pytest

_COLLECTORS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "collectors",
)
_SCRIPTS_DIR = os.path.dirname(_COLLECTORS_DIR)
for _p in (_SCRIPTS_DIR, _COLLECTORS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import load_vworld_bulk as target  # noqa: E402


# ── 픽스처 도우미 (2026-08-10 실측 헤더 26컬럼 그대로) ────────────────────────

HEADER = [
    "고유번호", "법정동코드", "법정동명", "대장구분코드", "대장구분명",
    "지번", "토지일련번호", "기준연도", "기준월",
    "지목코드", "지목명", "토지면적",
    "용도지역코드1", "용도지역명1", "용도지역코드2", "용도지역명2",
    "토지이용상황코드", "토지이용상황", "지형높이코드", "지형높이",
    "지형형상코드", "지형형상", "도로접면코드", "도로접면",
    "공시지가", "데이터기준일자",
]


def make_row(**overrides):
    """HEADER 순서에 맞는 기본 행(list). 값은 서울 파일 실제 행 형태를 따랐다."""
    base = {
        "고유번호": "1111010100100010000", "법정동코드": "1111010100",
        "법정동명": "서울특별시 종로구 청운동", "대장구분코드": "1", "대장구분명": "일반",
        "지번": "1", "토지일련번호": "999999", "기준연도": "2026", "기준월": "01",
        "지목코드": "08", "지목명": "대", "토지면적": "15622.100000000",
        "용도지역코드1": "13", "용도지역명1": "제1종일반주거지역",
        "용도지역코드2": "00", "용도지역명2": "지정되지않음",
        "토지이용상황코드": "120", "토지이용상황": "연립",
        "지형높이코드": "03", "지형높이": "완경사",
        "지형형상코드": "05", "지형형상": "부정형",
        "도로접면코드": "06", "도로접면": "소로한면",
        "공시지가": "5432000", "데이터기준일자": "2026-05-12",
    }
    base.update(overrides)
    return [base[h] for h in HEADER]


def make_zip(tmp_path, filename, rows, header=HEADER, encoding="cp949"):
    """원본과 같은 구조(zip 1개 안에 CSV 1개, cp949)의 시험용 zip을 만든다."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    path = os.path.join(str(tmp_path), filename)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(filename.replace(".zip", ".csv"), buf.getvalue().encode(encoding))
    return path


# parcel 이 이미 갖고 있는 PNU (pnu -> (bjd_code, sigungu_code))
EXISTING = {"1111010100100010000": ("1111010100", "11110")}


# ── 1. build_col_index ───────────────────────────────────────────────────────


def test_build_col_index_ok():
    idx = target.build_col_index(HEADER, "t.zip")
    assert idx["고유번호"] == 0
    assert idx["공시지가"] == HEADER.index("공시지가")


def test_build_col_index_missing_raises():
    bad = [h for h in HEADER if h != "도로접면"]
    with pytest.raises(target.MissingColumnsError) as exc:
        target.build_col_index(bad, "t.zip")
    assert "도로접면" in exc.value.missing_cols


def test_build_col_index_strips_bom():
    h = list(HEADER)
    h[0] = "﻿" + h[0]
    idx = target.build_col_index(h, "t.zip")
    assert "고유번호" in idx


# ── 2. build_parcel_update ───────────────────────────────────────────────────


def test_build_parcel_update_매핑():
    idx = target.build_col_index(HEADER, "t.zip")
    rec = target.build_parcel_update("1111010100100010000", make_row(), idx)
    assert rec["pnu"] == "1111010100100010000"
    assert rec["jimok"] == "대"
    assert rec["use_zone"] == "제1종일반주거지역"       # 용도지역명1 을 쓴다(2는 무시)
    assert rec["road_contact"] == "소로한면"            # 코드가 아니라 이름
    assert rec["land_price"] == 5432000
    assert rec["land_price_year"] == 2026
    assert rec["land_area_m2"] == pytest.approx(15622.1)


def test_build_parcel_update_빈_값이어도_키는_남긴다():
    """PostgREST 벌크 upsert는 배치에서 본 키를 대상 컬럼으로 삼는다 —
    어떤 행에서만 키를 빼면 매핑이 어긋난다(load_vworld_land와 같은 이유)."""
    idx = target.build_col_index(HEADER, "t.zip")
    row = make_row(지목명="", 용도지역명1="", 도로접면="", 공시지가="", 기준연도="", 토지면적="")
    rec = target.build_parcel_update("1111010100100010000", row, idx)
    for col in target.FILLABLE_COLS:
        assert col in rec and rec[col] is None


def test_build_parcel_update_공시지가_0은_값이다():
    idx = target.build_col_index(HEADER, "t.zip")
    rec = target.build_parcel_update("X", make_row(공시지가="0"), idx)
    assert rec["land_price"] == 0        # None 으로 만들면 '결측'과 섞인다


# ── 3. discover_zip_files ────────────────────────────────────────────────────


def test_discover_zip_files_filters_and_sorts(tmp_path):
    for name in ("AL_D195_41_20260519.zip", "AL_D195_11_20260519.zip",
                 "CH_D195_11_20260519.zip", "메모.txt"):
        open(os.path.join(str(tmp_path), name), "wb").close()
    got = [os.path.basename(p) for p in target.discover_zip_files(str(tmp_path))]
    assert got == ["AL_D195_11_20260519.zip", "AL_D195_41_20260519.zip"]


def test_discover_zip_files_없는_폴더는_빈_목록(tmp_path):
    assert target.discover_zip_files(os.path.join(str(tmp_path), "없음")) == []


# ── 4. scan_zip_file ─────────────────────────────────────────────────────────


def test_scan_zip_file_기본(tmp_path):
    path = make_zip(tmp_path, "AL_D195_11_20260519.zip", [make_row()])
    res = target.scan_zip_file(path, EXISTING)
    assert res["stats"]["rows"] == 1
    assert list(res["updates"]) == ["1111010100100010000"]
    rec = res["updates"]["1111010100100010000"]
    assert rec["bjd_code"] == "1111010100"     # DB 값을 그대로 되돌려 넣는다
    assert rec["sigungu_code"] == "11110"
    assert res["filled"]["road_contact"] == 1


def test_scan_zip_file_특수_블록_지번은_건너뛰고_센다(tmp_path):
    """전국 33,276건(0.09%) 실측 — `중`·`단`·`주` 등 문자가 섞인 고유번호."""
    rows = [make_row(), make_row(고유번호="111101010010001중00")]
    path = make_zip(tmp_path, "AL_D195_11_20260519.zip", rows)
    res = target.scan_zip_file(path, EXISTING)
    assert res["stats"]["invalid_pnu"] == 1
    assert len(res["updates"]) == 1


def test_scan_zip_file_19자리가_아니어도_건너뛴다(tmp_path):
    rows = [make_row(고유번호="11110101001000100")]     # 17자리
    path = make_zip(tmp_path, "AL_D195_11_20260519.zip", rows)
    res = target.scan_zip_file(path, EXISTING)
    assert res["stats"]["invalid_pnu"] == 1
    assert res["updates"] == {}


def test_scan_zip_file_parcel에_없는_PNU는_만들지_않는다(tmp_path):
    """분모 오염 방지 — 형제 load_vworld_land.py와 같은 규칙."""
    rows = [make_row(), make_row(고유번호="4113510300100010000")]
    path = make_zip(tmp_path, "AL_D195_41_20260519.zip", rows)
    res = target.scan_zip_file(path, EXISTING)
    assert res["stats"]["not_in_parcel"] == 1
    assert list(res["updates"]) == ["1111010100100010000"]


def test_scan_zip_file_파일_내_중복은_마지막_행이_이긴다(tmp_path):
    rows = [make_row(공시지가="111"), make_row(공시지가="222")]
    path = make_zip(tmp_path, "AL_D195_11_20260519.zip", rows)
    res = target.scan_zip_file(path, EXISTING)
    assert res["stats"]["dup_in_file"] == 1
    assert res["updates"]["1111010100100010000"]["land_price"] == 222
    assert res["filled"]["land_price"] == 1        # 중복이 채움 통계를 부풀리지 않는다


def test_scan_zip_file_빈_값은_None(tmp_path):
    rows = [make_row(도로접면="", 공시지가="")]
    path = make_zip(tmp_path, "AL_D195_11_20260519.zip", rows)
    res = target.scan_zip_file(path, EXISTING)
    rec = res["updates"]["1111010100100010000"]
    assert rec["road_contact"] is None and rec["land_price"] is None
    assert res["filled"]["road_contact"] == 0
    assert res["filled"]["jimok"] == 1


def test_scan_zip_file_칸_수_다른_행은_건너뛰고_센다(tmp_path):
    path = os.path.join(str(tmp_path), "AL_D195_11_20260519.zip")
    body = ",".join(HEADER) + "\n" + ",".join(make_row()) + "\n" + "짧은행,두칸\n"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("AL_D195_11_20260519.csv", body.encode("cp949"))
    res = target.scan_zip_file(path, EXISTING)
    assert res["stats"]["col_mismatch"] == 1
    assert len(res["updates"]) == 1


def test_scan_zip_file_컬럼이_없으면_에러(tmp_path):
    bad = [h for h in HEADER if h != "공시지가"]
    row = [v for h, v in zip(HEADER, make_row()) if h != "공시지가"]
    path = make_zip(tmp_path, "AL_D195_11_20260519.zip", [row], header=bad)
    with pytest.raises(target.MissingColumnsError):
        target.scan_zip_file(path, EXISTING)


def test_scan_zip_file_빈_CSV는_에러(tmp_path):
    path = os.path.join(str(tmp_path), "AL_D195_11_20260519.zip")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("AL_D195_11_20260519.csv", b"")
    with pytest.raises(target.EmptyFileError):
        target.scan_zip_file(path, EXISTING)


def test_scan_zip_file_CSV가_2개면_에러(tmp_path):
    path = os.path.join(str(tmp_path), "AL_D195_11_20260519.zip")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("a.csv", ",".join(HEADER).encode("cp949"))
        zf.writestr("b.csv", ",".join(HEADER).encode("cp949"))
    with pytest.raises(ValueError, match="CSV가 1개가 아닙니다"):
        target.scan_zip_file(path, EXISTING)


# ── 5. main() (Supabase 는 흉내만 — 실제 네트워크 없음) ──────────────────────


def _patch_supabase(monkeypatch, upsert_calls):
    monkeypatch.setattr(target, "get_supabase_config", lambda: ("https://x.supabase.co", "k"))
    monkeypatch.setattr(target, "fetch_existing_parcels", lambda base_url, headers: dict(EXISTING))

    def fake_upsert(base_url, headers, table, rows, batch_size=500):
        upsert_calls.append((table, len(rows)))
        return len(rows)

    monkeypatch.setattr(target, "upsert_batch", fake_upsert)


def test_main_dry_run_은_한_번도_쓰지_않는다(tmp_path, monkeypatch):
    make_zip(tmp_path, "AL_D195_11_20260519.zip", [make_row()])
    calls = []
    _patch_supabase(monkeypatch, calls)
    assert target.main(["--raw-dir", str(tmp_path), "--dry-run"]) == 0
    assert calls == []


def test_main_파일마다_따로_보낸다(tmp_path, monkeypatch):
    """시도 파일 1개를 다 읽을 때마다 보내고 버퍼를 비운다(메모리 폭주 방지)."""
    make_zip(tmp_path, "AL_D195_11_20260519.zip", [make_row()])
    make_zip(tmp_path, "AL_D195_41_20260519.zip", [make_row()])
    calls = []
    _patch_supabase(monkeypatch, calls)
    assert target.main(["--raw-dir", str(tmp_path)]) == 0
    assert calls == [("parcel", 1), ("parcel", 1)]


def test_main_zip이_없으면_1(tmp_path, monkeypatch):
    calls = []
    _patch_supabase(monkeypatch, calls)
    assert target.main(["--raw-dir", str(tmp_path)]) == 1
    assert calls == []


def test_parse_args_기본값():
    a = target.parse_args([])
    assert a.raw_dir is None and a.period_key is None and a.dry_run is False
    b = target.parse_args(["--dry-run", "--period-key", "202605"])
    assert b.dry_run is True and b.period_key == "202605"
