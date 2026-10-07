# -*- coding: utf-8 -*-
"""
scripts/check_watch_heartbeat.py 1:1 단위 테스트.

네트워크는 전부 monkeypatch로 막는다(실제 GitHub API에 접속하지 않음).
공용 설정 파일(conftest.py 등) 없이 이 파일 안에서 import 경로를 직접 해결한다.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import check_watch_heartbeat as chk  # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)


def _dt(days_ago):
    """NOW 기준 며칠 전 시각. **judge() 처럼 now 를 주입받는 함수에만** 쓴다."""
    return NOW - datetime.timedelta(days=days_ago)


def _recent(hours_ago):
    """**지금(실제 시각)** 기준 몇 시간 전.

    ⛔ `main()` 은 now 를 주입받지 않고 실제 시각을 쓴다. 그래서 main 테스트에 고정 상수
       NOW 기준 값을 주면 **날이 갈수록 나이가 벌어져 언젠가 저절로 깨진다** — 코드는 한
       줄도 안 고쳤는데 어느 날 빨간불이 되는 시한폭탄이다(2026-08-24 라이브 감시 기준을
       1일로 조인 순간 실제로 터졌다. 그 전에는 8일 기준이라 안 보였을 뿐이다).
       ⇒ main 을 부르는 테스트는 반드시 이 상대값을 쓴다.
    """
    return datetime.datetime.now(UTC) - datetime.timedelta(hours=hours_ago)


# 아래 자동 고정물이 갈아끼우기 전의 진짜 재확인 함수 — 연결부(주소 → 응답 → 파서) 시험이 되돌려 쓴다.
_REAL_FETCH_RECENT_SUCCESS = chk.fetch_recent_success


@pytest.fixture(autouse=True)
def _no_recheck_network(monkeypatch):
    """멈춤이 나오면 main 이 재확인(`fetch_recent_success`)을 부른다 — 기본은 '더 새로운 성공 없음'.

    ⛔ 이걸 안 막으면 멈춤을 다루는 기존 main 시험이 진짜 GitHub 을 두드린다(실패하면 재시도
       대기 15초). 재확인 자체를 보는 시험은 각자 다시 갈아끼운다.
    """
    monkeypatch.setattr(chk, "fetch_recent_success", lambda f: None)


# ── 시각 읽기 ─────────────────────────────────────────────────────────────────


def test_parse_iso_utc_handles_github_z_format():
    """GitHub 는 `2026-08-17T00:31:12Z` 형태로 준다."""
    got = chk.parse_iso_utc("2026-08-17T00:31:12Z")
    assert got == datetime.datetime(2026, 8, 17, 0, 31, 12, tzinfo=UTC)


def test_parse_iso_utc_handles_offset_format():
    """형식이 오프셋 표기로 바뀌어도 같은 순간으로 읽어야 한다."""
    got = chk.parse_iso_utc("2026-08-17T09:31:12+09:00")
    assert got == datetime.datetime(2026, 8, 17, 0, 31, 12, tzinfo=UTC)


def test_parse_iso_utc_assumes_utc_when_no_zone():
    """시간대가 없다고 로컬시각으로 오해하면 한국에서만 9시간 어긋난다."""
    got = chk.parse_iso_utc("2026-08-17T00:31:12")
    assert got == datetime.datetime(2026, 8, 17, 0, 31, 12, tzinfo=UTC)


@pytest.mark.parametrize("bad", ["", "   ", "어제", "2026-13-99T00:00:00Z"])
def test_parse_iso_utc_raises_on_garbage(bad):
    with pytest.raises(ValueError):
        chk.parse_iso_utc(bad)


# ── 응답에서 마지막 성공 뽑기 ─────────────────────────────────────────────────


def test_parse_latest_success_reads_run_started_at():
    payload = {
        "total_count": 1,
        "workflow_runs": [
            {"run_started_at": "2026-08-17T00:31:12Z", "created_at": "2026-08-17T00:30:00Z"}
        ],
    }
    assert chk.parse_latest_success(payload) == datetime.datetime(
        2026, 8, 17, 0, 31, 12, tzinfo=UTC
    )


def test_parse_latest_success_falls_back_to_created_at():
    """옛 실행 기록에는 run_started_at 이 없을 수 있다."""
    payload = {"workflow_runs": [{"created_at": "2026-08-17T00:30:00Z"}]}
    assert chk.parse_latest_success(payload) == datetime.datetime(
        2026, 8, 17, 0, 30, 0, tzinfo=UTC
    )


def test_parse_latest_success_returns_none_when_never_ran():
    """성공 기록이 0건이면 '언제 돌았는지 모른다' — 이것도 사람이 봐야 할 상태다."""
    assert chk.parse_latest_success({"total_count": 0, "workflow_runs": []}) is None


def test_parse_latest_success_raises_when_key_missing():
    """조용히 None 을 돌려주면 '한 번도 안 돌았다'와 구분이 안 돼 헛알림이 된다."""
    with pytest.raises(ValueError) as e:
        chk.parse_latest_success({"message": "Not Found"})
    assert "workflow_runs" in str(e.value)


@pytest.mark.parametrize("bad", [None, [], "문자열", {"workflow_runs": "목록아님"}])
def test_parse_latest_success_raises_on_wrong_shape(bad):
    with pytest.raises(ValueError):
        chk.parse_latest_success(bad)


def test_parse_latest_success_raises_when_run_has_no_timestamp():
    with pytest.raises(ValueError):
        chk.parse_latest_success({"workflow_runs": [{"id": 1}]})


# ── 나이 재기 ─────────────────────────────────────────────────────────────────


def test_age_days_counts_whole_days():
    assert chk.age_days(_dt(8), NOW) == pytest.approx(8.0)


def test_age_days_counts_fractions():
    assert chk.age_days(NOW - datetime.timedelta(hours=12), NOW) == pytest.approx(0.5)


# ── 판정 ──────────────────────────────────────────────────────────────────────


def test_judge_says_fresh_when_ran_this_week():
    results = [(chk.QUARTERLY_WATCH, _dt(3)), (chk.DISTRICT_WATCH, _dt(3))]
    assert chk.judge(results, max_age_days=8, now=NOW) == []


def test_judge_boundary_is_exclusive():
    """딱 기준일이면 아직 정상이다 — 큐가 조금 밀린 정상 상황을 헛알림으로 만들지 않는다."""
    assert chk.judge([(chk.QUARTERLY_WATCH, _dt(8))], max_age_days=8, now=NOW) == []


def test_judge_flags_just_over_the_boundary():
    stale = chk.judge([(chk.QUARTERLY_WATCH, _dt(8.5))], max_age_days=8, now=NOW)
    assert len(stale) == 1
    assert stale[0]["workflow"] == chk.QUARTERLY_WATCH
    assert stale[0]["age_days"] == pytest.approx(8.5)


def test_judge_flags_never_ran():
    stale = chk.judge([(chk.DISTRICT_WATCH, None)], max_age_days=8, now=NOW)
    assert len(stale) == 1
    assert stale[0]["last_success"] is None
    assert stale[0]["age_days"] is None
    assert "없습니다" in stale[0]["reason"]


def test_judge_keeps_given_order():
    """순서가 흔들리면 제목이 달라져 중복 방지(제목 비교)가 깨진다."""
    results = [(chk.QUARTERLY_WATCH, _dt(30)), (chk.DISTRICT_WATCH, _dt(30))]
    assert [s["workflow"] for s in chk.judge(results, 8, NOW)] == [
        chk.QUARTERLY_WATCH,
        chk.DISTRICT_WATCH,
    ]


def test_judge_only_flags_the_stale_one():
    results = [(chk.QUARTERLY_WATCH, _dt(1)), (chk.DISTRICT_WATCH, _dt(70))]
    stale = chk.judge(results, 8, NOW)
    assert [s["workflow"] for s in stale] == [chk.DISTRICT_WATCH]


def test_judge_handles_empty_input():
    assert chk.judge([], 8, NOW) == []
    assert chk.judge(None, 8, NOW) == []


def test_judge_uses_labels_people_can_read():
    stale = chk.judge([(chk.DISTRICT_WATCH, _dt(70))], 8, NOW)
    assert stale[0]["label"] == "상권 원천 감시"


def test_label_of_falls_back_to_filename():
    assert chk.label_of("낯선-워크플로우.yml") == "낯선-워크플로우.yml"


# ── 이슈 제목·본문 ────────────────────────────────────────────────────────────


def test_issue_title_has_no_date_so_dedup_works():
    """제목에 날짜를 박으면 매주 제목이 달라져 같은 사고로 이슈가 계속 쌓인다."""
    stale = chk.judge([(chk.DISTRICT_WATCH, _dt(70))], 8, NOW)
    title = chk.build_issue_title(stale)
    assert title == "감시 예약이 멈춘 것 같습니다: 상권 원천 감시"
    assert "2026" not in title


def test_issue_title_is_deterministic_for_both():
    stale = chk.judge(
        [(chk.QUARTERLY_WATCH, _dt(70)), (chk.DISTRICT_WATCH, _dt(70))], 8, NOW
    )
    assert chk.build_issue_title(stale) == (
        "감시 예약이 멈춘 것 같습니다: 분기 스냅샷 감시, 상권 원천 감시"
    )


def test_issue_body_shows_the_stale_workflow_and_how_to_revive_it():
    stale = chk.judge([(chk.DISTRICT_WATCH, _dt(70))], 8, NOW)
    body = chk.build_issue_body(stale, max_age_days=8)
    assert "상권 원천 감시" in body
    assert "60일" in body, "왜 멈추는지 사람이 알아야 다시 켤 수 있다"
    assert "Enable workflow" in body
    assert chk.DISTRICT_WATCH in body, "Actions 바로가기가 있어야 손이 안 헤맨다"
    assert "check_watch_heartbeat.py" in body, "내 PC에서 확인할 명령이 있어야 한다"


def test_issue_body_commands_run_in_powershell():
    """사장님 터미널은 PowerShell 이다 — `cd /d/sangga` 는 거기서 안 된다(2026-08-22)."""
    body = chk.build_issue_body(chk.judge([(chk.DISTRICT_WATCH, _dt(70))], 8, NOW))
    assert r"cd D:\sangga" in body
    assert "/d/sangga" not in body
    assert "```bash" not in body


def test_issue_body_shows_never_ran_without_a_fake_date():
    stale = chk.judge([(chk.QUARTERLY_WATCH, None)], 8, NOW)
    body = chk.build_issue_body(stale)
    assert "기록 없음" in body
    assert "None" not in body


def test_issue_body_reports_the_threshold_actually_used():
    stale = chk.judge([(chk.QUARTERLY_WATCH, _dt(70))], 30, NOW)
    assert "**30일**" in chk.build_issue_body(stale, max_age_days=30)


# ── 조회 주소 ─────────────────────────────────────────────────────────────────


def test_runs_url_asks_for_one_successful_run():
    url = chk.runs_url(chk.QUARTERLY_WATCH)
    assert url.startswith("https://api.github.com/repos/developer-duno/sangga/")
    assert "/actions/workflows/{}/runs".format(chk.QUARTERLY_WATCH) in url
    assert "status=success" in url
    assert "per_page=1" in url


# ── 재시도 ────────────────────────────────────────────────────────────────────


def _http_error(code):
    return urllib.error.HTTPError("https://api.github.com/x", code, "테스트", {}, None)


def _counting_retry(monkeypatch, raiser):
    """호출 횟수와 기다린 시간을 세면서 _get_json_with_retry 를 돌린다."""
    calls = []
    waits = []

    def fake_get(url, timeout=None):
        calls.append(url)
        raise raiser(len(calls))

    monkeypatch.setattr(chk, "_get_json", fake_get)
    with pytest.raises(Exception) as e:
        chk._get_json_with_retry("https://api.github.com/x", sleep=waits.append)
    return calls, waits, e.value


@pytest.mark.parametrize("code", sorted(chk.NO_RETRY_HTTP_CODES))
def test_retry_gives_up_at_once_on_codes_a_human_must_fix(monkeypatch, code):
    """404(파일명 드리프트)·403(권한 회수) 등은 15초를 더 기다려도 같은 답이 온다."""
    calls, waits, err = _counting_retry(monkeypatch, lambda _n: _http_error(code))
    assert len(calls) == 1, "재시도하면 시간만 버린다"
    assert waits == [], "기다리지도 말아야 한다"
    assert isinstance(err, urllib.error.HTTPError) and err.code == code


@pytest.mark.parametrize("code", [500, 502, 503, 429])
def test_retry_keeps_trying_on_codes_that_may_clear(monkeypatch, code):
    """5xx·429 는 다음 시도에 풀릴 수 있다 — 한 번에 포기하면 감시가 일주일을 건너뛴다."""
    calls, waits, _ = _counting_retry(monkeypatch, lambda _n: _http_error(code))
    assert len(calls) == chk.RETRY_COUNT
    assert waits == [5, 10], "5초 → 10초 백오프"


def test_retry_keeps_trying_on_timeout(monkeypatch):
    """간헐적 연결 끊김이 재시도가 존재하는 원래 이유다."""
    calls, waits, _ = _counting_retry(monkeypatch, lambda _n: TimeoutError("연결 끊김"))
    assert len(calls) == chk.RETRY_COUNT
    assert waits == [5, 10]


def test_retry_returns_the_first_success(monkeypatch):
    """두 번째 시도에서 풀리면 그 값을 그대로 쓴다."""
    calls = []

    def flaky(url, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError("연결 끊김")
        return {"workflow_runs": []}

    monkeypatch.setattr(chk, "_get_json", flaky)
    got = chk._get_json_with_retry("https://api.github.com/x", sleep=lambda _s: None)
    assert got == {"workflow_runs": []}
    assert len(calls) == 2


# ── GITHUB_OUTPUT ────────────────────────────────────────────────────────────


def test_write_github_output_noop_without_env(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert chk.write_github_output(chk.judge([(chk.DISTRICT_WATCH, _dt(70))], 8, NOW)) is False


def test_write_github_output_writes_stale_true(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    chk.write_github_output(chk.judge([(chk.DISTRICT_WATCH, _dt(70))], 8, NOW))
    text = out.read_text(encoding="utf-8")
    assert "stale=true" in text
    assert "title=감시 예약이 멈춘 것 같습니다: 상권 원천 감시" in text


def test_write_github_output_writes_stale_false(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    chk.write_github_output([])
    text = out.read_text(encoding="utf-8")
    assert "stale=false" in text
    # 빈 제목이어야 다음 단계가 이슈를 열지 않는다
    assert "title=\n" in text


# ── main() 흐름 ───────────────────────────────────────────────────────────────


def _patch_fetch(monkeypatch, mapping):
    """네트워크를 타지 않게 조회 함수를 갈아끼운다."""
    monkeypatch.setattr(chk, "fetch_latest_success", lambda f: mapping[f])


def _patch_created(monkeypatch, mapping):
    """'언제 만들었나' 조회를 갈아끼운다.

    ⚠️ main 은 **성공 기록이 없는 것에만** 이걸 묻는다. 그래서 mapping 에 그 워크플로가
       빠져 있으면 KeyError 로 시끄럽게 터진다 — 조용히 지나가면 테스트가 무엇을 검증한
       건지 알 수 없어진다.
    """
    monkeypatch.setattr(chk, "fetch_created_at", lambda f: mapping[f])


def test_main_returns_zero_when_everything_is_fresh(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.QUARTERLY_WATCH: _recent(48), chk.DISTRICT_WATCH: _recent(48),
                           # 라이브 감시는 6시간마다 돌므로 기준이 1일이다 — 이틀 전이면 이미 멈춘 것.
                           chk.LIVE_HEALTH_WATCH: _recent(3),
                           # 주간 알림도 예약이라 같은 그물 안에 있다(2026-08-24c).
                           chk.FEEDBACK_DIGEST: _recent(48),
                           # LH 공고 감시도 주 1회 예약이다(2026-08-28a).
                           chk.LH_NOTICE_WATCH: _recent(48),
                           # 지난 날짜 감시도 주 1회 예약이다(2026-10-01).
                           chk.DATA_FRESHNESS_WATCH: _recent(48)})
    assert chk.main([]) == 0
    assert "멈춘 감시           : 없음" in capsys.readouterr().out
    # 멈춘 게 없으면 이슈 본문 파일을 만들지 않는다
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_returns_one_and_writes_issue_body_when_stale(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.QUARTERLY_WATCH: _recent(48), chk.DISTRICT_WATCH: _recent(70 * 24),
                           chk.LIVE_HEALTH_WATCH: _recent(3),
                           # 주간 알림도 예약이라 같은 그물 안에 있다(2026-08-24c).
                           chk.FEEDBACK_DIGEST: _recent(48),
                           # LH 공고 감시도 주 1회 예약이다(2026-08-28a).
                           chk.LH_NOTICE_WATCH: _recent(48),
                           # 지난 날짜 감시도 주 1회 예약이다(2026-10-01).
                           chk.DATA_FRESHNESS_WATCH: _recent(48)})
    assert chk.main([]) == 1
    body = (tmp_path / chk.ISSUE_BODY_FILE).read_text(encoding="utf-8")
    assert "상권 원천 감시" in body
    # 멀쩡한 쪽까지 이슈에 적으면 사람이 엉뚱한 워크플로우를 들여다본다
    assert "분기 스냅샷 감시" not in body


def test_main_checks_only_the_workflow_asked_for(monkeypatch, tmp_path):
    """상호 감시는 **상대 하나만** 본다 — 자기 자신은 지금 돌고 있으니 볼 필요가 없다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    asked = []

    def fake(f):
        asked.append(f)
        # main() 은 실제 시계를 쓴다 — 고정 상수(_dt)를 주면 날이 갈수록 늙어
        # 저절로 깨진다(2026-08-30 CI 실사고: 8-29 초록 → 8-30 빨강, 코드 변경 0).
        return _recent(24)

    monkeypatch.setattr(chk, "fetch_latest_success", fake)
    assert chk.main(["--workflow", chk.DISTRICT_WATCH]) == 0
    assert asked == [chk.DISTRICT_WATCH]


def test_main_honors_max_age_days(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.DISTRICT_WATCH: _recent(20 * 24)})
    assert chk.main(["--workflow", chk.DISTRICT_WATCH]) == 1
    assert chk.main(["--workflow", chk.DISTRICT_WATCH, "--max-age-days", "30"]) == 0


def test_main_returns_two_when_lookup_fails(monkeypatch, capsys, tmp_path):
    """'감시가 멈췄다'와 '내가 확인을 못 했다'는 서로 다른 사건이라 코드를 가른다."""
    monkeypatch.chdir(tmp_path)

    def boom(_f):
        raise RuntimeError("연결 실패")

    monkeypatch.setattr(chk, "fetch_latest_success", boom)
    assert chk.main([]) == 2
    assert "실행 기록 조회 실패" in capsys.readouterr().err
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_writes_github_output_for_the_next_step(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    _patch_fetch(monkeypatch, {chk.DISTRICT_WATCH: _recent(70 * 24)})
    assert chk.main(["--workflow", chk.DISTRICT_WATCH]) == 1
    assert "stale=true" in out.read_text(encoding="utf-8")


def test_main_json_output(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.QUARTERLY_WATCH: _recent(48), chk.DISTRICT_WATCH: None,
                           chk.LIVE_HEALTH_WATCH: _recent(3),
                           # 주간 알림도 예약이라 같은 그물 안에 있다(2026-08-24c).
                           chk.FEEDBACK_DIGEST: _recent(48),
                           # LH 공고 감시도 주 1회 예약이다(2026-08-28a).
                           chk.LH_NOTICE_WATCH: _recent(48),
                           # 지난 날짜 감시도 주 1회 예약이다(2026-10-01).
                           chk.DATA_FRESHNESS_WATCH: _recent(48)})
    # 기록이 없는 쪽은 "언제 만들었나"를 되묻는다 — 오래전에 만든 것이라 유예 대상이 아니다.
    _patch_created(monkeypatch, {chk.DISTRICT_WATCH: _recent(70 * 24)})
    assert chk.main(["--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["max_age_days"] == chk.DEFAULT_MAX_AGE_DAYS
    assert [c["workflow"] for c in data["checked"]] == list(chk.DEFAULT_WORKFLOWS)
    assert [s["workflow"] for s in data["stale"]] == [chk.DISTRICT_WATCH]


def test_main_does_not_touch_network(monkeypatch, tmp_path):
    """테스트가 실수로 진짜 GitHub 을 두드리지 않는지 못을 박는다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    def forbidden(*a, **k):
        raise AssertionError("테스트가 네트워크를 탔습니다")

    monkeypatch.setattr(chk.urllib.request, "urlopen", forbidden)
    _patch_fetch(monkeypatch, {chk.QUARTERLY_WATCH: _recent(24), chk.DISTRICT_WATCH: _recent(24),
                           chk.LIVE_HEALTH_WATCH: _recent(3),
                           # 주간 알림도 예약이라 같은 그물 안에 있다(2026-08-24c).
                           chk.FEEDBACK_DIGEST: _recent(48),
                           # LH 공고 감시도 주 1회 예약이다(2026-08-28a).
                           chk.LH_NOTICE_WATCH: _recent(48),
                           # 지난 날짜 감시도 주 1회 예약이다(2026-10-01).
                           chk.DATA_FRESHNESS_WATCH: _recent(48)})
    assert chk.main([]) == 0


# ── 갓 만든 워크플로 유예 (2026-08-28 이슈 #98) ───────────────────────────────
#
# 주 1회 예약을 금요일에 머지하면 첫 슬롯(월요일)까지 성공 기록이 0건이다. 그걸 멈춤으로
# 읽으면 태어나자마자 부고가 뜬다. 그렇다고 기록 없음을 통째로 봐주면 cron 오타로 영영
# 안 도는 진짜 고장을 놓친다 — 그래서 **만든 지 얼마나 됐나**로 둘을 가른다.


def test_newborn_workflow_is_not_stale_yet():
    """오늘 만든 주간 예약은 아직 첫 슬롯을 기다리는 중이다."""
    results = [(chk.LH_NOTICE_WATCH, None)]
    assert chk.judge(results, 8, NOW, created_at={chk.LH_NOTICE_WATCH: _dt(2)}) == []


def test_old_workflow_with_no_runs_is_still_stale():
    """⛔ 만든 지 기준일을 넘겼는데 기록이 0건이면 진짜 고장이다(cron 오타 등).

    여기서 봐주면 유예가 '영구 면제'로 변해 감시가 통째로 눈을 감는다.
    """
    stale = chk.judge(
        [(chk.LH_NOTICE_WATCH, None)], 8, NOW, created_at={chk.LH_NOTICE_WATCH: _dt(30)}
    )
    assert len(stale) == 1
    assert stale[0]["workflow"] == chk.LH_NOTICE_WATCH
    assert "없습니다" in stale[0]["reason"]


def test_newborn_grace_boundary_matches_the_judge_boundary():
    """딱 기준일이면 아직 유예 — judge 의 경계(초과할 때만 알림)와 같은 쪽으로 맞춘다."""
    assert chk.judge(
        [(chk.LH_NOTICE_WATCH, None)], 8, NOW, created_at={chk.LH_NOTICE_WATCH: _dt(8)}
    ) == []
    assert len(chk.judge(
        [(chk.LH_NOTICE_WATCH, None)], 8, NOW, created_at={chk.LH_NOTICE_WATCH: _dt(8.5)}
    )) == 1


def test_newborn_grace_uses_each_workflows_own_threshold():
    """6시간마다 도는 감시는 하루면 이미 여러 번 돌았어야 한다 — 이틀은 유예가 아니다."""
    two_days = {chk.LIVE_HEALTH_WATCH: _dt(2), chk.QUARTERLY_WATCH: _dt(2)}
    assert len(chk.judge([(chk.LIVE_HEALTH_WATCH, None)], 8, NOW, created_at=two_days)) == 1
    assert chk.judge([(chk.QUARTERLY_WATCH, None)], 8, NOW, created_at=two_days) == []


def test_unknown_birth_date_does_not_grant_grace():
    """⛔ 만든 시각을 모른다는 이유로 봐주면, 조회가 어긋난 순간부터 영영 봐주게 된다."""
    assert chk.is_newborn(chk.LH_NOTICE_WATCH, None, NOW) is False
    assert len(chk.judge([(chk.LH_NOTICE_WATCH, None)], 8, NOW, created_at={})) == 1
    # created_at 을 아예 안 넘기던 옛 호출도 그대로 동작해야 한다
    assert len(chk.judge([(chk.LH_NOTICE_WATCH, None)], 8, NOW)) == 1


def test_grace_does_not_touch_workflows_that_did_run():
    """기록이 있는 쪽은 만든 시각과 무관하게 나이로만 판정한다."""
    born = {chk.LH_NOTICE_WATCH: _dt(1)}
    stale = chk.judge([(chk.LH_NOTICE_WATCH, _dt(30))], 8, NOW, created_at=born)
    assert len(stale) == 1, "갓 만들었어도 '한 달째 안 돎'은 멈춘 것이다"


# ── 만든 시각 읽기 ────────────────────────────────────────────────────────────


def test_parse_created_at_reads_the_workflow_meta():
    """⚠️ 이 응답의 시각에는 밀리초가 붙는다(라이브 실측 `2026-08-28T05:27:50.000Z`).

    실행 기록 쪽에는 안 붙어서 형식이 서로 다르다 — 여기서 못 읽으면 유예가 통째로 죽는다.
    """
    payload = {"id": 1, "path": ".github/workflows/x.yml", "created_at": "2026-08-28T05:27:50.000Z"}
    assert chk.parse_created_at(payload) == datetime.datetime(
        2026, 8, 28, 5, 27, 50, tzinfo=UTC
    )


@pytest.mark.parametrize("bad", [None, [], "문자열", {}, {"created_at": ""}])
def test_parse_created_at_raises_on_wrong_shape(bad):
    """조용히 None 을 돌려주면 '못 읽었다'가 '갓 만든 게 아니다'로 둔갑한다."""
    with pytest.raises(ValueError):
        chk.parse_created_at(bad)


def test_workflow_url_points_at_the_workflow_itself():
    """실행 목록(/runs)이 아니라 워크플로우 자체를 물어야 created_at 이 온다."""
    url = chk.workflow_url(chk.LH_NOTICE_WATCH)
    assert url == "https://api.github.com/repos/developer-duno/sangga/actions/workflows/{}".format(
        chk.LH_NOTICE_WATCH
    )
    assert "/runs" not in url


def test_created_at_map_asks_nothing_when_everything_ran(monkeypatch):
    """평소(전부 잘 도는 주)에는 API 호출을 하나도 더 얹지 않는다."""
    def forbidden(_f):
        raise AssertionError("물어볼 것이 없는데 조회했습니다")

    monkeypatch.setattr(chk, "fetch_created_at", forbidden)
    assert chk.fetch_created_at_map([]) == {}


# ── main() 에서의 신생 유예 ───────────────────────────────────────────────────


def _all_fresh_but(missing):
    """`missing` 하나만 기록 없음, 나머지는 최근에 돈 것으로 채운다."""
    fresh = {chk.QUARTERLY_WATCH: _recent(48), chk.DISTRICT_WATCH: _recent(48),
             chk.LIVE_HEALTH_WATCH: _recent(3), chk.FEEDBACK_DIGEST: _recent(48),
             chk.LH_NOTICE_WATCH: _recent(48),
             chk.DATA_FRESHNESS_WATCH: _recent(48)}
    fresh[missing] = None
    return fresh


def test_main_says_zero_for_a_just_merged_workflow(monkeypatch, capsys, tmp_path):
    """갓 머지된 예약에 부고를 띄우지 않는다 — 2026-08-28 이슈 #98 이 그 사고였다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, _all_fresh_but(chk.LH_NOTICE_WATCH))
    # main 은 실제 시계를 쓴다 — 고정 날짜를 주면 날이 갈수록 늙어 저절로 깨진다.
    _patch_created(monkeypatch, {chk.LH_NOTICE_WATCH: _recent(24)})

    assert chk.main([]) == 0
    out = capsys.readouterr().out
    assert "갓 만들어져 첫 예약을 기다리는 중" in out, "왜 봐줬는지 사람이 읽을 수 있어야 한다"
    assert "멈춘 감시           : 없음" in out
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists(), "이슈를 열면 안 된다"


def test_main_still_alarms_when_an_old_workflow_never_ran(monkeypatch, tmp_path):
    """만든 지 오래됐는데 한 번도 안 돌았으면 그건 유예가 아니라 고장이다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, _all_fresh_but(chk.LH_NOTICE_WATCH))
    _patch_created(monkeypatch, {chk.LH_NOTICE_WATCH: _recent(40 * 24)})

    assert chk.main([]) == 1
    body = (tmp_path / chk.ISSUE_BODY_FILE).read_text(encoding="utf-8")
    assert "LH 공고 감시" in body
    assert "기록 없음" in body


def test_main_returns_two_when_the_birth_date_lookup_fails(monkeypatch, capsys, tmp_path):
    """⛔ 못 물어봤으면 '멈췄다'가 아니라 '확인을 못 했다'다.

    여기서 1(멈춤)로 답하면 GitHub 이 잠깐 흔들린 것만으로 헛이슈가 열리고, 0(정상)으로
    답하면 진짜 고장을 덮는다. 기존 조회 실패와 같은 결로 2 를 낸다.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, _all_fresh_but(chk.LH_NOTICE_WATCH))

    def boom(_f):
        raise RuntimeError("연결 실패")

    monkeypatch.setattr(chk, "fetch_created_at", boom)
    assert chk.main([]) == 2
    assert "실행 기록 조회 실패" in capsys.readouterr().err
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_json_marks_the_newborn(monkeypatch, capsys, tmp_path):
    """기계용 출력에서도 '기록 없음'과 '갓 만들어짐'이 구분돼야 한다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, _all_fresh_but(chk.LH_NOTICE_WATCH))
    _patch_created(monkeypatch, {chk.LH_NOTICE_WATCH: _recent(24)})

    assert chk.main(["--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    newborn = [c["workflow"] for c in data["checked"] if c["newborn"]]
    assert newborn == [chk.LH_NOTICE_WATCH]
    assert data["stale"] == []


# ── 멈춤 판정 전 재확인 (2026-10-01 헛경보 #177) ─────────────────────────────
#
# GitHub 가 `status=success&per_page=1` 에 한 번 옛 답(09-17)을 줘, 6시간마다 잘 도는 라이브
# 감시에 "14일째 멈춤" 이슈가 열렸다. 멈춤으로 나온 것만 거름망 없는 목록으로 한 번 더 묻는다.


def _run(conclusion, started=None, created=None):
    run = {"conclusion": conclusion}
    if started:
        run["run_started_at"] = started
    if created:
        run["created_at"] = created
    return run


def test_recent_runs_url_has_no_status_filter():
    url = chk.recent_runs_url(chk.LIVE_HEALTH_WATCH)
    assert url == (
        "https://api.github.com/repos/developer-duno/sangga/actions/workflows/"
        "{}/runs?per_page=20".format(chk.LIVE_HEALTH_WATCH)
    )
    assert "status=" not in url


def test_among_picks_the_latest_success_and_skips_the_rest():
    payload = {"workflow_runs": [
        _run(None, "2026-10-01T18:36:00Z"),          # 아직 도는 중
        _run("failure", "2026-10-01T12:36:00Z"),
        _run("success", "2026-10-01T06:36:13Z"),
        _run("cancelled", "2026-10-01T03:00:00Z"),
        _run("success", "2026-09-30T18:36:00Z"),
    ]}
    assert chk.parse_latest_success_among(payload) == datetime.datetime(
        2026, 10, 1, 6, 36, 13, tzinfo=UTC
    )


def test_among_does_not_trust_list_order():
    payload = {"workflow_runs": [
        _run("success", "2026-09-17T12:32:00Z"),
        _run("success", "2026-10-01T12:36:13Z"),
    ]}
    assert chk.parse_latest_success_among(payload).day == 1


def test_among_uses_the_same_time_rule_as_the_first_answer():
    """run_started_at 이 없으면 created_at — parse_latest_success 와 같은 규칙."""
    payload = {"workflow_runs": [_run("success", created="2026-10-01T12:00:00Z")]}
    assert chk.parse_latest_success_among(payload) == datetime.datetime(
        2026, 10, 1, 12, 0, tzinfo=UTC
    )


def test_among_returns_none_without_any_success():
    assert chk.parse_latest_success_among({"workflow_runs": []}) is None
    assert chk.parse_latest_success_among({"workflow_runs": [_run("failure", "2026-10-01T00:00:00Z")]}) is None


@pytest.mark.parametrize("bad", [None, [], "문자열", {}, {"workflow_runs": "x"}])
def test_among_raises_on_wrong_shape(bad):
    with pytest.raises(ValueError):
        chk.parse_latest_success_among(bad)


def test_recheck_replaces_only_with_a_newer_success(monkeypatch):
    first = [(chk.LIVE_HEALTH_WATCH, _dt(14)), (chk.DISTRICT_WATCH, _dt(20))]
    stale = chk.judge(first, 8, NOW)
    answers = {chk.LIVE_HEALTH_WATCH: _dt(0.1), chk.DISTRICT_WATCH: _dt(30)}  # 하나는 더 옛날
    monkeypatch.setattr(chk, "fetch_recent_success", lambda f: answers[f])
    got = chk.recheck_stale(first, stale)
    assert got == [(chk.LIVE_HEALTH_WATCH, _dt(0.1)), (chk.DISTRICT_WATCH, _dt(20))]


def test_recheck_asks_only_the_stale_ones(monkeypatch):
    asked = []
    monkeypatch.setattr(chk, "fetch_recent_success", lambda f: asked.append(f))
    first = [(chk.QUARTERLY_WATCH, _dt(1)), (chk.LIVE_HEALTH_WATCH, _dt(14))]
    chk.recheck_stale(first, chk.judge(first, 8, NOW))
    assert asked == [chk.LIVE_HEALTH_WATCH]


def test_main_drops_the_false_alarm_when_recheck_is_fresh(monkeypatch, capsys, tmp_path):
    """#177 그대로: 첫 답 14일 전, 재확인은 몇 시간 전 → 멈춤 아님(이슈 안 엶)."""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    _patch_fetch(monkeypatch, {chk.LIVE_HEALTH_WATCH: _recent(14 * 24)})
    monkeypatch.setattr(chk, "fetch_recent_success", lambda f: _recent(2))
    assert chk.main(["--workflow", chk.LIVE_HEALTH_WATCH]) == 0
    captured = capsys.readouterr()
    assert "멈춘 감시           : 없음" in captured.out
    assert "재확인(라이브 생존 감시)" in captured.err
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()
    assert "stale=false" in out.read_text(encoding="utf-8")


def test_main_still_alarms_when_both_answers_are_old(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.LIVE_HEALTH_WATCH: _recent(14 * 24)})
    monkeypatch.setattr(chk, "fetch_recent_success", lambda f: _recent(10 * 24))
    assert chk.main(["--workflow", chk.LIVE_HEALTH_WATCH]) == 1
    assert "라이브 생존 감시" in (tmp_path / chk.ISSUE_BODY_FILE).read_text(encoding="utf-8")


def test_main_keeps_the_alarm_when_recheck_fails(monkeypatch, capsys, tmp_path):
    """⛔ 진짜 멈춤 + 재확인 실패가 겹쳐도 알림은 남는다 — 2(조회 실패)·0(침묵)으로 안 바꾼다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.LIVE_HEALTH_WATCH: _recent(14 * 24)})

    def boom(_f):
        raise RuntimeError("연결 실패")

    monkeypatch.setattr(chk, "fetch_recent_success", boom)
    assert chk.main(["--workflow", chk.LIVE_HEALTH_WATCH]) == 1
    assert "재확인 실패(라이브 생존 감시)" in capsys.readouterr().err
    assert (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_rechecks_never_ran_too(monkeypatch, tmp_path):
    """'성공 기록 없음(갓 만든 것 아님)'도 재확인 대상이다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.LH_NOTICE_WATCH: None})
    _patch_created(monkeypatch, {chk.LH_NOTICE_WATCH: _recent(40 * 24)})
    monkeypatch.setattr(chk, "fetch_recent_success", lambda f: _recent(48))
    assert chk.main(["--workflow", chk.LH_NOTICE_WATCH]) == 0


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_main_recheck_wiring_url_response_parser(monkeypatch, capsys, tmp_path):
    """연결부: 재확인이 **거름망 없는 주소**로 묻고, 그 응답에서 **가장 늦은 성공**을 고른다.

    자동 고정물이 `fetch_recent_success` 를 통째로 바꿔 두므로 여기서 진짜를 되돌리고, 더 아래
    `_get_json_with_retry` 만 가짜로 둔다(부른 주소를 기록). 재확인이 `runs_url` 을 쓰거나
    (`status=success&per_page=1` → 옛 답), 맨 앞 1건만 보면(`parse_latest_success`) 멈춤이 안 풀린다.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(chk, "fetch_recent_success", _REAL_FETCH_RECENT_SUCCESS)
    stale_answer = {"workflow_runs": [_run("success", _iso(_recent(14 * 24)))]}  # #177 의 옛 답
    mixed = {"workflow_runs": [                       # 순서가 섞인 최근 실행 목록
        _run("success", _iso(_recent(10 * 24))),      # 맨 앞은 옛 성공 — 1건만 보면 여기서 멈춘다
        _run("failure", _iso(_recent(1))),
        _run(None, _iso(_recent(0.5))),               # 아직 도는 중
        _run("success", _iso(_recent(3))),            # ← 가장 늦은 성공
        _run("cancelled", _iso(_recent(2))),
        _run("success", _iso(_recent(9))),
    ]}
    asked = []

    def fake_get(url, **_kw):
        asked.append(url)
        return stale_answer if "status=success" in url else mixed

    monkeypatch.setattr(chk, "_get_json_with_retry", fake_get)
    assert chk.main(["--workflow", chk.LIVE_HEALTH_WATCH]) == 0
    assert asked == [chk.runs_url(chk.LIVE_HEALTH_WATCH), chk.recent_runs_url(chk.LIVE_HEALTH_WATCH)]
    recheck = asked[1]
    assert "status=" not in recheck and recheck.endswith("per_page=20")
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()
    assert "마지막 성공" in capsys.readouterr().out


def test_main_recheck_wiring_keeps_alarm_when_list_is_old_too(monkeypatch, tmp_path):
    """연결부 반대쪽: 거름망 없는 목록에서도 성공이 오래됐으면(실패만 최근) 멈춤 그대로."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(chk, "fetch_recent_success", _REAL_FETCH_RECENT_SUCCESS)
    stale_answer = {"workflow_runs": [_run("success", _iso(_recent(14 * 24)))]}
    only_failures_recent = {"workflow_runs": [
        _run("failure", _iso(_recent(1))),
        _run("success", _iso(_recent(14 * 24))),
    ]}
    monkeypatch.setattr(
        chk, "_get_json_with_retry",
        lambda url, **_kw: stale_answer if "status=success" in url else only_failures_recent,
    )
    assert chk.main(["--workflow", chk.LIVE_HEALTH_WATCH]) == 1
    assert (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_makes_no_extra_call_when_nothing_is_stale(monkeypatch, tmp_path):
    """평소 경로(멈춤 없음)에는 재확인 호출이 0회다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    asked = []
    monkeypatch.setattr(chk, "fetch_recent_success", lambda f: asked.append(f))
    _patch_fetch(monkeypatch, _all_fresh_but(chk.LH_NOTICE_WATCH) | {chk.LH_NOTICE_WATCH: _recent(48)})
    assert chk.main([]) == 0
    assert asked == []


# ── 상호 감시 배선 점검 (한쪽만 걸려 있으면 반쪽 감시가 된다) ────────────────

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_DIR = os.path.join(REPO_ROOT, ".github", "workflows")


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_watched_workflow_files_actually_exist(name):
    """파일명을 바꾸고 이 상수를 안 고치면 조회가 404 로 계속 실패한다."""
    assert os.path.exists(os.path.join(WORKFLOW_DIR, name)), name


@pytest.mark.parametrize("mine", chk.DEFAULT_WORKFLOWS)
def test_each_watch_checks_all_the_others(mine):
    """⛔ 감시마다 **나머지 전부**를 봐야 한다.

    둘일 때는 "서로 본다"로 충분했지만 셋이 되면 그 표현이 구멍을 남긴다 — A가 B만 보고
    C를 아무도 안 보면, C가 죽어도 영영 모른다(2026-08-24 라이브 감시를 넣을 때 실제로
    그 상태였다). 그래서 "나머지 전부"로 못을 박는다.
    """
    wf = _read_text(os.path.join(WORKFLOW_DIR, mine))
    for other in chk.DEFAULT_WORKFLOWS:
        if other == mine:
            continue
        assert "--workflow {}".format(other) in wf, "{} 가 {} 를 안 본다".format(mine, other)


@pytest.mark.parametrize("mine", chk.DEFAULT_WORKFLOWS)
def test_no_watch_checks_itself(mine):
    """자기 자신을 보는 것은 아무 뜻이 없다 — 지금 도는 중이니 늘 '정상'이다."""
    wf = _read_text(os.path.join(WORKFLOW_DIR, mine))
    assert "--workflow {}".format(mine) not in wf


@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_each_watch_can_read_run_history(name):
    """actions: read 가 없으면 실행 기록 조회가 403 으로 막힌다."""
    assert "actions: read" in _read_text(os.path.join(WORKFLOW_DIR, name))


@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_heartbeat_step_cannot_fail_the_job(name):
    """하트비트가 job 을 실패시키면 failure() 가 **엉뚱한** 실패 이슈를 연다."""
    wf = _read_text(os.path.join(WORKFLOW_DIR, name))
    assert "continue-on-error: true" in wf


@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_heartbeat_still_runs_when_my_own_watch_failed(name):
    """내가 아픈 주야말로 상대까지 조용해지면 안 되는 주다.

    앞 단계가 실패하면 job status 가 failure 라 뒤 단계가 통째로 건너뛰어진다 —
    08-10 사고("예약은 도는데 실패")가 정확히 그 상태였다.
    """
    wf = _read_text(os.path.join(WORKFLOW_DIR, name))
    assert "if: ${{ !cancelled() }}" in wf


@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_heartbeat_issue_step_also_survives_a_failed_watch(name):
    """판정 단계만 살리고 알림 단계를 놔두면 암묵적 success() 에서 다시 막힌다.

    ⓘ 2026-10-01 그물 6호 때 분기·상권 둘에서 **예약 전부**로 넓혔다 — 새 워크플로에서
       `!cancelled() &&` 를 지워도 초록이던 것을 검사관이 잡았다.
    """
    wf = _read_text(os.path.join(WORKFLOW_DIR, name))
    assert "if: ${{ !cancelled() && steps.heartbeat.outputs.stale == 'true' }}" in wf


@pytest.mark.parametrize("name", [chk.QUARTERLY_WATCH, chk.DISTRICT_WATCH])
def test_workflow_uses_the_issue_body_this_script_writes(name):
    """스크립트가 쓰는 파일명과 워크플로우가 읽는 파일명이 어긋나면 이슈가 빈 채로 열린다."""
    wf = _read_text(os.path.join(WORKFLOW_DIR, name))
    assert chk.ISSUE_BODY_FILE in wf
    assert "steps.heartbeat.outputs.stale == 'true'" in wf


@pytest.mark.parametrize("name", [chk.QUARTERLY_WATCH, chk.DISTRICT_WATCH])
def test_heartbeat_issue_dedup_only_skips_open_ones(name):
    """닫힌 것까지 세면 한 번 닫은 뒤로는 영영 다시 안 알린다."""
    wf = _read_text(os.path.join(WORKFLOW_DIR, name))
    assert wf.count("gh issue list --state open") >= 2


# ── 기준값 자체 점검 ──────────────────────────────────────────────────────────


def test_default_max_age_covers_one_missed_weekly_run():
    """주 1회 예약이므로 7일은 정상 간격이다 — 그보다 커야 헛알림이 안 난다."""
    assert chk.DEFAULT_MAX_AGE_DAYS > 7


def test_default_max_age_is_shorter_than_github_auto_disable():
    """60일 자동중지가 실제로 걸리기 훨씬 전에 알아야 손 쓸 시간이 있다."""
    assert chk.DEFAULT_MAX_AGE_DAYS < 60


# ── 워크플로우마다 다른 기준 (2026-08-24 적대검증 반영) ─────────────────────────


def test_live_health_watch_has_a_tighter_threshold():
    """⛔ 6시간마다 도는 감시에 8일 기준을 쓰면, 그것이 죽어 라이브가 무너져도 일주일을 모른다.

    감시의 감시가 감시보다 굼뜨면 있으나 마나다.
    """
    assert chk.max_age_for(chk.LIVE_HEALTH_WATCH) == 1.0
    assert chk.max_age_for(chk.QUARTERLY_WATCH) == chk.DEFAULT_MAX_AGE_DAYS
    assert chk.max_age_for(chk.DISTRICT_WATCH) == chk.DEFAULT_MAX_AGE_DAYS


def test_user_can_tighten_but_not_loosen_the_tight_one():
    """사람이 더 짧게 주면 따르고, 더 길게 줘도 짧은 기준은 지킨다(놓치는 것보다 시끄러운 게 낫다)."""
    assert chk.max_age_for(chk.LIVE_HEALTH_WATCH, 0.5) == 0.5
    assert chk.max_age_for(chk.LIVE_HEALTH_WATCH, 30) == 1.0
    assert chk.max_age_for(chk.QUARTERLY_WATCH, 30) == 30


def test_live_health_watch_stale_after_a_day():
    """하루 넘게 성공 기록이 없으면 멈춘 것으로 본다."""
    stale = chk.judge([(chk.LIVE_HEALTH_WATCH, _dt(1.5))], now=NOW)
    assert len(stale) == 1
    assert stale[0]["label"] == "라이브 생존 감시"

    # 반나절이면 정상 (6시간 주기라 한두 번 걸러도 여유가 있다)
    assert chk.judge([(chk.LIVE_HEALTH_WATCH, _dt(0.4))], now=NOW) == []


def test_default_workflows_covers_every_scheduled_workflow():
    """예약을 새로 만들고 여기 안 넣으면, 그것이 죽어도 아무도 모른다.

    ⚠️ 대상은 "감시"만이 아니다 — **예약으로 도는 것 전부**다. 의견함 주간 알림
    (2026-08-24c)은 감시가 아니라 알림이지만, 죽으면 우편함을 다시 아무도 안 읽게 되므로
    똑같이 지켜져야 한다. 그래서 이름을 '감시 3종'에서 '예약 전부'로 넓혔다.
    """
    assert set(chk.DEFAULT_WORKFLOWS) == {
        chk.QUARTERLY_WATCH,
        chk.DISTRICT_WATCH,
        chk.LIVE_HEALTH_WATCH,
        chk.FEEDBACK_DIGEST,
        chk.LH_NOTICE_WATCH,
        chk.DATA_FRESHNESS_WATCH,
    }
    for wf in chk.DEFAULT_WORKFLOWS:
        assert wf in chk.WORKFLOW_LABELS


def _workflow_files():
    return [
        n for n in sorted(os.listdir(WORKFLOW_DIR)) if n.endswith((".yml", ".yaml"))
    ]


@pytest.mark.parametrize("name", _workflow_files())
def test_workflow_yaml_actually_parses(name):
    """⛔ 깨진 워크플로는 에러가 아니라 **그냥 안 도는 것**으로 끝난다.

    GitHub 은 문법이 깨진 워크플로를 조용히 실행하지 않는다 — Actions 탭 어딘가에 표시는
    되지만 아무도 그걸 매일 보지 않는다. 이 레포가 가장 여러 번 데인 형태(조용한 누락)다.
    실제로 2026-08-24c 에서 이슈 본문을 워크플로 안에 직접 써 넣다 들여쓰기가 깨져
    **파일 전체가 안 읽히는 상태**를 만들었고, 손으로 파싱해 보고서야 알았다.

    ⓘ pyyaml 은 CI 설치 목록에 있다(ci.yml). 안 깔린 환경에서는 건너뛰므로, 이 검사가
      실제로 강제되는 곳은 CI 다 — pyshp 와 같은 방식.
    """
    yaml = pytest.importorskip("yaml")
    with open(os.path.join(WORKFLOW_DIR, name), encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    assert isinstance(doc, dict), "{}: 최상위가 매핑이 아닙니다".format(name)
    # YAML 은 `on:` 을 참(True)으로 읽는다(이른바 Norway 문제) — 둘 다 본다.
    assert "jobs" in doc and ("on" in doc or True in doc), (
        "{}: jobs/on 이 없습니다 — 워크플로로 인식되지 않습니다".format(name)
    )


def test_every_scheduled_workflow_file_is_in_the_net():
    """⛔ 거꾸로도 막는다 — .github/workflows 에 예약(schedule)이 있는데 그물 밖이면 사고다.

    위 테스트는 "상수에 적힌 것"만 본다. 그래서 새 예약 워크플로 파일을 만들고 상수를
    안 고치면 **양쪽 다 초록인 채로** 그물 밖에 남는다. 파일 쪽에서 한 번 더 센다.
    (CI 는 예약이 아니라 push 로 도는 것이라 대상이 아니다.)
    """
    scheduled = []
    for name in sorted(os.listdir(WORKFLOW_DIR)):
        if not name.endswith((".yml", ".yaml")):
            continue
        if "schedule:" in _read_text(os.path.join(WORKFLOW_DIR, name)):
            scheduled.append(name)

    missing = [n for n in scheduled if n not in chk.DEFAULT_WORKFLOWS]
    assert not missing, (
        "예약으로 도는데 상호 감시 그물 밖입니다: {} — check_watch_heartbeat.py 의 "
        "DEFAULT_WORKFLOWS 와 형제 워크플로의 --workflow 인자에 넣으세요.".format(missing)
    )


# ── 점검 자체가 고장 났을 때 — 판정 실패 2 · 결과 쓰기 실패 4 (2026-10-02) ─────
#
# 결과를 쓰다 죽으면 파이썬 기본값 1 = "멈춘 것이 있음"과 겹친다. 워크플로는 1 을 통과시키는데
# stale 기록이 없으면 이슈 단계가 건너뛰어져 아무 알림이 없다 — 그래서 4 로 따로 끝낸다.


def _all_fresh():
    return {chk.QUARTERLY_WATCH: _recent(48), chk.DISTRICT_WATCH: _recent(48),
            chk.LIVE_HEALTH_WATCH: _recent(3), chk.FEEDBACK_DIGEST: _recent(48),
            chk.LH_NOTICE_WATCH: _recent(48), chk.DATA_FRESHNESS_WATCH: _recent(48)}


def _one_stale():
    """라이브 감시 하나만 30일째 멈춘 것으로 — 나머지는 최근."""
    m = _all_fresh()
    m[chk.LIVE_HEALTH_WATCH] = _recent(24 * 30)
    return m


def test_exit_output_failed_is_four_and_distinct():
    assert chk.EXIT_OUTPUT_FAILED == 4
    assert chk.EXIT_OUTPUT_FAILED not in (0, 1, 2)


def test_main_returns_2_when_judging_raises(monkeypatch, capsys, tmp_path):
    """판정에서 난 예외(응답 모양이 바뀜 등)는 기본값 1 이 아니라 2 = 확인을 못 했다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, _all_fresh())

    def boom(*_a, **_kw):
        raise ValueError("모양이 바뀜")

    monkeypatch.setattr(chk, "judge", boom)
    assert chk.main([]) == 2
    assert "판정하는 중 ValueError" in capsys.readouterr().err
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_returns_2_when_recheck_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, _one_stale())

    def boom(*_a, **_kw):
        raise TypeError("재확인 모양")

    monkeypatch.setattr(chk, "recheck_stale", boom)
    assert chk.main([]) == 2


def test_main_returns_2_when_second_judge_raises(monkeypatch, tmp_path):
    """재확인 뒤 두 번째 판정에서 죽어도 2 다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, _one_stale())
    real_judge = chk.judge
    calls = []

    def judge_then_boom(*a, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise KeyError("두 번째")
        return real_judge(*a, **kw)

    monkeypatch.setattr(chk, "judge", judge_then_boom)
    assert chk.main([]) == 2
    assert len(calls) == 2


def test_main_returns_4_when_github_output_is_a_folder_and_nothing_is_stale(
        monkeypatch, capsys, tmp_path):
    """멈춤이 없어도 기록 쓰기가 **실제로** 실패하면 4 — 다음 단계가 읽을 값이 비는 것은 같다."""
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "out_is_a_folder"
    folder.mkdir()
    monkeypatch.setenv("GITHUB_OUTPUT", str(folder))
    _patch_fetch(monkeypatch, _all_fresh())
    assert chk.main([]) == chk.EXIT_OUTPUT_FAILED
    assert "결과를 쓰는 중" in capsys.readouterr().err


def test_main_returns_4_when_github_output_is_a_folder_and_one_is_stale(monkeypatch, tmp_path):
    """⛔ 이슈 본문 파일은 썼는데 기록에서 죽은 경우 — 예전에는 1 로 통과해 조용히 초록이었다."""
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "out_is_a_folder"
    folder.mkdir()
    monkeypatch.setenv("GITHUB_OUTPUT", str(folder))
    _patch_fetch(monkeypatch, _one_stale())
    assert chk.main([]) == chk.EXIT_OUTPUT_FAILED
    assert (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_returns_4_when_issue_body_path_is_a_folder(monkeypatch, tmp_path):
    """멈춤인데 이슈 본문 파일 자리가 폴더라 못 쓰면 4 — stale 기록도 안 남는다."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / chk.ISSUE_BODY_FILE).mkdir()
    out = tmp_path / "gh_output"
    out.write_bytes(b"")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    _patch_fetch(monkeypatch, _one_stale())
    assert chk.main([]) == chk.EXIT_OUTPUT_FAILED
    assert "stale=true" not in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("exc", [OSError, TypeError])
@pytest.mark.parametrize("stale", [False, True], ids=["멈춤없음", "멈춤"])
def test_main_returns_4_when_writing_the_record_raises(monkeypatch, tmp_path, exc, stale):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, _one_stale() if stale else _all_fresh())

    def boom(_stale):
        raise exc("기록 실패")

    monkeypatch.setattr(chk, "write_github_output", boom)
    assert chk.main([]) == chk.EXIT_OUTPUT_FAILED


@pytest.mark.parametrize("exc", [OSError, TypeError])
def test_main_returns_4_when_building_the_issue_body_raises(monkeypatch, tmp_path, exc):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, _one_stale())

    def boom(*_a, **_kw):
        raise exc("본문 실패")

    monkeypatch.setattr(chk, "build_issue_body", boom)
    assert chk.main([]) == chk.EXIT_OUTPUT_FAILED


@pytest.mark.parametrize("exc", [OSError, TypeError])
def test_main_returns_4_when_json_output_raises(monkeypatch, tmp_path, exc):
    """--json 출력에서 죽어도 4 — 화면 출력도 '결과 쓰기'다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, _all_fresh())

    def boom(*_a, **_kw):
        raise exc("화면 실패")

    monkeypatch.setattr(chk, "is_newborn", boom)
    assert chk.main(["--json"]) == chk.EXIT_OUTPUT_FAILED


def test_docstring_lists_exit_code_4():
    assert "4 = 조회는 됐는데 결과" in chk.__doc__


# ── 워크플로: 하트비트 단계가 고장을 가르고, 고장이면 이슈를 연다 (2026-10-02) ────
#
# 글자 검사만으로는 검사 줄을 지워도 초록이다(형제 지난 날짜 감시 2026-10-01 실측). 그래서
# 단계의 run: 글자를 꺼내 GitHub 기본 셸(`bash -e` — `shell:` 을 안 적은 단계의 기본값)로
# 돌리고, PATH 앞에 가짜 `python`·`gh` 를 둔다. 네트워크·진짜 API 는 타지 않는다.
# 윈도우는 Git Bash 로 돈다(WSL 의 System32 bash 는 PATH·경로를 다르게 풀어 건너뛴다).
# 도우미는 tests/test_check_data_freshness.py 의 것을 옮겨 왔다(시험 파일끼리 import 하지 않는다).
# 다른 점: job 이름이 워크플로마다 달라(watch·health·digest) **모든 job** 에서 단계를 찾는다.
# ⛔ CI 에서는 bash 가 없으면 건너뛰지 않고 실패한다 — 거기서 조용히 skip 되면 이 시험이 지키는
#    빈틈(고장 가르기·열린 제목 건너뛰기)이 아무도 모르게 다시 열린다.

FAILURE_STEP_NAME = "상호 감시 점검이 고장 났으면 이슈를 연다"
FAILURE_TITLE = "상호 감시 점검(하트비트)이 결과를 내지 못했습니다 — 사람이 직접 확인해 주세요"
FAILURE_BODY = os.path.join(REPO_ROOT, ".github", "watch-heartbeat-failure-issue.md")
FAILURE_IF = "${{ !cancelled() && steps.heartbeat.outcome == 'failure' }}"
STALE_IF = "${{ !cancelled() && steps.heartbeat.outputs.stale == 'true' }}"


def _load_workflow(name):
    import yaml

    with open(os.path.join(WORKFLOW_DIR, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _heartbeat_job_steps(workflow):
    """하트비트 단계(id: heartbeat)가 든 job 의 단계 목록."""
    found = [job["steps"] for job in workflow["jobs"].values()
             if any(s.get("id") == "heartbeat" for s in job["steps"])]
    assert len(found) == 1, "하트비트 단계가 든 job 이 하나가 아닙니다"
    return found[0]


def _find_step(workflow, key, value):
    steps = [s for job in workflow["jobs"].values() for s in job["steps"] if s.get(key) == value]
    assert steps, "{}={} 단계를 워크플로에서 못 찾았습니다".format(key, value)
    return steps[0]


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


def _run_step(step, tmp_path, fakes, env_extra):
    bash = _find_bash()
    if bash is None:
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            pytest.fail("CI 인데 bash 를 못 찾았습니다 — 워크플로 단계 실행 시험을 건너뛸 수 없습니다")
        pytest.skip("bash 가 없습니다(윈도우는 Git Bash 필요)")
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    for fname, body in fakes.items():
        _write_lf(bin_dir / fname, body)
    _write_lf(tmp_path / "step.sh", step["run"])
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env.update(env_extra)
    return subprocess.run(
        [bash, "-e", "step.sh"],
        cwd=str(tmp_path), env=env, capture_output=True, timeout=60,
    )


FAKE_PYTHON = """#!/bin/sh
# 가짜 check_watch_heartbeat.py — 시나리오대로 이슈 본문 파일·기록을 남기고 정한 코드로 끝난다.
if [ -n "$FAKE_FILES" ]; then
  printf 'b\\n' > watch_heartbeat_issue.md
fi
if [ -n "$FAKE_OUTPUT" ]; then
  printf 'stale=true\\ntitle=t\\n' >> "$GITHUB_OUTPUT"
fi
exit "$FAKE_RC"
"""


@pytest.mark.parametrize("rc, files, output, expect, said_part", [
    (0, False, False, 0, None),                                # 전부 최근
    (1, True, True, 0, None),                                  # 멈춤 — 이슈 파일 + stale=true 둘 다 → 통과
    (1, True, False, 1, "stale=true 기록이 없습니다"),             # ⛔ 이슈 파일만 → 도중에 죽음
    (1, False, True, 1, "이슈 본문 파일이 없습니다"),               # ⛔ 기록만 → 도중에 죽음
    (1, False, False, 1, "이슈 본문 파일이 없습니다"),              # 잡지 못한 예외의 기본값 1
    (2, False, False, 2, "상호 감시 조회에 실패했습니다 (종료코드 2)"),  # 조회 실패
    (4, True, False, 4, "결과를 쓰다 실패했습니다 (종료코드 4)"),      # 결과 쓰기 실패
], ids=["0", "1-둘다", "1-파일만", "1-기록만", "1-둘다없음", "2", "4"])
@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_heartbeat_step_sorts_failures_for_real(name, tmp_path, rc, files, output, expect, said_part):
    gh_output = tmp_path / "gh_output"
    gh_output.write_bytes(b"")
    step = _find_step(_load_workflow(name), "id", "heartbeat")
    res = _run_step(step, tmp_path, {"python": FAKE_PYTHON}, {
        "FAKE_RC": str(rc),
        "FAKE_FILES": "1" if files else "",
        "FAKE_OUTPUT": "1" if output else "",
        "GITHUB_OUTPUT": "gh_output",
    })
    said = res.stdout.decode("utf-8", "replace") + res.stderr.decode("utf-8", "replace")
    assert res.returncode == expect, said
    if said_part:
        assert said_part in said, said
    if rc == 4:
        assert "조회에 실패했습니다" not in said, "4 는 조회 실패가 아니다 — 다른 말로 알린다"


FAKE_GH = """#!/bin/sh
# 가짜 gh — issue list 는 열린 제목 파일을, issue create 는 --title 과 --body-file 내용을 기록한다.
if [ "$1" = "issue" ] && [ "$2" = "list" ]; then
  cat open_titles.txt
  exit 0
fi
if [ "$1" = "issue" ] && [ "$2" = "create" ]; then
  shift 2
  while [ $# -gt 0 ]; do
    if [ "$1" = "--title" ]; then printf '%s\\n' "$2" >> created.txt; fi
    if [ "$1" = "--body-file" ]; then cat "$2" >> created_body.txt; fi
    shift
  done
  exit 0
fi
echo "예상 못 한 gh 호출: $*" >&2
exit 99
"""


def _prepare_failure_step(tmp_path, open_titles):
    (tmp_path / ".github").mkdir()
    shutil.copyfile(FAILURE_BODY, str(tmp_path / ".github" / "watch-heartbeat-failure-issue.md"))
    (tmp_path / "open_titles.txt").write_bytes(("\n".join(open_titles) + "\n").encode("utf-8"))


@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_failure_step_opens_one_issue_when_none_is_open_for_real(name, tmp_path):
    _prepare_failure_step(tmp_path, ["다른 이슈 제목"])
    step = _find_step(_load_workflow(name), "name", FAILURE_STEP_NAME)
    res = _run_step(step, tmp_path, {"gh": FAKE_GH}, {
        "GH_TOKEN": "fake", "RUN_URL": "https://example.test/run/7",
    })
    said = res.stdout.decode("utf-8", "replace") + res.stderr.decode("utf-8", "replace")
    assert res.returncode == 0, said
    created = (tmp_path / "created.txt").read_bytes().decode("utf-8").splitlines()
    assert created == [FAILURE_TITLE], said
    body = (tmp_path / "created_body.txt").read_bytes().decode("utf-8").replace("\r\n", "\n")
    with open(FAILURE_BODY, encoding="utf-8") as f:
        expected = f.read().replace("\r\n", "\n")
    assert expected in body
    assert "이 알림을 만든 실행: https://example.test/run/7" in body


@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_failure_step_skips_when_the_same_title_is_open_for_real(name, tmp_path):
    _prepare_failure_step(tmp_path, ["다른 이슈 제목", FAILURE_TITLE])
    step = _find_step(_load_workflow(name), "name", FAILURE_STEP_NAME)
    res = _run_step(step, tmp_path, {"gh": FAKE_GH}, {
        "GH_TOKEN": "fake", "RUN_URL": "https://example.test/run/7",
    })
    said = res.stdout.decode("utf-8", "replace") + res.stderr.decode("utf-8", "replace")
    assert res.returncode == 0, said
    assert not (tmp_path / "created.txt").exists(), "열린 같은 이슈가 있으면 새로 열면 안 된다"
    assert "이미 열린 같은 이슈가 있습니다" in said


# ── 워크플로: 글자·배치 ───────────────────────────────────────────────────────


@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_failure_step_is_wired_right_after_the_stale_step(name):
    """새 단계 = stale 단계 **바로 다음**, 그 뒤에 오는 단계는 전부 `if: failure()`(0개 또는 1개).

    ⓘ 라이브 감시는 failure() 단계가 하트비트 **앞**에 있어 새 단계가 맨 끝이다 — 이 한 규칙이
       여섯 파일을 예외 없이 덮는다.
    """
    steps = _heartbeat_job_steps(_load_workflow(name))
    names = [s.get("name") for s in steps]
    i_stale = [k for k, s in enumerate(steps) if s.get("if") == STALE_IF]
    assert len(i_stale) == 1, name
    i_new = names.index(FAILURE_STEP_NAME)
    assert i_new == i_stale[0] + 1, "{}: 새 단계가 stale 단계 바로 뒤가 아닙니다".format(name)
    after = steps[i_new + 1:]
    assert len(after) <= 1, name
    allowed = {"failure()"}
    if name == "data-freshness-watch.yml":  # 각주 뷰만 실패한 주도 실패 이슈를 연다(2026-10-07 (3))
        allowed.add("${{ failure() || steps.check.outputs.partial == 'true' }}")
    assert all(s.get("if") in allowed for s in after), name


@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_failure_step_reads_outcome_not_conclusion(name):
    """`conclusion` 은 continue-on-error 적용 뒤라 늘 success — outcome 을 봐야 고장이 보인다."""
    step = _find_step(_load_workflow(name), "name", FAILURE_STEP_NAME)
    assert step["if"] == FAILURE_IF
    assert "continue-on-error" not in step
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "RUN_URL" in step["env"]
    assert "set -euo pipefail" in step["run"]
    assert "watch-heartbeat-failure-issue.md" in step["run"]
    assert '<<< "$OPEN_TITLES"' in step["run"]
    # ⛔ `--state all` 이면 사람이 닫은 고장 이슈도 목록에 남아 다음 고장부터 영영 안 열린다.
    assert "--state open" in step["run"]


def test_failure_title_is_identical_in_all_six():
    """제목이 글자까지 같아야 같은 고장이 여섯 곳에서 이슈 하나로 묶인다."""
    titles = set()
    for name in chk.DEFAULT_WORKFLOWS:
        run = _find_step(_load_workflow(name), "name", FAILURE_STEP_NAME)["run"]
        found = re.findall(r'^TITLE="([^"]*)"$', run, re.M)
        assert len(found) == 1, name
        titles.add(found[0])
    assert titles == {FAILURE_TITLE}


@pytest.mark.parametrize("name", chk.DEFAULT_WORKFLOWS)
def test_heartbeat_step_keeps_its_guards(name):
    step = _find_step(_load_workflow(name), "id", "heartbeat")
    assert step["continue-on-error"] is True
    assert step["if"] == "${{ !cancelled() }}"
    assert step["env"]["GITHUB_TOKEN"] == "${{ github.token }}"
    assert "set +e" in step["run"]
    assert "python scripts/check_watch_heartbeat.py --workflow" in step["run"]


def test_failure_issue_body_exists_and_uses_powershell():
    with open(FAILURE_BODY, encoding="utf-8") as f:
        body = f.read()
    assert "```powershell" in body
    assert "cd D:\\sangga" in body
    assert "python scripts/check_watch_heartbeat.py" in body
    # PowerShell 5.1 에 없는 bash 문법을 사장님께 드리지 않는다.
    assert "&&" not in body
    assert "/dev/null" not in body


# ── bash 가 없을 때 가드 — CI 에서는 실패, 로컬에서만 건너뛴다 ─────────────────


def test_run_step_fails_on_ci_without_bash(monkeypatch, tmp_path):
    monkeypatch.setitem(globals(), "_find_bash", lambda: None)
    monkeypatch.setenv("CI", "1")
    # BaseException 으로 받는다 — 건너뜀(Skipped)이 새어 나가면 시험이 빨강이 아니라 '건너뜀'이 된다.
    with pytest.raises(BaseException) as caught:
        _run_step({"run": "true"}, tmp_path, {}, {})
    assert caught.type is pytest.fail.Exception, caught.type


def test_run_step_fails_on_github_actions_without_bash(monkeypatch, tmp_path):
    monkeypatch.setitem(globals(), "_find_bash", lambda: None)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    # BaseException 으로 받는다 — 건너뜀(Skipped)이 새어 나가면 시험이 빨강이 아니라 '건너뜀'이 된다.
    with pytest.raises(BaseException) as caught:
        _run_step({"run": "true"}, tmp_path, {}, {})
    assert caught.type is pytest.fail.Exception, caught.type


def test_run_step_skips_locally_without_bash(monkeypatch, tmp_path):
    monkeypatch.setitem(globals(), "_find_bash", lambda: None)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    # BaseException 으로 받는다 — 건너뜀(Skipped)이 새어 나가면 시험이 빨강이 아니라 '건너뜀'이 된다.
    with pytest.raises(BaseException) as caught:
        _run_step({"run": "true"}, tmp_path, {}, {})
    assert caught.type is pytest.skip.Exception, caught.type
