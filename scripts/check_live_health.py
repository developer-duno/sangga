# -*- coding: utf-8 -*-
"""라이브 사이트가 아직 제대로 서 있나 — 밖에서 두드려 본다.

왜 이 스크립트가 있나
---------------------
2026-08-24 첫 배포로 이 서비스는 남이 볼 수 있는 곳이 됐는데, **죽어도 우리가 알 방법이
0** 이었다. 이 앱에는 서버가 없어서(순수 화면 + Supabase 직결) 어디에도 로그가 안 남고,
main 에 push 하면 그대로 배포되므로 잘못 나간 것을 막아 줄 것도 없다.

무엇을 보나 (셋 다 "밖에서 본 모습"이다 — 안을 들여다보지 않는다)
  ① 첫 화면이 200 으로 오고, 그 안에 리액트가 붙을 자리(`<div id="root">`)가 있나
  ② 그 화면이 부르는 **자바스크립트 묶음**이 실제로 받아지나
     ⛔ 이게 핵심이다. 배포가 반쪽만 나가면 첫 화면은 200 인데 묶음이 404 라
        **화면이 하얗게 뜬다** — ①만 봐서는 절대 못 잡는 종류다.
  ③ 지도가 쓰는 상권 파일이 받아지나

무엇을 못 보나 (있다고 안심하면 안 되는 자리)
  · **창고(Supabase)가 살아 있는지는 안 본다.** 그러려면 공개키를 GitHub 에 올려야 하는데,
    지금은 비밀값을 하나도 안 쓰는 쪽을 골랐다(형제 감시들과 같은 철학). 창고가 죽으면
    화면은 뜨고 검색만 안 된다.
  · 화면이 **보기에** 멀쩡한지는 안 본다. 글자가 깨지거나 값이 틀린 것은 E2E 몫이다.
  · 이 예약 자체가 안 도는 경우는 스스로 못 알린다(GitHub 은 60일 무활동 시 예약을 멈춘다).

⚠️ 표준 라이브러리만 쓴다 — 워크플로에 설치 단계가 없다.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request

DEFAULT_SITE = "https://sangga-one.vercel.app"

# 배포가 느릴 때 조급하게 실패로 판정하지 않는다 — 그런데 예전 RETRIES=3 은 재시도
# 사이 대기가 **0초**였다(코드에 적힌 "조급하게 판정 안 한다"는 말과 실제 동작이
# 어긋나 있었다). 대기가 없으면 세 번이 밀리초 안에 끝나 사실상 한 번만 두드리는
# 것과 같다.
#
# ⚠️ 재시도 표준은 collect_lh_notices.py 의 get_json_with_retry(PR #109)를 따른다 —
#    5번 · 5초부터 지수 백오프(5·10·20·40초) · 401/403/404 는 다시 물어도 답이 같아
#    한 번만 두드리고 포기한다.
#
# ⚠️ TIMEOUT_S 는 형제(LH, 60초)와 **의도적으로 다르다**(30초로 유지) — 다음 사람이
#    "형제와 값이 다르네"하며 무심코 맞추지 말 것. LH 는 해외 러너→한국 포털이 대상이라
#    긴 지연 구간을 겪었지만, 이 감시는 우리 배포(Vercel, 보통 응답이 훨씬 빠름)를
#    보는 것이라 요청당 타임아웃은 그대로 두고 **횟수·백오프만** 표준에 맞췄다.
#
# ⚠️ 이 워크플로(live-health-watch.yml)에는 timeout-minutes 가 없어 GitHub 기본값
#    360분(6시간)이 적용된다(공식 문서 확인, docs.github.com — "The default is 360
#    minutes").
#
#    ⛔ **최악은 1배가 아니라 URL 수만큼이다** (2026-09-01 적대검증에서 정정).
#       처음에 "check() 가 첫 실패에서 곧장 예외를 던지니 뒤의 URL 은 안 두드린다 ⇒ 1배"
#       라고 적었는데 **틀렸다**: 앞 URL 이 **마지막 시도에서 성공**하면 예외가 안 나므로
#       그대로 다음 URL 로 넘어간다. 즉 "세 URL 이 각각 끝까지 버티다 겨우 성공"이 가장
#       비싼 경로다. 조기 종료는 **실패했을 때만** 일어난다.
#         URL 하나 몫 = TIMEOUT_S(30) × RETRY_COUNT(5) + 백오프합(5+10+20+40=75) = 225초
#         최악 = 225 × CHECKED_URLS(3) = **675초(11.25분)**
#       → 360분 기본 한도 안에는 여전히 넉넉하다. 다만 **틀린 공식을 시험에 박아 두면**
#         누가 `timeout-minutes` 를 짧게 박는 날 시험은 초록인데 job 만 잘린다(이 레포가
#         가장 두려워하는 조용한 실패). 그래서 TestWorkflowTimeout 이 URL 수까지 곱한다.
RETRY_COUNT = 5
RETRY_BACKOFF_SEC = 5

# check() 가 두드리는 URL 개수 — 첫 화면 · 자바스크립트 묶음 · 상권 지도 파일.
# ⚠️ check() 에 검사를 더하면 **이 값도 함께 올린다.** 안 올리면 위 최악 계산이 다시
#    낙관적으로 틀어지고, 그 틀린 값이 회귀 가드의 기준이 된다(시험이 개수를 대조한다).
CHECKED_URLS = 3

# 다시 물어봐도 답이 같은 실패 — 재시도는 시간만 버린다.
# 401·403 은 접근이 거절된 것, 404 는 주소가 바뀐 것. 전부 사람이 고쳐야 한다.
NO_RETRY_HTTP_CODES = frozenset({401, 403, 404})
TIMEOUT_S = 30

# 첫 화면이 정말 우리 화면인지 보는 표식. 리액트가 붙을 자리가 없으면
# 200 이 와도 그건 우리 앱이 아니다(호스팅 기본 페이지·오류 페이지 등).
ROOT_MARKER = '<div id="root">'

# index.html 안에서 자바스크립트 묶음 경로를 뽑는다. Vite 는 해시가 붙은 이름을 쓰므로
# 경로를 박아 둘 수 없다 — 화면이 실제로 부르는 것을 읽어서 그대로 두드린다.
BUNDLE_RE = re.compile(r'src="(/assets/[^"]+\.js)"')

# 배포된 묶음에 **관리자(비밀) 키가 실렸나**를 보는 표식 (2026-09-01 신설).
#
# ⛔ 접두사만 찾으면 안 된다 — `@supabase/supabase-js` 자신이 키 형식을 판별하는 함수를
#    들고 있어서 묶음에 접두사가 맨몸으로 등장한다(실측: ``e.startsWith(`sb_secret_`)``).
#    그래서 **뒤에 키 재료가 실제로 붙은 것만** 잡는다. 실제 키는 41자(접두사 10 + 재료 31)
#    이므로 20자만 요구해도 라이브러리 쪽(뒤가 백틱)과는 확실히 갈린다.
ADMIN_KEY_RE = re.compile(rb"sb_secret_[A-Za-z0-9_\-]{20,}")

# 옛 형식(JWT) 키.
#
# ⛔ **디코딩된 글자(`"role":"service_role"`)를 찾으면 안 된다 — 번들에 그 글자는 없다.**
#    JWT 는 payload 가 base64url 로 **인코딩된 채** 실린다:
#        eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJzZXJ2aWNlX3JvbGUi…
#    처음엔 `"role"\s*:\s*"service_role"` 로 찾게 만들었는데, 실측해 보니 **한 번도 발동할
#    수 없는 죽은 가드**였다(2026-09-01 2차 검증). 죽은 가드는 없는 가드보다 나쁘다 —
#    "막고 있다"는 거짓 안심을 주기 때문이다.
# ⇒ **JWT 모양을 찾아 payload 를 직접 풀어** 역할을 본다. base64 정렬(3가지)에 안 휘둘리고,
#   `role` 이 어디에 있든(중간·끝) 잡힌다.
# ⓘ 이 프로젝트는 새 형식(`sb_…`)을 쓰므로 이 갈래는 **방어적 이중 안전망**이다 — 옛 형식
#   키를 다른 프로젝트·옛 문서에서 복사해 오는 날을 위한 것.
JWT_RE = re.compile(rb"eyJ[A-Za-z0-9_\-]{8,}\.(eyJ[A-Za-z0-9_\-]{16,})\.[A-Za-z0-9_\-]{8,}")


def jwt_says_service_role(bundle: bytes) -> bool:
    """번들 안 JWT 들의 payload 를 풀어 `service_role` 인 것이 있나.

    ⛔ 값을 돌려주지도 찍지도 않는다 — True/False 만.
    ⚠️ 못 푸는 조각은 **조용히 건너뛴다**(JWT 를 닮았을 뿐인 글자일 수 있다). 여기서 예외를
       던지면 감시 전체가 죽어 진짜 사고까지 못 알린다.
    """
    import base64

    for m in JWT_RE.finditer(bundle):
        body = m.group(1)
        body += b"=" * (-len(body) % 4)      # base64url 은 패딩이 빠져 있다
        try:
            payload = base64.urlsafe_b64decode(body)
        except Exception:
            continue
        if b"service_role" in payload:
            return True
    return False


class CheckFailed(Exception):
    """검사 하나가 실패했다. 메시지가 그대로 사람에게 보인다.

    ⛔ **`kind` 를 붙이는 이유** (2026-09-01 2차 적대검증에서 신설).
       예전에는 실패에 종류가 없어서 워크플로가 **모든 실패에 같은 제목·같은 대본**을 썼다.
       그 대본 첫 줄은 "주소를 열어 **멀쩡히 뜨면** 잠깐 끊겼던 것이니 이 이슈를 닫으세요"다.
       그런데 관리자 키가 샌 날은 **사이트가 멀쩡히 뜬다** — 즉 운영자에게 유출 이슈를
       **닫으라고 지시**하게 된다. 게다가 제목이 같으면 이미 열린 '사이트 다운' 이슈가
       유출 알림을 통째로 삼킨다(중복 방지 로직이 제목 완전일치라서).
       ⇒ 종류를 달아 워크플로가 제목과 대본을 **갈라 쓰게** 한다.

    kind:
      "down" — 사이트가 안 뜬다·반쪽 배포·파일이 이상하다 (기본값)
      "leak" — 배포된 묶음에 관리자 키로 보이는 값이 실렸다 (사이트는 멀쩡하다)
    """

    def __init__(self, message: str, kind: str = "down"):
        super().__init__(message)
        self.kind = kind


def fetch(url: str) -> tuple[int, bytes]:
    """한 번 받아 본다. 실패하면 예외."""
    req = urllib.request.Request(url, headers={"User-Agent": "sangga-health-check"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
        return resp.status, resp.read()


def fetch_with_retry(url: str, what: str, attempts: int = RETRY_COUNT, sleep=time.sleep) -> bytes:
    """받아질 때까지 몇 번 다시 해 본다. 끝내 안 되면 CheckFailed.

    `sleep` 을 인자로 받는 이유는 collect_lh_notices.get_json_with_retry 와 같다 —
    시험이 실제로 몇십 초씩 기다리지 않게, 가짜 sleep 을 끼워 넣을 자리를 열어 둔다.
    """
    last = ""
    for attempt in range(1, attempts + 1):
        try:
            status, body = fetch(url)
            if status == 200:
                return body
            last = f"HTTP {status}"
            if status in NO_RETRY_HTTP_CODES:
                raise CheckFailed(f"{what}을(를) 못 받았습니다: {url} → {last}")
        except urllib.error.HTTPError as ex:
            last = f"HTTP {ex.code}"
            if ex.code in NO_RETRY_HTTP_CODES:
                raise CheckFailed(f"{what}을(를) 못 받았습니다: {url} → {last}") from ex
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            last = f"연결 실패({ex})"
        if attempt < attempts:
            wait = RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
            print(f"  · {what} {attempt}번째 실패({last}) — {wait}초 뒤 다시 시도합니다")
            sleep(wait)
    raise CheckFailed(f"{what}을(를) 못 받았습니다: {url} → {last}")


def check(site: str, sleep=time.sleep) -> list[str]:
    """세 가지를 본다. 통과한 것들의 설명을 돌려주고, 실패하면 CheckFailed.

    `sleep` 은 시험이 재시도 백오프를 실제로 기다리지 않게 끼워 넣는 자리다(기본은
    진짜 time.sleep).

    ⛔ **최악 대기는 한 번 몫이 아니라 URL 수만큼이다** (2026-09-01 정정). 검사 하나가
       끝내 실패하면 곧장 예외가 올라가 뒤의 URL 을 안 두드리는 것은 맞다 — 그러나
       앞 URL 이 **마지막 시도에서 성공**하면 예외가 안 나므로 그대로 다음으로 넘어간다.
       즉 조기 종료는 **실패했을 때만** 일어나고, 가장 비싼 경로는 "셋이 각각 끝까지
       버티다 겨우 성공"이다(위 상수 머리말의 계산 참조).
    """
    passed: list[str] = []

    # ① 첫 화면
    home = fetch_with_retry(site + "/", "첫 화면", sleep=sleep)
    html = home.decode("utf-8", errors="replace")
    if ROOT_MARKER not in html:
        raise CheckFailed(
            f"첫 화면은 200 인데 우리 화면이 아닙니다 — '{ROOT_MARKER}' 가 없습니다. "
            "배포가 엉뚱한 것을 올렸거나 호스팅 기본 페이지가 보이는 중일 수 있습니다."
        )
    passed.append("첫 화면 200 · 리액트가 붙을 자리 있음")

    # ② 자바스크립트 묶음 — 여기가 반쪽 배포를 잡는 자리다
    match = BUNDLE_RE.search(html)
    if not match:
        raise CheckFailed(
            "첫 화면에서 자바스크립트 묶음 경로를 못 찾았습니다. "
            "빌드 결과가 바뀌었다면 이 스크립트의 BUNDLE_RE 도 함께 고쳐야 합니다."
        )
    bundle_path = match.group(1)
    bundle = fetch_with_retry(site + bundle_path, "자바스크립트 묶음", sleep=sleep)
    if len(bundle) < 1024:
        raise CheckFailed(
            f"자바스크립트 묶음이 너무 작습니다({len(bundle)}바이트) — {bundle_path}. "
            "오류 페이지가 200 으로 온 것일 수 있습니다."
        )
    # ⛔ **관리자 키가 배포된 묶음에 실렸나** (2026-09-01 적대검증에서 신설).
    #
    # `scripts/make_env_local.py` 의 값 검사는 **로컬 번들**만 덮는다 — 라이브 번들은
    # `.env.local` 이 아니라 **Vercel 대시보드의 env** 로 빌드되기 때문이다. 즉 콘솔의
    # `VITE_SUPABASE_ANON_KEY` 칸에 관리자 키를 붙여넣는 경로는 그 검사를 통째로 지나간다.
    # 그 문은 여기서만 지킬 수 있다 — 이미 묶음 본문을 손에 들고 있으니 한 번 훑으면 된다.
    #
    # ⚠️ 찾는 것은 **관리자 키의 생김새**지 값이 아니다(값은 어디에도 안 적는다).
    #
    # ⛔ **접두사만 찾으면 오탐이 난다** — 라이브에 돌려 보고 그 자리에서 잡았다.
    #    `@supabase/supabase-js` 가 키 형식을 판별하는 함수를 들고 있어서, 묶음 안에
    #    접두사가 **맨몸으로** 등장한다(실측 2026-09-01):
    #        Va=e=>e.startsWith(`sb_publishable_`)||e.startsWith(`sb_secret_`)
    #    그대로 두면 이 감시가 6시간마다 "관리자 키 유출" 이슈를 영원히 연다 —
    #    오탐을 내는 감시는 곧 무시되고, 그러면 진짜 사고도 함께 묻힌다.
    # ⇒ **접두사 뒤에 키 재료가 실제로 붙어 있을 때만** 잡는다(실제 키는 41자 = 접두사
    #   10자 + 재료 31자). 라이브러리 쪽은 접두사 바로 뒤가 백틱이라 안 걸린다.
    # ⛔ 옛 형식(JWT)은 **디코딩된 글자를 찾으면 안 된다** — 번들에는 base64 로 인코딩된
    #    채 실려서 그 글자가 아예 없다(2026-09-01 2차 검증에서 죽은 가드로 드러남).
    #    jwt_says_service_role() 이 payload 를 직접 풀어 본다.
    # ⛔ 걸리면 **즉시 시끄럽게** 실패시킨다. 이건 "사이트가 죽었다"보다 급한 사고라,
    #    6시간마다 도는 이 감시가 그날 안에 이슈를 연다.
    if ADMIN_KEY_RE.search(bundle) or jwt_says_service_role(bundle):
        raise CheckFailed(
            "🔴 배포된 자바스크립트 묶음에 **관리자(비밀) 키로 보이는 값**이 들어 있습니다 "
            f"({bundle_path}). Vercel 프로젝트 설정의 VITE_SUPABASE_ANON_KEY 가 "
            "공개키(sb_publishable_…)인지 즉시 확인하고, 관리자 키였다면 "
            "Supabase 콘솔에서 **그 키를 회전(재발급)**하세요 — 이미 배포된 값은 회수할 수 "
            "없습니다. ⚠️ 값 자체는 여기에 찍지 않습니다(로그에 남으면 더 퍼집니다).",
            kind="leak",
        )
    passed.append(f"묶음 200 · {len(bundle):,}바이트 · 관리자 키 흔적 없음 ({bundle_path})")

    # ③ 지도가 쓰는 상권 파일
    geo = fetch_with_retry(site + "/districts.geojson", "상권 지도 파일", sleep=sleep)
    if not geo.lstrip().startswith(b"{"):
        raise CheckFailed("상권 지도 파일이 JSON 이 아닙니다 — 오류 페이지가 온 듯합니다.")
    passed.append(f"상권 지도 파일 200 · {len(geo):,}바이트")

    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description="라이브 사이트가 서 있는지 밖에서 확인한다.")
    parser.add_argument(
        "--site",
        default=os.environ.get("SANGGA_SITE_URL", DEFAULT_SITE),
        help=f"확인할 주소 (기본값: {DEFAULT_SITE})",
    )
    args = parser.parse_args()
    site = args.site.rstrip("/")

    print(f"라이브 확인: {site}")
    try:
        for line in check(site):
            print(f"  [정상] {line}")
    except CheckFailed as ex:
        print(f"  [실패] {ex}")
        # 워크플로가 이 줄을 읽어 이슈 본문에 넣는다.
        _emit_output("reason", str(ex))
        # ⛔ 종류도 함께 내보낸다 — 워크플로가 이걸로 **제목과 대본을 갈라 쓴다.**
        #    안 내보내면 유출도 '사이트 다운' 대본으로 나가고(닫으라는 지시가 된다),
        #    같은 제목이 이미 열려 있으면 통째로 삼켜진다. CheckFailed 머리말 참조.
        _emit_output("kind", getattr(ex, "kind", "down"))
        print("\n라이브가 정상이 아닙니다.")
        return 1

    print("\n라이브 정상입니다.")
    return 0


def _emit_output(key: str, value: str) -> None:
    """GitHub Actions 에 값을 넘긴다. 로컬에서 돌리면 아무 일도 안 한다.

    ⚠️ 구분자를 **실행마다 다르게** 만든다. 고정 문자열을 쓰면, 값 안에 그 문자열과 똑같은
       줄이 들어오는 순간 거기서 값이 끊기고 **그 뒤가 새 key=value 로 읽힌다**(GitHub 이
       랜덤 구분자를 권하는 이유). 지금 이 자리에 들어오는 값은 우리가 만든 문구뿐이라
       실제 위험은 낮지만, 값의 출처가 늘어나는 날 이 한 줄이 방어선이 된다.
       (2026-08-24 적대적 보안 검토 지적.)
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    # 여러 줄이 올 수 있으므로 구분자 형식을 쓴다(한 줄 형식은 줄바꿈에서 깨진다).
    delim = "SANGGA_EOF_" + secrets.token_hex(8)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{key}<<{delim}\n{value}\n{delim}\n")


if __name__ == "__main__":
    sys.exit(main())
