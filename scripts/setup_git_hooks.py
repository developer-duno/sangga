# -*- coding: utf-8 -*-
"""
main 가지 잠금을 **로컬과 GitHub 양쪽**에서 한 번에 켜고 확인한다.

왜 두 겹인가
------------
잠금은 성격이 다른 두 겹이다. 둘 다 있어야 제 값을 한다.

  ① GitHub 저장소 규칙("main 보호")  = **진짜 잠금.** 검사 2개(test·web) 통과 +
     PR 경유가 아니면 서버가 거부한다. 내 PC 설정과 무관하므로 끌 수 없다.
  ② 로컬 훅(.githooks/)               = **빨리 알려주는 알람.** 커밋·밀어넣기 직전에
     먼저 잡아서 헛걸음을 없앤다. 끄면 그만이라 이것만 믿으면 안 된다.

②만 있으면 다른 사람·다른 컴퓨터에서 그냥 뚫린다. ①만 있으면 커밋을 다 만든 뒤에야
거부당해 가지를 옮기는 뒷수습이 남는다. 그래서 둘을 한 명령에서 함께 본다.

왜 .git/hooks 가 아니라 .githooks 인가
--------------------------------------
`.git/hooks/` 안의 파일은 **git 이 추적하지 않는다.** 새로 내려받거나 다른 컴퓨터에서
열면 그냥 없다 — 아무 경고 없이 알람만 사라진 상태가 된다. 그래서 훅을 저장소에
`.githooks/` 로 담고, git 에게 "훅은 저기서 찾아라"라고 알려 준다(core.hooksPath).
새 컴퓨터에서는 이 명령 한 번이면 켜진다.

쓰는 법
-------
    python scripts/setup_git_hooks.py           # 켜기 + 양쪽 상태 보고
    python scripts/setup_git_hooks.py --check   # 확인만 (아무것도 안 바꿈, 어긋나면 exit 1)

--check 는 회귀 가드용이다. 훅 경로가 풀렸거나 훅 파일이 사라지면 종료코드 1 로 알린다.

GitHub 쪽 확인의 한계 (일부러 이렇게 둔다)
------------------------------------------
GitHub 규칙 확인은 `gh` 명령과 네트워크가 있어야 한다. 없는 환경(CI·비행기)에서도
로컬 점검은 되어야 하므로, **GitHub 쪽을 확인하지 못한 것은 실패로 치지 않는다**
("확인 못 함"으로 표시만). 확인에 성공했는데 잠금이 **없는** 경우에만 실패로 본다 —
"모르는 것"과 "없는 것"을 섞지 않는다.
"""

import argparse
import json
import os
import subprocess
import sys

HOOKS_DIR_NAME = ".githooks"
REQUIRED_HOOKS = ("pre-commit", "pre-push")
PROTECTED_BRANCH = "main"


def repo_root():
    """이 파일 기준으로 저장소 루트를 잡는다(어느 폴더에서 실행해도 같게)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_git(args, cwd):
    """git 을 돌리고 (종료코드, 표준출력) 을 돌려준다. git 이 없으면 (127, '')."""
    try:
        p = subprocess.run(
            ["git"] + list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return 127, ""
    return p.returncode, (p.stdout or "").strip()


def configured_hooks_path(root):
    """지금 설정된 훅 경로. 설정이 없으면 None."""
    code, out = run_git(["config", "--get", "core.hooksPath"], root)
    if code != 0 or not out:
        return None
    return out


def missing_hook_files(root):
    """있어야 하는데 없는 훅 파일 이름 목록."""
    missing = []
    for name in REQUIRED_HOOKS:
        path = os.path.join(root, HOOKS_DIR_NAME, name)
        if not os.path.isfile(path):
            missing.append(name)
    return missing


def enable_hooks_path(root):
    """git 에게 훅을 .githooks 에서 찾으라고 알려 준다."""
    code, _ = run_git(["config", "core.hooksPath", HOOKS_DIR_NAME], root)
    return code == 0


def ensure_executable(root):
    """훅에 실행 권한을 준다(윈도우에서는 의미가 없어 조용히 넘어간다)."""
    changed = []
    for name in REQUIRED_HOOKS:
        path = os.path.join(root, HOOKS_DIR_NAME, name)
        if not os.path.isfile(path):
            continue
        try:
            mode = os.stat(path).st_mode
            want = mode | 0o111
            if want != mode:
                os.chmod(path, want)
                changed.append(name)
        except OSError:
            pass
    return changed


def github_lock_status(root):
    """
    GitHub 쪽 잠금을 확인한다.

    돌려주는 값은 셋 중 하나다:
        ("있음", [규칙이름들])   — 활성 잠금이 있다
        ("없음", [])            — 확인은 됐는데 잠금이 없다
        ("확인못함", [사유])     — gh 가 없거나 네트워크·권한 문제
    """
    try:
        p = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}/rulesets"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return "확인못함", ["gh 명령이 없습니다"]
    if p.returncode != 0:
        detail = (p.stderr or p.stdout or "").strip().splitlines()
        return "확인못함", [detail[0] if detail else "gh 호출 실패"]
    try:
        data = json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        return "확인못함", ["gh 응답을 읽지 못했습니다"]
    active = [
        r.get("name", "(이름 없음)")
        for r in data
        if r.get("target") == "branch" and r.get("enforcement") == "active"
    ]
    if active:
        return "있음", active
    return "없음", []


def report(root, hooks_path, missing, gh_state, gh_detail):
    print("=" * 66)
    print("  main 가지 잠금 상태")
    print("=" * 66)

    ok_local = hooks_path == HOOKS_DIR_NAME and not missing
    mark = "[정상]" if ok_local else "[주의]"
    where = hooks_path if hooks_path else "(설정 없음 — 기본 .git/hooks)"
    print(f"  {mark} 로컬 알람   훅 찾는 곳 = {where}")
    if missing:
        print(f"         빠진 훅 파일: {', '.join(missing)}")
    else:
        print(f"         훅 파일 {len(REQUIRED_HOOKS)}개 모두 있음 ({', '.join(REQUIRED_HOOKS)})")

    if gh_state == "있음":
        print(f"  [정상] GitHub 잠금  활성 규칙: {', '.join(gh_detail)}")
    elif gh_state == "없음":
        print("  [주의] GitHub 잠금  활성 규칙이 없습니다 — 진짜 잠금이 빠졌습니다.")
    else:
        print(f"  [모름] GitHub 잠금  확인하지 못했습니다 ({gh_detail[0] if gh_detail else ''})")
        print("         네트워크·gh 없이도 로컬 점검은 됩니다. 이것만으로는 실패로 보지 않습니다.")

    print("=" * 66)
    return ok_local


def main(argv=None):
    args = argparse.ArgumentParser(
        description="main 가지 잠금을 로컬과 GitHub 양쪽에서 켜고 확인한다."
    )
    args.add_argument(
        "--check",
        action="store_true",
        help="확인만 한다(아무것도 안 바꾼다). 어긋나 있으면 종료코드 1.",
    )
    opts = args.parse_args(argv)

    root = repo_root()

    if not opts.check:
        missing_before = missing_hook_files(root)
        if missing_before:
            print(f"  [멈춤] 훅 파일이 없습니다: {', '.join(missing_before)}", file=sys.stderr)
            print(f"         {HOOKS_DIR_NAME}/ 폴더를 확인하세요.", file=sys.stderr)
            return 1
        if not enable_hooks_path(root):
            print("  [멈춤] git 설정을 바꾸지 못했습니다(git 이 없거나 저장소가 아닙니다).", file=sys.stderr)
            return 1
        changed = ensure_executable(root)
        if changed:
            print(f"  실행 권한을 준 훅: {', '.join(changed)}")

    hooks_path = configured_hooks_path(root)
    missing = missing_hook_files(root)
    gh_state, gh_detail = github_lock_status(root)

    ok_local = report(root, hooks_path, missing, gh_state, gh_detail)

    # "확인 못 함"은 실패가 아니다 — 모르는 것과 없는 것을 섞지 않는다.
    ok_github = gh_state != "없음"

    if ok_local and ok_github:
        if opts.check:
            print("  양쪽 다 제자리입니다.")
        else:
            print("  켰습니다. 이제 main 에 직접 커밋·밀어넣기가 먼저 여기서 막힙니다.")
        return 0

    if not ok_local and not opts.check:
        print("  [멈춤] 켰는데도 어긋나 있습니다 — 위 [주의] 줄을 보세요.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
