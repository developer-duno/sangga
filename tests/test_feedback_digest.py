# -*- coding: utf-8 -*-
"""
scripts/feedback_digest.py 1:1 단위 테스트.

네트워크는 전부 monkeypatch 로 막는다(실제 Supabase 에 접속하지 않음).
공용 설정 파일(conftest.py 등) 없이 이 파일 안에서 import 경로를 직접 해결한다.

여기서 특히 지키는 것
---------------------
이 스크립트가 존재하는 이유는 "우편함을 만들어 놓고 아무도 안 읽는" 상태를 깨는 것이다.
그러니 그 목적이 무너지는 자리를 가장 집요하게 본다:

  · 알릴 일이 없으면 **조용해야** 한다 — 매주 "0건입니다"가 쌓이면 진짜 알림도 무시된다.
  · 새 글이 있으면 **반드시** 알려야 한다 — 여기서 조용히 넘어가면 우편함은 다시
    "읽을 계기가 없는" 상태로 돌아간다.
  · 보관 기한을 넘긴 글이 있으면 **새 글이 하나도 없어도** 알려야 한다 — 치우기가
    편지 오는 길에 얹혀 있어서, 조용한 기간에는 정책이 말로만 남기 때문이다.
  · 본문(body)은 **어떤 경로로도** 이 스크립트에 안 들어온다.
"""

import json
import os
import sys
import urllib.error

import pytest
import yaml

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import feedback_digest as fd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "feedback-digest.yml")

URL = "https://example.test"
KEY = "anon-key-fake"


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def stats_row(opinion=0, error=0, total=0, oldest=None):
    return [
        {
            "opinion_cnt": opinion,
            "error_cnt": error,
            "total_cnt": total,
            "oldest_days": oldest,
        }
    ]


def install_fake_urlopen(monkeypatch, payload):
    """RPC 응답 하나를 흉내 낸다. 요청(헤더·본문)을 기록해 돌려준다."""
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append({
            "url": req.full_url,
            "headers": dict(req.header_items()),
            "data": req.data,
        })
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload)

    monkeypatch.setattr(fd.urllib.request, "urlopen", fake_urlopen)
    return calls


def set_env(monkeypatch, tmp_path=None):
    monkeypatch.setenv("SANGGA_SUPABASE_URL", URL)
    monkeypatch.setenv("SANGGA_SUPABASE_ANON_KEY", KEY)
    monkeypatch.setattr(sys, "argv", ["feedback_digest.py"])
    if tmp_path is None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        return None
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def outputs(path):
    """GITHUB_OUTPUT 파일을 {key: value} 로 되읽는다(구분자 형식 그대로 해석).

    ⚠️ 아무것도 안 넘긴 실행에서는 **파일 자체가 안 생긴다**(스크립트가 열지도 않는다).
       그건 정상이므로 빈 dict 로 본다 — 여기서 터지면 "실패했을 때 조용한가"를
       확인하려던 테스트가 엉뚱한 이유로 빨간불이 된다.
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    got, lines, i = {}, text.splitlines(), 0
    while i < len(lines):
        if "<<" in lines[i]:
            key, delim = lines[i].split("<<", 1)
            i += 1
            buf = []
            while i < len(lines) and lines[i] != delim:
                buf.append(lines[i])
                i += 1
            got[key] = "\n".join(buf)
        i += 1
    return got


# ── RPC 호출 모양 ────────────────────────────────────────────────────────────


def test_rpc_sends_content_profile_api_header(monkeypatch):
    """⛔ RPC 는 POST 라서 Accept-Profile 이 아니라 Content-Profile 로 스키마를 고른다.

    빠뜨리면 옛 문(public)을 닫아 둔 이 앱에서는 PGRST106 으로 죽는다 — 화면이 아니라
    워크플로에서 나는 고장이라 아무도 안 보고 있으면 그대로 묻힌다.
    """
    calls = install_fake_urlopen(monkeypatch, stats_row())
    fd.fetch_stats(URL, KEY, 7)
    assert calls[0]["headers"].get("Content-profile") == "api"


def test_rpc_calls_the_stats_function_not_the_table(monkeypatch):
    """표를 직접 읽으면 본문까지 딸려 온다 — 반드시 함수 경로여야 한다."""
    calls = install_fake_urlopen(monkeypatch, stats_row())
    fd.fetch_stats(URL, KEY, 7)
    assert calls[0]["url"].endswith("/rest/v1/rpc/get_feedback_stats")


def test_rpc_sends_apikey_and_bearer(monkeypatch):
    calls = install_fake_urlopen(monkeypatch, stats_row())
    fd.fetch_stats(URL, KEY, 7)
    headers = calls[0]["headers"]
    assert headers.get("Apikey") == KEY
    assert headers.get("Authorization") == f"Bearer {KEY}"


def test_days_is_passed_in_body(monkeypatch):
    calls = install_fake_urlopen(monkeypatch, stats_row())
    fd.fetch_stats(URL, KEY, 30)
    assert json.loads(calls[0]["data"].decode("utf-8")) == {"p_days": 30}


# ── 응답 파싱 ────────────────────────────────────────────────────────────────


def test_fetch_stats_parses_all_four_numbers(monkeypatch):
    install_fake_urlopen(monkeypatch, stats_row(opinion=3, error=1, total=9, oldest=12))
    assert fd.fetch_stats(URL, KEY, 7) == {
        "opinion_cnt": 3,
        "error_cnt": 1,
        "total_cnt": 9,
        "oldest_days": 12,
    }


def test_empty_table_gives_none_for_oldest(monkeypatch):
    """표가 비어 있으면 '가장 오래된 글'이라는 것이 없다 — 0일이 아니라 없음이다."""
    install_fake_urlopen(monkeypatch, stats_row(total=0, oldest=None))
    assert fd.fetch_stats(URL, KEY, 7)["oldest_days"] is None


def test_unexpected_shape_is_rejected(monkeypatch):
    install_fake_urlopen(monkeypatch, {"not": "a list"})
    with pytest.raises(fd.CallFailed):
        fd.fetch_stats(URL, KEY, 7)


def test_missing_column_is_rejected(monkeypatch):
    """서버 함수가 바뀌어 칸이 사라지면 조용히 0으로 읽지 않는다."""
    install_fake_urlopen(monkeypatch, [{"opinion_cnt": 1}])
    with pytest.raises(fd.CallFailed):
        fd.fetch_stats(URL, KEY, 7)


# ── 보관 기한 판정 ───────────────────────────────────────────────────────────


def test_retention_not_overdue_when_within_limit():
    assert fd.retention_overdue({"oldest_days": fd.RETENTION_DAYS}) is False


def test_retention_overdue_when_past_limit():
    assert fd.retention_overdue({"oldest_days": fd.RETENTION_DAYS + 1}) is True


def test_retention_not_overdue_when_table_empty():
    assert fd.retention_overdue({"oldest_days": None}) is False


def test_retention_days_matches_the_server_constant():
    """⛔ 판정 기준과 실제 삭제 기한이 갈리면, 알림은 조용한데 글은 안 지워진다.

    서버 쪽 상수는 마이그레이션(그리고 정본)의 `interval '90 days'` 다. 한쪽만 고치는
    순간 이 테스트가 빨간불로 알려 준다.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in (
        os.path.join(root, "supabase", "schema.sql"),
        os.path.join(
            root, "supabase", "migrations", "2026-08-24c_feedback_digest_and_retention.sql"
        ),
    ):
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        assert "interval '{} days'".format(fd.RETENTION_DAYS) in sql, (
            "{} 의 보관 기한이 feedback_digest.RETENTION_DAYS({})와 다릅니다".format(
                os.path.basename(path), fd.RETENTION_DAYS
            )
        )


# ── 재시도 ───────────────────────────────────────────────────────────────────


def test_transient_failure_is_retried(monkeypatch):
    """한 번 끊겼다고 실패로 알리면, 그 이슈를 닫는 손이 들고 결국 알림이 무시된다.

    ⛔ fetch_stats 가 아니라 rpc 를 직접 부른다 — sleep=lambda 로 재시도 사이 대기를
    없애야 하는데, fetch_stats 는 그 자리를 밖으로 안 열어 준다(collect_lh_notices.py
    가 get_json_with_retry 를 직접 시험하는 것과 같은 이유 — fetch_sanga 를 거치지
    않는다).
    """
    attempts = {"n": 0}

    def flaky(req, timeout=None):
        if attempts["n"] < 2:
            attempts["n"] += 1
            raise urllib.error.URLError("일시 장애")
        return FakeResponse(stats_row(opinion=1, total=1, oldest=0))

    monkeypatch.setattr(fd.urllib.request, "urlopen", flaky)
    result = fd.rpc(URL, KEY, fd.STATS_FN, {"p_days": 7}, sleep=lambda _s: None)
    assert result == stats_row(opinion=1, total=1, oldest=0)
    assert attempts["n"] == 2


def test_gives_up_after_retries(monkeypatch):
    install_fake_urlopen(monkeypatch, urllib.error.URLError("계속 장애"))
    with pytest.raises(fd.CallFailed):
        fd.rpc(URL, KEY, fd.STATS_FN, {"p_days": 7}, sleep=lambda _s: None)


# ── main() — 이 스크립트의 존재 이유 ─────────────────────────────────────────


def test_quiet_week_reports_nothing(monkeypatch, tmp_path, capsys):
    """⛔ 0건인데 이슈를 열면 "0건입니다"가 매주 쌓여 진짜 알림도 함께 무시된다."""
    install_fake_urlopen(monkeypatch, stats_row(opinion=0, error=0, total=0, oldest=None))
    out = set_env(monkeypatch, tmp_path)
    assert fd.main() == 0
    assert "알릴 일이 없습니다" in capsys.readouterr().out
    assert outputs(out)["should_report"] == "false"


def test_new_feedback_is_reported(monkeypatch, tmp_path):
    """⛔ 건수가 있는데 조용하면, 우편함은 다시 "읽을 계기가 없는" 상태로 돌아간다."""
    install_fake_urlopen(monkeypatch, stats_row(opinion=2, error=1, total=3, oldest=5))
    out = set_env(monkeypatch, tmp_path)
    assert fd.main() == 0

    got = outputs(out)
    assert got["should_report"] == "true"
    assert "의견 2건" in got["body"] and "오류 기록 1건" in got["body"]


def test_overdue_retention_is_reported_even_with_no_new_feedback(monkeypatch, tmp_path, capsys):
    """⭐ 이 테스트가 이 PR 의 급소다.

    치우기는 **편지가 들어올 때만** 돈다. 그러니 조용한 기간이 길면 기한을 넘긴 글이
    남는데, 그때는 새 글도 0건이라 "알릴 일 없음"으로 조용히 넘어가기 쉽다. 그러면
    "90일 보관"은 말로만 정책이고 실제로는 안 지켜진다 — 정확히 그 상태를 막는다.
    """
    install_fake_urlopen(monkeypatch, stats_row(opinion=0, error=0, total=4, oldest=120))
    out = set_env(monkeypatch, tmp_path)
    assert fd.main() == 0

    got = outputs(out)
    assert got["should_report"] == "true"
    assert "보관 기한" in got["body"]
    assert "purge_old_feedback" in got["body"], "정리하는 명령을 본문이 안내해야 한다"
    assert "보관 기한" in capsys.readouterr().out


def test_missing_credentials_returns_2(monkeypatch, capsys):
    monkeypatch.delenv("SANGGA_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SANGGA_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["feedback_digest.py"])
    assert fd.main() == 2
    assert "필요합니다" in capsys.readouterr().out


def test_rpc_failure_returns_1_and_reports_nothing(monkeypatch, tmp_path, capsys):
    """⛔ 조회에 실패했는데 '알릴 일 없음'으로 넘어가면, 창고가 죽어도 조용하다.

    ⛔ fetch_stats 를 바로 실패시킨다 — collect_lh_notices.py 의 TestMain 이
    fetch_recent 를 흉내 내는 것과 같은 이유다. main() 이 실제 재시도 루프
    (rpc)까지 거치게 두면 기본 sleep=time.sleep 때문에 이 시험이 몇 초씩(총
    75초) 실제로 기다리게 된다 — main() 은 재시도 루프를 우회할 자리를 안 열어
    두므로(운영 스크립트라 정상), 여기서는 그 위 계층에서 실패를 흉내 낸다.
    """
    def boom(*args, **kwargs):
        raise fd.CallFailed("장애")

    monkeypatch.setattr(fd, "fetch_stats", boom)
    out = set_env(monkeypatch, tmp_path)
    assert fd.main() == 1
    assert "실패" in capsys.readouterr().out
    assert "should_report" not in outputs(out)


def test_trailing_slash_in_url_is_normalized(monkeypatch):
    calls = install_fake_urlopen(monkeypatch, stats_row())
    monkeypatch.setenv("SANGGA_SUPABASE_URL", URL + "/")
    monkeypatch.setenv("SANGGA_SUPABASE_ANON_KEY", KEY)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(sys, "argv", ["feedback_digest.py"])
    assert fd.main() == 0
    assert "//rest" not in calls[0]["url"]


# ── 이슈 본문 ────────────────────────────────────────────────────────────────


def test_issue_body_guides_to_dbx_for_content():
    """건수만 아는 알림이라, 내용을 읽는 다음 걸음을 본문이 직접 안내해야 한다."""
    body = fd.build_issue_body(
        {"opinion_cnt": 2, "error_cnt": 1, "total_cnt": 3, "oldest_days": 5}, 7
    )
    assert "dbx.py" in body
    assert "app_feedback" in body


def test_issue_body_warns_about_contact_info_in_free_text():
    """앞문(연락처 칸)은 막았지만 뒷문(자유 글)은 열려 있다 — 읽는 사람이 알아야 한다."""
    body = fd.build_issue_body(
        {"opinion_cnt": 1, "error_cnt": 0, "total_cnt": 1, "oldest_days": 1}, 7
    )
    assert "연락처" in body


def test_issue_body_shows_total_for_tuning_the_cap():
    """하루 상한 1,000 은 안전망일 뿐이라, 조이려면 실제 총량이 보여야 한다."""
    body = fd.build_issue_body(
        {"opinion_cnt": 1, "error_cnt": 0, "total_cnt": 1234, "oldest_days": 1}, 7
    )
    assert "1,234" in body


def test_issue_body_has_no_purge_hint_when_not_overdue():
    """멀쩡할 때까지 '정리하세요'가 붙어 있으면 진짜 밀린 날의 신호가 묻힌다."""
    body = fd.build_issue_body(
        {"opinion_cnt": 1, "error_cnt": 0, "total_cnt": 1, "oldest_days": 1}, 7
    )
    assert "purge_old_feedback" not in body


# ── 출력 전달(GITHUB_OUTPUT) ─────────────────────────────────────────────────


def test_emit_output_delimiter_differs_every_run(monkeypatch, tmp_path):
    """⛔ 고정 구분자면 값 안에 같은 줄이 들어오는 순간 거기서 값이 끊긴다."""
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    fd._emit_output("body", "가")
    fd._emit_output("body", "나")

    delims = [
        line.split("<<", 1)[1]
        for line in out.read_text(encoding="utf-8").splitlines()
        if line.startswith("body<<")
    ]
    assert len(delims) == 2
    assert delims[0] != delims[1]


def test_emit_output_is_noop_outside_actions(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    fd._emit_output("body", "아무거나")  # 예외가 안 나면 통과


# ── 재시도 표준(collect_lh_notices.get_json_with_retry 와 같은 규칙) ───────────


class TestRetryStandard:
    """2026-08-31 PR #109 가 collect_lh_notices.py 에 세운 표준을 여기도 따른다 —
    예전엔 RETRIES=3 이면서 재시도 사이 대기가 0초였고, 401/403/404 같은 영구 실패도
    다시 물었다(check_live_health.py 와 같은 결함)."""

    def test_matches_the_collector_standard(self):
        """⛔ 두 벌로 두면 언젠가 한쪽만 고쳐진다 — 값이 갈리면 이 시험이 잡는다."""
        import collect_lh_notices as lh

        assert fd.RETRY_COUNT == lh.RETRY_COUNT
        assert fd.RETRY_BACKOFF_SEC == lh.RETRY_BACKOFF_SEC
        assert fd.NO_RETRY_HTTP_CODES == lh.NO_RETRY_HTTP_CODES

    def test_waits_longer_between_each_knock(self, monkeypatch):
        def always_down(req, timeout=None):
            raise urllib.error.URLError("계속 장애")

        monkeypatch.setattr(fd.urllib.request, "urlopen", always_down)
        waits = []
        with pytest.raises(fd.CallFailed):
            fd.rpc(URL, KEY, fd.STATS_FN, {"p_days": 7}, sleep=waits.append)
        assert waits == [fd.RETRY_BACKOFF_SEC * (2**i) for i in range(fd.RETRY_COUNT - 1)]

    @pytest.mark.parametrize("code", sorted(fd.NO_RETRY_HTTP_CODES))
    def test_does_not_retry_what_will_not_change(self, monkeypatch, code):
        """401·403·404 는 사람이 설정을 고쳐야 하는 것 — 참을성을 늘려도 한 번뿐이다."""
        calls = []

        def refused(req, timeout=None):
            calls.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, code, "refused", None, None)

        monkeypatch.setattr(fd.urllib.request, "urlopen", refused)
        with pytest.raises(fd.CallFailed):
            fd.rpc(URL, KEY, fd.STATS_FN, {"p_days": 7}, sleep=lambda _s: None)
        assert len(calls) == 1, "다시 물어도 답이 같은 실패인데 재시도했습니다"

    def test_retries_a_gateway_timeout_like_error(self, monkeypatch):
        """502·503 같은 HTTPError 는 다시 물으면 답이 달라질 수 있어 재시도한다."""
        calls = []

        def flaky(req, timeout=None):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", None, None)
            return FakeResponse(stats_row(opinion=1, total=1, oldest=0))

        monkeypatch.setattr(fd.urllib.request, "urlopen", flaky)
        result = fd.rpc(URL, KEY, fd.STATS_FN, {"p_days": 7}, sleep=lambda _s: None)
        assert result == stats_row(opinion=1, total=1, oldest=0)
        assert len(calls) == 2


# ── 워크플로 배선 ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def workflow_text():
    with open(WORKFLOW, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


def _step(workflow, name):
    matches = [s for s in workflow["jobs"]["digest"]["steps"] if s.get("name") == name]
    assert matches, f"'{name}' 단계를 워크플로에서 못 찾았습니다"
    return matches[0]


class TestWorkflow:
    """본보기는 lh-notice-watch.yml **하나**다 — 자격값 게이트 + outputs 기반 알림 +
    별도 failure 알림, feedback-digest.yml 과 구조가 같다. (live-health-watch.yml 의
    failure() 는 본연의 알림 그 자체라 모델이 아니다.)"""

    def test_exists_and_parses(self, workflow):
        assert workflow["name"]

    def test_failure_is_loud(self, workflow_text):
        """감시가 실패하면 이슈가 안 열린다 — 그 사실 자체를 이슈로 만든다(lh-notice
        와 같은 형태)."""
        assert "if: failure()" in workflow_text
        assert "feedback-digest-failure-issue.md" in workflow_text
        assert os.path.exists(os.path.join(ROOT, ".github", "feedback-digest-failure-issue.md"))

    def test_failure_step_is_last(self, workflow):
        """맨 끝에 둬야 앞의 모든 단계(자격값 게이트·숫자 세기·상호 감시)가 끝난
        뒤의 job 상태를 본다."""
        steps = workflow["jobs"]["digest"]["steps"]
        assert steps[-1]["name"] == "감시가 실패하면 그 사실을 이슈로 알린다"
        assert steps[-1]["if"] == "failure()"

    def test_failure_issue_dedup_looks_at_open_only(self, workflow):
        """제목에 날짜가 없으므로 **열려 있는** 같은 제목만 건너뛴다 —
        사람이 닫아야 다음 실패를 다시 알린다."""
        step = _step(workflow, "감시가 실패하면 그 사실을 이슈로 알린다")
        assert "--state open" in step["run"]

    def test_missing_vars_path_does_not_fail_the_job(self, workflow):
        """⛔ 새로 붙인 failure() 잡이가 '변수 없음'까지 사고로 알리면 안 된다 — 그
        경로는 이미 별도 설정 안내 이슈로 알리고, job 자체는 성공으로 끝나야 한다.

        확인 방법: 두 단계 모두 `exit 1`(또는 다른 실패 종료)이 없다 — `set -euo
        pipefail` 아래에서 마지막 명령이 성공(echo·gh issue create)으로 끝나면 job
        은 성공으로 마감된다.
        """
        for name in ("창고 주소·공개키가 있나", "변수가 없으면 그 사실을 알린다"):
            step = _step(workflow, name)
            assert "exit 1" not in step["run"]

    def test_uses_variables_not_secrets(self, workflow_text):
        """⛔ URL·공개키는 비밀값이 아니다 — Secrets 가 아니라 vars.* 여야 한다."""
        assert "vars.SANGGA_SUPABASE_URL" in workflow_text
        assert "vars.SANGGA_SUPABASE_ANON_KEY" in workflow_text
        assert "secrets.SANGGA_SUPABASE" not in workflow_text

    def test_watches_all_four_siblings(self, workflow_text):
        """⛔ 새 예약은 그물에 들어가야 하고, 그물도 새 예약을 봐야 한다(양방향)."""
        import check_watch_heartbeat as hb

        for other in hb.DEFAULT_WORKFLOWS:
            if other == os.path.basename(WORKFLOW):
                continue
            assert "--workflow {}".format(other) in workflow_text
        assert os.path.basename(WORKFLOW) in hb.DEFAULT_WORKFLOWS
