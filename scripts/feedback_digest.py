# -*- coding: utf-8 -*-
"""의견함에 쌓인 것을 매주 알린다 — 우편함을 **읽을 계기**를 만드는 장치.

왜 이 스크립트가 있나
---------------------
2026-08-24 우편함(app_feedback)을 만들었지만 **읽을 계기가 어디에도 없었다.** 넣는
길(`api.submit_feedback`)만 열렸을 뿐, 쌓인 것을 사람이 정기적으로 열어 볼 장치가
없으면 "나중에 읽겠다"는 영영 지켜지지 않는다. 이 레포는 이미 그 일을 겪었다 — 감시가
죽은 걸 나흘 뒤에야 알았고, 그래서 감시들이 서로를 보게 만들었다.
읽히지 않는 의견함은 값어치가 0인데 보안·CI 부담만 진다.

무엇을 하나
-----------
`api.get_feedback_stats()` 를 한 번 불러 **숫자만** 받아 오고, 알릴 일이 있으면
GitHub Actions 가 이슈를 열 수 있게 결과를 넘긴다. 알릴 일은 둘이다:

  ① **새 글이 있다** — 최근 이레 동안 의견이나 오류 기록이 하나라도 왔다.
  ② **치우기가 밀렸다** — 가장 오래된 글이 보관 기한(90일)을 넘겼다.
     ⓘ 치우기는 편지가 들어올 때 창고가 스스로 한다(2026-08-24c). 그래서 **아무도 안
       보내는 동안에는 안 돈다.** 그 빈틈을 여기서 지켜본다 — 이 한 줄이 없으면
       "90일 보관"은 말만 정책이고 실제로는 안 지켜질 수 있다.

둘 다 아니면 **아무것도 안 알린다.** "이번 주도 0건입니다"가 매주 쌓이면 알림이
소음이 되고, 소음은 결국 무시된다(형제 감시 셋과 같은 판단).

⛔ 이 스크립트는 **내용을 못 본다.** 서버 함수가 건수만 돌려주기 때문이다. 내용을 읽는
   길은 여전히 `dbx.py`(서비스 권한) 하나뿐이고, 이슈 본문이 그 명령을 안내한다.

여기 쓰는 값(URL·공개키)은 **비밀값이 아니다** — 이미 배포된 화면의 자바스크립트
묶음에 그대로 실려 있어 누구나 라이브에서 읽을 수 있다. GitHub 저장소 **변수**(Secrets
아님)로 넣어 두면 형제 감시 셋의 "비밀값 0" 철학이 그대로 유지된다.

⚠️ 표준 라이브러리만 쓴다 — 워크플로에 설치 단계가 없다.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request

# ⚠️ 있으면 쓰고 없으면 넘어간다. 워크플로에는 설치 단계가 없어서(표준 라이브러리만
#    쓴다는 약속) python-dotenv 가 아예 없다 — 거기서는 값이 저장소 변수로 들어온다.
#    내 PC 에서는 이것 덕분에 `python scripts/feedback_digest.py` 만 쳐도 바로 돈다.
try:
    from dotenv import load_dotenv

    load_dotenv(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    )
except Exception:
    pass

# 최근 며칠을 셀지. 주 1회 예약과 맞춘다 — 한 주를 건너뛰지도, 겹쳐 세지도 않는다.
DEFAULT_WINDOW_DAYS = 7

# 서버의 보관 기한(2026-08-24c 마이그레이션의 상수)과 같은 값이어야 한다.
# ⚠️ 여기만 고치면 판정 기준만 바뀌고 실제 삭제는 안 바뀐다 — 기한을 바꾸려면 서버 함수
#    (purge_old_feedback)와 이 값을 **함께** 고친다. 테스트가 그 짝을 붙잡는다.
RETENTION_DAYS = 90

TIMEOUT_S = 30
RETRIES = 3

STATS_FN = "get_feedback_stats"


class CallFailed(Exception):
    """RPC 호출이 실패했다. 메시지가 그대로 사람에게 보인다."""


def rpc(base_url: str, anon_key: str, fn_name: str, payload: dict) -> object:
    """PostgREST RPC 를 한 번 부른다 — 성공하면 JSON 을 그대로 돌려준다.

    ⚠️ `Content-Profile: api` 가 핵심이다. RPC 는 POST 라서 `Accept-Profile` 이 아니라
       `Content-Profile` 로 스키마를 고른다(PostgREST 공식 문서 — 2026-08-24 확인).
       빠뜨리면 이 앱이 옛 문(public)을 닫은 그 사고(PGRST106)를 워크플로에서 그대로
       재현한다. 화면은 supabase-js 가 `db.schema` 로 이걸 대신 해 준다.
    """
    url = f"{base_url}/rest/v1/rpc/{fn_name}"
    body = json.dumps(payload).encode("utf-8")
    last = ""
    for attempt in range(1, RETRIES + 1):
        # ⚠️ Request 를 **매번 새로 만든다.** urllib 은 재시도 때 같은 객체를 다시 쓰면
        #    리다이렉트 처리 등에서 상태가 남을 수 있다. 만드는 비용은 0에 가깝다.
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "apikey": anon_key,
                "Authorization": f"Bearer {anon_key}",
                "Content-Type": "application/json",
                "Content-Profile": "api",
                "User-Agent": "sangga-feedback-digest",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as ex:
            detail = ex.read().decode("utf-8", errors="replace") if ex.fp else ""
            last = f"HTTP {ex.code} — {detail}".strip()
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            last = f"연결 실패({ex})"
        except json.JSONDecodeError as ex:
            last = f"응답이 JSON 이 아닙니다({ex})"
        if attempt < RETRIES:
            print(f"  · {fn_name} {attempt}번째 실패({last}) — 다시 시도합니다")
    raise CallFailed(f"{fn_name} 호출에 실패했습니다: {last}")


def fetch_stats(base_url: str, anon_key: str, days: int) -> dict:
    """의견함 숫자를 받아 온다 — 의견·오류 건수, 표 전체 건수, 가장 오래된 글의 나이."""
    result = rpc(base_url, anon_key, STATS_FN, {"p_days": days})
    # table 을 돌려주는 함수라 PostgREST 는 행 배열을 준다. 집계 함수라 GROUP BY 없이
    # 전체를 한 줄로 요약하므로 **항상 정확히 한 행**이다.
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
        raise CallFailed(f"{STATS_FN} 응답 모양이 예상과 다릅니다: {result!r}")
    row = result[0]
    try:
        stats = {
            "opinion_cnt": int(row["opinion_cnt"]),
            "error_cnt": int(row["error_cnt"]),
            "total_cnt": int(row["total_cnt"]),
            # 표가 비어 있으면 NULL 이 온다 — 그때는 "가장 오래된 글"이라는 것이 없다.
            "oldest_days": None if row.get("oldest_days") is None else int(row["oldest_days"]),
        }
    except (KeyError, TypeError, ValueError) as ex:
        raise CallFailed(f"{STATS_FN} 응답에서 숫자를 못 읽었습니다: {row!r}") from ex
    return stats


def retention_overdue(stats: dict) -> bool:
    """보관 기한을 넘긴 글이 남아 있나.

    치우기는 편지가 들어올 때만 돌기 때문에, 조용한 기간이 길면 기한을 넘긴 글이
    남는다. 그것이 **말로만 정책이고 실제로는 안 지켜지는** 상태다.
    """
    oldest = stats.get("oldest_days")
    return oldest is not None and oldest > RETENTION_DAYS


def build_issue_body(stats: dict, days: int) -> str:
    """이슈 본문. 건수만 아는 알림이라 **내용을 읽는 다음 걸음**을 반드시 안내한다."""
    lines = [
        f"최근 {days}일 동안 의견함에 **의견 {stats['opinion_cnt']}건 · "
        f"오류 기록 {stats['error_cnt']}건**이 들어왔습니다.",
        "",
        "이 알림은 **건수만** 압니다 — 무엇이 적혔는지는 아래 명령으로 직접 읽어야 합니다.",
        "(서버 함수가 본문을 아예 안 돌려주도록 만들어져 있습니다.)",
        "",
        "## 내용 읽기 (내 PC에서)",
        "",
        "```powershell",
        "cd D:\\sangga",
        'python scripts/dbx.py -c "select id, kind, left(body, 200) as body, '
        'context, created_at from app_feedback order by created_at desc limit 50"',
        "```",
        "",
        "⚠️ 본문에 사람이 스스로 연락처를 적어 넣었을 수 있습니다(우리가 요구한 수집은",
        "아니지만 막을 수는 없습니다). 그런 줄을 보면 그 자리에서 지우세요.",
        "",
        "## 지금 창고 상태",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 표에 남아 있는 전부 | {stats['total_cnt']:,}건 |",
        "| 가장 오래된 글 | "
        + ("없음(표가 비어 있음)" if stats["oldest_days"] is None else f"{stats['oldest_days']}일 전")
        + " |",
        f"| 보관 기한 | {RETENTION_DAYS}일 |",
        "",
    ]

    if retention_overdue(stats):
        lines += [
            f"### ⚠️ 보관 기한({RETENTION_DAYS}일)을 넘긴 글이 남아 있습니다",
            "",
            "치우기는 **새 편지가 들어올 때** 창고가 스스로 합니다. 조용한 기간이 길어지면",
            "이렇게 밀립니다. 아래 명령을 한 번 돌리면 정리됩니다.",
            "",
            "```powershell",
            "cd D:\\sangga",
            'python scripts/dbx.py -c "select public.purge_old_feedback()"',
            "```",
            "",
        ]

    lines += [
        "## 상한은 아직 안전망일 뿐입니다",
        "",
        "지금 서버 상한은 **분당 60통 · 종류별 하루 1,000통**입니다. 실사용을 모른 채 잡은",
        "안전망이라 수백 배 여유가 있습니다. 위의 실제 건수가 쌓이면 그 숫자로 조입니다",
        "— 그게 이 알림을 만든 이유 중 하나입니다.",
        "",
        "---",
        "",
        "다 읽었으면 이 이슈를 **닫으세요.** 다음 주에도 알릴 일이 있으면 새 이슈가 열립니다",
        "(제목에 날짜가 들어가 이번 이슈와 안 겹칩니다).",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="의견함에 쌓인 것을 세어 알린다(내용은 안 본다)."
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
    parser.add_argument("--days", type=int, default=DEFAULT_WINDOW_DAYS)
    args = parser.parse_args(argv)

    if not args.url or not args.anon_key:
        print("SANGGA_SUPABASE_URL / SANGGA_SUPABASE_ANON_KEY 가 필요합니다.")
        return 2
    base_url = args.url.rstrip("/")

    try:
        stats = fetch_stats(base_url, args.anon_key, args.days)
    except CallFailed as ex:
        print(f"[실패] {ex}")
        return 1

    print(
        f"[집계] 최근 {args.days}일 — 의견 {stats['opinion_cnt']}건 · "
        f"오류 기록 {stats['error_cnt']}건"
    )
    oldest = "없음" if stats["oldest_days"] is None else f"{stats['oldest_days']}일 전"
    print(f"[창고] 전부 {stats['total_cnt']}건 · 가장 오래된 글 {oldest}")

    has_news = (stats["opinion_cnt"] + stats["error_cnt"]) > 0
    overdue = retention_overdue(stats)

    if overdue:
        print(f"[주의] 보관 기한({RETENTION_DAYS}일)을 넘긴 글이 남아 있습니다.")

    if has_news or overdue:
        _emit_output("should_report", "true")
        _emit_output("body", build_issue_body(stats, args.days))
        reason = "새 글" if has_news else "보관 기한 초과"
        print(f"\n알릴 일이 있습니다({reason}) — 이슈를 엽니다.")
    else:
        _emit_output("should_report", "false")
        print("\n알릴 일이 없습니다 — 이슈를 열지 않습니다.")

    return 0


def _emit_output(key: str, value: str) -> None:
    """GitHub Actions 에 값을 넘긴다. 로컬에서 돌리면 아무 일도 안 한다.

    ⚠️ 구분자를 **실행마다 다르게** 만든다(check_live_health.py 와 같은 이유) — 값 안에
       구분자와 똑같은 줄이 들어오면 거기서 값이 끊기고 **그 뒤가 새 key=value 로
       읽힌다**. 이 스크립트의 이슈 본문은 우리가 만든 문구뿐이지만, 언젠가 의견 본문을
       여기 실으려는 사람이 나오는 날 이 한 줄이 방어선이 된다.
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    delim = "SANGGA_EOF_" + secrets.token_hex(8)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{key}<<{delim}\n{value}\n{delim}\n")


if __name__ == "__main__":
    sys.exit(main())
