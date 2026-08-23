# -*- coding: utf-8 -*-
"""
소상공인 상권정보 — 새 분기 스냅샷이 포털에 떴는지 확인한다.

왜 이게 필요한가
----------------
CLAUDE.md 절대 규칙 6: 분기 스냅샷은 **소급 불가**다. 포털에서 내려가면 영원히 못
받는다. 그런데 수집은 지금 전부 사람 손이고(`.github/workflows/`에 cron 0건),
"새 분기가 떴다"는 사실을 알려주는 장치가 없었다. 사람이 잊는 것이 이 데이터를
잃는 가장 현실적인 경로다.

왜 다운로드까지 자동화하지 않나 (2026-08-08 결정)
--------------------------------------------------
① 원본 백업이 어차피 사람 손이다 — 외장 SSD(F:)를 꽂아야 `backup_raw.py`가 돈다.
   CI 러너가 받은 zip 은 러너가 사라지면 같이 사라지므로, 자동으로 받아도 보관은
   해결되지 않는다.
② 적재하려면 DB 서비스키(전체 권한)를 GitHub 에 올려야 한다. 알림만 하면 비밀값이
   0개다.
③ 게시일이 미뤄질 수 있다. 날짜 고정 cron 은 헛발질하지만, **실제 게시를 감지**하면
   언제 올라오든 잡는다.
그래서 이 스크립트는 **알리기만** 하고, 받는 것·적재·백업은 사람이 로컬에서 한다.

쓰는 법
-------
    python scripts/check_new_sangkwon_quarter.py          # 사람이 눈으로 확인
    python scripts/check_new_sangkwon_quarter.py --json   # 기계용 출력

GitHub Actions 에서는 GITHUB_OUTPUT 에 found/quarters 를 써서 다음 단계가 이슈를
연다. 종료코드: 0 = 정상(새 분기가 있든 없든) / 1 = 포털 조회 실패.

새 분기를 실제로 받아 적재했으면 아래 LATEST_KNOWN_QUARTER 를 그 날짜로 올린다.
그게 이 스크립트의 유일한 기준선이다.
"""

import argparse
import json
import os
import re
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from download_sangkwon_history import fetch_history_list  # noqa: E402

# ── 기준선 ────────────────────────────────────────────────────────────────────

# 이미 받아서 보관 중인 가장 최신 분기(YYYYMMDD). 이보다 뒤면 "새 분기"로 본다.
# 2026-08-08 실측: data/raw/sangkwon_zips 에 44개 보관, 최신이 20260630.
# ⚠️ 새 분기를 받아 적재했으면 **이 값을 올려야** 다음 분기를 제대로 감지한다.
LATEST_KNOWN_QUARTER = "20260630"

# 파일명 끝의 분기 날짜. download_sangkwon_history.RE_QUARTERLY 와 같은 형태를 보되
# 여기서는 날짜를 **뽑아내야** 하므로 캡처 그룹을 둔다.
RE_QUARTER_DATE = re.compile(r"_(20\d{6})$")

ISSUE_BODY_FILE = "sangkwon_new_quarter_issue.md"


# ── 순수 함수 (네트워크 없음 — 테스트 대상) ───────────────────────────────────


def extract_quarter_date(name):
    """파일명에서 분기 날짜(YYYYMMDD)를 뽑는다. 분기 파일이 아니면 None."""
    if not name:
        return None
    m = RE_QUARTER_DATE.search(name.strip())
    return m.group(1) if m else None


def find_new_quarters(items, latest_known=LATEST_KNOWN_QUARTER):
    """포털 목록에서 기준선보다 뒤인 분기만 골라 (날짜, 이름) 목록으로 돌려준다.

    날짜 오름차순. 같은 날짜가 여러 줄이면 먼저 나온 이름을 쓴다(포털이 같은 분기를
    두 번 올린 적이 있어 중복을 제거한다).
    """
    found = {}
    for it in items or []:
        d = extract_quarter_date(it.get("name", ""))
        if d and d > latest_known and d not in found:
            found[d] = it["name"]
    return [(d, found[d]) for d in sorted(found)]


def build_issue_body(new_quarters, latest_known=LATEST_KNOWN_QUARTER):
    """사람이 그대로 따라 할 수 있는 이슈 본문을 만든다."""
    lines = [
        "소상공인 상권정보에 **새 분기 스냅샷**이 올라왔습니다.",
        "",
        "> 이 데이터는 포털에서 내려가면 **다시 받을 수 없습니다**(CLAUDE.md 절대 규칙 6).",
        "> 공실 이력·점포 생존기간이 전부 여기서 나옵니다.",
        "",
        "## 새로 올라온 것",
        "",
        "| 분기 | 파일명 |",
        "|---|---|",
    ]
    for d, name in new_quarters:
        lines.append("| {}-{}-{} | `{}` |".format(d[:4], d[4:6], d[6:8], name))
    lines += [
        "",
        "지금 기준선(보관 중인 최신 분기)은 `{}` 입니다.".format(latest_known),
        "",
        "## 할 일 (내 PC에서)",
        "",
        "```powershell",
        r"cd D:\sangga",
        "python scripts/download_sangkwon_history.py   # 새 분기만 이어받는다",
        "python scripts/collectors/load_sangkwon_snapshot.py",
        "python scripts/backup_raw.py                  # 외장 SSD(F:) 연결 필요",
        "python scripts/backup_raw.py --verify",
        "```",
        "",
        "적재·백업까지 끝나면 `scripts/check_new_sangkwon_quarter.py` 의",
        "`LATEST_KNOWN_QUARTER` 를 `{}` 로 올리고 이 이슈를 닫습니다.".format(
            new_quarters[-1][0] if new_quarters else latest_known
        ),
        "",
        "*(이 이슈는 분기 감시 워크플로우가 자동으로 열었습니다.)*",
    ]
    return "\n".join(lines) + "\n"


def build_issue_title(new_quarters):
    """이슈 제목. 같은 분기로 이슈가 두 번 열리지 않게 날짜를 제목에 박는다."""
    return "새 분기 상권정보 스냅샷: {}".format(
        ", ".join(d for d, _ in new_quarters)
    )


# ── 출력 ──────────────────────────────────────────────────────────────────────


def write_github_output(new_quarters):
    """GitHub Actions 다음 단계가 읽을 값을 GITHUB_OUTPUT 에 쓴다.

    로컬 실행(환경변수 없음)에서는 아무것도 하지 않는다.
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write("found={}\n".format("true" if new_quarters else "false"))
        f.write("quarters={}\n".format(",".join(d for d, _ in new_quarters)))
        f.write("title={}\n".format(build_issue_title(new_quarters) if new_quarters else ""))
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="새 분기 상권정보 스냅샷 감시")
    ap.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    args = ap.parse_args(argv)

    try:
        items, excluded = fetch_history_list()
    except Exception as e:  # 네트워크·포털 구조 변경 등
        print("포털 목록 조회 실패: {}".format(e), file=sys.stderr)
        print(
            "포털이 응답하지 않거나 목록 HTML 구조가 바뀌었을 수 있습니다. "
            "download_sangkwon_history.py 의 정규식을 확인하세요.",
            file=sys.stderr,
        )
        return 1

    if not items:
        print("포털 목록이 비어 있습니다 — 구조가 바뀌었을 가능성이 높습니다.", file=sys.stderr)
        return 1

    new_quarters = find_new_quarters(items)

    if args.json:
        print(json.dumps(
            {
                "latest_known": LATEST_KNOWN_QUARTER,
                "portal_total": len(items),
                "excluded": len(excluded),
                "new": [{"date": d, "name": n} for d, n in new_quarters],
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print("=" * 66)
        print("소상공인 상권정보 — 새 분기 감시")
        print("=" * 66)
        print("  기준선(보관 중 최신) : {}".format(LATEST_KNOWN_QUARTER))
        print("  포털 분기 파일       : {}개 (비분기 {}개 제외)".format(len(items), len(excluded)))
        if new_quarters:
            print("  ★ 새 분기           : {}개".format(len(new_quarters)))
            for d, name in new_quarters:
                print("      {}  {}".format(d, name))
            print()
            print("  → 지금 받으세요. 포털에서 내려가면 다시 못 받습니다.")
        else:
            print("  새 분기             : 없음")
        print("=" * 66)

    if new_quarters:
        with open(ISSUE_BODY_FILE, "w", encoding="utf-8") as f:
            f.write(build_issue_body(new_quarters))
    write_github_output(new_quarters)
    return 0


if __name__ == "__main__":
    sys.exit(main())
