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
    지금은 비밀값을 하나도 안 쓰는 쪽을 골랐다(형제 감시 둘과 같은 철학). 창고가 죽으면
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
import urllib.error
import urllib.request

DEFAULT_SITE = "https://sangga-one.vercel.app"

# 배포가 느릴 때 조급하게 실패로 판정하지 않는다. 죽었다고 잘못 알리면
# 그 이슈를 닫는 사람의 손이 들고, 몇 번 반복되면 알림 자체가 무시된다.
TIMEOUT_S = 30
RETRIES = 3

# 첫 화면이 정말 우리 화면인지 보는 표식. 리액트가 붙을 자리가 없으면
# 200 이 와도 그건 우리 앱이 아니다(호스팅 기본 페이지·오류 페이지 등).
ROOT_MARKER = '<div id="root">'

# index.html 안에서 자바스크립트 묶음 경로를 뽑는다. Vite 는 해시가 붙은 이름을 쓰므로
# 경로를 박아 둘 수 없다 — 화면이 실제로 부르는 것을 읽어서 그대로 두드린다.
BUNDLE_RE = re.compile(r'src="(/assets/[^"]+\.js)"')


class CheckFailed(Exception):
    """검사 하나가 실패했다. 메시지가 그대로 사람에게 보인다."""


def fetch(url: str) -> tuple[int, bytes]:
    """한 번 받아 본다. 실패하면 예외."""
    req = urllib.request.Request(url, headers={"User-Agent": "sangga-health-check"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
        return resp.status, resp.read()


def fetch_with_retry(url: str, what: str) -> bytes:
    """받아질 때까지 몇 번 다시 해 본다. 끝내 안 되면 CheckFailed."""
    last = ""
    for attempt in range(1, RETRIES + 1):
        try:
            status, body = fetch(url)
            if status == 200:
                return body
            last = f"HTTP {status}"
        except urllib.error.HTTPError as ex:
            last = f"HTTP {ex.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            last = f"연결 실패({ex})"
        if attempt < RETRIES:
            print(f"  · {what} {attempt}번째 실패({last}) — 다시 시도합니다")
    raise CheckFailed(f"{what}을(를) 못 받았습니다: {url} → {last}")


def check(site: str) -> list[str]:
    """세 가지를 본다. 통과한 것들의 설명을 돌려주고, 실패하면 CheckFailed."""
    passed: list[str] = []

    # ① 첫 화면
    home = fetch_with_retry(site + "/", "첫 화면")
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
    bundle = fetch_with_retry(site + bundle_path, "자바스크립트 묶음")
    if len(bundle) < 1024:
        raise CheckFailed(
            f"자바스크립트 묶음이 너무 작습니다({len(bundle)}바이트) — {bundle_path}. "
            "오류 페이지가 200 으로 온 것일 수 있습니다."
        )
    passed.append(f"묶음 200 · {len(bundle):,}바이트 ({bundle_path})")

    # ③ 지도가 쓰는 상권 파일
    geo = fetch_with_retry(site + "/districts.geojson", "상권 지도 파일")
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
