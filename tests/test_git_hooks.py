# -*- coding: utf-8 -*-
"""
.githooks/ 훅 2개 + scripts/setup_git_hooks.py 1:1 테스트.

여기서 특히 지키는 것
---------------------
훅은 **읽어서 맞아 보이는 것으로는 아무 증거가 안 된다.** 실행 권한이 빠졌거나
shebang 이 틀렸거나 git 이 훅을 못 찾으면, 에러가 나는 게 아니라 **그냥 조용히 안
돈다.** 이 저장소가 이미 같은 성질의 일을 겪었다(예약이 죽은 걸 나흘 뒤에 알았다).

그래서 이 테스트는 문자열을 훑지 않고 **임시 저장소를 만들어 진짜 git 으로 커밋·
밀어넣기를 시켜 본다.** 훅이 안 돌면 커밋이 성공해 버리므로 그 자리에서 빨간불이 된다.

원격도 임시 폴더에 만든 로컬 저장소라 네트워크를 쓰지 않는다.
"""

import os
import shutil
import stat
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import setup_git_hooks as sgh  # noqa: E402

HOOK_NAMES = ("pre-commit", "pre-push")


def git(args, cwd, env=None):
    """테스트용 git 실행. 부모 환경의 SANGGA_ALLOW_MAIN 오염을 막는다."""
    base = os.environ.copy()
    base.pop("SANGGA_ALLOW_MAIN", None)
    # 사용자 설정 파일이 테스트 결과를 흔들지 않게 격리한다.
    base["GIT_CONFIG_NOSYSTEM"] = "1"
    base["HOME"] = str(cwd)
    if env:
        base.update(env)
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=base,
    )


@pytest.fixture
def repo(tmp_path):
    """훅이 켜진 임시 저장소 + 원격(로컬 bare) 한 쌍."""
    work = tmp_path / "work"
    work.mkdir()
    init = git(["init", "-b", "main"], work)
    if init.returncode != 0:
        pytest.skip("이 환경의 git 이 'init -b' 를 지원하지 않습니다")
    git(["config", "user.email", "t@example.test"], work)
    git(["config", "user.name", "테스트"], work)
    git(["config", "commit.gpgsign", "false"], work)

    hooks = work / ".githooks"
    hooks.mkdir()
    for name in HOOK_NAMES:
        src = os.path.join(ROOT, ".githooks", name)
        dst = hooks / name
        shutil.copyfile(src, dst)
        os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    git(["config", "core.hooksPath", ".githooks"], work)

    remote = tmp_path / "remote.git"
    git(["init", "--bare", str(remote)], tmp_path)
    git(["remote", "add", "origin", str(remote)], work)
    return work


def write_and_add(repo_dir, name="a.txt", text="hello"):
    (repo_dir / name).write_text(text, encoding="utf-8")
    git(["add", name], repo_dir)


# ---------------------------------------------------------------- 파일 자체


def test_hook_files_exist_with_shebang():
    """훅 파일이 있고 sh 로 시작해야 한다 — shebang 이 없으면 조용히 안 돈다."""
    for name in HOOK_NAMES:
        path = os.path.join(ROOT, ".githooks", name)
        assert os.path.isfile(path), f"{name} 훅이 없습니다"
        with open(path, encoding="utf-8") as fh:
            first = fh.readline().strip()
        assert first == "#!/bin/sh", f"{name} 의 첫 줄이 shebang 이 아닙니다"


def test_hooks_have_no_carriage_returns():
    """
    훅에 CRLF(윈도우 줄바꿈)가 섞이면 안 된다.

    첫 줄이 `#!/bin/sh\\r` 이 되는 순간 셸은 그런 이름의 프로그램을 못 찾아 훅을
    실행하지 못한다. 그런데 그 실패는 **막는 쪽으로 기울지 않는다** — 훅이 안 돌면
    커밋이 그냥 통과하므로, 알람이 꺼진 줄도 모른 채 지나간다.

    윈도우 기본 설정(core.autocrlf=true)이 내려받을 때 이 사고를 만든다.
    `.gitattributes` 의 `eol=lf` 가 예방이고, 이 테스트가 그 예방이 살아 있는지 본다.
    """
    for name in HOOK_NAMES:
        path = os.path.join(ROOT, ".githooks", name)
        with open(path, "rb") as fh:
            raw = fh.read()
        assert b"\r" not in raw, f"{name} 에 CRLF 가 섞였습니다 — .gitattributes 를 확인하세요"


def test_gitattributes_pins_hook_line_endings():
    """예방장치 자체가 사라지면 다음 내려받기에서 조용히 되살아난다."""
    path = os.path.join(ROOT, ".gitattributes")
    assert os.path.isfile(path), ".gitattributes 가 없습니다"
    with open(path, encoding="utf-8") as fh:
        body = fh.read()
    assert "eol=lf" in body and ".githooks" in body


def test_hooks_are_marked_executable_in_git_index():
    """
    git 인덱스에 실행 비트가 박혀 있어야 한다.

    윈도우 파일시스템에는 실행 권한 개념이 없어 로컬에서는 늘 통과처럼 보이지만,
    다른 컴퓨터(리눅스)에서 내려받으면 실행이 안 돼 훅이 조용히 죽는다. git 이
    기억하는 모드(100755)를 직접 확인해야 그 사고를 여기서 잡는다.
    """
    out = subprocess.run(
        ["git", "ls-files", "-s", ".githooks"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if out.returncode != 0 or not out.stdout.strip():
        pytest.skip("아직 git 에 등록되지 않은 훅입니다(첫 커밋 전)")
    for line in out.stdout.strip().splitlines():
        mode = line.split(" ", 1)[0]
        assert mode == "100755", f"실행 비트가 없습니다: {line}"


# ------------------------------------------------------------- pre-commit


def test_commit_on_main_is_blocked(repo):
    write_and_add(repo)
    r = git(["commit", "-m", "main 에 직접"], repo)
    assert r.returncode != 0, "main 에서 커밋이 막히지 않았습니다"
    assert "멈춤" in (r.stderr + r.stdout)
    # 정말로 커밋이 안 만들어졌는지 확인 — 메시지만 뜨고 통과하면 의미가 없다.
    log = git(["log", "--oneline"], repo)
    assert log.returncode != 0 or not log.stdout.strip()


def test_commit_on_other_branch_passes(repo):
    git(["switch", "-c", "work"], repo)
    write_and_add(repo)
    r = git(["commit", "-m", "작업 가지"], repo)
    assert r.returncode == 0, f"작업 가지 커밋이 막혔습니다: {r.stderr}"


def test_commit_on_main_passes_with_escape_hatch(repo):
    write_and_add(repo)
    r = git(["commit", "-m", "일부러"], repo, env={"SANGGA_ALLOW_MAIN": "1"})
    assert r.returncode == 0, f"빠져나가는 길이 막혔습니다: {r.stderr}"


# --------------------------------------------------------------- pre-push


def _one_commit_on_work(repo):
    git(["switch", "-c", "work"], repo)
    write_and_add(repo)
    git(["commit", "-m", "작업"], repo)


def test_push_to_main_is_blocked_even_from_another_branch(repo):
    """
    pre-commit 이 못 잡는 길이 이것이다 — 다른 가지에서 커밋해 놓고
    도착지만 main 으로 바꿔 밀어넣는 경우.
    """
    _one_commit_on_work(repo)
    r = git(["push", "origin", "HEAD:main"], repo)
    assert r.returncode != 0, "main 으로 밀어넣기가 막히지 않았습니다"
    assert "멈춤" in (r.stderr + r.stdout)


def test_push_to_other_branch_passes(repo):
    _one_commit_on_work(repo)
    r = git(["push", "origin", "HEAD:refs/heads/work"], repo)
    assert r.returncode == 0, f"작업 가지 밀어넣기가 막혔습니다: {r.stderr}"


def test_push_to_main_passes_with_escape_hatch(repo):
    _one_commit_on_work(repo)
    r = git(["push", "origin", "HEAD:main"], repo, env={"SANGGA_ALLOW_MAIN": "1"})
    assert r.returncode == 0, f"빠져나가는 길이 막혔습니다: {r.stderr}"


# ------------------------------------------------- setup_git_hooks.py 로직


def test_missing_hook_files_finds_gaps(tmp_path):
    (tmp_path / ".githooks").mkdir()
    (tmp_path / ".githooks" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    assert sgh.missing_hook_files(str(tmp_path)) == ["pre-push"]


def test_missing_hook_files_empty_when_all_present():
    assert sgh.missing_hook_files(ROOT) == []


def test_github_lock_status_reads_active_branch_ruleset(monkeypatch):
    payload = '[{"name":"main 보호","target":"branch","enforcement":"active"}]'
    monkeypatch.setattr(
        sgh.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, payload, ""),
    )
    state, detail = sgh.github_lock_status(ROOT)
    assert state == "있음"
    assert detail == ["main 보호"]


def test_github_lock_status_ignores_disabled_and_tag_rulesets(monkeypatch):
    """꺼져 있거나 다른 대상(tag)인 규칙을 '잠금 있음'으로 세면 안 된다."""
    payload = (
        '[{"name":"꺼짐","target":"branch","enforcement":"disabled"},'
        '{"name":"태그","target":"tag","enforcement":"active"}]'
    )
    monkeypatch.setattr(
        sgh.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, payload, ""),
    )
    state, _ = sgh.github_lock_status(ROOT)
    assert state == "없음"


def test_github_lock_status_when_gh_missing(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(sgh.subprocess, "run", boom)
    state, _ = sgh.github_lock_status(ROOT)
    assert state == "확인못함"


def test_check_does_not_fail_when_github_cannot_be_checked(monkeypatch, capsys):
    """
    '모르는 것'을 '없는 것'으로 취급하면, 네트워크 없는 CI 에서 이 가드가 늘
    빨간불이 되어 결국 꺼진다. 그 길을 막는다.
    """
    monkeypatch.setattr(sgh, "github_lock_status", lambda root: ("확인못함", ["gh 없음"]))
    monkeypatch.setattr(sgh, "configured_hooks_path", lambda root: ".githooks")
    monkeypatch.setattr(sgh, "missing_hook_files", lambda root: [])
    assert sgh.main(["--check"]) == 0
    assert "모름" in capsys.readouterr().out


def test_check_fails_when_github_lock_is_absent(monkeypatch):
    monkeypatch.setattr(sgh, "github_lock_status", lambda root: ("없음", []))
    monkeypatch.setattr(sgh, "configured_hooks_path", lambda root: ".githooks")
    monkeypatch.setattr(sgh, "missing_hook_files", lambda root: [])
    assert sgh.main(["--check"]) == 1


def test_check_fails_when_hooks_path_not_configured(monkeypatch):
    monkeypatch.setattr(sgh, "github_lock_status", lambda root: ("있음", ["main 보호"]))
    monkeypatch.setattr(sgh, "configured_hooks_path", lambda root: None)
    monkeypatch.setattr(sgh, "missing_hook_files", lambda root: [])
    assert sgh.main(["--check"]) == 1


def test_check_makes_no_changes(monkeypatch):
    """--check 는 절대 git 설정을 건드리면 안 된다."""
    called = []

    def spy(root):
        called.append("설정")
        return True

    monkeypatch.setattr(sgh, "enable_hooks_path", spy)
    monkeypatch.setattr(sgh, "github_lock_status", lambda root: ("있음", ["main 보호"]))
    sgh.main(["--check"])
    assert called == []
