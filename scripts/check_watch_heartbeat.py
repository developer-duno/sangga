# -*- coding: utf-8 -*-
"""
감시 워크플로우가 **아직 살아서 돌고 있는지** 확인한다 (하트비트).

왜 이게 필요한가
----------------
감시 2종(`sangkwon-quarterly-watch.yml` · `district-source-watch.yml`)은 "돌았는데
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

이 판정을 누가 쓰나 (상호 감시)
-------------------------------
감시 둘이 **서로를 본다.** 자기 일이 끝난 뒤 상대의 마지막 성공 나이를 재고, 오래됐으면
이슈를 연다. 한쪽 예약이 살아 있는 한 다른 쪽의 죽음은 일주일 안에 이슈로 뜬다.
둘 다 죽는 경우만 남는데, 그건 사람이 내 PC 에서 이 명령을 직접 돌려 잡는다:

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
    python scripts/check_watch_heartbeat.py                              # 감시 2종 전부
    python scripts/check_watch_heartbeat.py --workflow district-source-watch.yml
    python scripts/check_watch_heartbeat.py --max-age-days 15 --json

종료코드: 0 = 전부 최근에 돌았음 / 1 = 오래된 것이 있음 / 2 = 조회 실패.
  ↳ 1 과 2 를 가르는 이유: "감시가 멈췄다"와 "내가 확인을 못 했다"는 서로 다른 사건이라
    한 코드로 뭉뚱그리면 워크플로우가 엉뚱한 이슈를 연다.
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

# 아무것도 안 주면 감시 3종을 다 본다(사람이 내 PC 에서 돌릴 때의 기본값).
DEFAULT_WORKFLOWS = (QUARTERLY_WATCH, DISTRICT_WATCH, LIVE_HEALTH_WATCH)

# 화면·이슈 제목에 쓸 짧은 이름표
WORKFLOW_LABELS = {
    QUARTERLY_WATCH: "분기 스냅샷 감시",
    DISTRICT_WATCH: "상권 원천 감시",
    LIVE_HEALTH_WATCH: "라이브 생존 감시",
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
    run = runs[0]
    if not isinstance(run, dict):
        raise ValueError("실행 기록이 객체가 아닙니다 — API 형식이 바뀌었을 수 있습니다.")
    # run_started_at 이 "실제로 돌기 시작한 시각"이라 하트비트에 가장 맞다.
    # 옛 실행 기록에는 없을 수 있어 created_at 으로 물러선다.
    stamp = run.get("run_started_at") or run.get("created_at")
    if not stamp:
        raise ValueError("실행 기록에 시각 칸이 없습니다 — API 형식이 바뀌었을 수 있습니다.")
    return parse_iso_utc(stamp)


def age_days(last_success, now):
    """마지막 성공이 며칠 전인지. 미래 시각이면 음수가 나온다(그대로 돌려준다)."""
    return (now - last_success).total_seconds() / 86400.0


def judge(results, max_age_days=DEFAULT_MAX_AGE_DAYS, now=None):
    """조회 결과에서 **오래된 것만** 골라 목록으로 돌려준다.

    `results` 는 `[(워크플로우 파일명, 마지막 성공 시각 또는 None), ...]` 이다.
    순서는 준 그대로 지킨다 — 이슈 제목이 실행마다 달라지면 중복 방지가 깨진다.
    """
    now = now or datetime.datetime.now(UTC)
    stale = []
    for workflow_file, last_success in results or []:
        if last_success is None:
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
        "python scripts/check_watch_heartbeat.py          # 감시 2종이 최근에 돌았나",
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
        help="확인할 워크플로우 파일명 (여러 번 쓸 수 있음). 기본 = 감시 2종 전부",
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
    except Exception as e:  # 네트워크·API 형식 변경 등
        print("실행 기록 조회 실패: {}".format(e), file=sys.stderr)
        print(
            "GitHub 가 응답하지 않거나 워크플로우 파일명이 바뀌었을 수 있습니다. "
            "check_watch_heartbeat.py 의 파일명 상수를 확인하세요.",
            file=sys.stderr,
        )
        return 2

    now = datetime.datetime.now(UTC)
    stale = judge(results, max_age_days=args.max_age_days, now=now)

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
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
