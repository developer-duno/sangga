# -*- coding: utf-8 -*-
"""LH 상가 공고 — 우리가 아직 못 받은 새 공고가 떴는지 확인한다.

왜 이게 필요한가
----------------
공고는 **마감이 있다.** 상가 공고의 마감일까지는 대개 2~3주라, 놓치면 그 공고는 그냥
지나간다 — 나중에 받아도 이미 끝난 것을 창고에 넣는 일이 된다. 그런데 수집은 사람 손이라
"새 공고가 떴다"를 알려 주는 장치가 없으면 잊는 것이 기본값이 된다. 이 레포는 이미
같은 병을 앓았다(분기 스냅샷 — 절대 규칙 6).

왜 받아서 적재까지 하지 않나
----------------------------
형제 감시들과 같은 원칙이다:
  ① 적재하려면 **DB 서비스키를 GitHub 에 올려야 한다.** 알림만 하면 비밀값은 인증키
     하나(MOLIT_KEY)로 끝나고, 그 키는 읽기 전용 공공 API 키다.
  ② 사람이 한 번 보고 받는 편이 낫다 — 공고는 내용을 눈으로 훑을 값어치가 있다.
그래서 이 스크립트는 **알리기만** 하고, 받는 것·적재는 사람이 로컬에서 한다.

무엇을 보나
-----------
LH 공고문 API 를 최근 창으로 훑어 **상가 공고**만 고르고, 그중 기준선
(`LATEST_KNOWN_NOTICE_DATE`)보다 **뒤에 게시된 것**이 있으면 알린다.

  ⚠️ 마감이 지난 것은 세지 않는다 — 이미 끝난 공고를 알려 봐야 할 일이 없다.

쓰는 법
-------
    python scripts/check_lh_notices.py          # 사람이 눈으로 확인
    python scripts/check_lh_notices.py --json   # 기계용 출력

종료코드: 0 = 새 공고 없음 / 1 = **새 공고 있음** / 2 = 조회 실패.
  ↳ 형제 감시(분기 스냅샷)는 새 것이 있어도 0 으로 끝내지만, 여기는 1 로 끝낸다.
    공고는 마감이 있어 "있는데 아무도 안 봄"이 곧 손실이기 때문이다. 워크플로는
    GITHUB_OUTPUT 의 found 값으로 이슈를 열므로, 종료코드 1 이 job 을 실패시키지 않게
    `continue-on-error` 로 받는다(워크플로 주석 참조).

적재한 뒤에는 아래 LATEST_KNOWN_NOTICE_DATE 를 그 판의 가장 최근 공고일로 올린다.
그게 이 스크립트의 유일한 기준선이다(check_new_sangkwon_quarter.py 의
LATEST_KNOWN_QUARTER 와 같은 방식).
"""

import argparse
import datetime
import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
COLLECTORS_DIR = os.path.join(SCRIPTS_DIR, "collectors")
for _p in (SCRIPTS_DIR, COLLECTORS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ⚠️ 수집기를 그대로 쓴다 — 주소·유형코드·파싱을 여기서 다시 짜면 두 벌이 되고, 언젠가
#    한쪽만 고쳐져 **감시가 "새 공고 없음"이라고 말하는 동안 수집기는 다른 것을 본다.**
#    수집기는 표준 라이브러리만으로 열린다(dotenv·requests 는 필요할 때만 늦게 부른다) —
#    그래서 설치 단계가 없는 워크플로 러너에서도 이 import 가 통한다.
import collect_lh_notices as lh  # noqa: E402

# ── 기준선 ────────────────────────────────────────────────────────────────────

# 이미 받아서 창고에 넣은 가장 최신 공고일(YYYYMMDD). 이보다 뒤면 "새 공고"로 본다.
# ⚠️ 적재했으면 **이 값을 올려야** 다음 공고를 제대로 감지한다. 안 올리면 같은 공고로
#    매주 이슈가 열려 알림이 소음이 되고, 소음은 결국 무시된다.
# 2026-09-05 두 번째 적재(533건) 시점의 최신 공고일 — 첫 적재(2026-08-28)는 20260826 이었다.
LATEST_KNOWN_NOTICE_DATE = "20260904"

# ── API (수집기가 정본 — 여기서 다시 정하지 않는다) ───────────────────────────

BASE_URL = lh.BASE_URL
SANGA_UPP_CD = lh.SANGA_UPP_CD

MAX_PAGES = 60          # 감시는 짧은 창(기본 2개월)만 보므로 이 정도면 넉넉하다
DEFAULT_MONTHS = 2      # 주 1회 도는 감시에 2개월 창이면 한 달을 통째로 걸러도 잡힌다

ISSUE_BODY_FILE = "lh_new_notice_issue.md"

KST = datetime.timezone(datetime.timedelta(hours=9), "KST")


# ── 순수 함수 (네트워크 없음 — 테스트 대상) ───────────────────────────────────


def to_yyyymmdd(iso_date):
    """'2026-08-27' → '20260827'. 비어 있으면 None."""
    if not iso_date:
        return None
    return str(iso_date).replace("-", "").strip() or None


def is_open(close_date, pan_ss=None, today=None):
    """아직 마감 전인가. 마감일을 **모르는 것은 열린 것으로 본다**.

    모르는 것을 닫힌 것으로 치면 살아 있는 공고가 조용히 사라진다 — 읽는 함수
    (list_lh_notices)가 NULL 을 남겨 두는 것과 같은 판단이다.

    ⛔ **LH 가 '접수마감'이라 적어 준 것도 마감일과 무관하게 닫힌 것으로 본다**
       (2026-09-01d, 화면과 같은 규칙). 마감일만 보면 못 거른다 — 실측으로 마감일이
       2028년으로 먼 미래인 [취소공고]가 남아 있었다. 이걸 안 보면 이미 접수가
       끝난(또는 취소된) 공고에 "새 공고입니다"라며 매주 소음 이슈가 열린다.
    """
    if pan_ss == "접수마감":
        return False
    if not close_date:
        return True
    today = today or datetime.datetime.now(KST).date()
    return str(close_date) >= today.isoformat()


def find_new_notices(rows, latest_known=LATEST_KNOWN_NOTICE_DATE, today=None):
    """기준선보다 뒤에 게시됐고 **아직 마감 전인** 공고만 골라 돌려준다.

    돌려주는 것: `[{pan_id, pan_nm, kind_nm, notice_date, close_date, region, dtl_url}, ...]`
    공고일 내림차순(최신이 위), 같은 날이면 공고번호 순.
    """
    out = []
    for r in rows or []:
        nd = to_yyyymmdd(r.get("notice_date"))
        if not nd or nd <= latest_known:
            continue
        if not is_open(r.get("close_date"), pan_ss=r.get("pan_ss"), today=today):
            continue
        out.append({
            "pan_id": r.get("pan_id"),
            "pan_nm": r.get("pan_nm"),
            "kind_nm": r.get("kind_nm"),
            "notice_date": r.get("notice_date"),
            "close_date": r.get("close_date"),
            "region": "전국" if r.get("is_nationwide") else (r.get("cnp_nm") or "(지역 미상)"),
            "dtl_url": r.get("dtl_url"),
        })
    out.sort(key=lambda x: ((x["notice_date"] or ""), (x["pan_id"] or "")), reverse=True)
    return out


def build_issue_title(new_notices):
    """이슈 제목. 같은 판으로 이슈가 두 번 열리지 않게 **가장 최근 공고일**을 박는다."""
    newest = new_notices[0]["notice_date"] if new_notices else "?"
    return "새 LH 상가 공고 {}건 ({} 기준)".format(len(new_notices), newest)


def build_issue_body(new_notices, latest_known=LATEST_KNOWN_NOTICE_DATE):
    """사람이 그대로 따라 할 수 있는 이슈 본문."""
    lines = [
        "LH 청약센터에 **새 상가 공고**가 올라왔습니다.",
        "",
        "> 공고는 마감이 있습니다(대개 2~3주). 놓치면 그 공고는 그냥 지나갑니다 —",
        "> 나중에 받아도 이미 끝난 것을 창고에 넣는 일이 됩니다.",
        "",
        "## 새로 올라온 것",
        "",
        "| 공고일 | 마감일 | 지역 | 종류 | 공고명 |",
        "|---|---|---|---|---|",
    ]
    for n in new_notices[:30]:
        lines.append("| {} | {} | {} | {} | [{}]({}) |".format(
            n["notice_date"] or "?",
            n["close_date"] or "미상",
            n["region"],
            n["kind_nm"] or "?",
            (n["pan_nm"] or "?").replace("|", "·"),
            n["dtl_url"] or "https://apply.lh.or.kr",
        ))
    if len(new_notices) > 30:
        lines.append("")
        lines.append("… 외 {}건.".format(len(new_notices) - 30))
    lines += [
        "",
        "지금 기준선(창고에 넣은 최신 공고일)은 `{}` 입니다.".format(latest_known),
        "",
        "## 할 일 (내 PC에서)",
        "",
        "```powershell",
        r"cd D:\sangga",
        "python scripts/collectors/collect_lh_notices.py --dry-run   # 무엇이 들어올지 먼저 본다",
        "python scripts/collectors/collect_lh_notices.py             # 적재(한 트랜잭션)",
        "python scripts/post_load.py                                 # 요약표 갱신 + 신선도 점검",
        "```",
        "",
        "적재까지 끝나면 `scripts/check_lh_notices.py` 의 `LATEST_KNOWN_NOTICE_DATE` 를",
        "`{}` 로 올리고 이 이슈를 닫습니다.".format(
            to_yyyymmdd(new_notices[0]["notice_date"]) if new_notices else latest_known),
        "",
        "*(이 이슈는 LH 공고 감시 워크플로가 자동으로 열었습니다.)*",
    ]
    return "\n".join(lines) + "\n"


# ── 출력 ──────────────────────────────────────────────────────────────────────


def write_github_output(new_notices):
    """GitHub Actions 다음 단계가 읽을 값을 GITHUB_OUTPUT 에 쓴다.

    로컬 실행(환경변수 없음)에서는 아무것도 하지 않는다.
    """
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write("found={}\n".format("true" if new_notices else "false"))
        f.write("count={}\n".format(len(new_notices)))
        f.write("title={}\n".format(build_issue_title(new_notices) if new_notices else ""))
    return True


def get_api_key():
    """인증키. Actions 에서는 secrets.MOLIT_KEY 가 환경변수로 들어온다."""
    key = os.environ.get("MOLIT_KEY", "").strip()
    if key:
        return key
    # 로컬에서는 .env 를 읽는다(러너에는 .env 도 python-dotenv 도 없다).
    try:
        from dotenv import load_dotenv  # noqa: PLC0415

        load_dotenv(os.path.join(os.path.dirname(SCRIPTS_DIR), ".env"))
    except Exception:
        return ""
    return os.environ.get("MOLIT_KEY", "").strip()


def fetch_recent(key, months=DEFAULT_MONTHS):
    """최근 창의 상가 공고를 수집기와 **같은 코드로** 받아 온다."""
    start_dt, end_dt = lh.window(months=months)
    stamp = datetime.datetime.now(KST).isoformat(timespec="seconds")
    rows, pages, all_cnt = lh.fetch_sanga(
        key, start_dt, end_dt, stamp, max_pages=MAX_PAGES, verbose=False)
    return rows, pages, all_cnt, start_dt, end_dt


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

    ap = argparse.ArgumentParser(description="새 LH 상가 공고 감시")
    ap.add_argument("--months", type=int, default=DEFAULT_MONTHS,
                    help="최근 몇 개월을 볼지 (기본 {})".format(DEFAULT_MONTHS))
    ap.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    args = ap.parse_args(argv)

    key = get_api_key()
    if not key:
        print("MOLIT_KEY 가 없습니다 — 이 감시는 인증키 하나만 씁니다.", file=sys.stderr)
        print("  Actions 라면 저장소 Secrets 에 MOLIT_KEY 를 넣으세요.", file=sys.stderr)
        return 2

    try:
        rows, pages, all_cnt, start_dt, end_dt = fetch_recent(key, months=args.months)
    except Exception as e:
        print("LH 공고 조회 실패: {}".format(lh.mask_key(e, key)), file=sys.stderr)
        print(
            "포털이 응답하지 않거나 인증키가 거절됐을 수 있습니다(403). "
            "응답 형식이 바뀐 경우에는 collect_lh_notices.py 의 extract_rows 를 확인하세요.",
            file=sys.stderr,
        )
        return 2

    # ⛔ 조용한 빈손 금지. 최근 두 달에 상가 공고가 0건인 일은 없다(1년 531건 실측).
    #    0 이면 유형코드가 바뀌었거나 응답이 빈 것이라, "새 공고 없음"으로 끝내면
    #    그날부터 감시가 장님이 된 채 매주 초록불만 켠다.
    if not rows:
        print(
            "최근 {}개월에 상가 공고가 한 건도 없습니다 — 정상이 아닙니다 "
            "(상위 유형코드 {} 가 바뀌었을 수 있습니다).".format(args.months, SANGA_UPP_CD),
            file=sys.stderr)
        return 2

    new_notices = find_new_notices(rows)

    if args.json:
        print(json.dumps({
            "latest_known": LATEST_KNOWN_NOTICE_DATE,
            "window": {"start": start_dt, "end": end_dt},
            "pages": pages,
            "portal_total": all_cnt,
            "sanga_in_window": len(rows),
            "new": new_notices,
        }, ensure_ascii=False, indent=2))
    else:
        print("=" * 66)
        print("LH 상가 공고 — 새 공고 감시")
        print("=" * 66)
        print("  기준선(창고 최신 공고일) : {}".format(LATEST_KNOWN_NOTICE_DATE))
        print("  본 창                    : {} ~ {} ({}쪽)".format(start_dt, end_dt, pages))
        print("  창 안의 상가 공고        : {:,}건".format(len(rows)))
        if new_notices:
            print("  ★ 새 공고(마감 전)      : {}건".format(len(new_notices)))
            for n in new_notices[:10]:
                print("      {}  {:<8} {:<20} {}".format(
                    n["notice_date"], n["region"][:8], (n["kind_nm"] or "")[:10],
                    (n["pan_nm"] or "")[:34]))
            if len(new_notices) > 10:
                print("      … 외 {}건".format(len(new_notices) - 10))
            print()
            print("  → 지금 받으세요. 공고는 마감이 지나면 지나간 것이 됩니다.")
        else:
            print("  새 공고                  : 없음")
        print("=" * 66)

    if new_notices:
        with open(ISSUE_BODY_FILE, "w", encoding="utf-8") as f:
            f.write(build_issue_body(new_notices))
    write_github_output(new_notices)
    return 1 if new_notices else 0


if __name__ == "__main__":
    sys.exit(main())
