# -*- coding: utf-8 -*-
"""
scripts/check_data_freshness.py 1:1 단위 테스트.

네트워크는 전부 가짜로 막는다 — 가짜를 안 끼운 시험이 실제 창고로 나가려 하면 그 자리에서
실패한다(아래 autouse 고정물). 공용 설정 파일 없이 이 파일 안에서 import 경로를 직접 푼다.

여기서 특히 지키는 것
---------------------
  · 판정 경계: 예정일 **전날·당일은 안 지남**, 다음 날부터 지남(`<`, `<=` 아님).
  · 오늘은 **한국 날짜**다 — UTC 15:00 이 한국 다음 날 0시다. UTC 로 재면 한국 오전
    0~9시에 하루 늦게 판정한다.
  · ⛔ **장님이 되는 길은 전부 조회 실패(2)** 다 — 0줄·모양 이상·HTTP 오류·잡지 못한 예외·
    예정일 있는 줄 0개·날짜가 아닌 예정일. 섞으면 창고가 죽은 주에 감시가 초록불을 켠다.
  · 지난 자료 **하나에 이슈 하나**, 제목에 변하는 값이 없다 — 하나를 적재해도 남은 자료의
    제목이 그대로라 새 이슈가 안 열린다.
"""

import datetime
import http.client
import json
import os
import shutil
import subprocess
import sys
import urllib.error

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import check_data_freshness as cdf  # noqa: E402
import check_watch_heartbeat as hb  # noqa: E402

WORKFLOW_DIR = os.path.join(ROOT, ".github", "workflows")
WORKFLOW = os.path.join(WORKFLOW_DIR, "data-freshness-watch.yml")

URL = "https://example.test"
KEY = "anon-key-fake"


def row(src, next_expected, basis="202608", basis_kind="기준월", cadence="월 1회"):
    return {
        "src": src,
        "basis_kind": basis_kind,
        "basis": basis,
        "next_expected": next_expected,
        "cadence": cadence,
    }


def live_like_rows():
    """2026-10-01 11:57 KST 라이브 응답의 모양 — 열 줄, 예정일 있는 줄 넷, null 여섯."""
    return [
        row("점포·업종 (상권정보)", "2026-10-31", basis="202606", basis_kind="분기"),
        row("실거래 (매매)", None, basis="202608", basis_kind="계약월"),
        row("건축물대장", None, basis="2026-09-01", basis_kind="적재일"),
        row("상권 경계", None, basis="2026-08-14", basis_kind="계산일"),
        row("LH 상가 공고", None, basis="2026-10-01", basis_kind="수집일"),
        row("건축 인허가", "2026-10-31", basis="202608", basis_kind="기준월"),
        row("국세청 기준시가", "2027-03-31", basis="2026-01-01", basis_kind="고시일"),
        row("상권 임대 동향 (부동산원)", "2026-10-31", basis="2026Q2", basis_kind="분기"),
        row("참고 시세 성적표", None, basis="2026-08-16", basis_kind="적재일"),
        row("필지 (토지 특성)", None, basis="2026-08-13", basis_kind="갱신일"),
    ]


class FakeResponse:
    def __init__(self, payload=None, raw=None, read_error=None):
        self._body = raw if raw is not None else json.dumps(payload).encode("utf-8")
        self._read_error = read_error

    def read(self):
        if self._read_error is not None:
            raise self._read_error
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """⛔ 실요청 0 — 가짜를 안 끼운 시험이 밖으로 나가려 하면 여기서 실패한다."""
    def refuse(*_a, **_kw):
        raise AssertionError("시험이 실제 네트워크로 나가려 했습니다")

    monkeypatch.setattr(cdf.fd.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(cdf.time, "sleep", lambda _s: None)


def install_fake_urlopen(monkeypatch, payload):
    """RPC 응답 하나를 흉내 낸다. 요청(주소·머리·본문)을 기록해 돌려준다.

    payload 가 예외면 urlopen 이 그걸 던지고, FakeResponse 면 그대로 돌려준다.
    """
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append({
            "url": req.full_url,
            "headers": {k.lower(): v for k, v in req.header_items()},
            "data": req.data,
        })
        if isinstance(payload, Exception):
            raise payload
        if isinstance(payload, FakeResponse):
            return payload
        return FakeResponse(payload)

    monkeypatch.setattr(cdf.fd.urllib.request, "urlopen", fake_urlopen)
    return calls


def set_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SANGGA_SUPABASE_URL", URL)
    monkeypatch.setenv("SANGGA_SUPABASE_ANON_KEY", KEY)
    monkeypatch.chdir(tmp_path)  # 이슈 파일을 레포에 흘리지 않게
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def outputs(path):
    """GITHUB_OUTPUT 을 {key: value} 로 되읽는다."""
    if not path.exists():
        return {}
    got = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            got[key] = value
    return got


def issue_files(tmp_path):
    """폴더의 자료별 이슈를 [(제목, 본문), ...] 로 — 워크플로 루프가 보는 순서(*.md 정렬)."""
    folder = tmp_path / cdf.ISSUE_DIR
    if not folder.exists():
        return []
    pairs = []
    for md in sorted(folder.glob("*.md")):
        title = md.with_suffix(".title").read_text(encoding="utf-8").rstrip("\n")
        pairs.append((title, md.read_text(encoding="utf-8")))
    return pairs


D = datetime.date


# ── 한국 날짜 ─────────────────────────────────────────────────────────────────


def test_today_is_korean_date_just_before_midnight():
    """UTC 14:59 = 한국 23:59 — 아직 같은 날."""
    now = datetime.datetime(2026, 11, 1, 14, 59, tzinfo=datetime.timezone.utc)
    assert cdf.today_kst(now) == D(2026, 11, 1)


def test_today_turns_at_utc_1500():
    """⛔ UTC 15:00 = 한국 다음 날 0시. UTC 날짜로 재면 여기서 하루 늦는다."""
    now = datetime.datetime(2026, 11, 1, 15, 0, tzinfo=datetime.timezone.utc)
    assert cdf.today_kst(now) == D(2026, 11, 2)


def test_korean_midnight_flips_the_verdict():
    """한국 날짜가 바뀌는 순간 판정도 바뀐다 — 예정 2026-11-01 은 한국 11-02 0시부터 지남."""
    rows = [row("건축 인허가", "2026-11-01")]
    before = cdf.today_kst(datetime.datetime(2026, 11, 1, 14, 59, tzinfo=datetime.timezone.utc))
    after = cdf.today_kst(datetime.datetime(2026, 11, 1, 15, 0, tzinfo=datetime.timezone.utc))
    assert cdf.find_overdue(rows, before) == []
    assert len(cdf.find_overdue(rows, after)) == 1


# ── 판정 경계 ─────────────────────────────────────────────────────────────────


def test_day_before_is_not_overdue():
    assert cdf.find_overdue([row("x", "2026-10-31")], D(2026, 10, 30)) == []


def test_same_day_is_not_overdue():
    """예정일은 '그날까지'다 — 당일은 아직 안 지났다."""
    assert cdf.find_overdue([row("x", "2026-10-31")], D(2026, 10, 31)) == []


def test_next_day_is_overdue_by_one():
    got = cdf.find_overdue([row("건축 인허가", "2026-10-31")], D(2026, 11, 1))
    assert got == [{
        "src": "건축 인허가",
        "basis_kind": "기준월",
        "basis": "202608",
        "next_expected": "2026-10-31",
        "days_over": 1,
    }]


def test_live_like_rows_on_nov_2():
    """브리프 예시: 오늘 2026-11-02 → 10-31 예정인 셋이 지남, 2027-03-31 은 아님."""
    got = cdf.find_overdue(live_like_rows(), D(2026, 11, 2))
    assert [o["src"] for o in got] == [
        "점포·업종 (상권정보)", "건축 인허가", "상권 임대 동향 (부동산원)",
    ]
    assert {o["days_over"] for o in got} == {2}


def test_live_like_rows_today_are_quiet():
    """2026-10-01 라이브 값으로는 지난 줄이 없다(조용해야 한다)."""
    assert cdf.find_overdue(live_like_rows(), D(2026, 10, 1)) == []


@pytest.mark.parametrize("bad", [None, "", "2026-13-40", "2026/10/31", "202610", 20261031, ["2026-10-31"]])
def test_find_overdue_never_judges_a_non_date(bad):
    """판정 함수 자체는 날짜가 아닌 값을 '지남'으로 세지 않는다(모양 검사는 check_rows 몫)."""
    assert cdf.find_overdue([row("x", bad)], D(2030, 1, 1)) == []


# ── 응답 모양 = 장님이 되는 길은 전부 조회 실패 ─────────────────────────────────


def test_zero_rows_is_a_lookup_failure():
    """⛔ 0줄은 '지난 것 없음'이 아니다 — 이 함수는 자료가 비어도 줄을 늘 준다."""
    with pytest.raises(cdf.fd.CallFailed):
        cdf.check_rows([])


@pytest.mark.parametrize("bad", [
    {"code": "PGRST202", "message": "function does not exist"},
    None,
    [None],
    ["점포"],
    [{"src": "점포", "basis_kind": "분기"}],  # 칸이 빠졌다 = 함수 모양이 바뀌었다
])
def test_wrong_shape_is_a_lookup_failure(bad):
    with pytest.raises(cdf.fd.CallFailed):
        cdf.check_rows(bad)


def test_all_null_expected_is_a_lookup_failure():
    """⛔ 예정일 있는 줄이 0개면 판정할 것이 없다 — 서버 규칙이 깨진 것이지 '지난 것 없음'이 아니다."""
    rows = [dict(r, next_expected=None) for r in live_like_rows()]
    with pytest.raises(cdf.fd.CallFailed, match="10줄 모두"):
        cdf.check_rows(rows)


@pytest.mark.parametrize("bad", ["2026-13-40", "2026/10/31", "", 20261031, ["2026-10-31"]])
def test_non_date_expected_is_a_lookup_failure_naming_the_row(bad):
    """⛔ null 도 날짜도 아닌 예정일 — 조용히 건너뛰면 그 자료는 영영 판정 밖이다."""
    rows = live_like_rows()
    rows[5] = dict(rows[5], next_expected=bad)
    with pytest.raises(cdf.fd.CallFailed, match="건축 인허가"):
        cdf.check_rows(rows)


def test_live_like_rows_pass_the_shape_check():
    assert cdf.check_rows(live_like_rows()) == live_like_rows()


# ── 호출 모양 ─────────────────────────────────────────────────────────────────


def test_calls_the_api_function_with_profile_header(monkeypatch):
    calls = install_fake_urlopen(monkeypatch, live_like_rows())
    cdf.fetch_rows(URL, KEY)
    assert len(calls) == 1
    assert calls[0]["url"] == URL + "/rest/v1/rpc/get_data_freshness"
    assert calls[0]["headers"]["content-profile"] == "api"
    assert calls[0]["headers"]["apikey"] == KEY
    assert calls[0]["headers"]["authorization"] == "Bearer " + KEY
    assert json.loads(calls[0]["data"]) == {}


# ── main: 종료코드 ────────────────────────────────────────────────────────────


def test_missing_credentials_has_its_own_exit_code(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("SANGGA_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SANGGA_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    assert cdf.main([]) == cdf.EXIT_NO_CREDENTIALS == 3
    assert "SANGGA_SUPABASE_URL" in capsys.readouterr().out


def test_nothing_overdue_exits_zero_and_writes_no_issue(monkeypatch, tmp_path):
    out = set_env(monkeypatch, tmp_path)
    install_fake_urlopen(monkeypatch, live_like_rows())
    assert cdf.main(["--today", "2026-10-01"]) == cdf.EXIT_OK == 0
    got = outputs(out)
    assert got["overdue"] == "false"
    assert issue_files(tmp_path) == []


def test_overdue_exits_one_with_one_issue_per_row(monkeypatch, tmp_path, capsys):
    out = set_env(monkeypatch, tmp_path)
    install_fake_urlopen(monkeypatch, live_like_rows())
    assert cdf.main(["--today", "2026-11-02"]) == cdf.EXIT_OVERDUE == 1
    got = outputs(out)
    assert got == {"overdue": "true", "count": "3"}, "자료 이름(창고 값)은 GITHUB_OUTPUT 에 싣지 않는다"
    issues = issue_files(tmp_path)
    assert [t for t, _ in issues] == [
        "갱신 예정일이 지난 자료 — 점포·업종 (상권정보) (예정 2026-10-31)",
        "갱신 예정일이 지난 자료 — 건축 인허가 (예정 2026-10-31)",
        "갱신 예정일이 지난 자료 — 상권 임대 동향 (부동산원) (예정 2026-10-31)",
    ]
    body = issues[1][1]
    assert "| 건축 인허가 | 기준월 202608 | 2026-10-31 | 2일 |" in body
    assert "점포·업종" not in body, "본문은 그 자료 것만"
    assert "포털에 새 판이 떴는지 확인 → 떴으면 적재" in body
    assert "적재해 해결했으면 이 이슈를 닫습니다" in body
    assert "아직 밀린 채 닫으면 다음 주에 다시 열립니다" in body
    printed = capsys.readouterr().out
    assert "건축 인허가" in printed and "2일 지남" in printed


def test_one_resolved_next_week_keeps_the_other_title(monkeypatch, tmp_path):
    """⛔ 두 자료가 지났다가 하나만 적재한 다음 주 — 남은 자료의 제목이 **그대로**여야 한다.

    그래야 워크플로가 열린 같은 제목을 보고 새 이슈를 안 연다. 제목에 건수·지난 날수가 들어가면
    여기서 제목이 바뀌어 같은 지남에 이슈가 하나 더 열리고 옛 이슈가 남는다.
    """
    set_env(monkeypatch, tmp_path)
    week1 = [row("건축 인허가", "2026-10-31"), row("상권 임대 동향 (부동산원)", "2026-10-31", basis="2026Q2")]
    install_fake_urlopen(monkeypatch, week1)
    assert cdf.main(["--today", "2026-11-02"]) == 1
    titles_week1 = [t for t, _ in issue_files(tmp_path)]

    # 부동산원을 적재해 예정일이 다음 분기로 넘어간 다음 주
    week2 = [row("건축 인허가", "2026-10-31"), row("상권 임대 동향 (부동산원)", "2027-01-31", basis="2026Q3")]
    install_fake_urlopen(monkeypatch, week2)
    assert cdf.main(["--today", "2026-11-09"]) == 1
    titles_week2 = [t for t, _ in issue_files(tmp_path)]

    assert titles_week2 == [titles_week1[0]], "남은 자료 하나 — 제목이 지난주와 같아야 한다"


def test_title_is_stable_week_to_week():
    item1 = cdf.find_overdue([row("건축 인허가", "2026-10-31")], D(2026, 11, 2))[0]
    item2 = cdf.find_overdue([row("건축 인허가", "2026-10-31")], D(2026, 12, 7))[0]
    assert cdf.build_issue_title(item1) == cdf.build_issue_title(item2) == (
        "갱신 예정일이 지난 자료 — 건축 인허가 (예정 2026-10-31)"
    )


def test_title_folds_newlines_from_the_database():
    """자료 이름은 창고가 준다 — 줄바꿈이 섞여도 제목은 한 줄이다(워크플로가 파일 한 줄로 읽는다)."""
    item = cdf.find_overdue([row("가\n나  다", "2026-10-31")], D(2026, 11, 2))[0]
    assert cdf.build_issue_title(item) == "갱신 예정일이 지난 자료 — 가 나 다 (예정 2026-10-31)"


def test_rerun_removes_stale_issue_files(monkeypatch, tmp_path):
    """로컬에서 거듭 돌려도 해결된 자료의 파일이 남아 섞이지 않는다."""
    set_env(monkeypatch, tmp_path)
    install_fake_urlopen(monkeypatch, live_like_rows())
    assert cdf.main(["--today", "2026-11-02"]) == 1
    assert len(issue_files(tmp_path)) == 3
    assert cdf.main(["--today", "2026-10-01"]) == 0
    assert issue_files(tmp_path) == []


def test_body_says_no_data_instead_of_none():
    item = cdf.find_overdue([row("국세청 기준시가", "2027-03-31", basis=None)], D(2027, 4, 2))[0]
    body = cdf.build_issue_body(item, D(2027, 4, 2))
    assert "(자료 없음)" in body and "None" not in body


def test_today_comes_from_korean_clock_when_not_given(monkeypatch, tmp_path):
    """--today 를 안 주면 today_kst() 를 쓴다(실제 시각 대신 가짜를 끼워 확인)."""
    set_env(monkeypatch, tmp_path)
    install_fake_urlopen(monkeypatch, live_like_rows())
    monkeypatch.setattr(cdf, "today_kst", lambda now=None: D(2026, 11, 2))
    assert cdf.main([]) == 1
    monkeypatch.setattr(cdf, "today_kst", lambda now=None: D(2026, 10, 31))
    assert cdf.main([]) == 0


def _assert_lookup_failed(monkeypatch, tmp_path, capsys, out):
    assert cdf.main(["--today", "2026-11-02"]) == cdf.EXIT_LOOKUP_FAILED == 2
    assert "[실패]" in capsys.readouterr().out
    assert outputs(out) == {}, "실패한 주에는 '지난 것 없음'도 '있음'도 넘기지 않는다"
    assert issue_files(tmp_path) == []


def test_zero_rows_exits_two_not_zero(monkeypatch, tmp_path, capsys):
    """⛔ 0줄을 '지난 것 없음(0)'으로 끝내면 감시가 장님이 된 채 매주 초록불을 켠다."""
    out = set_env(monkeypatch, tmp_path)
    install_fake_urlopen(monkeypatch, [])
    _assert_lookup_failed(monkeypatch, tmp_path, capsys, out)


def test_all_null_expected_exits_two_not_zero(monkeypatch, tmp_path, capsys):
    out = set_env(monkeypatch, tmp_path)
    install_fake_urlopen(monkeypatch, [dict(r, next_expected=None) for r in live_like_rows()])
    _assert_lookup_failed(monkeypatch, tmp_path, capsys, out)


def test_non_date_expected_exits_two(monkeypatch, tmp_path, capsys):
    out = set_env(monkeypatch, tmp_path)
    rows = live_like_rows()
    rows[0] = dict(rows[0], next_expected="2026-10-32")
    install_fake_urlopen(monkeypatch, rows)
    _assert_lookup_failed(monkeypatch, tmp_path, capsys, out)


def test_wrong_shape_exits_two(monkeypatch, tmp_path, capsys):
    out = set_env(monkeypatch, tmp_path)
    install_fake_urlopen(monkeypatch, {"message": "oops"})
    _assert_lookup_failed(monkeypatch, tmp_path, capsys, out)


def test_http_error_exits_two(monkeypatch, tmp_path, capsys):
    out = set_env(monkeypatch, tmp_path)
    err = urllib.error.HTTPError(URL, 404, "Not Found", None, None)
    calls = install_fake_urlopen(monkeypatch, err)
    _assert_lookup_failed(monkeypatch, tmp_path, capsys, out)
    assert len(calls) == 1, "404 는 다시 물어도 같다 — 한 번만 두드린다"


def test_connection_failure_retries_then_exits_two(monkeypatch, tmp_path, capsys):
    """창고가 죽은 주 — 몇 번 다시 묻고(대기는 가짜) 조회 실패로 끝난다."""
    out = set_env(monkeypatch, tmp_path)
    calls = install_fake_urlopen(monkeypatch, urllib.error.URLError("down"))
    _assert_lookup_failed(monkeypatch, tmp_path, capsys, out)
    assert len(calls) == cdf.fd.RETRY_COUNT


@pytest.mark.parametrize("fake", [
    FakeResponse(read_error=http.client.IncompleteRead(b"[{")),  # 응답이 도중에 끊김
    FakeResponse(raw=b"\xff\xfe\xfd"),                            # UTF-8 이 아닌 본문
    http.client.BadStatusLine("garbage"),                        # 상태 줄이 깨진 응답
], ids=["IncompleteRead", "UnicodeDecodeError", "BadStatusLine"])
def test_unexpected_exceptions_exit_two_not_one(monkeypatch, tmp_path, capsys, fake):
    """⛔ rpc() 가 못 잡는 예외 — 그대로 새면 파이썬 기본값 1(= "지난 줄 있음")이 된다."""
    out = set_env(monkeypatch, tmp_path)
    install_fake_urlopen(monkeypatch, fake)
    _assert_lookup_failed(monkeypatch, tmp_path, capsys, out)


def test_malformed_url_exits_two_not_one(monkeypatch, tmp_path, capsys):
    """잘못 넣은 주소(스킴 없음)는 Request 를 만들 때 ValueError — 이것도 조회 실패다."""
    out = set_env(monkeypatch, tmp_path)
    monkeypatch.setenv("SANGGA_SUPABASE_URL", "not-a-url")
    _assert_lookup_failed(monkeypatch, tmp_path, capsys, out)


# ── 조회 뒤 결과를 쓰다 죽음 = 4 (1 과 겹치면 워크플로가 조용히 초록) ───────────


@pytest.mark.parametrize("today, overdue_cnt", [("2026-11-02", 3), ("2026-10-01", 0)],
                         ids=["지남", "안지남"])
def test_unwritable_github_output_exits_four_not_one(monkeypatch, tmp_path, capsys, today, overdue_cnt):
    """⛔ 이슈 파일을 다 쓴 뒤 GITHUB_OUTPUT 에서 죽는 경로 — 기본값 1 이면 '지남'과 겹친다.

    GITHUB_OUTPUT 을 폴더로 가리켜 실제로 open 이 실패하게 만든다(윈도우·리눅스 공통).
    """
    set_env(monkeypatch, tmp_path)
    blocked = tmp_path / "gh_output_is_a_folder"
    blocked.mkdir()
    monkeypatch.setenv("GITHUB_OUTPUT", str(blocked))
    install_fake_urlopen(monkeypatch, live_like_rows())
    assert cdf.main(["--today", today]) == cdf.EXIT_OUTPUT_FAILED == 4
    out = capsys.readouterr().out
    assert "[실패] 결과를 쓰는 중" in out and "알림이 안 나갔을 수 있습니다" in out
    assert len(issue_files(tmp_path)) == overdue_cnt, "이슈 파일은 이미 써졌다 — 그래도 1 이 아니다"


@pytest.mark.parametrize("stage", ["report", "write_issue_files", "write_github_output"])
def test_any_failure_after_lookup_exits_four(monkeypatch, tmp_path, capsys, stage):
    """조회가 끝난 뒤 화면 출력·이슈 파일·GITHUB_OUTPUT 어디서 죽든 4 다(1·0 아님)."""
    set_env(monkeypatch, tmp_path)
    install_fake_urlopen(monkeypatch, live_like_rows())

    def boom(*_a, **_kw):
        raise OSError("디스크가 가득 찼습니다")

    monkeypatch.setattr(cdf, stage, boom)
    assert cdf.main(["--today", "2026-11-02"]) == cdf.EXIT_OUTPUT_FAILED
    assert "OSError: 디스크가 가득 찼습니다" in capsys.readouterr().out


def test_exit_codes_are_distinct_and_documented():
    codes = [cdf.EXIT_OK, cdf.EXIT_OVERDUE, cdf.EXIT_LOOKUP_FAILED, cdf.EXIT_NO_CREDENTIALS,
             cdf.EXIT_OUTPUT_FAILED]
    assert codes == [0, 1, 2, 3, 4]
    assert "4 = 조회는 됐는데 결과" in cdf.__doc__


def test_github_output_is_noop_outside_actions(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert cdf.write_github_output([]) is False


def test_issue_folder_and_temp_files_are_gitignored():
    """로컬에서 돌리면 생기는 출력이 커밋에 딸려 들어가지 않게(형제 감시와 같은 처방)."""
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
        ignored = set(f.read().splitlines())
    assert cdf.ISSUE_DIR + "/" in ignored
    assert "data_freshness_issue_full.md" in ignored
    assert "data_freshness_failure_issue.md" in ignored


# ── 워크플로 배선 ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def workflow_text():
    with open(WORKFLOW, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


def _steps(workflow):
    return workflow["jobs"]["watch"]["steps"]


def _step(workflow, name):
    matches = [s for s in _steps(workflow) if s.get("name") == name]
    assert matches, f"'{name}' 단계를 워크플로에서 못 찾았습니다"
    return matches[0]


def _crons(text):
    return [
        line.split("cron:", 1)[1].strip().strip('"')
        for line in text.splitlines()
        if "cron:" in line and not line.strip().startswith("#")
    ]


class TestWorkflow:
    """본보기는 의견함 주간 알림(같은 변수) + LH 공고 감시(종료코드 0/1/2 가르기)."""

    def test_parses_and_runs_weekly_on_monday(self, workflow, workflow_text):
        on = workflow.get("on", workflow.get(True))
        assert "workflow_dispatch" in on
        assert _crons(workflow_text) == ["0 2 * * 1"]

    def test_schedule_does_not_collide_with_siblings(self, workflow_text):
        """같은 시각에 몰리면 큐가 밀릴 때 함께 드롭된다."""
        mine = set(_crons(workflow_text))
        for name in os.listdir(WORKFLOW_DIR):
            if name == os.path.basename(WORKFLOW) or not name.endswith(".yml"):
                continue
            with open(os.path.join(WORKFLOW_DIR, name), encoding="utf-8") as f:
                assert not mine & set(_crons(f.read())), name

    def test_minimal_permissions(self, workflow):
        assert workflow["permissions"] == {
            "contents": "read", "issues": "write", "actions": "read",
        }

    def test_uses_variables_not_secrets(self, workflow_text):
        """⛔ URL·공개키는 비밀값이 아니다 — 의견함 주간 알림과 같은 vars.* 두 개."""
        assert "vars.SANGGA_SUPABASE_URL" in workflow_text
        assert "vars.SANGGA_SUPABASE_ANON_KEY" in workflow_text
        assert "secrets." not in workflow_text

    def test_missing_vars_opens_an_issue_without_failing_the_job(self, workflow):
        step = _step(workflow, "변수가 없으면 그 사실을 알린다")
        assert step["if"] == "steps.creds.outputs.ready == 'false'"
        assert ".github/data-freshness-setup-issue.md" in step["run"]
        assert os.path.exists(os.path.join(ROOT, ".github", "data-freshness-setup-issue.md"))
        for name in ("창고 주소·공개키가 있나", "변수가 없으면 그 사실을 알린다"):
            assert "exit 1" not in _step(workflow, name)["run"]

    def test_check_step_separates_overdue_from_failure(self, workflow):
        """1(지남)은 job 을 살리고, 그 밖(2·3)은 job 을 실패시켜 실패 알림으로 보낸다."""
        step = _step(workflow, "예정일이 지난 자료가 있는지 확인")
        run = step["run"]
        assert "python scripts/check_data_freshness.py" in run
        assert '[ "$rc" -eq 0 ] || [ "$rc" -eq 1 ]' in run
        assert 'exit "$rc"' in run
        assert "continue-on-error" not in step

    def test_check_step_treats_one_without_issue_files_as_failure(self, workflow):
        """⛔ 잡지 못한 예외도 파이썬은 1 로 끝낸다 — 이슈 파일이 없으면 '지남'이 아니라 실패다.

        이 검사가 0·1 통과보다 **먼저** 와야 한다(뒤에 있으면 이미 exit 0 으로 빠져나간다).
        """
        run = _step(workflow, "예정일이 지난 자료가 있는지 확인")["run"]
        guard = '[ "$rc" -eq 1 ] && ! ls {}/*.md'.format(cdf.ISSUE_DIR)
        assert guard in run
        assert run.index(guard) < run.index('[ "$rc" -eq 0 ] || [ "$rc" -eq 1 ]')

    def test_issue_step_loops_over_the_files_the_script_writes(self, workflow):
        step = _step(workflow, "지난 자료마다 이슈를 연다")
        assert step["if"] == "steps.check.outputs.overdue == 'true'"
        run = step["run"]
        assert "for body in {}/*.md".format(cdf.ISSUE_DIR) in run
        assert '"${body%.md}.title"' in run
        assert "--body-file" in run

    def test_issue_dedup_looks_at_open_only_per_row(self, workflow):
        """열린 같은 제목이면 **그 자료만** 건너뛴다(continue) — 나머지 자료는 계속 연다."""
        run = _step(workflow, "지난 자료마다 이슈를 연다")["run"]
        assert "--state open" in run and "grep -Fxq" in run
        assert "continue" in run
        assert "exit 0" not in run

    def test_database_values_never_enter_run_via_expressions(self, workflow, workflow_text):
        """⛔ 자료 이름은 창고가 준 값이다 — `${{ }}` 로 run 에 끼우면 주입 통로가 된다."""
        assert "steps.check.outputs.title" not in workflow_text
        for step in _steps(workflow):
            assert "${{" not in step.get("run", ""), step.get("name")

    def test_failure_step_is_last_and_loud(self, workflow):
        step = _steps(workflow)[-1]
        assert step["name"] == "감시가 실패하면 그 사실을 이슈로 알린다"
        assert step["if"] == "failure()"
        assert "--state open" in step["run"]
        assert ".github/data-freshness-failure-issue.md" in step["run"]
        assert os.path.exists(os.path.join(ROOT, ".github", "data-freshness-failure-issue.md"))

    def test_heartbeat_step_survives_and_cannot_fail_the_job(self, workflow):
        step = _step(workflow, "형제 감시들이 아직 도는지 확인")
        assert step["if"] == "${{ !cancelled() }}"
        assert step["continue-on-error"] is True

    def test_watches_all_siblings_and_is_in_the_net(self, workflow_text):
        """⛔ 그물은 양방향이다 — 새 예약이 형제를 보고, 형제가 새 예약을 본다."""
        mine = os.path.basename(WORKFLOW)
        assert mine == hb.DATA_FRESHNESS_WATCH
        assert mine in hb.DEFAULT_WORKFLOWS
        assert len(hb.DEFAULT_WORKFLOWS) == 6
        for other in hb.DEFAULT_WORKFLOWS:
            if other != mine:
                assert "--workflow {}".format(other) in workflow_text
        assert "--workflow {}".format(mine) not in workflow_text

    def test_weekly_threshold_applies(self):
        """주 1회 예약이라 기준은 기본값(8일)이다 — 6시간 감시용 1일이 붙으면 헛알림이 매주 뜬다."""
        assert hb.max_age_for(hb.DATA_FRESHNESS_WATCH) == hb.DEFAULT_MAX_AGE_DAYS
        assert hb.label_of(hb.DATA_FRESHNESS_WATCH) == "지난 날짜 감시"


# ── 워크플로 단계를 실제로 bash 로 돌려 본다 ─────────────────────────────────
#
# 글자 검사만으로는 `<<< "$OPEN_TITLES"` 를 `<<< ""` 로 바꿔도 초록이었다(2026-10-01 실측).
# 그래서 단계의 run: 글자를 꺼내 GitHub 기본 셸(`bash -e` — `shell:` 을 안 적은 단계의 기본값,
# 2026-10-01 run 36870678169 로그에 `shell: /usr/bin/bash -e {0}` 로 찍힘)로 돌리고, PATH 앞에
# 가짜 `gh`·`python` 을 둔다. 네트워크·진짜 gh 는 타지 않는다. pipefail 은 단계가 스스로
# `set -euo pipefail` 로 켜는 것만 따른다(기본 셸에는 없다).
# 윈도우는 Git Bash 로 돈다(WSL 의 System32 bash 는 PATH·경로를 다르게 풀어 건너뛴다).
# ⛔ CI 에서는 bash 가 없으면 건너뛰지 않고 실패한다 — 거기서 조용히 skip 되면 이 시험이 지키는
#    빈틈(열린 제목 건너뛰기·overdue 기록 검사)이 아무도 모르게 다시 열린다.


def _find_bash():
    path = shutil.which("bash")
    if not path:
        return None
    low = path.lower()
    if os.name == "nt" and ("system32" in low or "windowsapps" in low):
        return None
    return path


def _write_lf(path, text):
    """줄 끝을 LF 로 — CRLF 가 섞이면 bash 가 `\\r` 을 명령 글자로 읽는다."""
    path.write_bytes(text.encode("utf-8"))
    path.chmod(0o755)


def _run_step(workflow, name, tmp_path, fakes, env_extra):
    bash = _find_bash()
    if bash is None:
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            pytest.fail("CI 인데 bash 를 못 찾았습니다 — 워크플로 단계 실행 시험을 건너뛸 수 없습니다")
        pytest.skip("bash 가 없습니다(윈도우는 Git Bash 필요)")
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    for fname, body in fakes.items():
        _write_lf(bin_dir / fname, body)
    _write_lf(tmp_path / "step.sh", _step(workflow, name)["run"])
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env.update(env_extra)
    return subprocess.run(
        [bash, "-e", "step.sh"],
        cwd=str(tmp_path), env=env, capture_output=True, timeout=60,
    )


FAKE_PYTHON = """#!/bin/sh
# 가짜 check_data_freshness.py — 시나리오대로 파일·기록을 남기고 정한 코드로 끝난다.
if [ -n "$FAKE_FILES" ]; then
  mkdir -p data_freshness_issues
  printf 't\\n' > data_freshness_issues/01.title
  printf 'b\\n' > data_freshness_issues/01.md
fi
if [ -n "$FAKE_OUTPUT" ]; then
  printf 'overdue=true\\ncount=1\\n' >> "$GITHUB_OUTPUT"
fi
exit "$FAKE_RC"
"""


@pytest.mark.parametrize("rc, files, output, expect", [
    (1, True, True, 0),     # 지남 — 이슈 파일 + overdue=true 둘 다 → 통과
    (1, True, False, 1),    # ⛔ 이슈 파일만 있고 기록 없음 → 도중에 죽음 (A2)
    (1, False, True, 1),    # ⛔ 기록만 있고 이슈 파일 없음 → 도중에 죽음
    (1, False, False, 1),   # 잡지 못한 예외의 기본값 1
    (0, False, False, 0),   # 지난 것 없음
    (2, False, False, 2),   # 조회 실패 → 실패 알림
    (4, True, False, 4),    # 결과를 쓰다 실패 → 실패 알림
], ids=["1-둘다", "1-파일만", "1-기록만", "1-둘다없음", "0", "2", "4"])
def test_check_step_runs_for_real(workflow, tmp_path, rc, files, output, expect):
    gh_output = tmp_path / "gh_output"
    gh_output.write_bytes(b"")
    res = _run_step(workflow, "예정일이 지난 자료가 있는지 확인", tmp_path, {"python": FAKE_PYTHON}, {
        "FAKE_RC": str(rc),
        "FAKE_FILES": "1" if files else "",
        "FAKE_OUTPUT": "1" if output else "",
        "GITHUB_OUTPUT": "gh_output",
    })
    said = res.stdout.decode("utf-8", "replace") + res.stderr.decode("utf-8", "replace")
    assert res.returncode == expect, said
    if (rc, files, output) == (1, True, False):
        assert "overdue=true 기록이 없습니다" in said


FAKE_GH = """#!/bin/sh
# 가짜 gh — issue list 는 열린 제목 파일을, issue create 는 --title 값을 기록 파일에 덧붙인다.
if [ "$1" = "issue" ] && [ "$2" = "list" ]; then
  cat open_titles.txt
  exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "create" ]; then
  shift 2
  while [ $# -gt 0 ]; do
    if [ "$1" = "--title" ]; then printf '%s\\n' "$2" >> created.txt; fi
    shift
  done
  exit 0
fi
echo "예상 못 한 gh 호출: $*" >&2
exit 99
"""


def test_issue_step_skips_only_the_open_title_for_real(workflow, tmp_path):
    """열린 제목은 **그 자료만** 건너뛰고 나머지는 연다 — 단계를 실제로 돌려 확인한다.

    `<<< ""` 로 바꾸면(열린 제목을 안 봄) 01 도 열려 빨강, `continue` 를 지우면 01 도 열려 빨강.
    """
    t1 = "갱신 예정일이 지난 자료 — 건축 인허가 (예정 2026-10-31)"
    t2 = "갱신 예정일이 지난 자료 — 상권 임대 동향 (부동산원) (예정 2026-10-31)"
    folder = tmp_path / cdf.ISSUE_DIR
    folder.mkdir()
    for stem, title in (("01", t1), ("02", t2)):
        (folder / (stem + ".title")).write_bytes((title + "\n").encode("utf-8"))
        (folder / (stem + ".md")).write_bytes("본문\n".encode("utf-8"))
    (tmp_path / "open_titles.txt").write_bytes((t1 + "\n다른 이슈 제목\n").encode("utf-8"))

    res = _run_step(workflow, "지난 자료마다 이슈를 연다", tmp_path, {"gh": FAKE_GH}, {
        "GH_TOKEN": "fake", "RUN_URL": "https://example.test/run/1",
    })
    said = res.stdout.decode("utf-8", "replace") + res.stderr.decode("utf-8", "replace")
    assert res.returncode == 0, said
    created = (tmp_path / "created.txt").read_bytes().decode("utf-8").splitlines()
    assert created == [t2], said
