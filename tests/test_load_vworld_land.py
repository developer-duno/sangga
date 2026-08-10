# -*- coding: utf-8 -*-
"""
scripts/collectors/load_vworld_land.py 단위 테스트

DB 없이 순수 로직만 검증한다:
  1. to_int / to_float / clean_text — 빈 값과 0을 구분한다
  2. build_parcel_update            — 브이월드 필드 → parcel 컬럼 매핑
  3. read_raw_records               — 깨진 줄을 건너뛰되 몇 줄인지 센다
  4. collapse_records               — ★ 같은 PNU가 두 번 나와도 최신 1행으로 접는다

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import json
import os
import sys

import pytest

_COLLECTORS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "collectors",
)
if _COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, _COLLECTORS_DIR)

import load_vworld_land as lvl  # noqa: E402


# ── 1. 형 변환 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("18400000", 18400000), (" 2026 ", 2026), ("493.9", 493),
    ("0", 0),                      # 0은 값이다 — None으로 만들면 안 된다
    ("", None), (None, None), ("없음", None),
])
def test_to_int(raw, expected):
    assert lvl.to_int(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("493.9", 493.9), ("0", 0.0), ("", None), (None, None), ("x", None),
])
def test_to_float(raw, expected):
    assert lvl.to_float(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("광대소각", "광대소각"), ("  대  ", "대"), ("", None), (None, None),
])
def test_clean_text(raw, expected):
    assert lvl.clean_text(raw) == expected


# ── 2. 매핑 ──────────────────────────────────────────────────────────────────


_ROW = {
    "lndcgrCodeNm": "대",
    "prposArea1Nm": "일반상업지역",
    "prposArea2Nm": "제3종일반주거지역",
    "roadSideCodeNm": "광대소각",
    "roadSideCode": "02",
    "pblntfPclnd": "59490000",
    "stdrYear": "2026",
    "lndpclAr": "493.9",
    "ladSn": "999999",
}


def test_build_parcel_update_매핑():
    rec = lvl.build_parcel_update("1168010100106010000", _ROW)
    assert rec["pnu"] == "1168010100106010000"
    assert rec["jimok"] == "대"
    assert rec["use_zone"] == "일반상업지역"          # prposArea1Nm 을 쓴다
    assert rec["road_contact"] == "광대소각"          # 코드가 아니라 이름
    assert rec["land_price"] == 59490000
    assert rec["land_price_year"] == 2026
    assert rec["land_area_m2"] == 493.9


def test_build_parcel_update_값이_없어도_키는_남긴다():
    """PostgREST 벌크 upsert는 배치에서 본 키를 대상 컬럼으로 삼는다 —
    어떤 행에서만 키를 빼면 매핑이 어긋난다(load_sangkwon_snapshot과 같은 이유)."""
    rec = lvl.build_parcel_update("1168", {})
    for col in ("jimok", "use_zone", "road_contact", "land_price",
                "land_price_year", "land_area_m2"):
        assert col in rec and rec[col] is None


# ── 3. raw 읽기 ──────────────────────────────────────────────────────────────


def _write(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def test_read_raw_records_정상(tmp_path):
    p = str(tmp_path / "land.jsonl")
    _write(p, [json.dumps({"pnu": "A", "rows": [_ROW]}, ensure_ascii=False),
               json.dumps({"pnu": "B", "rows": []}, ensure_ascii=False)])
    got = [(pnu, rows) for pnu, rows, _ in lvl.read_raw_records(p)]
    assert got == [("A", [_ROW]), ("B", [])]


def test_read_raw_records_깨진_줄은_건너뛰고_센다(tmp_path):
    p = str(tmp_path / "land.jsonl")
    _write(p, [json.dumps({"pnu": "A", "rows": [_ROW]}, ensure_ascii=False),
               '{"pnu": "B", "rows": [',          # 반 줄 (강제 종료 흔적)
               json.dumps({"rows": []}),           # pnu 없음
               json.dumps({"pnu": "C", "rows": "리스트가 아님"}),
               json.dumps({"pnu": "D", "rows": [_ROW]}, ensure_ascii=False)])
    out = list(lvl.read_raw_records(p))
    assert [pnu for pnu, _, _ in out] == ["A", "D"]
    assert out[-1][2] == 3                          # 깨진 줄 3개를 셌다


def test_read_raw_records_마지막_줄이_잘려도_총수를_센다(tmp_path):
    """강제 종료로 잘리는 건 언제나 '마지막 줄'이다.

    yield 되는 누계는 그 줄까지라, 마지막 정상 줄 뒤의 깨진 줄은 전달되지 못했다
    (2026-08-09 재현: 1줄이 깨졌는데 0으로 보고 → 경고 자체가 안 떴다).
    counter 를 넘기면 파일을 끝까지 읽은 뒤 총수가 들어온다.
    """
    p = str(tmp_path / "land.jsonl")
    _write(p, [json.dumps({"pnu": "A", "rows": [_ROW]}, ensure_ascii=False),
               json.dumps({"pnu": "B", "rows": [_ROW]}, ensure_ascii=False),
               '{"pnu": "C", "rows": ['])           # 잘린 마지막 줄
    counter = {"broken": 0}
    out = list(lvl.read_raw_records(p, counter))
    assert [pnu for pnu, _, _ in out] == ["A", "B"]
    assert out[-1][2] == 0                          # yield 시점엔 아직 0이 맞다
    assert counter["broken"] == 1                   # 끝까지 읽은 뒤엔 1로 보인다


def test_read_raw_records_전부_깨져도_총수를_센다(tmp_path):
    """정상 줄이 하나도 없으면 yield 가 한 번도 안 일어난다 — 그래도 세야 한다."""
    p = str(tmp_path / "land.jsonl")
    _write(p, ['{"pnu": "A", "rows": [', "깨진 줄"])
    counter = {"broken": 0}
    assert list(lvl.read_raw_records(p, counter)) == []
    assert counter["broken"] == 2


def test_read_raw_records_counter_는_재사용해도_초기화된다(tmp_path):
    """같은 dict 을 두 번 쓰면 앞 파일의 수가 남아 부풀지 않아야 한다."""
    dirty = str(tmp_path / "dirty.jsonl")
    _write(dirty, ['{"pnu": "A", "rows": ['])
    clean = str(tmp_path / "clean.jsonl")
    _write(clean, [json.dumps({"pnu": "A", "rows": []})])
    counter = {"broken": 0}
    list(lvl.read_raw_records(dirty, counter))
    assert counter["broken"] == 1
    list(lvl.read_raw_records(clean, counter))
    assert counter["broken"] == 0


def test_read_raw_records_빈_줄은_무시(tmp_path):
    p = str(tmp_path / "land.jsonl")
    _write(p, ["", json.dumps({"pnu": "A", "rows": []}), ""])
    assert [pnu for pnu, _, _ in lvl.read_raw_records(p)] == ["A"]


# ── 4. 중복 접기 ─────────────────────────────────────────────────────────────


def _row(year, upd, price):
    return {"stdrYear": year, "lastUpdtDt": upd, "pblntfPclnd": price, "ladSn": "999999"}


def test_collapse_records_필지당_최신_1행():
    records = [("A", [_row("2024", "2024-07-30", "1"), _row("2026", "2026-05-12", "2")])]
    best = lvl.collapse_records(records)
    assert list(best) == ["A"]
    assert best["A"]["pblntfPclnd"] == "2"


def test_collapse_records_같은_PNU가_두_줄이면_더_최신이_이긴다():
    """★ '나중 줄이 무조건 이긴다'로 하면, 옛 연도만 담긴 재수집이 최신을 덮는다."""
    records = [("A", [_row("2026", "2026-05-12", "최신")]),
               ("A", [_row("2013", "2013-01-01", "옛것")])]
    best = lvl.collapse_records(records)
    assert best["A"]["pblntfPclnd"] == "최신"


def test_collapse_records_행이_없는_필지는_빠진다():
    best = lvl.collapse_records([("A", []), ("B", [_row("2026", "2026-01-01", "x")])])
    assert list(best) == ["B"]


def test_parse_args_기본값():
    a = lvl.parse_args([])
    assert a.raw_dir is None and a.period_key is None and a.dry_run is False
    b = lvl.parse_args(["--dry-run", "--period-key", "202608"])
    assert b.dry_run is True and b.period_key == "202608"


# ── 5. upsert_batch 재시도 (결함 1 — docs/decisions/0005 §[A] 결정 2) ────────
# ⚠️ 아래 테스트들은 고치기 전 코드(재시도 없이 즉시 예외)로 되돌리면 전부
# 빨간불이 된다: 실패 응답이 1번만 오고(calls == 1) 재시도가 없어 성공 케이스는
# 애초에 성공하지 못하고, "재시도 N회 소진" 문구도 없다.


class _FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else []
        self.text = text

    def json(self):
        return self._json


def test_upsert_batch_5xx는_재시도_후_성공한다(monkeypatch):
    responses = [_FakeResp(503, text="unavailable"), _FakeResp(201, text="ok")]
    calls = []

    def fake_post(url, headers=None, data=None, timeout=None):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(lvl.requests, "post", fake_post)
    sleeps = []
    sent = lvl.upsert_batch(
        "https://x.supabase.co", {"apikey": "k"}, "parcel", [{"pnu": "1"}],
        sleep=sleeps.append,
    )
    assert sent == 1
    assert len(calls) == 2
    assert sleeps == [2]


def test_upsert_batch_네트워크_오류는_재시도_후_성공한다(monkeypatch):
    state = {"n": 0}

    def fake_post(url, headers=None, data=None, timeout=None):
        state["n"] += 1
        if state["n"] == 1:
            raise lvl.requests.exceptions.ConnectionError("boom")
        return _FakeResp(201, text="ok")

    monkeypatch.setattr(lvl.requests, "post", fake_post)
    sent = lvl.upsert_batch(
        "https://x.supabase.co", {"apikey": "k"}, "parcel", [{"pnu": "1"}],
        sleep=lambda s: None,
    )
    assert sent == 1
    assert state["n"] == 2


def test_upsert_batch_5xx_재시도_소진하면_예외(monkeypatch):
    monkeypatch.setattr(
        lvl.requests, "post",
        lambda url, headers=None, data=None, timeout=None: _FakeResp(500, text="boom"),
    )
    sleeps = []
    with pytest.raises(RuntimeError, match="재시도 3회 소진"):
        lvl.upsert_batch(
            "https://x.supabase.co", {"apikey": "k"}, "parcel", [{"pnu": "1"}],
            sleep=sleeps.append,
        )
    assert sleeps == [2, 4]


def test_upsert_batch_4xx는_재시도_없이_즉시_실패(monkeypatch):
    calls = []

    def fake_post(url, headers=None, data=None, timeout=None):
        calls.append(url)
        return _FakeResp(400, text="bad")

    monkeypatch.setattr(lvl.requests, "post", fake_post)
    with pytest.raises(RuntimeError, match="저장 실패"):
        lvl.upsert_batch(
            "https://x.supabase.co", {"apikey": "k"}, "parcel", [{"pnu": "1"}],
            sleep=lambda s: None,
        )
    assert len(calls) == 1


# ── 6. fetch_existing_parcels keyset 페이지네이션 (결함 2) ───────────────────
# ⚠️ 되돌리면(limit/offset) 빨간불: 요청 URL에 "pnu=gt."가 안 나오고 "offset="이
# 나온다.


def test_fetch_existing_parcels_페이지_경계에서_행이_누락되지_않는다(monkeypatch):
    """2,500행을 1,000씩 3페이지로 주는 가짜 REST — 전량 수집 + 커서 기반 다음
    페이지 요청을 함께 확인한다(과제가 요구한 회귀 가드)."""
    all_pnus = ["{:019d}".format(i) for i in range(2500)]
    requested_urls = []

    def fake_get(url, headers=None, timeout=None):
        requested_urls.append(url)
        if "pnu=gt." not in url:
            page = all_pnus[0:1000]
        else:
            cursor = url.split("pnu=gt.")[1].split("&")[0]
            start = all_pnus.index(cursor) + 1
            page = all_pnus[start:start + 1000]
        rows = [{"pnu": p, "bjd_code": "B", "sigungu_code": "S"} for p in page]
        return _FakeResp(200, rows)

    monkeypatch.setattr(lvl.requests, "get", fake_get)
    result = lvl.fetch_existing_parcels("https://x.supabase.co", {"apikey": "k"}, page_size=1000)

    assert len(result) == 2500
    assert set(result) == set(all_pnus)
    assert result[all_pnus[0]] == ("B", "S")
    assert len(requested_urls) == 3
    assert "pnu=gt." not in requested_urls[0]           # 첫 페이지는 커서 없음
    assert "pnu=gt.{}".format(all_pnus[999]) in requested_urls[1]
    assert "pnu=gt.{}".format(all_pnus[1999]) in requested_urls[2]
    assert "offset=" not in requested_urls[0] + requested_urls[1] + requested_urls[2]


def test_fetch_existing_parcels_빈_결과는_빈_dict(monkeypatch):
    monkeypatch.setattr(lvl.requests, "get",
                        lambda url, headers=None, timeout=None: _FakeResp(200, []))
    assert lvl.fetch_existing_parcels("https://x.supabase.co", {"apikey": "k"}) == {}


def test_fetch_existing_parcels_HTTP_오류면_예외(monkeypatch):
    monkeypatch.setattr(
        lvl.requests, "get",
        lambda url, headers=None, timeout=None: _FakeResp(500, [], text="boom"),
    )
    with pytest.raises(RuntimeError, match="parcel 조회 실패"):
        lvl.fetch_existing_parcels("https://x.supabase.co", {"apikey": "k"})
