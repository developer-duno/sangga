# -*- coding: utf-8 -*-
"""적재 뒤에 반드시 돌리는 마무리 — 통계 갱신 + 검색 요약표 갱신.

왜 따로 있나
------------
적재기(scripts/collectors/*.py)는 **REST 로 쓴다.** 그런데 `ANALYZE` 와
`refresh materialized view` 는 REST 로 못 한다(SQL 전용). 그래서 적재기 안에 넣을 수가
없었고, 지금까지는 **문서에만** "적재 후 하세요"라고 적혀 있었다.

문서에만 있는 절차는 잊힌다. 잊히면 **에러 없이** 틀린다:

  · VACUUM ANALYZE 를 빼먹으면 → ① 통계가 낡아 플래너가 잘못된 계획을 고르고
    ② **가시성 지도가 낡아** 인덱스만 읽으면 될 조회가 행마다 힙을 다시 방문한다.
    실측(2026-08-11): 각주 뷰가 ANALYZE 전 3,474ms → 후 374ms (9배).
    실측(2026-08-13, 전국 시드 뒤): 같은 뷰가 Heap Fetches 232,890 · 956ms 로 되돌아갔고
    `vacuum (analyze)` 한 번에 Heap Fetches **0** · 화면 0.31초가 됐다.
    결정 0005 가 "공식이 강력 권장하는데 우리 적재기에 없다"고 이미 지적해 둔 구멍이다.
  · 요약표 갱신을 빼먹으면 → **새로 넣은 건물이 검색에 안 나온다.**
    화면엔 "결과가 없습니다"만 뜨고 아무도 원인을 모른다(2026-08-13 신설).
  · 지도용 상권 파일 굽기를 빼먹으면 → **지도만 옛날 상권을 보여준다.**
    지도는 DB 가 아니라 구워 둔 정적 파일을 읽기 때문이다(2026-08-14 신설, 결정 0010).
    ⚠️ 굽는 것까지 대신 해 주지는 않는다 — 그 파일은 git 에 커밋하는 자산이라
    사람이 보고 커밋해야 한다. 여기서는 "낡았다"고 알리고 명령을 안내한다.

그래서 "적재 후 이거 하나만 돌리면 된다"를 한 곳으로 모은다.

⭐ 신선도는 **정확히 검사할 수 있다**
--------------------------------------
`mv_search_parcel` 은 "건물이 있는 필지"만 담는다. 그리고 `building.pnu` 는 `parcel` 을
참조하므로(FK), 그 표의 행수는 **반드시** `count(distinct building.pnu)` 와 같아야 한다.
두 수가 다르면 = 건물이 늘었는데 요약표를 안 갱신했다는 뜻이다. 추측이 아니라 등식이다.

사용
----
    python scripts/post_load.py            # 통계 + 요약표 갱신 (그리고 결과 재확인)
    python scripts/post_load.py --check    # 갱신이 필요한 상태인지만 본다 (DB 쓰기 0)

`--check` 는 낡았으면 **종료 코드 1** 로 끝난다 — 다른 스크립트·CI 가 받아 쓸 수 있게.
"""

import os
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_district_geojson  # noqa: E402  (지도 파일의 형식·SQL 은 굽는 쪽이 주인이다)
import dbx  # noqa: E402  (같은 폴더의 접속 정보 해석기를 그대로 쓴다)

# 대량 적재의 영향을 받는 표만 고른다. 전부 다 돌리면 느리기만 하고 얻는 게 없다.
ANALYZE_TABLES = (
    "parcel",
    "unit_business",
    "building",
    "building_floor",
    "unit",
    "transaction",
)

# ⚠️ **순서가 중요하다.** mv_open_sigungu 는 mv_search_parcel 에서 만들어지므로
#    반드시 그 뒤에 갱신해야 한다. 순서를 바꾸면 새 구가 목록에 한 박자 늦게 나타난다.
# ⛔ 2026-08-13 2차 적대검증에서 **mv_open_sigungu 가 통째로 빠져 있던 것**을 잡았다.
#    그러면 새 구에 건물이 들어와도 화면의 지역 목록에 안 나타나 **고를 수도, 검색할
#    수도 없다**(에러는 안 난다 — 그냥 그 지역이 없는 것처럼 보인다).
# ⚠️ mv_sigungu_tx_stats(Stage A · 결정 0012)는 앞의 둘과 의존관계가 없지만, **창(24개월)이
#    갱신하는 순간에 정해져 굳는다.** 안 돌리면 화면의 구 단가가 옛 창을 계속 말한다
#    (에러는 안 난다 — 새 거래를 넣어도 숫자가 그대로다).
# ⚠️ mv_coverage_stats(각주 집계 사전계산 · 2026-08-22d)는 **mv_open_sigungu 를 읽는다**
#    ("서비스 지역만 센다") — 반드시 그 뒤에 와야 한다. 앞에 두면 구가 늘어난 날 각주만
#    한 박자 낡은 범위를 센다. 안 돌리면 각주 숫자가 옛 적재 때 값에 굳는다(에러 0).
REFRESH_MVS = (
    "mv_search_parcel",
    "mv_open_sigungu",
    "mv_sigungu_tx_stats",
    "mv_coverage_stats",
)
SEARCH_MV = REFRESH_MVS[0]


def build_analyze_sql(tables=ANALYZE_TABLES):
    """통계 + **가시성 지도**를 갱신한다 (순수 함수 — 테스트가 여기만 보면 된다).

    ⛔ `analyze` 만으로는 부족하다. 대량 적재 뒤에는 **가시성 지도(visibility map)**
       가 낡아, 인덱스만 읽으면 되는 조회(Index Only Scan)가 **행마다 힙을 다시 방문**한다.
       그건 통계 문제가 아니라 `vacuum` 이 해 주는 일이다.

    2026-08-13 실측 — 전국 시드 뒤 각주 뷰(v_coverage_stats):
        vacuum 전 : Heap Fetches 232,890 · 버퍼 36,157 · 956ms
        vacuum 후 : Heap Fetches **0**    · 버퍼 2,650  · 화면 0.31초
    08-11 에 커버링 인덱스로 고쳐 뒀던 것이 대량 적재 한 번에 되돌아가 있었다.
    """
    return "\n".join("vacuum (analyze) {};".format(t) for t in tables)


def build_refresh_sql(mvs=REFRESH_MVS):
    """요약표 갱신문 (여러 개를 **적힌 순서대로**).

    ⚠️ `concurrently` 가 핵심이다. 없으면 갱신이 끝날 때까지 **그 표를 읽는 검색이 통째로
       잠긴다**. 대신 대상마다 unique 인덱스가 있어야 한다(idx_msp_pnu · idx_mos_sigungu).
    """
    if isinstance(mvs, str):
        mvs = (mvs,)
    return "\n".join("refresh materialized view concurrently {};".format(m) for m in mvs)


def build_freshness_sql(mv=SEARCH_MV):
    """요약표 행수와 '있어야 할 행수'를 한 줄로 뽑는다."""
    return (
        "select (select count(*) from {})::text || '|' || "
        "(select count(distinct pnu) from building)::text;".format(mv)
    )


def is_stale(mv_rows, expected_rows):
    """낡았는가. 같으면 신선, 다르면 낡음 (많아도 적어도 문제다)."""
    return int(mv_rows) != int(expected_rows)


def query_one(sql):
    """값 한 줄만 받아온다 (psql -tA). 실패하면 예외."""
    args, password = dbx.parts()
    env = dict(os.environ)
    env["PGPASSWORD"] = password           # ⚠️ 명령줄 노출 금지 (dbx.py 와 같은 이유)
    env["PGCLIENTENCODING"] = "UTF8"
    cmd = ["psql"] + args + ["-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql]
    out = subprocess.check_output(cmd, env=env, stderr=subprocess.STDOUT)
    return out.decode("utf-8", "replace").strip()


def report_freshness():
    """신선도를 재서 (mv행수, 있어야할행수, 낡음여부) 를 돌려주고 사람 말로 찍는다."""
    raw = query_one(build_freshness_sql())
    mv_rows, expected = raw.split("|")
    stale = is_stale(mv_rows, expected)
    if stale:
        print("[낡음] 검색 요약표 {}행 / 있어야 할 행수 {}행 — 갱신이 필요합니다."
              .format(mv_rows, expected))
        print("       이대로 두면 새로 넣은 건물이 검색에 안 나옵니다(에러는 안 납니다).")
    else:
        print("[신선] 검색 요약표 {}행 = 건물의 고유 필지 수 {}행.".format(mv_rows, expected))
    return mv_rows, expected, stale


# ── 지도 상권 파일 신선도 (2026-08-14 신설 — 결정 0010) ─────────────────────
#
# 지도에 그리는 상권 면은 DB 가 아니라 **구워 둔 정적 파일**(public/districts.geojson)
# 에서 읽는다(CLAUDE.md 성능 원칙). 그래서 상권을 새로 적재하고 파일 굽기를 잊으면
# **지도만 옛날 상권을 계속 보여준다** — 에러는 안 난다. 여기서도 등식으로 잡는다:
# 파일 meta 의 (행수 · 자료 시각) == 라이브 district 의 (count · max(computed_at)).
#
# ⚠️ 이 스크립트는 파일을 **자동으로 굽지 않는다.** 그 파일은 git 에 커밋하는 자산이라
#    사람이 보고 커밋해야 한다 — 여기서는 "낡았다"고 알리고 명령을 안내만 한다.


def is_map_stale(meta, live_cnt, live_max):
    """지도 파일이 낡았는가 (순수 함수 — 테스트가 여기만 보면 된다).

    파일이 아예 없으면(meta=None) **낡음**으로 본다. "없으니 검사할 게 없다"고 넘어가면
    지도가 통째로 비어 있는 상태를 정상이라고 보고하게 된다.
    """
    if not meta:
        return True
    try:
        cnt = int(meta.get("district_cnt"))
    except (TypeError, ValueError):
        return True          # 형식이 깨졌으면 믿을 수 없으니 낡은 것으로 친다
    if cnt != int(live_cnt):
        return True
    return str(meta.get("max_computed_at") or "") != str(live_max or "")


def report_map_freshness():
    """지도 파일과 라이브를 대조해 (meta, 낡음여부) 를 돌려주고 사람 말로 찍는다."""
    meta = build_district_geojson.read_meta()
    live_cnt, live_max = build_district_geojson.parse_meta_row(
        query_one(build_district_geojson.build_meta_sql()))
    stale = is_map_stale(meta, live_cnt, live_max)
    if stale:
        if meta is None:
            print("[낡음] 지도 상권 파일이 없습니다 — 라이브 상권은 {}개입니다."
                  .format(live_cnt))
        else:
            print("[낡음] 지도 상권 파일 {}개(자료 시각 {}) / 라이브 {}개({}) — 다릅니다."
                  .format(meta.get("district_cnt"), meta.get("max_computed_at"),
                          live_cnt, live_max))
        print("       이대로 두면 지도가 옛날 상권을 계속 보여줍니다(에러는 안 납니다).")
        print("       python scripts/build_district_geojson.py 를 실행한 뒤 커밋하세요.")
    else:
        print("[신선] 지도 상권 파일 {}개 = 라이브 상권 {}개.".format(
            meta.get("district_cnt"), live_cnt))
    return meta, stale


# ── 실거래 단가 창 신선도 (2026-08-15 신설 — 결정 0012 Stage A) ─────────────
#
# mv_sigungu_tx_stats 의 "최근 24개월" 창은 **갱신하는 순간** 계산돼 그대로 굳는다.
# 자료가 안 들어와 이 스크립트를 오래 안 돌리면, 화면 문구의 "최근 24개월" 쪽만
# 조용히 낡는다(뒤에 붙는 실제 시작 달은 window_from 이 말해 줘 항상 사실이다).
# 독립 리뷰(2026-08-15)가 잡은 구멍 — 여기서도 등식으로 잡는다:
# 표에 굳은 window_from == 오늘(KST) 기준 기대 시작 달 (경계 1개월 오차는 정상).

KST = ZoneInfo("Asia/Seoul")
TX_WINDOW_MONTHS = 24


def expected_tx_window_from(now=None):
    """오늘(KST) 기준 창 시작 달(YYYYMM). matview 가 재는 것과 같은 자다."""
    now = now or datetime.now(KST)
    idx = now.year * 12 + (now.month - 1) - TX_WINDOW_MONTHS
    return "{:04d}{:02d}".format(idx // 12, idx % 12 + 1)


def is_tx_window_stale(window_from, expected):
    """창이 낡았는가 (순수 함수 — 테스트가 여기만 보면 된다).

    빈 표(window_from 없음)·형식 깨짐은 낡음이다. 갱신 직후에도 달이 바뀌면 1개월
    차이가 날 수 있어 **1개월까지는 신선**으로 본다(월말·월초 경계의 정상 오차).
    연 경계(202412↔202501)를 문자열 뺄셈으로 재면 오판하므로 달 인덱스로 잰다.
    """
    s = str(window_from or "").strip()
    if len(s) != 6 or not s.isdigit():
        return True

    def _idx(ym):
        return int(ym[:4]) * 12 + int(ym[4:]) - 1

    try:
        return abs(_idx(s) - _idx(str(expected))) > 1
    except (TypeError, ValueError):
        return True


def report_tx_window_freshness():
    """실거래 단가 표의 창을 오늘과 대조해 (창, 기대, 낡음여부) 를 돌려주고 사람 말로 찍는다."""
    got = query_one("select coalesce(max(window_from), '') from mv_sigungu_tx_stats;")
    expected = expected_tx_window_from()
    stale = is_tx_window_stale(got, expected)
    if stale:
        if not got:
            print("[낡음] 실거래 단가 표가 비어 있습니다 — 갱신이 필요합니다.")
        else:
            print("[낡음] 실거래 단가 창 {} / 오늘 기준 기대 {} — 오래 갱신하지 않았습니다."
                  .format(got, expected))
        print("       이대로 두면 화면의 \"최근 24개월\" 문구만 조용히 낡습니다(에러는 안 납니다).")
        print("       python scripts/post_load.py 를 실행하면 창이 오늘 기준으로 다시 잡힙니다.")
    else:
        print("[신선] 실거래 단가 창 {} = 오늘 기준 {}개월.".format(got, TX_WINDOW_MONTHS))
    return got, expected, stale


# ── 공개키(anon)가 읽어도 되는 것 ──────────────────────────────────────────
# 화면이 실제로 읽는 것만 적는다. 이 목록에 없는 것이 열려 있으면 사고다.
#
# ⛔ 왜 이 점검이 있나 (2026-08-13 실제 사고)
#    새로 만든 물질화뷰 2개가 **자동으로** anon 에게 열렸다. Supabase 가 스키마 public 에
#    기본 권한을 걸어 두기 때문이고, 2026-08-08 의 `revoke ... on all tables` 는 그때
#    있던 것만 닫는 일회성 명령이었다. 실측: `GET /rest/v1/mv_search_parcel?limit=3` 이
#    200 + 188,442행 카운트까지 가능 — 검색 상한 게이트를 페이지네이션으로 통째로
#    건너뛸 수 있었다. **정적 검사(schema.sql 에 revoke 가 적혀 있나)로는 이걸 못 잡는다**
#    — 라이브에 실제로 뭐가 열려 있는지 물어봐야 한다.
ANON_READABLE_ALLOWLIST = ("v_floor_stack", "v_coverage_stats")

# anon 이 **불러도 되는** 함수. 화면이 실제로 쓰는 것만.
ANON_CALLABLE_ALLOWLIST = (
    "search_buildings", "search_scope", "list_open_sigungu", "list_building_districts",
    # Stage A 실거래 표시(결정 0012). 물질화뷰 mv_sigungu_tx_stats 는 **여기 없다** —
    # 화면은 함수로만 읽고, 표 자체가 열리면 그건 사고다.
    "list_parcel_transactions", "get_sigungu_tx_stats",
    # Stage B 참고 시세 밴드(결정 0013). 게이트 표 price_gate_sigungu 와 층대 도우미
    # price_floor_band 는 **여기 없다** — 화면은 이 함수 하나로만 읽는다.
    "list_price_bands",
)


def build_anon_exposure_sql():
    """anon 이 읽거나 부를 수 있는 **우리 것**을 나열한다.

    ⚠️ 표·뷰만 보면 안 된다 — **함수도 자동으로 열린다.** 2026-08-13 2차 검증에서
       `unit_business_append_only`(트리거용)가 anon 에게 열려 있는 것을 그렇게 찾았다.

    ⛔ 그런데 함수를 그냥 다 세면 **PostGIS·pg_trgm 이 딸고 오는 수백 개**가 전부 걸려
       "사고" 목록이 스크롤을 채운다. 그러면 진짜 사고가 그 안에 묻힌다(경보 피로).
       그래서 **확장(extension)이 만든 것은 제외**한다 — `pg_depend.deptype='e'` 가
       "이 객체는 확장의 일부"라는 뜻이다. 남는 것이 곧 **우리가 만든 것**이다.
    """
    not_from_extension = (
        "not exists (select 1 from pg_depend d "
        "where d.objid = {oid} and d.deptype = 'e')"
    )
    return (
        "select c.relname from pg_class c "
        "join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relkind in ('r','v','m','p') "
        "and has_table_privilege('anon', c.oid, 'SELECT') "
        "and " + not_from_extension.format(oid="c.oid") + " "
        "union all "
        "select p.proname from pg_proc p "
        "join pg_namespace n2 on n2.oid = p.pronamespace "
        "where n2.nspname = 'public' "
        "and has_function_privilege('anon', p.oid, 'EXECUTE') "
        "and " + not_from_extension.format(oid="p.oid") + ";"
    )


def unexpected_anon_readables(names, allowlist=None):
    """허용 목록에 없는데 열려 있는 것 (순수 함수 — 테스트가 여기만 보면 된다).

    ⚠️ psql 출력에는 빈 줄·공백 줄이 섞인다. `if n` 만으로는 공백 줄(' ')이 통과해
       이름인 척하므로 반드시 strip 후 판정한다.
    """
    allowed = set(allowlist if allowlist is not None
                  else ANON_READABLE_ALLOWLIST + ANON_CALLABLE_ALLOWLIST)
    return sorted({n.strip() for n in names if n and n.strip() and n.strip() not in allowed})


def report_anon_exposure():
    """공개키가 읽을 수 있는 것을 실제로 물어보고 사람 말로 찍는다."""
    raw = query_one(build_anon_exposure_sql())
    names = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    bad = unexpected_anon_readables(names)
    if bad:
        print("[사고] 공개키에게 열리면 안 되는 것이 열려 있습니다: {}".format(", ".join(bad)))
        print("       → revoke all on <이름> from public, anon, authenticated; 를 적용하고")
        print("         supabase/schema.sql 에도 같이 반영하세요.")
    else:
        print("[정상] 공개키가 읽거나 부를 수 있는 것은 허용된 {}개뿐입니다.".format(len(names)))
    return names, bad


def parse_args(argv):
    opts = {"check": False}
    for a in argv:
        if a == "--check":
            opts["check"] = True
        else:
            raise ValueError("알 수 없는 인자: {!r}  (쓸 수 있는 것: --check)".format(a))
    return opts


def main(argv=None):
    opts = parse_args(list(sys.argv[1:] if argv is None else argv))

    if opts["check"]:
        _, _, stale = report_freshness()
        _, map_stale = report_map_freshness()
        _, _, tx_stale = report_tx_window_freshness()
        _, exposed = report_anon_exposure()
        return 1 if (stale or map_stale or tx_stale or exposed) else 0

    print("통계·가시성 지도를 갱신합니다 (VACUUM ANALYZE {}개 표)…".format(len(ANALYZE_TABLES)))
    rc = dbx.run_sql("set statement_timeout = '600s';\n" + build_analyze_sql(), quiet=True)
    if rc != 0:
        print("[실패] VACUUM ANALYZE 가 실패했습니다.")
        return rc

    print("검색 요약표를 갱신합니다 ({}개)…".format(len(REFRESH_MVS)))
    rc = dbx.run_sql("set statement_timeout = '600s';\n" + build_refresh_sql(), quiet=True)
    if rc != 0:
        print("[실패] 요약표 갱신이 실패했습니다.")
        return rc

    # 했다고 믿지 않고 다시 잰다.
    _, _, stale = report_freshness()

    # 지도 파일은 **여기서 굽지 않는다** — 커밋이 필요한 자산이라 사람이 봐야 한다.
    # 낡았으면 알리고 명령만 안내한다.
    _, map_stale = report_map_freshness()
    # 방금 갱신했으니 창도 오늘 기준이어야 한다 — 했다고 믿지 않고 다시 잰다.
    _, _, tx_stale = report_tx_window_freshness()
    return 1 if (stale or map_stale or tx_stale) else 0


if __name__ == "__main__":
    sys.exit(main())
