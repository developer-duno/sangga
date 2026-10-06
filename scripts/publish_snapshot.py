# -*- coding: utf-8 -*-
"""분기 표지(snapshot_release)를 보거나 손으로 맞춘다 — 되돌리기·확인 전용 (결정 0035).

왜 있나
-------
화면은 점포 분기를 `max(snapshot_ym)` 이 아니라 표지 한 줄에서 읽는다:
  loaded_ym    = 다 들어온 분기 — 적재기(load_sangkwon_snapshot.py)가 전국 적재 + 교차검증 뒤 적는다
  published_ym = 화면이 보는 분기 — post_load.py 가 요약표를 구운 뒤 올린다
평소에는 이 스크립트를 쓸 일이 없다(적재기 → post_load.py 가 알아서 한다). 쓰는 때는 셋:
  · 지금 표지가 어떤지 볼 때                         → --show
  · 화면을 옛 분기로 되돌릴 때(예행연습·사고 대응)     → --ym <옛 분기> 뒤 post_load.py
  · 적재기가 표지를 못 올렸을 때(RPC 실패 · 빠진 시·도 파일 · 시도 모드)
                                                     → --loaded <새 분기> 뒤 post_load.py

사용
----
    python scripts/publish_snapshot.py --show          # 표지 두 칸·시각·행수 + 점포 표 분기별 행수 + 요약표 셋의 분기
    python scripts/publish_snapshot.py --loaded 202609 # '다 들어온 분기'만 적는다(보여 주는 분기는 그대로)
    python scripts/publish_snapshot.py --ym 202606     # 되돌리기 전용 — 두 칸을 **모두** 그 분기로(점포 표에 있는 분기만)
    → 이어서 python scripts/post_load.py               # 요약표를 그 분기로 굽고, 확인이 끝나면 표지를 올린다

⛔ 새 분기를 손으로 적을 때는 --ym 이 아니라 --loaded 다(2026-10-07 맹점 검사관) — --ym 은 화면
   기준(published_ym)을 **바로** 바꿔, 요약표 굽기·확인(post_load)을 건너뛰고 반쪽 분기도 그대로
   공개한다. --loaded 는 post_load 가 굽고 확인한 뒤에만 화면이 바뀐다.
⚠️ --ym(되돌리기)은 층 목록·상권 건물 목록·신선도 표가 그 순간 그 분기를 말하고, 요약표 셋(가게
   이름 검색·각주·업종 카드)은 post_load.py 를 돌릴 때까지 옛 분기를 말한다. 그래서 끝에
   post_load.py 를 꼭 안내한다(한가한 시간에 한 묶음으로).
ⓘ DB 는 dbx(psql) 경유 — 비밀값은 출력하지 않는다(접속 정보는 dbx 가 환경변수로 넘긴다).
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbx  # noqa: E402  (같은 폴더의 접속 정보 해석기를 그대로 쓴다)

YM_RE = re.compile(r"^\d{6}$")

USAGE = "쓸 수 있는 것: --show | --loaded YYYYMM | --ym YYYYMM"

SHOW_FLAG_SQL = (
    "select coalesce(string_agg(concat_ws('|', r.loaded_ym, "
    "to_char(r.loaded_at at time zone 'Asia/Seoul', 'YYYY-MM-DD HH24:MI'), "
    "coalesce(r.loaded_rows::text, '(기록 없음)'), r.published_ym, "
    "to_char(r.published_at at time zone 'Asia/Seoul', 'YYYY-MM-DD HH24:MI')), ''), '') "
    "from snapshot_release r;"
)
SHOW_QUARTERS_SQL = (
    "select coalesce(string_agg(q.snapshot_ym || ':' || q.n::text, ',' order by q.snapshot_ym), '') "
    "from (select snapshot_ym, count(*) as n from unit_business group by 1) q;"
)
SHOW_MVS_SQL = (
    "select coalesce((select max(snapshot_ym) from mv_coverage_stats), '') || '|' || "
    "coalesce((select max(snapshot_ym) from mv_district_industry_mix), '') || '|' || "
    "coalesce((select max(store_snapshot_ym) from mv_parcel_store_names), '');"
)


def parse_args(argv):
    """--show · --loaded YYYYMM · --ym YYYYMM 중 하나만. 모르는 인자·빈 인자·모양이 틀린 분기는 ValueError."""
    argv = list(argv)
    if argv == ["--show"]:
        return {"mode": "show"}
    for flag, mode in (("--ym", "ym"), ("--loaded", "loaded")):
        if len(argv) == 2 and argv[0] == flag:
            if not YM_RE.match(argv[1]):
                raise ValueError("{} 은 YYYYMM 여섯 자리 숫자여야 합니다: {!r}".format(flag, argv[1]))
            return {"mode": mode, "ym": argv[1]}
        if len(argv) == 1 and argv[0].startswith(flag + "="):
            return parse_args([flag, argv[0][len(flag) + 1:]])
    raise ValueError("알 수 없는 인자: {!r}  ({})".format(" ".join(argv) or "(없음)", USAGE))


def build_exists_sql(ym):
    """점포 표에 그 분기 행이 있나 — 'n' 하나(행 수)를 돌려준다."""
    if not YM_RE.match(ym or ""):
        raise ValueError("분기 모양이 다릅니다: {!r}".format(ym))
    return "select count(*) from unit_business where snapshot_ym = '{}';".format(ym)


def build_set_sql(ym):
    """표지 두 칸을 모두 그 분기로(없으면 첫 줄을 만든다). 행 수는 그 자리에서 센다."""
    if not YM_RE.match(ym or ""):
        raise ValueError("분기 모양이 다릅니다: {!r}".format(ym))
    return (
        "insert into snapshot_release (id, loaded_ym, loaded_at, loaded_rows, published_ym, published_at)\n"
        "values (1, '{ym}', now(), (select count(*) from unit_business where snapshot_ym = '{ym}'),\n"
        "        '{ym}', now())\n"
        "on conflict (id) do update set loaded_ym = excluded.loaded_ym, loaded_at = excluded.loaded_at,\n"
        "  loaded_rows = excluded.loaded_rows, published_ym = excluded.published_ym,\n"
        "  published_at = excluded.published_at;\n"
    ).format(ym=ym)


def build_set_loaded_sql(ym):
    """'다 들어온 분기'만 그 분기로 — loaded_ym·loaded_at·loaded_rows(그 자리에서 센 행 수).

    ⛔ published_ym·published_at 은 **안 건드린다** — 화면은 post_load.py 가 요약표를 굽고 확인한
       뒤에만 바뀐다(적재기 RPC 와 같은 일을 사람이 손으로 하는 길 · 결정 0035).
    """
    if not YM_RE.match(ym or ""):
        raise ValueError("분기 모양이 다릅니다: {!r}".format(ym))
    return (
        "update snapshot_release set loaded_ym = '{ym}', loaded_at = now(),\n"
        "  loaded_rows = (select count(*) from unit_business where snapshot_ym = '{ym}')\n"
        "where id = 1;\n"
    ).format(ym=ym)


PUBLISHED_SQL = "select coalesce((select published_ym from snapshot_release where id = 1), '');"


def has_quarter(count_text):
    """build_exists_sql 의 답(행 수 글자)이 1 이상인가."""
    text = str(count_text or "").strip()
    return text.isdigit() and int(text) > 0


def query_one(sql):
    """값 한 줄만 받아온다 (psql -tA). 실패하면 예외 — post_load.query_one 과 같은 방식."""
    args, password = dbx.parts()
    env = dict(os.environ)
    env["PGPASSWORD"] = password           # ⚠️ 명령줄 노출 금지 (dbx.py 와 같은 이유)
    env["PGCLIENTENCODING"] = "UTF8"
    cmd = ["psql"] + args + ["-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql]
    out = subprocess.check_output(cmd, env=env, stderr=subprocess.STDOUT)
    return out.decode("utf-8", "replace").strip()


def show():
    flag = query_one(SHOW_FLAG_SQL)
    if not flag:
        print("[사고] 표지(snapshot_release)가 비었습니다 — 화면 가게 칸이 통째로 빈 상태입니다.")
        print("       python scripts/publish_snapshot.py --ym <분기> 로 채운 뒤 python scripts/post_load.py")
    else:
        loaded, loaded_at, rows, published, published_at = (flag.split("|") + [""] * 5)[:5]
        print("표지  다 들어온 분기 {} ({} · {}행)".format(loaded, loaded_at, rows))
        print("      보여 주는 분기 {} ({})".format(published, published_at))
    quarters = query_one(SHOW_QUARTERS_SQL)
    print("점포 표 분기별 행수: {}".format(
        " · ".join(q.replace(":", " ") for q in quarters.split(",") if q) or "(없음)"))
    cov, mix, names = (query_one(SHOW_MVS_SQL).split("|") + ["", "", ""])[:3]
    print("요약표 분기: 각주 {} · 업종 {} · 가게 이름 {}".format(
        cov or "(없음)", mix or "(없음)", names or "(없음)"))
    return 0


def set_quarter(ym):
    n = query_one(build_exists_sql(ym))
    if not has_quarter(n):
        print("[에러] 점포 표(unit_business)에 {} 분기 행이 없습니다 — 표지를 그 분기로 둘 수 없습니다.".format(ym))
        return 1
    rc = dbx.run_sql(build_set_sql(ym), quiet=True)
    if rc != 0:
        print("[실패] 표지를 바꾸지 못했습니다(psql 종료 코드 {}).".format(rc))
        return 1
    print("표지 = {} (다 들어온 분기 · 보여 주는 분기 둘 다 · {}행).".format(ym, n))
    print("이어서 python scripts/post_load.py — 요약표(가게 이름 검색·각주·업종 카드)를 그 분기로 다시 굽습니다.")
    return 0


def set_loaded(ym):
    """적재기가 표지를 못 올렸을 때 — '다 들어온 분기'만 적는다(화면은 그대로)."""
    published = query_one(PUBLISHED_SQL).strip()
    if not YM_RE.match(published):
        print("[에러] 표지(snapshot_release)가 비었거나 보여 주는 분기를 못 읽었습니다({!r}) — "
              "python scripts/publish_snapshot.py --show 로 확인하세요.".format(published))
        return 1
    if ym < published:
        print("[에러] {} 은 지금 보여 주는 분기 {} 보다 옛 분기입니다 — --loaded 는 앞으로만 적습니다. "
              "뒤로는 python scripts/publish_snapshot.py --ym {} (되돌리기)".format(ym, published, ym))
        return 1
    n = query_one(build_exists_sql(ym))
    if not has_quarter(n):
        print("[에러] 점포 표(unit_business)에 {} 분기 행이 없습니다 — 다 들어온 분기로 적을 수 없습니다.".format(ym))
        return 1
    rc = dbx.run_sql(build_set_loaded_sql(ym), quiet=True)
    if rc != 0:
        print("[실패] 표지를 바꾸지 못했습니다(psql 종료 코드 {}).".format(rc))
        return 1
    print("표지: 다 들어온 분기 = {} ({}행) · 보여 주는 분기는 그대로 {} — 화면은 아직 안 바뀌었습니다.".format(
        ym, n.strip(), published))
    print("이어서 python scripts/post_load.py — 요약표를 그 분기로 굽고, 확인이 끝나면 표지를 올립니다.")
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
    if opts["mode"] == "loaded":
        return set_loaded(opts["ym"])
    return set_quarter(opts["ym"])


if __name__ == "__main__":
    sys.exit(main())
