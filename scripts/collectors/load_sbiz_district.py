# -*- coding: utf-8 -*-
"""소상공인시장진흥공단 "주요상권현황" CSV → `district` 표 적재 (기본: 대전만).

왜 대전만인가
-------------
서울 176개도 이 파일에 들어 있지만 **넣지 않는다**. 서울의 정본은 이미 서울시
상권분석서비스 1,650개(결정 0008)다 — 같은 서울을 두 소스로 채우면 한 건물이 두 벌의
상권에 걸려 "속한 상권" 줄이 중복으로 늘어난다. 그래서 기본값은 `--sido-code 30`
(대전, 37개)이고, 다른 시도는 필요할 때 사람이 명시해야 한다.

왜 psql 경유인가 (REST 가 아니라)
---------------------------------
경계를 넣으려면 `ST_GeomFromText`·`ST_MakeValid`·`ST_Area(geography)` 를 서버에서
불러야 하는데 REST(PostgREST)로는 못 부른다. 그래서 SQL 을 만들어 `dbx.py` 에 넘긴다
(load_seoul_district.py 와 같은 방식이다). 새 의존성 0 — pyshp 도 필요 없다(CSV 라서).

⚠️ 좌표 관문 (이 프로젝트에서 가장 비싼 실수를 막는 자리)
---------------------------------------------------------
이 자료의 `상권좌표` 는 `경도,위도|경도,위도|…` 텍스트인데 **좌표계가 어디에도 안 적혀
있다**. 그래서 값 자체를 검사한다 — 모든 점이 경도 124~132·위도 33~39(한국 상자) 안에
있어야 하고, **하나라도 벗어나면 통째로 멈춘다**. 경위도가 뒤바뀌었거나(위도가 경도
자리로 오면 33~39 라 124~132 를 벗어난다) 투영좌표(미터, 수십만 단위)가 섞여 들어오면
여기서 잡힌다. 2026-08-14 에 서울 자료에서 좌표계 관문에 구멍이 있어 사고가 났었다.

⚠️ 한 칸에 링이 여러 개 들어 있다 (36%)
---------------------------------------
처음엔 "상권 하나 = 링 하나"로 봤는데 **틀렸다**(2026-08-14 적대검증). 전 행 실측:

  · 1,227행 중 **440행(36%)** 이 링을 여러 개 담고 있다 — 대전 37개 중 **11개** 포함
  · 링 구분자는 `)|(` 다 (링 경계 0개 787행 / 1개 245 / 2개 112 / 최대 12)
  · 링은 전부(2,043개) **이미 닫혀** 있고, `상권좌표수` 는 **전 링 점 합계**와 1,227행
    모두 정확히 일치한다

그리고 **어느 링이 겉이고 어느 것이 구멍인지 소스가 알려주지 않는다.** 그래서 우리가
정하지 않는다 — 닫힌 링들을 MULTILINESTRING 으로 내보내고 `ST_BuildArea` 가 even-odd
규칙으로 "안에 든 링 = 구멍, 떨어진 링 = 별개 조각"을 스스로 판정하게 한다. 우리가
규칙을 지어내면 그게 곧 숨은 판단이 되고, 섬이 구멍이 되거나 그 반대가 된다.
(링이 하나뿐인 787행도 같은 길을 지난다 — 갈래를 둘로 만들지 않는다.)

⚠️ 큰 칸 (csv 기본 상한에 걸린다)
---------------------------------
`상권좌표` 한 칸이 13만 자를 넘는다. `csv.field_size_limit` 를 올리지 않으면 파이썬이
"field larger than field limit" 로 죽는다. 여기서 올린다.

쓰는 법
-------
    python scripts/collectors/load_sbiz_district.py --dry-run    # DB 쓰기 0
    python scripts/collectors/load_sbiz_district.py              # 대전 37개 적재
    python scripts/collectors/load_sbiz_district.py --sido-code 11 --dry-run
"""

import argparse
import csv
import glob
import io
import os
import re
import sys

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "sbiz_district")

ENCODING = "cp949"
FIELD_SIZE_LIMIT = 2 ** 28        # 상권좌표 한 칸이 13만 자를 넘는다 (기본 상한 131,072)

TARGET_SRID = 4326                # 소스가 경위도이므로 변환 없이 그대로 넣는다
DEFAULT_SIDO = "30"               # 대전 (결정: 서울은 서울시 자료가 정본)
SOURCE_NM = "소상공인시장진흥공단"

# ⛔ 이 소스로 **넣으면 안 되는** 시도 (결정 0009 §1-②).
# 서울은 이 파일에도 176개가 들어 있지만, 서울의 정본은 서울시 상권분석서비스
# 1,650개(결정 0008)다. 둘을 다 넣으면 한 건물이 두 벌의 상권에 걸려 "속한 상권" 줄이
# 중복으로 늘고, 어느 쪽이 진짜인지 화면에서 가릴 방법이 없어진다.
# 이 결정을 사람 기억이 아니라 코드가 지킨다.
BLOCKED_SIDO = {"11": "서울"}

# 서울 자료의 상권코드(3110008 같은 숫자)와 **영구히** 겹치지 않게 접두사를 붙인다.
# 두 소스가 우연히 같은 번호를 쓰면 upsert 가 남의 상권을 덮어쓴다 — 조용한 오염이다.
ID_PREFIX = "sbiz-"

# 한국 상자. 이 밖의 점이 하나라도 있으면 좌표계·순서가 우리 가정과 다른 것이다.
LNG_RANGE = (124.0, 132.0)
LAT_RANGE = (33.0, 39.0)

REQUIRED_COLUMNS = ("상권번호", "상권명", "유형구분", "시도코드",
                    "시군구코드", "상권좌표수", "상권좌표")

BATCH_ROWS = 100
COORD_FMT = "{:.7f}"              # 경위도 소수 7자리 ≈ 1cm. 이보다 더 적을 이유가 없다

# 한 칸 안에서 링을 가르는 표시. 소스가 `…,36.298)|(127.338,…` 처럼 괄호를 맞대어 쓴다.
RING_SEP = ")|("

RE_SIGUNGU = re.compile(r"^\d{5}$")


# ── 순수 함수 (파일·DB 없음 — 테스트 대상) ───────────────────────────────────


def sql_str(value):
    """SQL 문자열 리터럴. 작은따옴표는 두 번 써서 escape 한다."""
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def assert_required_columns(fieldnames):
    """머리글이 우리가 아는 그것인지 확인한다. 다르면 조용히 NULL 이 되지 않게 멈춘다."""
    have = [(f or "").strip().lstrip("﻿") for f in (fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in have]
    if missing:
        raise ValueError(
            "CSV 머리글에 {} 가 없습니다 (있는 것: {}). 소스 형식이 바뀌었습니다.".format(
                ", ".join(missing), ", ".join(have) or "(없음)"))
    return True


def assert_sido_allowed(sido_code):
    """이 소스로 넣으면 안 되는 시도를 **코드가** 막는다 (결정 0009 §1-②).

    사람이 "서울은 넣지 말자"를 기억하는 방식은 언젠가 깨진다 — 몇 달 뒤 전국을 열
    차례가 오면 `--sido-code 11` 이 아무 저항 없이 통과하고, 그날 서울에 상권 정본이
    둘 생긴다. 되돌리려면 어느 1,650개가 원래 것이었는지 다시 가려야 한다.
    """
    code = (sido_code or "").strip()
    if code in BLOCKED_SIDO:
        raise ValueError(
            "시도코드 {}({})는 이 소스로 넣지 않습니다. "
            "서울 정본은 서울시 상권분석서비스 1,650개(결정 0008)입니다 — "
            "이 소스의 서울 176개를 넣으면 정본이 둘이 되어 한 건물이 두 벌의 상권에 "
            "걸립니다(결정 0009 §1-②). "
            "서울 경계를 갱신하려면 scripts/collectors/load_seoul_district.py 를 쓰세요.".format(
                code, BLOCKED_SIDO[code]))
    return True


def assert_korea_point(lng, lat, where):
    """한 점이 한국 상자 안인지 본다. 벗어나면 **전체를 멈춘다**.

    조용히 건너뛰면 경계 일부가 빠진 폴리곤이 들어가고, 그건 "틀린 지도"를 만든다.
    """
    if not (LNG_RANGE[0] <= lng <= LNG_RANGE[1]) or not (LAT_RANGE[0] <= lat <= LAT_RANGE[1]):
        raise ValueError(
            "{}: 좌표가 한국 밖입니다 (경도 {:.6f}, 위도 {:.6f}). "
            "기대 범위는 경도 {:g}~{:g} · 위도 {:g}~{:g} 입니다 — "
            "경위도가 뒤바뀌었거나 투영좌표(미터)가 섞였을 수 있습니다. "
            "그대로 넣으면 조용히 엉뚱한 자리의 상권이 됩니다.".format(
                where, lng, lat, LNG_RANGE[0], LNG_RANGE[1], LAT_RANGE[0], LAT_RANGE[1]))
    return True


def split_rings(coord_text, where):
    """한 칸을 링 여러 개로 가른다 (`…36.298)|(127.338…` → 두 링).

    ★ 이 함수가 없으면 `float('36.298)')` 에서 죽는다 — 처음 판이 실제로 그랬다.
    첫 링 앞·끝 링 뒤에 여는/닫는 괄호가 남아 있을 수 있어(파일마다 다르다) 떼어 낸다.
    링이 하나뿐이어도 같은 길을 지난다 — 갈래를 둘로 만들지 않는다.
    """
    raw = (coord_text or "").strip()
    if not raw:
        raise ValueError("{}: 상권좌표가 비어 있습니다.".format(where))
    rings = [r.strip().lstrip("(").rstrip(")").strip() for r in raw.split(RING_SEP)]
    rings = [r for r in rings if r]
    if not rings:
        raise ValueError("{}: 상권좌표에 링이 하나도 없습니다.".format(where))
    return rings


def parse_ring(coord_text, where):
    """링 하나(`경도,위도|경도,위도|…`) → [(경도, 위도), …]. **적힌 그대로** 돌려준다.

    닫는 일은 close_ring 이 따로 한다 — 여기서 닫아 버리면 점 개수가 늘어
    `상권좌표수` 와 대조할 수 없게 된다(소스가 이미 닫아 보낸 경우와 구분이 안 된다).
    실측으로는 2,043개 링이 전부 이미 닫혀 있었지만, 그건 이 파일 한 판의 사실일 뿐이다.

    · 점이 3개 미만이면 면이 될 수 없다 → 그 행에서 멈춘다(조용한 건너뛰기 금지).
    · 구분자 끝에 붙는 빈 칸은 좌표가 아니므로 버린다 — 실제 개수는 `상권좌표수` 와
      대조해 확인한다(assert_point_count).
    """
    raw = (coord_text or "").strip()
    if not raw:
        raise ValueError("{}: 상권좌표가 비어 있습니다.".format(where))

    pts = []
    for i, token in enumerate(raw.split("|"), start=1):
        token = token.strip()
        if not token:
            continue
        parts = token.split(",")
        if len(parts) != 2:
            raise ValueError(
                "{} {}번째 점: '경도,위도' 형태가 아닙니다: {!r}".format(where, i, token[:60]))
        try:
            lng, lat = float(parts[0]), float(parts[1])
        except ValueError:
            raise ValueError(
                "{} {}번째 점: 숫자가 아닙니다: {!r}".format(where, i, token[:60]))
        assert_korea_point(lng, lat, "{} {}번째 점".format(where, i))
        pts.append((lng, lat))

    if len(pts) < 3:
        raise ValueError(
            "{}: 점이 {}개뿐입니다 — 면이 될 수 없습니다.".format(where, len(pts)))
    return pts


def close_ring(points):
    """WKT 링은 첫 점과 끝 점이 같아야 한다. 다르면 첫 점을 붙인다."""
    return points if points[0] == points[-1] else points + [points[0]]


def assert_point_count(declared, parsed_count, where):
    """`상권좌표수` 와 실제로 읽은 점 개수를 대조한다.

    왜 필요한가: 큰 칸이 어딘가에서 잘려도 **에러가 안 난다** — 짧아진 링은 그냥
    작은 폴리곤이 되어 조용히 들어간다. 소스가 스스로 적어 둔 개수와 맞춰 보는 것이
    그걸 잡는 유일한 방법이다.

    세는 단위 = **전 링 점 합계**(링이 여러 개면 다 더한다). 소스가 적어 준 그대로의
    개수와 비교하며, 우리가 링을 닫으려고 더한 점은 세지 않는다. 실측으로 1,227행
    전부 이 정의에서 정확히 일치했다(2026-08-14).
    """
    text = str(declared or "").strip()
    if not text:
        return True                     # 소스가 안 적어 줬으면 대조할 것이 없다
    try:
        want = int(float(text))
    except ValueError:
        raise ValueError("{}: 상권좌표수가 숫자가 아닙니다: {!r}".format(where, text[:40]))
    if want != parsed_count:
        raise ValueError(
            "{}: 상권좌표수는 {:,}인데 실제로 읽은 점은 {:,}개입니다. "
            "칸이 잘렸을 수 있습니다 — 그대로 넣으면 모양이 다른 상권이 됩니다.".format(
                where, want, parsed_count))
    return True


def ring_to_wkt(points):
    """닫힌 좌표 목록 하나를 WKT 링으로."""
    return "(" + ", ".join(
        (COORD_FMT + " " + COORD_FMT).format(lng, lat) for lng, lat in points) + ")"


def coords_to_linework_wkt(coord_text, declared_count, where):
    """상권좌표 한 칸 → 닫힌 링들의 MULTILINESTRING WKT + 링 개수.

    ⚠️ **폴리곤을 우리가 조립하지 않는다.** 소스는 어느 링이 겉이고 어느 것이 구멍인지
    알려주지 않는다(2,043개 링 어디에도 표시가 없다). 우리가 "먼저 나온 게 겉"이라고
    정하면 그 규칙이 곧 숨은 판단이 되어, 도넛이 섬으로 바뀌거나 그 반대가 된다.

    그래서 선(링)만 내보내고 면 만들기는 SQL 의 `ST_BuildArea` 에 맡긴다 — even-odd
    규칙으로 "안에 든 링 = 구멍, 떨어진 링 = 별개 조각"을 스스로 판정한다.

    돌려주는 값: (wkt, 링 개수)
    """
    ring_texts = split_rings(coord_text, where)
    rings, total = [], 0
    for i, text in enumerate(ring_texts, start=1):
        pts = parse_ring(text, "{} {}번째 링".format(where, i) if len(ring_texts) > 1 else where)
        total += len(pts)
        rings.append(ring_to_wkt(close_ring(pts)))
    assert_point_count(declared_count, total, where)
    return "MULTILINESTRING(" + ", ".join(rings) + ")", len(rings)


def record_to_row(rec, where):
    """CSV 한 줄 → 적재용 dict. 값 정리·검증을 여기서 끝낸다."""
    code = (rec.get("상권번호") or "").strip()
    if not code:
        raise ValueError("{}: 상권번호가 비어 있습니다 — 식별자 없이는 넣을 수 없습니다.".format(where))

    sigungu = (rec.get("시군구코드") or "").strip()
    # district.sigungu_code 는 char(5) 다. 더 긴 코드가 오면 **말없이 잘려** 엉뚱한
    # 시군구가 된다(그리고 covered 판정이 그 앞 2자리를 쓴다). 그래서 미리 막는다.
    if not RE_SIGUNGU.match(sigungu):
        raise ValueError(
            "{}: 시군구코드가 5자리 숫자가 아닙니다: {!r}. "
            "우리 컬럼은 char(5) 라 그대로 넣으면 잘립니다.".format(where, sigungu[:20]))

    wkt, ring_count = coords_to_linework_wkt(
        rec.get("상권좌표"), rec.get("상권좌표수"), where)
    return {
        "district_id": ID_PREFIX + code,
        "district_nm": (rec.get("상권명") or "").strip() or None,
        # 실측: "주요상권" 뒤에 공백이 붙어 온다. 안 떼면 화면에 "주요상권 (…)"처럼 보인다.
        "district_type": (rec.get("유형구분") or "").strip() or None,
        "sigungu_code": sigungu,
        "sido_code": (rec.get("시도코드") or "").strip(),
        "wkt": wkt,
        # 링이 여럿인 행은 36%다. 요약에서 세어 보여 준다 — 조용히 지나가면 다음 세션이
        # 또 "링 하나"라고 착각한다(이 착각이 실제로 첫 판을 깨뜨렸다).
        "ring_count": ring_count,
    }


def row_to_values_sql(row):
    """한 상권을 values(...) 한 줄로. 기하 계산은 전부 아래 build_sql 이 한다."""
    return "({}, {}, {}, {}, {})".format(
        sql_str(row["district_id"]), sql_str(row["district_nm"]),
        sql_str(row["district_type"]), sql_str(row["sigungu_code"]),
        sql_str(row["wkt"]))


def build_insert(chunk):
    """values 목록 한 뭉치 → insert 한 문장.

    왜 `values … cross join lateral` 인가
    -------------------------------------
    폴리곤 WKT 한 칸이 13만 자다. geom 식을 center_lat·center_lng·area 자리마다
    되풀이하면 같은 문자열이 네 번 실려 SQL 이 수십 MB 로 부푼다. lateral 로 한 번만
    만들어 두고 네 자리가 그걸 나눠 쓴다.

    왜 st_buildarea 인가 (우리가 폴리곤을 조립하지 않는다)
    ------------------------------------------------------
    소스는 링만 주고 어느 것이 겉이고 어느 것이 구멍인지 말해 주지 않는다(36%가 링을
    여러 개 갖고 있다). 우리가 규칙을 정하면 그게 숨은 판단이 되므로, 닫힌 링들을 선으로
    넘기고 st_buildarea 가 even-odd 규칙으로 "안에 든 링 = 구멍, 떨어진 링 = 별개 조각"을
    판정하게 한다.

    왜 st_node 를 st_buildarea **앞에** 끼우나
    ------------------------------------------
    자기끼리 꼬인 링(나비넥타이 모양)을 그대로 넘기면 st_buildarea 가 오류가 아니라
    **SQL NULL** 을 돌려준다 — 그 상권은 에러 한 줄 없이 **보이지 않는 행**이 된다
    (2026-08-14 적대검증에서 라이브 쿼리로 확인). 순서를 바꿔 st_makevalid 를 먼저
    걸어도 소용없다: makevalid 는 면을 고치는 도구라 **선에는 무력**하다. st_node 는
    교차점에서 선을 잘라 주므로, 그 뒤 st_buildarea 가 정상적으로 면을 만든다.
    꼬이지 않은 링에는 아무 일도 하지 않으므로 전부에 걸어도 안전하다.

    왜 st_makevalid 를 거치나
    -------------------------
    서울 자료에서는 1,650개 중 6개가 Ring Self-intersection 으로 깨져 있었다. 깨진
    폴리곤에 st_contains 를 쓰면 오류를 던지거나 조용히 틀린 답을 낸다 — "이 건물이 어느
    상권인가"가 이 표의 존재 이유라 그냥 넣을 수 없다. 정상인 폴리곤에는 아무 일도 하지
    않으므로 전부에 걸어도 안전하고, collectionextract(…,3) 은 makevalid 가 드물게
    선·점을 섞어 돌려줄 때 **면만** 남기는 안전핀이다.
    """
    return (
        "insert into district "
        "(district_id, district_nm, district_type, sigungu_code, geom, "
        "center_lat, center_lng, area_m2, source_nm, computed_at)\n"
        "select v.id::text, v.nm::text, v.ty::text, v.gu::char(5), g.geom, "
        "st_y(c.pt), st_x(c.pt), st_area(g.geom::geography), {source}, now()\n"
        "from (values\n{values}\n) as v(id, nm, ty, gu, wkt)\n"
        "cross join lateral (select st_multi(st_collectionextract("
        "st_makevalid(st_buildarea(st_node(st_geomfromtext(v.wkt::text, {srid})))), 3)) "
        "as geom) g\n"
        "cross join lateral (select st_centroid(g.geom) as pt) c\n"
        "on conflict (district_id) do update set "
        "district_nm = excluded.district_nm, "
        "district_type = excluded.district_type, "
        "sigungu_code = excluded.sigungu_code, "
        "geom = excluded.geom, "
        "center_lat = excluded.center_lat, "
        "center_lng = excluded.center_lng, "
        "area_m2 = excluded.area_m2, "
        "source_nm = excluded.source_nm, "
        "computed_at = excluded.computed_at;"
    ).format(source=sql_str(SOURCE_NM), srid=TARGET_SRID,
             values=",\n".join(row_to_values_sql(r) for r in chunk))


def build_sql(rows, batch_rows=BATCH_ROWS):
    """전체 적재 SQL. 한 트랜잭션으로 묶어 **중간에 실패하면 통째로 되돌린다.**

    반쯤 들어간 상권 표는 "있는데 비어 보이는" 최악의 상태다 — 화면이 조용히 틀린
    답을 낸다. 그래서 all-or-nothing 으로 간다.
    """
    if not rows:
        raise ValueError("넣을 상권이 없습니다.")

    # 한 문장 안에 같은 식별자가 두 번 있으면 PostgreSQL 이 "ON CONFLICT DO UPDATE command
    # cannot affect row a second time" 로 **트랜잭션째 죽는다**. 그 메시지만 보고는 원인을
    # 알 수 없으니, 어느 상권이 겹쳤는지 여기서 이름을 대고 멈춘다.
    seen = {}
    for r in rows:
        seen[r["district_id"]] = seen.get(r["district_id"], 0) + 1
    dupes = sorted(k for k, v in seen.items() if v > 1)
    if dupes:
        raise ValueError(
            "같은 상권번호가 여러 번 나옵니다: {}{}. "
            "원본에 중복 행이 있다는 뜻이라 사람이 봐야 합니다.".format(
                ", ".join(dupes[:5]), " 외 {}개".format(len(dupes) - 5) if len(dupes) > 5 else ""))

    out = ["begin;", "set local statement_timeout = '600s';"]
    for i in range(0, len(rows), batch_rows):
        out.append(build_insert(rows[i:i + batch_rows]))
    # 아래 두 점검은 **일부러 성격이 다르다**:
    #   · 면이 안 만들어진 상권 = **관문**(raise exception → 트랜잭션째 되돌린다).
    #     기계가 판정할 수 있는 명백한 결함이고, 그대로 두면 "행은 있는데 지도에 안 보이는"
    #     상권이 남는다. 사람이 나중에 볼 여지가 없으니 아예 들어가지 못하게 막는다.
    #   · 유령 의심 = **정보**(select 로 세어 보여만 준다). 통폐합인지 이번 판의 일시
    #     누락인지는 자료를 봐야 알 수 있어 기계가 정할 수 없다. 여기서 막으면 정상적인
    #     통폐합 때마다 적재가 통째로 실패한다.
    #
    # st_buildarea 가 면을 못 만들면(링이 안 닫히거나 자기끼리 꼬인 극단적인 경우)
    # geom 이 NULL·빈 도형으로 들어간다 — 에러가 아니라 **보이지 않는 상권**이 된다.
    # 행 수는 맞으니 아무도 눈치채지 못한다.
    # ⚠️ 세기만 해서는 못 막는다 — psql 은 select 가 몇을 돌려주든 종료코드 0 이라
    #    "0 이어야 정상"이라고 적어 둬도 그대로 commit 된다. do 블록에서 예외를 던져야
    #    ON_ERROR_STOP 이 걸리고 트랜잭션이 통째로 되돌아간다.
    out.append(
        "do $$\n"
        "declare cnt int;\n"
        "begin\n"
        "  select count(*) into cnt from district\n"
        "   where district_id like '{p}%' and (geom is null or st_isempty(geom));\n"
        "  if cnt > 0 then\n"
        "    raise exception '면이 안 만들어진 상권 %개 — 조용한 반쪽 적재를 막기 위해 "
        "통째로 되돌립니다', cnt;\n"
        "  end if;\n"
        "end $$;".format(p=ID_PREFIX))
    # ⚠️ 세는 범위를 **우리 소스로 한정**한다. 서울 자료의 유령 감지 쿼리를 그대로
    #    베끼면 전역 max(computed_at) 와 비교하게 되어, 대전을 넣는 순간 서울 1,650개가
    #    전부 "유령"으로 잡힌다(오탐).
    # 소스에서 **사라진** 상권은 upsert 로 안 지워진다 — 옛 경계·옛 이름 그대로 남는데
    # 행 수는 비슷해서 아무도 눈치채지 못한다. 지우지도, 막지도 않되(통폐합인지 일시
    # 누락인지 사람이 봐야 한다) 조용히 지나가지 않게 세어서 보여준다.
    out.append(
        'select count(*) as "이번 판에 없던 소진공 상권(유령 의심 — 0 이어야 정상)" '
        "from district where district_id like '{p}%' "
        "and computed_at < (select max(computed_at) from district "
        "where district_id like '{p}%');".format(p=ID_PREFIX))
    out.append("commit;")
    return "\n".join(out) + "\n"


def summarize(rows):
    """사람이 눈으로 확인할 요약. 적재 전후로 같은 것을 본다."""
    by_type, by_gu = {}, {}
    for r in rows:
        by_type[r["district_type"]] = by_type.get(r["district_type"], 0) + 1
        by_gu[r["sigungu_code"]] = by_gu.get(r["sigungu_code"], 0) + 1
    return {
        "total": len(rows),
        "by_type": by_type,
        "by_gu": by_gu,
        # 링이 여럿인 상권 = 구멍이 있거나 조각이 떨어진 상권. 36%가 그렇다(전국 기준).
        "multi_ring": sum(1 for r in rows if r.get("ring_count", 1) > 1),
        "ring_total": sum(r.get("ring_count", 1) for r in rows),
    }


# ── 파일 읽기 ────────────────────────────────────────────────────────────────


def read_csv(path, sido_code=DEFAULT_SIDO):
    """CSV 를 읽어 해당 시도의 행만 돌려준다.

    한 행이라도 검증에 걸리면 그 자리에서 멈춘다 — 나머지를 넣고 "성공"이라고 말하면
    빠진 상권을 아무도 못 찾는다.
    """
    # CLI 뿐 아니라 어느 경로로 불러도 막히도록 여기서 본다(main 은 read_csv 를 지난다).
    assert_sido_allowed(sido_code)
    csv.field_size_limit(FIELD_SIZE_LIMIT)

    rows, seen = [], {}
    with io.open(path, encoding=ENCODING, newline="") as f:
        reader = csv.DictReader(f)
        assert_required_columns(reader.fieldnames)
        for lineno, rec in enumerate(reader, start=2):   # 1행은 머리글
            sido = (rec.get("시도코드") or "").strip()
            seen[sido] = seen.get(sido, 0) + 1
            if sido != sido_code:
                continue
            rows.append(record_to_row(rec, "{}행(상권번호 {})".format(
                lineno, (rec.get("상권번호") or "?").strip())))

    if not rows:
        raise ValueError(
            "시도코드 {!r} 인 상권이 한 건도 없습니다. 파일에 있는 시도코드: {}".format(
                sido_code, ", ".join("{}({:,}행)".format(k or "(빈값)", v)
                                     for k, v in sorted(seen.items()))))
    return rows


def newest_csv(raw_dir):
    """가장 최근에 받은 CSV 를 고른다(원본명에 기준일자가 들어 있어 사전순 = 시간순)."""
    hits = sorted(glob.glob(os.path.join(raw_dir, "*.csv")))
    if not hits:
        raise SystemExit(
            "원본이 없습니다: {}\n"
            "  먼저 받으세요: python scripts/collectors/fetch_sbiz_district.py".format(raw_dir))
    return hits[-1]


def main(argv=None):
    p = argparse.ArgumentParser(description="소진공 주요상권현황 CSV → district 적재")
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    p.add_argument("--csv", help="특정 CSV 를 직접 지정")
    p.add_argument("--sido-code", default=DEFAULT_SIDO,
                   help="넣을 시도코드 (기본 {} = 대전. {} 은 거부한다 — 서울 정본은 "
                        "서울시 자료다, 결정 0009 §1-②)".format(
                            DEFAULT_SIDO, "·".join(sorted(BLOCKED_SIDO))))
    p.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않는다")
    p.add_argument("--sql-out", help="만들어진 SQL 을 이 파일로 저장(검토용)")
    a = p.parse_args(argv)

    csv_path = a.csv or newest_csv(a.raw_dir)
    print("=" * 70)
    print("소진공 주요상권현황 → district 적재 (시도코드 {})".format(a.sido_code))
    print("=" * 70)
    print("  원본: {}".format(csv_path))

    try:
        rows = read_csv(csv_path, a.sido_code)
    except ValueError as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1

    s = summarize(rows)
    print("  상권 {:,}개 / 시군구 {}개".format(s["total"], len(s["by_gu"])))
    print("  링 {:,}개 (링이 여럿인 상권 {:,}개 — 구멍이 있거나 조각이 떨어져 있다)".format(
        s["ring_total"], s["multi_ring"]))
    for k, v in sorted(s["by_type"].items(), key=lambda kv: -kv[1]):
        print("    {:<12} {:>5,}".format(k or "(종류 없음)", v))
    for k, v in sorted(s["by_gu"].items()):
        print("    {:<12} {:>5,}".format(k, v))

    sql = build_sql(rows)
    print("  만들어진 SQL: {:,} 글자".format(len(sql)))

    if a.sql_out:
        with io.open(a.sql_out, "w", encoding="utf-8", newline="\n") as f:
            f.write(sql)
        print("  SQL 저장: {}".format(a.sql_out))

    if a.dry_run:
        print()
        print("--dry-run 지정 — DB 에 아무것도 쓰지 않았습니다.")
        return 0

    import dbx  # noqa: PLC0415  (dry-run 은 DB 설정 없이도 돌아야 한다)
    rc = dbx.run_sql(sql)
    if rc != 0:
        print("적재 실패 (psql 종료코드 {}). 트랜잭션이라 아무것도 안 들어갔습니다.".format(rc),
              file=sys.stderr)
        return rc
    print()
    print("  적재 완료.")
    print("  다음: python scripts/post_load.py   (matview 갱신 + 노출 점검)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
