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
import re
import sys
import urllib.error

import pytest
import yaml

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import check_live_health as chk  # noqa: E402

# ⛔ **가짜 키를 소스에 통짜로 적지 말 것** — GitHub 의 비밀 검사(push protection)가 진짜
#    Supabase 관리자 키로 오인해 **푸시를 막는다**(2026-09-01 실제로 막혔다). 그때 "허용
#    처리"로 뚫으면 앞으로 진짜 유출도 함께 통과시키는 방향이 된다. 나눠 조립한다.
FAKE_SECRET = b"sb_secret_" + b"x" * 25


def fake_jwt(role):
    """옛 형식 키가 **번들에 실제로 실리는 모양**(base64url 인코딩)으로 만든다.

    ⛔ 이게 핵심이다 — 2026-09-01 2차 검증 전까지 이 시험은 **디코딩된 글자**
       (`{"role":"service_role"}`)를 그대로 번들에 넣어 검사했다. 그러면 시험은 초록인데
       **실제 번들에는 그 글자가 없어서** 가드가 한 번도 발동할 수 없었다.
       죽은 가드는 없는 가드보다 나쁘다 — "막고 있다"는 거짓 안심을 주기 때문이다.
    """
    import base64
    import json

    def seg(obj):
        return base64.urlsafe_b64encode(
            json.dumps(obj, separators=(",", ":")).encode()).rstrip(b"=")

    return (seg({"alg": "HS256", "typ": "JWT"}) + b"."
            + seg({"iss": "supabase", "role": role, "iat": 1, "exp": 2}) + b"."
            + b"c2lnbmF0dXJlLXBsYWNlaG9sZGVy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "live-health-watch.yml")

SITE = "https://example.test"

NO_SLEEP = lambda _s: None  # noqa: E731

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
    # sleep=NO_SLEEP — 실제로 두 번(5초·10초)을 기다리지 않고도 재시도 자체는
    # 그대로 검증된다(gives_up 류 시험과 같은 이유).
    passed = chk.check(SITE, sleep=NO_SLEEP)
    assert len(passed) == 3
    assert attempts["n"] == 2


def test_gives_up_after_retries(monkeypatch):
    def always_down(_url):
        raise urllib.error.URLError("계속 장애")

    monkeypatch.setattr(chk, "fetch", always_down)
    with pytest.raises(chk.CheckFailed):
        chk.check(SITE, sleep=NO_SLEEP)


def test_non_200_status_is_failure(monkeypatch):
    """예외가 아니라 상태코드로 오는 경우도 있다(리다이렉트 처리 등)."""
    routes = all_good()
    routes["/"] = (503, b"maintenance")
    install_fake_fetch(monkeypatch, routes)

    with pytest.raises(chk.CheckFailed) as ex:
        chk.check(SITE, sleep=NO_SLEEP)
    assert "503" in str(ex.value)


# ── 재시도 표준(collect_lh_notices.get_json_with_retry 와 같은 규칙) ───────────


class TestRetryStandard:
    """2026-08-31 PR #109 가 collect_lh_notices.py 에 세운 표준을 여기도 따른다 —
    예전엔 RETRIES=3 이면서 재시도 사이 대기가 0초였다(주석은 '조급하게 판정 안 한다'
    고 적혀 있었는데 실제로는 그렇지 않았다)."""

    def test_matches_the_collector_standard(self):
        """⛔ 두 벌로 두면 언젠가 한쪽만 고쳐진다 — 값이 갈리면 이 시험이 잡는다."""
        import collect_lh_notices as lh

        assert chk.RETRY_COUNT == lh.RETRY_COUNT
        assert chk.RETRY_BACKOFF_SEC == lh.RETRY_BACKOFF_SEC
        assert chk.NO_RETRY_HTTP_CODES == lh.NO_RETRY_HTTP_CODES

    def test_waits_longer_between_each_knock(self, monkeypatch):
        """쉬지 않고 연달아 두드리면 배포 확인이 무의미해진다."""

        def always_down(_url):
            raise urllib.error.URLError("계속 장애")

        monkeypatch.setattr(chk, "fetch", always_down)
        waits = []
        with pytest.raises(chk.CheckFailed):
            chk.fetch_with_retry(SITE + "/", "첫 화면", sleep=waits.append)
        assert waits == [chk.RETRY_BACKOFF_SEC * (2**i) for i in range(chk.RETRY_COUNT - 1)]

    @pytest.mark.parametrize("code", sorted(chk.NO_RETRY_HTTP_CODES))
    def test_does_not_retry_what_will_not_change(self, monkeypatch, code):
        """401·403·404 는 사람이 고쳐야 하는 것 — 참을성을 늘려도 여기는 한 번뿐이다."""
        calls = []

        def refused(url):
            calls.append(url)
            raise urllib.error.HTTPError(url, code, "refused", None, None)

        monkeypatch.setattr(chk, "fetch", refused)
        with pytest.raises(chk.CheckFailed):
            chk.fetch_with_retry(SITE + "/", "첫 화면", sleep=NO_SLEEP)
        assert calls == [SITE + "/"], "다시 물어도 답이 같은 실패인데 재시도했습니다"

    def test_does_not_retry_a_non_exception_no_retry_status(self, monkeypatch):
        """예외로 안 오고 상태코드로만 오는 404/403/401 도 마찬가지로 한 번뿐이어야 한다."""
        routes = all_good()
        routes["/"] = (404, b"not found")
        calls = install_fake_fetch(monkeypatch, routes)
        with pytest.raises(chk.CheckFailed):
            chk.fetch_with_retry(SITE + "/", "첫 화면", sleep=NO_SLEEP)
        assert calls == [SITE + "/"]

    def test_retries_a_gateway_timeout_like_error(self, monkeypatch):
        """502·503 처럼 다시 물으면 답이 달라질 수 있는 상태코드는 재시도한다."""
        calls = []

        def flaky(url):
            calls.append(url)
            if len(calls) == 1:
                return (503, b"maintenance")
            return all_good()["/"]

        monkeypatch.setattr(chk, "fetch", flaky)
        body = chk.fetch_with_retry(SITE + "/", "첫 화면", sleep=NO_SLEEP)
        assert body == GOOD_HTML.encode("utf-8")
        assert len(calls) == 2


# ── 워크플로 배선 ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def workflow():
    with open(WORKFLOW, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestWorkflowTimeout:
    # GitHub 공식 문서: timeout-minutes 를 안 정하면 job 기본값은 360분(6시간)이다.
    DEFAULT_GH_JOB_TIMEOUT_MIN = 360

    def test_live_health_watch_has_no_explicit_timeout(self, workflow):
        """⛔ 지금은 명시값이 없다 — 없으면 위 기본 360분이 적용된다는 전제로
        아래 여유 계산을 한다. 누군가 나중에 timeout-minutes 를 짧게 박으면 이
        시험이 그 값을 읽어 여유를 다시 따지게 고쳐야 한다."""
        job = workflow["jobs"]["health"]
        assert "timeout-minutes" not in job

    def test_worst_case_wait_fits_the_job_timeout(self, workflow):
        """⛔ 최악은 **URL 수만큼**이다 (2026-09-01 적대검증에서 정정).

        처음엔 "check() 가 첫 실패에서 곧장 예외를 던지니 뒤의 URL 은 안 두드린다 ⇒ 1배"
        라고 적었는데 **틀렸다**: 앞 URL 이 **마지막 시도에서 성공**하면 예외가 안 나므로
        그대로 다음 URL 로 넘어간다. 조기 종료는 실패했을 때만 일어나므로, 가장 비싼
        경로는 "셋이 각각 끝까지 버티다 겨우 성공"이다.

        ⛔ 틀린 공식을 그대로 두면 이 가드가 3배 헐거워진다 — 누가 `timeout-minutes` 를
           짧게 박거나 RETRY_COUNT 를 크게 올리는 날 **시험은 초록인데 job 만 잘린다.**
        """
        job = workflow["jobs"]["health"]
        timeout_min = job.get("timeout-minutes", self.DEFAULT_GH_JOB_TIMEOUT_MIN)
        waits = sum(chk.RETRY_BACKOFF_SEC * (2**i) for i in range(chk.RETRY_COUNT - 1))
        per_url = chk.TIMEOUT_S * chk.RETRY_COUNT + waits
        worst_case_sec = per_url * chk.CHECKED_URLS
        assert worst_case_sec < timeout_min * 60, (
            "재시도 표준을 올리며 총 대기가 워크플로 제한 시간을 넘길 수 있습니다 "
            "(최악 {}초 = URL {}개 × {}초)".format(worst_case_sec, chk.CHECKED_URLS, per_url)
        )

    def test_checked_urls_matches_what_check_actually_fetches(self):
        """⛔ `CHECKED_URLS` 가 실제 호출 수와 어긋나면 위 계산이 **조용히** 낙관적이 된다.

        상수와 코드가 갈리는 순간 위 가드는 "지킨다고 주장하는 것"을 안 지킨다 —
        이 레포가 여러 번 데인 가짜 초록의 전형이다. 그래서 기계로 세어 대조한다.

        ⚠️ **이 시험 자체의 한계 — 정직히 적어 둔다(2026-09-01 감사에서 발견).**
        `fetch_with_retry(` 글자 수를 세는 방식이라 양쪽으로 틀릴 수 있다:
          · **과다 계수** — 이 이름이 `check()` 안 주석(`#` 로 시작하는 줄)이나 함수
            자신의 독스트링에 설명 삼아 등장하면 실제 호출이 아닌데도 세어진다. 그래서
            아래는 **독스트링과 `#` 주석을 걷어낸 뒤** 센다(이 파일의 `#` 주석은 전부
            한 줄 전체라 트레일링 주석까지는 안 다룬다 — 지금 이 코드베이스 관례로는
            충분하다).
          · **과소 계수** — 언젠가 `check()` 가 URL 하나를 헬퍼 함수로 빼내 그 헬퍼가
            `fetch_with_retry` 를 부르면, 이 문자열 세기는 `check()` 함수 **본문**만
            보므로 그 호출을 못 센다(호출 자체는 여전히 일어나는데 카운트만 준다).
            이건 문자열 세기로는 원리적으로 못 잡는 한계라, 함수 추출 리팩터를 할 때는
            이 시험이 통과하더라도 `CHECKED_URLS` 를 손으로 다시 확인해야 한다.
        """
        with open(chk.__file__, encoding="utf-8") as f:
            src = f.read()
        body = src[src.index("def check("):]
        body = body[:body.index("\ndef ", 1)] if "\ndef " in body[1:] else body
        # 독스트링(설명문 안에 이름이 등장할 수 있다)과 `#` 주석 줄을 걷어낸 뒤 센다 —
        # 안 걷으면 위 한계에서 말한 과다 계수가 실제로 일어난다.
        body_no_docstring = re.sub(r'"""[\s\S]*?"""', "", body, count=1)
        code_only = "\n".join(
            ln for ln in body_no_docstring.splitlines() if not ln.lstrip().startswith("#")
        )
        calls = code_only.count("fetch_with_retry(")
        assert calls == chk.CHECKED_URLS, (
            "check() 가 부르는 fetch_with_retry 는 {}번인데 CHECKED_URLS 는 {}입니다 — "
            "검사를 더했으면 상수도 함께 올리세요.".format(calls, chk.CHECKED_URLS)
        )


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


# ── 관리자 키가 배포된 묶음에 실렸나 (2026-09-01 적대검증에서 신설) ────────────
#
# 왜 여기인가: `scripts/make_env_local.py` 의 값 검사는 **로컬 번들**만 덮는다. 라이브
# 번들은 `.env.local` 이 아니라 **Vercel 대시보드의 env** 로 빌드되므로, 콘솔 칸에 관리자
# 키를 붙여넣는 경로는 그 검사를 통째로 지나간다. 그 문은 밖에서 묶음을 열어 보는 이
# 감시만 지킬 수 있다 — 두 검사는 서로 다른 문이라 하나로 합칠 수 없다.


class TestAdminKeyNeverShipsInTheBundle:
    # ⛔ **가짜 키를 소스에 통짜로 적지 말 것** — GitHub 의 비밀 검사(push protection)가
    #    진짜 Supabase 관리자 키로 오인해 **푸시를 막는다**(2026-09-01 실제로 막혔다).
    #    그때 "허용 처리"로 뚫으면 안 된다 — 그건 앞으로 진짜 유출도 함께 통과시키는
    #    방향이다. 대신 **접두사와 뒷부분을 나눠 조립**한다: 소스에는 온전한 모양이
    #    한 번도 나타나지 않지만, 검사 대상 문자열은 똑같이 만들어진다.
    #    (뒤 25자는 우리 정규식이 요구하는 "재료 20자 이상"을 넘기려는 것.)
    _FAKE_SECRET = FAKE_SECRET

    @pytest.mark.parametrize("mark", [
        FAKE_SECRET,                                     # 새 형식(이 프로젝트가 쓰는 것)
        fake_jwt("service_role"),                        # 옛 형식 — **인코딩된 실제 모양**
    ])
    def test_admin_key_in_bundle_is_a_loud_failure(self, monkeypatch, mark):
        """⛔ 걸리면 **즉시 시끄럽게** 실패한다 — '사이트가 죽었다'보다 급한 사고다."""
        routes = all_good()
        routes["/assets/index-ABC123.js"] = (200, GOOD_BUNDLE + b"\n" + mark + b"\n")
        install_fake_fetch(monkeypatch, routes)

        with pytest.raises(chk.CheckFailed) as ex:
            chk.check(SITE)
        said = str(ex.value)
        assert "관리자" in said, "무엇이 문제인지 사람 말로 알려야 한다"
        assert "회전" in said, "이미 배포된 값은 회수 불가 — 재발급을 안내해야 한다"
        # ⛔ 값 자체는 절대 메시지에 담지 않는다(로그·이슈에 남으면 더 퍼진다).
        assert mark.decode("utf-8") not in said

    def test_a_normal_bundle_passes(self, monkeypatch):
        """⛔ 오탐이 나면 이 감시가 매번 울어 곧 무시된다 — 정상 묶음은 조용히 통과."""
        install_fake_fetch(monkeypatch, all_good())
        passed = chk.check(SITE)
        assert any("관리자 키 흔적 없음" in p for p in passed)

    def test_publishable_key_is_not_mistaken_for_a_secret(self, monkeypatch):
        """공개키(`sb_publishable_…`)는 원래 묶음에 실려 나간다 — 이걸 막으면 앱이 못 돈다."""
        routes = all_good()
        routes["/assets/index-ABC123.js"] = (
            200, GOOD_BUNDLE + b'\nconst k="sb_publishable_aaaaaaaaaaaaaaaaaaaa";\n')
        install_fake_fetch(monkeypatch, routes)
        chk.check(SITE)      # 예외가 안 나야 정상

    def test_an_anon_jwt_is_not_mistaken_for_an_admin_key(self, monkeypatch):
        """⛔ 옛 형식 **공개키**(role=anon)는 원래 번들에 실려 나간다 — 막으면 앱이 못 돈다.

        payload 를 풀어 역할을 보므로 anon 과 service_role 이 정확히 갈린다.
        (접두사·글자 찾기로는 이 둘을 못 가른다.)
        """
        routes = all_good()
        routes["/assets/index-ABC123.js"] = (
            200, GOOD_BUNDLE + b'\nconst k="' + fake_jwt("anon") + b'";\n')
        install_fake_fetch(monkeypatch, routes)
        chk.check(SITE)      # 예외가 안 나야 정상

    def test_a_jwt_shaped_but_undecodable_string_does_not_crash(self, monkeypatch):
        """⛔ JWT 를 닮았을 뿐인 글자에 감시가 죽으면 **진짜 사고까지 못 알린다.**

        ⚠️ **픽스처가 실제로 그 코드에 닿는지 먼저 못 박는다** (2026-09-01 독립 검토 지적).
           예전 픽스처(`eyJnot-real.eyJalso-not-real.zzz…`)는 payload 조각이 13자라
           `JWT_RE` 의 `{16,}` 에 **아예 안 걸렸다** — 지키겠다던 try/except 에 한 번도
           들어가지 않은 채 초록이었다. 그런 시험은 있으나 마나가 아니라, 있는 줄 알고
           **안 지켜지는 것**이라 더 나쁘다.

        여기 쓰는 글자는 payload 길이가 4로 나눈 나머지 1이라 base64 디코딩이 **실제로
        예외를 던진다**(`binascii.Error: … cannot be 1 more than a multiple of 4`).
        가드가 없으면 그 예외는 `CheckFailed` 가 아니라서 `main()` 이 못 잡고, 스텝이
        traceback 으로 죽어 `kind` 가 빈 값으로 나가고, 워크플로가 `down` 으로 폴백해
        **"사이트가 죽었다" 대본**을 연다 — 이 브랜치가 없애려던 바로 그 실패 모드다.
        """
        probe = b"eyJabcdefgh." + b"eyJ" + b"a" * 18 + b".zzzzzzzz"
        assert chk.JWT_RE.search(probe), (
            "픽스처가 JWT_RE 에 안 걸립니다 — 지키려는 코드에 닿지도 못하는 시험입니다.")
        routes = all_good()
        routes["/assets/index-ABC123.js"] = (200, GOOD_BUNDLE + b"\n" + probe + b"\n")
        install_fake_fetch(monkeypatch, routes)
        chk.check(SITE)      # 조용히 건너뛰어야 정상

    def test_the_library_own_prefix_check_is_not_a_false_alarm(self, monkeypatch):
        """⛔ **이 시험이 이 가드의 존재 이유만큼 중요하다** (2026-09-01 라이브에서 실제로 터짐).

        `@supabase/supabase-js` 는 키 형식을 판별하는 함수를 들고 있어서, 배포된 묶음에
        접두사가 **맨몸으로** 등장한다(실측):

            Va=e=>e.startsWith(`sb_publishable_`)||e.startsWith(`sb_secret_`)

        접두사만 찾는 가드를 그대로 뒀다면 6시간마다 "🔴 관리자 키 유출" 이슈가 영원히
        열렸을 것이다 — **오탐을 내는 감시는 곧 무시되고, 그러면 진짜 사고도 함께 묻힌다.**
        되돌리면(뒤에 붙은 키 재료 요구를 빼면) 이 시험이 빨간불이 된다.
        """
        routes = all_good()
        routes["/assets/index-ABC123.js"] = (
            200,
            GOOD_BUNDLE
            + b"\nVa=e=>e.startsWith(`sb_publishable_`)||e.startsWith(`sb_secret_`)\n",
        )
        install_fake_fetch(monkeypatch, routes)
        chk.check(SITE)      # 예외가 안 나야 정상
