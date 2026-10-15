# -*- coding: utf-8 -*-
"""건축물대장 판 표지(ledger_release)를 보거나 올린다 (마이그레이션 2026-10-15a · F3).

왜 있나
-------
신선도 표의 '건축물대장' 줄은 `max(building.updated_at)`(적재일)이 아니라 이 표지 한 줄의 **판**
(건축HUB 일괄 파일의 기준월 YYYYMM)을 읽고, 다음 갱신 예정을 판 + 3개월 - 하루로 계산한다.
적재일을 읽으면 30개 구 중 한 구만 넣은 순간에도 '오늘'이 되므로, 판은 **다 넣은 뒤 사람이** 올린다.

사용
----
    python scripts/publish_ledger_release.py --show               # 지금 표지(판·적은 시각) + 열린 구마다 적재 여부
    python scripts/publish_ledger_release.py --ym 202609 --dry-run # 판정만(쓰기 0)
    python scripts/publish_ledger_release.py --ym 202609          # 판정을 다 지나면 표지를 그 판으로

--ym 이 올리기 전에 보는 넷(하나라도 걸리면 쓰기 0):
  ⓐ 모양 — 여섯 자리 숫자 · 달 01~12 (아니면 exit 2)
  ⓑ 앞으로만 — 지금 판보다 작으면 거부(exit 1) · 같으면 바꿀 것 없음(exit 0 · 쓰기 0)
  ⓒ 지난달까지만 — 한국 시각 이번 달 이상이면 거부(exit 1 · N월 판은 (N+1)월 20일 무렵 게시된다).
     한국 날짜가 20일 전인데 지난달 판이면 [주의] 한 줄만(거부 아님 · 종료 코드 무관 — 정말 받은 판인지 확인)
  ⓓ 다 넣었나 — 열린 구(mv_open_sigungu) **전부**의 max(building.updated_at) 이 지금 표지를 적은 시각
     (loaded_at) 뒤여야 한다. 아니면 안 된 구 코드를 찍고 거부(exit 1) — 손대지 않은 구가 남은 채 새 판이라
     적는 일을 막는다. ⚠️ 한 구 도중 실패는 못 본다(그 구도 첫 배치부터 시각이 바뀐다): 30개 구 적재가 모두
     exit 0 인지 먼저 본다.
     (대장 적재기는 2026-10-15 부터 평소 적재의 갱신 행에도 적재 시각을 싣는다 — 그 전 판의 적재기로 넣으면
      새 건물이 없는 구가 '안 됨'으로 남는다.)

ⓘ --building-only 칸 채우기 재적재는 적재 시각을 싣지 않는다(2026-10-15 보완) — 그래서 ⓓ 를 지나가지 않는다.
⚠️ 열린 구 목록은 mv_open_sigungu(요약표)라 post_load.py 가 갱신한다 — 새 구를 처음 넣었으면 post_load 뒤에.
ⓘ DB 는 dbx(psql) 경유 — 비밀값은 출력하지 않는다. `-c` 로 보내는 SQL 은 ASCII 만(한글 표시는 파이썬에서).
"""

import os
import re
import subprocess
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbx  # noqa: E402  (같은 폴더의 접속 정보 해석기를 그대로 쓴다)

KST = ZoneInfo("Asia/Seoul")
YM_RE = re.compile(r"^\d{4}(0[1-9]|1[0-2])$")

USAGE = "쓸 수 있는 것: --show | --ym YYYYMM [--dry-run]"

# 'release_ym;loaded_at(epoch 초);loaded_at(한국 시각)' 한 줄 — 표지가 비었으면 빈 글자.
# ⛔ ASCII 만 — query_one 은 psql -c.
FLAG_SQL = (
    "select coalesce((select r.release_ym || ';' || extract(epoch from r.loaded_at)::text || ';' || "
    "to_char(r.loaded_at at time zone 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') "
    "from ledger_release r where r.id = 1), '');"
)

# 열린 구마다 'code;max(updated_at) epoch;한국 시각' 을 쉼표로 이은 한 줄(건물이 없는 구는 뒤 둘이 빈 글자).
# building 을 한 번만 훑어 구별 max 를 낸다(구마다 like 로 30번 훑지 않는다).
GU_SQL = (
    "select coalesce(string_agg(o.sigungu_code::text || ';' || coalesce(extract(epoch from g.mx)::text, '') "
    "|| ';' || coalesce(to_char(g.mx at time zone 'Asia/Seoul', 'YYYY-MM-DD HH24:MI'), ''), ',' "
    "order by o.sigungu_code), '') "
    "from mv_open_sigungu o "
    "left join (select substr(b.pnu, 1, 5) as gu, max(b.updated_at) as mx from building b group by 1) g "
    "on g.gu = o.sigungu_code::text;"
)


def parse_args(argv):
    """--show · --ym YYYYMM [--dry-run]. 모르는 인자·빈 인자는 ValueError(모양 판정 ⓐ 는 judge 몫)."""
    argv = list(argv)
    if argv == ["--show"]:
        return {"mode": "show"}
    dry = "--dry-run" in argv
    rest = [a for a in argv if a != "--dry-run"]
    if len(rest) == 1 and rest[0].startswith("--ym="):
        rest = ["--ym", rest[0][len("--ym="):]]
    if len(rest) == 2 and rest[0] == "--ym" and rest[1] and argv.count("--dry-run") <= 1:
        return {"mode": "ym", "ym": rest[1], "dry_run": dry}
    raise ValueError("알 수 없는 인자: {!r}  ({})".format(" ".join(argv) or "(없음)", USAGE))


def parse_flag(text):
    """FLAG_SQL 의 답 → (판, loaded_at epoch Decimal, 한국 시각 글자). 비었거나 모양이 다르면 None.

    마지막 줄만 읽는다(앞에 psql 경고 줄이 섞여도)."""
    parts = last_line(text).split(";")
    if len(parts) != 3 or not re.match(r"^\d{6}$", parts[0]):
        return None
    try:
        return parts[0], Decimal(parts[1]), parts[2]
    except InvalidOperation:
        return None


def parse_gu_rows(text):
    """GU_SQL 의 답 → [(구 코드, max epoch Decimal 또는 None, 한국 시각 글자)]."""
    out = []
    for item in last_line(text).split(","):
        if not item:
            continue
        code, epoch, kst = (item.split(";") + ["", ""])[:3]
        try:
            ep = Decimal(epoch) if epoch else None
        except InvalidOperation:
            ep = None
        out.append((code.strip(), ep, kst))
    return out


def not_loaded_gu(gu_rows, loaded_at):
    """ⓓ — 지금 표지를 적은 시각(loaded_at) 뒤에 적재되지 않은 열린 구 코드 목록(순서 그대로).

    건물이 하나도 없는 구(max 가 None)도 '안 됨'이다. ⛔ '뒤'는 엄격히 크다(같은 시각은 안 됨).
    """
    return [code for code, ep, _ in gu_rows if ep is None or not ep > loaded_at]


PUBLISH_DAY = 20   # 건축HUB 는 N월 판을 (N+1)월 20일 무렵 올린다(2026-10-15 실측 — 8월 판 OPN20260920…)


def prev_month(ym):
    """'YYYYMM' 의 앞 달."""
    y, m = int(ym[:4]), int(ym[4:])
    return "{:04d}{:02d}".format(y - 1, 12) if m == 1 else "{:04d}{:02d}".format(y, m - 1)


def early_month_warning(ym, this_month, today_day):
    """ⓒ 보강(경고만 · 종료 코드 무관) — 한국 날짜가 20일 전인데 지난달 판이면 [주의] 한 줄, 아니면 None."""
    if today_day is None or today_day >= PUBLISH_DAY or ym != prev_month(this_month):
        return None
    return ("[주의] ⓒ 오늘은 {}일입니다 — 건축HUB 는 N월 판을 N+1월 {}일 무렵 올립니다. {} 판을 정말 받았는지 "
            "확인하세요(fetch_bldrgst_bulk.py --list 의 파일 id 날짜).".format(today_day, PUBLISH_DAY, ym))


def judge(ym, flag, this_month, gu_rows, today_day=None):
    """--ym 판정 ⓐ~ⓓ (순수 함수 — 본체와 시험이 이 함수 하나를 지난다).

    ym        : 올리려는 판 글자
    flag      : parse_flag 결과(None = 표지가 비었거나 못 읽음)
    this_month: 한국 시각 이번 달 'YYYYMM'
    gu_rows   : parse_gu_rows 결과
    today_day : 한국 시각 오늘 날짜(1~31 · 밖에서 넣는다) — 20일 전 지난달 판 [주의](거부 아님)
    돌려주는 것: (종료 코드, 찍을 줄 목록, 쓸지 여부)
    """
    code, lines, write = _judge(ym, flag, this_month, gu_rows)
    warn = None
    same_as_now = flag is not None and ym == flag[0]     # 같은 판 = 쓰기 0 이라 경고할 일이 없다
    if code != 2 and not same_as_now:                    # code 2 = 모양이 틀림(달을 셈할 수 없다)
        warn = early_month_warning(ym, this_month, today_day)
    return code, ([warn] if warn else []) + lines, write


def _judge(ym, flag, this_month, gu_rows):
    if not YM_RE.match(str(ym or "")):
        return 2, ["[에러] ⓐ 판은 YYYYMM 여섯 자리 숫자이고 달이 01~12 여야 합니다: {!r}".format(ym)], False
    if flag is None:
        return 1, ["[에러] 표지(ledger_release)가 비었거나 못 읽었습니다 — 마이그레이션 2026-10-15a 를 "
                   "다시 돌리면 처음 한 줄(202608)이 들어갑니다(on conflict do nothing). "
                   "python scripts/publish_ledger_release.py --show 로 확인하세요."], False
    current, loaded_at, loaded_kst = flag
    if ym < current:
        return 1, ["[에러] ⓑ {} 은 지금 판 {} 보다 옛 판입니다 — 표지는 앞으로만 올립니다.".format(ym, current)], False
    if ym == current:
        return 0, ["이미 판이 {} 입니다 — 바꿀 것 없음(쓰기 0).".format(ym)], False
    if ym >= this_month:
        return 1, ["[에러] ⓒ {} 은 한국 시각 이번 달({}) 이상입니다 — 판은 지난달까지만 있습니다"
                   "(N월 판은 (N+1)월 20일 무렵 게시).".format(ym, this_month)], False
    if not gu_rows:
        return 1, ["[에러] ⓓ 열린 구 목록(mv_open_sigungu)이 비었습니다 — 다 넣었는지 확인할 수 없습니다."], False
    missing = not_loaded_gu(gu_rows, loaded_at)
    if missing:
        return 1, ["[에러] ⓓ 지금 표지를 적은 {} 뒤에 적재되지 않은 열린 구가 {}개입니다: {}".format(
                       loaded_kst, len(missing), " ".join(missing)),
                   "       30개 구를 다 넣은 뒤 다시 하세요(load_building_ledger.py --raw-dir … 를 구마다)."], False
    return 0, ["판정 통과 — 열린 구 {}개 전부 {} 뒤에 적재됨 · {} → {}".format(
        len(gu_rows), loaded_kst, current, ym)], True


def build_update_sql(ym):
    """표지를 그 판으로(앞으로만 — 옛 판보다 클 때만) 바꾸고 바뀐 줄 수를 돌려준다. ASCII 만."""
    if not YM_RE.match(ym or ""):
        raise ValueError("판 모양이 다릅니다: {!r}".format(ym))
    return ("with u as (update ledger_release set release_ym = '{ym}', loaded_at = now() "
            "where id = 1 and release_ym < '{ym}' returning 1) select count(*) from u;").format(ym=ym)


def query_one(sql):
    """값 한 줄만 받아온다 (psql -tA). 실패하면 예외 — publish_snapshot.query_one 과 같은 방식.

    ⛔ 여기로 보내는 SQL 은 **ASCII 만** — `-c` 인자는 Windows 에서 cp949 로 넘어가 한글이 든 SQL 이
       `invalid byte sequence for encoding "UTF8"` 로 죽는다(2026-10-07 publish_snapshot 실측).
    """
    args, password = dbx.parts()
    env = dict(os.environ)
    env["PGPASSWORD"] = password           # ⚠️ 명령줄 노출 금지 (dbx.py 와 같은 이유)
    env["PGCLIENTENCODING"] = "UTF8"
    cmd = ["psql"] + args + ["-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql]
    out = subprocess.check_output(cmd, env=env, stderr=subprocess.STDOUT)
    return out.decode("utf-8", "replace").strip()


def kst_this_month(now=None):
    """한국 시각 이번 달 'YYYYMM' (now 를 밖에서 넣을 수 있다 — 시험용)."""
    return (now or datetime.now(KST)).astimezone(KST).strftime("%Y%m")


def kst_today_day(now=None):
    """한국 시각 오늘 날짜(1~31)."""
    return (now or datetime.now(KST)).astimezone(KST).day


def last_line(text):
    """psql 출력의 마지막 줄 — 앞에 경고(WARNING·NOTICE) 줄이 섞여도 값만 읽는다(2026-10-15 검사관 지적)."""
    lines = [ln for ln in str(text or "").strip().splitlines() if ln.strip()]
    return lines[-1].strip() if lines else ""


def show():
    flag = parse_flag(query_one(FLAG_SQL))
    if flag is None:
        print("[사고] 대장 표지(ledger_release)가 비었습니다 — 신선도 표 건축물대장 줄의 기준이 빈 상태입니다.")
        print("       마이그레이션 2026-10-15a 를 다시 돌리면 처음 한 줄이 들어갑니다.")
        return 1
    current, loaded_at, loaded_kst = flag
    print("대장 표지  판 {} (적은 시각 {}) — 지금 화면은 이 판을 말합니다.".format(current, loaded_kst))
    rows = parse_gu_rows(query_one(GU_SQL))
    missing = set(not_loaded_gu(rows, loaded_at))
    print("열린 구마다 '표지를 적은 뒤 다시 넣었나'(= 다음 판을 넣었나 · {} 판은 이미 다 들어 있다):".format(current))
    for code, _, kst in rows:
        print("  {}  max(updated_at) {}  {}".format(
            code, kst or "(건물 없음)", "다음 판 넣음" if code not in missing else "다음 판 아직"))
    print("열린 구 {}개 중 다음 판을 넣은 구 {}개 — 30개가 다 차야 --ym <다음 판> 이 지나간다".format(
        len(rows), len(rows) - len(missing)))
    return 0


def publish(ym, dry_run):
    flag = parse_flag(query_one(FLAG_SQL))
    rows = parse_gu_rows(query_one(GU_SQL)) if flag is not None else []
    code, lines, write = judge(ym, flag, kst_this_month(), rows, kst_today_day())
    for ln in lines:
        print(ln)
    if not write:
        return code
    if dry_run:
        print("(--dry-run) 쓰기 0 — 판정만 했습니다.")
        return 0
    n = last_line(query_one(build_update_sql(ym)))     # 바뀐 줄 수는 마지막 줄만(앞의 경고 줄은 건너뛴다)
    if n != "1":
        print("[실패] 표지를 바꾸지 못했습니다(바뀐 줄 {!r}) — 그 사이 다른 판이 올라갔을 수 있습니다. "
              "--show 로 확인하세요.".format(n))
        return 1
    print("대장 표지 = {} — 신선도 표 건축물대장 줄이 이 판을 말합니다.".format(ym))
    print("이어서 python scripts/post_load.py 뒤 python scripts/post_load.py --check")
    return 0


def main(argv=None):
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        opts = parse_args(sys.argv[1:] if argv is None else argv)
    except ValueError as e:
        print("[에러] {}".format(e))
        return 2
    if opts["mode"] == "show":
        return show()
    return publish(opts["ym"], opts["dry_run"])


if __name__ == "__main__":
    sys.exit(main())
