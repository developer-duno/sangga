# -*- coding: utf-8 -*-
"""라이브 감시가 **어떤 알림을 내보내는가** — 검사 자체가 아니라 그 뒤의 배선을 본다.

왜 이 파일이 따로 필요했나 (2026-09-01 2차 적대검증)
----------------------------------------------------
감시가 사고를 **정확히 잡아도**, 그 사고를 알리는 글이 틀리면 알림은 있으나 마나가 아니라
**거꾸로 해가 된다.** 실제로 그런 상태였다.

  · 실패에 종류가 없어서 워크플로가 **모든 실패에 같은 제목·같은 대본**을 썼다.
  · 그 대본(.github/live-health-failure-issue.md) 첫 지시는
      "주소를 직접 열어 봅니다 … **멀쩡히 뜬다 → 이 이슈를 닫으세요**"
    인데, **관리자 키가 샌 날은 사이트가 멀쩡히 뜬다.**
    ⇒ 운영자에게 **유출 이슈를 닫으라고 지시**하게 된다.
  · 게다가 중복 방지가 제목 **완전일치**라, 이미 열린 '사이트 다운' 이슈가 유출 알림을
    **통째로 삼킨다.**

이 파일은 그 배선이 되살아나지 못하게 지킨다. 검사 로직 자체는
`tests/test_check_live_health.py` 소관이고, 여기는 **"잡은 뒤 무슨 말을 하는가"** 만 본다.

⚠️ 워크플로 전체를 실제로 실행하지는 않는다(러너가 없다). 위쪽 시험들은 글자를 읽어 배선을
   확인하고, 2026-10-02 부터는 **이슈를 여는 단계 하나**만 가짜 `gh` 로 진짜 bash 에서 돌린다
   (아래 「세 갈래」 절). 그래도 "이 파일이 초록 = 알림이 진짜 잘 나간다"는 아니다 —
   진짜 gh·진짜 GitHub 는 한 번도 안 부른다.

세 번째 갈래 (2026-10-02)
-------------------------
종류(kind)는 스크립트가 "정상이 아니다"라고 **판정했을 때만** 온다. 스크립트가 다른 예외로
죽거나 그 앞 단계(받기·파이썬 설치)가 실패하면 kind 가 빈 채로 오는데, 예전 워크플로는 그것을
'사이트 다운'으로 쳤다. 그 대본의 첫 지시가 "멀쩡히 뜬다 → 이 이슈를 닫으세요"라, 감시가
고장 난 날(사이트는 대개 멀쩡하다) 운영자는 닫고 끝낸다 — 그동안 **관리자 키 검사도 안 돈**
사실을 모른 채. ⇒ 정확히 leak · 정확히 down 이 아니면 '감시 고장' 제목·대본으로 간다.
"""

import io
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "check_live_health.py")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "live-health-watch.yml")
DOWN_BODY = os.path.join(ROOT, ".github", "live-health-failure-issue.md")
LEAK_BODY = os.path.join(ROOT, ".github", "live-health-leak-issue.md")
BROKEN_BODY = os.path.join(ROOT, ".github", "live-health-broken-issue.md")

# 제목은 **글자 그대로** 여기 적는다 — 워크플로에서 읽어 오면 둘이 함께 틀려도 초록이다.
LEAK_TITLE = "🔴 배포된 화면에 관리자 키가 실렸습니다 — 즉시 회전이 필요합니다"
DOWN_TITLE = "라이브 사이트가 정상이 아닙니다 — 확인이 필요합니다"
BROKEN_TITLE = "라이브 감시가 확인을 끝내지 못했습니다 — 사이트 상태는 아직 모릅니다"
# '감시 고장' 대본이 '사이트 다운' 대본의 닫으라는 말을 **부정하며 인용**하는 자리의 글자.
DOWN_CLOSE_QUOTE = "'멀쩡히 뜨면 닫으세요'는"


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def chk():
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_live_health", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFailuresCarryAKind:
    """실패가 **자기 종류를 안다** — 이게 없으면 워크플로가 갈라 쓸 재료가 없다."""

    def test_a_plain_failure_is_a_down(self, chk):
        assert chk.CheckFailed("아무 이유").kind == "down"

    def test_an_admin_key_in_the_bundle_is_a_leak(self, chk, monkeypatch):
        """⛔ 이 시험이 빨간불이면 유출 알림이 다시 '사이트 다운' 대본으로 나간다."""
        fake = b"sb_secret_" + b"q" * 30
        html = '<html><div id="root"></div><script src="/assets/app.js"></script></html>'

        def fake_fetch(url, what, attempts=5, sleep=None):
            if url.endswith("/"):
                return html.encode()
            return b"x" * 4096 + fake

        monkeypatch.setattr(chk, "fetch_with_retry", fake_fetch)
        with pytest.raises(chk.CheckFailed) as ex:
            chk.check("https://example.test")
        assert ex.value.kind == "leak", (
            "관리자 키 유출이 'down' 으로 분류되면 워크플로가 '사이트 다운' 대본을 쓴다 — "
            "그 대본은 '사이트가 멀쩡하면 닫으세요'라고 적혀 있어 정확히 거꾸로 지시한다."
        )

    def test_main_hands_the_kind_to_the_workflow(self, chk, monkeypatch, tmp_path):
        """종류를 알아도 **내보내지 않으면** 워크플로는 못 읽는다."""
        out = tmp_path / "gh_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setattr(
            chk, "check", lambda site, sleep=None: (_ for _ in ()).throw(
                chk.CheckFailed("샜다", kind="leak")))
        monkeypatch.setattr("sys.argv", ["check_live_health.py"])
        assert chk.main() == 1
        assert "kind" in out.read_text(encoding="utf-8")
        assert "leak" in out.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def wf():
    return read(WORKFLOW)


class TestTheWorkflowSplitsTitleAndScript:
    """제목과 대본이 종류에 따라 갈라지는가 — 안 갈라지면 삼켜지고 거꾸로 지시한다."""

    def test_it_reads_the_kind_output(self, wf):
        assert "steps.check.outputs.kind" in wf, (
            "워크플로가 kind 를 안 읽으면 스크립트가 내보내도 소용이 없다.")

    def test_it_branches_to_the_leak_script(self, wf):
        assert ".github/live-health-leak-issue.md" in wf
        assert ".github/live-health-failure-issue.md" in wf
        assert re.search(r'KIND[^\n]*=[^\n]*"leak"|"\$\{KIND:-down\}"\s*=\s*"leak"', wf), (
            "kind=leak 분기가 없다 — 유출이 다시 '사이트 다운' 대본으로 나간다.")

    def test_the_two_titles_are_different(self, wf):
        """⛔ 제목이 같으면 중복 방지(완전일치)에 걸려 **유출 알림이 통째로 삼켜진다.**"""
        titles = re.findall(r'^\s*TITLE="([^"]+)"', wf, re.M)
        assert len(titles) >= 2, "제목이 하나뿐이다 — 종류별로 갈라져 있지 않다."
        assert len(set(titles)) == len(titles), (
            "같은 제목이 둘 이상이다 — 먼저 열린 이슈가 나중 사고를 삼킨다: {}".format(titles))

    def test_an_unknown_kind_gets_its_own_script_not_the_down_one(self, wf):
        """확인 단계가 아예 못 돌면 kind 가 비어 온다 — 그때 '사이트 다운'으로 치지 않는다.

        예전 규칙은 "비면 down" 이었다(2026-10-02 에 바꿈 — 파일 머리말 「세 번째 갈래」).
        ⓘ 글자 검사다. 실제로 그렇게 갈라지는지는 아래 「세 갈래」 절이 bash 로 돌려서 본다
           (이 '없음' 단언의 양성 대조도 거기 있다 — 옛 꼴을 넣으면 빨강이 되는지).
        """
        assert "KIND:-down" not in wf, "빈 kind 를 down 으로 치는 옛 꼴이 되살아났다."
        assert ".github/live-health-broken-issue.md" in wf
        assert BROKEN_TITLE in wf


class TestTheLeakScriptSaysTheOppositeOfTheDownScript:
    """대본 내용 자체를 본다 — 배선만 맞고 글이 틀리면 같은 사고다."""

    def test_the_down_script_still_tells_you_to_close_when_the_site_is_up(self):
        """전제 확인. 이 문장이 사라지면 이 파일의 존재 이유가 바뀐 것이니 다시 생각한다."""
        assert "이 이슈를 닫으세요" in read(DOWN_BODY)

    def test_the_leak_script_forbids_closing_just_because_the_site_loads(self):
        body = read(LEAK_BODY)
        assert "사이트는 멀쩡히 뜹니다" in body
        assert "닫지 마세요" in body

    def test_the_leak_script_puts_rotation_first(self):
        """⛔ 회전(재발급)이 **파일 고치기보다 먼저**여야 한다 — 고치는 동안에도 옛 열쇠는
        계속 유효하다."""
        body = read(LEAK_BODY)
        assert "회전" in body
        assert body.index("회전") < body.index("다시 배포")

    def test_the_leak_script_tells_you_not_to_paste_the_value(self):
        """값을 이슈에 붙여넣으면 **더 퍼진다.** 그 경고가 대본에 있어야 한다."""
        assert "붙여넣지 마세요" in read(LEAK_BODY)

    def test_the_leak_script_handles_the_false_alarm_path(self):
        """오탐을 방치하면 6시간마다 같은 이슈가 열려 **진짜 사고까지 함께 묻힌다.**
        전례가 실제로 있었다(supabase-js 가 접두사를 맨몸으로 들고 있었다)."""
        body = read(LEAK_BODY)
        assert "오탐" in body
        assert "ADMIN_KEY_RE" in body


class TestTheHomePageIsScannedToo:
    """첫 화면(HTML)에 키가 박히는 경로도 막는다 — 이미 손에 든 글자라 추가 요청 0."""

    def test_an_admin_key_in_the_html_is_caught(self, chk, monkeypatch):
        fake = b"sb_secret_" + b"w" * 30
        html = ('<html><div id="root"></div><script src="/assets/app.js"></script>'
                '<script>window.K="').encode() + fake + b'"</script></html>'

        def fake_fetch(url, what, attempts=5, sleep=None):
            return html if url.endswith("/") else b"y" * 4096

        monkeypatch.setattr(chk, "fetch_with_retry", fake_fetch)
        with pytest.raises(chk.CheckFailed) as ex:
            chk.check("https://example.test")
        assert ex.value.kind == "leak"

    def test_a_clean_home_page_still_passes(self, chk, monkeypatch):
        """⛔ 거짓 경보를 내면 6시간마다 열려 진짜 사고까지 묻힌다 — 반대편도 못 박는다."""
        html = '<html><div id="root"></div><script src="/assets/app.js"></script></html>'

        def fake_fetch(url, what, attempts=5, sleep=None):
            if url.endswith("/"):
                return html.encode()
            if url.endswith(".js"):
                return b"z" * 4096
            return b'{"type":"FeatureCollection"}'

        monkeypatch.setattr(chk, "fetch_with_retry", fake_fetch)
        assert len(chk.check("https://example.test")) == 3


class TestTheBrokenScriptDoesNotTellYouToClose:
    """'감시 고장' 대본 — 사이트가 멀쩡해 보여도 닫으라고 하지 않는다 (2026-10-02)."""

    def test_its_first_line_says_this_is_not_a_site_down_alarm(self):
        first = read(BROKEN_BODY).splitlines()[0]
        assert "확인을 끝내지 못했습니다" in first
        assert "사이트가 죽었다는 뜻이 아닙니다" in first

    def test_it_says_the_admin_key_check_did_not_run(self):
        """⛔ 이 갈래를 만든 이유 — 감시가 못 돈 동안 **유출 검사도 안 돌았다.**"""
        assert "관리자 키 검사도 안 돌았습니다" in read(BROKEN_BODY)

    def test_it_never_tells_you_to_close_because_the_site_loads(self):
        """⛔ '사이트 다운' 대본의 그 문장이 여기 있으면 운영자는 닫고 끝낸다.

        양성 대조: 같은 글자 검사가 '사이트 다운' 대본에서는 그 문장을 실제로 본다 —
        `test_the_down_script_still_tells_you_to_close_when_the_site_is_up`.
        """
        body = read(BROKEN_BODY)
        assert "이 이슈를 닫으세요" not in body
        # '닫으세요' 라는 글자는 딱 한 번 — "그 말은 이 이슈에는 해당하지 않는다"고 **부정하며 인용**한 자리뿐.
        assert body.count("닫으세요") == body.count(DOWN_CLOSE_QUOTE) == 1
        assert "닫지 마세요" in body
        assert "닫아도 되는 이유가 아닙니다" in body

    def test_closing_is_not_an_instruction_before_the_closing_section(self):
        """'닫아도 될 때' 절 앞에서 '닫'이 나오는 자리는 "닫지 마세요"와, '사이트 다운' 대본의
        닫으라는 말을 **부정하며 인용**한 한 곳뿐이다 — 닫으라는 말이 첫 지시가 아니다."""
        body = read(BROKEN_BODY)
        head = body[:body.index("## 이 이슈를 닫아도 될 때")]
        assert head.count("닫지 마세요") >= 1
        assert head.count("닫") == head.count("닫지 마세요") + head.count(DOWN_CLOSE_QUOTE)

    def test_it_does_not_send_you_back_to_the_close_it_instruction(self):
        """⛔ 내 PC 확인에서 `[실패]` 가 나와 '사이트 다운' 대본으로 넘어갈 때, 그 대본의 첫 지시
        ("멀쩡히 뜬다 → 이 이슈를 닫으세요")를 따라 **이 이슈를 닫는** 길을 막는다 (검사관 지적).

        넘겨 보내는 자리가 「어디가 깨졌나」 절이고, 그 절이 '사이트 다운' 대본에 실제로 있어야 한다.
        """
        body = read(BROKEN_BODY)
        assert "해당하지 않습니다" in body
        assert DOWN_CLOSE_QUOTE in body
        assert "「어디가 깨졌나」 절부터" in body
        assert "## 어디가 깨졌나" in read(DOWN_BODY)

    def test_the_only_reason_to_close_is_that_the_watch_ran_again(self):
        body = read(BROKEN_BODY)
        section = body.index("## 이 이슈를 닫아도 될 때")
        cond = body.index("감시가 다시 정상으로 돈 것을 확인한 뒤")
        assert section < cond < body.index("닫아 주세요")
        assert "닫아야 다음 고장을 다시 알립니다" in body

    def test_it_tells_you_what_to_do_by_hand(self):
        """주소를 직접 열기 → 하얗면 '사이트 다운' 대본 → 내 PC 에서 감시가 못 본 것을 대신 본다."""
        body = read(BROKEN_BODY)
        assert "https://sangga-one.vercel.app" in body
        assert ".github/live-health-failure-issue.md" in body
        assert "Promote to Production" in body
        assert "```powershell" in body
        assert "python scripts/check_live_health.py" in body
        # PowerShell 5.1 에 없는 bash 문법을 드리지 않는다.
        assert "&&" not in body
        assert "/dev/null" not in body

    def test_the_words_it_tells_you_to_look_for_are_what_the_script_prints(self):
        """대본이 "이 글자가 보이면 괜찮다"고 한 글자를 스크립트가 실제로 찍어야 한다."""
        body, script = read(BROKEN_BODY), read(SCRIPT)
        for words in ("관리자 키 흔적 없음", "[정상]", "[실패]"):
            assert words in body
            assert words in script

    def test_it_names_the_step_that_can_die(self, wf):
        """대본이 가리키는 단계 이름이 워크플로에 실제로 있다."""
        assert "라이브가 서 있는지 확인" in read(BROKEN_BODY)
        assert "- name: 라이브가 서 있는지 확인" in wf


# ── 세 갈래: 이슈를 여는 단계를 진짜 bash 로 돌린다 (2026-10-02) ─────────────────
#
# 글자 검사만으로는 분기 줄을 망가뜨려도 초록일 수 있다(형제 지난 날짜 감시 2026-10-01 실측).
# 그래서 단계의 run: 글자를 꺼내 GitHub 기본 셸(`bash -e` — `shell:` 을 안 적은 단계의 기본값)로
# 돌리고, PATH 앞에 가짜 `gh` 를 둔다. 네트워크·진짜 gh·진짜 API 는 타지 않는다.
# 윈도우는 Git Bash 로 돈다(WSL 의 System32 bash 는 PATH·경로를 다르게 풀어 건너뛴다).
# 도우미는 tests/test_check_watch_heartbeat.py 의 것을 옮겨 왔다(시험 파일끼리 import 하지 않는다).
#
# ⛔ CI 에서는 bash 가 없으면 건너뛰지 않고 **실패**한다 — 거기서 조용히 skip 되면 이 절이 지키는
#    것(세 갈래·열린 제목 건너뛰기·받기 실패 때도 열기)이 아무도 모르게 다시 열린다.
#
# ⚠️ 가짜 gh 의 한계: "`.git` 도 GH_REPO 도 없으면 실패한다"는 것은 **우리가 그렇게 흉내 낸 것**이다.
#    진짜 gh 가 `.git` 없이 GH_REPO 만으로 도는지는 이 시험이 못 잰다 — 근거는 gh 문서
#    ("gh help environment": GH_REPO = "specify the GitHub repository in the [HOST/]OWNER/REPO
#    format for commands that otherwise operate on a local repository").

ISSUE_STEP_NAME = "라이브가 죽었으면(또는 키가 샜으면) 이슈를 연다"
NO_BODY_LINE = "대본 파일을 읽지 못했습니다 — 저장소 받기 단계가 실패했을 수 있습니다. 실행 기록을 보세요."
NO_REASON_LINE = "(확인 단계가 아예 못 돌았습니다 — 아래 실행 기록을 보세요)"
RUN_URL = "https://example.test/run/7"
SKIP_LINE = "이미 열린 같은 이슈가 있습니다"

# (KIND, 기대 제목, 기대 대본) — 정확히 leak · 정확히 down · 그 밖(빈 값·모르는 값).
BRANCHES = [
    ("leak", LEAK_TITLE, LEAK_BODY),
    ("down", DOWN_TITLE, DOWN_BODY),
    ("", BROKEN_TITLE, BROKEN_BODY),
    ("xyz", BROKEN_TITLE, BROKEN_BODY),
    # "정확히"를 행동으로 지킨다 — 앞 글자만 보거나(`${KIND:0:4}`) 대소문자를 무시하거나
    # 끝 공백을 떼는 쪽으로 분기가 바뀌면, 스크립트가 낸 적 없는 값이 판정으로 둔갑한다.
    ("leakage", BROKEN_TITLE, BROKEN_BODY),
    ("LEAK", BROKEN_TITLE, BROKEN_BODY),
    ("down\n", BROKEN_TITLE, BROKEN_BODY),
]
BRANCH_IDS = ["leak", "down", "빈값", "모르는값", "leakage", "LEAK", "down+줄바꿈"]

FAKE_GH = """#!/bin/sh
# 가짜 gh. 진짜 gh 처럼 대상 저장소를 알아야 돈다 — 작업 폴더에 .git 이 있거나 GH_REPO 가 있어야 한다.
# issue list 는 열린 제목 파일을, issue create 는 --title 과 --body-file 내용을 기록한다.
if [ ! -d .git ] && [ -z "${GH_REPO:-}" ]; then
  echo "fatal: not a git repository - fake gh has no GH_REPO either" >&2
  exit 1
fi
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
echo "unexpected gh call: $*" >&2
exit 99
"""


def _issue_step():
    import yaml

    workflow = yaml.safe_load(read(WORKFLOW))
    steps = [s for job in workflow["jobs"].values() for s in job["steps"]
             if s.get("name") == ISSUE_STEP_NAME]
    assert len(steps) == 1, "이슈를 여는 단계가 하나가 아닙니다"
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
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
    path.chmod(0o755)


def _first_line(path):
    return read(path).splitlines()[0]


def _run_step(run_text, env_keys, work, kind, reason="", checked_out=True, open_titles=()):
    """단계 글(run_text)을 `work` 폴더에서 돌린다.

    env_keys     워크플로 단계의 env 에 **실제로 적힌** 이름들 — 여기 없는 값은 단계에 안 넘어간다
                 (GH_REPO 줄을 지우면 가짜 gh 가 저장소를 못 찾는다).
    checked_out  True = 받기가 된 날(`.git` + 대본 셋) · False = 받기가 실패한 날(빈 폴더).
    """
    bash = _find_bash()
    if bash is None:
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            pytest.fail("CI 인데 bash 를 못 찾았습니다 — 워크플로 단계 실행 시험을 건너뛸 수 없습니다")
        pytest.skip("bash 가 없습니다(윈도우는 Git Bash 필요)")
    work.mkdir(exist_ok=True)
    if checked_out:
        (work / ".git").mkdir()
        (work / ".github").mkdir()
        for src in (LEAK_BODY, DOWN_BODY, BROKEN_BODY):
            shutil.copyfile(src, str(work / ".github" / os.path.basename(src)))
    (work / "open_titles.txt").write_bytes(("\n".join(open_titles) + "\n").encode("utf-8"))
    bin_dir = work / "fakebin"
    bin_dir.mkdir()
    _write_lf(bin_dir / "gh", FAKE_GH)
    _write_lf(work / "step.sh", run_text)

    values = {"GH_TOKEN": "fake", "GH_REPO": "owner/repo", "RUN_URL": RUN_URL,
              "KIND": kind, "REASON": reason}
    unknown = set(env_keys) - set(values)
    assert not unknown, "단계 env 에 시험이 모르는 이름이 생겼습니다 — 이 표에 더하세요: {}".format(unknown)
    env = dict(os.environ)
    for key in values:  # 내 PC·CI 에 우연히 있던 값이 새어 들어오지 않게.
        env.pop(key, None)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    for key in env_keys:
        env[key] = values[key]
    if os.name == "nt":
        # 윈도우 Git Bash 의 grep 3.0 은 UTF-8 로캘에서 이모지(유출 제목의 빨간 동그라미)가 든 줄을
        # `-Fx` 로 못 맞춘다 — 한글은 맞춘다(2026-10-02 실측: 같은 글이 로캘 C 에서는 맞고,
        # 리눅스 grep 3.12 는 C·C.UTF-8 어느 쪽이든 맞는다). 러너(우분투)에는 없는 윈도우만의
        # 한계라 **윈도우에서만** 로캘을 C 로 둔다. CI 는 러너 로캘 그대로 돈다.
        env["LC_ALL"] = "C"
    return subprocess.run(
        [bash, "-e", "step.sh"],
        cwd=str(work), env=env, capture_output=True, timeout=60,
    )


def _said(res):
    return res.stdout.decode("utf-8", "replace") + res.stderr.decode("utf-8", "replace")


def _check_opens(run_text, env_keys, work, kind, title, first_line, **scenario):
    """단계를 돌려 **이 제목 · 이 첫 줄**로 이슈가 딱 하나 열렸는지 본다. 본문을 돌려준다.

    어긋나면 AssertionError — 양성 대조 시험이 망가뜨린 단계 글을 넣어 이것이 터지는지 본다.
    """
    res = _run_step(run_text, env_keys, work, kind, **scenario)
    said = _said(res)
    assert res.returncode == 0, said
    assert (work / "created.txt").exists(), "이슈를 열지 않았습니다: " + said
    created = (work / "created.txt").read_bytes().decode("utf-8").splitlines()
    assert created == [title], said
    body = (work / "created_body.txt").read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert body.splitlines()[0] == first_line, body[:300]
    return body


def _check_skips(run_text, env_keys, work, kind, title):
    """같은 제목이 열려 있으면 새로 열지 않는지 본다. 어긋나면 AssertionError."""
    res = _run_step(run_text, env_keys, work, kind, open_titles=["다른 이슈 제목", title])
    said = _said(res)
    assert res.returncode == 0, said
    assert not (work / "created.txt").exists(), "열린 같은 이슈가 있으면 새로 열면 안 된다"
    assert SKIP_LINE in said


@pytest.fixture(scope="module")
def step():
    return _issue_step()


class TestTheIssueStepForReal:
    """고치지 않은 워크플로의 단계를 그대로 돌린다."""

    @pytest.mark.parametrize("kind, title, body_path", BRANCHES, ids=BRANCH_IDS)
    def test_each_kind_opens_its_own_title_and_script(self, step, tmp_path, kind, title, body_path):
        """⛔ 빈 값·모르는 값이 '사이트 다운' 대본으로 가면 운영자는 "멀쩡하네" 하고 닫는다."""
        body = _check_opens(step["run"], step["env"], tmp_path / "w", kind, title,
                            _first_line(body_path), reason="bundle 404")
        assert read(body_path).replace("\r\n", "\n") in body
        assert "## 이번에 걸린 것" in body
        assert "bundle 404" in body
        assert "실패한 실행: " + RUN_URL in body

    @pytest.mark.parametrize("kind, title, body_path", BRANCHES, ids=BRANCH_IDS)
    def test_an_empty_reason_says_the_check_never_ran(self, step, tmp_path, kind, title, body_path):
        body = _check_opens(step["run"], step["env"], tmp_path / "w", kind, title,
                            _first_line(body_path))
        assert NO_REASON_LINE in body

    @pytest.mark.parametrize("kind, title, body_path", BRANCHES, ids=BRANCH_IDS)
    def test_the_same_open_title_means_no_new_issue(self, step, tmp_path, kind, title, body_path):
        _check_skips(step["run"], step["env"], tmp_path / "w", kind, title)

    @pytest.mark.parametrize("kind, title, body_path", BRANCHES, ids=BRANCH_IDS)
    def test_the_other_open_titles_do_not_swallow_it(self, step, tmp_path, kind, title, body_path):
        """제목이 갈라진 이유 — 먼저 열린 다른 갈래의 이슈가 이 알림을 삼키면 안 된다."""
        others = [t for t in (LEAK_TITLE, DOWN_TITLE, BROKEN_TITLE) if t != title]
        _check_opens(step["run"], step["env"], tmp_path / "w", kind, title,
                     _first_line(body_path), open_titles=others)

    @pytest.mark.parametrize("kind, title, body_path", BRANCHES, ids=BRANCH_IDS)
    def test_it_still_opens_when_checkout_failed(self, step, tmp_path, kind, title, body_path):
        """받기가 실패한 날은 작업 폴더가 비어 있다 — 대본도 `.git` 도 없다. 그래도 연다."""
        body = _check_opens(step["run"], step["env"], tmp_path / "w", kind, title,
                            NO_BODY_LINE, checked_out=False)
        assert NO_REASON_LINE in body
        assert "실패한 실행: " + RUN_URL in body

    def test_the_step_tells_gh_which_repo(self, step):
        """받기가 실패하면 `.git` 이 없어 gh 가 대상 저장소를 못 찾는다 → GH_REPO 로 알려 준다.

        ⚠️ 글자 단언이다. 진짜 gh 가 `.git` 없이 도는지는 못 잰다(문서 근거 — 이 절 머리말).
        """
        assert step["env"]["GH_REPO"] == "${{ github.repository }}"
        assert step["if"] == "failure()"
        assert step["env"]["KIND"] == "${{ steps.check.outputs.kind }}"
        assert step["env"]["REASON"] == "${{ steps.check.outputs.reason }}"

    def test_the_check_step_is_the_one_the_issue_step_reads_from(self, step):
        """⛔ 확인 단계의 `id` 가 바뀌면 `steps.check.outputs.kind` 가 **늘 빈 값**이 된다 —
        진짜 사이트 다운·유출이 전부 '감시 고장' 대본으로 나간다(에러 없이). 양쪽을 함께 묶는다.
        """
        import yaml

        workflow = yaml.safe_load(read(WORKFLOW))
        checks = [s for job in workflow["jobs"].values() for s in job["steps"]
                  if "python scripts/check_live_health.py" in s.get("run", "")]
        assert len(checks) == 1, "check_live_health.py 를 돌리는 단계가 하나가 아닙니다"
        assert checks[0].get("id") == "check"
        assert step["env"]["KIND"] == "${{ steps.check.outputs.kind }}"
        assert step["env"]["REASON"] == "${{ steps.check.outputs.reason }}"

    def test_the_dedup_looks_at_open_issues_only(self, step):
        """⛔ `--state all`·`closed` 면 사람이 닫은 이슈도 목록에 남아 다음 사고부터 영영 안 열린다."""
        assert "--state open" in step["run"]
        assert step["run"].count("--state") == 1

    def test_the_three_titles_are_each_set_once_and_differ(self, step):
        titles = re.findall(r'^\s*TITLE="([^"]+)"$', step["run"], re.M)
        assert sorted(titles) == sorted([LEAK_TITLE, DOWN_TITLE, BROKEN_TITLE])
        assert len({LEAK_TITLE, DOWN_TITLE, BROKEN_TITLE}) == 3


def _mutate(run_text, old, new):
    assert run_text.count(old) == 1, "망가뜨릴 자리를 못 찾았습니다(단계 글이 바뀌었나): " + old
    return run_text.replace(old, new)


class TestTheChecksAboveActuallyCatchABrokenStep:
    """양성 대조 — 단계 글을 일부러 망가뜨려 **같은 도우미**에 넣으면 터지는가.

    "빈 값이 down 으로 안 간다" 같은 '없음' 단언은, 잡는 힘이 없어도 초록이다. 그래서 망가진
    글에서는 빨강이 되는 것을 여기서 못 박는다(2026-10-02 #186 의 죽은 가드가 계기).
    """

    @pytest.mark.parametrize("kind", ["", "xyz"], ids=["빈값", "모르는값"])
    def test_the_old_rule_everything_but_leak_is_down_is_caught(self, step, tmp_path, kind):
        """옛 규칙(`${KIND:-down}` 꼴 — leak 이 아니면 전부 '사이트 다운')."""
        broken = _mutate(step["run"], 'elif [ "${KIND:-}" = "down" ]; then',
                         'elif [ "${KIND:-down}" != "leak" ]; then')
        with pytest.raises(AssertionError):
            _check_opens(broken, step["env"], tmp_path / "w", kind, BROKEN_TITLE,
                         _first_line(BROKEN_BODY))

    def test_an_empty_kind_defaulting_to_down_is_caught(self, step, tmp_path):
        broken = _mutate(step["run"], 'elif [ "${KIND:-}" = "down" ]; then',
                         'elif [ "${KIND:-down}" = "down" ]; then')
        with pytest.raises(AssertionError):
            _check_opens(broken, step["env"], tmp_path / "w", "", BROKEN_TITLE,
                         _first_line(BROKEN_BODY))

    def test_a_broken_title_borrowing_the_down_script_is_caught(self, step, tmp_path):
        """제목만 새것이고 대본이 '사이트 다운'이면 첫 줄 대조가 잡는다."""
        broken = _mutate(step["run"], 'BODY_FILE=".github/live-health-broken-issue.md"',
                         'BODY_FILE=".github/live-health-failure-issue.md"')
        with pytest.raises(AssertionError):
            _check_opens(broken, step["env"], tmp_path / "w", "", BROKEN_TITLE,
                         _first_line(BROKEN_BODY))

    def test_a_missing_script_file_killing_the_step_is_caught(self, step, tmp_path):
        """대본 파일 확인을 빼면 `cat` 이 죽어 이슈가 안 열린다(옛 동작)."""
        broken = _mutate(step["run"], 'if [ -f "$BODY_FILE" ]; then', "if true; then")
        with pytest.raises(AssertionError):
            _check_opens(broken, step["env"], tmp_path / "w", "", BROKEN_TITLE,
                         NO_BODY_LINE, checked_out=False)

    def test_a_missing_gh_repo_is_caught(self, step, tmp_path):
        """env 에서 GH_REPO 줄이 빠지면 받기 실패한 날 (가짜) gh 가 저장소를 못 찾는다."""
        env_keys = [k for k in step["env"] if k != "GH_REPO"]
        assert len(env_keys) == len(step["env"]) - 1
        with pytest.raises(AssertionError):
            _check_opens(step["run"], env_keys, tmp_path / "w", "", BROKEN_TITLE,
                         NO_BODY_LINE, checked_out=False)

    def test_a_dedup_that_never_matches_is_caught(self, step, tmp_path):
        broken = _mutate(step["run"], 'grep -Fxq "$TITLE"', 'grep -Fxq "no-such-title"')
        with pytest.raises(AssertionError):
            _check_skips(broken, step["env"], tmp_path / "w", "", BROKEN_TITLE)


class TestNoBashIsNotASilentSkipOnCI:
    """bash 가 없을 때 — CI 에서는 실패, 내 PC 에서만 건너뛴다."""

    def test_it_fails_on_ci(self, monkeypatch, tmp_path):
        monkeypatch.setitem(globals(), "_find_bash", lambda: None)
        monkeypatch.setenv("CI", "1")
        # BaseException 으로 받는다 — 건너뜀(Skipped)이 새어 나가면 시험이 빨강이 아니라 '건너뜀'이 된다.
        with pytest.raises(BaseException) as caught:
            _run_step("true", [], tmp_path / "w", "")
        assert caught.type is pytest.fail.Exception, caught.type

    def test_it_fails_on_github_actions(self, monkeypatch, tmp_path):
        monkeypatch.setitem(globals(), "_find_bash", lambda: None)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        with pytest.raises(BaseException) as caught:
            _run_step("true", [], tmp_path / "w", "")
        assert caught.type is pytest.fail.Exception, caught.type

    def test_it_skips_on_my_pc(self, monkeypatch, tmp_path):
        monkeypatch.setitem(globals(), "_find_bash", lambda: None)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        with pytest.raises(BaseException) as caught:
            _run_step("true", [], tmp_path / "w", "")
        assert caught.type is pytest.skip.Exception, caught.type
