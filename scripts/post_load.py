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
  · 각주 집계(mv_coverage_stats) 갱신을 빼먹으면 → **화면 각주만 옛 분기의 결측률을
    계속 말한다.** 2026-08-22d 부터 그 값을 미리 계산해 두기 때문이다(실시간 집계는
    277만 행 대조로 2~5초가 걸려 공개 호출의 3초 제한을 넘나들었다). 미리 계산해 두는
    대가는 정확히 이것 하나뿐이라, 아래 report_coverage_freshness() 가 등식으로 잡는다.
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
# ⚠️ mv_district_industry_mix(둘레의 업종 분포 · 결정 0014)도 갱신이 **유일한** 최신화
#    수단이다. 이 표는 "최신 분기"를 담는데, 그 분기가 무엇인지는 **구울 때** 정해져
#    굳는다. 새 분기를 적재하고 이걸 안 돌리면 업종 분포만 옛 분기를 계속 말한다(에러 0).
#    아래 report_industry_mix_freshness() 가 그 어긋남을 등식으로 잡는다.
#    (앞의 것들과 의존관계는 없다 — 순서는 "먼저 만들어진 것부터"일 뿐이다.)
REFRESH_MVS = (
    "mv_search_parcel",
    "mv_open_sigungu",
    "mv_sigungu_tx_stats",
    "mv_coverage_stats",
    "mv_district_industry_mix",
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


# ── 업종 분포 표 신선도 (2026-08-22 신설 — 결정 0014) ──────────────────────
#
# mv_district_industry_mix 는 "최신 분기"를 담는데, **어느 분기가 최신인지는 구울 때
# 정해져 굳는다.** 새 분기를 적재하고 갱신을 안 하면 층별 화면의 업종 분포만 옛 분기를
# 계속 말한다 — 에러는 안 나고, 화면에 적히는 "2026년 2분기 기준"도 그 옛 분기를 정직히
# 말하므로 **아무도 눈치채지 못한다**(다른 블록은 최신 분기를 쓰는데 여기만 뒤처진다).
#
# 앞의 두 점검과 같은 방식이다 — 표에 굳은 값 == 지금 있어야 할 값.


def is_industry_mix_stale(mix_ym, latest_ym):
    """업종 분포 표가 낡았는가 (순수 함수 — 테스트가 여기만 보면 된다).

    빈 표(굽지 않음)는 낡음이다 — 화면에서 섹션이 통째로 사라지는데, 그건 정상이 아니다.

    ⚠️ **원본이 빈 경우의 판정이 형제(is_coverage_stale)와 일부러 반대다.** 여기서는
       '낡지 않음', 저기서는 '낡음'이다. 까닭은 두 표가 없을 때 화면이 겪는 일이 다르기
       때문이다:
         · 각주 집계 — 점포 자료가 없으면 각주 숫자 자체를 못 만든다. 화면이 기대하는
           값이 비는 것이라 알려야 한다.
         · 업종 분포 — 점포 자료가 없으면 **애초에 셀 것이 없다.** 이 섹션은 자기가 알아서
           사라지도록 만들어져 있고(그게 설계된 정상 동작이다), 그 상태로 경보를 내면
           자료를 아직 안 넣은 새 환경에서 --check 가 영원히 1 을 돌려준다.
       즉 "견줄 기준이 없을 때 무엇이 정상인가"가 두 표에서 다르다. 통일하지 말 것.
    """
    mix = str(mix_ym or "").strip()
    latest = str(latest_ym or "").strip()
    if not latest:
        return False
    return mix != latest


def report_industry_mix_freshness():
    """업종 분포 표의 분기를 점포 자료의 최신 분기와 대조한다."""
    raw = query_one(
        "select coalesce((select max(snapshot_ym) from mv_district_industry_mix), '')"
        " || '|' || coalesce((select max(snapshot_ym) from unit_business), '');"
    )
    # partition 을 쓴다 — split 은 값에 '|' 가 섞이면 "unpack 3 into 2" 로 죽는다
    # (형제 report_coverage_freshness 와 같은 방식으로 맞춘다).
    mix_ym, _, latest_ym = raw.partition("|")
    mix_ym, latest_ym = mix_ym.strip(), latest_ym.strip()
    stale = is_industry_mix_stale(mix_ym, latest_ym)
    if stale:
        if not mix_ym:
            print("[낡음] 업종 분포 표가 비어 있습니다 — 갱신이 필요합니다.")
        else:
            print("[낡음] 업종 분포 표 {} / 점포 자료 최신 {} — 갱신이 필요합니다."
                  .format(mix_ym, latest_ym))
        print("       이대로 두면 층별 화면의 업종 분포만 옛 분기를 말합니다(에러는 안 납니다).")
        print("       python scripts/post_load.py 를 실행하면 최신 분기로 다시 굽습니다.")
    else:
        print("[신선] 업종 분포 표 {} = 점포 자료 최신 분기.".format(mix_ym or "(자료 없음)"))
    return mix_ym, latest_ym, stale


# ── 각주 집계 신선도 (2026-08-22d 신설 — 사전계산의 유일한 대가) ─────────────
#
# mv_coverage_stats 는 **갱신하는 순간 계산돼 그대로 굳는다.** 미리 계산해 두는 값이
# 치르는 대가는 정확히 하나 — 갱신을 잊으면 조용히 낡는다. 새 분기를 적재하고 이
# 스크립트를 안 돌리면 화면 각주만 옛 분기의 결측률을 계속 말한다(에러는 안 난다).
# 그러니 등식으로 잡는다: 표에 굳은 snapshot_ym == unit_business 의 최신 snapshot_ym.
#
# ⚠️ **이 검사가 못 보는 것** — 같은 분기 안에서 행이 늘거나 열린 구가 늘어난 경우.
#    그걸 정확히 재려면 결국 우리가 없앤 그 무거운 집계(~2~5초)를 다시 돌려야 한다.
#    갱신이 필요해지는 사유의 대부분이 "새 분기"라, 싸고 확실한 쪽만 본다.
#    (열린 구가 느는 경로는 적재 → post_load 한 세트라 어차피 여기서 같이 갱신된다.)


def build_coverage_freshness_sql():
    """표에 굳은 분기와 원본의 최신 분기를 한 줄로 뽑는다."""
    return (
        "select coalesce((select max(snapshot_ym) from mv_coverage_stats), '') || '|' || "
        "coalesce((select max(snapshot_ym) from unit_business), '');"
    )


def is_coverage_stale(mv_ym, live_ym):
    """각주 집계가 낡았는가 (순수 함수 — 테스트가 여기만 보면 된다).

    빈 표(mv_ym 없음)는 낡음이다. "없으니 검사할 게 없다"고 넘어가면 각주가 통째로
    비어 있는 상태를 정상이라고 보고하게 된다(is_map_stale 과 같은 판단).
    원본이 비어 있는 경우(live_ym 없음)도 낡음으로 본다 — 대조할 기준이 없으면
    "신선하다"고 말할 근거도 없다.
    """
    got = str(mv_ym or "").strip()
    live = str(live_ym or "").strip()
    if not got or not live:
        return True
    return got != live


def report_coverage_freshness():
    """각주 집계 표를 원본과 대조해 (표분기, 원본분기, 낡음여부) 를 돌려주고 사람 말로 찍는다."""
    mv_ym, _, live_ym = query_one(build_coverage_freshness_sql()).partition("|")
    mv_ym, live_ym = mv_ym.strip(), live_ym.strip()
    stale = is_coverage_stale(mv_ym, live_ym)
    if stale:
        if not mv_ym:
            print("[낡음] 각주 집계 표가 비어 있습니다 — 갱신이 필요합니다.")
        else:
            print("[낡음] 각주 집계 분기 {} / 점포 원본 최신 분기 {} — 다릅니다."
                  .format(mv_ym, live_ym or "(없음)"))
        print("       이대로 두면 화면 각주가 옛 분기의 결측률을 계속 말합니다(에러는 안 납니다).")
        print("       python scripts/post_load.py 를 실행하면 오늘 자료 기준으로 다시 잡힙니다.")
    else:
        print("[신선] 각주 집계 분기 {} = 점포 원본 최신 분기.".format(mv_ym))
    return mv_ym, live_ym, stale


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
#
# ⚠️ **이름은 이제 `스키마.이름`으로 적는다(2026-09-01 감사 신설).** 예전엔 이름만 보고
#    판정해서 `api.search_buildings`(의도된 노출)와 `public.search_buildings`(잔존 노출 —
#    아래 ANON_CALLABLE_PENDING 참조)가 **같은 이름이라는 이유로 하나로 묶여**, 뒤엣것이
#    앞엣것 뒤에 3주 넘게 조용히 숨어 있었다. 스키마까지 적으면 그 둘은 서로 다른 항목이
#    되어 다시는 서로를 가려주지 못한다.
ANON_READABLE_ALLOWLIST = (
    "public.v_floor_stack", "api.v_floor_stack",
    "public.v_coverage_stats", "api.v_coverage_stats",
)

# anon 이 **불러도 되는** 함수. 화면이 실제로 쓰는 것만.
# ⚠️ 전부 `api.` 스키마다 — 화면(src/lib/appConstants.ts 등)이 REST 로 부르는 것은 이제
#    api 스키마 래퍼뿐이고, 같은 이름의 `public.*` 원본은 **여기 없다**(그게 열려 있으면
#    아래 ANON_CALLABLE_PENDING 이 알려진 백로그로 따로 담는다 — 허용이 아니다).
ANON_CALLABLE_ALLOWLIST = (
    "api.search_buildings", "api.search_scope", "api.list_open_sigungu",
    "api.list_building_districts",
    # Stage A 실거래 표시(결정 0012). 물질화뷰 mv_sigungu_tx_stats 는 **여기 없다** —
    # 화면은 함수로만 읽고, 표 자체가 열리면 그건 사고다.
    "api.list_parcel_transactions", "api.get_sigungu_tx_stats",
    # Stage B 참고 시세 밴드(결정 0013). 게이트 표 price_gate_sigungu 와 층대 도우미
    # price_floor_band 는 **여기 없다** — 화면은 이 함수 하나로만 읽는다.
    "api.list_price_bands",
    # 둘레의 업종 분포(결정 0014). 사전계산표 mv_district_industry_mix 는 **여기 없다** —
    # 그 표가 열리면 상호명은 안 나가더라도 상권별 점포 구성이 통째로 긁힌다.
    "api.list_industry_mix", "api.list_industry_detail",
    # 의견함·오류 기록(2026-08-24b). ⚠️ **이 목록에서 유일하게 쓰는 함수다** — 나머지 아홉은
    # 전부 읽기다. 그래서 여는 뜻이 다르다는 것을 여기 적어 둔다:
    #   · 표 app_feedback 은 **여기 없다** — anon 에게 통째로 닫혀 있다(select·insert 전부).
    #     넣기는 이 함수가 소유자 권한으로 대신 한다. 표가 열리면 그건 사고다.
    #   · 읽는 함수는 만들지 않았다. 넣은 사람도 자기 글을 다시 못 본다.
    "api.submit_feedback",
    # 의견함 주간 알림(2026-08-24c). 화면이 아니라 GitHub Actions 주간 워크플로가
    # 공개키로 부른다 — **숫자만** 준다(건수·총량·가장 오래된 글의 나이).
    #   ⛔ body·context 는 어떤 칸으로도 안 나간다. 내용은 여전히 dbx.py 로만 읽는다.
    #   ⛔ 지우는 함수(purge_old_feedback)는 **여기 없다** — 일부러 안 열었다. 밖에서
    #      부를 수 있으면 지금은 무해해도 "유연성"으로 인자가 붙는 날 파괴 창구가 된다.
    #      치우기는 편지가 들어올 때 submit_feedback 이 소유자 권한으로 스스로 한다.
    "api.get_feedback_stats",
    # 국세청 층별 기준시가(2026-08-27a). 표 nts_base_price 는 **여기 없다** — anon 에게
    # 통째로 닫혀 있고, 열리면 전국 249만 호실의 건물명·호수가 그대로 긁힌다.
    # 화면은 이 함수 하나로만 읽고, 그것도 층별 중앙값까지만 나간다(호실별 값은 안 나간다).
    "api.list_base_prices",
    # LH 상가 공고 알림판(2026-08-28a). 표 lh_notice 는 **여기 없다** — 화면은 이 함수
    # 하나로만 읽는다. 함수가 마감 지난 공고를 빼 주는데 표가 열리면 그 규칙이 통째로
    # 우회돼, 이미 끝난 공고가 화면에 뜨는 길이 생긴다.
    "api.list_lh_notices",
    # 곧 올라오는 상가 건물(2026-08-28b). 표 arch_permit 은 **여기 없다** — 열리면 전국
    # 55만 건의 허가 주소·건물 규모가 통째로 긁힌다. 이 함수는 **개수와 기준월만** 준다
    # (건물 주소·이름은 한 글자도 안 나간다).
    "api.count_nearby_permits",
    # 상권 임대 동향(2026-08-31a · 결정 0024). 표 rent_stat 과 이름 잇기 표
    # district_rone_map 은 **여기 없다** — 화면은 이 함수 하나로만 읽는다. 표가 열리면
    # 전국 상권의 임대 통계가 통째로 긁히고, "이을 근거가 없으면 줄이 없다"는 규칙
    # (시·도 평균으로 안 메운다)도 함께 우회된다.
    "api.list_rent_stats",
    # 상권 → 건물 다리(2026-08-31b · Wave 3). 표 district·parcel·building 은 **여기 없다** —
    # 화면은 이 두 함수로만 읽는다. district 가 열리면 상권 경계(geom)가 통째로 긁히고,
    # building 이 열리면 전국 24만 동의 대장 정보가 그대로 나간다.
    #   ⛔ 점포는 **땅 단위 개수**만 나간다 — 상호명·업종은 한 글자도 안 나간다.
    #   ⓘ 같은 이름의 public 쪽 함수는 이 목록에 없다 — 스키마까지 보므로 api 쪽만 열려
    #      있어도 정확히 그것만 통과한다(예전 이름 기준 판정의 구멍이 여기서 막힌다).
    "api.list_district_buildings", "api.list_parcel_buildings",
    # 성적표 공개(2026-09-05e · 로드맵 Wave 4). 표 price_gate_sigungu 는 **여기 없다** —
    # 화면은 이 함수 하나로만 읽는다. 나가는 것은 **구별 요약 한 줄씩**(짝지은 거래 수와
    # 두 방법의 오차 중앙값)이고, 검증 거래 하나하나(필지·층·단가)는 그 표에 아예 없다.
    "api.list_price_gate",
    # 이 자료는 언제 것인가(2026-09-05d). 나가는 것은 열 갈래 자료의 **max() 도장뿐**이라
    # 원본 행은 한 줄도 안 나간다. ⛔ api_quota_log 는 쳐다보지도 않는다(호출 장부이지
    # 자료의 나이가 아니고, 하한선일 뿐이라 신선도 근거로 쓰면 틀린 날짜를 자신 있게 적는다).
    "api.get_data_freshness",
)

# ── 공개키가 아직 못 닫은 "대기" 함수 — 지금은 비어 있다 ─────────────────
#
# ✅ **닫힘 이력** — 2026-09-01 감사가 찾은 잔존 노출 9개는 마이그레이션
#    **2026-09-05a** 로 닫혔다(get_sigungu_tx_stats·list_building_districts·
#    list_industry_detail·list_industry_mix·list_open_sigungu·list_parcel_transactions·
#    list_price_bands·search_buildings·search_scope 의 **public** 원본).
# ⓘ **왜 열려 있었나** — PostgreSQL 은 새 함수에 PUBLIC EXECUTE 를 기본으로 준다
#    (공식 문서 §5.8 표 5.2). 그 기본값을 막는 전역 한 줄은 2026-09-01b 에서야 들어갔고,
#    기본권한은 "앞으로"에만 걸려서 그보다 먼저 태어난 아홉은 손으로 닫을 수밖에 없었다.
#
# ⚠️ **비어 있는 것이 정상이다 — 여기에 이름을 다시 더하지 말 것.** 이 목록은 "알고
#    있지만 결재 때문에 아직 못 닫은 것"을 [주의]로 내려 exit 1 을 면제해 주는 장치다.
#    앞으로 새 누출이 보이면 그건 백로그가 아니라 **[사고]** 다 — 여기 적어 넣으면
#    빨간불이 꺼져 그 누출이 잠긴다. 닫는 것이 먼저다.
#
# ⓘ 명단은 비워도 **상수는 지우지 않는다** — report_anon_exposure() 가 이 목록을
#    돌며 "대기 목록에 있는데 지금은 안 열린 것"을 [정리] 로 알려 주는 장치가
#    그대로 돌아야 하고, tests/test_post_load.py 가 이 상수를 직접 읽는다.
ANON_CALLABLE_PENDING = ()


def _bare_names(qualified):
    """`스키마.이름` 튜플에서 **맨 이름만** 뽑는다 (순수 함수 — 첫 등장 순서로 중복 제거).

    ⚠️ 다른 파일(tests/test_api_schema_migration.py)이 `api.<이름>` 형태의 마이그레이션
       정규식과 맞대 보려고 맨 이름이 필요해서 여기서 파생해 준다. **손으로 다시 적지
       말 것** — 위 두 허용 목록에서 파생해야 이름을 더하거나 뺄 때 두 목록이 갈라지지
       않는다(따로 적으면 드리프트가 나고, 실패 메시지가 "허용 목록에 없다"만 말해
       진짜 원인인 스키마 접두어 불일치를 가린다).
    """
    seen = []
    for q in qualified:
        bare = q.split(".", 1)[1] if "." in q else q
        if bare not in seen:
            seen.append(bare)
    return tuple(seen)


# ANON_READABLE_ALLOWLIST·ANON_CALLABLE_ALLOWLIST 의 맨 이름 버전. 뷰는 public·api 두
# 스키마에 같은 이름으로 열려 있어 4개 → 2개로 줄어드는 게 정상이다(v_floor_stack·
# v_coverage_stats). 함수는 api.* 만 허용이라 17개 그대로 나온다.
ANON_READABLE_NAMES = _bare_names(ANON_READABLE_ALLOWLIST)
ANON_CALLABLE_NAMES = _bare_names(ANON_CALLABLE_ALLOWLIST)


def build_anon_exposure_sql():
    """anon 이 읽거나 부를 수 있는 **우리 것**을 나열한다.

    ⚠️ 표·뷰만 보면 안 된다 — **함수도 자동으로 열린다.** 2026-08-13 2차 검증에서
       `unit_business_append_only`(트리거용)가 anon 에게 열려 있는 것을 그렇게 찾았다.

    ⛔ 그런데 함수를 그냥 다 세면 **PostGIS·pg_trgm 이 딸고 오는 수백 개**가 전부 걸려
       "사고" 목록이 스크롤을 채운다. 그러면 진짜 사고가 그 안에 묻힌다(경보 피로).
       그래서 **확장(extension)이 만든 것은 제외**한다 — `pg_depend.deptype='e'` 가
       "이 객체는 확장의 일부"라는 뜻이다. 남는 것이 곧 **우리가 만든 것**이다.

    ⚠️ 스키마가 **둘**이다(2026-08-22e). REST 노출면이 public 에서 api 로 옮겨 가는데,
       api 만 보면 전환 전 상태를 못 보고 public 만 보면 전환 후 상태를 못 본다.
       둘 다 물어야 **어느 시점에 돌려도** 같은 답을 준다.

    ⚠️ **이름만이 아니라 `스키마.이름`을 돌려준다(2026-09-01 감사 신설).** 예전엔
       `c.relname`/`p.proname` 만 돌려줬는데, 그러면 `api.search_buildings`(의도된
       노출)와 `public.search_buildings`(잔존 노출)가 **같은 문자열**이 되어 허용
       목록의 중복 제거 로직이 뒤엣것을 앞엣것 뒤에 가려 버렸다(라이브에서 실제로
       3주 넘게 그렇게 숨어 있었다). 스키마를 붙이면 둘은 서로 다른 문자열이라
       다시는 서로를 가리지 못한다.
    """
    # ⚠️ classid 를 함께 한정한다. oid 는 카탈로그마다 따로 매겨지므로, 한정하지 않으면
    #    **번호가 우연히 같은 남의 카탈로그 항목**(예: 어떤 확장의 연산자)이 우리 표를
    #    "확장이 만든 것"으로 만들어 점검에서 통째로 빼 버릴 수 있다.
    not_from_extension = (
        "not exists (select 1 from pg_depend d "
        "where d.classid = '{cat}'::regclass and d.objid = {oid} and d.deptype = 'e')"
    )
    return (
        "select n.nspname || '.' || c.relname from pg_class c "
        "join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname in ('public','api') and c.relkind in ('r','v','m','p') "
        "and has_table_privilege('anon', c.oid, 'SELECT') "
        "and " + not_from_extension.format(cat="pg_class", oid="c.oid") + " "
        "union all "
        "select n2.nspname || '.' || p.proname from pg_proc p "
        "join pg_namespace n2 on n2.oid = p.pronamespace "
        "where n2.nspname in ('public','api') "
        "and has_function_privilege('anon', p.oid, 'EXECUTE') "
        "and " + not_from_extension.format(cat="pg_proc", oid="p.oid") + ";"
    )


# ── 공개 롤이 **고칠 수 있는** 것 (2026-08-22 독립 리뷰 B-2) ────────────────
#
# 위 읽기 점검은 허용 목록으로 판정한다. 그래서 `v_floor_stack` 처럼 목록에 있는 이름에
# INSERT·UPDATE·DELETE 가 붙어도 조용히 통과했다 — 읽혀도 되는 것과 공개키로 고쳐도
# 되는 것은 전혀 다른 이야기인데, 그 차이를 아무도 안 물어보고 있었다.

# 밖에서 키만 있으면 되는 롤 **둘 다** 본다. anon 만 재면 로그인 사용자에게만 열린
# 쓰기를 통째로 놓친다(이 앱에는 아직 로그인이 없지만, 생기는 날 조용히 새는 자리다).
WRITE_ROLES = ("anon", "authenticated")
WRITE_PRIVS = ("INSERT", "UPDATE", "DELETE")

# 이미 알고 있고 **우리 권한으로는 못 고치는** 노출. PostGIS 가 extensions 가 아니라
# public 스키마에 설치돼 REST 에 그대로 딸려 나온다.
#
# ⛔ revoke 를 시도하지 말 것 — 소유자가 `supabase_admin` 이라 postgres 롤의 revoke 가
#    통하지 않는다("WARNING: no privileges could be revoked" 만 나온다). postgres 는
#    슈퍼유저가 아니고 `set role supabase_admin` 도 거부된다(2026-08-08 컨테이너 실측 —
#    근거·피해 범위·복구 절차는 supabase/migrations/2026-08-08_public_read_policy.sql §5).
#    근본 처방은 **REST 노출 스키마에서 public 을 빼는 것**이다(2026-08-22e 로 api 스키마를
#    만들어 뒀고, 노출 목록에서 public 을 내리는 것이 그 마지막 단계다).
#
# 그래서 이 셋은 종료 코드를 1 로 만들지 않는다. 대신 **매번 [주의]로 적는다** — 조용히
# 넘기면 "public 을 내리는 일"이 끝났는지 아무도 안 묻게 된다.
WRITE_KNOWN_POSTGIS = ("spatial_ref_sys", "geometry_columns", "geography_columns")

# REST 가 어느 스키마를 노출하는지의 진실은 authenticator 롤 설정이다(대시보드 화면엔
# 안 보인다 — 2026-08-22 실측). 2026-08-24 에 노출에서 public 을 뺐다(옛 문 닫기) —
# 그 뒤로 위 셋은 권한이 열린 채여도 인터넷에서 닿지 않는다. 아래 점검은 그 조치가
# 유지되는지도 함께 본다: 누가 노출에 public 을 되돌리면 [주의]가 다시 살아난다.
AUTHENTICATOR_CONFIG_SQL = (
    "select coalesce((select array_to_string(rolconfig, chr(10)) from pg_roles "
    "where rolname = 'authenticator'), '');"
)


def public_rest_exposed(rolconfig_text):
    """REST 노출 목록에 public 이 있는가 (순수 함수 — 테스트가 여기만 보면 된다).

    ⚠️ 'graphql_public' 안에도 'public' 이 글자로 들어 있다 — 부분 문자열로 찾으면
       오판하므로 쉼표로 갈라 항목 단위로 비교한다.
    설정 줄(pgrst.db_schemas=...)이 아예 없으면 **노출로 간주**한다 — Supabase 기본값이
    public 을 포함하므로, 모르는 상태를 안전하다고 말하면 안 된다.
    """
    for line in str(rolconfig_text or "").splitlines():
        line = line.strip()
        if line.startswith("pgrst.db_schemas="):
            schemas = [s.strip() for s in line.split("=", 1)[1].split(",")]
            return "public" in schemas
    return True


def build_write_exposure_sql(roles=WRITE_ROLES, privs=WRITE_PRIVS):
    """공개 롤이 쓸 수 있는 표·뷰를 나열한다.

    ⚠️ **여기에는 확장 제외 필터(deptype='e')가 없다.** 읽기 점검에는 있는데 여기만
       없는 것이 실수처럼 보이지만 정반대다 — 걸러지는 그 집합이 **정확히 실제 사고
       지점**이다(PostGIS 가 public 에 설치돼 딸려 온 spatial_ref_sys 등 셋). 읽기 쪽은
       확장 함수 수백 개가 걸려 경보 피로가 나지만, 쓰기 쪽은 라이브 실측 결과 **상수 셋**
       뿐이라 그 논리가 성립하지 않는다. 대신 위 WRITE_KNOWN_POSTGIS 로 이름을 갈라
       "알고 있는 것"과 "새로 생긴 것"을 구분한다.

    스코프의 나머지는 읽기 점검과 같다(public·api 두 스키마, 표·뷰·물질화뷰). 함수는
    EXECUTE 하나뿐이라 여기 해당이 없다.
    """
    tests = " or ".join(
        "has_table_privilege('{}', c.oid, '{}')".format(r, p) for r in roles for p in privs
    )
    return (
        "select c.relname from pg_class c "
        "join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname in ('public','api') and c.relkind in ('r','v','m','p') "
        "and (" + tests + ");"
    )


def split_writables(names, known=WRITE_KNOWN_POSTGIS):
    """(알려진 것, 처음 보는 것) 으로 가른다 (순수 함수 — 테스트가 여기만 보면 된다).

    빈 줄·공백 줄은 버린다(unexpected_anon_readables 와 같은 이유 — psql 출력에는
    공백 줄이 섞인다). 알려진 것은 [주의], 처음 보는 것은 [사고]다.
    """
    seen = sorted({n.strip() for n in names if n and n.strip()})
    return ([n for n in seen if n in known], [n for n in seen if n not in known])


def report_write_exposure():
    """공개 롤이 고칠 수 있는 것을 실제로 물어보고 사람 말로 찍는다.

    돌려주는 것은 **처음 보는 것만**이다 — 알려진 셋은 우리 손으로 못 고치므로 종료
    코드를 1 로 만들지 않는다(매번 1 이면 --check 가 쓸모없어진다). 다만 [주의]로는
    반드시 적는다.
    """
    known, bad = split_writables(query_one(build_write_exposure_sql()).splitlines())
    if bad:
        print("[사고] 공개 롤({})이 **고칠 수 있는** 것이 있습니다: {}".format(
            "·".join(WRITE_ROLES), ", ".join(bad)))
        print("       읽기 허용과 쓰기 허용은 다릅니다 — 읽기 허용 목록에 있는 이름이라도 사고입니다.")
        print("       → revoke insert, update, delete on <이름> from public, anon, authenticated;")
        print("         supabase/schema.sql 에도 같이 반영하세요.")
    else:
        # ⚠️ 그냥 "없습니다"라고 하면 아래 [주의] 셋과 앞뒤가 안 맞는다 — 범위를 밝힌다.
        print("[정상] 공개 롤이 고칠 수 있는 것은 **우리가 만든 것 중에는** 없습니다.")
    if known:
        if public_rest_exposed(query_one(AUTHENTICATOR_CONFIG_SQL)):
            print("[주의] PostGIS 가 public 에 설치돼 딸려 온 {}개가 열려 있습니다: {}".format(
                len(known), ", ".join(known)))
            print("       소유자가 supabase_admin 이라 **우리 권한으로는 회수할 수 없습니다**")
            print("       (2026-08-08 실측 — revoke 는 무효로 끝납니다. 시도하지 마세요).")
            print("       근본 처방은 REST 노출 스키마에서 public 을 빼는 것입니다 —")
            print("       2026-08-24 에 한 번 뺐으므로, 이 줄이 보인다면 누군가 되돌린 것입니다.")
        else:
            print("[정상] PostGIS 딸림 {}개({})는 권한이 열린 채지만(회수 불가 — 2026-08-08 실측),".format(
                len(known), ", ".join(known)))
            print("       REST 노출에서 public 을 빼 둬서(2026-08-24 옛 문 닫기) 인터넷에서는 닿지 않습니다.")
    return bad


def unexpected_anon_readables(names, allowlist=None):
    """허용 목록에 없는데 열려 있는 것 (순수 함수 — 테스트가 여기만 보면 된다).

    ⚠️ psql 출력에는 빈 줄·공백 줄이 섞인다. `if n` 만으로는 공백 줄(' ')이 통과해
       이름인 척하므로 반드시 strip 후 판정한다.

    ⓘ **여기서는 "허용 목록에 있나"만 본다** — ANON_CALLABLE_PENDING(알려진 백로그)에
       있는 것도 이 함수 기준으로는 여전히 "허용 안 됨"이다. [사고]/[주의]를 가르는 일은
       report_anon_exposure() 가 이 함수의 결과 위에서 한 번 더 한다. 이름은 이제
       `스키마.이름`(예: "api.search_buildings")을 전제한다(2026-09-01 감사) — 스키마
       없이 넘기면 어느 쪽에도 안 걸려 있는 것으로 보여 실제로는 열린 것을 놓칠 수 있다.
    """
    allowed = set(allowlist if allowlist is not None
                  else ANON_READABLE_ALLOWLIST + ANON_CALLABLE_ALLOWLIST)
    return sorted({n.strip() for n in names if n and n.strip() and n.strip() not in allowed})


def report_anon_exposure():
    """공개키가 읽을 수 있는 것을 실제로 물어보고 사람 말로 **세 갈래**로 찍는다.

    ⚠️ **스키마까지 봐야 잔존 노출을 잡는다(2026-09-01 감사).** 예전엔 이름 하나로 판정해서
       `api.search_buildings`(의도된 노출)와 `public.search_buildings`(잔존 노출)가 같은
       이름이라는 이유로 하나로 묶였다 — 뒤엣것이 앞엣것 뒤에 조용히 숨어 라이브에서 3주
       넘게 아무도 몰랐다. 지금은 `스키마.이름`을 통째로 비교하므로 그 둘은 서로 다른
       항목이고, 아래 세 갈래 중 어디에 속하는지가 이름만으로도 드러난다.

    세 갈래:
      · [정상] — ANON_READABLE_ALLOWLIST·ANON_CALLABLE_ALLOWLIST 에 있는 것(의도된 노출).
      · [주의] — 그 목록엔 없지만 ANON_CALLABLE_PENDING 에 있는 것(알려진 백로그 — 결재
        대기. WRITE_KNOWN_POSTGIS 와 같은 논리로 exit 1 을 만들지 않는다 — 매번 실패하면
        "알려진 것"이라는 사실이 --check 를 무쓸모하게 만든다).
      · [사고] — 어느 목록에도 없는 것. 여기만 exit 1 을 만든다.

    대기 목록이 낡지 않게, 목록에 있는데 지금은 안 열려 있는 항목은 [정리] 로 따로 알린다.
    """
    raw = query_one(build_anon_exposure_sql())
    names = sorted({ln.strip() for ln in raw.splitlines() if ln.strip()})
    not_allowed = unexpected_anon_readables(names)
    pending_open = sorted(n for n in not_allowed if n in ANON_CALLABLE_PENDING)
    bad = sorted(n for n in not_allowed if n not in ANON_CALLABLE_PENDING)
    if bad:
        print("[사고] 공개키에게 열리면 안 되는 것이 열려 있습니다: {}".format(", ".join(bad)))
        print("       → revoke all on <이름> from public, anon, authenticated; 를 적용하고")
        print("         supabase/schema.sql 에도 같이 반영하세요.")
        print("       ⓘ 정본에는 이미 닫혀 있는데 라이브만 뒤처진 것이면(머지 뒤·적용 전 창),")
        print("         준비된 마이그레이션을 그대로 적용하면 됩니다 — 예: 2026-09-05a_close_public_leftovers.sql")
    else:
        print("[정상] 공개키가 읽거나 부를 수 있는 것은 허용된 {}개뿐입니다.".format(
            len(names) - len(not_allowed)))
    if pending_open:
        print("[주의] 아직 안 닫은 것 {}개 (백로그 — 결재 후 정리): {}".format(
            len(pending_open), ", ".join(pending_open)))
        print("       PostgreSQL 기본값이 새 함수에 PUBLIC EXECUTE 를 줘서 열린 것이지,")
        print("       화면이 그걸 부르는 게 아닙니다(화면은 같은 이름의 api.* 만 씁니다).")
        print("       닫는 것은 이 스크립트가 아니라 사장님 결재 뒤의 일입니다.")
    # 대기 목록에 있는데 지금은 안 열려 있는 것 — 낡은 백로그를 남겨 두면 다음 사람이
    # 이미 닫힌 것을 또 결재 대상으로 착각한다.
    for closed in (p for p in ANON_CALLABLE_PENDING if p not in names):
        print("[정리] {} 는 이제 닫혔습니다 — ANON_CALLABLE_PENDING 에서 빼세요.".format(closed))
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
    # cp949 콘솔에서 한글·특수문자(—) 출력이 UnicodeEncodeError 로 죽지 않게 —
    # 형제 스크립트들(build_district_geojson.py·backup_raw.py 등)과 같은 처방.
    # ⛔ 이 블록이 **없어서 실제로 죽었다**(2026-08-22 실측): 콘솔에 바로 찍을 때는
    #    멀쩡하다가 `> 파일` 로 넘기는 순간(파이프·CI 로그도 같다) 파이썬이 cp949 로
    #    인코딩해 em dash 한 글자에서 통째로 터졌다 — 그것도 점검을 다 마치고
    #    **결과를 찍는 도중**이라, 종료 코드만 보면 "점검 실패"로 오해하게 된다.
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    opts = parse_args(list(sys.argv[1:] if argv is None else argv))

    if opts["check"]:
        _, _, stale = report_freshness()
        _, map_stale = report_map_freshness()
        _, _, tx_stale = report_tx_window_freshness()
        _, _, cov_stale = report_coverage_freshness()
        _, _, mix_stale = report_industry_mix_freshness()
        _, exposed = report_anon_exposure()
        # 읽기와 쓰기는 따로 묻는다 — 허용 목록에 있는 이름이라도 쓰기가 붙어 있으면 사고다.
        writable = report_write_exposure()
        return 1 if (stale or map_stale or tx_stale or cov_stale or mix_stale
                     or exposed or writable) else 0

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
    # 각주 집계도 마찬가지 — 갱신했다고 믿지 않고 원본 최신 분기와 대조한다.
    _, _, cov_stale = report_coverage_freshness()
    # 업종 분포 표도 방금 다시 구웠으니 최신 분기여야 한다 — 역시 다시 잰다.
    _, _, mix_stale = report_industry_mix_freshness()
    return 1 if (stale or map_stale or tx_stale or cov_stale or mix_stale) else 0


if __name__ == "__main__":
    sys.exit(main())
