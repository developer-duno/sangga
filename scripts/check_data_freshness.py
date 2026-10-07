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
      - **0줄** — 서버 함수는 자료가 비어도 열한 줄을 늘 준다(2026-10-05b 부터 — 서울 개업·폐업 · 빈 자료는 basis 가 null 인 줄로 남는다).
      - **예정일 있는 줄이 0개** — 서버 규칙이 깨져 전부 null 이 되면 판정할 것이 없다.
      - **null 도 날짜도 아닌 예정일** — 서버가 날짜 칸에 다른 모양을 주기 시작한 것이다.

지난 자료는 **하나에 이슈 하나**다. 제목은 `갱신 예정일이 지난 자료 — <자료 이름> (예정
YYYY-MM-DD)` 로, 매주 바뀌는 값(며칠 지났나·건수)을 넣지 않는다 — 그래야 하나를 적재해도
**남은 자료의 제목이 그대로**라 그쪽 이슈가 새로 열리지 않는다(워크플로가 열린 같은 제목을 본다).
자료별 제목·본문은 `data_freshness_issues/` 폴더에 `NN.title`·`NN.md` 쌍으로 쓴다.

화면 분기 섞임도 본다(결정 0035 · 2026-10-07 (2)) — 공개 뷰 `api.v_coverage_stats` 의 snapshot_ym
(요약표를 구울 때의 분기)을 읽어, 위 표 '점포·업종 (상권정보)' 줄의 기준 분기(표지 published_ym)와
**다르면** 고정 제목 `화면 분기가 섞였습니다 — 점포·업종 (상권정보)` 이슈 한 쌍을 같은 폴더에 더 쓴다
(표지를 `--ym` 으로 되돌린 뒤 post_load 를 안 돌림(또는 요약표를 손으로 갱신함) — `post_load.py --check`
를 돌려야만 보이던 것. post_load 가 도중에 멈추는 것은 원인이 아니다 — 요약표 셋 굽기와 표지 올림이
한 트랜잭션이라 멈추면 통째로 되돌아간다). 뷰 조회 실패·0줄·그 줄이 없음은 조회 실패(2)다 — 단
그때도 예정일 지남 판정·이슈 파일·GITHUB_OUTPUT 은 그대로 쓰고 끝만 2 로 낸다(2026-10-07 (3) — 각주
뷰 하나가 죽은 주에 지남 이슈까지 막히지 않게). 신선도 함수 자체가 실패하면 둘 다 못 본다(2).

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

종료코드: 0 = 지난 줄 없음 / 1 = **지난 줄 있음 또는 화면 분기 섞임** / 2 = 조회 실패 / 3 = 주소·공개키 없음 /
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
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
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

# ── 화면 분기 섞임 (결정 0035 · 2026-10-07 (2)) ──
# 신선도 '점포·업종 (상권정보)' 줄의 basis = 표지 published_ym(화면이 보는 분기). 각주 뷰
# api.v_coverage_stats 의 snapshot_ym = 요약표를 구울 때의 분기(loaded_ym). 둘이 다르면 화면 일부
# (가게 이름 검색·각주·업종 카드)만 다른 분기를 말하는 섞인 상태다 — 표지를 `--ym` 으로 되돌린 뒤
# post_load 를 안 돌림(또는 요약표를 손으로 갱신함). post_load 가 멈추면 한 트랜잭션이라 통째로 되돌아가
# 섞임을 못 만든다.
STORE_SRC = "점포·업종 (상권정보)"
COVERAGE_VIEW = "v_coverage_stats"
MIXED_TITLE = "화면 분기가 섞였습니다 — " + STORE_SRC
YM_RE = re.compile(r"^\d{6}$")


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


def check_coverage(result) -> str:
    """각주 뷰 응답 → 분기(YYYYMM). 정확히 한 줄 · snapshot_ym 여섯 자리가 아니면 CallFailed(= 조회 실패).

    ⓘ 0줄도 조회 실패다 — 요약표가 비면 화면 각주가 조용히 사라진 것이라 '섞이지 않음'으로 넘기지 않는다.
    """
    if not (isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict)):
        raise fd.CallFailed(f"{COVERAGE_VIEW} 응답 모양이 예상과 다릅니다(한 줄이어야 합니다): {result!r}")
    ym = str(result[0].get("snapshot_ym") or "").strip()
    if not YM_RE.match(ym):
        raise fd.CallFailed(f"{COVERAGE_VIEW} 의 snapshot_ym 이 YYYYMM 이 아닙니다: {result!r}")
    return ym


def find_mixed(rows, coverage_ym: str) -> dict | None:
    """신선도 '점포·업종 (상권정보)' 줄의 기준 분기(표지 published)와 각주 분기가 다르면 그 둘을 돌려준다.

    같으면 None. ⛔ 그 줄이 없으면 판정할 수 없다 — '섞이지 않음'이 아니라 CallFailed(조회 실패):
       서버 줄 이름이 바뀌었는데 None 으로 넘기면 이 감시가 그날부터 조용히 꺼진다.
    """
    store = [r for r in rows if r.get("src") == STORE_SRC]
    if len(store) != 1:
        raise fd.CallFailed(
            f"신선도 표에 '{STORE_SRC}' 줄이 {len(store)}개입니다 — 정확히 하나여야 화면 분기를 대조합니다."
        )
    published = store[0].get("basis")
    published = str(published).strip() if published is not None else None
    if published == coverage_ym:
        return None
    return {"src": STORE_SRC, "published": published, "coverage": coverage_ym}


def build_mixed_body(mixed) -> str:
    """화면 분기 섞임 이슈 본문 — 두 분기 값과 고치는 절차."""
    lines = [
        "화면이 보는 점포 분기(표지)와 요약표(가게 이름 검색·각주·업종 카드)의 분기가 **다릅니다** — "
        "화면 일부만 다른 분기를 말하는 섞인 상태입니다.",
        "",
        "| 자리 | 분기 |",
        "|---|---|",
        "| 화면 기준 = 표지 보여 주는 분기 (신선도 표 '{}' 줄) | {} |".format(
            STORE_SRC, mixed["published"] if mixed["published"] is not None else "(자료 없음)"),
        "| 각주 뷰 `api.{}` (요약표를 구울 때의 분기) | {} |".format(COVERAGE_VIEW, mixed["coverage"]),
        "",
        "## 왜 생기나",
        "",
        "- 표지를 `publish_snapshot.py --ym` 으로 되돌린 뒤 `post_load.py` 를 안 돌렸습니다"
        "(또는 요약표를 손으로 갱신했습니다).",
        "- `post_load.py` 가 도중에 멈춘 것은 원인이 아닙니다 — 요약표 셋 굽기와 표지 올림이 한 트랜잭션이라 "
        "멈추면 통째로 되돌아갑니다.",
        "- 일부러 되돌려 둔 상태(`--ym`)라면 `post_load.py` 의 [경고] + exit 1 은 정상입니다 — "
        "`--loaded` 로 새 분기를 다시 올리지 마세요.",
        "",
        "## 할 일",
        "",
        "```powershell",
        r"cd D:\sangga",
        "python scripts/publish_snapshot.py --show   # 표지 두 칸 · 요약표 셋의 분기를 본다",
        "python scripts/post_load.py                  # 요약표를 표지 분기로 다시 굽는다",
        "python scripts/post_load.py --check",
        "python scripts/check_data_freshness.py       # 이 감시를 내 PC에서 다시 — 섞임이 사라지면 끝",
        "```",
        "",
        "- **고쳤으면 이 이슈를 닫습니다.** 섞인 채 닫으면 다음 주에 다시 열립니다.",
        "",
        "*(이 이슈는 지난 날짜 주간 감시 워크플로가 자동으로 열었습니다. 읽기만 하고 창고에는 "
        "아무것도 쓰지 않습니다.)*",
    ]
    return "\n".join(lines) + "\n"


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


def write_issue_files(overdue, today: datetime.date, folder: str = ISSUE_DIR, mixed=None) -> list:
    """자료별 `NN.title`·`NN.md` 를 폴더에 쓴다. 지난 실행이 남긴 쌍은 먼저 지운다.

    화면 분기가 섞였으면(mixed) 그 이슈 한 쌍을 지난 자료 뒤에 더 쓴다 — 제목은 고정(MIXED_TITLE)이라
    워크플로가 열린 같은 제목을 보고 건너뛴다(워크플로는 폴더의 쌍을 그대로 돈다 — 고칠 것 0).
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
    if mixed:
        stem = os.path.join(folder, "{:02d}".format(len(overdue) + 1))
        with open(stem + ".title", "w", encoding="utf-8") as f:
            f.write(MIXED_TITLE + "\n")
        with open(stem + ".md", "w", encoding="utf-8") as f:
            f.write(build_mixed_body(mixed))
        written.append(stem)
    return written


def write_github_output(overdue, mixed=None) -> bool:
    """GitHub Actions 다음 단계가 읽을 값을 GITHUB_OUTPUT 에 쓴다. 로컬에서는 아무 일도 안 한다.

    `overdue=true` 는 "열 이슈 파일이 있다"는 뜻이다 — 지난 자료든 화면 분기 섞임이든(워크플로의
    이슈 단계가 이 값 하나로 폴더를 돈다 · 2026-10-07 (2)). count = 이슈 파일 쌍의 수.
    ⓘ 자료 이름(창고가 준 값)은 여기 싣지 않는다 — 워크플로가 `${{ }}` 로 run 에 끼우면 주입
       통로가 된다. 이름은 폴더의 파일로만 넘긴다.
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return False
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("overdue={}\n".format("true" if (overdue or mixed) else "false"))
        fh.write("count={}\n".format(len(overdue) + (1 if mixed else 0)))
    return True


def fetch_rows(base_url: str, anon_key: str, sleep=None) -> list:
    """신선도 표를 받아 온다. 모양이 이상하거나 0줄이면 CallFailed."""
    result = fd.rpc(base_url, anon_key, FRESHNESS_FN, {}, sleep=sleep or time.sleep)
    return check_rows(result)


def fetch_coverage_ym(base_url: str, anon_key: str, sleep=None) -> str:
    """공개 뷰 `api.v_coverage_stats` 의 snapshot_ym 하나를 읽는다(GET · `Accept-Profile: api`).

    재시도 표준은 의견함 rpc() 와 같다(같은 상수 — 5번 · 지수 백오프 · 401/403/404 는 한 번만).
    뷰는 RPC 가 아니라 GET 이라 `Content-Profile` 이 아니라 `Accept-Profile` 로 스키마를 고른다
    (PostgREST — 옛 문(public)은 노출 스키마에서 빠져 있다). 실패·모양 이상은 CallFailed.
    """
    sleep = sleep or time.sleep
    url = f"{base_url}/rest/v1/{COVERAGE_VIEW}?select=snapshot_ym"
    last = ""
    for attempt in range(1, fd.RETRY_COUNT + 1):
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "apikey": anon_key,
                "Authorization": f"Bearer {anon_key}",
                "Accept-Profile": "api",
                "User-Agent": "sangga-data-freshness",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=fd.TIMEOUT_S) as resp:  # noqa: S310
                return check_coverage(json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as ex:
            detail = ex.read().decode("utf-8", errors="replace") if ex.fp else ""
            last = f"HTTP {ex.code} — {detail}".strip()
            if ex.code in fd.NO_RETRY_HTTP_CODES or attempt == fd.RETRY_COUNT:
                raise fd.CallFailed(f"{COVERAGE_VIEW} 조회에 실패했습니다: {last}") from ex
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            last = f"연결 실패({ex})"
            if attempt == fd.RETRY_COUNT:
                raise fd.CallFailed(f"{COVERAGE_VIEW} 조회에 실패했습니다: {last}") from ex
        except json.JSONDecodeError as ex:
            last = f"응답이 JSON 이 아닙니다({ex})"
            if attempt == fd.RETRY_COUNT:
                raise fd.CallFailed(f"{COVERAGE_VIEW} 조회에 실패했습니다: {last}") from ex
        wait = fd.RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
        print(f"  · {COVERAGE_VIEW} {attempt}번째 실패({last}) — {wait}초 뒤 다시 시도합니다")
        sleep(wait)
    raise RuntimeError("재시도 루프가 한 번도 돌지 않았습니다 (RETRY_COUNT 확인).")


def report(rows, overdue, today: datetime.date, mixed=None, mixed_unknown: bool = False) -> None:
    """사람이 읽는 결과 화면.

    mixed_unknown = 화면 분기 대조(각주 뷰)를 못 한 주 — 그때 '섞임 없음'이라고 말하면 거짓이다.
    """
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
    if mixed:
        print("  ★ 화면 분기가 섞였습니다 : 화면 기준(표지) {} · 각주 {}".format(
            mixed["published"] if mixed["published"] is not None else "(자료 없음)", mixed["coverage"]))
        print("  → 화면 일부(가게 이름 검색·각주·업종 카드)가 다른 분기 — 표지를 되돌린 뒤 post_load 를 "
              "안 돌림(또는 요약표를 손으로 갱신함) → python scripts/publish_snapshot.py --show 로 보고 "
              "python scripts/post_load.py 뒤 python scripts/post_load.py --check")
    elif mixed_unknown:
        print("  화면 분기 섞임           : 확인 못 함(각주 뷰 조회·대조 실패 — '없음' 이 아닙니다)")
    else:
        print("  화면 분기 섞임           : 없음")
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
    # ⓘ 화면 분기 대조(각주 뷰 조회 `fetch_coverage_ym` · `find_mixed`)만 실패하면 **섞임만 '확인 못 함'**
    #    으로 두고 지남 판정·이슈 파일·GITHUB_OUTPUT 은 그대로 한 뒤 끝을 2 로 낸다(2026-10-07 (3)) —
    #    예전엔 각주 뷰 하나가 죽은 주에 '예정일 지남' 이슈까지 통째로 안 열렸다. 안쪽 처리부도
    #    **어떤 예외든**(Exception 전체) 받는다.
    mixed_unknown = False
    try:
        try:
            coverage_ym = fetch_coverage_ym(args.url.rstrip("/"), args.anon_key)
            mixed = find_mixed(rows, coverage_ym)
        except Exception as ex:
            print(f"[실패] 화면 분기 대조(각주 뷰) {type(ex).__name__}: {ex}")
            print("화면 분기 섞임은 확인을 못 했습니다 — '섞이지 않음'이 아닙니다. 예정일 지남은 그대로 봅니다.")
            mixed, mixed_unknown = None, True
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
        report(rows, overdue, today, mixed, mixed_unknown=mixed_unknown)
        write_issue_files(overdue, today, mixed=mixed)
        write_github_output(overdue, mixed)
    except Exception as ex:
        print(f"[실패] 결과를 쓰는 중 {type(ex).__name__}: {ex} — 알림이 안 나갔을 수 있습니다.")
        return EXIT_OUTPUT_FAILED
    # 섞임 대조만 못 한 주 — 지남 이슈 파일·기록은 위에서 다 썼다. 워크플로가 rc 2 + 그 둘을 보고
    # 지남 이슈는 열고 이 실패는 실패 이슈로 알린다(결과 쓰기 실패 4 가 이것보다 먼저다).
    if mixed_unknown:
        return EXIT_LOOKUP_FAILED
    return EXIT_OVERDUE if (overdue or mixed) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
