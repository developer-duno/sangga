# -*- coding: utf-8 -*-
"""백테스트 성적표 CSV 를 화면이 읽는 정적 파일 `public/scorecard-v1.json` 으로 굽는다.

왜 파일로 굽나 (DB 에 넣지 않고)
--------------------------------
성적표는 **자료가 아니라 산출물**이다. `scripts/backtest_price.py` 가 DB 를 읽어 만든
CSV 가 원본이고, 그것을 다시 DB 에 넣으면 같은 사실이 두 곳에 살게 된다. 상권 경계
(`build_district_geojson.py`)와 같은 판단이다 — 몇 백 줄뿐이고 거의 안 변하는 것은
**굽고 커밋**한다.

⛔ 통과 구 목록은 여기서 읽지 않는다
------------------------------------
화면의 "어느 구가 켜지고 꺼졌나"는 **서버 함수 `list_price_gate()`** 로만 읽는다
(결정 0013 §4 — 통과 구 목록의 정본은 서버 한 곳). 이 파일에도 `gate` 칸을 담기는
하지만, 그것은 **"이 성적표 판이 어떤 게이트를 낳았나"의 기록**이지 화면이 보는 값이
아니다. 그래서 화면 쪽 타입(`src/types.ts` 의 `Scorecard`)에는 `gate` 가 아예 없다 —
읽을 수 있게 두면 언젠가 읽고, 그때부터 사본이 정본과 갈린다.

⛔ 숫자를 손으로 옮겨 적지 않는다
---------------------------------
로드맵 Wave 4 가 "숫자 복사 금지"라고 못박은 것이 이 스크립트의 존재 이유다. 화면 코드
(`src/lib/scorecard.ts`·`src/components/ScorecardSection.tsx`)에는 통계 수치가 **한 개도**
없고, 그 사실을 `src/lib/scorecard.test.ts` 가 정규식으로 지킨다.

⚠️ `generated_at` 은 **이 파일을 구운 시각이 아니다**
-----------------------------------------------------
성적표 자체를 뽑은 시각(`docs/backtest/성적표-v1.md` 머리말의 "생성: … (KST)")이다.
구운 시각을 적으면 자료가 하나도 안 바뀌었는데 다시 구울 때마다 파일이 달라져 git diff
가 매번 지저분해진다(`build_district_geojson.py` 가 `generated_at` 을 아예 안 넣는 것과
같은 이유). 화면이 "성적표 v1 · 생성 …"이라고 말할 때 사람이 알고 싶은 것도 **성적을
언제 냈나**이지 파일을 언제 구웠나가 아니다.

⚠️ 판(version)은 손으로 올린다
------------------------------
`v1` 은 성적표 문서의 판 번호다. v2 재생성은 **별건 결재**(통과 구가 조용히 바뀔 수 있어
사장님 확인이 선행 — 로드맵 Wave 4·결정 0013 §4). 그때는 이 상수와 출력 파일 이름,
그리고 화면 쪽 `SCORECARD_URL` 을 함께 올린다.

쓰는 법
-------
    python scripts/build_scorecard_json.py --dry-run   # 파일 안 씀 (무엇을 쓸지만 알려준다)
    python scripts/build_scorecard_json.py             # public/scorecard-v1.json 생성

⚠️ 이 파일은 **생성물이지만 git 에 커밋한다**(화면이 정적으로 읽는 자산이라서).
   성적표 CSV 를 다시 뽑았으면 이 명령을 돌리고 결과를 함께 커밋한다.
"""

import argparse
import hashlib
import io
import json
import os
import re
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)

BACKTEST_DIR = os.path.join(PROJECT_ROOT, "docs", "backtest")

# 성적표 판. 위 머리말 참조 — 올리는 것은 사람 손이고 별건 결재가 선행한다.
VERSION = "v1"

# 화면이 정적으로 읽는 자리. Vite 는 `public/` 밑을 그대로 서빙한다(`/scorecard-v1.json`).
OUT_PATH = os.path.join(PROJECT_ROOT, "public", "scorecard-{}.json".format(VERSION))

# 성적표 문서 — **생성 시각 한 줄만** 여기서 읽는다(숫자는 전부 CSV 에서 온다).
DOC_PATH = os.path.join(BACKTEST_DIR, "성적표-{}.md".format(VERSION))

# 굽는 데 쓰는 CSV. `검증거래별원자료.csv`(개별 실거래)와 `1층유형별지표.csv`(L7 유형축
# 검증 — 아직 결재 전 실험)는 **일부러 안 읽는다.**
#   ⛔ 원자료는 필지·층·단가가 든 개별 거래라, 밖으로 내보내려면 별건 판단이 필요하다.
#   ⛔ 1층 유형축은 결정 0013 §3 이 1층을 미제공으로 정한 뒤의 후속 실험이라, 화면에
#      올리면 "쓰지 않기로 한 값"을 성적표라며 보여주게 된다.
STAGE_CSV = "단계별지표.csv"
OPS_CSV = "운영모드지표.csv"
GATE_CSV = "통과구.csv"
CSV_SOURCES = (STAGE_CSV, OPS_CSV, GATE_CSV)

# ── CSV 칸 이름 → JSON 칸 이름 ────────────────────────────────────────────────
#
# 한글 칸 이름을 그대로 JSON 에 쓰지 않는 이유: 화면 코드가 이 이름으로 값을 꺼내는데,
# 거기서는 영문 식별자라야 오타를 편집기가 잡아 준다. 뜻은 아래 표가 정본이다.
#
# ⚠️ 값의 뜻(원본 CSV 그대로):
#   검증거래수   = 채점 대상이 된 거래 수
#   추정성립수   = 그중 그 단계가 값을 낸 거래 수
#   커버리지     = 추정성립수 / 검증거래수 (0~1)
#   MdAPE·MAPE  = 오차 중앙값·평균 (0~1 비율)
#   적중률20     = ±20% 안에 맞힌 비율 (0~1)
#
# (칸 이름, JSON 이름, 값 종류) — 값 종류는 'text' | 'int' | 'num' | 'bool'.
STAGE_COLUMNS = (
    ("단계", "stage", "text"),
    ("축", "axis", "text"),
    ("축값", "axis_value", "text"),
    ("축값이름", "axis_name", "text"),
    ("검증거래수", "n_verified", "int"),
    ("추정성립수", "n_estimated", "int"),
    ("커버리지", "coverage", "num"),
    ("MdAPE", "mdape", "num"),
    ("MAPE", "mape", "num"),
    ("적중률20", "hit20", "num"),
)

# 운영 모드(사다리)를 여러 축으로 자른 것. `구분` 이 '채택단계' 인 줄들이 화면의
# **"체감 단계 분포"** 다 — 사다리가 실제로 어느 칸에서 멈췄나(로드맵 Wave 4).
OPS_COLUMNS = (
    ("구분", "kind", "text"),
    ("축값", "axis_value", "text"),
    ("축값이름", "axis_name", "text"),
    ("검증거래수", "n_verified", "int"),
    ("추정성립수", "n_estimated", "int"),
    ("커버리지", "coverage", "num"),
    ("MdAPE", "mdape", "num"),
    ("MAPE", "mape", "num"),
    ("적중률20", "hit20", "num"),
)

# 통과구.csv 는 이미 영문 칸이다(그대로 `price_gate_sigungu` 로 들어가는 파일이라서).
GATE_COLUMNS = (
    ("sigungu_code", "sigungu_code", "text"),
    ("sigungu_nm", "sigungu_nm", "text"),
    ("n_paired", "n_paired", "int"),
    ("ladder_mdape", "ladder_mdape", "num"),
    ("base_mdape", "base_mdape", "num"),
    ("gate_pass", "gate_pass", "bool"),
)

# 화면이 반드시 있어야 그릴 수 있는 것들. 하나라도 없으면 카드가 **에러 없이** 반쪽이
# 되므로 굽는 자리에서 멈춘다.
REQUIRED_OPS_KINDS = ("전체", "채택단계")

# 성적표 머리말의 "> 생성: 2026-08-15 23:44 (KST) · …" 한 줄.
RE_DOC_GENERATED = re.compile(
    r"생성:\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})\s*\(KST\)"
)

# 굽고 난 뒤 되재는 눈. **한국 시각(+09:00)이라야 한다** — 시간대를 안 적으면 읽는 쪽
# (브라우저)이 제 시간대로 해석해 날짜가 하루 밀린다(글로벌 규칙: 한 시스템 한 시간축).
RE_KST_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00")


# ── 순수 함수 (테스트가 여기만 보면 된다) ────────────────────────────────────


def read_text(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_generated_at(doc_text):
    """성적표 머리말에서 **성적을 낸 시각**을 뽑아 KST ISO 로.

    ⛔ 못 찾으면 조용히 지금 시각으로 때우지 않고 **멈춘다.** 여기서 때우면 화면의
       "생성 …" 도장이 성적과 상관없는 값이 되고, 그 거짓말은 아무 에러도 안 낸다.
    """
    m = RE_DOC_GENERATED.search(doc_text)
    if not m:
        raise ValueError(
            "성적표 머리말에서 '생성: YYYY-MM-DD HH:MM (KST)' 를 못 찾았습니다 — "
            "형식이 바뀌었으면 이 정규식도 함께 고치세요."
        )
    y, mo, d, h, mi = m.groups()
    return "{}-{}-{}T{:02d}:{}:00+09:00".format(y, mo, d, int(h), mi)


def to_int(raw):
    """빈 칸은 None. '2986' → 2986."""
    s = (raw or "").strip()
    if s == "":
        return None
    return int(s)


def to_num(raw):
    """빈 칸은 None. '0.29056' → 0.29056 (정수로 떨어지면 int 로 준다).

    ⓘ `no_estimate` 줄의 MdAPE 처럼 **비어 있는 것이 정상**인 칸이 있다. 그때 0 으로
      메우면 "오차 0%"라는 정반대의 뜻이 된다 — 없는 것은 없는 채로 둔다.
    """
    s = (raw or "").strip()
    if s == "":
        return None
    v = float(s)
    return int(v) if v.is_integer() else v


def to_bool(raw):
    """'true'/'false' (통과구.csv 는 파이썬이 쓴 소문자다). 그 밖의 값은 예외."""
    s = (raw or "").strip().lower()
    if s in ("true", "1"):
        return True
    if s in ("false", "0"):
        return False
    raise ValueError("참/거짓으로 읽을 수 없는 값입니다: {!r}".format(raw))


_CASTS = {"text": lambda s: (s or "").strip(), "int": to_int, "num": to_num, "bool": to_bool}


def map_row(raw_row, columns):
    """CSV 한 줄 → JSON 한 줄. 표에 없는 칸은 **버린다**(새 칸이 조용히 새어 나가지 않게)."""
    out = {}
    for csv_key, json_key, kind in columns:
        if csv_key not in raw_row:
            raise KeyError("CSV 에 '{}' 칸이 없습니다 — 성적표 형식이 바뀌었습니다".format(csv_key))
        out[json_key] = _CASTS[kind](raw_row[csv_key])
    return out


def parse_csv(text, columns):
    """BOM 이 있어도 없어도 같은 결과.

    ⚠️ 이 CSV 들은 엑셀에서 열리라고 **BOM 을 달고** 쓰였다(`utf-8-sig`). 파일을 바이트로
       읽어 여기로 넘기는 쪽이 BOM 을 안 걷으면 첫 칸 이름이 `\\ufeff단계` 가 되어 "칸이
       없습니다"로 터진다 — 그래서 이 함수가 스스로 걷는다.
    """
    import csv as _csv

    if text.startswith("﻿"):
        text = text[1:]
    reader = _csv.DictReader(io.StringIO(text))
    return [map_row(row, columns) for row in reader]


def sha256_of_text(text):
    """원본 파일의 지문. 성적표가 바뀌었는데 굽는 것을 잊었는지 나중에 대조할 수 있다."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assemble(stages, ops_modes, gate, sources, generated_at, version=VERSION):
    return {
        "version": version,
        # 위 머리말 참조 — **성적을 낸 시각**이지 이 파일을 구운 시각이 아니다.
        "generated_at": generated_at,
        "sources": sources,
        "stages": stages,
        "ops_modes": ops_modes,
        # ⛔ 화면은 이 칸을 읽지 않는다(정본은 서버 `list_price_gate()`). 기록으로만 둔다.
        "gate": gate,
    }


def check_document(doc):
    """구운 것이 쓸 만한지 따진다 — 문제 목록을 돌려준다(빈 목록 = 정상).

    "했다고 믿지 않고 다시 잰다"(post_load.py·build_district_geojson.py 관행).
    여기서 잡는 것은 전부 **에러 없이 화면만 반쪽이 되는** 종류다.
    """
    problems = []

    if doc.get("version") != VERSION:
        problems.append("version 이 {!r} 가 아닙니다: {!r}".format(VERSION, doc.get("version")))
    if not RE_KST_ISO.fullmatch(str(doc.get("generated_at") or "")):
        problems.append("generated_at 이 KST 시각 모양이 아닙니다: {!r}".format(doc.get("generated_at")))

    sources = doc.get("sources")
    if not isinstance(sources, dict) or set(sources) != set(CSV_SOURCES):
        problems.append("sources 가 원본 {}개의 해시가 아닙니다: {!r}".format(
            len(CSV_SOURCES), sorted(sources) if isinstance(sources, dict) else sources))
    else:
        for name, digest in sources.items():
            if not re.fullmatch(r"[0-9a-f]{64}", str(digest or "")):
                problems.append("{} 의 해시가 sha256 모양이 아닙니다".format(name))

    for key in ("stages", "ops_modes", "gate"):
        rows = doc.get(key)
        if not isinstance(rows, list) or not rows:
            problems.append("{} 가 비어 있습니다".format(key))

    ops = doc.get("ops_modes") or []
    kinds = {r.get("kind") for r in ops if isinstance(r, dict)}
    for need in REQUIRED_OPS_KINDS:
        if need not in kinds:
            # 화면의 단계 분포·커버리지 공지가 통째로 사라지는 자리다.
            problems.append("운영모드 표에 '{}' 줄이 없습니다".format(need))

    # 개별 거래가 새어 들어왔는지 — 칸 이름을 표로 못박아 두었으니 원리적으로 못 오지만,
    # 표를 손대는 날 이 가드가 먼저 운다.
    allowed = {
        "stages": {j for _, j, _ in STAGE_COLUMNS},
        "ops_modes": {j for _, j, _ in OPS_COLUMNS},
        "gate": {j for _, j, _ in GATE_COLUMNS},
    }
    for key, keys in allowed.items():
        for row in (doc.get(key) or []):
            if isinstance(row, dict) and set(row) != keys:
                problems.append("{} 의 칸이 표와 다릅니다: {}".format(key, sorted(set(row) ^ keys)))
                break

    return problems


def dumps_compact(doc):
    """공백 없이, 한글은 한글 그대로(`build_district_geojson.dumps_compact` 와 같은 이유)."""
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def display_path(path, start=PROJECT_ROOT):
    """사람에게 보여줄 경로. 프로젝트 안이면 짧게, 아니면 그대로.

    ⚠️ `os.path.relpath` 는 윈도우에서 **드라이브가 다르면 예외로 터진다**(임시 폴더가
       C: 이고 레포가 D: 인 이 PC 가 정확히 그 경우다). 화면에 예쁘게 적으려다 굽기가
       통째로 실패하면 안 되므로 여기서 받아 넘긴다.
    """
    try:
        return os.path.relpath(path, start)
    except ValueError:
        return path


def format_size(n_bytes):
    """사람이 읽는 크기. 글자 수가 아니라 **바이트**다(한글 한 글자가 3바이트)."""
    return "{:.1f}KB ({:,} bytes)".format(n_bytes / 1024.0, n_bytes)


# ── 조립 ────────────────────────────────────────────────────────────────────


def build(backtest_dir=BACKTEST_DIR, doc_path=DOC_PATH):
    """CSV 3개 + 성적표 머리말 → 문서 하나. 파일은 쓰지 않는다."""
    texts = {name: read_text(os.path.join(backtest_dir, name)) for name in CSV_SOURCES}
    return assemble(
        stages=parse_csv(texts[STAGE_CSV], STAGE_COLUMNS),
        ops_modes=parse_csv(texts[OPS_CSV], OPS_COLUMNS),
        gate=parse_csv(texts[GATE_CSV], GATE_COLUMNS),
        sources={name: sha256_of_text(text) for name, text in texts.items()},
        generated_at=parse_generated_at(read_text(doc_path)),
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description="성적표 CSV → public/scorecard-v1.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="파일을 쓰지 않고 무엇을 쓸지만 보여준다")
    args = ap.parse_args(argv)

    doc = build()
    body = dumps_compact(doc)
    problems = check_document(doc)

    print("성적표 {} · 생성 {}".format(doc["version"], doc["generated_at"]))
    for name in CSV_SOURCES:
        print("  원본 {:<16} sha256 {}…".format(name, doc["sources"][name][:12]))
    print("  단계별 {}줄 · 운영모드 {}줄 · 게이트 {}줄".format(
        len(doc["stages"]), len(doc["ops_modes"]), len(doc["gate"])))
    print("  대상 파일 {} · {}".format(
        display_path(OUT_PATH), format_size(len(body.encode("utf-8")))))

    if problems:
        print("\n[중단] 굽기 전 점검에서 걸렸습니다:")
        for p in problems:
            print("  · {}".format(p))
        return 1

    if args.dry_run:
        print("\n[미리보기] 파일을 쓰지 않았습니다. 실제로 구우려면 --dry-run 을 빼세요.")
        return 0

    with io.open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)

    # 썼다고 믿지 않고 **다시 읽어** 확인한다.
    with io.open(OUT_PATH, "r", encoding="utf-8") as f:
        again = json.load(f)
    problems = check_document(again)
    if problems:
        print("\n[중단] 쓴 파일을 다시 읽었더니 어긋납니다:")
        for p in problems:
            print("  · {}".format(p))
        return 1

    print("\n[완료] {} — 이 파일은 **커밋해야** 화면에 반영됩니다.".format(
        display_path(OUT_PATH)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
