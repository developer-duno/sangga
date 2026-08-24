# -*- coding: utf-8 -*-
"""
scripts/check_live_health.py 1:1 단위 테스트.

네트워크는 전부 monkeypatch 로 막는다(실제 사이트에 접속하지 않음).
공용 설정 파일(conftest.py 등) 없이 이 파일 안에서 import 경로를 직접 해결한다.

여기서 특히 지키는 것
---------------------
이 감시가 존재하는 **유일한 이유**는 "첫 화면은 200 인데 알맹이가 없는" 반쪽 배포를
잡는 것이다. 그러니 이 테스트도 그 한 가지를 가장 집요하게 본다 — 첫 화면만 보고
"정상"이라 말하기 시작하면 감시가 있으나 마나 해진다.
"""

import os
import sys
import urllib.error

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import check_live_health as chk  # noqa: E402

SITE = "https://example.test"

GOOD_HTML = (
    '<!doctype html><html lang="ko"><head><title>상가 층별 스택뷰</title></head>'
    '<body><div id="root"></div>'
    '<script type="module" src="/assets/index-ABC123.js"></script></body></html>'
)
GOOD_BUNDLE = b"x" * 5000
GOOD_GEOJSON = b'{"type":"FeatureCollection","features":[]}'


def install_fake_fetch(monkeypatch, routes):
    """{경로: (상태, 바이트)} 로 응답을 흉내 낸다. 없는 경로는 404."""
    calls = []

    def fake_fetch(url):
        calls.append(url)
        path = url[len(SITE) :] if url.startswith(SITE) else url
        if path not in routes:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return routes[path]

    monkeypatch.setattr(chk, "fetch", fake_fetch)
    # 다시 시도 사이의 기다림은 없지만, 실패 경로에서 3회를 도는 것을 그대로 두면
    # 테스트가 느려지지 않으면서도 재시도 자체는 그대로 검증된다.
    return calls


def all_good():
    return {
        "/": (200, GOOD_HTML.encode("utf-8")),
        "/assets/index-ABC123.js": (200, GOOD_BUNDLE),
        "/districts.geojson": (200, GOOD_GEOJSON),
    }


# ── 정상 ─────────────────────────────────────────────────────────────────────


def test_all_green_returns_three_lines(monkeypatch):
    install_fake_fetch(monkeypatch, all_good())
    passed = chk.check(SITE)
    assert len(passed) == 3


def test_bundle_path_is_read_from_html_not_hardcoded(monkeypatch):
    """Vite 는 해시가 붙은 이름을 쓴다 — 경로를 박아 두면 배포마다 깨진다."""
    routes = {
        "/": (
            200,
            GOOD_HTML.replace("index-ABC123.js", "index-ZZZ999.js").encode("utf-8"),
        ),
        "/assets/index-ZZZ999.js": (200, GOOD_BUNDLE),
        "/districts.geojson": (200, GOOD_GEOJSON),
    }
    calls = install_fake_fetch(monkeypatch, routes)
    chk.check(SITE)
    assert any("index-ZZZ999.js" in c for c in calls)


# ── 반쪽 배포 — 이 감시의 존재 이유 ──────────────────────────────────────────


def test_bundle_404_is_caught_even_though_home_is_200(monkeypatch):
    """⛔ 첫 화면 200 + 묶음 404 = 사용자에게는 하얀 화면. 이걸 놓치면 감시가 무의미하다."""
    routes = all_good()
    del routes["/assets/index-ABC123.js"]
    install_fake_fetch(monkeypatch, routes)

    with pytest.raises(chk.CheckFailed) as ex:
        chk.check(SITE)
    assert "자바스크립트 묶음" in str(ex.value)


def test_tiny_bundle_is_treated_as_failure(monkeypatch):
    """오류 페이지가 200 으로 오는 호스팅이 있다 — 크기로 한 번 더 거른다."""
    routes = all_good()
    routes["/assets/index-ABC123.js"] = (200, b"not found")
    install_fake_fetch(monkeypatch, routes)

    with pytest.raises(chk.CheckFailed) as ex:
        chk.check(SITE)
    assert "너무 작습니다" in str(ex.value)


# ── 첫 화면 ──────────────────────────────────────────────────────────────────


def test_home_200_but_not_our_page_is_failure(monkeypatch):
    """호스팅 기본 페이지·엉뚱한 배포도 200 을 준다. 우리 표식이 있어야 우리 화면이다."""
    routes = all_good()
    routes["/"] = (200, b"<html><body>Welcome to nginx</body></html>")
    install_fake_fetch(monkeypatch, routes)

    with pytest.raises(chk.CheckFailed) as ex:
        chk.check(SITE)
    assert "우리 화면이 아닙니다" in str(ex.value)


def test_home_down_is_failure(monkeypatch):
    install_fake_fetch(monkeypatch, {})
    with pytest.raises(chk.CheckFailed) as ex:
        chk.check(SITE)
    assert "첫 화면" in str(ex.value)


def test_missing_bundle_tag_is_failure(monkeypatch):
    """빌드 결과 모양이 바뀌면 정규식도 함께 고쳐야 한다 — 조용히 통과시키지 않는다."""
    routes = all_good()
    routes["/"] = (200, b'<html><body><div id="root"></div></body></html>')
    install_fake_fetch(monkeypatch, routes)

    with pytest.raises(chk.CheckFailed) as ex:
        chk.check(SITE)
    assert "묶음 경로를 못 찾았습니다" in str(ex.value)


# ── 지도 파일 ────────────────────────────────────────────────────────────────


def test_geojson_missing_is_failure(monkeypatch):
    routes = all_good()
    del routes["/districts.geojson"]
    install_fake_fetch(monkeypatch, routes)

    with pytest.raises(chk.CheckFailed) as ex:
        chk.check(SITE)
    assert "상권 지도 파일" in str(ex.value)


def test_geojson_html_error_page_is_failure(monkeypatch):
    """JSON 자리에 HTML 이 200 으로 오는 경우."""
    routes = all_good()
    routes["/districts.geojson"] = (200, b"<html>404</html>")
    install_fake_fetch(monkeypatch, routes)

    with pytest.raises(chk.CheckFailed) as ex:
        chk.check(SITE)
    assert "JSON 이 아닙니다" in str(ex.value)


# ── 재시도 ───────────────────────────────────────────────────────────────────


def test_transient_failure_is_retried(monkeypatch):
    """한 번 끊겼다고 죽었다 알리면, 그 이슈를 닫는 손이 들고 결국 알림이 무시된다."""
    attempts = {"n": 0}

    def flaky_fetch(url):
        if url.endswith("/") and attempts["n"] < 2:
            attempts["n"] += 1
            raise urllib.error.URLError("일시 장애")
        path = url[len(SITE) :]
        return all_good()[path]

    monkeypatch.setattr(chk, "fetch", flaky_fetch)
    passed = chk.check(SITE)
    assert len(passed) == 3
    assert attempts["n"] == 2


def test_gives_up_after_retries(monkeypatch):
    def always_down(_url):
        raise urllib.error.URLError("계속 장애")

    monkeypatch.setattr(chk, "fetch", always_down)
    with pytest.raises(chk.CheckFailed):
        chk.check(SITE)


def test_non_200_status_is_failure(monkeypatch):
    """예외가 아니라 상태코드로 오는 경우도 있다(리다이렉트 처리 등)."""
    routes = all_good()
    routes["/"] = (503, b"maintenance")
    install_fake_fetch(monkeypatch, routes)

    with pytest.raises(chk.CheckFailed) as ex:
        chk.check(SITE)
    assert "503" in str(ex.value)


# ── Actions 로 값 넘기기 ─────────────────────────────────────────────────────


def test_emit_output_uses_multiline_delimiter(monkeypatch, tmp_path):
    """실패 사유는 여러 줄일 수 있다 — 한 줄 형식(key=value)은 줄바꿈에서 깨진다."""
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    chk._emit_output("reason", "첫 줄\n둘째 줄")

    text = out.read_text(encoding="utf-8")
    assert text.startswith("reason<<SANGGA_EOF_")
    assert "첫 줄\n둘째 줄" in text
    # 여는 구분자와 닫는 구분자가 같아야 GitHub 이 값을 제대로 끊어 읽는다.
    delim = text.split("<<", 1)[1].split("\n", 1)[0]
    assert text.rstrip("\n").endswith(delim)


def test_emit_output_delimiter_differs_every_run(monkeypatch, tmp_path):
    """⛔ 고정 구분자면 값 안에 같은 줄이 들어오는 순간 거기서 값이 끊긴다.

    그 뒤는 **새 key=value 로 읽힌다**(2026-08-24 적대적 보안 검토 지적).
    """
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    chk._emit_output("reason", "가")
    chk._emit_output("reason", "나")

    delims = [
        line.split("<<", 1)[1]
        for line in out.read_text(encoding="utf-8").splitlines()
        if line.startswith("reason<<")
    ]
    assert len(delims) == 2
    assert delims[0] != delims[1]


def test_emit_output_is_noop_outside_actions(monkeypatch):
    """로컬에서 돌려도 터지지 않는다."""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    chk._emit_output("reason", "아무거나")  # 예외가 안 나면 통과


def test_main_returns_1_on_failure(monkeypatch, capsys):
    install_fake_fetch(monkeypatch, {})
    monkeypatch.setattr(sys, "argv", ["check_live_health.py", "--site", SITE])
    assert chk.main() == 1
    assert "정상이 아닙니다" in capsys.readouterr().out


def test_main_returns_0_on_success(monkeypatch, capsys):
    install_fake_fetch(monkeypatch, all_good())
    monkeypatch.setattr(sys, "argv", ["check_live_health.py", "--site", SITE])
    assert chk.main() == 0
    assert "라이브 정상입니다" in capsys.readouterr().out


def test_trailing_slash_in_site_is_normalized(monkeypatch):
    """--site 를 슬래시로 끝내도 '//' 로 두드리지 않는다."""
    calls = install_fake_fetch(monkeypatch, all_good())
    monkeypatch.setattr(sys, "argv", ["check_live_health.py", "--site", SITE + "/"])
    assert chk.main() == 0
    assert all("//" not in c[len("https://") :] for c in calls)
