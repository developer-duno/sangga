# -*- coding: utf-8 -*-
"""적재 뒤 '다음:' 안내가 `post_load.py` 를 말하면 `--check` 도 말해야 한다(2026-10-06).

`post_load.py`(옵션 없음)는 vacuum·요약표·신선도만 돈다 — 권한(공개키가 읽거나 고칠 수 있는 것)·
옛 문 닫힘·정본 색인·별관 점검은 `--check` 에서만 돈다(CLAUDE.md 운영 7계명 🔎). 적재기 끝
안내가 앞의 것만 말하면 사람은 그것만 돌리고 끝낸다.

⛔ 탐지는 이 파일 안의 작은 함수 하나(`missing_check_hints`)로 — 가드 본체와 양성 대조가
   같은 함수를 지난다(2026-10-02 #190 규칙).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")

RE_PRINT = re.compile(r"\bprint\s*\(")


def missing_check_hints(text):
    """`print(` 이 든 줄 가운데 '다음:' 안내이면서 `post_load.py` 를 말하는데 `--check` 가 없는 줄
    (1부터 센 줄 번호, 줄) 목록.

    잡는 꼴: `print("  다음: python scripts/post_load.py   (…)")` · 따옴표 종류·f 문자열·
    `print (` 처럼 괄호 앞 공백이 있는 꼴.
    못 보는 것: 여러 줄에 걸친 print(첫 줄에 '다음:'·`post_load.py`·`--check` 가 함께 있어야 한다 —
    `--check` 만 다음 줄에 있으면 빨강, '다음:' 이 다른 줄이면 못 본다) · print 가 아닌 출력
    (`sys.stdout.write`·logging·문자열 목록을 나중에 찍는 꼴 — 예 check_lh_notices.py 의 명령 목록) ·
    '다음:' 대신 다른 낱말로 시작하는 안내.
    """
    bad = []
    for no, line in enumerate(text.splitlines(), 1):
        if RE_PRINT.search(line) and "다음:" in line and "post_load.py" in line and "--check" not in line:
            bad.append((no, line.strip()))
    return bad


def _script_files():
    for dirpath, dirnames, filenames in os.walk(SCRIPTS_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def test_every_next_hint_mentions_check():
    bad = []
    seen = 0
    for path in _script_files():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for line in text.splitlines():
            if RE_PRINT.search(line) and "다음:" in line and "post_load.py" in line:
                seen += 1
        for no, line in missing_check_hints(text):
            bad.append("{}:{}: {}".format(os.path.relpath(path, ROOT), no, line))
    assert seen >= 6, "전제: 적재기 다음: 안내 6곳 이상을 실제로 훑었다(헛돌기 방지) — {}곳".format(seen)
    assert bad == [], "\n".join(bad)


@pytest.mark.parametrize("line", [
    # 흔한 꼴 — 고치기 전 적재기 다섯이 이랬다
    '    print("  다음: python scripts/post_load.py   (vacuum + 요약표 갱신)")',
    # 변형 꼴 — 작은따옴표 f 문자열 · print 와 괄호 사이 공백
    "    print (f'다음:  python  scripts/post_load.py  — {n:,}행 적재')",
])
def test_positive_control_missing_check_is_caught(line):
    assert missing_check_hints("x = 1\n" + line + "\n") == [(2, line.strip())]


@pytest.mark.parametrize("line", [
    '    print("  다음: python scripts/post_load.py   그리고   python scripts/post_load.py --check")',
    '    print("       python scripts/post_load.py 를 실행하면 다시 굽습니다.")',   # '다음:' 안내가 아니다
    '    print("  다음: python scripts/collectors/load_seoul_district.py --dry-run")',  # post_load 가 아니다
])
def test_negative_controls_pass(line):
    assert missing_check_hints(line + "\n") == []
