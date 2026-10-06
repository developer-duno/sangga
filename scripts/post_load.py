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

`--check` 는 2026-09-27(P7)부터 세 가지를 더 본다:
  · 느려짐 — 화면이 부르는 api 함수의 **지난 점검 이후** 평균이 1초 초과면 [주의](종료 코드 1 아님).
    누적값을 data/logs/post_load_api_stats.json 에 남겨 다음 점검과의 차이로 잰다(첫 번째는 기준만).
  · 정본 색인 — schema.sql 의 색인이 라이브에 없거나 indisvalid=false 이거나 INCLUDE 칸이
    다르면 [사고](종료 코드 1). 거꾸로 라이브에만 남은 색인(제약이 만든 것·확장 소유 표의
    것은 뺀다)은 [주의](종료 코드 1 아님 — 2026-10-02 보탬).
  · 정본↔라이브 함수 — 언어·본문 md5·설정(set …)이 schema.sql 과 다르면 [사고](종료 코드 1).
  · 참고 시세 이웃 요약표(mv_tx_parcel_geog) pnu 집합 == 좌표·거래 있는 필지 집합 — 어느 쪽에든
    남는 필지가 있으면 [낡음](종료 코드 1 · 2026-10-03 부터 행수가 아니라 양쪽 차집합으로 잰다).
  · 별관 쫓겨남 — 별관(TOAST)을 쓰는 public·api 표에서 256바이트 미만 값이 별관에 있으면(큰 옆 칸
    탓에 쫓겨난 작은 값 — 그 칸을 훑는 쿼리가 느려진다) [주의](종료 코드 1 아님 · 2026-10-05 보탬).
  · 분기 표지(snapshot_release · 결정 0035 · 2026-10-07 보탬) — 표가 비었거나 보여 주는 분기가
    점포 표에 0행이면 [사고], 다 들어온 분기 ≠ 보여 주는 분기면 [낡음](둘 다 종료 코드 1) ·
    점포 표에 표지보다 새 분기가 있거나(적재 중) 행 수가 표지 기록과 다르면 [주의](종료 코드 무관).

⭐ 새 상권 분기는 이 스크립트가 **표지를 올려야** 화면에 보인다(결정 0035) — 갱신 흐름은
   요약표를 다 들어온 분기(loaded_ym)로 굽고 → 낡음 판정 6종을 통과하면 → 보여 주는 분기
   (published_ym)를 한 줄 UPDATE 로 올리고("표지 올림 X → Y") → 다시 잰다.
"""

import hashlib
import json
import os
import re
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
# ⚠️ mv_sigungu_tx_yearly(동네 매매 단가 흐름 · 결정 0027)는 앞의 것들과 **의존관계가
#    없다** — `transaction` 하나만 읽는다. 그래도 목록에 있어야 하는 이유는 같다:
#    이 표는 해마다 묶은 요약이라 새 거래를 넣어도 **갱신하지 않으면 화면만 옛 해에
#    굳은 채** 남는다(에러 0 — 그래서 아무도 모른다). 형제 mv_sigungu_tx_stats 와 달리
#    창(window)을 굳히지 않으므로 "낡음"을 등식으로 잴 자가 없다 — 그만큼 이 목록이
#    유일한 방어선이다.
# ⚠️ mv_parcel_store_names(상호명으로 찾기 · 2026-09-09c · 결정 0028)는 바로 위
#    mv_search_parcel 의 **형제**다 — 의존관계가 없다(그 표를 참조하지 않고 parcel·
#    building·unit_business 에서 직접 만든다. 그래야 그 표를 손볼 때 이게 딸려 오지
#    않는다). 그런데도 바로 뒤에 두는 이유는 **읽는 사람에게 짝으로 보이게** 하려는 것뿐이다.
#    새 분기를 적재하고 이걸 안 돌리면 **새 가게가 조용히 검색에서 빠진다**(에러 0 —
#    새 건물이 빠지는 것과 똑같은 방식이다). 굽는 데 시간이 걸린다(188,442 필지마다
#    최신 분기 점포를 모은다).
REFRESH_MVS = (
    "mv_search_parcel",
    "mv_parcel_store_names",
    "mv_open_sigungu",
    "mv_sigungu_tx_stats",
    "mv_sigungu_tx_yearly",
    "mv_coverage_stats",
    "mv_district_industry_mix",
    # 참고 시세의 반경 이웃 찾기 전용(2026-09-27c) — 빠지면 새 거래 필지가 이웃에서 조용히 빠진다.
    "mv_tx_parcel_geog",
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
    """업종 분포 표의 분기를 표지 loaded_ym(다 들어온 분기 · 결정 0035)과 대조한다.

    ⓘ 2026-10-07a 전에는 `max(snapshot_ym) from unit_business` 와 견줬다 — 그러면 적재 도중
       (반쯤 찬 새 분기가 max 인 동안) 이 점검이 '낡음'이라 말했고, 그 말대로 굽으면 반쪽을 구웠다.
    """
    raw = query_one(
        "select coalesce((select max(snapshot_ym) from mv_district_industry_mix), '')"
        " || '|' || coalesce((select loaded_ym from snapshot_release), '');"
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
            print("[낡음] 업종 분포 표 {} / 다 들어온 분기(표지) {} — 갱신이 필요합니다."
                  .format(mix_ym, latest_ym))
        print("       이대로 두면 층별 화면의 업종 분포만 옛 분기를 말합니다(에러는 안 납니다).")
        print("       python scripts/post_load.py 를 실행하면 최신 분기로 다시 굽습니다.")
    else:
        print("[신선] 업종 분포 표 {} = 다 들어온 분기(표지).".format(mix_ym or "(자료 없음)"))
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
    """표에 굳은 분기와 표지 loaded_ym(다 들어온 분기 · 결정 0035)을 한 줄로 뽑는다."""
    return (
        "select coalesce((select max(snapshot_ym) from mv_coverage_stats), '') || '|' || "
        "coalesce((select loaded_ym from snapshot_release), '');"
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
            print("[낡음] 각주 집계 분기 {} / 다 들어온 분기(표지) {} — 다릅니다."
                  .format(mv_ym, live_ym or "(없음)"))
        print("       이대로 두면 화면 각주가 옛 분기의 결측률을 계속 말합니다(에러는 안 납니다).")
        print("       python scripts/post_load.py 를 실행하면 오늘 자료 기준으로 다시 잡힙니다.")
    else:
        print("[신선] 각주 집계 분기 {} = 다 들어온 분기(표지).".format(mv_ym))
    return mv_ym, live_ym, stale


# ── 분기 표지 snapshot_release (2026-10-07a · 결정 0035 — 굽고, 확인하고, 올린다) ────
#
# 화면은 점포 분기를 `max(snapshot_ym)` 이 아니라 표지 한 줄에서 읽는다:
#   loaded_ym    = 다 들어온 분기(적재기가 전국 적재 + 교차검증 뒤 RPC 로 적는다) — 요약표가 이 칸으로 굽는다
#   published_ym = 화면이 보는 분기 — **이 스크립트가** 요약표를 굽고 낡음 판정을 다 통과한 뒤 올린다
# 그래서 새 분기는 적재 2시간 동안 화면에 안 새고, 이 UPDATE 한 줄에 모든 카드가 한순간에 바뀐다.
# ⛔ 표지가 0줄이면 화면 가게 칸이 **조용히** 빈다(하위질의가 null) — [사고].
# ⛔ 올리는 일은 갱신 흐름(`--check` 없이)에서만 한다. `--check` 는 DB 쓰기 0.

SNAPSHOT_RELEASE_SQL = (
    "select coalesce((select r.loaded_ym from snapshot_release r), '') || '|' || "
    "coalesce((select r.published_ym from snapshot_release r), '') || '|' || "
    "coalesce((select r.loaded_rows::text from snapshot_release r), '') || '|' || "
    "coalesce((select max(snapshot_ym) from unit_business), '') || '|' || "
    "(select count(*) from unit_business u"
    " where u.snapshot_ym = (select r.published_ym from snapshot_release r))::text || '|' || "
    "(select count(*) from unit_business u"
    " where u.snapshot_ym = (select r.loaded_ym from snapshot_release r))::text;"
)

PUBLISH_SNAPSHOT_SQL = (
    "update snapshot_release set published_ym = loaded_ym, published_at = now()"
    " where id = 1 and loaded_ym > published_ym;"
)


def _int_or_none(v):
    v = str(v if v is not None else "").strip()
    return int(v) if v.lstrip("-").isdigit() else None


def judge_snapshot_release(loaded, published, loaded_rows, max_ub, published_cnt, loaded_cnt):
    """표지 상태를 판정해 [(수준, 말)…] 을 돌려준다 (순수 함수 — 시험이 여기만 보면 된다).

    수준: "사고"(--check exit 1 · 화면 가게 칸이 빈 상태) · "낡음"(exit 1 · 구웠는데 안 올림) ·
          "주의"(종료 코드 무관). 문제가 없으면 빈 목록.
    """
    loaded = str(loaded or "").strip()
    published = str(published or "").strip()
    max_ub = str(max_ub or "").strip()
    published_cnt = _int_or_none(published_cnt)
    loaded_cnt = _int_or_none(loaded_cnt)
    rows = _int_or_none(loaded_rows)
    if not loaded and not published:
        return [("사고", "표지(snapshot_release)가 비었습니다 — 화면 가게 칸·각주·업종 카드가 통째로 빈 상태입니다. "
                       "python scripts/publish_snapshot.py --ym <분기> 로 채운 뒤 python scripts/post_load.py")]
    out = []
    if not published_cnt:
        out.append(("사고", "보여 주는 분기 {} 의 점포 행이 0 입니다 — 화면 가게 칸이 통째로 빈 상태입니다. "
                           "python scripts/publish_snapshot.py --show 로 확인하세요".format(published or "(없음)")))
    if loaded != published:
        out.append(("낡음", "다 들어온 분기 {} ≠ 보여 주는 분기 {} — 요약표를 구웠는데 표지를 안 올렸거나 "
                           "post_load 를 안 돌렸습니다. python scripts/post_load.py 를 돌리면 올라갑니다"
                    .format(loaded or "(없음)", published or "(없음)")))
    if max_ub and loaded and max_ub > loaded:
        out.append(("주의", "점포 표에 표지보다 새 분기 {} 가 있습니다(다 들어온 분기 {}) — 적재 중이거나 중간에 "
                           "멈췄습니다. 전국 적재가 끝나면 적재기가 표지를 올립니다".format(max_ub, loaded)))
    if rows != loaded_cnt:
        out.append(("주의", "표지를 적을 때 센 {} 분기 행 수 {} ≠ 지금 {} — 행이 더 들어왔거나 덜 들어왔습니다"
                    .format(loaded or "(없음)", "(기록 없음)" if rows is None else rows,
                            "(없음)" if loaded_cnt is None else loaded_cnt)))
    return out


def read_snapshot_release():
    """표지를 읽어 판정 함수의 인자 여섯 개를 dict 로. 표가 없거나 못 읽으면 예외."""
    raw = query_one(SNAPSHOT_RELEASE_SQL)
    parts = (raw.splitlines()[-1] if raw else "").split("|")
    if len(parts) != 6:
        raise ValueError("표지 응답 모양이 다릅니다: {!r}".format(raw[:200]))
    keys = ("loaded", "published", "loaded_rows", "max_ub", "published_cnt", "loaded_cnt")
    return dict(zip(keys, (p.strip() for p in parts)))


def report_snapshot_release():
    """표지를 재서 찍고 (사고 여부, 낡음 여부) 를 돌려준다. 못 읽으면 [사고]."""
    try:
        st = read_snapshot_release()
    except Exception as exc:  # noqa: BLE001 — 표가 없거나(마이그레이션 전) 접속 실패
        print("[사고] 분기 표지(snapshot_release)를 읽지 못했습니다 — {}".format(
            str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__))
        print("       마이그레이션 2026-10-07a 가 적용됐는지 보세요(python scripts/publish_snapshot.py --show).")
        return True, False
    found = judge_snapshot_release(**st)
    for level, msg in found:
        print("[{}] {}".format(level, msg))
    if not found:
        print("[신선] 분기 표지 — 다 들어온 분기 = 보여 주는 분기 = {} ({}행).".format(
            st["published"], st["published_cnt"]))
    fatal = any(level == "사고" for level, _ in found)
    stale = any(level == "낡음" for level, _ in found)
    return fatal, stale


def should_publish(loaded, published):
    """표지를 올릴 때인가 — 두 칸이 다 YYYYMM 이고 다 들어온 분기가 보여 주는 분기보다 새것."""
    loaded = str(loaded or "").strip()
    published = str(published or "").strip()
    ok = re.fullmatch(r"\d{6}", loaded) and re.fullmatch(r"\d{6}", published)
    return bool(ok) and loaded > published


def publish_snapshot_release_if_ready():
    """갱신 흐름 끝(요약표 굽기·낡음 판정 6종 통과 뒤): 올릴 때면 표지를 올리고 다시 잰다.

    (사고 여부, 낡음 여부) 를 돌려준다 — main 이 둘 중 하나면 1 을 돌려준다.
    """
    try:
        st = read_snapshot_release()
    except Exception:  # noqa: BLE001 — report_snapshot_release 가 같은 실패를 [사고]로 찍는다
        return report_snapshot_release()
    if should_publish(st["loaded"], st["published"]):
        rc = dbx.run_sql(PUBLISH_SNAPSHOT_SQL, quiet=True)
        if rc != 0:
            print("[실패] 표지를 올리지 못했습니다 — 화면은 그대로 {} 입니다.".format(st["published"]))
            return True, False
        print("표지 올림 {} → {} — 화면이 이제 {} 분기를 보여 줍니다.".format(
            st["published"], st["loaded"], st["loaded"]))
    # 했다고 믿지 않고 다시 잰다.
    return report_snapshot_release()


# ── 참고 시세 이웃 요약표 신선도 (2026-09-27 P7 — 사장님 결재) ─────────────────
#
# mv_tx_parcel_geog(2026-09-27c)는 "좌표 있고 거래가 한 건이라도 있는 필지"만 담는다.
# 실거래를 새로 넣고 갱신을 잊으면 **새로 거래가 생긴 필지가 참고 시세 이웃에서 조용히
# 빠진다**(에러 0). 표의 pnu 집합 == 정의 조건의 pnu 집합(양쪽 차집합이 0)으로 잡는다
# (2026-10-03 — 행수만 보면 지워진 필지와 새 필지가 같은 수일 때 [신선]이었다).
# ⛔ 아래 조건은 schema.sql 의 뷰 정의(where 절)와 **글자 그대로 같은 뜻**이어야 한다.
#    정의를 바꾸면 여기도 바꾼다(tests/test_post_load_check_alarms.py 가 두 곳을 맞대 본다).
TX_GEOG_MV = "mv_tx_parcel_geog"
TX_GEOG_CONDITION = (
    "p.geom is not null and exists (select 1 from transaction t where t.pnu = p.pnu)"
)


def build_tx_geog_freshness_sql():
    """한 번의 조회로 네 수를 뽑는다: 표 행수 | 있어야 할 행수 | 표에만 있는 pnu | 표에 빠진 pnu.

    ⛔ 행수만 보면 지워진 필지와 새 필지가 같은 수일 때 [신선]이다 — 그래서 pnu 집합을 양쪽으로
       뺀다(4천 행끼리라 싸다). '있어야 할 필지'는 CTE 한 번으로 구해 양쪽 차집합이 같이 쓴다.
    ⚠️ 못 보는 것: pnu 집합만 본다 — 필지 도형(geom)이 바뀌었는데 표의 geog 가 옛것인 경우는 [신선]이다.
    """
    return (
        "with want as (select p.pnu from parcel p where {cond}) "
        "select (select count(*) from {mv})::text || '|' || "
        "(select count(*) from want)::text || '|' || "
        "(select count(*) from {mv} m where not exists "
        "(select 1 from want w where w.pnu = m.pnu))::text || '|' || "
        "(select count(*) from want w where not exists "
        "(select 1 from {mv} m where m.pnu = w.pnu))::text;"
    ).format(mv=TX_GEOG_MV, cond=TX_GEOG_CONDITION)


def report_tx_geog_freshness():
    """참고 시세 이웃 요약표를 재서 (표행수, 있어야할행수, 낡음여부) 를 돌려준다.

    낡음 = 표에만 있는 pnu 가 있거나 표에 빠진 pnu 가 있다(행수가 같아도) — 종료 코드도
    형제들처럼 낡음이면 1. 답이 네 칸이 아니거나 숫자가 아니면 예외로 시끄럽게 죽는다.
    """
    mv_rows, expected, only_mv, missing = query_one(build_tx_geog_freshness_sql()).split("|")
    # 네 칸을 **먼저 전부** 숫자로 — 판정이 앞에서 끝나도 뒤 칸이 글자면 죽어야 설명이 참이다.
    n_rows, n_expected, n_only, n_missing = (int(v) for v in (mv_rows, expected, only_mv, missing))
    stale = n_only > 0 or n_missing > 0 or is_stale(n_rows, n_expected)
    if stale:
        print("[낡음] 참고 시세 이웃 요약표 {}행 / 있어야 할 행수 {}행 · 표에만 있는 필지 {}곳 · "
              "표에 빠진 필지 {}곳 — 갱신이 필요합니다.".format(mv_rows, expected, only_mv, missing))
        print("       이대로 두면 새로 거래가 생긴 필지가 참고 시세 이웃에서 빠집니다(에러는 안 납니다).")
        print("       python scripts/post_load.py 를 실행하면 다시 굽습니다.")
    else:
        print("[신선] 참고 시세 이웃 요약표 {}행 = 좌표·거래 있는 필지 수 · 표에만 있는 필지 0곳 · "
              "표에 빠진 필지 0곳.".format(mv_rows))
    return mv_rows, expected, stale


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
    # 동네 매매 단가 흐름(2026-09-09a · 결정 0027). 물질화뷰 mv_sigungu_tx_yearly 는
    # **여기 없다** — 화면은 이 함수 하나로만 읽는다. 나가는 것은 **구×연도 요약**
    # (그 해의 거래 수·단가 중앙값·가운데 절반·층 미상 수, 그리고 그 해가 얼마나
    # 온전한지)뿐이고, 개별 거래(필지·층·단가)는 그 뷰에 아예 없다.
    "api.get_sigungu_tx_yearly",
    # 상호명으로 찾기(2026-09-09c · 결정 0028). 점포 표 unit_business 는 **여기 없다** —
    # 열리면 전국 339만 점포의 상호·업종·좌표가 통째로 긁힌다. 이 함수가 내보내는 것은
    # **땅 한 줄**(대표 동·주소·층 요약)과 그 땅에서 **일치한 상호 최대 3개**, 그리고 개수뿐이다.
    #   ⛔ biz_no·업종 코드·점포 좌표는 한 글자도 안 나간다.
    #   ⛔ 요약표 mv_parcel_store_names 도 여기 없다 — 그 표가 열리면 상호 묶음
    #      (store_names)이 통째로 긁혀 이 함수의 상한·구 좁히기가 전부 우회된다.
    "api.search_stores",
    # 호실 구성표(2026-10-04b · 결정 0032). 표 unit 은 **여기 없다** — 열면 아파트 세대 목록이 통째로 긁힌다.
    "api.list_unit_floor_summary", "api.list_floor_units",
    # 서울 상권 개업·폐업(2026-10-05b · 결정 0033). 표 district_openclose 는 **여기 없다** —
    # 화면은 이 함수 하나로만 읽는다. 나가는 것은 상권 합산(공표 수의 더하기)과 최신 분기 업종
    # 상위 10줄 + '그 밖' 합뿐이다. 표가 열리면 서울 1,650 상권 × 100 업종 × 22분기가 통째로 긁힌다.
    "api.list_district_openclose",
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


# ── 경보 셋 (2026-09-27 P7 — 사장님 결재) ────────────────────────────────────
#
# 아래 셋은 "적재가 끝났나"가 아니라 **"라이브가 정본·평소와 같은가"** 를 본다.
#   ① 느려짐 경보 — 화면이 부르는 api 함수의 평균이 **지난 점검 이후** 1초를 넘었나.
#   ② 정본 색인 — schema.sql 의 색인이 라이브에 있고 쓸 수 있는(indisvalid) 상태이며
#      INCLUDE 칸이 같은가. 라이브에만 남은 색인은 [주의]로만 알린다(종료 코드 1 아님).
#   ③ 정본↔라이브 함수 — 언어·본문·설정이 글자 그대로 같은가(파일 없이 라이브만 바꾼 "뒷문").
# ②③ 은 [사고](종료 코드 1), ① 은 [주의](종료 코드 1 아님 — 느린 것은 고장이 아니라 신호다).

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_SQL_PATH = os.path.join(PROJECT_ROOT, "supabase", "schema.sql")

# ① 느려짐 경보 ───────────────────────────────────────────────────────────
#
# ⛔ **누적 평균을 보지 않는다.** pg_stat_statements 의 평균은 통계가 시작된 뒤 전부의
#    평균이라, 색인을 고쳐 빨라진 함수도 옛 느린 호출이 평균을 끌어올려 몇 주씩 "느림"으로
#    남는다(실측: 신선도 함수 누적 평균 2,412ms — 색인 뒤 한 번은 12~16ms). 그래서 점검할
#    때마다 누적값을 **로컬 파일**에 남기고, 직전 파일과의 **차이**(새로 쌓인 호출 수·시간)로
#    평균을 낸다. 파일은 data/logs/ 아래라 git 에 안 올라간다(.gitignore).
SLOW_MEAN_MS = 1000.0
API_STATS_SNAPSHOT_PATH = os.path.join(PROJECT_ROOT, "data", "logs", "post_load_api_stats.json")


def build_api_stats_sql(names=None):
    """화면이 부르는 api 함수의 **최상위 문장** 누적 통계를 한 줄씩 뽑는다.

    PostgREST 는 함수 호출 하나를 최상위 문장 하나로 보내고, 그 글 안에 `"api"."<함수>"(`
    꼴로 이름이 들어 있다. 같은 함수라도 인자 모양·역할마다 줄이 갈리므로 줄마다
    (userid, queryid) 로 따로 들고 온다 — 초기화 판정이 줄 단위라서다.
    ⚠️ `"api"."parcel"(` 같은 INSERT 도 같은 꼴이라 **허용 목록 이름으로만** 거른다.
    """
    names = ANON_CALLABLE_NAMES if names is None else names
    arr = ",".join("'{}'".format(n) for n in names)
    return (
        "select s.userid::text || '|' || s.queryid::text || '|' || m[1] || '|' || "
        "s.calls::text || '|' || s.total_exec_time::text || '|' || "
        "coalesce(extract(epoch from s.stats_since)::text, '') "
        "from extensions.pg_stat_statements s, "
        "lateral regexp_match(s.query, '\"api\"\\.\"([A-Za-z0-9_]+)\"\\(') m "
        "where s.toplevel and m[1] = any(array[" + arr + "]::text[]);"
    )


def parse_api_stats(raw):
    """psql 출력 → {줄열쇠: {fn, calls, total_ms, since}} (순수 함수)."""
    out = {}
    for line in str(raw or "").splitlines():
        parts = line.strip().split("|")
        if len(parts) != 6:
            continue
        userid, queryid, fn, calls, total, since = parts
        try:
            out[userid + ":" + queryid] = {
                "fn": fn, "calls": int(calls), "total_ms": float(total), "since": since}
        except ValueError:
            continue
    return out


def diff_api_stats(prev, cur, prev_taken_at=None):
    """직전·지금 스냅샷 → ({함수: [새 호출 수, 새 시간 ms]}, 기준만 새로 잡은 줄 수) (순수 함수).

    · 직전 스냅샷이 없으면(None) 비교하지 않는다 — 전부 기준만.
    · 직전과 같은 줄(stats_since 그대로 · calls 안 줄음)은 **차이**를 센다.
    · 그 밖(직전에 없던 줄 · stats_since 가 바뀐 줄 · calls 가 준 줄)은 stats_since 가
      직전 점검 **뒤**면 "그 뒤 새로 생긴 줄"이라 **통째로** 센다. pg_stat_statements 는 줄 수
      상한(라이브 5,000 · 2026-09-27 에 4,888)에 닿으면 드문 줄을 밀어내고, 밀려난 줄은 다시
      생길 때 stats_since 가 그 시각으로 새로 찍힌다 — 그 호출은 전부 직전 점검 뒤의 것이다.
      직전 점검보다 **앞**이면 언제 쌓였는지 모르므로 기준만 새로 잡는다.
    """
    per_fn = {}
    rebased = 0
    if prev is None:
        return per_fn, len(cur)
    for key, c in cur.items():
        p = prev.get(key)
        if p is not None and p.get("since") == c["since"] and c["calls"] >= p["calls"]:
            d_calls, d_ms = c["calls"] - p["calls"], c["total_ms"] - p["total_ms"]
        else:
            try:
                fresh = prev_taken_at is not None and float(c["since"]) > float(prev_taken_at)
            except (TypeError, ValueError):
                fresh = False
            if not fresh:
                rebased += 1
                continue
            d_calls, d_ms = c["calls"], c["total_ms"]
        if d_calls <= 0:
            continue
        acc = per_fn.setdefault(c["fn"], [0, 0.0])
        acc[0] += d_calls
        acc[1] += d_ms
    return per_fn, rebased


def slow_functions(per_fn, threshold_ms=SLOW_MEAN_MS):
    """새 호출 평균이 기준을 **넘는** 함수 → [(함수, 새 호출 수, 평균 ms)] (순수 함수)."""
    out = []
    for fn, (calls, ms) in sorted(per_fn.items()):
        if calls > 0 and ms / calls > threshold_ms:
            out.append((fn, calls, ms / calls))
    return out


def load_api_stats_snapshot(path=API_STATS_SNAPSHOT_PATH):
    """직전 스냅샷 → (taken_at epoch, entries). 파일이 **없으면** (None, None).

    파일은 있는데 모양이 틀리면 **예외를 그대로 올린다** — "처음 점검"과 "파일이 깨짐"은
    다른 말이라, 부르는 쪽(report_slow_functions)이 [주의] 로 따로 알린다.
    """
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    taken_at, entries = float(data["taken_at"]), dict(data["entries"])
    # 줄마다 diff_api_stats 가 직전 줄에서 실제로 쓰는 것(calls·total_ms 는 숫자, since 는 .get)을
    # 여기서 미리 본다 — 그래야 비교 코드에서 터진 것과 "파일 모양이 틀림"이 갈린다(2026-10-03).
    for key, row in entries.items():
        if not isinstance(row, dict) or not all(
                isinstance(row.get(k), (int, float)) and not isinstance(row.get(k), bool)
                for k in ("calls", "total_ms")):
            raise ValueError("스냅샷 줄 {} 의 모양이 틀립니다".format(key))
    return taken_at, entries


def save_api_stats_snapshot(entries, taken_at, path=API_STATS_SNAPSHOT_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"taken_at": taken_at, "entries": entries}, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def report_slow_functions():
    """느려짐 경보를 찍는다. **종료 코드에 영향을 주지 않는다**([주의]까지만)."""
    try:
        taken_at = float(query_one("select extract(epoch from now())::text;"))
        cur = parse_api_stats(query_one(build_api_stats_sql()))
    except Exception as exc:          # 통계 확장이 없거나 권한이 없으면 — 경보만 못 낸다
        print("[주의] 느려짐 경보를 읽지 못했습니다(pg_stat_statements): {}".format(
            _psql_failure_reason(exc)))
        return []
    # ⚠️ 스냅샷 읽기·비교가 깨져도 --check 전체를 죽이지 않는다 — 경보 하나가 못 도는 것이지
    #    다른 점검의 판정까지 잃을 일은 아니다. 깨진 파일은 기준만 새로 써서 다음부터 되살린다.
    # ⛔ 읽기(파일 모양)와 비교(코드)는 따로 잡는다 — 한 try 면 비교 코드의 결함도 "파일 모양이
    #    틀립니다"로 찍혀 엉뚱한 파일을 의심하게 된다(2026-10-03). 둘 다 [주의] · 종료 코드 영향 0.
    broken = None
    try:
        prev_at, prev = load_api_stats_snapshot(API_STATS_SNAPSHOT_PATH)
    except Exception as exc:
        print("[주의] 느려짐 경보: 직전 스냅샷 파일 모양이 틀립니다({}) — 이번엔 비교하지 않습니다."
              .format(type(exc).__name__))
        prev, per_fn, rebased, broken = None, {}, 0, "file"
    else:
        try:
            per_fn, rebased = diff_api_stats(prev, cur, prev_at)
        except Exception as exc:
            print("[주의] 느려짐 경보: 직전 스냅샷과 비교하는 코드가 실패했습니다({}) — 파일 모양 탓이"
                  " 아닙니다. 이번엔 비교하지 않습니다.".format(type(exc).__name__))
            prev, per_fn, rebased, broken = None, {}, 0, "diff"
    had_prev = prev is not None
    # ⛔ 저장이 실패하면 os.replace 앞에서 멈추므로 **옛 스냅샷 파일이 그대로 남는다** — 다음 점검은
    #    "기준부터"가 아니라 그 옛 파일을 다시 읽는다. 그리고 실패했으면 "저장했습니다"를 말하지 않는다.
    try:
        save_api_stats_snapshot(cur, taken_at, API_STATS_SNAPSHOT_PATH)
    except OSError as exc:
        if broken:
            after = "옛 스냅샷 파일이 그대로 남아 다음 점검도 그 파일을 다시 읽습니다"
        elif had_prev:
            after = "옛 스냅샷 파일이 그대로 남아 다음 점검은 그 파일과 다시 비교합니다"
        else:
            after = "스냅샷 파일이 아직 없어 다음 점검도 기준부터입니다"
        print("[주의] 느려짐 경보: 스냅샷을 저장하지 못했습니다({}) — {}.".format(type(exc).__name__, after))
        saved = False
    else:
        saved = True
    if prev is None:
        if saved and broken:
            print("       ⓘ 기준을 새로 저장했습니다({}줄) — 다음 점검부터 이 기준과 비교합니다.".format(len(cur)))
        elif saved:
            print("[정보] 느려짐 경보: 기준만 저장했습니다({}줄) — 다음 점검부터 비교합니다.".format(len(cur)))
        return []
    slow = slow_functions(per_fn)
    for fn, calls, mean in slow:
        print("[주의] 느려짐: api.{} — 지난 점검 이후 {}회 · 평균 {:,.0f}ms (기준 {:,.0f}ms 초과)"
              .format(fn, calls, mean, SLOW_MEAN_MS))
    if not per_fn:
        print("[정상] 느려짐 경보: 지난 점검 이후 api 호출 없음.")
    elif not slow:
        print("[정상] 느려짐 경보: 지난 점검 이후 호출된 api 함수 {}개 모두 평균 {:,.0f}ms 이하."
              .format(len(per_fn), SLOW_MEAN_MS))
    if rebased and saved:
        print("       ⓘ 통계가 초기화됐거나 새로 잡힌 {}줄은 이번엔 기준만 새로 잡았습니다.".format(rebased))
    elif rebased:
        print("       ⓘ 통계가 초기화됐거나 새로 잡힌 {}줄은 이번엔 비교하지 않았습니다"
              "(저장이 실패해 기준도 새로 잡히지 않았습니다).".format(rebased))
    return slow


# ② 정본 색인 ─────────────────────────────────────────────────────────────
#
# 줄머리의 `create [unique] index [concurrently] [if not exists] <이름> on` 만 센다 —
# 주석(`-- create index …`)은 줄머리가 `--` 라 안 걸린다. 이름 뒤 `on` 이 다음 줄에 있어도
# 된다(mv_district_industry_mix_key 가 그 꼴이다).
#
# 보는 것(앞의 둘은 2026-09-27 P7, 뒤의 둘은 2026-10-02 에 보탰다):
#   · 정본 색인이 라이브에 있는가 · 쓸 수 있는가(indisvalid)            → [사고]
#   · INCLUDE 칸 목록이 정본과 같은가(순서까지)                          → [사고]
#   · 라이브에만 있는 색인이 있는가(제약이 만든 것·확장 소유 표의 것은 뺀다) → [주의]
# ⛔ INCLUDE 를 보는 이유: 이름만 같으면 칸이 빠져도 예전 점검은 [정상]이었다. 빠져도 **에러는
#    안 나고 느려지기만 한다**(idx_arch_permit_pnu 의 arch_pms_day — 58쪽 ↔ 13쪽, 2026-09-27e).
# ⛔ 라이브 전용이 [주의]인 이유: 남은 색인은 고장이 아니라 디스크·쓰기 비용 신호다(색인을
#    지우는 마이그레이션이 덜 적용됐거나 라이브에서 손으로 만든 것 — 2026-10-01b 경고).
# ⚠️ 여전히 못 보는 것: 색인 열(키 칸)·식·WHERE 조건·색인 방식(btree/gin/gist)·유일 여부·
#    연산자 클래스의 차이. 이름과 INCLUDE 가 같으면 그런 차이는 [정상]으로 지나간다.
#    그 밖(2026-10-02 검사 기록 — 알고 둔 것): 칸이 모자란 줄은 정본에 없는 이름이면 라이브
#    전용으로 찍힌다 · 정본 추출은 문자열 안의 `--`/`;` 와 블록 주석(/* */)을 모른다 · 정의 칸이
#    NULL 이면 빈 칸(coalesce)이라 "읽지 못함"이 된다(그 coalesce 는 시험이 안 지킨다 — 벗기면
#    그 줄이 통째로 사라져 "라이브에 없음"으로 시끄럽다) · 이름만으로 맞춰 public·api 에 같은 이름이
#    있으면 뒤 줄이 덮는다 · "읽지 못함"일 때도 안내 줄은 "create index 문을 적용하세요"다.
CANON_INDEX_RE = re.compile(
    r"(?im)^[ \t]*create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?"
    r"(?:if\s+not\s+exists\s+)?(\w+)\s+on\b"
)
_SQL_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_CANON_INCLUDE_RE = re.compile(r"(?i)\binclude\s*\(([^)]*)\)")
# pg_get_indexdef 는 `… USING btree (pnu) INCLUDE (a, b) WHERE …` 꼴로 대문자를 찍는다.
_LIVE_INCLUDE_RE = re.compile(r"\bINCLUDE\s*\(([^)]*)\)")
# 한 줄 = 이름|valid|표|제약이 만든 색인인가|확장 소유 표의 색인인가|색인 정의.
# ⚠️ 색인 정의는 **맨 끝 칸**이어야 한다 — 식 색인의 `||` 가 구분자와 같은 글자라, 파서가
#    앞의 다섯 번만 자른다(parse_live_indexes). 칸을 보태려면 정의 앞에 끼운다.
# ⛔ 제약 칸은 기본키·유일·배제(contype p·u·x)만 센다 — pg_constraint.conindid 는 **외래키
#    제약에도 채워진다**(참조되는 쪽 색인, PostgreSQL 문서). contype 을 안 거르면 외래키가
#    가리키는 일반 유일 색인이 "제약이 만든 색인"으로 잘못 빠져 라이브 전용에서 안 보인다.
LIVE_INDEX_SQL = (
    "select c.relname || '|' || i.indisvalid::text || '|' || t.relname || '|' || "
    "(exists (select 1 from pg_constraint k where k.conindid = i.indexrelid "
    "and k.contype in ('p','u','x')))::text || '|' || "
    "(exists (select 1 from pg_depend d where d.classid = 'pg_class'::regclass "
    "and d.objid in (i.indrelid, i.indexrelid) and d.deptype = 'e'))::text || '|' || "
    "coalesce(pg_get_indexdef(i.indexrelid), '') "
    "from pg_index i "
    "join pg_class c on c.oid = i.indexrelid "
    "join pg_class t on t.oid = i.indrelid "
    "join pg_namespace n on n.oid = c.relnamespace "
    "where n.nspname in ('public','api');"
)
_LIVE_INDEX_FIELDS = 6


def canonical_index_names(sql):
    """정본 → 색인 이름 목록 (순수 함수 — 첫 등장 순서, 중복 제거)."""
    seen = []
    for m in CANON_INDEX_RE.finditer(sql):
        name = m.group(1).lower()
        if name not in seen:
            seen.append(name)
    return seen


def _split_columns(text):
    """`a, "B" ,c` → ['a', 'b', 'c'] (소문자 · 공백·큰따옴표 제거 · **순서 그대로**)."""
    return [c.strip().strip('"').lower() for c in str(text).split(",") if c.strip()]


def _format_columns(cols):
    return "({})".format(", ".join(cols)) if cols else "(없음)"


def canonical_index_includes(sql):
    """정본 → {색인 이름: INCLUDE 칸 목록} (순수 함수 — include 가 없으면 빈 목록).

    문장 = 머리(`create … index`)부터 첫 `;` 까지. 문장 가운데 낀 주석의 `;` 나 `include (…)`
    글자에 속지 않게 `--` 주석을 먼저 걷어 낸다. 같은 이름이 두 번 나오면 첫 문장만 본다
    (canonical_index_names 와 같은 규칙)."""
    bare = _SQL_LINE_COMMENT_RE.sub("", sql)
    out = {}
    for m in CANON_INDEX_RE.finditer(bare):
        name = m.group(1).lower()
        if name in out:
            continue
        end = bare.find(";", m.end())
        stmt = bare[m.start(): end if end != -1 else len(bare)]
        found = _CANON_INCLUDE_RE.search(stmt)
        out[name] = _split_columns(found.group(1)) if found else []
    return out


def parse_live_indexes(live_raw):
    """LIVE_INDEX_SQL 의 출력 → {이름: {valid, table, constraint, extension, include}} (순수 함수).

    색인 정의(맨 끝 칸)에는 `||` 같은 식이 들어갈 수 있어 **앞의 다섯 번만** 자른다.
    ⛔ 칸이 모자란 줄(옛 두 칸 모양)이나 정의가 빈 줄은 include 를 None(모름)으로 둔다 —
       빈 목록으로 두면 "INCLUDE 없음"과 구별이 안 돼, 조회 모양이 틀어진 날 조용히 초록이 된다."""
    live = {}
    for line in str(live_raw or "").splitlines():
        parts = line.strip().split("|", _LIVE_INDEX_FIELDS - 1)
        name = parts[0].strip().lower()
        if not name:
            continue
        full = len(parts) == _LIVE_INDEX_FIELDS
        definition = parts[5].strip() if full else ""
        if definition:
            found = _LIVE_INCLUDE_RE.search(definition)
            include = _split_columns(found.group(1)) if found else []
        else:
            include = None
        live[name] = {
            "valid": len(parts) > 1 and parts[1].strip() == "true",
            "table": parts[2].strip() if full else "",
            "constraint": full and parts[3].strip() == "true",
            "extension": full and parts[4].strip() == "true",
            "include": include,
        }
    return live


def index_problems(canon_names, live_raw, canon_includes=None):
    """정본 색인 중 라이브에 없거나 invalid 이거나 INCLUDE 칸이 다른 것 → [(이름, 사유)] (순수 함수).

    canon_includes(canonical_index_includes 의 결과)를 주면 INCLUDE 칸도 맞춘다 — 정본에
    include 가 없는 색인은 라이브에도 없어야 한다. 안 주면 이름·indisvalid 만 본다."""
    live = parse_live_indexes(live_raw)
    out = []
    for name in canon_names:
        row = live.get(name)
        if row is None:
            out.append((name, "라이브에 없음"))
        elif not row["valid"]:
            out.append((name, "indisvalid=false(쓸 수 없는 색인)"))
        elif canon_includes is not None:
            want = list(canon_includes.get(name, []))
            got = row["include"]
            if got is None:
                out.append((name, "INCLUDE 칸을 읽지 못함(라이브 조회 줄에 색인 정의가 없음)"))
            elif got != want:
                out.append((name, "INCLUDE 칸이 다름: 정본 {} · 라이브 {}".format(
                    _format_columns(want), _format_columns(got))))
    return out


def live_only_indexes(canon_names, live_raw):
    """라이브에만 있는 색인 → [(이름, 표, valid)] 이름순 (순수 함수).

    ⛔ 둘은 뺀다: 제약(기본키·유일·배제)이 만든 색인 — 정본에는 `create index` 가 아니라
       표 정의로 적혀 있다 / 확장 소유 표의 색인(PostGIS spatial_ref_sys 등) — 우리 것이 아니다."""
    canon = set(canon_names)
    out = []
    for name, row in parse_live_indexes(live_raw).items():
        if name in canon or row["constraint"] or row["extension"]:
            continue
        out.append((name, row["table"], row["valid"]))
    return sorted(out)


def report_canonical_indexes(sql_text=None):
    if sql_text is None:
        with open(SCHEMA_SQL_PATH, encoding="utf-8") as fh:
            sql_text = fh.read()
    names = canonical_index_names(sql_text)
    includes = canonical_index_includes(sql_text)
    live_raw = query_one(LIVE_INDEX_SQL)          # 라이브 조회는 이 한 번뿐이다.
    bad = index_problems(names, live_raw, includes)
    if bad:
        print("[사고] 정본(schema.sql) 색인 중 라이브에 없거나 못 쓰거나 INCLUDE 칸이 다른 것 {}개:"
              .format(len(bad)))
        for name, why in bad:
            print("       · {} — {}".format(name, why))
        print("       이대로 두면 검색·화면이 조용히 느려집니다. 정본의 create index 문을 라이브에 적용하세요.")
        if any(why.startswith("INCLUDE 칸이 다름") for _, why in bad):
            print("       ⓘ INCLUDE 칸이 다른 색인은 `create index if not exists` 로는 안 고쳐집니다"
                  "(이름이 이미 있어 건너뜁니다) — 그 색인의 마이그레이션(새로 만들고 옛것을 지우는 문장)을 적용하세요.")
        print("       ⓘ 또는 아직 머지 안 한 PR 의 마이그레이션을 먼저 적용한 것 — 머지하면 사라집니다.")
    else:
        print("[정상] 정본 색인 {}개가 라이브에 모두 있고 쓸 수 있으며, INCLUDE 칸도 같습니다"
              "(INCLUDE 가 있는 색인 {}개).".format(len(names), sum(1 for n in names if includes.get(n))))
    if not parse_live_indexes(live_raw):
        # 빈 응답에 "라이브에만 있는 색인 없음"이라 하면 거짓 안심이다(위의 [사고]가 종료 코드를 정한다).
        print("[주의] 라이브 색인 목록을 한 줄도 읽지 못했습니다 — 라이브 전용 색인 판정을 건너뜁니다.")
        return bad
    extra = live_only_indexes(names, live_raw)
    if extra:
        print("[주의] 라이브에만 있는 색인 {}개(정본 schema.sql 에 없음):".format(len(extra)))
        for name, table, valid in extra:
            print("       · {} (표 {}{})".format(name, table or "?", "" if valid else " · indisvalid=false"))
        print("       색인을 지우는 마이그레이션이 덜 적용됐거나 라이브에서 손으로 만든 것 — 정본에 넣거나 지우세요.")
        print("       ⓘ 고장은 아닙니다(종료 코드에 안 넣습니다) — 남은 색인은 디스크와 쓰기 비용을 먹습니다."
              " 아직 머지 안 한 PR 의 마이그레이션이 만든 색인이면 머지하면 사라집니다.")
    else:
        print("[정상] 라이브에만 있는 색인 없음(제약이 만든 색인·확장 소유 표의 색인은 셈에서 뺍니다).")
    return bad


# ③ 정본↔라이브 함수 대조 ────────────────────────────────────────────────
#
# tests/test_schema_function_drift.py 는 "정본 == 마지막 마이그레이션"(글자)만 본다 — CI 에
# DB 가 없어서다. 그래서 **파일 없이 라이브에서 바로 고친 것**은 아무도 못 본다. 여기서는
# 라이브 pg_proc 을 직접 읽어 언어(prolang)·본문(prosrc md5)·설정(proconfig)을 맞춘다.
# ⚠️ 본문은 양쪽 모두 CRLF→LF 만 접는다(주석까지 라이브의 일부 — 그 파일의 norm() 과 같은 자).
_DOLLAR = chr(36) * 2
CANON_FN_RE = re.compile(
    r"(?im)^[ \t]*create\s+(?:or\s+replace\s+)?function\s+([\w.]+)\s*\((.*?)"
    + re.escape(_DOLLAR) + r"(.*?)" + re.escape(_DOLLAR) + r"\s*;",
    re.S,
)
CANON_FN_HEAD_RE = re.compile(r"(?im)^[ \t]*create\s+(?:or\s+replace\s+)?function\s+[\w.]+\s*\(")
_SET_RE = re.compile(r"(?im)^[ \t]*set\s+(\w+)\s*(?:=|\bto\b)\s*(.*?)[ \t]*$")
_LANG_RE = re.compile(r"(?i)\blanguage\s+(\w+)")
LIVE_FUNCTION_SQL = (
    "select n.nspname || '|' || p.proname || '|' || l.lanname || '|' || "
    "md5(replace(p.prosrc, chr(13) || chr(10), chr(10))) || '|' || "
    "coalesce(array_to_string(p.proconfig, ';'), '') "
    "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
    "join pg_language l on l.oid = p.prolang "
    "where n.nspname in ('public','api') and p.prokind = 'f' "
    "and not exists (select 1 from pg_depend d where d.classid = 'pg_proc'::regclass "
    "and d.objid = p.oid and d.deptype = 'e');"
)


def _norm_config(item):
    """`search_path = public, pg_temp` · `search_path=public, pg_temp` · `search_path=""` 를
    한 모양으로 (열쇠 소문자 · 값의 공백·따옴표 제거 · 소문자)."""
    key, _, val = str(item).partition("=")
    val = re.sub(r"""[\s'"]""", "", val).lower()
    return "{}={}".format(key.strip().lower(), val)


def body_md5(body):
    return hashlib.md5(body.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def canonical_functions(sql):
    """정본 → {"스키마.이름": (언어, 본문 md5, 설정)} (순수 함수 — 뒤 정의가 이긴다)."""
    out = {}
    for m in CANON_FN_RE.finditer(sql):
        name = m.group(1).strip().lower()
        if "." not in name:
            name = "public." + name
        header = re.sub(r"--[^\n]*", "", m.group(2))   # 머리 주석의 'language' 글자에 안 속게
        lang = _LANG_RE.search(header)
        cfg = sorted(_norm_config(k + "=" + v) for k, v in _SET_RE.findall(header))
        out[name] = ((lang.group(1).lower() if lang else ""), body_md5(m.group(3)), ";".join(cfg))
    return out


def parse_live_functions(raw):
    """psql 출력 → {"스키마.이름": [(언어, md5, 설정), …]} (순수 함수 — 같은 이름 여럿이면 목록)."""
    out = {}
    for line in str(raw or "").splitlines():
        parts = line.strip().split("|")
        if len(parts) != 5:
            continue
        schema, name, lang, md5, cfg = parts
        norm = ";".join(sorted(_norm_config(c) for c in cfg.split(";") if c))
        out.setdefault("{}.{}".format(schema, name).lower(), []).append((lang.lower(), md5, norm))
    return out


def function_drift(canon, live):
    """정본 함수마다 라이브와 다른 점 → [(이름, [사유…])] (순수 함수).

    라이브에만 있는 함수는 이번 범위 밖이다. 같은 이름이 라이브에 여럿(오버로드)이면
    어느 하나가 정본과 완전히 같아도 **남는 것은 옛 판의 찌꺼기**라 사고로 본다.
    """
    out = []
    for name, (lang, md5, cfg) in sorted(canon.items()):
        rows = live.get(name)
        if not rows:
            out.append((name, ["라이브에 없음"]))
            continue
        if len(rows) > 1:
            out.append((name, ["라이브에 같은 이름 {}개(오버로드)".format(len(rows))]))
            continue
        l_lang, l_md5, l_cfg = rows[0]
        why = []
        if l_lang != lang:
            why.append("언어 정본 {} / 라이브 {}".format(lang or "?", l_lang))
        if l_md5 != md5:
            why.append("본문 md5 정본 {} / 라이브 {}".format(md5[:8], l_md5[:8]))
        if l_cfg != cfg:
            why.append("설정 정본 [{}] / 라이브 [{}]".format(cfg, l_cfg))
        if why:
            out.append((name, why))
    return out


def report_function_drift(sql_text=None):
    if sql_text is None:
        with open(SCHEMA_SQL_PATH, encoding="utf-8") as fh:
            sql_text = fh.read()
    canon = canonical_functions(sql_text)
    bad = function_drift(canon, parse_live_functions(query_one(LIVE_FUNCTION_SQL)))
    if bad:
        print("[사고] 정본(schema.sql)과 라이브가 다른 함수 {}개:".format(len(bad)))
        for name, why in bad:
            print("       · {} — {}".format(name, " · ".join(why)))
        print("       파일 없이 라이브만 바뀌었거나(뒷문), 머지한 마이그레이션을 아직 안 적용한 것입니다.")
        print("       ⓘ 또는 아직 머지 안 한 PR 의 마이그레이션을 먼저 적용한 것 — 머지하면 사라집니다.")
        print("       어느 쪽이 맞는지 확인한 뒤 정본이나 라이브를 맞추세요(허용 목록으로 덮지 말 것).")
    else:
        print("[정상] 정본 함수 {}개가 라이브와 언어·본문·설정까지 같습니다.".format(len(canon)))
    return bad


# ④ 별관(TOAST)으로 쫓겨난 작은 값 (2026-10-05 — 사장님 결재) ─────────────────────
#
# 한 줄이 약 2kB 를 넘으면 PostgreSQL 은 저장 방식이 x(extended)·e(external)인 칸의 값을
# 별관(TOAST)으로 내보낸다. 큰 옆 칸이 본관 고정(m — PostGIS 도형이 그렇다)이면 그 대신
# **제 크기와 상관없는 작은 값**들이 쫓겨나고, 그 칸을 훑는 쿼리가 별관을 다시 읽어 10배
# 느려진다(2026-09-27 P10 #164 — district 이름 칸: `distinct source_nm`(시도 11) 15,361쪽·20ms →
# 라이브 적용 뒤 551쪽·2.4ms · 마이그레이션 2026-09-27d 머리말). 에러는 안 난다 — 느려지기만 한다. 그래서 [주의](종료 코드 1 아님 — 느려짐
# 경보와 같은 세기).
# 판정: 별관에 있는데(pg_column_toast_chunk_id 가 not null — PostgreSQL 17 부터) 저장 크기가
# 256바이트 **미만**이면 제 크기 탓이 아니라 옆 칸 탓으로 본다. 큰 값의 별관행(가게 수백 개
# 건물의 이름 묶음 등)은 정상이라 세지 않는다.
# 비용 묶음: 별관에 자료가 있는 표만(별관 크기 > 0) 고르고, 한 표는 한 번만 훑는다.
TOAST_SMALL_BYTES = 256
TOAST_SCAN_TIMEOUT = "60s"
# 1단계 — 볼 표·칸 목록. 한 줄 jsonb 배열: [스키마, 표, 칸, 따옴표 친 표, 따옴표 친 칸] 들.
# ⛔ 이름은 서버가 감싼다(format('%I.%I')·quote_ident) — 대소문자·특수문자가 든 이름도 안전하다.
# ⓘ jsonb 로 받는 이유: json_agg 는 원소 사이에 줄바꿈을 넣지만 jsonb 의 글 모양은 한 줄이다.
# ⓘ 2단계와 같이 앞에 statement_timeout 을 붙인다(출력 앞에 `SET` 줄 — 파서는 마지막 줄만 본다).
TOAST_TARGETS_SQL = (
    "set statement_timeout = '" + TOAST_SCAN_TIMEOUT + "';\n"
    "select coalesce(jsonb_agg(jsonb_build_array(n.nspname::text, c.relname::text, a.attname::text, "
    "format('%I.%I', n.nspname, c.relname), quote_ident(a.attname)) "
    "order by n.nspname, c.relname, a.attnum), '[]'::jsonb)::text "
    "from pg_class c "
    "join pg_namespace n on n.oid = c.relnamespace "
    "join pg_attribute a on a.attrelid = c.oid "
    "where n.nspname in ('public','api') and c.relkind in ('r','m') "
    "and c.reltoastrelid <> 0 and pg_relation_size(c.reltoastrelid) > 0 "
    "and a.attnum > 0 and not a.attisdropped and a.attlen = -1 "
    "and a.attstorage in ('x','e');"
)


def _last_line(raw):
    """psql 출력의 마지막 빈 줄 아닌 줄 — 앞에 `SET` 같은 명령 꼬리표가 붙어 와도 결과만 본다."""
    lines = [ln.strip() for ln in str(raw or "").splitlines() if ln.strip()]
    if not lines:
        raise ValueError("빈 응답")
    return lines[-1]


def parse_toast_targets(raw):
    """TOAST_TARGETS_SQL 의 출력 → [(스키마, 표, 칸, 따옴표 친 표, 따옴표 친 칸)] (순수 함수).

    모양이 틀리면 예외 — "볼 칸 없음"과 "목록을 못 읽음"이 섞이면 조용히 초록이 된다."""
    data = json.loads(_last_line(raw))
    if not isinstance(data, list):
        raise ValueError("대상 목록이 배열이 아닙니다")
    out = []
    for row in data:
        if not (isinstance(row, list) and len(row) == 5
                and all(isinstance(x, str) and x for x in row)):
            raise ValueError("대상 목록 줄 모양이 틀립니다: {!r}".format(row))
        out.append(tuple(row))
    return out


def _group_toast_targets(targets):
    """칸 목록을 표별로 묶는다 → [(따옴표 친 표, [칸 줄…])] (처음 나온 순서 그대로)."""
    groups = []
    index = {}
    for t in targets:
        key = (t[0], t[1])
        if key not in index:
            index[key] = len(groups)
            groups.append((t[3], []))
        groups[index[key]][1].append(t)
    return groups


def build_toast_scan_sql(targets, small_bytes=TOAST_SMALL_BYTES, timeout=TOAST_SCAN_TIMEOUT):
    """2단계 — 표마다 한 번 훑어 칸별 '별관에 있는 작은 값' 수를 센다 (순수 함수 · 탐지는 여기다).

    한 줄 jsonb 배열로 돌려준다: [[표 번호, 칸1 수, 칸2 수, …], …] (표 번호 = 묶은 순서).
    앞에 `set statement_timeout` 을 붙인다 — query_one 은 -c 하나라 같은 문자열에 잇는다
    (그래서 출력 앞에 `SET` 줄이 온다 · parse_toast_scan 은 마지막 줄만 본다).

    못 보는 것:
      · 256바이트 이상인데 옆 칸 탓에 쫓겨난 값 — 제 크기 탓과 구별할 수 없어 일부러 안 센다.
        예: district 의 jsonb 칸(dna_vector·metrics·raw_metrics — 지금 비어 있음)이 채워지면
        도형(m)보다 먼저 쫓겨나는데, 256바이트 이상이면 세지 않는다.
      · 256 은 **압축 뒤** 저장 크기다 — 원래 수 kB 인 값도 압축이 잘 되면 256 미만으로 세어진다.
      · 별관이 빈 표 — 1단계가 고르지 않는다(지금 안 쫓겨났으면 볼 것도 없다).
      · public·api 밖 스키마의 표, 일반 표·요약표가 아닌 것(분할 표의 부모 등).
      · 지금은 쫓겨난 값이 없지만 저장 방식이 x 로 되돌아간 칸(다음 적재 때 다시 쫓겨난다) —
        schema.sql 은 새로 만들 때만 지킨다 · 라이브 저장 방식을 대조하는 점검은 없다
        (값이 다시 쓰여 쫓겨난 뒤에야 이 경보가 잡는다).
      · 칸이 99개를 넘는 표 — jsonb_build_array 의 인자 한도(100)에 걸려 조회가 실패한다
        (조용히 넘어가지 않고 [주의] "점검을 하지 못했습니다"로 나온다).
      · 이름에 한글 등 ASCII 밖 글자가 든 표·칸 — 윈도우에서 psql -c 인자가 cp949 로 넘어가
        서버가 `invalid byte sequence` 로 거부한다(2026-10-05 실측 · 역시 [주의]로 나온다).
    """
    groups = _group_toast_targets(targets)
    if not groups:
        raise ValueError("볼 칸이 없습니다")
    parts = []
    for i, (rel, cols) in enumerate(groups):
        counts = ", ".join(
            "count(*) filter (where pg_column_toast_chunk_id({c}) is not null"
            " and pg_column_size({c}) < {n})".format(c=t[4], n=int(small_bytes))
            for t in cols)
        parts.append("select jsonb_build_array({}, {}) as r from {}".format(i, counts, rel))
    return ("set statement_timeout = '{}';\n".format(timeout)
            + "select coalesce(jsonb_agg(r), '[]'::jsonb)::text from (\n  "
            + "\n  union all ".join(parts) + "\n) s;")


def parse_toast_scan(raw, targets):
    """build_toast_scan_sql 의 출력 → [(스키마, 표, 칸, 수)] 대상 순서대로 (순수 함수).

    물은 표가 다 왔는지·칸 수가 맞는지 본다 — 모자라면 예외(빠진 표를 0 으로 치면 거짓 안심이다)."""
    groups = _group_toast_targets(targets)
    data = json.loads(_last_line(raw))
    if not isinstance(data, list) or len(data) != len(groups):
        raise ValueError("표 {}개를 물었는데 답 모양이 다릅니다".format(len(groups)))
    by_table = {}
    for row in data:
        ok = (isinstance(row, list) and row
              and all(isinstance(x, int) and not isinstance(x, bool) for x in row))
        if not ok or not 0 <= row[0] < len(groups) or row[0] in by_table \
                or len(row) != 1 + len(groups[row[0]][1]):
            raise ValueError("답 줄 모양이 틀립니다: {!r}".format(row))
        by_table[row[0]] = row[1:]
    out = []
    for i, (_, cols) in enumerate(groups):
        for t, n in zip(cols, by_table[i]):
            out.append((t[0], t[1], t[2], n))
    return out


def toast_evictions(counts):
    """쫓겨난 작은 값이 있는 칸만 → [(스키마, 표, 칸, 수)] (순수 함수 — 판정)."""
    return [row for row in counts if row[3] > 0]


def _psql_failure_reason(exc):
    """실패 이유 한 줄(별관 경보·느려짐 경보가 함께 쓴다 — 2026-10-06) — psql 실패면 출력에서 `ERROR:`·`FATAL:`·`psql:` 로 시작하는 첫 줄을,
    그런 줄이 없을 때만 마지막 비어 있지 않은 줄을 고른다.

    마지막 줄만 고르면 `ERROR: relation … does not exist` 뒤의 `줄 1: …`(cp949)·`^` 표시나
    `힌트:` 줄이 찍혀 정작 이유가 사라진다(2026-10-05 재검사관 라이브 실측).
    psql 명령줄(접속 인자·SQL 전문)은 찍지 않는다. 다만 psql 접속 실패면 그 오류 줄 자체에
    호스트 이름이 들어갈 수 있다 — 로컬 화면에만 찍힌다(CI 는 --check 를 돌리지 않는다)."""
    if isinstance(exc, subprocess.CalledProcessError):
        text = (exc.output or b"")
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for ln in lines:
            if ln.startswith(("ERROR:", "FATAL:", "psql:")):
                return ln
        return lines[-1] if lines else "psql 이 이유 없이 실패했습니다(종료 코드 {})".format(exc.returncode)
    first = str(exc).splitlines()[0] if str(exc) else ""
    return "{}: {}".format(type(exc).__name__, first) if first else type(exc).__name__


def report_toast_evictions():
    """별관 쫓겨남 경보를 찍는다. **종료 코드에 영향을 주지 않는다**([주의]까지만).

    조회가 실패해도 --check 전체를 죽이지 않는다 — [주의] 한 줄로 알리고 넘어간다."""
    try:
        targets = parse_toast_targets(query_one(TOAST_TARGETS_SQL))
        if not targets:
            print("[정상] 별관 점검: public·api 에 별관을 쓰는 표가 없습니다 — 볼 칸 0.")
            return []
        counts = parse_toast_scan(query_one(build_toast_scan_sql(targets)), targets)
    except Exception as exc:
        print("[주의] 별관(TOAST) 점검을 하지 못했습니다: {}".format(_psql_failure_reason(exc)))
        return []
    found = toast_evictions(counts)
    for schema, table, column, n in found:
        print("[주의] 별관(TOAST)으로 쫓겨난 작은 값: {}.{}.{} {:,}개({}바이트 미만)".format(
            schema, table, column, n, TOAST_SMALL_BYTES))
    if found:
        print("       고치는 법: 새 마이그레이션 + schema.sql 에 그 칸 `set storage main`(lock_timeout 은 begin 앞 —"
              " 본보기 supabase/migrations/2026-09-27d_district_name_storage.sql) →")
        print("       다시 싣기: 일반 표는 `vacuum full <표>`, 요약표는 concurrently 없는 refresh 또는 vacuum full"
              "(post_load 의 concurrently 갱신은 안 바뀐 줄을 다시 쓰지 않아 별관 값이 그대로 남는다).")
        print("       ⓘ 고장은 아닙니다(종료 코드에 안 넣습니다) — 그 칸을 훑는 쿼리가 별관을 다시 읽어 느려집니다.")
    else:
        print("[정상] 별관 점검: 별관을 쓰는 표 {}개 · 칸 {}개 · 쫓겨난 작은 값({}바이트 미만) 0.".format(
            len(_group_toast_targets(targets)), len(targets), TOAST_SMALL_BYTES))
    return found


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
        _, _, geog_stale = report_tx_geog_freshness()
        _, exposed = report_anon_exposure()
        # 읽기와 쓰기는 따로 묻는다 — 허용 목록에 있는 이름이라도 쓰기가 붙어 있으면 사고다.
        writable = report_write_exposure()
        # 경보 셋(2026-09-27 P7). 느려짐은 [주의]까지만 — 종료 코드에 안 넣는다.
        report_slow_functions()
        # 별관 쫓겨남(2026-10-05)도 [주의]까지만 — 종료 코드에 안 넣는다.
        report_toast_evictions()
        bad_index = report_canonical_indexes()
        drifted = report_function_drift()
        # 분기 표지(2026-10-07a · 결정 0035) — 비었거나 보여 주는 분기가 0행이면 [사고],
        # 구웠는데 안 올렸으면 [낡음] → 둘 다 exit 1. [주의] 둘은 종료 코드 무관.
        rel_fatal, rel_stale = report_snapshot_release()
        return 1 if (stale or map_stale or tx_stale or cov_stale or mix_stale or geog_stale
                     or exposed or writable or bad_index or drifted
                     or rel_fatal or rel_stale) else 0

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
    # 참고 시세 이웃 요약표도 REFRESH_MVS 에 있어 방금 다시 구웠다 — 다시 잰다(2026-10-03).
    _, _, geog_stale = report_tx_geog_freshness()
    if stale or map_stale or tx_stale or cov_stale or mix_stale or geog_stale:
        return 1
    # 요약표를 다 들어온 분기로 굽고 판정 6종을 다 통과했다 — 이제 화면 기준 분기(표지)를 올린다
    # (결정 0035). 다 들어온 분기가 보여 주는 분기보다 새것일 때만 UPDATE 한 줄이 돈다.
    rel_fatal, rel_stale = publish_snapshot_release_if_ready()
    if rel_fatal or rel_stale:
        return 1
    # 권한·옛 문·색인·별관은 --check 에서만 돈다 — 성공했을 때만 이어서 돌리라고 알린다(2026-10-06).
    print("  ⓘ 권한·옛 문 닫힘·색인·함수 일치·느려짐·별관 점검은 여기서 안 돕니다 — 이어서 python scripts/post_load.py --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
