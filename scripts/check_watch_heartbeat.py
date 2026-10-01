# -*- coding: utf-8 -*-
"""
감시 워크플로우가 **아직 살아서 돌고 있는지** 확인한다 (하트비트).

왜 이게 필요한가
----------------
예약 6종(분기 스냅샷·상권 원천·라이브 생존·의견함 주간 알림·LH 공고·지난 날짜)은 "돌았는데
실패"는 이슈로 시끄럽게 알린다. 그런데 **예약이 아예 안 도는 경우**는 실패조차 없다 —
실행이 없으니 알릴 것도 없다. 그 경로가 둘이다.

  ① 공개 저장소는 **60일간 활동이 없으면 예약 실행이 자동으로 멈춘다**.
  ② GitHub 부하가 높으면 예약된 실행이 **큐에서 조용히 드롭**된다.

둘 다 에러가 아니라 **아무 일도 안 일어나는 것**이라, Actions 탭을 사람이 들여다보지
않는 한 영영 모른다. 그 사이 새 분기 스냅샷은 포털에서 내려가고(절대 규칙 6), 화면의
상권 경계는 조용히 낡는다.

무엇을 보나
-----------
GitHub REST API 로 그 워크플로우의 **가장 최근 성공 실행 시각**을 읽어, 기준일(기본
8일 = 주 1회 예약 + 하루 여유)보다 오래됐으면 경고하고 종료코드 1 로 끝난다.

  ⚠️ "성공한 실행"에는 손으로 돌린 것(workflow_dispatch)도 포함된다. 예약이 죽었어도
     사람이 한 번 손으로 돌리면 그 주는 살아 있는 것으로 보인다 — 그래도 **점검 자체는
     실제로 일어났으므로** 조용한 낡음은 없다. 그래서 일부러 실행 종류를 가리지 않는다.

  ⛔ **멈춤으로 나오면 다른 방식으로 한 번 더 묻는다**(거름망 없이 최근 실행 20건 → 그중
     마지막 성공). 2026-10-01 GitHub 가 한 번 옛 답(09-17)을 줘 잘 도는 라이브 감시에
     헛경보(#177)가 열렸다. 재확인이 실패하면 처음 판정(멈춤)을 그대로 둔다 — 알림이
     사라지는 쪽보다 시끄러운 쪽이 낫다. 멈춤이 없는 평소에는 추가 호출이 없다.

  ⛔ **갓 만든 워크플로는 기록이 없는 게 정상이다.** 주 1회 예약을 금요일에 머지하면
     첫 예약 슬롯(월요일)이 오기 전까지 성공 기록이 0건인데, 그걸 "멈췄다"로 읽으면
     태어나자마자 부고가 뜬다(2026-08-28 LH 공고 감시가 실제로 그랬다 — 이슈 #98).
     그래서 기록이 없을 때는 **워크플로를 언제 만들었는지**를 한 번 더 묻고, 만든 지
     그 워크플로의 기준일이 안 지났으면 유예한다. 반대로 만든 지 기준일을 넘겼는데도
     기록이 0건이면 그건 진짜 고장이다(cron 오타 등) — 그때는 지금처럼 알린다.

이 판정을 누가 쓰나 (상호 감시)
-------------------------------
예약들이 **서로를 본다.** 자기 일이 끝난 뒤 나머지의 마지막 성공 나이를 재고, 오래됐으면
이슈를 연다. 하나라도 예약이 살아 있는 한 다른 것의 죽음은 그 주기 안에 이슈로 뜬다.
전부 죽는 경우만 남는데, 그건 사람이 내 PC 에서 이 명령을 직접 돌려 잡는다:

    python scripts/check_watch_heartbeat.py

왜 requests 를 안 쓰나
----------------------
형제 감시(`check_new_sangkwon_quarter.py` · `check_district_source_update.py`)와 같은
원칙이다 — CI 워크플로우에 설치 단계를 두지 않는다(비밀값 0개 + 설치 0개). 러너에는
requests 가 없으므로 표준 라이브러리(urllib)만 쓴다.

토큰은 필요한가
---------------
공개 저장소라 **없어도 읽힌다**(내 PC 에서 그냥 돌려도 된다). 다만 Actions 러너는 IP 를
수많은 작업과 나눠 쓰기 때문에 무인증 한도(시간당 60회)가 남의 호출로 이미 소진돼
있을 수 있다. 그래서 `GITHUB_TOKEN` 환경변수가 있으면 붙여 쓴다(워크플로우가 기본
토큰을 넘겨준다 — 새 비밀값은 여전히 0개다).

쓰는 법
-------
    python scripts/check_watch_heartbeat.py                              # 예약 6종 전부
    python scripts/check_watch_heartbeat.py --workflow district-source-watch.yml
    python scripts/check_watch_heartbeat.py --max-age-days 15 --json

종료코드: 0 = 전부 최근에 돌았음 / 1 = 오래된 것이 있음 / 2 = 조회·판정 실패 /
          4 = 조회는 됐는데 결과(화면·--json·이슈 본문 파일·GITHUB_OUTPUT)를 쓰다 실패.
  ↳ 1 과 2 를 가르는 이유: "감시가 멈췄다"와 "내가 확인을 못 했다"는 서로 다른 사건이라
    한 코드로 뭉뚱그리면 워크플로우가 엉뚱한 이슈를 연다.
  ↳ 4 를 따로 두는 이유: 결과를 쓰다 죽으면 파이썬 기본값 1 = "멈춘 것이 있음"과 겹친다.
    워크플로는 1 을 통과시키는데 stale 기록이 없으면 이슈 단계가 건너뛰어져 아무 알림이 없다.
    판정에서 난 예외(응답 모양이 바뀐 것 등)도 같은 이유로 2 로 잡는다(형제 LH·지난 날짜 감시와 같다).
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

# ── 대상 ──────────────────────────────────────────────────────────────────────

# ⚠️ .github/workflows/ 의 실제 파일명이다. 파일 이름을 바꾸면 여기도 같이 고칠 것
#    (테스트가 파일 존재 여부로 붙잡는다).
QUARTERLY_WATCH = "sangkwon-quarterly-watch.yml"
DISTRICT_WATCH = "district-source-watch.yml"
LIVE_HEALTH_WATCH = "live-health-watch.yml"
FEEDBACK_DIGEST = "feedback-digest.yml"
LH_NOTICE_WATCH = "lh-notice-watch.yml"
DATA_FRESHNESS_WATCH = "data-freshness-watch.yml"

# 아무것도 안 주면 예약 6종을 다 본다(사람이 내 PC 에서 돌릴 때의 기본값).
DEFAULT_WORKFLOWS = (
    QUARTERLY_WATCH, DISTRICT_WATCH, LIVE_HEALTH_WATCH, FEEDBACK_DIGEST, LH_NOTICE_WATCH,
    DATA_FRESHNESS_WATCH,
)

# 화면·이슈 제목에 쓸 짧은 이름표
WORKFLOW_LABELS = {
    QUARTERLY_WATCH: "분기 스냅샷 감시",
    DISTRICT_WATCH: "상권 원천 감시",
    LIVE_HEALTH_WATCH: "라이브 생존 감시",
    FEEDBACK_DIGEST: "의견함 주간 알림",
    LH_NOTICE_WATCH: "LH 공고 감시",
    DATA_FRESHNESS_WATCH: "지난 날짜 감시",
}

# 분기·상권 감시는 **주 1회**(월요일) 예약이다. 8일이면 한 번을 통째로 걸러야 걸린다 —
# 하루치 여유는 큐가 조금 밀리는 정상 상황을 헛알림으로 만들지 않기 위한 것이다.
DEFAULT_MAX_AGE_DAYS = 8

# ⛔ **주기가 다른 감시는 기준도 달라야 한다.** 라이브 생존 감시는 6시간마다 도는데
#    거기에 8일 기준을 쓰면, 그것이 죽어 **라이브가 무너져도 일주일을 모른다** — 감시의
#    감시가 감시보다 굼떠서 아무 뜻이 없어지는 상태다(2026-08-24 적대검증 지적).
#    하루면 정상 실행 네 번을 통째로 걸러야 걸리므로 큐가 밀리는 정도로는 안 울린다.
WORKFLOW_MAX_AGE_DAYS = {
    LIVE_HEALTH_WATCH: 1.0,
}


def max_age_for(workflow_file, fallback=DEFAULT_MAX_AGE_DAYS):
    """이 워크플로우에 적용할 기준(일).

    ⚠️ 사람이 `--max-age-days` 로 더 **짧게** 주면 그것을 따르고, 더 **길게** 줘도 여기
       적힌 짧은 기준은 그대로 지킨다(min). 놓치는 쪽보다 시끄러운 쪽이 낫다.
    """
    return min(fallback, WORKFLOW_MAX_AGE_DAYS.get(workflow_file, fallback))

REPO = "developer-duno/sangga"
API_BASE = "https://api.github.com"

ISSUE_BODY_FILE = "watch_heartbeat_issue.md"

# 조회는 됐는데 결과를 쓰다 죽음 — 1(멈춘 것이 있음)과 겹치지 않게 따로 둔다(머리말 참조).
EXIT_OUTPUT_FAILED = 4

USER_AGENT = "sangga-watch-heartbeat"

TIMEOUT_SEC = 30
RETRY_COUNT = 3  # 최초 시도 포함
RETRY_BACKOFF_SEC = 5  # 5초 → 10초 (2배씩)

# 다시 물어봐도 답이 같은 실패 — 재시도는 15초를 버리기만 한다.
#   401 인증 실패 · 403 권한 회수(actions: read 누락) · 404 워크플로우 파일명 드리프트 ·
#   422 요청이 틀림. 전부 **사람이 고쳐야** 풀리는 것들이다.
# 반대로 타임아웃·연결 끊김·5xx 는 다음 시도에 풀릴 수 있으므로 재시도한다.
NO_RETRY_HTTP_CODES = frozenset({401, 403, 404, 422})

UTC = datetime.timezone.utc


# ── 순수 함수 (네트워크 없음 — 테스트 대상) ───────────────────────────────────


def label_of(workflow_file):
    """이름표. 모르는 파일이면 파일명을 그대로 쓴다."""
    return WORKFLOW_LABELS.get(workflow_file, workflow_file)


def parse_iso_utc(text):
    """GitHub 가 주는 시각(`2026-08-17T00:31:12Z`)을 UTC datetime 으로 바꾼다."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("시각이 비어 있습니다.")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError("시각을 읽을 수 없습니다: {!r}".format(text))
    if dt.tzinfo is None:
        # GitHub 은 항상 Z 를 붙이지만, 형식이 바뀌어도 로컬시각으로 오해하지 않는다.
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_latest_success(payload):
    """runs 응답에서 **가장 최근 성공 실행의 시각**을 뽑는다.

    성공한 실행이 한 번도 없으면 None(= "언제 돌았는지 모른다"). 응답 모양이 예상과
    다르면 ValueError — 조용히 None 을 돌려주면 "한 번도 안 돌았다"와 구분이 안 돼
    감시가 장님이 된 채 헛알림만 낸다.
    """
    if not isinstance(payload, dict):
        raise ValueError("GitHub 응답이 객체가 아닙니다 — API 형식이 바뀌었을 수 있습니다.")
    runs = payload.get("workflow_runs")
    if runs is None:
        raise ValueError(
            "GitHub 응답에 workflow_runs 칸이 없습니다 — "
            "워크플로우 파일명이 틀렸거나 API 형식이 바뀌었을 수 있습니다."
        )
    if not isinstance(runs, list):
        raise ValueError("workflow_runs 가 목록이 아닙니다 — API 형식이 바뀌었을 수 있습니다.")
    if not runs:
        return None
    return _run_time(runs[0])


def _run_time(run):
    """실행 기록 한 건의 시각(UTC). `parse_latest_success`·`parse_latest_success_among` 공용."""
    if not isinstance(run, dict):
        raise ValueError("실행 기록이 객체가 아닙니다 — API 형식이 바뀌었을 수 있습니다.")
    # run_started_at 이 "실제로 돌기 시작한 시각"이라 하트비트에 가장 맞다.
    # 옛 실행 기록에는 없을 수 있어 created_at 으로 물러선다.
    stamp = run.get("run_started_at") or run.get("created_at")
    if not stamp:
        raise ValueError("실행 기록에 시각 칸이 없습니다 — API 형식이 바뀌었을 수 있습니다.")
    return parse_iso_utc(stamp)


def parse_latest_success_among(payload):
    """상태 거름망 **없이** 받은 최근 실행 목록에서 `conclusion == "success"` 중 가장 최근 시각.

    재확인용이다(`recheck_stale` 참조). 성공이 하나도 없으면 None, 모양이 이상하면 ValueError.
    목록 순서에 기대지 않고 가장 늦은 시각을 고른다.
    """
    if not isinstance(payload, dict):
        raise ValueError("GitHub 응답이 객체가 아닙니다 — API 형식이 바뀌었을 수 있습니다.")
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("workflow_runs 가 목록이 아닙니다 — API 형식이 바뀌었을 수 있습니다.")
    times = [
        _run_time(run) for run in runs
        if isinstance(run, dict) and run.get("conclusion") == "success"
    ]
    return max(times) if times else None


def parse_created_at(payload):
    """워크플로우 메타 응답에서 **그것을 만든 시각**을 뽑는다.

    ⚠️ 이 응답의 시각에는 밀리초가 붙는다(`2026-08-28T05:27:50.000Z` — 라이브 실측).
       실행 기록 쪽(`run_started_at`)에는 안 붙어서 형식이 서로 다르다.
    """
    if not isinstance(payload, dict):
        raise ValueError("GitHub 응답이 객체가 아닙니다 — API 형식이 바뀌었을 수 있습니다.")
    stamp = payload.get("created_at")
    if not stamp:
        raise ValueError(
            "워크플로우 메타에 created_at 칸이 없습니다 — API 형식이 바뀌었을 수 있습니다."
        )
    return parse_iso_utc(stamp)


def age_days(last_success, now):
    """마지막 성공이 며칠 전인지. 미래 시각이면 음수가 나온다(그대로 돌려준다)."""
    return (now - last_success).total_seconds() / 86400.0


def is_newborn(workflow_file, created, now, max_age_days=DEFAULT_MAX_AGE_DAYS):
    """**갓 만들어져 아직 첫 예약을 기다리는 중**인가.

    만든 지 그 워크플로의 기준일이 안 지났으면 성공 기록이 0건인 게 당연하다 — 주 1회
    예약을 금요일에 머지하면 월요일까지는 기록이 없다. 그 구간을 멈춤으로 읽으면
    태어나자마자 부고가 뜬다(이슈 #98).

    ⚠️ 만든 시각을 모르면(None) 유예하지 않는다. 모른다는 이유로 봐주면, 조회가 어긋난
       순간부터 **진짜 멈춘 워크플로까지 영영 봐주게** 된다.
    """
    if created is None:
        return False
    return age_days(created, now) <= max_age_for(workflow_file, max_age_days)


def judge(results, max_age_days=DEFAULT_MAX_AGE_DAYS, now=None, created_at=None):
    """조회 결과에서 **오래된 것만** 골라 목록으로 돌려준다.

    `results` 는 `[(워크플로우 파일명, 마지막 성공 시각 또는 None), ...]` 이다.
    순서는 준 그대로 지킨다 — 이슈 제목이 실행마다 달라지면 중복 방지가 깨진다.

    `created_at` 은 `{파일명: 만든 시각}` 이다(성공 기록이 없는 것만 담긴다). 갓 만든
    워크플로를 멈춤으로 오해하지 않기 위한 것 — `is_newborn` 참조.
    """
    now = now or datetime.datetime.now(UTC)
    created_at = created_at or {}
    stale = []
    for workflow_file, last_success in results or []:
        if last_success is None:
            if is_newborn(workflow_file, created_at.get(workflow_file), now, max_age_days):
                continue  # 아직 첫 예약을 기다리는 중 — 기록이 없는 게 정상이다
            stale.append({
                "workflow": workflow_file,
                "label": label_of(workflow_file),
                "last_success": None,
                "age_days": None,
                "reason": "성공한 실행 기록이 없습니다",
            })
            continue
        age = age_days(last_success, now)
        # 워크플로우마다 예약 주기가 다르므로 기준도 다르다(max_age_for 참조).
        if age > max_age_for(workflow_file, max_age_days):
            stale.append({
                "workflow": workflow_file,
                "label": label_of(workflow_file),
                "last_success": last_success.strftime("%Y-%m-%d %H:%M UTC"),
                "age_days": round(age, 1),
                "reason": "마지막 성공이 {:.1f}일 전입니다".format(age),
            })
    return stale


def build_issue_title(stale):
    """이슈 제목.

    **날짜를 넣지 않는다.** 넣으면 매주 제목이 달라져 같은 사고로 이슈가 계속 쌓인다.
    워크플로우는 '열려 있는' 같은 제목만 건너뛰므로, 사람이 닫으면 다음 사고 때 다시 열린다.
    """
    return "감시 예약이 멈춘 것 같습니다: {}".format(
        ", ".join(s["label"] for s in stale)
    )


def build_issue_body(stale, max_age_days=DEFAULT_MAX_AGE_DAYS):
    """사람이 그대로 따라 할 수 있는 이슈 본문을 만든다."""
    lines = [
        "감시 워크플로우가 **한동안 돌지 않았습니다.**",
        "",
        "> 감시가 멈추면 실패 이슈조차 안 열립니다 — 아무 일도 안 일어나는 것이라",
        "> 아무도 모릅니다. 그 사이 새 분기 스냅샷은 포털에서 내려가고(절대 규칙 6),",
        "> 화면의 상권 경계는 조용히 낡습니다.",
        "",
        "## 무엇이 멈췄나",
        "",
        "| 감시 | 마지막 성공 | 며칠 전 |",
        "|---|---|---|",
    ]
    for s in stale:
        lines.append("| {} | `{}` | {} |".format(
            s["label"],
            s["last_success"] or "기록 없음",
            "-" if s["age_days"] is None else "{}일".format(s["age_days"]),
        ))
    lines += [
        "",
        "기준: 마지막 성공이 **{}일**보다 오래되면 알립니다(주 1회 예약 + 하루 여유).".format(
            max_age_days
        ),
        "",
        "## 왜 멈추나",
        "",
        "- 공개 저장소는 **60일간 활동이 없으면** 예약 실행이 자동으로 중지됩니다.",
        "- GitHub 부하가 높으면 예약된 실행이 **큐에서 드롭**되기도 합니다.",
        "",
        "## 할 일",
        "",
        "1. Actions 탭에서 아래 워크플로우가 **사용 중지(disabled)** 상태인지 봅니다.",
        "",
    ]
    for s in stale:
        lines.append("   - {} — <https://github.com/{}/actions/workflows/{}>".format(
            s["label"], REPO, s["workflow"]
        ))
    lines += [
        "",
        "2. 중지돼 있으면 **Enable workflow** 를 누릅니다.",
        "3. 그런 뒤 **Run workflow** 로 한 번 손수 돌려, 그 사이 놓친 것이 없는지 확인합니다.",
        "4. 내 PC 에서도 같은 확인을 할 수 있습니다.",
        "",
        "```powershell",
        r"cd D:\sangga",
        "python scripts/check_watch_heartbeat.py          # 예약 6종이 최근에 돌았나",
        "python scripts/check_new_sangkwon_quarter.py     # 새 분기가 떴나",
        "python scripts/check_district_source_update.py   # 상권 원천이 갱신됐나",
        "```",
        "",
        "*(이 이슈는 살아 있는 쪽 감시가 상대를 확인하고 자동으로 열었습니다.)*",
    ]
    return "\n".join(lines) + "\n"


# ── 네트워크 ──────────────────────────────────────────────────────────────────


def _get_json(url, timeout=TIMEOUT_SEC):
    """GitHub REST API 응답을 JSON 으로 받아온다."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # 공개 저장소라 토큰 없이도 읽히지만, Actions 러너는 IP 를 남과 나눠 써서 무인증
    # 한도(시간당 60회)가 이미 소진돼 있을 수 있다. 있으면 붙인다.
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer {}".format(token)
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="replace"))


def _get_json_with_retry(url, timeout=TIMEOUT_SEC, attempts=RETRY_COUNT, sleep=time.sleep):
    """짧은 타임아웃으로 여러 번 두드린다 (형제 감시와 같은 처방).

    한 번 실패했다고 포기하면 주 1회 감시가 일주일을 통째로 건너뛴다.

    단 **다시 물어봐야 답이 달라질 수 있는 실패만** 재시도한다(타임아웃·5xx·연결 끊김).
    404(파일명이 바뀜)·403(권한 회수)·401·422 는 15초를 더 기다려도 같은 답이 오므로
    즉시 포기하고 사람이 읽을 오류를 낸다.
    """
    for attempt in range(1, attempts + 1):
        try:
            return _get_json(url, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code in NO_RETRY_HTTP_CODES:
                raise
            if attempt == attempts:
                raise
            wait = RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
            print(
                "  GitHub 응답 없음 ({}/{}) — {}초 뒤 다시 시도합니다: {}".format(
                    attempt, attempts, wait, e
                ),
                file=sys.stderr,
                flush=True,
            )
            sleep(wait)
        except Exception as e:
            if attempt == attempts:
                raise
            wait = RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
            print(
                "  GitHub 응답 없음 ({}/{}) — {}초 뒤 다시 시도합니다: {}".format(
                    attempt, attempts, wait, e
                ),
                file=sys.stderr,
                flush=True,
            )
            sleep(wait)
    raise RuntimeError("재시도 루프가 한 번도 실행되지 않았습니다 (attempts 확인 필요).")


def runs_url(workflow_file, repo=REPO):
    """그 워크플로우의 **성공한 실행 1건**만 달라고 하는 주소."""
    return "{}/repos/{}/actions/workflows/{}/runs?status=success&per_page=1".format(
        API_BASE, repo, workflow_file
    )


def fetch_latest_success(workflow_file):
    """그 워크플로우의 마지막 성공 시각(UTC). 성공 기록이 없으면 None."""
    return parse_latest_success(_get_json_with_retry(runs_url(workflow_file)))


# 재확인 때 받을 최근 실행 수. 6시간 감시는 하루 4번이라 20건이면 닷새치다.
RECHECK_PER_PAGE = 20


def recent_runs_url(workflow_file, repo=REPO):
    """상태 거름망 **없이** 최근 실행 여러 건을 달라고 하는 주소(재확인용)."""
    return "{}/repos/{}/actions/workflows/{}/runs?per_page={}".format(
        API_BASE, repo, workflow_file, RECHECK_PER_PAGE
    )


def fetch_recent_success(workflow_file):
    """재확인: 최근 실행 목록에서 고른 마지막 성공 시각(UTC). 없으면 None."""
    return parse_latest_success_among(_get_json_with_retry(recent_runs_url(workflow_file)))


def recheck_stale(results, stale):
    """멈춤으로 나온 것만 **다른 방식으로 한 번 더** 묻고, 더 새로운 성공이 있으면 바꿔 끼운다.

    왜: 2026-10-01 GitHub 가 `status=success&per_page=1` 에 한 번 옛 답(09-17)을 줘, 6시간마다
    잘 도는 라이브 감시에 "14일째 멈춤" 이슈(#177)가 열렸다. 같은 주소를 직후에 다시 물으면
    정상이었다 — 거름망 없는 목록으로 한 번 더 확인하면 그런 헛경보를 거른다.

    ⛔ 재확인이 실패하면 **처음 판정을 그대로 둔다**(stderr 경고 한 줄). 진짜 멈춤 + 재확인
       실패가 겹칠 때 알림이 사라지면 안 되기 때문이다 — 종료코드 2·침묵으로 바꾸지 않는다.
    ⓘ 멈춤이 없으면 이 함수를 부르지 않는다(평소 경로 추가 호출 0).
    """
    targets = {s["workflow"] for s in stale}
    out = []
    for workflow_file, first in results:
        if workflow_file in targets:
            try:
                again = fetch_recent_success(workflow_file)
            except Exception as e:
                print("  재확인 실패({}): {} — 처음 판정(멈춤)을 그대로 둡니다.".format(
                    label_of(workflow_file), e), file=sys.stderr)
                again = None
            if again is not None and (first is None or again > first):
                print("  재확인({}): 마지막 성공이 {} 로 더 새롭습니다(처음 답 {}).".format(
                    label_of(workflow_file),
                    again.strftime("%Y-%m-%d %H:%M UTC"),
                    first.strftime("%Y-%m-%d %H:%M UTC") if first else "기록 없음",
                ), file=sys.stderr)
                first = again
        out.append((workflow_file, first))
    return out


def workflow_url(workflow_file, repo=REPO):
    """그 워크플로우 **자체**(만든 시각 포함)를 달라고 하는 주소."""
    return "{}/repos/{}/actions/workflows/{}".format(API_BASE, repo, workflow_file)


def fetch_created_at(workflow_file):
    """그 워크플로우를 만든 시각(UTC)."""
    return parse_created_at(_get_json_with_retry(workflow_url(workflow_file)))


def fetch_created_at_map(workflow_files):
    """`{파일명: 만든 시각}`.

    ⚠️ **성공 기록이 없는 것에만** 쓴다 — 평소 경로(전부 잘 도는 주)에 API 호출을 하나씩
       더 얹지 않기 위해서다. 빈 목록이면 네트워크를 아예 안 탄다.
    """
    return {f: fetch_created_at(f) for f in workflow_files}


def fetch_all(workflow_files):
    """여러 워크플로우를 순서대로 조회해 `[(파일명, 시각 또는 None), ...]` 로 돌려준다."""
    return [(f, fetch_latest_success(f)) for f in workflow_files]


# ── 출력 ──────────────────────────────────────────────────────────────────────


def write_github_output(stale):
    """GitHub Actions 다음 단계가 읽을 값을 GITHUB_OUTPUT 에 쓴다.

    로컬 실행(환경변수 없음)에서는 아무것도 하지 않는다.
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write("stale={}\n".format("true" if stale else "false"))
        f.write("title={}\n".format(build_issue_title(stale) if stale else ""))
    return True


def report(args, results, created, stale, now):
    """판정 결과를 화면(또는 --json)에 내고, 멈춤이면 이슈 본문 파일을 쓰고, GITHUB_OUTPUT 을 쓴다.

    ⓘ 여기서 난 예외는 main 이 종료코드 4 로 바꾼다(머리말 참조).
    """
    if args.json:
        print(json.dumps(
            {
                "max_age_days": args.max_age_days,
                "checked": [
                    {
                        "workflow": f,
                        "label": label_of(f),
                        "last_success": t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None,
                        "age_days": None if t is None else round(age_days(t, now), 1),
                        # 기록이 없어도 갓 만든 것이면 멈춘 게 아니다 — 그 구분을 남긴다.
                        "newborn": is_newborn(
                            f, created.get(f), now, args.max_age_days
                        ),
                    }
                    for f, t in results
                ],
                "stale": stale,
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print("=" * 66)
        print("감시 워크플로우 하트비트 — 아직 돌고 있나")
        print("=" * 66)
        for f, t in results:
            if t is None:
                born = created.get(f)
                if is_newborn(f, born, now, args.max_age_days):
                    print("  {:<12} 갓 만들어져 첫 예약을 기다리는 중 (만든 지 {:.1f}일)".format(
                        label_of(f), age_days(born, now)
                    ))
                else:
                    print("  {:<12} 성공 기록 없음".format(label_of(f)))
            else:
                print("  {:<12} 마지막 성공 {} ({:.1f}일 전)".format(
                    label_of(f), t.strftime("%Y-%m-%d %H:%M UTC"), age_days(t, now)
                ))
        print("  기준                : {}일보다 오래되면 멈춘 것으로 본다".format(
            args.max_age_days
        ))
        if stale:
            print("  ★ 멈춘 것 같음      : {}개".format(len(stale)))
            for s in stale:
                print("      {}  {}".format(s["label"], s["reason"]))
            print()
            print("  → Actions 탭에서 사용 중지(disabled) 됐는지 보고, 그렇다면 다시 켜세요.")
        else:
            print("  멈춘 감시           : 없음")
        print("=" * 66)

    if stale:
        with open(ISSUE_BODY_FILE, "w", encoding="utf-8") as f:
            f.write(build_issue_body(stale, max_age_days=args.max_age_days))
    write_github_output(stale)


def main(argv=None):
    # cp949 콘솔에서 한글·특수문자(—) 출력이 깨지거나 죽지 않게 — 형제 감시와 같은 처방.
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="감시 워크플로우 하트비트 점검")
    ap.add_argument(
        "--workflow",
        action="append",
        metavar="파일명",
        help="확인할 워크플로우 파일명 (여러 번 쓸 수 있음). 기본 = 예약 6종 전부",
    )
    ap.add_argument(
        "--max-age-days",
        type=float,
        default=DEFAULT_MAX_AGE_DAYS,
        help="이만큼보다 오래됐으면 멈춘 것으로 본다 (기본 {})".format(DEFAULT_MAX_AGE_DAYS),
    )
    ap.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    args = ap.parse_args(argv)

    workflows = list(args.workflow) if args.workflow else list(DEFAULT_WORKFLOWS)

    try:
        results = fetch_all(workflows)
        # 성공 기록이 없는 것만 "언제 만들었나"를 되묻는다. 갓 만든 워크플로는 첫 예약이
        # 오기 전이라 기록이 없는 게 정상이기 때문이다(이슈 #98). 조회가 실패하면 여기서
        # 같이 터져 종료코드 2 로 간다 — "멈췄다"가 아니라 "확인을 못 했다"가 맞다.
        created = fetch_created_at_map([f for f, t in results if t is None])
    except Exception as e:  # 네트워크·API 형식 변경 등
        print("실행 기록 조회 실패: {}".format(e), file=sys.stderr)
        print(
            "GitHub 가 응답하지 않거나 워크플로우 파일명이 바뀌었을 수 있습니다. "
            "check_watch_heartbeat.py 의 파일명 상수를 확인하세요.",
            file=sys.stderr,
        )
        return 2

    # ⛔ 판정에서 난 예외도 2 다. 응답 모양이 바뀐 것(시각 칸이 문자열이 아님 등)은 조회 실패와
    #    같은 종류인데, 놓치면 파이썬 기본값 1 = "멈춘 것이 있음"으로 읽힌다 — 그런데 stale 기록이
    #    없어 이슈 단계가 건너뛰어지고 아무 알림이 없다(형제 LH 공고 감시와 같은 처방).
    try:
        now = datetime.datetime.now(UTC)
        stale = judge(results, max_age_days=args.max_age_days, now=now, created_at=created)
        if stale:
            # 멈춤으로 나온 것만 다른 방식으로 한 번 더 묻는다 — GitHub 가 옛 답을 준 헛경보 거르기.
            results = recheck_stale(results, stale)
            stale = judge(results, max_age_days=args.max_age_days, now=now, created_at=created)
    except Exception as e:
        print("[실패] 실행 기록을 판정하는 중 {}: {} — 응답 모양이 바뀌었을 수 있습니다.".format(
            type(e).__name__, e), file=sys.stderr)
        return 2

    # ⛔ 조회 **뒤**(화면 출력·--json·이슈 본문 파일·GITHUB_OUTPUT)에서 난 예외도 잡는다. 놓치면
    #    파이썬 기본값 1 = "멈춘 것이 있음"과 겹친다 — 이슈 파일을 다 쓴 뒤 GITHUB_OUTPUT 에서
    #    죽으면 stale 기록이 없어 이슈 단계가 건너뛰어진다. 멈춤이 없어도 기록 쓰기가 실패하면
    #    4 다(다음 단계가 읽을 값이 비는 것은 같다). 워크플로가 4 를 받아 고장 알림을 연다.
    try:
        report(args, results, created, stale, now)
    except Exception as e:
        print("[실패] 결과를 쓰는 중 {}: {} — 멈춘 감시 알림이 안 나갔을 수 있습니다.".format(
            type(e).__name__, e), file=sys.stderr)
        return EXIT_OUTPUT_FAILED
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
