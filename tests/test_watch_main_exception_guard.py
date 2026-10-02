# -*- coding: utf-8 -*-
"""
감시 스크립트 일곱 개의 main() 이 **예외로 죽을 때 조용해지지 않는지** 훑는 가드.

왜 필요한가
-----------
파이썬은 잡지 못한 예외로 죽으면 종료코드 1 이다. 그런데 감시 스크립트는 1 의 뜻이 두 부류다.

  A 부류 — 1 = **알릴 일 있음**(지난 자료·새 공고·멈춘 감시). 워크플로는 1 을 통과시켜 이슈
           단계로 넘긴다. 여기서 예외가 1 로 새면 "알릴 일 있음"과 겹친다 — 이슈 파일도 기록도
           없는데 1 이라, 최악에는 그 주가 조용히 초록이 된다. 그래서 main 의 조회·판정은 2,
           결과 쓰기는 4 로 따로 끝낸다(#178·#181·#183).
  B 부류 — 1 = **실패 자체**. 워크플로가 `if: failure()` 로 이슈를 연다. 여기서는 예외가 1 로
           나가는 것이 곧 알림이다. 지킬 것은 하나 — 예외를 삼키고 0 으로 끝내지 않는다.

개별 경우(이 함수가 죽으면 2, 저 함수가 죽으면 4)는 스크립트마다의 시험 파일이 이미 본다.
이 파일은 그 위에서 **"앞으로 main 에 새 호출이 보태져도"** 를 지킨다.

  ① 행동 훑기 — main 이 부르는 모듈 함수를 AST 로 뽑아 아래 표와 대조하고(새 호출이 생기면
     빨강), 표의 이름을 하나씩 예외를 던지는 가짜로 바꿔 main 을 실제로 돌린다.
  ② 구조 검사(A 부류) — 인자 해석 뒤의 문장은 try 안이거나, try 밖이면 허용 목록의 호출뿐이다.
     try 는 Exception 을 잡고 0·1 이 아닌 값을 돌려준다. 처리부 안의 다시 던지기(raise)와,
     try 본문 속 중첩 try 의 처리부가 0·1 을 돌려주거나 다시 던지는 것도 문제로 본다.
     ⓘ 중첩 처리부의 다시 던지기는 바깥 처리부가 받아 실제로는 안전하지만, 규칙을 한 벌로
        두려고 함께 막는다(그 경우 메시지의 "1 로 샐 수 있습니다"는 실제보다 엄격한 말이다).
  ③ 목록 대조 — 예약 워크플로가 돌리는 스크립트 집합 == 이 표의 스크립트 집합.

⛔ 못 보는 것(정직하게 — 2026-10-02 검사관 두 명이 변이로 확인):
   · 호출이 아닌 것에서 나는 예외(`rows[0]`·나눗셈·속성 접근)가 try 밖에 있는 경우, `print` 자체의
     실패, 인자 해석 앞부분.
   · 처리부가 raise 문이 아니라 **끝내는 호출**(`sys.exit(1)`·`os._exit(1)`)로, 그것도 예외 종류를
     가려서 새는 경우(무조건이면 ① 행동 훑기가 잡는다) · try 안의 조건부 정상 반환 1.
   · SystemExit·KeyboardInterrupt 는 Exception 이 아니라 A 부류 main 이 안 잡는다(지금 그런 경로 없음).
   위 셋은 워크플로의 2차 방어(종료코드 1 은 이슈 파일 + 기록이 둘 다 있어야 통과)가 받는다.
   · ⚠️ 2차 방어도 못 받는 것 하나: 중첩 처리부가 좁게 잡고 **대체값만 두는 꼴**(또는
     `contextlib.suppress`)은 그 예외 종류에서만 조용히 0 으로 갈 수 있다. 정당한 대체값과 글자로는
     못 가른다 — main 에 그런 꼴을 넣을 때는 그 스크립트의 시험 파일에 그 경우를 따로 둔다.
⛔ 네트워크·창고·깃허브 호출 0. 닿으면 하네스가 호출을 빠뜨린 것이다(그 자리에서 실패).
"""

import ast
import datetime
import importlib
import os
import re
import socket
import sys
import urllib.request
from typing import Callable, NamedTuple

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
COLLECTORS_DIR = os.path.join(SCRIPTS_DIR, "collectors")
WORKFLOW_DIR = os.path.join(ROOT, ".github", "workflows")
for _p in (SCRIPTS_DIR, COLLECTORS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

A = "A"  # 1 = 알릴 일 있음 → 예외는 2(조회·판정) 또는 4(결과 쓰기)여야 한다
B = "B"  # 1 = 실패 자체 → 예외가 0 으로 삼켜지지만 않으면 된다

QUIET = "알릴 일 없음"
TELL = "알릴 일 있음"
SCENARIOS = (QUIET, TELL)

LOOKUP = 2  # 조회·판정 실패
OUTPUT = 4  # 결과 쓰기 실패


# ── 스크립트마다의 정상 경로 하네스 ───────────────────────────────────────────
#
# 각 함수는 네트워크로 나가는 자리만 가짜로 막고, **main 을 부르는 함수**를 돌려준다.
# 판정·출력 함수는 진짜를 그대로 둔다(작업 폴더와 GITHUB_OUTPUT 이 임시 폴더라 레포에 안 샌다).


def _install_freshness(mp, mod, scenario):
    rows = [{
        "src": "가짜 자료",
        "basis_kind": "기준월",
        "basis": "202608",
        "next_expected": "2000-01-01" if scenario == TELL else "2999-12-31",
        "cadence": "월 1회",
    }]
    mp.setattr(mod, "fetch_rows", lambda base_url, anon_key, sleep=None: rows)
    # --today 를 주면 today_kst 가 안 불린다 — 일부러 안 주고 시계만 가짜로 고정한다.
    mp.setattr(mod, "today_kst", lambda now=None: datetime.date(2026, 10, 2))
    return lambda: mod.main(["--url", "https://example.invalid", "--anon-key", "anon-fake"])


def _install_lh(mp, mod, scenario):
    mp.setenv("MOLIT_KEY", "fake-key")  # 진짜 get_api_key 가 환경변수에서 읽고 끝난다(.env 안 봄)
    row = {
        "pan_id": "P1",
        "pan_nm": "가짜 공고",
        "kind_nm": "분양",
        # 기준선 상수가 올라가도 안 흔들리게 양 끝 날짜를 쓴다. 마감일을 비워 실제 시계에 안 기댄다.
        "notice_date": "2999-12-31" if scenario == TELL else "2000-01-01",
        "close_date": None,
        "pan_ss": "공고중",
        "cnp_nm": "서울",
        "is_nationwide": False,
        "dtl_url": None,
    }
    mp.setattr(mod, "fetch_recent",
               lambda key, months=mod.DEFAULT_MONTHS: ([row], 1, 1, "20260801", "20261001"))
    return lambda: mod.main([])


def _install_heartbeat(mp, mod, scenario):
    # main 이 실제 시계를 직접 읽는다(주입할 자리가 없다). 그래서 기준(1일·8일)에서 아주 먼 값만
    # 쓴다 — "한 시간 전"과 "2000년".
    if scenario == TELL:
        last = datetime.datetime(2000, 1, 1, tzinfo=mod.UTC)
    else:
        last = datetime.datetime.now(mod.UTC) - datetime.timedelta(hours=1)
    mp.setattr(mod, "fetch_all", lambda workflows: [(f, last) for f in workflows])
    # 멈춤이면 진짜 recheck_stale 이 이것을 부른다(네트워크) — 같은 답을 준다.
    mp.setattr(mod, "fetch_recent_success", lambda workflow_file: last)
    return lambda: mod.main([])


def _install_quarter(mp, mod, scenario):
    day = "20991231" if scenario == TELL else "20000101"
    items = [{"name": "소상공인시장진흥공단_상가(상권)정보_{}".format(day)}]
    mp.setattr(mod, "fetch_history_list", lambda: (items, []))
    return lambda: mod.main([])


def _install_district(mp, mod, scenario):
    current = {"sbiz": mod.SBIZ_KNOWN_UPDATE, "seoul": mod.SEOUL_KNOWN_UPDATE}
    if scenario == TELL:
        current["seoul"] = "2999-12-31"
    mp.setattr(mod, "fetch_current_dates", lambda: dict(current))
    return lambda: mod.main([])


def _install_feedback(mp, mod, scenario):
    stats = {
        "opinion_cnt": 3 if scenario == TELL else 0,
        "error_cnt": 0,
        "total_cnt": 3 if scenario == TELL else 0,
        "oldest_days": 1 if scenario == TELL else None,
    }
    mp.setattr(mod, "fetch_stats", lambda base_url, anon_key, days: dict(stats))
    return lambda: mod.main(["--url", "https://example.invalid", "--anon-key", "anon-fake"])


def _install_live(mp, mod, scenario):
    def fake_check(site, sleep=None):
        if scenario == TELL:
            raise mod.CheckFailed("가짜 실패 — 첫 화면이 안 뜹니다")
        return ["가짜 정상"]

    mp.setattr(mod, "check", fake_check)
    # 이 main 만 argv 인자가 없다 — sys.argv 를 직접 읽는다.
    mp.setattr(sys, "argv", ["check_live_health.py", "--site", "https://example.invalid"])
    return lambda: mod.main()


class Target(NamedTuple):
    kind: str            # A 또는 B
    calls: dict          # main 이 (except 처리부 밖에서) 부르는 모듈 함수 → 예외 때 기대 종료코드
    handler_only: tuple  # except 처리부 안에서만 부르는 것 — 워크플로의 2차 방어가 받는다(훑지 않음)
    install: Callable    # 정상 경로 하네스
    normal: dict         # 시나리오 → 가짜를 하나도 안 깨뜨렸을 때의 종료코드
    evidence: dict       # 시나리오 → GITHUB_OUTPUT 에 있어야 할 글자("" = 아무것도 안 씀)


# ⛔ 이 표가 정본이다. main 에 호출을 보태거나 빼면 여기를 함께 고친다.
#    A 부류의 값: 그 함수가 예외를 던질 때의 종료코드(2 조회·판정 / 4 결과 쓰기).
#    B 부류의 값: None — "0 이 아니다"만 본다(잡아서 1 을 돌려주든, 예외가 그대로 나가든).
TARGETS = {
    "check_data_freshness": Target(
        kind=A,
        calls={
            "today_kst": LOOKUP,
            "fetch_rows": LOOKUP,
            "find_overdue": LOOKUP,
            "report": OUTPUT,
            "write_issue_files": OUTPUT,
            "write_github_output": OUTPUT,
        },
        handler_only=(),
        install=_install_freshness,
        normal={QUIET: 0, TELL: 1},
        evidence={QUIET: "overdue=false", TELL: "overdue=true"},
    ),
    "check_lh_notices": Target(
        kind=A,
        calls={
            "get_api_key": LOOKUP,
            "fetch_recent": LOOKUP,
            "to_yyyymmdd": LOOKUP,
            "find_new_notices": LOOKUP,
            "report": OUTPUT,
            "write_issue_body": OUTPUT,
            "write_github_output": OUTPUT,
        },
        handler_only=("lh.mask_key",),
        install=_install_lh,
        normal={QUIET: 0, TELL: 1},
        evidence={QUIET: "found=false", TELL: "found=true"},
    ),
    "check_watch_heartbeat": Target(
        kind=A,
        calls={
            "fetch_all": LOOKUP,
            "fetch_created_at_map": LOOKUP,
            "judge": LOOKUP,
            "recheck_stale": LOOKUP,
            "report": OUTPUT,
        },
        handler_only=(),
        install=_install_heartbeat,
        normal={QUIET: 0, TELL: 1},
        evidence={QUIET: "stale=false", TELL: "stale=true"},
    ),
    "check_new_sangkwon_quarter": Target(
        kind=B,
        calls={
            "fetch_history_list": None,
            "find_new_quarters": None,
            "build_issue_body": None,
            "write_github_output": None,
        },
        handler_only=(),
        install=_install_quarter,
        normal={QUIET: 0, TELL: 0},
        evidence={QUIET: "found=false", TELL: "found=true"},
    ),
    "check_district_source_update": Target(
        kind=B,
        calls={
            "fetch_current_dates": None,
            "known_dates": None,
            "find_changes": None,
            "build_issue_body": None,
            "write_github_output": None,
        },
        handler_only=(),
        install=_install_district,
        normal={QUIET: 0, TELL: 0},
        evidence={QUIET: "found=false", TELL: "found=true"},
    ),
    "feedback_digest": Target(
        kind=B,
        calls={
            "fetch_stats": None,
            "retention_overdue": None,
            "_emit_output": None,
            "build_issue_body": None,
        },
        handler_only=(),
        install=_install_feedback,
        normal={QUIET: 0, TELL: 0},
        evidence={QUIET: "\nfalse\n", TELL: "\ntrue\n"},
    ),
    "check_live_health": Target(
        kind=B,
        calls={"check": None},
        handler_only=("_emit_output",),
        install=_install_live,
        # 이 스크립트는 "사이트가 정상이 아님" 자체가 1 이다(워크플로가 failure() 로 이슈를 연다).
        normal={QUIET: 0, TELL: 1},
        evidence={QUIET: "", TELL: "\ndown\n"},
    ),
}

A_SCRIPTS = sorted(name for name, t in TARGETS.items() if t.kind == A)
SWEEP = [(script, name) for script, t in TARGETS.items() for name in t.calls]


# ── AST: main 이 부르는 "모듈 전역 이름" 뽑기 ─────────────────────────────────


def _read_source(script):
    with open(os.path.join(SCRIPTS_DIR, script + ".py"), encoding="utf-8") as f:
        return f.read()


def _main_def(tree):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    raise AssertionError("main 함수를 못 찾았습니다")


def _is_repo_module(name):
    """그 이름이 이 레포 scripts/ (또는 collectors/) 의 모듈인가."""
    return any(os.path.exists(os.path.join(d, (name or "") + ".py"))
               for d in (SCRIPTS_DIR, COLLECTORS_DIR))


def _module_globals(tree):
    """(그 모듈에 정의됐거나 레포 모듈에서 import 된 함수 이름, 레포 모듈의 별칭)."""
    names, aliases = set(), set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ImportFrom) and _is_repo_module(node.module):
            names.update(a.asname or a.name for a in node.names)
        elif isinstance(node, ast.Import):
            aliases.update(a.asname or a.name for a in node.names if _is_repo_module(a.name))
    return names, aliases


def _walk_calls(node, in_handler=False):
    """(호출 노드, except 처리부 안인가) 를 중첩 블록까지 전부 내놓는다."""
    if isinstance(node, ast.Call):
        yield node, in_handler
    for child in ast.iter_child_nodes(node):
        yield from _walk_calls(child, in_handler or isinstance(child, ast.ExceptHandler))


def main_global_calls(source):
    """main 이 부르는 모듈 전역 이름 → (처리부 밖에서 부르는 것, 처리부 안에서만 부르는 것)."""
    tree = ast.parse(source)
    names, aliases = _module_globals(tree)
    outside, inside = set(), set()
    for call, in_handler in _walk_calls(_main_def(tree)):
        func = call.func
        if isinstance(func, ast.Name) and func.id in names:
            found = func.id
        elif (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
              and func.value.id in aliases):
            found = "{}.{}".format(func.value.id, func.attr)
        else:
            continue  # 내장·표준 라이브러리 — 구조 검사가 본다
        (inside if in_handler else outside).add(found)
    return outside, inside - outside


def test_extractor_sees_nested_calls_and_separates_handlers(monkeypatch):
    """뽑는 눈이 멀지 않았나 — 중첩 블록·제너레이터 안 호출은 잡고, 처리부 안은 따로 둔다."""
    monkeypatch.setitem(globals(), "_is_repo_module", lambda name: name in {"sibling", "helper"})
    source = (
        "import json\n"
        "import sibling as sb\n"
        "from helper import imported\n"
        "def local(): pass\n"
        "def other(): pass\n"
        "def cleanup(): pass\n"
        "def unused(): pass\n"
        "def main(argv=None):\n"
        "    try:\n"
        "        rows = imported()\n"
        "        for r in rows:\n"
        "            if r:\n"
        "                total = sum(1 for x in r if local(x))\n"
        "        sb.fetch(json.dumps(total))\n"
        "    except Exception as e:\n"
        "        print(sb.mask(e))\n"
        "        cleanup()\n"
        "        return 2\n"
        "    other()\n"
        "    return 0\n"
    )
    outside, inside = main_global_calls(source)
    assert outside == {"imported", "local", "sb.fetch", "other"}
    assert inside == {"sb.mask", "cleanup"}


@pytest.mark.parametrize("script", sorted(TARGETS))
def test_main_calls_match_the_table(script):
    """⛔ main 에 새 호출이 생기면(또는 사라지면) 여기서 빨강 — 표에 넣고 기대 종료코드를 정한다."""
    target = TARGETS[script]
    outside, inside = main_global_calls(_read_source(script))
    expected = set(target.calls)
    assert outside == expected, (
        "{}.py 의 main 에 새 호출 {} 가 생겼습니다(또는 {} 가 사라졌습니다) — "
        "tests/test_watch_main_exception_guard.py 의 TARGETS 표에 넣고, 그 함수가 예외를 던질 때 "
        "기대 종료코드를 정하세요(A 부류: 조회·판정 2 / 결과 쓰기 4).".format(
            script, sorted(outside - expected) or "없음", sorted(expected - outside) or "없음")
    )
    assert inside == set(target.handler_only), (
        "{}.py 의 main 이 except 처리부 안에서만 부르는 것이 표와 다릅니다: 실제 {} / 표 {} — "
        "처리부 안에서 죽으면 스크립트는 못 막고 워크플로의 2차 방어가 받습니다. "
        "표의 handler_only 에 이름을 적어 두세요.".format(
            script, sorted(inside), sorted(target.handler_only))
    )


def test_class_a_expectations_are_two_or_four():
    for script in A_SCRIPTS:
        for name, code in TARGETS[script].calls.items():
            assert code in (LOOKUP, OUTPUT), "{}:{} 의 기대 종료코드가 2·4 가 아닙니다".format(script, name)


# ── 행동 훑기 ─────────────────────────────────────────────────────────────────


def _exit_status(outcome):
    """main 의 결과를 프로세스 종료코드로 옮긴다(`sys.exit(main())` 과 같은 규칙)."""
    how, value = outcome
    if how == "raise":
        if not isinstance(value, SystemExit):
            return 1  # 잡지 못한 예외 = 파이썬 기본값 1
        value = value.code
    if value is None:
        return 0
    if isinstance(value, int):
        return int(value)
    return 1  # sys.exit("글자") = 1


def _run(tmp_path, script, scenario, broken=None):
    """임시 폴더에서 main 을 한 번 돌린다 → (결과, 깨뜨린 가짜가 불렸나, GITHUB_OUTPUT 내용)."""
    target = TARGETS[script]
    mod = importlib.import_module(script)
    workdir = tmp_path / ("없음" if scenario == QUIET else "있음")
    workdir.mkdir(exist_ok=True)
    out = workdir / "gh_output.txt"
    network, hits = [], []

    def no_network(*_a, **_kw):
        network.append(1)
        raise AssertionError("이 시험은 네트워크에 닿으면 안 됩니다 — 하네스가 호출을 빠뜨렸습니다")

    def boom(*_a, **_kw):
        hits.append(1)
        raise RuntimeError("가드 시험이 일부러 던진 예외({})".format(broken))

    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(workdir)  # 이슈 본문 파일이 레포에 안 생기게
        mp.setenv("GITHUB_OUTPUT", str(out))
        mp.setattr(urllib.request, "urlopen", no_network)
        mp.setattr(socket, "create_connection", no_network)
        call = target.install(mp, mod, scenario)
        if broken:
            owner, attr = mod, broken
            if "." in broken:
                alias, attr = broken.split(".", 1)
                owner = getattr(mod, alias)
            assert callable(getattr(owner, attr)), "{} 에 {} 가 없습니다".format(script, broken)
            mp.setattr(owner, attr, boom)
        try:
            outcome = ("return", call())
        except (Exception, SystemExit) as ex:
            outcome = ("raise", ex)

    assert not network, "{} [{}] 가 네트워크에 닿으려 했습니다 — 하네스를 고치세요".format(script, scenario)
    text = out.read_text(encoding="utf-8") if out.exists() else ""
    return outcome, bool(hits), text


@pytest.mark.parametrize("script", sorted(TARGETS))
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_harness_walks_the_real_main(tmp_path, script, scenario):
    """가짜를 하나도 안 깨뜨렸을 때 하네스가 진짜 main 을 끝까지 지나는가(가짜 초록 방지)."""
    target = TARGETS[script]
    outcome, _, text = _run(tmp_path, script, scenario)
    assert outcome == ("return", target.normal[scenario]), (
        "{} [{}] 정상 경로가 기대와 다릅니다: {!r}".format(script, scenario, outcome))
    wanted = target.evidence[scenario]
    if wanted:
        assert wanted in text, "{} [{}] 의 GITHUB_OUTPUT 에 {!r} 가 없습니다: {!r}".format(
            script, scenario, wanted, text)
    else:
        assert text == "", "{} [{}] 는 GITHUB_OUTPUT 에 아무것도 안 써야 합니다".format(script, scenario)


@pytest.mark.parametrize("script, name", SWEEP, ids=["{}:{}".format(s, n) for s, n in SWEEP])
def test_exception_in_any_main_call_is_never_quiet(tmp_path, script, name):
    """⛔ main 이 부르는 함수 하나하나가 예외를 던질 때 —
    A 부류: 밖으로 안 새고 표의 종료코드(2·4)와 같다(1 도 0 도 아니다).
    B 부류: 0 이 아니다(조용히 삼키지 않는다)."""
    target = TARGETS[script]
    called_somewhere = False
    for scenario in SCENARIOS:
        outcome, called, _ = _run(tmp_path, script, scenario, broken=name)
        if not called:
            # 이 시나리오에서는 안 불리는 이름이다 — 그러면 결과가 정상 경로와 같아야 한다.
            assert outcome == ("return", target.normal[scenario]), (
                "{}:{} 는 [{}] 에서 안 불렸는데 결과가 정상과 다릅니다: {!r}".format(
                    script, name, scenario, outcome))
            continue
        called_somewhere = True
        if target.kind == A:
            assert outcome[0] == "return", (
                "{}:{} 의 예외가 main 밖으로 샜습니다 [{}] — 파이썬 기본값 1 = '알릴 일 있음'과 "
                "겹칩니다. try 안으로 넣으세요: {!r}".format(script, name, scenario, outcome[1]))
            assert outcome[1] == target.calls[name], (
                "{}:{} 가 예외를 던지면 종료코드 {} 이어야 하는데 {!r} 입니다 [{}]".format(
                    script, name, target.calls[name], outcome[1], scenario))
        else:
            assert _exit_status(outcome) != 0, (
                "{}:{} 의 예외가 종료코드 0 으로 삼켜졌습니다 [{}] — 실패가 조용히 초록이 됩니다".format(
                    script, name, scenario))
    assert called_somewhere, (
        "{}:{} 가 두 시나리오 어디서도 불리지 않았습니다 — 한 번도 안 깨뜨려 보고 초록이면 "
        "가짜 초록입니다. 하네스(시나리오)를 고치세요.".format(script, name))


# ── 구조 검사 (A 부류) ────────────────────────────────────────────────────────

# try 밖(if·대입·return)에서 불러도 되는 것. 이것뿐이다 — 늘리려면 이유를 여기 적는다.
#   print : 인증키 없음·빈 응답 같은 안내 한 줄(스트림은 main 머리에서 errors="replace" 로 맞춰 둔다)
#   list  : 하트비트의 `list(args.workflow)` / `list(DEFAULT_WORKFLOWS)` — 튜플·리스트 복사
#   "글자".format(...) : 위 print 안에서 문구를 맞추는 것(문자열 리터럴에 붙은 것만)
ALLOWED_OUTSIDE_TRY = frozenset({"print", "list"})


def _allowed_outside_try(call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in ALLOWED_OUTSIDE_TRY
    return (isinstance(func, ast.Attribute) and func.attr == "format"
            and isinstance(func.value, ast.Constant) and isinstance(func.value.value, str))


def _int_constants(tree):
    """모듈 최상위의 `이름 = 정수` (EXIT_* 상수 값을 알기 위해)."""
    out = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant) and type(node.value.value) is int):
            out[node.targets[0].id] = node.value.value
    return out


def _catches_exception(handler):
    kinds = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(k, ast.Name) and k.id == "Exception" for k in kinds)


def structure_problems(source):
    """main 의 인자 해석 뒤 최상위 문장을 보고 어긴 것을 글로 돌려준다(없으면 빈 목록)."""
    tree = ast.parse(source)
    main = _main_def(tree)
    constants = _int_constants(tree)
    start = next(
        (i for i, stmt in enumerate(main.body)
         if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "parse_args" for n in ast.walk(stmt))),
        None,
    )
    if start is None:
        return ["main 에서 parse_args 호출을 못 찾았습니다 — 어디부터 볼지 알 수 없습니다"]

    problems = []
    for stmt in main.body[start + 1:]:
        if not isinstance(stmt, ast.Try):
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call) and not _allowed_outside_try(node):
                    problems.append("{}줄: try 밖 호출 `{}`".format(node.lineno, ast.unparse(node.func)))
            continue
        if stmt.finalbody:
            problems.append("{}줄: finally 절 — 그 안은 try 보호 밖입니다".format(stmt.lineno))
        if stmt.orelse:
            problems.append("{}줄: else 절 — 그 안은 try 보호 밖입니다".format(stmt.lineno))
        if not any(_catches_exception(h) for h in stmt.handlers):
            problems.append(
                "{}줄: Exception 을 잡는 처리부가 없거나 더 넓게(BaseException·맨몸 except) "
                "잡습니다".format(stmt.lineno))
        for handler in stmt.handlers:
            if not isinstance(handler.body[-1], ast.Return):
                problems.append("{}줄: 처리부가 return 으로 끝나지 않습니다".format(handler.lineno))
            problems += _handler_problems(handler, constants, "처리부")
        # try 본문 속 중첩 try 의 처리부 — 좁게 잡는 것은 괜찮다(나머지는 바깥 처리부가 받는다).
        # 그러나 거기서 0·1 을 돌려주거나 다시 던지면 예외 종류를 가려 새는 길이 된다. 훑기는
        # RuntimeError 하나만 던져 보므로 "OSError 일 때만 1" 같은 길은 여기서만 잡힌다.
        for inner in stmt.body:
            for node in ast.walk(inner):
                if isinstance(node, _TRY_NODES):
                    for handler in node.handlers:
                        problems += _handler_problems(handler, constants, "중첩 처리부")
    return list(dict.fromkeys(problems))  # 중첩의 중첩은 두 번 보인다 — 같은 줄은 한 번만


_TRY_NODES = tuple(t for t in (ast.Try, getattr(ast, "TryStar", None)) if t is not None)


def _handler_problems(handler, constants, label):
    """except 처리부 하나(그 안의 중첩 포함)에서 — 0·1 을 돌려주거나 다시 던지면 문제."""
    problems = []
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            problems.append(
                "{}줄: {} 안에서 다시 던집니다(raise) — 예외 종류를 가려 종료코드 1 로 "
                "샐 수 있습니다".format(node.lineno, label))
        if not isinstance(node, ast.Return):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and type(value.value) is int:
            code = value.value
        elif isinstance(value, ast.Name) and value.id in constants:
            code = constants[value.id]
        else:
            problems.append("{}줄: {}의 return 값을 알 수 없습니다".format(node.lineno, label))
            continue
        if code in (0, 1):
            problems.append(
                "{}줄: {}가 {} 을 돌려줍니다 — 0 은 조용한 초록, 1 은 '알릴 일 있음'과 "
                "겹칩니다".format(node.lineno, label, code))
    return problems


@pytest.mark.parametrize("script", A_SCRIPTS)
def test_class_a_main_keeps_everything_inside_try(script):
    """⛔ A 부류 main: 인자 해석 뒤에는 try 안이거나, 밖이면 허용 목록(print·list·글자.format)뿐."""
    problems = structure_problems(_read_source(script))
    assert problems == [], (
        "{}.py 의 main 이 예외를 종료코드 1 로 흘릴 수 있습니다 — 이 스크립트는 1 이 '알릴 일 "
        "있음'이라 겹칩니다. try 안으로 넣고 2(조회·판정) 또는 4(결과 쓰기)로 끝내세요:\n  {}".format(
            script, "\n  ".join(problems))
    )


_FAKE_HEAD = (
    "EXIT_OUTPUT_FAILED = 4\n"
    "EXIT_TELL = 1\n"
    "def main(argv=None):\n"
    "    args = parser.parse_args(argv)\n"
)
_FAKE_GOOD_TRY = (
    "    try:\n"
    "        rows = fetch()\n"
    "    except Exception as e:\n"
    "        print('실패 {}'.format(e))\n"
    "        return 2\n"
)


def test_structure_check_passes_a_clean_main():
    """음성 대조 — 멀쩡한 main 은 안 걸린다(늘 걸리는 검사가 아닌지)."""
    source = _FAKE_HEAD + (
        "    names = list(args.names)\n"
        "    if not names:\n"
        "        print('이름 {} 없음'.format(args.names))\n"
        "        return 2\n"
        + _FAKE_GOOD_TRY +
        "    try:\n"
        "        write(rows)\n"
        "    except Exception:\n"
        "        return EXIT_OUTPUT_FAILED\n"
        "    return 1 if rows else 0\n"
    )
    assert structure_problems(source) == []


@pytest.mark.parametrize("body, expect", [
    (_FAKE_GOOD_TRY + "    with open('x.md', 'w') as f:\n        pass\n    return 0\n",
     "try 밖 호출 `open`"),
    ("    rows = fetch()\n    return 0\n", "try 밖 호출 `fetch`"),
    ("    stamp = datetime.datetime.now()\n    return 0\n", "try 밖 호출 `datetime.datetime.now`"),
    ("    print(args.fmt.format(1))\n    return 0\n", "try 밖 호출 `args.fmt.format`"),
    ("    try:\n        rows = fetch()\n    except Exception:\n        return 1\n    return 0\n",
     "처리부가 1 을 돌려줍니다"),
    ("    try:\n        rows = fetch()\n    except Exception:\n        return 0\n    return 0\n",
     "처리부가 0 을 돌려줍니다"),
    ("    try:\n        rows = fetch()\n    except Exception:\n        return EXIT_TELL\n    return 0\n",
     "처리부가 1 을 돌려줍니다"),
    ("    try:\n        rows = fetch()\n    except Exception:\n        return code\n    return 0\n",
     "return 값을 알 수 없습니다"),
    ("    try:\n        rows = fetch()\n    except ValueError:\n        return 2\n    return 0\n",
     "Exception 을 잡는 처리부가 없거나 더 넓게"),
    ("    try:\n        rows = fetch()\n    except:\n        return 2\n    return 0\n",
     "Exception 을 잡는 처리부가 없거나 더 넓게"),
    ("    try:\n        rows = fetch()\n    except BaseException:\n        return 2\n    return 0\n",
     "Exception 을 잡는 처리부가 없거나 더 넓게"),
    ("    try:\n        rows = fetch()\n    except Exception:\n        rows = []\n    return 0\n",
     "처리부가 return 으로 끝나지 않습니다"),
    ("    try:\n        rows = fetch()\n    except Exception:\n        return 2\n"
     "    finally:\n        cleanup()\n    return 0\n", "finally 절"),
    ("    try:\n        rows = fetch()\n    except Exception:\n        return 2\n"
     "    else:\n        write(rows)\n    return 0\n", "else 절"),
    ("    try:\n        rows = fetch()\n    except ValueError:\n        return 1\n"
     "    except Exception:\n        return 2\n    return 0\n", "처리부가 1 을 돌려줍니다"),
    # ↓ 예외 종류를 가려 새는 길 — 훑기(RuntimeError 하나만 던진다)로는 못 잡는다.
    ("    try:\n        rows = fetch()\n    except Exception as e:\n"
     "        if isinstance(e, OSError):\n            raise\n        return 2\n    return 0\n",
     "처리부 안에서 다시 던집니다"),
    ("    try:\n        rows = fetch()\n    except Exception as e:\n"
     "        raise RuntimeError('감쌈') from e\n        return 2\n    return 0\n",
     "처리부 안에서 다시 던집니다"),
    ("    try:\n        try:\n            rows = fetch()\n        except OSError:\n            return 1\n"
     "    except Exception:\n        return 2\n    return 0\n", "중첩 처리부가 1 을 돌려줍니다"),
    ("    try:\n        for f in args.files:\n            if f:\n                try:\n"
     "                    rows = fetch(f)\n                except KeyError:\n"
     "                    return 0\n"
     "    except Exception:\n        return 2\n    return 0\n", "중첩 처리부가 0 을 돌려줍니다"),
    ("    try:\n        try:\n            rows = fetch()\n        except OSError:\n            raise\n"
     "    except Exception:\n        return 2\n    return 0\n", "중첩 처리부 안에서 다시 던집니다"),
], ids=["try밖-open", "try밖-모듈함수", "try밖-표준라이브러리", "try밖-변수.format",
        "처리부-return1", "처리부-return0", "처리부-상수가1", "처리부-값모름",
        "ValueError만", "맨몸except", "BaseException", "처리부-return없음", "finally", "else",
        "좁은처리부-return1", "처리부-조건부-다시던짐", "처리부-감싸-던짐", "중첩처리부-return1",
        "깊은중첩처리부-return0", "중첩처리부-다시던짐"])
def test_structure_check_catches(body, expect):
    """양성 대조 — 이 검사가 실제로 잡는지(검사 함수가 눈을 감으면 여기가 빨강)."""
    problems = structure_problems(_FAKE_HEAD + body)
    assert any(expect in p for p in problems), problems


def test_structure_check_allows_narrow_nested_handlers():
    """음성 대조 — try 본문 속 중첩 처리부가 좁게 잡는 것 자체는 괜찮다(나머지는 바깥이 받는다).

    2 를 돌려주거나, return 없이 대체값만 두고 이어 가거나, 처리부가 아닌 try 본문에서
    던지는 것은 전부 바깥 `except Exception` 이 받는 길이다.
    """
    source = _FAKE_HEAD + (
        "    try:\n"
        "        try:\n"
        "            rows = fetch()\n"
        "        except OSError:\n"
        "            return 2\n"
        "        try:\n"
        "            again = recheck(rows)\n"
        "        except KeyError:\n"
        "            again = None\n"
        "        if again is None:\n"
        "            raise ValueError('빈 응답')\n"
        "    except Exception:\n"
        "        return 2\n"
        "    return 1 if rows else 0\n"
    )
    assert structure_problems(source) == []


def test_structure_check_needs_parse_args():
    source = "def main(argv=None):\n    rows = fetch()\n    return 0\n"
    assert "parse_args" in structure_problems(source)[0]


# ── 목록 대조: 예약 워크플로가 돌리는 스크립트 == 이 표 ────────────────────────

RE_SCRIPT = re.compile(r"\bpython3?\s+(scripts/[\w./-]+\.py)")


def _scheduled_run_steps():
    """예약(`schedule:`)이 있는 워크플로의 `run:` 중 scripts/*.py 를 부르는 것 → [(파일, 스크립트, run 글)]."""
    found = []
    for name in sorted(os.listdir(WORKFLOW_DIR)):
        if not name.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(WORKFLOW_DIR, name), encoding="utf-8") as f:
            text = f.read()
        if "schedule:" not in text:
            continue
        for job in (yaml.safe_load(text).get("jobs") or {}).values():
            for step in job.get("steps") or []:
                run = step.get("run") or ""
                code = "\n".join(ln for ln in run.splitlines() if not ln.lstrip().startswith("#"))
                for script in RE_SCRIPT.findall(code):
                    found.append((name, script, run))
    return found


def test_table_covers_exactly_the_scripts_the_watch_workflows_run():
    """⛔ 새 감시 스크립트가 생기면(또는 사라지면) 빨강 — 표에 넣고 A/B 부류를 정한다."""
    in_workflows = {script for _, script, _ in _scheduled_run_steps()}
    in_table = {"scripts/{}.py".format(name) for name in TARGETS}
    assert in_workflows, "예약 워크플로에서 scripts/*.py 호출을 하나도 못 찾았습니다 — 훑는 눈이 멀었습니다"
    assert in_workflows == in_table, (
        "예약 워크플로가 돌리는 스크립트와 이 가드의 대상 표가 다릅니다 — 워크플로에만 {} / 표에만 {}. "
        "tests/test_watch_main_exception_guard.py 의 TARGETS 에 넣고(또는 빼고) 종료코드 1 의 뜻"
        "(A: 알릴 일 있음 / B: 실패)을 정하세요.".format(
            sorted(in_workflows - in_table) or "없음", sorted(in_table - in_workflows) or "없음")
    )


def test_class_matches_how_the_workflow_reads_exit_code_one():
    """A/B 부류가 워크플로와 맞나 — A 는 종료코드를 받아(`rc=$?`) 1 을 가르고, B 는 그대로 실패시킨다.

    어긋나면 표의 부류가 낡은 것이다: B 스크립트의 1 을 워크플로가 '알릴 일'로 읽기 시작했으면
    그 스크립트는 A 로 옮기고 구조 검사를 받아야 한다.
    """
    steps = _scheduled_run_steps()
    assert steps
    for workflow, script, run in steps:
        name = os.path.splitext(os.path.basename(script))[0]
        reads_code = "rc=$?" in run
        assert reads_code == (TARGETS[name].kind == A), (
            "{} 의 {} 단계: 워크플로가 종료코드를 {} 표는 {} 부류입니다".format(
                workflow, script, "받아 가르는데" if reads_code else "안 받는데", TARGETS[name].kind)
        )
