# -*- coding: utf-8 -*-
"""
scripts/collectors/collect_vworld_land.py 단위 테스트

라이브 API·Supabase 없이 검증한다 (requests는 전부 흉내낸다):
  1. envelope / read_result_code / read_total_count — 봉투 파싱
  2. extract_rows          — ★ 행 1개일 때 field가 dict로 오는 경우(조용한 누락 방어)
  3. is_config_error / is_ok_code — 성공 코드가 빈 값이거나 NORMAL_SERVICE
  4. pick_latest_row       — ★ stdrYear 최대 → lastUpdtDt 최대. ladSn으로 고르지 않는다
  5. is_truncated / budget_verdict
  6. mask_secret           — 'key=' 파라미터만 가린다
  7. append_jsonl          — raw 한 줄 = 한 필지, 해석하지 않고 그대로
  8. fetch_land            — 정상 / 429 재시도 / INCORRECT_KEY → ConfigError
  9. collect_one           — 행 0건은 실패가 아니라 skipped
 10. parse_args / current_period_key

conftest.py를 새로 만들지 않기 위해(다른 수집기 작업과 충돌 방지),
sys.path 조작은 이 파일 안에서만 한다.
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

import collect_vworld_land as cvl  # noqa: E402


# ── 1. 봉투 파싱 ──────────────────────────────────────────────────────────────


def _envelope(**kw):
    return {"landCharacteristicss": kw}


def test_envelope_는_최상위_키가_하나인_dict에서_꺼낸다():
    assert cvl.envelope(_envelope(field=[])) == {"field": []}


@pytest.mark.parametrize("bad", [None, [], "x", {}, {"a": 1, "b": 2}, {"a": "not dict"}])
def test_envelope_는_모양이_이상하면_None(bad):
    assert cvl.envelope(bad) is None


def test_read_result_code_정상은_빈_문자열이다():
    # ⚠️ MOLIT('00')·R-ONE('INFO-000')과 정반대 — 성공일 때 코드가 비어 있다.
    code, msg = cvl.read_result_code(_envelope(resultCode="", resultMsg="", field=[]))
    assert (code, msg) == ("", "")


def test_read_result_code_오류코드를_읽는다():
    code, msg = cvl.read_result_code(
        _envelope(resultCode="INCORRECT_KEY", resultMsg="인증키 정보가 올바르지 않습니다."))
    assert code == "INCORRECT_KEY"
    assert "인증키" in msg


def test_read_result_code_봉투가_이상하면_빈값():
    assert cvl.read_result_code({"a": 1, "b": 2}) == ("", "")


def test_read_total_count():
    assert cvl.read_total_count(_envelope(totalCount="18")) == 18
    assert cvl.read_total_count(_envelope(totalCount="")) is None
    assert cvl.read_total_count(_envelope()) is None


# ── 2. extract_rows — 단일 행이 dict로 오는 함정 ─────────────────────────────


def test_extract_rows_리스트를_그대로():
    rows = [{"pnu": "1"}, {"pnu": "2"}]
    assert cvl.extract_rows(_envelope(field=rows)) == rows


def test_extract_rows_행이_하나면_dict로_오는데_리스트로_감싼다():
    """★ 이 방어가 없으면 그 필지가 에러 없이 통째로 누락된다.

    형제 레포 naver-estate-web/crawler/vworld_client.py가 같은 API에서 이미
    `if isinstance(fields, dict): fields = [fields]` 방어를 하고 있다.
    """
    one = {"pnu": "1168010100106010000", "stdrYear": "2026"}
    assert cvl.extract_rows(_envelope(field=one)) == [one]


@pytest.mark.parametrize("bad", [None, "", 0])
def test_extract_rows_없으면_빈_리스트(bad):
    assert cvl.extract_rows(_envelope(field=bad)) == []


# ── 3. 코드 판정 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("code", ["INCORRECT_KEY", "incorrect_key", " INCORRECT_KEY ",
                                  "NOT_EXISTS_KEY", "INVALID_KEY"])
def test_is_config_error_참(code):
    assert cvl.is_config_error(code) is True


@pytest.mark.parametrize("code", ["", None, "NORMAL_SERVICE", "SOME_OTHER"])
def test_is_config_error_거짓(code):
    assert cvl.is_config_error(code) is False


@pytest.mark.parametrize("code", ["", None, "NORMAL_SERVICE", " normal_service "])
def test_is_ok_code_참(code):
    """성공 코드가 오퍼레이션마다 다르다 — 빈 값(토지특성)과 NORMAL_SERVICE(중개업소) 둘 다."""
    assert cvl.is_ok_code(code) is True


def test_is_ok_code_거짓():
    assert cvl.is_ok_code("INCORRECT_KEY") is False


# ── 4. pick_latest_row — 중복 행에서 '지금의 값' 고르기 ──────────────────────


def _row(year, upd, price, ladsn="999999"):
    return {"stdrYear": year, "lastUpdtDt": upd, "pblntfPclnd": price, "ladSn": ladsn}


def test_pick_latest_row_연도가_최대인_행():
    rows = [_row("2024", "2024-07-30", "53630000"),
            _row("2026", "2026-05-12", "59490000"),
            _row("2025", "2026-03-26", "56560000")]
    assert cvl.pick_latest_row(rows)["stdrYear"] == "2026"


def test_pick_latest_row_같은_연도면_lastUpdtDt가_최대인_행():
    """실측: 2025년에 3행이 온다(2026-03-26 x2, 2025-08-06). ladSn은 전부 999999라 못 쓴다."""
    rows = [_row("2025", "2025-08-06", "56560000"),
            _row("2025", "2026-03-26", "56560000"),
            _row("2025", "2026-03-26", "56560000")]
    assert cvl.pick_latest_row(rows)["lastUpdtDt"] == "2026-03-26"


def test_pick_latest_row_ladSn이_모두_같아도_고를_수_있다():
    """★ 직전 세션 메모의 'ladSn으로 최신 1행'은 틀렸다 — 판별자는 lastUpdtDt다."""
    rows = [_row("2025", "2025-01-01", "1", ladsn="999999"),
            _row("2026", "2026-01-01", "2", ladsn="999999")]
    picked = cvl.pick_latest_row(rows)
    assert picked["pblntfPclnd"] == "2"


def test_pick_latest_row_연도가_빈_행은_밀린다():
    rows = [_row("", "2099-01-01", "쓰레기"), _row("2013", "2013-01-01", "정상")]
    assert cvl.pick_latest_row(rows)["pblntfPclnd"] == "정상"


def test_pick_latest_row_빈_입력은_None():
    assert cvl.pick_latest_row([]) is None
    assert cvl.pick_latest_row(None) is None


# ── 5. 절단·예산 ─────────────────────────────────────────────────────────────


def test_is_truncated():
    assert cvl.is_truncated(101, num_of_rows=100) is True
    assert cvl.is_truncated(100, num_of_rows=100) is False
    assert cvl.is_truncated(None) is False


def test_budget_verdict():
    v = cvl.budget_verdict(calls_used=4900, planned_calls=200, budget=5000)
    assert v["remaining"] == 100
    assert v["fits"] is False
    assert v["shortfall"] == 100
    v2 = cvl.budget_verdict(calls_used=0, planned_calls=50, budget=5000)
    assert v2["fits"] is True and v2["shortfall"] == 0


def test_budget_verdict_이미_초과했으면_남은_예산은_0():
    v = cvl.budget_verdict(calls_used=6000, planned_calls=1, budget=5000)
    assert v["remaining"] == 0


# ── 6. 시크릿 마스킹 ─────────────────────────────────────────────────────────


def test_mask_secret_key_파라미터를_가린다():
    url = "https://api.vworld.kr/ned/data/getLandCharacteristics?key=ABCD-1234&pnu=116"
    out = cvl.mask_secret(url)
    assert "ABCD-1234" not in out
    assert "pnu=116" in out


def test_mask_secret_다른_파라미터명_안의_부분일치는_건드리지_않는다():
    url = "https://x?monkey=banana&key=SECRET"
    out = cvl.mask_secret(url)
    assert "monkey=banana" in out
    assert "SECRET" not in out


def test_mask_secret_키값을_직접_주면_본문에서도_지운다():
    assert "SEC" not in cvl.mask_secret("오류: SEC 사용 불가", key="SEC")


# ── 7. raw 쓰기 ──────────────────────────────────────────────────────────────


def test_append_jsonl_한_줄에_한_필지를_해석없이_적는다(tmp_path):
    path = str(tmp_path / "sub" / "land.jsonl")
    rows = [{"stdrYear": "2026", "roadSideCodeNm": "광대소각"}]
    cvl.append_jsonl(path, "1168010100106010000", rows, "2026-08-09T00:00:00+09:00")
    cvl.append_jsonl(path, "1168010100106190007", rows, "2026-08-09T00:00:01+09:00")

    lines = open(path, encoding="utf-8").read().strip().split("\n")
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["pnu"] == "1168010100106010000"
    assert rec["rows"] == rows          # 원본 그대로 — 해석하지 않는다
    assert rec["fetched_at"].startswith("2026-08-09")


# ── 8. fetch_land ────────────────────────────────────────────────────────────


class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _Session:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):  # noqa: ARG002
        self.calls.append(params)
        return self._responses.pop(0)


def test_fetch_land_정상():
    rows = [{"stdrYear": "2026"}]
    s = _Session([_Resp(payload=_envelope(field=rows, totalCount="1", resultCode=""))])
    got, total = cvl.fetch_land(s, "KEY", "1168", "https://github.com/x", sleep_sec=0)
    assert got == rows and total == 1
    assert s.calls[0]["domain"] == "https://github.com/x"   # domain은 반드시 실린다
    assert s.calls[0]["pnu"] == "1168"


def test_fetch_land_행이_하나면_dict로_와도_받는다():
    one = {"stdrYear": "2026"}
    s = _Session([_Resp(payload=_envelope(field=one, totalCount="1"))])
    got, _ = cvl.fetch_land(s, "KEY", "1168", "d", sleep_sec=0)
    assert got == [one]


def test_fetch_land_INCORRECT_KEY는_ConfigError로_즉시_멈춘다():
    s = _Session([_Resp(payload=_envelope(
        resultCode="INCORRECT_KEY", resultMsg="인증키 정보가 올바르지 않습니다."))])
    with pytest.raises(cvl.ConfigError) as e:
        cvl.fetch_land(s, "KEY", "1168", "https://github.com/x", sleep_sec=0)
    assert "domain" in str(e.value)      # 사람이 뭘 고쳐야 하는지 메시지에 있어야 한다


def test_fetch_land_429는_재시도한다(monkeypatch):
    monkeypatch.setattr(cvl.time, "sleep", lambda *_: None)
    rows = [{"stdrYear": "2026"}]
    s = _Session([_Resp(status_code=429),
                  _Resp(payload=_envelope(field=rows, totalCount="1"))])
    counter = {"calls": 0}
    got, _ = cvl.fetch_land(s, "KEY", "1168", "d", call_counter=counter, sleep_sec=0)
    assert got == rows
    assert counter["calls"] == 2        # 재시도로 나간 요청도 장부에 센다


def test_fetch_land_5xx를_끝까지_실패하면_ApiError(monkeypatch):
    monkeypatch.setattr(cvl.time, "sleep", lambda *_: None)
    s = _Session([_Resp(status_code=503) for _ in range(cvl.RETRY_COUNT)])
    with pytest.raises(cvl.ApiError):
        cvl.fetch_land(s, "KEY", "1168", "d", sleep_sec=0)


def test_fetch_land_4xx는_즉시_ApiError():
    s = _Session([_Resp(status_code=400, text="bad request")])
    with pytest.raises(cvl.ApiError) as e:
        cvl.fetch_land(s, "KEY", "1168", "d", sleep_sec=0)
    assert "HTTP 400" in str(e.value)


def test_fetch_land_4xx_오류_본문에_키가_섞여도_새지_않는다():
    """실제 방어선 두 개를 확인한다: ① 키 값 자체 ② 쿼리 파라미터 위치의 key=.

    (본문 아무 데나 있는 'key=xxx' 꼴을 전부 지우지는 않는다 — 다른 파라미터명 안의
    우연한 일치까지 건드리지 않으려는 의도적 설계다. mask_secret 주석 참조.)
    """
    real_key = "D398-DEAD-BEEF"
    s = _Session([_Resp(status_code=400,
                        text="요청 실패 url=https://x?key={}&pnu=1168".format(real_key))])
    with pytest.raises(cvl.ApiError) as e:
        cvl.fetch_land(s, real_key, "1168", "d", sleep_sec=0)
    msg = str(e.value)
    assert real_key not in msg
    assert "pnu=1168" in msg              # 진단에 필요한 나머지는 남는다


def test_fetch_land_행이_없고_오류코드도_없으면_빈_결과():
    s = _Session([_Resp(payload=_envelope(field=[], totalCount="0", resultCode=""))])
    rows, total = cvl.fetch_land(s, "KEY", "1168", "d", sleep_sec=0)
    assert rows == [] and total == 0


# ── 9. collect_one ───────────────────────────────────────────────────────────


def test_collect_one_정상은_done이고_raw에_적힌다(tmp_path):
    rows = [{"stdrYear": "2026"}]
    s = _Session([_Resp(payload=_envelope(field=rows, totalCount="1"))])
    res = cvl.collect_one(s, "KEY", "1168", "d", str(tmp_path), sleep_sec=0)
    assert res["status"] == "done" and res["row_count"] == 1
    assert os.path.isfile(cvl.raw_path(str(tmp_path)))


def test_collect_one_행이_0건이면_실패가_아니라_skipped(tmp_path):
    """토지특성이 없는 필지가 있을 수 있다 — failed로 세면 재시도만 반복한다."""
    s = _Session([_Resp(payload=_envelope(field=[], totalCount="0"))])
    res = cvl.collect_one(s, "KEY", "1168", "d", str(tmp_path), sleep_sec=0)
    assert res["status"] == "skipped" and res["row_count"] == 0
    assert not os.path.isfile(cvl.raw_path(str(tmp_path)))   # 빈 줄을 raw에 남기지 않는다


def test_collect_one_절단이_의심되면_경고를_남긴다(tmp_path):
    rows = [{"stdrYear": "2026"}]
    s = _Session([_Resp(payload=_envelope(field=rows, totalCount="500"))])
    res = cvl.collect_one(s, "KEY", "1168", "d", str(tmp_path), sleep_sec=0)
    assert res["status"] == "done"
    assert "절단" in (res["error_msg"] or "")


# ── 10. CLI·기타 ─────────────────────────────────────────────────────────────


def test_parse_args_기본값():
    a = cvl.parse_args([])
    assert a.dry_run is False and a.limit is None and a.sigungu is None
    assert a.daily_budget == cvl.DEFAULT_DAILY_BUDGET


def test_parse_args_옵션():
    a = cvl.parse_args(["--dry-run", "--limit", "10", "--sigungu", "11680",
                        "--period-key", "202608", "--daily-budget", "100"])
    assert a.dry_run is True and a.limit == 10
    assert a.sigungu == "11680" and a.period_key == "202608" and a.daily_budget == 100


def test_current_period_key_는_YYYYMM():
    from datetime import datetime
    key = cvl.current_period_key(datetime(2026, 8, 9, tzinfo=cvl.KST))
    assert key == "202608"


def test_build_progress_row_실패면_attempts가_는다():
    row = cvl.build_progress_row("1168", "202608",
                                 {"status": "failed", "row_count": None, "error_msg": "x"}, 2)
    assert row["attempts"] == 3
    ok = cvl.build_progress_row("1168", "202608",
                                {"status": "done", "row_count": 18, "error_msg": None}, 2)
    assert ok["attempts"] == 2
