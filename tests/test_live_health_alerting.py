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

⚠️ 워크플로 YAML 을 실제로 실행하지는 않는다(러너가 없다) — 글자를 읽어 배선을 확인한다.
   그래서 "이 파일이 초록 = 알림이 진짜 잘 나간다"는 아니다. 다만 위 두 실패 모드는
   전부 **글자로 드러나는 종류**라, 글자 검사만으로 되살아남을 막을 수 있다.
"""

import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "check_live_health.py")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "live-health-watch.yml")
DOWN_BODY = os.path.join(ROOT, ".github", "live-health-failure-issue.md")
LEAK_BODY = os.path.join(ROOT, ".github", "live-health-leak-issue.md")


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

    def test_an_unknown_kind_falls_back_to_down(self, wf):
        """확인 단계가 아예 못 돌면 kind 가 비어 온다 — 그때 조용히 죽지 않아야 한다."""
        assert "KIND:-down" in wf


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
