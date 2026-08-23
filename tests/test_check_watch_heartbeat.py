# -*- coding: utf-8 -*-
"""
scripts/check_watch_heartbeat.py 1:1 단위 테스트.

네트워크는 전부 monkeypatch로 막는다(실제 GitHub API에 접속하지 않음).
공용 설정 파일(conftest.py 등) 없이 이 파일 안에서 import 경로를 직접 해결한다.
"""

import datetime
import json
import os
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
    """NOW 기준 며칠 전 시각."""
    return NOW - datetime.timedelta(days=days_ago)


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


def test_main_returns_zero_when_everything_is_fresh(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.QUARTERLY_WATCH: _dt(2), chk.DISTRICT_WATCH: _dt(2)})
    assert chk.main([]) == 0
    assert "멈춘 감시           : 없음" in capsys.readouterr().out
    # 멈춘 게 없으면 이슈 본문 파일을 만들지 않는다
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_returns_one_and_writes_issue_body_when_stale(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.QUARTERLY_WATCH: _dt(2), chk.DISTRICT_WATCH: _dt(70)})
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
        return _dt(1)

    monkeypatch.setattr(chk, "fetch_latest_success", fake)
    assert chk.main(["--workflow", chk.DISTRICT_WATCH]) == 0
    assert asked == [chk.DISTRICT_WATCH]


def test_main_honors_max_age_days(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.DISTRICT_WATCH: _dt(20)})
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
    _patch_fetch(monkeypatch, {chk.DISTRICT_WATCH: _dt(70)})
    assert chk.main(["--workflow", chk.DISTRICT_WATCH]) == 1
    assert "stale=true" in out.read_text(encoding="utf-8")


def test_main_json_output(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, {chk.QUARTERLY_WATCH: _dt(2), chk.DISTRICT_WATCH: None})
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
    _patch_fetch(monkeypatch, {chk.QUARTERLY_WATCH: _dt(1), chk.DISTRICT_WATCH: _dt(1)})
    assert chk.main([]) == 0


# ── 상호 감시 배선 점검 (한쪽만 걸려 있으면 반쪽 감시가 된다) ────────────────

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_DIR = os.path.join(REPO_ROOT, ".github", "workflows")


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("name", [chk.QUARTERLY_WATCH, chk.DISTRICT_WATCH])
def test_watched_workflow_files_actually_exist(name):
    """파일명을 바꾸고 이 상수를 안 고치면 조회가 404 로 계속 실패한다."""
    assert os.path.exists(os.path.join(WORKFLOW_DIR, name)), name


@pytest.mark.parametrize(
    "mine,other",
    [(chk.QUARTERLY_WATCH, chk.DISTRICT_WATCH), (chk.DISTRICT_WATCH, chk.QUARTERLY_WATCH)],
)
def test_each_watch_checks_the_other_one(mine, other):
    """서로를 봐야 한쪽이 죽어도 다른 쪽이 알린다. 자기 자신을 보면 아무 의미가 없다."""
    wf = _read_text(os.path.join(WORKFLOW_DIR, mine))
    assert "check_watch_heartbeat.py --workflow {}".format(other) in wf


@pytest.mark.parametrize("name", [chk.QUARTERLY_WATCH, chk.DISTRICT_WATCH])
def test_each_watch_can_read_run_history(name):
    """actions: read 가 없으면 실행 기록 조회가 403 으로 막힌다."""
    assert "actions: read" in _read_text(os.path.join(WORKFLOW_DIR, name))


@pytest.mark.parametrize("name", [chk.QUARTERLY_WATCH, chk.DISTRICT_WATCH])
def test_heartbeat_step_cannot_fail_the_job(name):
    """하트비트가 job 을 실패시키면 failure() 가 **엉뚱한** 실패 이슈를 연다."""
    wf = _read_text(os.path.join(WORKFLOW_DIR, name))
    assert "continue-on-error: true" in wf


@pytest.mark.parametrize("name", [chk.QUARTERLY_WATCH, chk.DISTRICT_WATCH])
def test_heartbeat_still_runs_when_my_own_watch_failed(name):
    """내가 아픈 주야말로 상대까지 조용해지면 안 되는 주다.

    앞 단계가 실패하면 job status 가 failure 라 뒤 단계가 통째로 건너뛰어진다 —
    08-10 사고("예약은 도는데 실패")가 정확히 그 상태였다.
    """
    wf = _read_text(os.path.join(WORKFLOW_DIR, name))
    assert "if: ${{ !cancelled() }}" in wf


@pytest.mark.parametrize("name", [chk.QUARTERLY_WATCH, chk.DISTRICT_WATCH])
def test_heartbeat_issue_step_also_survives_a_failed_watch(name):
    """판정 단계만 살리고 알림 단계를 놔두면 암묵적 success() 에서 다시 막힌다."""
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
