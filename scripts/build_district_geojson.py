# -*- coding: utf-8 -*-
"""`district` 경계를 지도용 정적 파일 `public/districts.geojson` 으로 굽는다.

왜 파일로 굽나 (조회하지 않고)
------------------------------
CLAUDE.md 성능 원칙: **"상권(수천 개)은 사전계산 정적 JSON, 호실(수백만)은 쿼리."**
상권은 1,687개뿐이고 거의 안 변한다. 지도를 열 때마다 1,687개 면을 DB 에서 뽑으면
느리기만 하고 얻는 게 없다 — 한 번 구워 두고 브라우저가 캐시하게 한다.

왜 단순화하나 (그리고 왜 PreserveTopology 인가)
-----------------------------------------------
원본 그대로면 4.98MB 다(실측). 지도에서 상권 하나는 화면 몇 백 픽셀이라 원본 정밀도가
눈에 보이지도 않는데 첫 로딩만 무거워진다. 그래서 **0.0001°(≈11m)** 로 단순화한다 —
실측 4.98MB → **0.76MB**.

⛔ `ST_Simplify` 가 아니라 **`ST_SimplifyPreserveTopology`** 를 쓴다. 앞의 것은 점을
   솎다가 **면을 스스로 교차시켜(자기교차) 깨뜨린다** — 그러면 지도에 리본처럼 꼬인
   도형이 그려지거나 아예 안 그려진다. 에러가 아니라 그림이 이상해지는 종류라 눈으로
   찾기 어렵다. PreserveTopology 는 위상을 지키느라 조금 느릴 뿐 그 사고를 안 낸다.
   실측(2026-08-14): 단순화 뒤 NULL 0개 · `ST_IsValid` 실패 **0개**.

⚠️ 왜 좌표를 소수 6자리로 자르나
--------------------------------
경위도 소수 6자리 = 약 **11cm**. 그 아래는 상권 경계에 의미가 없는데 글자 수만 먹는다
(자릿수 하나가 곧 파일 크기다).

⚠️ 왜 넓은 상권부터 적나 (순서가 곧 그리는 순서다)
--------------------------------------------------
GeoJSON 의 feature 순서대로 지도에 겹쳐 그린다. **넓은 것을 먼저(아래) 좁은 것을
나중(위)** 그려야 좁은 골목상권이 넓은 발달상권에 덮여 사라지지 않는다. 반대로 하면
작은 상권은 클릭도 안 된다. 그래서 `area_m2` **내림차순**으로 적어 둔다
(사장님 확정 겹침 규칙 · 결정 0010).

동점은 `district_id` 로 가른다 — **DB 정렬이 아니라 파이썬에서** 정렬하는 이유가 이것이다.
DB 의 문자열 정렬 규칙(collation)은 서버 설정에 따라 달라질 수 있어서, 같은 자료인데도
줄 순서가 흔들리면 매번 통째로 diff 가 난다.

⚠️ `generated_at` 을 넣지 않는다
--------------------------------
"만든 시각"을 적으면 자료가 하나도 안 바뀌었는데 다시 구울 때마다 파일이 달라져
git diff 가 매번 지저분해진다. 대신 **자료 자체의 시각**(`max(computed_at)`)만 적는다.

신선도는 **정확히 검사할 수 있다** (post_load.py 와 같은 정신)
--------------------------------------------------------------
파일 맨 위 `meta` 에 `district_cnt`·`max_computed_at` 을 박아 둔다. 라이브 `district` 의
`count(*)`·`max(computed_at)` 과 **같아야 한다** — 추측이 아니라 등식이다. 다르면
"상권을 새로 적재하고 이 파일을 다시 굽는 것을 잊었다"가 확정된다.
그 검사는 `python scripts/post_load.py --check` 가 대신 해 준다.

쓰는 법
-------
    python scripts/build_district_geojson.py --dry-run   # 파일 안 씀 (행수·크기만)
    python scripts/build_district_geojson.py             # public/districts.geojson 생성

⚠️ 이 파일은 **생성물이지만 git 에 커밋한다** (화면이 정적으로 읽는 자산이라서).
   그래서 굽는 것은 사람이 판단해서 돌린다 — `post_load.py` 가 자동으로 굽지 않는다.
"""

import io
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import dbx  # noqa: E402  (같은 폴더의 접속 정보 해석기를 그대로 쓴다)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)

# 화면이 정적으로 읽는 자리. Vite 는 `public/` 밑을 그대로 서빙한다(`/districts.geojson`).
OUT_PATH = os.path.join(PROJECT_ROOT, "public", "districts.geojson")

SIMPLIFY_TOLERANCE = 0.0001   # 도(°) 단위 — 약 11m
COORD_DIGITS = 6              # 소수 6자리 = 약 11cm

# 화면이 쓰는 것만 담는다. geom 은 따로(geometry), 나머지 칸은 지도에 필요 없다.
# `source_nm` 은 **빼면 안 된다** — 공공누리 1유형 출처 표기를 자료에서 읽어 보여준다
# (결정 0009 §1-③: 고정 문구를 박으면 소스가 둘이 되는 순간 거짓말이 된다).
PROPERTY_KEYS = (
    "district_id", "district_nm", "district_type",
    "source_nm", "sigungu_code", "area_m2",
)

# ⚠️ 시간대를 **UTC 로 못박아** 찍는다. `computed_at::text` 로 두면 접속 세션의 시간대
#    설정에 따라 `+00` 이 `+09` 로 렌더링돼, 자료가 그대로인데도 신선도 등식이 어긋난다
#    (굽는 사람과 검사하는 사람의 환경이 다르면 바로 터진다).
MAX_COMPUTED_AT_SQL = (
    "to_char(max(computed_at) at time zone 'UTC', "
    "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"')"
)


# ── SQL 만들기 (순수 함수 — 테스트가 여기만 보면 된다) ──────────────────────


def build_features_sql(tolerance=SIMPLIFY_TOLERANCE, digits=COORD_DIGITS):
    """상권 한 개 = JSON 한 줄로 뽑는다.

    한 줄에 하나씩 주는 이유: `json_build_object` 의 출력에는 줄바꿈이 없고(문자열 안의
    줄바꿈은 `\\n` 으로 이스케이프된다) psql `-t -A` 는 행마다 줄을 바꾼다. 그래서
    **받은 줄 수 = 상권 수**가 되어 세는 일이 간단하고 정확해진다.

    ⚠️ 여기서 `order by` 를 쓰지 않는다 — 정렬은 파이썬이 한다(위 모듈 설명 참조).
    """
    props = ", ".join("'{k}', {k}".format(k=k) for k in PROPERTY_KEYS)
    return (
        "select json_build_object("
        "'type', 'Feature', "
        "'properties', json_build_object({props}), "
        "'geometry', st_asgeojson("
        "st_simplifypreservetopology(geom, {tol}), {dig})::json"
        ")::text from district;"
    ).format(props=props, tol=tolerance, dig=digits)


def build_meta_sql():
    """신선도 등식의 오른쪽(라이브) — 행수와 자료 시각을 한 줄로."""
    return ("select count(*)::text || '|' || coalesce({}, '') from district;"
            .format(MAX_COMPUTED_AT_SQL))


def parse_meta_row(raw):
    """`1687|2026-08-13T23:18:22.882729Z` → (1687, '2026-...Z').

    형식이 어긋나면 조용히 넘기지 않고 예외로 멈춘다 — 여기가 어긋난 채 지나가면
    신선도 검사가 **항상 통과**하는 무용지물이 된다.
    """
    cnt, sep, max_ca = raw.strip().partition("|")
    if not sep:
        raise ValueError("메타 한 줄의 형식이 다릅니다(구분자 '|' 없음): {!r}".format(raw))
    return int(cnt.strip()), max_ca.strip()


# ── 문서 조립·검사 (순수 함수) ──────────────────────────────────────────────


def feature_sort_key(feature):
    """넓은 것부터(내림차순), 같으면 district_id 순.

    면적이 비어 있으면 0 으로 본다 — 그런 행은 맨 뒤(가장 위에 그려짐)로 간다.
    지금은 1,687개 전부 면적이 있지만, 없다고 정렬이 깨져 순서가 뒤죽박죽이 되면
    겹침 규칙 자체가 무너지므로 조용히 처리하지 않고 자리를 정해 둔다.
    """
    props = feature.get("properties") or {}
    area = props.get("area_m2")
    return (-(float(area) if area is not None else 0.0),
            str(props.get("district_id") or ""))


def assemble_geojson(feature_texts, district_cnt, max_computed_at):
    """줄 단위 JSON 들을 FeatureCollection 하나로 묶는다.

    받은 줄 수와 라이브 행수가 다르면 **여기서 멈춘다** — 도형이 없어 빠진 상권이
    있는데도 "다 구웠다"고 넘어가면 지도에서 그 상권만 조용히 사라진다.
    """
    features = [json.loads(t) for t in feature_texts]
    if len(features) != int(district_cnt):
        raise ValueError(
            "받은 상권 {}개 ≠ 라이브 행수 {}개 — 도중에 빠진 것이 있습니다."
            .format(len(features), district_cnt))
    features.sort(key=feature_sort_key)
    return {
        "type": "FeatureCollection",
        # ⚠️ FeatureCollection 의 표준 밖 항목(foreign member)이다. GeoJSON 규격이
        #    허용하며, 지도 라이브러리들은 모르는 항목을 그냥 지나친다.
        "meta": {
            "district_cnt": len(features),
            "max_computed_at": max_computed_at,
        },
        "features": features,
    }


def dumps_compact(doc):
    """공백 없이, 한글은 한글 그대로.

    `ensure_ascii=True`(기본값)면 '강남역'이 `\\uac15\\ub0a8\\uc5ed` 로 부풀어
    파일이 커지고 사람이 열어 봐도 못 읽는다.
    """
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def check_document(doc, expected_cnt, expected_max):
    """구운 파일이 정말 맞는지 따진다 — 문제 목록을 돌려준다(빈 목록 = 정상).

    "했다고 믿지 않고 다시 잰다"(post_load.py 관행). 파일을 **다시 읽어서** 이걸 통과해야
    성공으로 친다.
    """
    problems = []
    meta = doc.get("meta") or {}
    features = doc.get("features")

    if doc.get("type") != "FeatureCollection":
        problems.append("최상위 type 이 FeatureCollection 이 아닙니다: {!r}".format(doc.get("type")))
    if not isinstance(features, list):
        return problems + ["features 가 목록이 아닙니다."]

    if len(features) != int(expected_cnt):
        problems.append("파일의 상권 {}개 ≠ 라이브 {}개".format(len(features), expected_cnt))
    if int(meta.get("district_cnt", -1)) != len(features):
        problems.append("meta.district_cnt {} ≠ 실제 feature 수 {}"
                        .format(meta.get("district_cnt"), len(features)))
    if str(meta.get("max_computed_at") or "") != str(expected_max or ""):
        problems.append("meta.max_computed_at {!r} ≠ 라이브 {!r}"
                        .format(meta.get("max_computed_at"), expected_max))
    if "generated_at" in meta:
        problems.append("meta 에 generated_at 이 있습니다 — 다시 구울 때마다 diff 가 납니다.")

    # 도형이 비었으면 지도에 아무것도 안 그려지는데 에러는 안 난다.
    empty = [f for f in features if not (f.get("geometry") or {}).get("coordinates")]
    if empty:
        problems.append("도형이 빈 상권 {}개".format(len(empty)))

    # 겹침 규칙(넓은 것이 아래)이 지켜졌나 — 이게 어긋나면 골목상권이 덮여 안 보인다.
    keys = [feature_sort_key(f) for f in features]
    if keys != sorted(keys):
        problems.append("넓은 상권부터 적혀 있지 않습니다 — 좁은 상권이 덮여 안 보입니다.")

    return problems


def read_meta(path=OUT_PATH):
    """구워 둔 파일의 meta 만 돌려준다 (없거나 깨졌으면 None).

    `post_load.py --check` 가 이걸 읽어 라이브와 대조한다.
    """
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (IOError, OSError, ValueError):
        return None
    meta = doc.get("meta")
    return meta if isinstance(meta, dict) else None


def format_size(n_bytes):
    """사람이 읽는 크기. 글자 수가 아니라 **바이트**다 — 한글 한 글자가 3바이트라
    글자 수로 재면 실제 파일보다 한참 작게 나온다."""
    return "{:.2f}MB ({:,} bytes)".format(n_bytes / 1048576.0, n_bytes)


# ── DB 에서 받아오기 ────────────────────────────────────────────────────────


def query_lines(sql):
    """psql -tA 로 받아 줄 목록으로. 빈 줄은 버린다. 실패하면 예외.

    (post_load.query_one 과 같은 방식 — 비밀번호를 명령줄이 아니라 환경변수로 넘긴다.)
    """
    args, password = dbx.parts()
    env = dict(os.environ)
    env["PGPASSWORD"] = password           # ⚠️ 명령줄 노출 금지 (dbx.py 와 같은 이유)
    env["PGCLIENTENCODING"] = "UTF8"
    cmd = ["psql"] + args + ["-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql]
    out = subprocess.check_output(cmd, env=env, stderr=subprocess.STDOUT)
    return [ln for ln in out.decode("utf-8", "replace").splitlines() if ln.strip()]


def fetch_live_meta():
    lines = query_lines(build_meta_sql())
    if not lines:
        raise ValueError("메타 조회 결과가 비었습니다.")
    return parse_meta_row(lines[0])


def parse_args(argv):
    opts = {"dry_run": False}
    for a in argv:
        if a == "--dry-run":
            opts["dry_run"] = True
        else:
            raise ValueError("알 수 없는 인자: {!r}  (쓸 수 있는 것: --dry-run)".format(a))
    return opts


def main(argv=None):
    # cp949 콘솔에서 한글·특수문자(—) 출력이 UnicodeEncodeError 로 죽지 않게 —
    # 형제 스크립트들(backup_raw.py 등)과 같은 처방(2026-08-14 사실검증에서 누락 발견).
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    opts = parse_args(list(sys.argv[1:] if argv is None else argv))

    live_cnt, live_max = fetch_live_meta()
    print("라이브 상권 {}개 (자료 시각 {}) — 경계를 받아옵니다…".format(live_cnt, live_max))

    feature_texts = query_lines(build_features_sql())
    doc = assemble_geojson(feature_texts, live_cnt, live_max)
    text = dumps_compact(doc) + "\n"
    size = len(text.encode("utf-8"))

    if opts["dry_run"]:
        print("[미리보기] 상권 {}개 · {} — 파일은 쓰지 않았습니다."
              .format(len(doc["features"]), format_size(size)))
        return 0

    # ⚠️ newline="\n" — 윈도우에서 기본값으로 쓰면 CRLF 가 섞여, 내용이 똑같아도
    #    CI(리눅스)에서 구운 것과 파일이 달라진다.
    out_dir = os.path.dirname(OUT_PATH)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    with io.open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("[생성] {} · 상권 {}개 · {}"
          .format(OUT_PATH, len(doc["features"]), format_size(size)))

    # 했다고 믿지 않고 **파일을 다시 읽어** 잰다. 라이브도 다시 물어본다 —
    # 굽는 사이에 자료가 바뀌었다면 이 파일은 이미 낡은 것이라 다시 구워야 한다.
    with io.open(OUT_PATH, "r", encoding="utf-8") as f:
        written = json.load(f)
    again_cnt, again_max = fetch_live_meta()
    problems = check_document(written, again_cnt, again_max)
    if problems:
        print("[실패] 구운 파일이 라이브와 안 맞습니다:")
        for p in problems:
            print("       · {}".format(p))
        print("       (굽는 도중 자료가 바뀌었다면 한 번 더 실행하세요.)")
        return 1

    print("[확인] 파일의 상권 {}개 = meta {}개 = 라이브 {}개, 자료 시각도 같습니다."
          .format(len(written["features"]), written["meta"]["district_cnt"], again_cnt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
