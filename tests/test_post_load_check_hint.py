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
    (`sys.stdout.write`·logging·문자열 목록을 나중에 찍는 꼴 — 예 check_lh_notices.py 의 명령 목록 →
    `missing_check_in_command_lists` 가 본다) · '다음:' 대신 다른 낱말로 시작하는 안내.
    """
    bad = []
    for no, line in enumerate(text.splitlines(), 1):
        if RE_PRINT.search(line) and "다음:" in line and "post_load.py" in line and "--check" not in line:
            bad.append((no, line.strip()))
    return bad


RE_LIST_ITEM = re.compile(r'^\s*[fFrRuU]{0,2}["\']')  # f"…"·r"…" 접두도 (2026-10-06 검사관 🟡)
RE_POST_LOAD_START = re.compile(r'^python\s+scripts/post_load\.py(?=\s|$|["\'])')  # 주석 없이 따옴표로 바로 닫히는 꼴도


def missing_check_in_command_lists(text):
    """문자열 목록 꼴 안내(각 줄이 따옴표 문자열 하나)에서 `python scripts/post_load.py` 로
    시작하는 줄을 찾아, 바로 뒤가 `--check` 가 아니고 **다음 3줄 안**에도
    `post_load.py --check` 가 든 줄이 없으면 (줄번호, 줄) 목록을 돌려준다.

    잡는 꼴: `"python scripts/post_load.py   # 주석",` 처럼 따옴표로 시작하는 줄 하나에
    `python scripts/post_load.py` 로 시작하되 뒤에 공백만 있고 `--check` 가 없는 경우
    (큰따옴표·작은따옴표·공백 두 칸 이상 섞인 변형 포함), 그 뒤 1~3줄 안에 `--check` 짝이
    없는 경우.
    f·r 접두(`f"python scripts/post_load.py"`)도 본다. 짝이 4줄 이상 떨어지면 일부러 빨강이다
    (안내가 그만큼 떨어지면 사람이 짝으로 못 읽는다).
    못 보는 것: 한 줄에 두 명령이 같이 적힌 꼴(그 줄 자체에 `--check` 가 있으면 짝으로 친다) ·
    따옴표로 시작하지 않는 목록(괄호 `("…",`·`+ "…"` 이어 붙이기·딕셔너리 값) · `post_load.py`
    앞에 다른 낱말이 붙어 뒤로 밀린 줄.
    """
    bad = []
    lines = text.splitlines()
    for no, line in enumerate(lines, 1):
        stripped = line.strip()
        m = RE_LIST_ITEM.match(line)
        if not m:
            continue
        # 접두·따옴표를 떼고 "python scripts/post_load.py" 로 시작하는지 본다(공백 1칸 이상 허용)
        if not RE_POST_LOAD_START.match(line[m.end():]):
            continue
        if "--check" in line:
            continue
        paired = False
        for j in range(no, min(no + 3, len(lines))):
            if "post_load.py --check" in lines[j]:
                paired = True
                break
        if not paired:
            bad.append((no, stripped))
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


def test_every_command_list_mentions_check():
    bad = []
    seen = 0
    for path in _script_files():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for line in text.splitlines():
            m = RE_LIST_ITEM.match(line)
            if m and RE_POST_LOAD_START.match(line[m.end():]):
                seen += 1
        for no, line in missing_check_in_command_lists(text):
            bad.append("{}:{}: {}".format(os.path.relpath(path, ROOT), no, line))
    assert seen >= 3, "전제: 문자열 목록 꼴 post_load.py 줄 3곳 이상을 실제로 훑었다(헛돌기 방지) — {}곳".format(seen)
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


def test_positive_control_command_list_common_shape():
    # 흔한 꼴 — 큰따옴표, 주석 붙은 줄 하나만, 뒤에 --check 짝 없음
    line = '        "python scripts/post_load.py                 # vacuum + 요약표 갱신 + 신선도 점검",'
    assert missing_check_in_command_lists(line + "\n") == [(1, line.strip())]


def test_positive_control_command_list_bare_shape():
    # 변형 꼴 — 주석 없이 따옴표로 바로 닫힌다(메인 검토에서 처음 정규식이 놓친 꼴)
    line = '        "python scripts/post_load.py",'
    assert missing_check_in_command_lists(line + "\n") == [(1, line.strip())]


def test_positive_control_command_list_fstring_shape():
    # 변형 꼴 — f 문자열 목록 항목(2026-10-06 검사관 🟡: 처음 탐지가 놓쳤다)
    line = '        f"python scripts/post_load.py   # {n}행 적재 뒤",'
    assert missing_check_in_command_lists(line + "\n") == [(1, line.strip())]


def test_positive_control_command_list_variant_shape():
    # 변형 꼴 — 작은따옴표, 공백 두 칸, --check 짝이 4줄 아래(3줄 안이 아님) → 여전히 빨강
    text = (
        "        'python  scripts/post_load.py   # 요약표 갱신',\n"
        "        '그 사이 안내 줄 1',\n"
        "        '그 사이 안내 줄 2',\n"
        "        '그 사이 안내 줄 3',\n"
        "        'python scripts/post_load.py --check   # 권한 점검',\n"
    )
    bad = missing_check_in_command_lists(text)
    assert bad == [(1, "'python  scripts/post_load.py   # 요약표 갱신',")]


@pytest.mark.parametrize("line", [
    # 짝이 맞는 두 줄(바로 다음 줄에 --check)
    (
        '        "python scripts/post_load.py                 # vacuum + 요약표 갱신 + 신선도 점검",\n'
        '        "python scripts/post_load.py --check         # 권한(노출) 점검 — 위 줄에서는 안 돈다",\n'
    ),
    # --check 한 줄만
    '        "python scripts/post_load.py --check",\n',
    # post_load.py 가 아니라 다른 스크립트
    '        "python scripts/collectors/load_seoul_district.py --dry-run",\n',
])
def test_negative_controls_command_list_pass(line):
    assert missing_check_in_command_lists(line) == []
