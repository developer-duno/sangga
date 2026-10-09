"""IndexNow 알림 — 바뀐 주소를 빙·네이버(·Yandex·Seznam·Yep)에 한 번에 알린다.

IndexNow(https://www.indexnow.org/documentation)는 "이 주소가 새로 생겼거나 바뀌었다"를
검색엔진에 알리는 공개 규격이다. 한 곳(api.indexnow.org)에 보내면 참여 엔진 전부가 나눠 받는다
(규격 원문: "submitted URLs will be automatically shared with all other participating search engines").
구글은 참여하지 않는다 — 구글은 sitemap·서치콘솔이 길이다.

열쇠(key)는 비밀이 아니다 — 사이트 루트의 `/<key>.txt`(public/ 에 둔다) 가 "이 사이트 주인이 보낸 알림"임을
증명하는 공개 표식이다. 열쇠 파일이 없거나 내용이 다르면 403 으로 거부된다.

응답 코드(규격 원문): 200 받음 · 202 받음(열쇠 검증은 나중) · 400 형식 오류 · 403 열쇠 불일치 ·
422 주소가 이 호스트가 아님 · 429 너무 잦음. **200 은 "받았다"일 뿐 색인을 보장하지 않는다.**

쓰는 때: 첫 HTML 이 바뀌는 배포 뒤(제목·설명·소개문) · 새 분기 적재 뒤 · sitemap 에 주소를 더한 뒤.
기본값은 첫 화면 하나. 더 보내려면 인자로 주소를 나열한다(한 번에 1만 개까지 — 규격).

    python scripts/indexnow_ping.py                                  # 첫 화면 알림
    python scripts/indexnow_ping.py --dry-run                        # 보낼 본문만 출력(네트워크 0)
    python scripts/indexnow_ping.py https://sangga-one.vercel.app/?sgg=11680   # 주소 여러 개

종료 코드: 0 = 200/202 · 1 = 그 밖의 응답 · 2 = 연결 실패.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SITE = "https://sangga-one.vercel.app/"
HOST = "sangga-one.vercel.app"
ENDPOINT = "https://api.indexnow.org/indexnow"
# 열쇠 = public/<key>.txt 파일 이름과 내용 — tests/test_indexnow.py 가 셋이 같은지 지킨다.
KEY = "12c00fba9aca9a86435817c17a3c8b89"
KEY_FILE = Path(__file__).resolve().parent.parent / "public" / f"{KEY}.txt"


def build_body(urls: list[str]) -> dict:
    """규격의 POST 본문 — host·key·keyLocation·urlList."""
    bad = [u for u in urls if not u.startswith(SITE)]
    if bad:
        raise ValueError(f"이 사이트 주소가 아님: {bad}")
    return {
        "host": HOST,
        "key": KEY,
        "keyLocation": f"{SITE}{KEY}.txt",
        "urlList": urls,
    }


def ping(urls: list[str], timeout: float = 20.0) -> int:
    """POST 한 번. 응답 코드를 돌려준다(연결 실패는 -1)."""
    data = json.dumps(build_body(urls), ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=data, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — 고정 https 주소
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError) as e:
        print(f"[연결 실패] {e}", file=sys.stderr)
        return -1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="IndexNow 로 바뀐 주소를 빙·네이버에 알린다")
    ap.add_argument("urls", nargs="*", default=[SITE], help=f"알릴 주소(기본 {SITE})")
    ap.add_argument("--dry-run", action="store_true", help="보낼 본문만 출력(네트워크 0)")
    args = ap.parse_args(argv)

    if not KEY_FILE.is_file() or KEY_FILE.read_text(encoding="utf-8").strip() != KEY:
        print(f"[사고] 열쇠 파일이 없거나 내용이 다름: {KEY_FILE}", file=sys.stderr)
        return 1
    body = build_body(args.urls)
    print(json.dumps(body, ensure_ascii=False, indent=2))
    if args.dry_run:
        print("[dry-run] 보내지 않음")
        return 0
    code = ping(args.urls)
    print(f"응답 {code} — " + {
        200: "받음(색인 보장 아님)", 202: "받음 · 열쇠 검증은 나중", 400: "형식 오류",
        403: "열쇠 불일치(배포가 아직이거나 파일 내용이 다름)", 422: "주소가 이 호스트가 아님",
        429: "너무 잦음", -1: "연결 실패",
    }.get(code, "알 수 없는 응답"))
    if code in (200, 202):
        return 0
    return 2 if code == -1 else 1


if __name__ == "__main__":
    sys.exit(main())
