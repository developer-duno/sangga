# -*- coding: utf-8 -*-
"""
scripts/check_new_sangkwon_quarter.py 1:1 단위 테스트.

네트워크는 전부 monkeypatch로 막는다(실제 포털에 접속하지 않음).
공용 설정 파일(conftest.py 등) 없이 이 파일 안에서 import 경로를 직접 해결한다.
"""

import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import check_new_sangkwon_quarter as chk  # noqa: E402


# ── 분기 날짜 뽑기 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,expected",
    [
        ("소상공인시장진흥공단_상가(상권)정보_20260630", "20260630"),
        ("상가(상권)정보_20260930", "20260930"),
        ("  상가(상권)정보_20251231  ", "20251231"),  # 앞뒤 공백은 무시
        # 분기 파일이 아닌 것 — 포털 목록에 실제로 섞여 있다(2026-08-07 실측 48건 중 7건)
        ("포천시 업소수", None),
        ("상가(상권)정보", None),
        ("", None),
        (None, None),
        # 밑줄 없이 숫자만 붙은 것은 분기 파일이 아니다
        ("상가정보20260630", None),
        # 1900년대·2100년대는 패턴 밖(20으로 시작하는 8자리만)
        ("자료_19991231", None),
    ],
)
def test_extract_quarter_date(name, expected):
    assert chk.extract_quarter_date(name) == expected


# ── 새 분기 고르기 ────────────────────────────────────────────────────────────


def items(*names):
    return [{"name": n, "uddi": "uddi-{}".format(i)} for i, n in enumerate(names)]


def test_find_new_quarters_picks_only_newer():
    got = chk.find_new_quarters(
        items("자료_20260331", "자료_20260630", "자료_20260930", "자료_20261231"),
        latest_known="20260630",
    )
    assert got == [("20260930", "자료_20260930"), ("20261231", "자료_20261231")]


def test_find_new_quarters_boundary_is_exclusive():
    """기준선과 **같은** 날짜는 이미 가진 것이므로 새 분기가 아니다."""
    assert chk.find_new_quarters(items("자료_20260630"), latest_known="20260630") == []


def test_find_new_quarters_empty_when_nothing_new():
    assert chk.find_new_quarters(items("자료_20260331", "자료_20260630"), "20260630") == []


def test_find_new_quarters_dedupes_same_date():
    """포털이 같은 분기를 두 줄로 올려도 이슈는 한 번만 열려야 한다."""
    got = chk.find_new_quarters(
        items("A_20260930", "B_20260930"), latest_known="20260630"
    )
    assert got == [("20260930", "A_20260930")]


def test_find_new_quarters_sorted_ascending():
    got = chk.find_new_quarters(
        items("자료_20270331", "자료_20260930", "자료_20261231"), "20260630"
    )
    assert [d for d, _ in got] == ["20260930", "20261231", "20270331"]


def test_find_new_quarters_ignores_non_quarterly():
    assert chk.find_new_quarters(items("포천시 업소수", "안내문"), "20260630") == []


def test_find_new_quarters_handles_none():
    assert chk.find_new_quarters(None, "20260630") == []


# ── 이슈 제목·본문 ────────────────────────────────────────────────────────────


def test_issue_title_contains_dates():
    """제목에 날짜가 박혀야 같은 분기로 이슈가 두 번 열리지 않는다(중복 방지 키)."""
    t = chk.build_issue_title([("20260930", "자료_20260930")])
    assert "20260930" in t


def test_issue_body_lists_every_new_quarter():
    body = chk.build_issue_body(
        [("20260930", "자료_20260930"), ("20261231", "자료_20261231")],
        latest_known="20260630",
    )
    assert "2026-09-30" in body
    assert "2026-12-31" in body
    assert "자료_20260930" in body
    # 사람이 그대로 따라 할 명령이 들어 있어야 한다
    assert "download_sangkwon_history.py" in body
    assert "load_sangkwon_snapshot.py" in body
    assert "backup_raw.py" in body
    # 기준선을 올리라는 안내가 마지막 분기 날짜를 가리켜야 한다
    assert "20261231" in body.split("LATEST_KNOWN_QUARTER")[1]


def test_issue_body_warns_irreversible():
    """소급 불가라는 경고가 빠지면 이슈를 미루게 된다 — 이게 이 알림의 핵심이다."""
    body = chk.build_issue_body([("20260930", "자료_20260930")])
    assert "다시 받을 수 없" in body


# ── GITHUB_OUTPUT ────────────────────────────────────────────────────────────


def test_write_github_output_noop_without_env(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert chk.write_github_output([("20260930", "x")]) is False


def test_write_github_output_writes_found_true(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    chk.write_github_output([("20260930", "자료_20260930")])
    text = out.read_text(encoding="utf-8")
    assert "found=true" in text
    assert "quarters=20260930" in text
    assert "title=새 분기" in text


def test_write_github_output_writes_found_false(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    chk.write_github_output([])
    text = out.read_text(encoding="utf-8")
    assert "found=false" in text
    # 빈 제목이어야 다음 단계가 이슈를 열지 않는다
    assert "title=\n" in text


# ── main() 흐름 ───────────────────────────────────────────────────────────────


def test_main_fails_when_portal_unreachable(monkeypatch, capsys):
    def boom():
        raise RuntimeError("연결 실패")

    monkeypatch.setattr(chk, "fetch_history_list", boom)
    assert chk.main([]) == 1
    assert "포털 목록 조회 실패" in capsys.readouterr().err


def test_main_fails_when_portal_returns_empty(monkeypatch, capsys):
    """빈 목록을 '새 분기 없음'으로 조용히 넘기면 구조 변경을 영영 못 알아챈다."""
    monkeypatch.setattr(chk, "fetch_history_list", lambda: ([], []))
    assert chk.main([]) == 1
    assert "비어 있습니다" in capsys.readouterr().err


def test_main_reports_no_new_quarter(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        chk, "fetch_history_list", lambda: (items("자료_20260630"), [])
    )
    assert chk.main([]) == 0
    assert "새 분기             : 없음" in capsys.readouterr().out
    # 새 분기가 없으면 이슈 본문 파일을 만들지 않는다
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_writes_issue_body_when_new(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        chk, "fetch_history_list", lambda: (items("자료_20260930"), [])
    )
    assert chk.main([]) == 0
    body = (tmp_path / chk.ISSUE_BODY_FILE).read_text(encoding="utf-8")
    assert "2026-09-30" in body


def test_main_json_output(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        chk, "fetch_history_list", lambda: (items("자료_20260930"), ["포천시 업소수"])
    )
    assert chk.main(["--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["new"] == [{"date": "20260930", "name": "자료_20260930"}]
    assert data["excluded"] == 1


# ── 감시 워크플로우 자체 점검 (조용한 실패 방지) ─────────────────────────────

# 이 감시의 진짜 실패 모드는 "새 분기를 못 알아보는 것"이 아니라 **감시가 죽었는데
# 아무도 모르는 것**이다. 2026-08-10 예약 실행이 죽은 걸 나흘 뒤에야 알았다.
# 아래 두 가지가 사라지면 알림 경로가 통째로 조용해지므로 여기서 붙잡는다.

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "sangkwon-quarterly-watch.yml")
FAILURE_BODY_PATH = os.path.join(REPO_ROOT, ".github", "watch-failure-issue.md")


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_workflow_opens_an_issue_when_the_watch_itself_fails():
    wf = _read_text(WORKFLOW_PATH)
    assert "if: failure()" in wf, "실패해도 조용하면 새 분기를 통째로 놓친다"
    # 실패 알림도 결국 이슈로 나가야 사람 눈에 띈다
    assert wf.count("gh issue create") >= 2, "새 분기 알림 + 실패 알림 두 갈래여야 한다"


def test_failure_issue_body_file_exists_and_tells_the_human_what_to_do():
    """워크플로우가 이 파일을 그대로 읽어 이슈 본문으로 쓴다 — 사라지면 알림이 실패한다."""
    assert ".github/watch-failure-issue.md" in _read_text(WORKFLOW_PATH)
    body = _read_text(FAILURE_BODY_PATH)
    assert "check_new_sangkwon_quarter.py" in body, "내 PC에서 확인할 명령이 있어야 한다"
    assert "LATEST_KNOWN_QUARTER" in body, "기준선 올리는 걸 잊으면 다음 분기를 못 본다"


# ── 기준선 자체 점검 ──────────────────────────────────────────────────────────


def test_latest_known_quarter_is_a_valid_date():
    """기준선을 손으로 올리다 오타가 나면 감시가 통째로 무의미해진다."""
    v = chk.LATEST_KNOWN_QUARTER
    assert len(v) == 8 and v.isdigit(), v
    assert v.startswith("20"), v
    assert "01" <= v[4:6] <= "12", v
    assert "01" <= v[6:8] <= "31", v
