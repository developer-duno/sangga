# -*- coding: utf-8 -*-
"""
상권(district) 원천 2곳이 갱신됐는지 확인한다 — 서울시 상권영역 / 소진공 주요상권현황.

왜 이게 필요한가
----------------
`district` 표 1,687개(서울 1,650 + 대전 37)는 화면에서 "속한 상권" 한 줄로 그대로
보인다. 그런데 이 두 원천은 **갱신 주기가 비정기**다 — 분기 스냅샷처럼 날짜가 정해져
있지 않아서, 이미 있는 분기 감시 크론(`sangkwon-quarterly-watch.yml`)으로는 못 잡는다.
그래서 원천이 바뀌어도 아무 신호가 없고, 화면 상권 경계는 **조용히 낡는다**. 조용한
낡음은 에러가 아니라서 아무도 모른다(결정 0008 §8 · 0009 §6 의 미해결 항목).

왜 다운로드까지 자동화하지 않나 (형제 감시와 같은 이유)
--------------------------------------------------------
① 원본 백업이 어차피 사람 손이다 — 외장 SSD(F:)를 꽂아야 `backup_raw.py`가 돈다.
② 적재하려면 DB 서비스키(전체 권한)를 GitHub 에 올려야 한다. 알림만 하면 비밀값이 0개다.
③ 갱신일이 언제일지 모른다. 날짜 고정 cron 은 헛발질하지만, **실제 갱신을 감지**하면
   언제 바뀌든 잡는다.
그래서 이 스크립트는 **알리기만** 하고, 받는 것·적재·백업은 사람이 로컬에서 한다.

왜 신호가 하필 "HTML 의 수정일 칸"인가 (2026-08-15 실측)
---------------------------------------------------------
소진공(15090955)의 다운로드 메타 JSON 에는 `fileDataRegistVO.updtDt` 칸이 있는데
**값이 null 로 온다.** 즉 기계용 메타로는 갱신 시점을 알 수 없다. 상세 페이지 HTML 의
"수정일" 칸만이 유일하게 날짜를 준다. 서울(OA-15560)도 마찬가지로 상세 페이지의
"데이터 갱신일" 칸을 본다.

⚠️ 그래서 이 감시는 **포털 화면 구조에 의존한다.** 구조가 바뀌면 날짜를 못 찾는데,
   그걸 "변경 없음"으로 조용히 넘기면 감시가 장님이 된 채 초록불만 켜진다. 그래서
   못 찾으면 예외를 던져 **시끄럽게 실패**시킨다(워크플로우가 실패 이슈를 연다).

왜 requests 를 안 쓰나
----------------------
CI 워크플로우에 설치 단계를 두지 않는 것이 형제 감시의 원칙이고(비밀값 0개 + 설치 0개),
러너에는 requests 가 없다. 그래서 표준 라이브러리(urllib)만 쓴다. 같은 이유로
`fetch_sbiz_district.py` / `fetch_seoul_district.py` 를 import 하지 않는다 — 그 모듈들이
맨 위에서 requests 를 import 하므로 CI 에서 즉시 죽는다.

쓰는 법
-------
    python scripts/check_district_source_update.py          # 사람이 눈으로 확인
    python scripts/check_district_source_update.py --json   # 기계용 출력

GitHub Actions 에서는 GITHUB_OUTPUT 에 found/title 을 써서 다음 단계가 이슈를 연다.
종료코드: 0 = 정상(변경이 있든 없든) / 1 = 조회·파싱 실패.

원천을 실제로 받아 적재했으면 아래 SBIZ_KNOWN_UPDATE / SEOUL_KNOWN_UPDATE 를 새 날짜로
올린다. 그게 이 스크립트의 유일한 기준선이다.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request

# ── 기준선 ────────────────────────────────────────────────────────────────────

# 지금 받아서 적재해 둔 판의 갱신일. 포털 값이 이것과 **다르면** 사람에게 알린다.
# 2026-08-15 라이브 실측값.
# ⚠️ 새 판을 받아 적재했으면 **이 값을 올려야** 다음 갱신을 제대로 감지한다.
SBIZ_KNOWN_UPDATE = "2025-08-12"
SEOUL_KNOWN_UPDATE = "2026-06-11"

# 상세 페이지 주소.
# ⚠️ fetch_sbiz_district.py / fetch_seoul_district.py 의 DATASET_PAGE 와 **같은 값**이다.
#    한쪽이 바뀌면 같이 고칠 것. (여기서 그 모듈을 import 하지 않는 이유는 위 docstring 참조)
SBIZ_PAGE = "https://www.data.go.kr/data/15090955/fileData.do"
SEOUL_PAGE = "https://data.seoul.go.kr/dataList/OA-15560/S/1/datasetView.do"

# 화면·이슈 제목에 쓸 짧은 이름표
SOURCE_LABELS = {"sbiz": "소진공", "seoul": "서울"}
# 출력 순서를 고정한다 — 제목이 실행할 때마다 달라지면 이슈 중복 방지가 깨진다.
SOURCE_ORDER = ("sbiz", "seoul")

ISSUE_BODY_FILE = "district_source_update_issue.md"

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

TIMEOUT_SEC = 30
RETRY_COUNT = 3  # 최초 시도 포함
RETRY_BACKOFF_SEC = 5  # 5초 → 10초 (2배씩)

# ── 날짜 뽑기 정규식 ──────────────────────────────────────────────────────────

# 소진공: `<strong class="key">수정일</strong> <div class="value">2025-08-12</div>`
# "등록일"이 바로 위에 같은 모양으로 있으므로 라벨을 반드시 붙여서 본다.
RE_SBIZ_UPDATE = re.compile(
    r"수정일\s*</strong>\s*<div[^>]*class=[\"']value[\"'][^>]*>\s*(\d{4}-\d{2}-\d{2})"
)

# 서울: `<th scope="row">데이터 갱신일</th> <td><span class="en">2026.06.11.</span></td>`
# 라벨 앞뒤 공백이 있는 판과 없는 판이 둘 다 실측됐다(2026-08-15) → \s* 로 둘 다 받는다.
# <span> 이 없는 판이 나와도 날짜는 잡히게 span 은 선택으로 둔다.
RE_SEOUL_UPDATE = re.compile(
    r"데이터\s*갱신일\s*</th>\s*<td[^>]*>\s*(?:<span[^>]*>\s*)?(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})"
)


# ── 순수 함수 (네트워크 없음 — 테스트 대상) ───────────────────────────────────


def parse_sbiz_update_date(html):
    """소진공 상세 페이지 HTML 에서 "수정일"(YYYY-MM-DD)을 뽑는다.

    못 찾으면 ValueError. 조용히 None 을 돌려주면 감시가 장님이 된 채 초록불만 켜진다.
    """
    m = RE_SBIZ_UPDATE.search(html or "")
    if not m:
        raise ValueError(
            "소진공 상세 페이지에서 '수정일' 칸을 못 찾았습니다 — "
            "포털 화면 구조가 바뀌었을 수 있으니 사람이 직접 확인하세요 "
            "(check_district_source_update.py 의 RE_SBIZ_UPDATE)."
        )
    return m.group(1)


def parse_seoul_update_date(html):
    """서울 상세 페이지 HTML 에서 "데이터 갱신일"을 뽑아 YYYY-MM-DD 로 돌려준다.

    포털은 `2026.06.11.`(점 구분·끝점) 형태로 준다 — 두 원천의 날짜를 같은 자로 재려면
    한 형식으로 맞춰야 하므로 여기서 정규화한다. 못 찾으면 ValueError.
    """
    m = RE_SEOUL_UPDATE.search(html or "")
    if not m:
        raise ValueError(
            "서울 상세 페이지에서 '데이터 갱신일' 칸을 못 찾았습니다 — "
            "포털 화면 구조가 바뀌었을 수 있으니 사람이 직접 확인하세요 "
            "(check_district_source_update.py 의 RE_SEOUL_UPDATE)."
        )
    y, mo, d = m.group(1), m.group(2), m.group(3)
    return "{}-{:02d}-{:02d}".format(y, int(mo), int(d))


def find_changes(current_by_source, known_by_source):
    """기준선과 **다른** 원천만 골라 목록으로 돌려준다.

    부등호(>)가 아니라 `!=` 로 본다 — 포털이 날짜를 되돌리거나(재게시) 형식을 바꿔도
    그건 사람이 봐야 할 사건이지, 조용히 넘길 일이 아니기 때문이다.
    """
    changes = []
    for key in SOURCE_ORDER:
        if key not in (current_by_source or {}):
            continue
        cur = current_by_source[key]
        known = (known_by_source or {}).get(key)
        if cur != known:
            changes.append({
                "key": key,
                "label": SOURCE_LABELS.get(key, key),
                "known": known,
                "current": cur,
            })
    return changes


def build_issue_title(changes):
    """이슈 제목. 같은 갱신으로 이슈가 두 번 열리지 않게 **새 날짜를 제목에 박는다.**"""
    return "상권 원천 갱신: {}".format(
        ", ".join("{} {}".format(c["label"], c["current"]) for c in changes)
    )


def _sbiz_steps():
    return [
        "### 소진공 주요상권현황 (대전 37개)",
        "",
        "```powershell",
        "python scripts/collectors/fetch_sbiz_district.py --probe   # 크기·형식만 확인",
        "python scripts/collectors/fetch_sbiz_district.py           # 본 다운로드",
        "python scripts/collectors/load_sbiz_district.py --dry-run  # DB 쓰기 0",
        "python scripts/collectors/load_sbiz_district.py",
        "```",
        "",
        "> ⚠️ 이 자료는 전국을 담고 있지만 우리는 **대전만** 넣습니다. 서울(11)은 서울시",
        "> 자료가 정본이라 적재기가 **거부합니다**(정본이 둘로 갈라지는 것을 막는 장치).",
    ]


def _seoul_steps():
    return [
        "### 서울시 상권영역 (1,650개)",
        "",
        "```powershell",
        "python scripts/collectors/fetch_seoul_district.py --probe   # 크기·좌표계만 확인",
        "python scripts/collectors/fetch_seoul_district.py           # 본 다운로드",
        "python scripts/collectors/load_seoul_district.py --dry-run  # DB 쓰기 0",
        "python scripts/collectors/load_seoul_district.py",
        "```",
    ]


def build_issue_body(changes):
    """사람이 그대로 따라 할 수 있는 이슈 본문을 만든다."""
    lines = [
        "상권(district) 원천의 **갱신일이 바뀌었습니다.**",
        "",
        "> 받지 않으면 화면의 \"속한 상권\"이 옛 경계를 계속 보여줍니다 — 에러가 나지",
        "> 않으니 **조용히 낡습니다.**",
        "",
        "## 무엇이 바뀌었나",
        "",
        "| 원천 | 내가 알던 갱신일 | 포털의 지금 갱신일 |",
        "|---|---|---|",
    ]
    for c in changes:
        lines.append("| {} | `{}` | `{}` |".format(c["label"], c["known"], c["current"]))
    lines += [
        "",
        "## 할 일 (내 PC에서)",
        "",
        "```powershell",
        r"cd D:\sangga",
        "```",
        "",
    ]
    steps = {"sbiz": _sbiz_steps, "seoul": _seoul_steps}
    for c in changes:
        lines += steps[c["key"]]()
        lines.append("")
    lines += [
        "### 적재한 뒤 (공통 마무리)",
        "",
        "상권 이름이나 구성이 바뀌었으면 임대통계 매핑표가 어긋납니다 — 관문을 한 번 돌려",
        "확인하고, 어긋났으면 `scripts/seeds/district_rone_map.csv` 를 고칩니다.",
        "",
        "```powershell",
        "python scripts/build_rone_map.py --seed scripts/seeds/district_rone_map.csv   # exit 0 이어야 한다",
        "python scripts/build_district_geojson.py    # 지도용 파일을 다시 굽고 **커밋**한다",
        "python scripts/post_load.py                 # vacuum + 검색 요약표 갱신 + 노출 점검",
        "python scripts/backup_raw.py                # 외장 SSD(F:) 연결 필요",
        "```",
        "",
        "`public/districts.geojson` 은 **커밋해야** 지도에 반영됩니다(정적 파일).",
        "",
        "## 마지막으로",
        "",
        "`scripts/check_district_source_update.py` 의 기준선을 새 날짜로 올리고 이 이슈를 닫습니다.",
        "",
    ]
    for c in changes:
        const = "SBIZ_KNOWN_UPDATE" if c["key"] == "sbiz" else "SEOUL_KNOWN_UPDATE"
        lines.append("- `{}` → `\"{}\"`".format(const, c["current"]))
    lines += [
        "",
        "*(이 이슈는 상권 원천 감시 워크플로우가 자동으로 열었습니다.)*",
    ]
    return "\n".join(lines) + "\n"


# ── 네트워크 ──────────────────────────────────────────────────────────────────


def _get(url, timeout=TIMEOUT_SEC):
    """상세 페이지 HTML 을 문자열로 받아온다."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Accept-Language": "ko-KR,ko;q=0.9",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        # 포털마다 인코딩이 다르다(utf-8 / euc-kr). 헤더가 말해 주면 그걸 믿는다 —
        # 잘못 풀면 '수정일' 같은 한글 라벨이 깨져 정규식이 통째로 빗나간다.
        charset = None
        try:
            charset = resp.headers.get_content_charset()
        except Exception:
            pass
    return raw.decode(charset or "utf-8", errors="replace")


def _get_with_retry(url, timeout=TIMEOUT_SEC, attempts=RETRY_COUNT, sleep=time.sleep):
    """짧은 타임아웃으로 여러 번 두드린다.

    왜 재시도가 필요한가 (2026-08-10 실측)
    --------------------------------------
    형제 감시(분기 스냅샷)의 CI 실행이 `Errno 110 Connection timed out` 으로 죽었는데,
    **이틀 전 같은 러너가 같은 포털을 8초 만에 읽고 성공**했다. 즉 미국 러너에서 한국
    포털이 영영 안 닿는 게 아니라 **간헐적으로 막힌다.** 한 번 실패했다고 포기하면
    주 1회 감시가 일주일을 통째로 건너뛴다.
    """
    for attempt in range(1, attempts + 1):
        try:
            return _get(url, timeout=timeout)
        except Exception as e:
            if attempt == attempts:
                raise
            wait = RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
            print(
                "  포털 응답 없음 ({}/{}) — {}초 뒤 다시 시도합니다: {}".format(
                    attempt, attempts, wait, e
                ),
                file=sys.stderr,
                flush=True,
            )
            sleep(wait)
    # attempts >= 1 이면 위 루프에서 반드시 return 하거나 raise 한다.
    raise RuntimeError("재시도 루프가 한 번도 실행되지 않았습니다 (attempts 확인 필요).")


def fetch_sbiz_update_date():
    """소진공 상세 페이지를 읽어 수정일을 돌려준다."""
    return parse_sbiz_update_date(_get_with_retry(SBIZ_PAGE))


def fetch_seoul_update_date():
    """서울 상세 페이지를 읽어 데이터 갱신일을 돌려준다."""
    return parse_seoul_update_date(_get_with_retry(SEOUL_PAGE))


def fetch_current_dates():
    """두 원천의 지금 갱신일을 {키: 날짜} 로 돌려준다."""
    return {
        "sbiz": fetch_sbiz_update_date(),
        "seoul": fetch_seoul_update_date(),
    }


# ── 출력 ──────────────────────────────────────────────────────────────────────


def write_github_output(changes):
    """GitHub Actions 다음 단계가 읽을 값을 GITHUB_OUTPUT 에 쓴다.

    로컬 실행(환경변수 없음)에서는 아무것도 하지 않는다.
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write("found={}\n".format("true" if changes else "false"))
        f.write("title={}\n".format(build_issue_title(changes) if changes else ""))
    return True


def known_dates():
    """기준선을 {키: 날짜} 로 모은다."""
    return {"sbiz": SBIZ_KNOWN_UPDATE, "seoul": SEOUL_KNOWN_UPDATE}


def main(argv=None):
    # cp949 콘솔에서 한글·특수문자(—) 출력이 UnicodeEncodeError 로 죽지 않게 —
    # 형제 스크립트들(fetch_sbiz_district.py 등)과 같은 처방. 여기는 stderr 도 본다:
    # 실패 안내(포털 구조 변경 등)가 stderr 로 나가는데, stderr 기본값(backslashreplace)은
    # 죽지는 않지만 — 가 "\\u2014" 같은 이스케이프로 찍힌다(2026-08-15 실측). 그 안내문이 읽히는 순간이
    # 바로 비개발자가 손으로 진단해야 하는 순간이라, 읽을 수 있게 맞춘다.
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="상권 원천 갱신 감시")
    ap.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    args = ap.parse_args(argv)

    try:
        current = fetch_current_dates()
    except Exception as e:  # 네트워크·포털 구조 변경 등
        print("상권 원천 조회 실패: {}".format(e), file=sys.stderr)
        print(
            "포털이 응답하지 않거나 상세 페이지 구조가 바뀌었을 수 있습니다. "
            "check_district_source_update.py 의 정규식을 확인하세요.",
            file=sys.stderr,
        )
        return 1

    known = known_dates()
    changes = find_changes(current, known)

    if args.json:
        print(json.dumps(
            {
                "known": known,
                "current": current,
                "changes": changes,
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print("=" * 66)
        print("상권(district) 원천 갱신 감시")
        print("=" * 66)
        for key in SOURCE_ORDER:
            print("  {:<6} 기준선 {} / 포털 {}".format(
                SOURCE_LABELS.get(key, key), known.get(key), current.get(key)
            ))
        if changes:
            print("  ★ 갱신됨            : {}곳".format(len(changes)))
            for c in changes:
                print("      {}  {} → {}".format(c["label"], c["known"], c["current"]))
            print()
            print("  → 새 판을 받으세요. 안 받으면 화면 상권이 조용히 낡습니다.")
        else:
            print("  변경                : 없음")
        print("=" * 66)

    if changes:
        with open(ISSUE_BODY_FILE, "w", encoding="utf-8") as f:
            f.write(build_issue_body(changes))
    write_github_output(changes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
