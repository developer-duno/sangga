# -*- coding: utf-8 -*-
"""'다음 갱신 예정'이 지났는데 아직 옛 자료인 줄이 있는지 매주 확인한다.

왜 이게 필요한가
----------------
화면 아래 "이 자료는 언제 것인가" 표(`api.get_data_freshness()`)는 자료마다 **다음 갱신
예정일**을 규칙으로 계산해 보여 준다. 그런데 그 날짜가 지나도 **아무도 안 본다** — 표는
화면 맨 아래에 있고, 우리는 우리 화면을 손님처럼 매일 내려 보지 않는다. 실제로 건축
인허가는 지난 날짜가 22일간 떠 있었다(2026-10-01 발견 — 규칙 자체가 틀렸던 것, 2026-10-01a).

지난 날짜는 둘 중 하나다:
  ① 포털에 새 판이 떴는데 **우리가 안 받았다** → 받아서 적재하면 된다.
  ② 포털이 아직 안 올렸거나 **예정 규칙이 틀렸다** → 기다리거나 규칙을 고친다.
어느 쪽이든 사람이 한 번 봐야 하는 일이다. 이 스크립트는 그 계기를 만든다.

무엇을 하나
-----------
공개키로 `api.get_data_freshness()` 를 한 번 불러, `next_expected` 가 **한국 날짜의 오늘보다
앞선** 줄을 고른다(같은 날은 아직 안 지난 것이다 — 예정일은 "그날 말일까지"라는 뜻이라).
  · `next_expected` 가 null 인 줄(주기가 없는 자료 여섯 줄)은 건너뛴다 — 없는 주기를 두고
    "늦었다"고 하면 거짓 신호다(서버 함수가 null 을 주는 이유와 같다).
  · ⛔ 아래 셋은 "지난 것 없음"이 아니라 **조회 실패**다. 어느 것이든 "없음"으로 끝내면
    그날부터 감시가 장님이 된 채 매주 초록불만 켠다.
      - **0줄** — 서버 함수는 자료가 비어도 열 줄을 늘 준다(빈 자료는 basis 가 null 인 줄로 남는다).
      - **예정일 있는 줄이 0개** — 서버 규칙이 깨져 전부 null 이 되면 판정할 것이 없다.
      - **null 도 날짜도 아닌 예정일** — 서버가 날짜 칸에 다른 모양을 주기 시작한 것이다.

지난 자료는 **하나에 이슈 하나**다. 제목은 `갱신 예정일이 지난 자료 — <자료 이름> (예정
YYYY-MM-DD)` 로, 매주 바뀌는 값(며칠 지났나·건수)을 넣지 않는다 — 그래야 하나를 적재해도
**남은 자료의 제목이 그대로**라 그쪽 이슈가 새로 열리지 않는다(워크플로가 열린 같은 제목을 본다).
자료별 제목·본문은 `data_freshness_issues/` 폴더에 `NN.title`·`NN.md` 쌍으로 쓴다.

⛔ 읽기만 한다 — 창고에 쓰지 않고, 적재도 안 한다(알리기만 한다. 형제 감시와 같은 원칙).

키가 필요하다
-------------
`SANGGA_SUPABASE_URL` · `SANGGA_SUPABASE_ANON_KEY` 두 값이 **있어야** 돈다. 비밀값은
아니다 — 이미 배포된 화면의 자바스크립트 묶음에 그대로 실려 있는 공개키다. 의견함 주간
알림(`feedback_digest.py`)과 **같은 변수·같은 호출 경로**를 쓴다. 내 PC 에서는 `.env` 를
자동으로 읽는다(feedback_digest 를 불러올 때 그쪽이 읽어 둔다).

쓰는 법
-------
    python scripts/check_data_freshness.py                     # 오늘(한국 날짜) 기준
    python scripts/check_data_freshness.py --today 2026-11-02  # 오늘을 밖에서 넣기(시험·되짚기용)

종료코드: 0 = 지난 줄 없음 / 1 = **지난 줄 있음** / 2 = 조회 실패 / 3 = 주소·공개키 없음 /
          4 = 조회는 됐는데 결과(화면·이슈 파일·GITHUB_OUTPUT)를 쓰다 실패.
  ↳ 1 과 2 를 가르는 이유: "자료가 늦었다"와 "확인을 못 했다"는 서로 다른 사건이다.
    한 코드로 뭉뚱그리면 창고가 죽은 주에 "자료가 늦었습니다"라는 엉뚱한 이슈가 열린다.
  ↳ ⛔ 조회 중 **어떤 예외든** 2 로 끝낸다. 잡지 못한 예외는 파이썬 기본값 1 로 끝나는데,
    그건 여기서 "지난 줄 있음"과 같은 숫자다(워크플로는 그 경우를 한 번 더 막는다).
  ↳ 3 을 따로 두는 이유: 설정이 빠진 것은 창고가 죽은 것과도 다르다 — 사람이 변수만
    넣으면 끝난다(워크플로는 이 경우를 앞 단계에서 먼저 가려 설정 안내 이슈를 연다).
  ↳ 4 를 따로 두는 이유: 이슈 파일을 다 쓴 뒤 GITHUB_OUTPUT 에서 죽으면 기본값 1 이 "지남"과
    겹치는데, 워크플로의 이슈 단계는 overdue 값이 없어 건너뛰어진다 — 그 주가 조용히 초록이 된다.

⚠️ 표준 라이브러리만 쓴다 — 워크플로에 설치 단계가 없다.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from zoneinfo import ZoneInfo

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# ⚠️ 호출은 의견함 주간 알림의 rpc() 를 그대로 쓴다 — `Content-Profile: api` 머리·재시도
#    표준(5번·지수 백오프·401/403/404 는 한 번만)을 여기서 다시 짜면 두 벌이 되고, 언젠가
#    한쪽만 고쳐진다. 불러오는 순간 그쪽이 `.env` 도 읽어 둔다(로컬 실행용).
import feedback_digest as fd  # noqa: E402

FRESHNESS_FN = "get_data_freshness"

# 이 DB 는 UTC 지만 예정일은 한국 달력으로 계산된 날짜다. 오늘도 한국 날짜로 잰다 —
# UTC 로 재면 한국 오전 0~9시에 하루 늦게 판정한다(서버 함수가 Asia/Seoul 로 자르는 것과 같은 이유).
KST = ZoneInfo("Asia/Seoul")

# 자료별 이슈 제목·본문을 두는 폴더(워크플로가 *.md 를 돌며 짝 *.title 을 읽는다).
ISSUE_DIR = "data_freshness_issues"

EXIT_OK = 0
EXIT_OVERDUE = 1
EXIT_LOOKUP_FAILED = 2
EXIT_NO_CREDENTIALS = 3
EXIT_OUTPUT_FAILED = 4

# 서버가 늘 주는 칸. 이 중 하나라도 없으면 함수 모양이 바뀐 것이다 — 조회 실패로 본다.
REQUIRED_KEYS = ("src", "basis_kind", "basis", "next_expected", "cadence")


# ── 순수 함수 (네트워크 없음 — 시험 대상) ─────────────────────────────────────


def today_kst(now: datetime.datetime | None = None) -> datetime.date:
    """한국 날짜의 오늘. `now` 를 넣으면 그 시각 기준(시험용 — 실제 시각에 기대지 않는다)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now.astimezone(KST).date()


def parse_date(value) -> datetime.date | None:
    """'2026-10-31' → date. null·모양 이상이면 None."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        return None


def unreadable_dates(rows) -> list:
    """`next_expected` 에 값은 있는데 날짜로 못 읽은 줄의 이름."""
    return [
        row.get("src") or "(이름 없음)"
        for row in rows
        if row.get("next_expected") is not None and parse_date(row.get("next_expected")) is None
    ]


def check_rows(result) -> list:
    """서버 응답이 판정할 수 있는 모양인지 본다. 아니면 CallFailed(= 조회 실패)."""
    if not isinstance(result, list):
        raise fd.CallFailed(f"{FRESHNESS_FN} 응답 모양이 예상과 다릅니다: {result!r}")
    if not result:
        raise fd.CallFailed(
            f"{FRESHNESS_FN} 가 0줄을 돌려줬습니다 — 정상이 아닙니다"
            "(이 함수는 자료가 비어도 줄을 늘 줍니다)."
        )
    for row in result:
        if not isinstance(row, dict) or any(k not in row for k in REQUIRED_KEYS):
            raise fd.CallFailed(f"{FRESHNESS_FN} 응답의 한 줄이 예상과 다릅니다: {row!r}")
    bad = unreadable_dates(result)
    if bad:
        raise fd.CallFailed(
            "다음 갱신 예정일이 null 도 날짜(YYYY-MM-DD)도 아닌 줄이 있습니다: {} — "
            "서버 함수가 날짜 칸에 다른 모양을 주기 시작했습니다.".format(", ".join(bad))
        )
    if not any(parse_date(r.get("next_expected")) for r in result):
        raise fd.CallFailed(
            f"{FRESHNESS_FN} 의 {len(result)}줄 모두 다음 갱신 예정일이 비어 있습니다 — "
            "예정 규칙이 깨졌을 수 있습니다(지금은 분기·월간·연 1회 자료에 날짜가 있어야 합니다)."
        )
    return result


def find_overdue(rows, today: datetime.date) -> list:
    """`next_expected` 가 오늘보다 **앞선** 줄만 고른다(같은 날은 아직 안 지남).

    돌려주는 것: `[{src, basis_kind, basis, next_expected, days_over}, ...]` — 서버 순서 그대로.
    """
    out = []
    for row in rows:
        expected = parse_date(row.get("next_expected"))
        if expected is None or not expected < today:
            continue
        out.append({
            "src": row.get("src") or "(이름 없음)",
            "basis_kind": row.get("basis_kind") or "기준",
            "basis": row.get("basis"),
            "next_expected": expected.isoformat(),
            "days_over": (today - expected).days,
        })
    return out


def build_issue_title(item) -> str:
    """자료 **하나**의 이슈 제목. 매주 바뀌는 값(며칠 지났나·건수)은 넣지 않는다.

    같은 자료가 같은 예정일로 밀려 있는 동안은 제목이 같아, 열린 이슈가 있으면 다시 안 열린다.
    다른 자료를 적재해도 이 제목은 안 바뀐다. 이 자료를 적재해 예정일이 바뀌면 그때 새 제목이 된다.
    ⓘ 자료 이름은 창고가 준다 — 줄바꿈·연속 공백은 한 칸으로 접어 제목이 한 줄로 남게 한다.
    """
    name = " ".join(str(item["src"]).split())
    return "갱신 예정일이 지난 자료 — {} (예정 {})".format(name, item["next_expected"])


def build_issue_body(item, today: datetime.date) -> str:
    """자료 하나의 이슈 본문 — 사람이 그대로 따라 할 수 있게."""
    basis = item["basis"] if item["basis"] is not None else "(자료 없음)"
    lines = [
        "화면 아래 **\"이 자료는 언제 것인가\"** 표에서, 다음 갱신 예정일이 지났는데 "
        "아직 옛 자료입니다.",
        "",
        "| 자료 | 지금 기준 | 다음 갱신 예정 | 지난 날수 |",
        "|---|---|---|---|",
        "| {} | {} {} | {} | {}일 |".format(
            str(item["src"]).replace("|", "·"),
            item["basis_kind"],
            basis,
            item["next_expected"],
            item["days_over"],
        ),
        "",
        "판정 기준: 다음 갱신 예정일 < 오늘(한국 날짜 {}). 지난 날수는 이 이슈를 연 날 기준입니다."
        .format(today.isoformat()),
        "",
        "## 할 일",
        "",
        "**포털에 새 판이 떴는지 확인 → 떴으면 적재**합니다. 받기·적재 명령은 "
        "`CLAUDE.md` 의 명령 표에 있습니다. 적재한 뒤에는 늘 하던 대로:",
        "",
        "```powershell",
        r"cd D:\sangga",
        "python scripts/post_load.py           # 요약표 갱신",
        "python scripts/post_load.py --check   # 권한·신선도 점검",
        "python scripts/check_data_freshness.py   # 이 감시를 내 PC에서 다시 — 이 자료가 목록에서 빠지면 끝",
        "```",
        "",
        "- **적재해 해결했으면 이 이슈를 닫습니다.** 아직 밀린 채 닫으면 다음 주에 다시 열립니다.",
        "- **아직 안 떴으면** 이 이슈를 열어 둔 채로 두세요. 열려 있는 동안은 같은 알림이 "
        "매주 새로 쌓이지 않습니다.",
        "- **포털이 원래 예정보다 늦게 올리는 자료**라면 적재할 일이 아니라 예정 규칙"
        "(`get_data_freshness`)을 고칠 일입니다 — 건축 인허가가 그 예였습니다"
        "(마이그레이션 2026-10-01a).",
        "",
        "*(이 이슈는 지난 날짜 주간 감시 워크플로가 자동으로 열었습니다. 지난 자료 하나에 이슈 "
        "하나씩 열립니다. 읽기만 하고 창고에는 아무것도 쓰지 않습니다.)*",
    ]
    return "\n".join(lines) + "\n"


# ── 출력 ──────────────────────────────────────────────────────────────────────


def write_issue_files(overdue, today: datetime.date, folder: str = ISSUE_DIR) -> list:
    """자료별 `NN.title`·`NN.md` 를 폴더에 쓴다. 지난 실행이 남긴 쌍은 먼저 지운다.

    ⓘ 이 폴더는 이 스크립트 전용이다(.gitignore). 남은 쌍을 안 지우면 로컬에서 거듭 돌릴 때
       이미 해결된 자료의 본문이 섞인다.
    """
    os.makedirs(folder, exist_ok=True)
    for name in os.listdir(folder):
        if name.endswith((".title", ".md")):
            os.remove(os.path.join(folder, name))
    written = []
    for i, item in enumerate(overdue, start=1):
        stem = os.path.join(folder, "{:02d}".format(i))
        with open(stem + ".title", "w", encoding="utf-8") as f:
            f.write(build_issue_title(item) + "\n")
        with open(stem + ".md", "w", encoding="utf-8") as f:
            f.write(build_issue_body(item, today))
        written.append(stem)
    return written


def write_github_output(overdue) -> bool:
    """GitHub Actions 다음 단계가 읽을 값을 GITHUB_OUTPUT 에 쓴다. 로컬에서는 아무 일도 안 한다.

    ⓘ 자료 이름(창고가 준 값)은 여기 싣지 않는다 — 워크플로가 `${{ }}` 로 run 에 끼우면 주입
       통로가 된다. 이름은 폴더의 파일로만 넘긴다.
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return False
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("overdue={}\n".format("true" if overdue else "false"))
        fh.write("count={}\n".format(len(overdue)))
    return True


def fetch_rows(base_url: str, anon_key: str, sleep=None) -> list:
    """신선도 표를 받아 온다. 모양이 이상하거나 0줄이면 CallFailed."""
    result = fd.rpc(base_url, anon_key, FRESHNESS_FN, {}, sleep=sleep or time.sleep)
    return check_rows(result)


def report(rows, overdue, today: datetime.date) -> None:
    """사람이 읽는 결과 화면."""
    with_date = sum(1 for r in rows if parse_date(r.get("next_expected")) is not None)

    print("=" * 66)
    print("자료 신선도 — 다음 갱신 예정일이 지났나")
    print("=" * 66)
    print(f"  오늘(한국 날짜)          : {today.isoformat()}")
    print(f"  받은 줄                  : {len(rows)}줄 (예정일 있는 줄 {with_date})")
    if overdue:
        print(f"  ★ 예정일이 지난 줄       : {len(overdue)}줄")
        for o in overdue:
            print("      {} — {} {} · 예정 {} · {}일 지남".format(
                o["src"], o["basis_kind"], o["basis"], o["next_expected"], o["days_over"]))
        print()
        print("  → 포털에 새 판이 떴는지 확인 → 떴으면 적재")
    else:
        print("  예정일이 지난 줄         : 없음")
    print("=" * 66)


def main(argv=None) -> int:
    # cp949 콘솔에서 한글·특수문자(—) 출력이 깨지거나 죽지 않게 — 형제 감시와 같은 처방.
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="'다음 갱신 예정'이 지났는데 아직 옛 자료인 줄이 있나 (읽기만)."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("SANGGA_SUPABASE_URL"),
        help="Supabase 프로젝트 URL (기본값: 환경변수 SANGGA_SUPABASE_URL)",
    )
    parser.add_argument(
        "--anon-key",
        default=os.environ.get("SANGGA_SUPABASE_ANON_KEY"),
        help="Supabase 공개(anon) 키 (기본값: 환경변수 SANGGA_SUPABASE_ANON_KEY)",
    )
    parser.add_argument(
        "--today",
        type=datetime.date.fromisoformat,
        default=None,
        help="오늘로 칠 날짜 YYYY-MM-DD (기본값: 한국 날짜의 오늘)",
    )
    args = parser.parse_args(argv)

    if not args.url or not args.anon_key:
        print("SANGGA_SUPABASE_URL / SANGGA_SUPABASE_ANON_KEY 가 필요합니다 — 이 감시는 "
              "공개키로 창고에 묻습니다(내 PC 는 .env, Actions 는 저장소 Variables).")
        return EXIT_NO_CREDENTIALS

    # ⛔ **어떤 예외든** 조회 실패(2)다 — CallFailed 만 잡으면 IncompleteRead·UnicodeDecodeError·
    #    잘못된 주소의 ValueError 같은 것이 파이썬 기본값 1(= "지난 줄 있음")로 새어 나간다.
    #    형제 check_lh_notices.py 와 같은 처방. 오늘 날짜를 정하는 것도 여기 안에 둔다 —
    #    try 밖에서 죽으면 같은 1 로 샌다.
    try:
        today = args.today or today_kst()
        rows = fetch_rows(args.url.rstrip("/"), args.anon_key)
    except Exception as ex:
        print(f"[실패] {type(ex).__name__}: {ex}")
        print("확인을 못 했습니다 — '지난 것 없음'이 아닙니다.")
        return EXIT_LOOKUP_FAILED

    # ⛔ 판정에서 난 예외도 2 다. 놓치면 파이썬 기본값 1 = "지난 줄 있음"으로 읽히는데 이슈
    #    파일도 overdue 기록도 없다(형제 LH 공고 감시·하트비트와 같은 처방).
    try:
        overdue = find_overdue(rows, today)
    except Exception as ex:
        print(f"[실패] 판정하는 중 {type(ex).__name__}: {ex} — 응답 모양이 바뀌었을 수 있습니다.")
        print("확인을 못 했습니다 — '지난 것 없음'이 아닙니다.")
        return EXIT_LOOKUP_FAILED

    # ⛔ 조회 **뒤**(화면 출력·이슈 파일·GITHUB_OUTPUT)에서 난 예외도 잡는다. 놓치면 파이썬
    #    기본값 1 = "지난 줄 있음"과 겹친다 — 이슈 파일을 다 쓴 뒤 GITHUB_OUTPUT 에서 죽으면
    #    워크플로가 1 + 이슈 파일만 보고 통과시키는데 overdue 값이 없어 이슈 단계가 건너뛰어져
    #    그 주가 조용히 초록이 된다. 그래서 따로 4 로 끝내 실패 알림으로 보낸다.
    try:
        report(rows, overdue, today)
        write_issue_files(overdue, today)
        write_github_output(overdue)
    except Exception as ex:
        print(f"[실패] 결과를 쓰는 중 {type(ex).__name__}: {ex} — 알림이 안 나갔을 수 있습니다.")
        return EXIT_OUTPUT_FAILED
    return EXIT_OVERDUE if overdue else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
