# -*- coding: utf-8 -*-
"""마이그레이션 2026-09-09c(상호명으로 찾기 — 결정 0028)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다.
DB 없이 SQL 글자만 본다(CI 에는 DB 가 없다) — 대신 아래는 글자만으로 확실히 잡힌다.

  0) **기존 표와 그 사슬을 건드린다** ← 이 파일에서 가장 중요한 가드.
     이 마이그레이션의 1차 초안은 mv_search_parcel 에 칸을 더하려고 그 표를 떨어뜨렸다
     다시 만들었고, 거기 기대어 사는 넷(mv_open_sigungu → mv_coverage_stats →
     v_coverage_stats → api.v_coverage_stats)까지 함께 되세우는 538줄이 됐다. 그건
     ①"⛔ drop 하고 다시 만들지 말 것"이라 못 박아 둔 뷰를 건드리고 ②되세울 본문을
     정본에서 베껴 오다 정본↔라이브 드리프트를 **라이브에 실어 나른다**(2026-09-01
     감사에서 함수 8개가 실제로 갈려 있었다). 그래서 **형제 표**로 방향을 바꿨다 —
     기존 표·사슬을 한 글자도 안 건드린다. 그 약속을 기계가 지킨다.
  1) 나가는 칸이 늘어난다 → 이 함수의 계약은 **땅 한 줄 + 일치 상호 최대 3개**다.
     biz_no·업종 코드·점포 좌표를 붙이는 순간 점포 원자료가 공개키로 새는 길이 된다.
  2) `sigungu` 없이도 답한다 → 상호는 같은 이름이 전국에 널려 있어 구 없이는 답이
     될 수 없다(결정 0007). 조건 한 줄이 빠지면 **전국 검색이 조용히 열린다.**
  3) `grant` 가 `revoke` 보다 먼저 온다 → 대시보드가 함수를 다시 만들 때 붙는 anon
     기본권한을 못 걷는다.
  4) `notify pgrst` 누락 → DB 에는 함수가 멀쩡히 있는데 화면만 404(PGRST202) 가 난다.
  5) 정본(schema.sql) 미동기 → 새 환경만 다르게 만들어진다.
  6) 새 표가 mv_search_parcel 을 **참조하게** 된다 → 참조하는 순간 그 사슬에 하나 더
     매달려, 다음에 그 표를 손볼 사람이 여기까지 함께 떨어뜨려야 한다(방금 피한 그 일).
  7) `drop index idx_ub_name` 이 덩어리 **안**으로 들어간다 → ACCESS EXCLUSIVE 락이
     커밋까지 유지돼, 표를 굽는 내내 점포 표 읽기가 전부 줄을 선다(2026-08-22c).

ⓘ 도우미(read·statements·flat·fn_block)는 형제 test_tx_yearly_migration.py 에서
  **복사**해 왔다 — import 하지 않는다. 시험 파일끼리 얽히면 한쪽의 고장이 다른 쪽을
  조용히 가린다. (returns_columns 만은 새로 썼다 — 형제 것은 `char(19)` 처럼 괄호가
  든 타입에서 첫 칸만 읽고 멈춘다.)
"""

import hashlib
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

MIG_DIR = os.path.join(ROOT, "supabase", "migrations")
MIGRATION = os.path.join(MIG_DIR, "2026-09-09c_search_stores.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

# 이름 대조를 자르기 **뒤로** 옮긴 판(0028 §백로그 🟡-5). public 쪽 함수만 다시 만든다 —
# api 쌍둥이는 통과 함수라 한 글자도 안 건드린다(그래서 쌍둥이의 최신은 아직 09-09c 다).
NEW_MIGRATION = os.path.join(
    MIG_DIR, "2026-09-10b_search_stores_names_after_limit.sql")

BOTH = [MIGRATION, SCHEMA]

FN = "search_stores"
NEW_MV = "mv_parcel_store_names"
OLD_INDEX = "idx_ub_name"

# ⛔ 이 마이그레이션이 **한 글자도 안 건드리기로 한** 것들. 1차 초안이 이 다섯을 전부
#    떨어뜨렸다 되세웠고, 그 판을 버린 것이 이 PR 의 방향 전환이다(위 docstring 0).
# ⓘ `v_coverage_stats` 는 `mv_coverage_stats` 의 뒷부분이기도 하다 — 그래서 아래 검사는
#    반드시 낱말 경계(\b)로 찾는다. `\bv_coverage_stats\b` 는 "mv_coverage_stats" 안에서
#    안 걸린다(m 과 v 사이에는 낱말 경계가 없다).
PROTECTED = (
    "mv_search_parcel",
    "mv_open_sigungu",
    "mv_coverage_stats",
    "v_coverage_stats",
)

# 정본에서 그 다섯 문장을 뜯어 낸 **원문 그대로**의 SHA-256(2026-09-09, origin/main 기준).
# ⛔ 이 값이 안 맞으면 "누군가 그 문장을 고쳤다"는 뜻이다. 이 PR 의 전제가 무너진 것이니
#    상수를 조용히 갱신하지 말 것 — 정말 그 표를 고쳐야 한다면 그건 **별건 결정**이고,
#    사슬 넷을 어떻게 다룰지부터 다시 정해야 한다(위 docstring 0).
# ⓘ 왜 `git show origin/main:…` 으로 대조하지 않나: CI 의 checkout 은 얕아서(fetch-depth
#   기본 1) origin/main 이 아예 없다 — 그러면 이 가드가 조용히 건너뛰어진다(가짜 초록).
CANON_STATEMENT_SHA = {
    "mv_search_parcel":
        "8d731a2729e2eb5ea6ca5db2e6f73bc4e38bd51f61ce0ddee00be7a45b3949c4",
    "mv_open_sigungu":
        "681ecf13de19675ab4f977a8ce1c7078b6514b54c55579d08963fa9b83fc8f86",
    "mv_coverage_stats":
        "ce57acc493a75969d784ed4896ad73294d97198256930834d43168e9524b2df2",
    "v_coverage_stats":
        "161a8aefd7126bac44cd423d73b699ee1bee8c799aef8f8b2f92a70093186f55",
    "api.v_coverage_stats":
        "f4b9c20328bd2e7c2bcdcf4a7ee52854479529a30c1783fd018855d2958bdb87",
}

CANON_HEADER = {
    "mv_search_parcel":
        r"^create materialized view if not exists mv_search_parcel as\b",
    "mv_open_sigungu":
        r"^create materialized view if not exists mv_open_sigungu as\b",
    "mv_coverage_stats":
        r"^create materialized view if not exists mv_coverage_stats as\b",
    "v_coverage_stats":
        r"^create or replace view v_coverage_stats as\b",
    "api.v_coverage_stats":
        r"^create or replace view api\.v_coverage_stats as\b",
}

NEW_MV_HEADER = (
    r"^create materialized view if not exists %s as\b" % NEW_MV)

# 나가도 되는 칸 — **이것이 전부다**. 땅 한 줄(대표 동·주소·층 요약)과, 그 땅에서
# 무엇이 몇 곳 걸렸는지, 그리고 전체 규모·너무 넓은지·언제 기준 자료인지.
RETURNED_COLUMNS = (
    "pnu",
    "bld_id",
    "bld_nm",
    "road_addr",
    "jibun_addr",
    "lat",
    "lng",
    "bld_cnt_in_pnu",
    "floor_cnt",
    "min_floor",
    "max_floor",
    "has_roof",
    # 화면에 적을 상호 최대 3개와, 그 땅에서 걸린 가게 수.
    "matched_names",
    "match_store_cnt",
    # 잘리기 전 전체 규모(모든 행에 같은 값) — '더 보기'와 "N곳" 문구가 이걸 읽는다.
    "total_parcel_cnt",
    "total_store_cnt",
    # 너무 넓은 검색어면 0건이 아니라 이 칸이 참인 **한 줄**로 답한다.
    "too_broad",
    # "2026년 6월 기준 점포 자료" 도장(서버 값 — 화면에 숫자 리터럴 0).
    "store_snapshot_ym",
)

# 새 표가 내놓는 칸과 **그 칸이 어떻게 만들어지는지**를 함께 못 박는다.
# ⛔ 이름만 보면 안 된다 — 예컨대 store_names 를 distinct 로 접어도 이름은 그대로다.
NEW_MV_OUTPUT = (
    "pc.pnu,",
    "substr(pc.pnu, 1, 5)::char(5) as sigungu_code,",
    "s.store_names,",
    "s.store_names_key,",
    "s.store_cnt,",
    "(select l.ym from latest l)::char(6) as store_snapshot_ym",
)

# (이름, 유니크인가) — 셋 다 있어야 한다.
NEW_MV_INDEXES = (
    ("idx_mpsn_pnu", True),      # unique — refresh … concurrently 의 자격 요건
    ("idx_mpsn_sigungu", False),
    ("idx_mpsn_names", False),
)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def norm(text):
    """줄바꿈 표기(CRLF/LF)만 통일한다 — 공백·주석은 일부러 안 건드린다.

    ⛔ 이걸 빼면 `.gitattributes` 나 편집기 설정이 바뀐 날 해시 가드가 통째로 빨개진다
      (2026-08 훅이 CRLF 로 바뀌어 조용히 안 돌던 사고의 반대 얼굴).
    """
    return text.replace("\r\n", "\n")


def statements(sql):
    """주석을 걷어낸 **실제 SQL 문장만** (줄바꿈은 그대로 — `(?m)^…` 정규식용).

    설명 주석에 적어 둔 말이 문장으로 오해되면 코드가 망가져도 초록이 된다
    (형제 test_tx_yearly_migration·test_price_gate_migration 이 같은 방식을 쓴다).
    """
    return "\n".join(
        line for line in norm(sql).splitlines() if not line.lstrip().startswith("--")
    )


# `comment on … is '…';` 한 문장. 여러 줄에 걸치고, 끝은 항상 `';` 다.
RE_COMMENT_STMT = re.compile(r"(?ims)^comment\s+on\s+.*?';\s*$")


def code_only(sql):
    """주석 **그리고 `comment on … is '…'` 문장까지** 걷어낸 것.

    ⛔ 왜 필요한가: `comment on` 의 본문은 사람이 읽는 **글**인데 SQL 로는 엄연한 문장이라
       `statements()` 에 그대로 남는다. 이 파일의 코멘트에는 "형제 mv_search_parcel 과…"
       같은 설명이 들어 있어서, 그것만 보고 "사슬을 건드렸다"고 판정하면 가드가 영영
       빨간불이 된다 — 그러면 사람이 가드를 느슨하게 고친다.
       (2026-09-01 감사에서 `comment on column` 문자열 때문에 인덱스 가드에 구멍이 났던
        것과 **같은 병**이다. 그때는 반대 방향으로 새서 못 잡았고, 여기서는 헛것을 잡는다.)
    """
    return RE_COMMENT_STMT.sub("", statements(sql))


def flat(sql):
    """주석을 걷고 **공백을 한 칸으로** 접은 것 — 권한 문장 단언은 전부 이것을 본다.

    ⛔ 왜 접나: 정본은 권한 문장을 칸 맞춰 적는다. 원문 그대로 찾으면 그 정렬 때문에
       "없다"고 판정해 거짓 빨간불이 나고, 그러면 사람이 시험을 느슨하게 고치게 된다.
    """
    return re.sub(r"\s+", " ", statements(sql))


def sql_block(text, header_pattern):
    """줄머리가 `header_pattern` 인 문장 하나를 **원문 그대로** 뜯어 온다.

    끝은 "주석을 뗀 부분이 `;` 로 끝나는 첫 줄"이다 — 문장 안의 설명 주석에 세미콜론이
    들어 있어도 거기서 안 끊긴다.
    """
    lines = norm(text).splitlines()
    for i, line in enumerate(lines):
        if re.match(header_pattern, line, re.I):
            out = []
            for j in range(i, len(lines)):
                out.append(lines[j])
                if lines[j].split("--")[0].rstrip().endswith(";"):
                    return "\n".join(out)
            raise AssertionError("문장이 안 끝납니다: " + header_pattern)
    raise AssertionError("못 찾았습니다: " + header_pattern)


def fn_block(sql, name=FN, schema=""):
    """`create or replace function [schema.]<name>(` 부터 `$$;` 까지 (본문 + 머리)."""
    sql = norm(sql)
    m = re.search(
        r"(?im)^create\s+or\s+replace\s+function\s+"
        + (re.escape(schema) if schema else r"(?!api\.)(?:public\.)?")
        + name + r"\s*\(",
        sql,
    )
    assert m, "{}{} 정의를 못 찾았습니다".format(schema, name)
    end = sql.index("$$;", m.start())
    return sql[m.start():end]


def returns_columns(block):
    """`returns table ( … )` 안의 칸 이름을 **적힌 순서대로**.

    ⛔ 괄호 짝을 세어 닫는다 — `pnu char(19)` 처럼 타입 안에 괄호가 있으면, 첫 `)` 에서
       끊는 형제 구현은 **첫 칸 하나만 읽고 멈춘다**(그러면 칸이 열일곱 개 늘어도 초록).
    """
    start = block.index("returns table")
    open_at = block.index("(", start)
    depth = 0
    close_at = None
    for j in range(open_at, len(block)):
        if block[j] == "(":
            depth += 1
        elif block[j] == ")":
            depth -= 1
            if depth == 0:
                close_at = j
                break
    assert close_at is not None, "returns table 의 괄호가 안 닫힙니다"
    head = block[open_at:close_at]
    return tuple(m.group(1) for m in re.finditer(r"(?m)^\s+(\w+)\s+\w", head))


def at(pattern, sql, last=False):
    """줄머리 정규식이 처음(또는 마지막) 나오는 **위치**."""
    found = [m.start() for m in re.finditer(pattern, sql)]
    assert found, pattern
    return found[-1] if last else found[0]


def sha(text):
    return hashlib.sha256(norm(text).encode("utf-8")).hexdigest()


# `create [or replace] function [public.]search_stores(` — api 쌍둥이는 뺀다.
RE_DEFINES_FN = re.compile(
    r"(?im)^create\s+(?:or\s+replace\s+)?function\s+(?!api\.)(?:public\.)?"
    + FN + r"\s*\(")


def latest_migration_defining_the_function():
    """public 쪽 `search_stores` 를 정의하는 **가장 최신** 마이그레이션 경로.

    ⛔ 파일 이름을 상수로 박지 않는다 — 박아 두면 다음에 이 함수를 또 고치는 사람이
       거울 시험을 함께 옮겨야 하고, 잊으면 **더 낡은 파일과 비교되며 초록**이 되어
       가드가 있는 척만 한다(형제 test_schema_function_drift.py:86-95 와 같은 방식:
       파일명 정렬이 곧 적용 순서라 뒤가 이긴다).
    """
    found = None
    for name in sorted(os.listdir(MIG_DIR)):
        if not name.endswith(".sql"):
            continue
        if RE_DEFINES_FN.search(code_only(read(os.path.join(MIG_DIR, name)))):
            found = os.path.join(MIG_DIR, name)
    assert found, "{} 를 정의하는 마이그레이션이 하나도 없습니다".format(FN)
    return found


LATEST_FN_MIGRATION = latest_migration_defining_the_function()


def cte_block(sql, name):
    """`with … <name> as ( … )` 한 덩어리를 괄호 짝을 세어 뜯어 온다.

    ⛔ 반드시 `statements()` 로 주석을 걷은 텍스트를 넘길 것 — 설명 주석에 든 괄호나
       낱말이 판정에 섞이면, 주석 한 줄 때문에 가드가 헛것을 잡거나 놓친다.
    """
    m = re.search(r"(?im)^ *%s as \(" % re.escape(name), sql)
    assert m, "{} CTE 를 못 찾았습니다".format(name)
    start = sql.index("(", m.start())
    depth = 0
    for j in range(start, len(sql)):
        if sql[j] == "(":
            depth += 1
        elif sql[j] == ")":
            depth -= 1
            if depth == 0:
                return sql[start:j + 1]
    raise AssertionError("{} CTE 의 괄호가 안 닫힙니다".format(name))


def squeeze(text):
    """공백을 한 칸으로 접는다 (이미 주석을 걷어 낸 텍스트에 쓴다)."""
    return re.sub(r"\s+", " ", text)


# ── 0. 기존 표와 사슬 넷은 **한 글자도 안 건드린다** (이 파일의 본론) ────────


class TestTheCanonBlocksAreUntouched:
    """⛔ 이 PR 의 방향 전환 자체를 지키는 가드다.

    1차 초안은 mv_search_parcel 에 칸을 더하려고 그 표와 사슬 넷을 떨어뜨렸다 되세웠다.
    그 판을 버리고 **형제 표**로 바꾼 것이 이 PR 이므로, 다섯 문장이 정본에서 그대로여야
    한다. 하나라도 달라졌다면 누군가 옛 길로 돌아간 것이다.
    """

    @pytest.mark.parametrize("name", sorted(CANON_STATEMENT_SHA))
    def test_the_statement_is_byte_for_byte_the_same(self, name):
        got = sql_block(read(SCHEMA), CANON_HEADER[name])
        assert sha(got) == CANON_STATEMENT_SHA[name], (
            "{} 의 정의가 바뀌었습니다 — 이 PR 은 그 표를 안 건드리기로 했습니다. "
            "정말 고쳐야 한다면 사슬 넷을 어떻게 다룰지부터 다시 정할 일이라 "
            "**별건 결정**입니다(해시 상수만 조용히 갱신하지 마세요).".format(name)
        )

    def test_the_migration_never_names_them_in_any_statement(self):
        """⛔ 마이그레이션의 **문장**에는 그 넷의 이름이 아예 없어야 한다.

        (설명 주석과 `comment on` 의 글에는 있다 — 왜 안 건드리는지를 적어 둔 자리라
         오히려 있어야 한다. 그래서 code_only() 로 그 둘을 걷고 본다.)
        """
        code = code_only(read(MIGRATION))
        for name in PROTECTED:
            assert re.search(r"\b%s\b" % name, code) is None, (
                "마이그레이션이 {} 를 건드리고 있습니다 — 1차 초안으로 되돌아갔습니다"
                .format(name)
            )

    def test_the_migration_drops_nothing_but_the_old_index(self):
        """⛔ 이 판에서 떨어뜨려도 되는 것은 옛 상호 색인 **하나뿐**이다."""
        code = code_only(read(MIGRATION))
        drops = re.findall(r"(?im)^drop\s+.*$", code)
        assert drops == ["drop index if exists {};".format(OLD_INDEX)], drops


# ── 1. 새 표는 **홀로 서는 형제**다 ──────────────────────────────────────────


class TestTheNewTableIsAFreeStandingSibling:
    @pytest.mark.parametrize("path", BOTH)
    def test_it_never_reads_the_old_summary_table(self, path):
        """⛔ mv_search_parcel 을 **참조하면** 이 표가 그 사슬에 하나 더 매달린다 —
        다음에 그 표를 손볼 사람이 여기까지 함께 떨어뜨려야 한다(방금 피한 그 일이다).
        포함 규칙만 같게 쓰고, 판단은 parcel·building 에서 직접 한다."""
        stmt = statements(sql_block(read(path), NEW_MV_HEADER))
        for name in PROTECTED:
            assert re.search(r"\b%s\b" % name, stmt) is None, name

    @pytest.mark.parametrize("path", BOTH)
    def test_the_columns_and_how_they_are_made(self, path):
        """⛔ 이름만 보면 안 된다 — store_names 를 distinct 로 접어도 이름은 그대로다."""
        stmt = flat(sql_block(read(path), NEW_MV_HEADER))
        for piece in NEW_MV_OUTPUT:
            assert piece in stmt, piece

    @pytest.mark.parametrize("path", BOTH)
    def test_store_names_keeps_one_item_per_store(self, path):
        """⛔ **distinct 로 접으면 안 된다.**

        접는 순간 "이 이름의 가게 N곳"을 이 표 한 줄에서 못 세고, 세러 점포 표를
        되짚어야 한다 — 그 2단계가 찬 캐시 3.2초였다(강남 시제품 실측). 그런데 접어도
        에러는 안 나고 숫자만 조용히 작아진다(같은 이름 가게가 한 곳으로 세어진다).
        """
        stmt = flat(sql_block(read(path), NEW_MV_HEADER))
        assert "array_agg(ub.biz_name order by ub.biz_name) as store_names" in stmt
        assert "array_agg(distinct ub.biz_name" not in stmt, (
            "store_names 를 distinct 로 접었습니다 — 가게 수가 조용히 줄어듭니다"
        )

    @pytest.mark.parametrize("path", BOTH)
    def test_the_key_column_uses_the_same_ruler_as_building_names(self, path):
        """⛔ 건물 이름과 **같은 자**(search_key)로 자른다 — 같은 검색어에 건물과 상호가
        다른 답을 내면 안 된다."""
        stmt = flat(sql_block(read(path), NEW_MV_HEADER))
        assert (
            "string_agg(distinct search_key(ub.biz_name), '|') as store_names_key"
            in stmt
        )

    @pytest.mark.parametrize("path", BOTH)
    def test_only_the_latest_snapshot(self, path):
        """⛔ 분기를 안 고르면 폐업한 옛 가게가 그대로 검색된다.

        ⓘ 스칼라 하위질의여야 idx_ub_pnu_cat (pnu, snapshot_ym) 이 이 조회를 받친다 —
          조인 조건으로 바꾸면 에러 없이 느려지기만 한다(가장 늦게 발견되는 회귀).
        """
        stmt = flat(sql_block(read(path), NEW_MV_HEADER))
        assert "select max(u.snapshot_ym) as ym from unit_business u" in stmt
        assert "and ub.snapshot_ym = (select l.ym from latest l)" in stmt
        assert "and ub.biz_name is not null" in stmt

    @pytest.mark.parametrize("path", BOTH)
    def test_it_keeps_only_parcels_that_have_buildings(self, path):
        """⛔ 이 조건이 빠지면 표가 parcel 전체 사본(112만 행)이 되고, 상호로 찾아 들어간
        땅이 주소로는 안 나오는 모순도 난다(형제 표와 포함 규칙이 갈린다)."""
        stmt = flat(sql_block(read(path), NEW_MV_HEADER))
        assert "where exists (select 1 from building b where b.pnu = pc.pnu);" in stmt

    @pytest.mark.parametrize("path", BOTH)
    def test_the_empty_parcels_are_dropped_by_the_join(self, path):
        """가게가 하나도 없는 땅은 줄 자체가 없어야 한다 — 그래야 표가 작다."""
        stmt = flat(sql_block(read(path), NEW_MV_HEADER))
        assert ") s on s.store_cnt > 0" in stmt

    @pytest.mark.parametrize("path", BOTH)
    def test_every_index_exists(self, path):
        """유니크가 빠지면 `refresh … concurrently` 가 에러로 멈춰 `post_load.py` 가 통째로
        서고, trgm·구 색인이 빠지면 **에러 없이 검색만 느려진다**(가장 늦게 발견된다)."""
        text = statements(read(path))
        for name, unique in NEW_MV_INDEXES:
            pat = r"(?im)^create %sindex if not exists %s\s+on %s " % (
                "unique " if unique else "", name, NEW_MV)
            assert re.search(pat, text), "{} 가 없습니다".format(name)
        assert re.search(
            r"(?im)^create index if not exists idx_mpsn_names\s+on %s "
            r"using gin \(store_names_key gin_trgm_ops\);" % NEW_MV, text)


# ── 2. 나가는 것은 땅 한 줄 + 상호 3개뿐 ─────────────────────────────────────


class TestReturnedColumnsAreFixed:
    @pytest.mark.parametrize("path", BOTH)
    @pytest.mark.parametrize("schema", ["", "api."])
    def test_exactly_these_columns(self, path, schema):
        """⛔ **칸이 늘면 여기서 먼저 운다.**

        점포 원자료(biz_no·업종 코드·좌표)를 붙이는 것은 별건 판단이라, 조용히 늘어나는
        것을 막는다(returns table 안의 칸 이름을 순서까지 통째로 대조한다).
        """
        assert returns_columns(
            fn_block(statements(read(path)), schema=schema)) == RETURNED_COLUMNS

    @pytest.mark.parametrize("path", BOTH)
    def test_the_api_twin_never_restates_the_body(self, path):
        """⛔ api 쌍둥이가 본문에서 칸을 **다시 나열하기 시작하면** 위 자물쇠가 통하지
        않는 자리가 하나 더 생긴다(두 곳의 순서가 갈려도 에러가 안 난다 — PostgreSQL 은
        이름이 아니라 **자리**로 맞춘다). 통째로 넘기게 둔다."""
        body = flat(fn_block(read(path), schema="api."))
        body = body[body.index("$$"):]
        assert "select * from public.{}(q, lim, sigungu, p_offset)".format(FN) in body
        assert re.search(r"\bo\.", body) is None, "쌍둥이가 칸을 직접 나열하고 있습니다"

    @pytest.mark.parametrize("path", BOTH)
    def test_the_store_raw_columns_never_leave(self, path):
        """⛔ 상호 말고는 점포 표의 어떤 칸도 안 나간다.

        나가는 것은 `biz_name`(원문 상호)뿐이다 — 사업자번호·업종 코드·점포 좌표가
        붙는 순간 이 함수는 "가게 찾기"가 아니라 **점포 원자료 창구**가 된다.
        """
        body = statements(fn_block(read(path)))
        for banned in ("biz_no", "cat_l_cd", "cat_m_cd", "cat_s_cd", "ksic_cd",
                       "ub.lat", "ub.lng", "ub.geom"):
            assert banned not in body, banned

    @pytest.mark.parametrize("path", BOTH)
    def test_it_only_reads(self, path):
        """⛔ 이 길에 쓰기가 붙는 날, 읽기 전용이라는 전제가 사라진다."""
        body = statements(fn_block(read(path))).lower()
        for banned in ("insert", "update ", "delete", "truncate"):
            assert banned not in body, banned


# ── 3. 구를 안 고르면 0건 · 너무 넓으면 한 줄 ────────────────────────────────


class TestScopeRules:
    @pytest.mark.parametrize("path", BOTH)
    def test_no_sigungu_means_no_rows(self, path):
        """⛔ 상호는 같은 이름이 전국에 널려 있다 — 구 없이는 답이 될 수 없다(결정 0007).

        이 조건 한 줄이 빠지면 **전국 검색이 조용히 열린다**(에러 없이 느려지고, 결과도
        쓸모없어진다). 형제 search_buildings 는 `gu is null` 이면 전국을 보므로 그쪽
        문장을 그대로 베끼면 이 규칙이 사라진다 — 그 실수를 여기서 잡는다.
        """
        body = flat(fn_block(read(path)))
        assert "and pat.gu is not null" in body, (
            "구를 안 고른 검색이 열려 있습니다 — 결정 0007 위반"
        )
        assert "and m.sigungu_code = pat.gu" in body
        assert "pat.gu is null or" not in body, (
            "형제 search_buildings 의 '구를 안 고르면 전국' 조건을 베껴 왔습니다"
        )

    @pytest.mark.parametrize("path", BOTH)
    def test_the_gu_comparison_is_cast_to_char5(self, path):
        """⛔ `::char(5)` 를 지우면 색인이 죽는다 — 에러 없이 느려지기만 한다.

        sigungu_code 컬럼은 char(5) 인데 pat.gu 는 text 라, 캐스트가 없으면 **컬럼 쪽**이
        text 로 올려붙여져 색인이 Index Cond 가 아니라 Filter 로 떨어진다(형제 표 라이브
        실측 2026-09-10: 2글자 검색 859.9ms → 76.6ms, 훑는 행 188,442 → 12,138).
        형제 `list_parcel_buildings` 의 `p_pnu::char(19)` 가 같은 처방이다(2026-08-16b).
        """
        body = flat(fn_block(read(path)))
        assert "and m.sigungu_code = pat.gu::char(5)" in body, (
            "구 비교에 ::char(5) 캐스트가 없습니다 — 색인이 죽습니다(2026-08-16b 와 같은 병)"
        )

    @pytest.mark.parametrize("path", BOTH)
    def test_the_gate_uses_the_shared_limit(self, path):
        """⛔ 상한을 숫자로 박지 않는다 — 정본은 search_scope_limit() 한 곳뿐이다."""
        body = flat(fn_block(read(path)))
        assert "> search_scope_limit()" in body
        assert "6000" not in body, "상한을 숫자로 박았습니다"

    @pytest.mark.parametrize("path", BOTH)
    def test_too_broad_answers_with_one_row_not_zero(self, path):
        """⛔ 게이트에 걸렸을 때 0건을 돌려주면 화면이 "그런 가게가 없다"고 말하게 된다 —
        사실은 "너무 많다"이다. 총계를 실은 **한 줄**로 답한다."""
        body = flat(fn_block(read(path)))
        assert "true, gr.store_snapshot_ym::text," in body, (
            "too_broad 한 줄을 내는 가지가 없습니다"
        )
        assert "where g.broad" in body
        assert "where not g.broad" in body, "정상 결과가 게이트를 안 봅니다"

    @pytest.mark.parametrize("path", BOTH)
    def test_paging_is_clamped_and_tie_broken(self, path):
        """⛔ tie-break 가 없으면 '더 보기'가 이미 본 줄을 다시 가져오거나 건너뛴다."""
        body = flat(fn_block(read(path)))
        assert "limit greatest(1, least(coalesce(lim, 50), 200))" in body
        assert "offset greatest(0, coalesce(p_offset, 0))" in body
        assert "t.road_addr asc nulls last, t.pnu" in body

    @pytest.mark.parametrize("path", BOTH)
    def test_input_wildcards_are_escaped(self, path):
        """⛔ `% _ \\` 를 그대로 흘리면 검색어 한 글자가 표 전체를 부른다."""
        body = flat(fn_block(read(path)))
        assert "replace(replace(replace(search_key(q), '\\', '\\\\'), '%', '\\%'), '_', '\\_')" in body
        assert "like pat.p escape '\\'" in body


# ── 4. 새 함수·새 표는 닫힌 채로 태어난다 (2026-09-01b) ──────────────────────


class TestClosedByDefault:
    @pytest.mark.parametrize("path", BOTH)
    def test_it_is_security_definer_with_a_fixed_search_path(self, path):
        """점포 표가 anon 에게 닫혀 있어 소유자 권한으로 대신 읽는다 — 그 대신
        검색경로를 못 박아 다른 함수가 대신 불릴 수 없게 한다."""
        block = fn_block(read(path))
        assert "security definer" in block
        assert "set search_path = public" in block
        api = fn_block(read(path), schema="api.")
        assert "security definer" in api
        assert "set search_path = ''" in api

    @pytest.mark.parametrize("path", BOTH)
    def test_public_is_revoked_and_never_granted(self, path):
        """⛔ 통과 함수가 security definer 라 public 원본을 열 필요가 없다."""
        text = flat(read(path))
        assert (
            "revoke all on function %s(text, int, text, int) "
            "from public, anon, authenticated;" % FN in text
        )
        assert not re.search(
            r"grant execute on function (public\.)?%s\(text, int, text, int\)" % FN, text)

    @pytest.mark.parametrize("path", BOTH)
    def test_api_twin_is_granted_after_revoke(self, path):
        """⛔ 순서가 뒤집히면 대시보드가 붙인 anon 기본권한을 못 걷는다."""
        text = flat(read(path))
        rv = text.index("revoke all on function api.%s(text, int, text, int) "
                        "from public, anon, authenticated;" % FN)
        gr = text.index("grant execute on function api.%s(text, int, text, int) "
                        "to anon, authenticated;" % FN)
        assert rv < gr

    @pytest.mark.parametrize("path", BOTH)
    def test_the_new_table_is_never_opened_to_anon(self, path):
        """⛔ 이 표가 열리면 상호 묶음(store_names)이 통째로 긁혀 구 좁히기·상한이
        전부 우회된다 — 2026-08-13 사고(mv_search_parcel 200)와 같은 형태다."""
        text = flat(read(path))
        assert "grant select on {}".format(NEW_MV) not in text
        assert "grant all on {}".format(NEW_MV) not in text
        assert "revoke all on {} from public, anon, authenticated;".format(NEW_MV) in text

    def test_the_exposure_check_knows_it(self):
        """허용 목록에 없으면 `--check` 가 멀쩡한 함수를 **[사고]** 로 알린다."""
        assert "api.{}".format(FN) in post_load.ANON_CALLABLE_ALLOWLIST
        assert FN in post_load.ANON_CALLABLE_NAMES
        assert NEW_MV not in post_load.ANON_READABLE_ALLOWLIST
        assert NEW_MV not in post_load.ANON_CALLABLE_ALLOWLIST

    def test_the_migration_reloads_postgrest(self):
        """⛔ 빠뜨리면 DB 에는 있는데 화면만 404(PGRST202) 가 난다."""
        assert "notify pgrst, 'reload schema';" in statements(read(MIGRATION))


# ── 5. 전부 아니면 전무 (begin … commit) ─────────────────────────────────────


DDL_RE = r"(?m)^(alter |analyze |comment on |create |drop |grant |revoke )"


class TestTheMigrationIsAtomic:
    """표 하나 + 색인 셋 + 함수 둘을 만드는 판은 ``begin`` … ``commit`` 으로 감싼다.

    ``scripts/dbx.py -f`` 는 psql 자동커밋(``--single-transaction`` 없음)이라, 감싸지
    않으면 중간에 끊겼을 때 **색인 없는 표**(갱신이 concurrently 로 안 된다)나
    **표 없는 함수**(화면이 부르면 "그런 표 없음")가 남는다.
    """

    DDL = DDL_RE

    def test_begin_comes_before_the_first_create(self):
        sql = statements(read(MIGRATION)).lower()
        assert at(r"(?m)^begin;", sql) < at(r"(?m)^create ", sql)

    def test_commit_comes_after_every_ddl_but_the_last_drop_index(self):
        """⛔ 커밋 뒤에 남아도 되는 것은 **옛 색인 지우기 하나뿐**이다(아래 §6). 다른 DDL 이
        덩어리 밖으로 새면 그만큼 '전부 아니면 전무'가 깨진다."""
        sql = statements(read(MIGRATION)).lower()
        commit = at(r"(?m)^commit;", sql)
        outside = [m.start() for m in re.finditer(self.DDL, sql) if m.start() > commit]
        assert outside == [at(r"(?m)^drop index if exists %s;" % OLD_INDEX, sql)], (
            "커밋 뒤에 있으면 안 되는 DDL 이 있습니다: {}".format(
                [sql[p:p + 60] for p in outside])
        )

    def test_notify_comes_after_commit(self):
        """⛔ 안에 두면 롤백된 판에서도 PostgREST 에 헛알림이 간다(09-09b 선례)."""
        sql = statements(read(MIGRATION)).lower()
        assert at(r"(?m)^commit;", sql) < at(r"(?m)^notify pgrst", sql)

    def test_no_concurrent_index_build(self):
        """⛔ `create index concurrently` 만은 트랜잭션 안에서 못 돈다 — 넣으면 이
        마이그레이션이 통째로 실패한다."""
        assert "concurrently" not in statements(read(MIGRATION)).lower()


# ── 6. 옛 상호 색인은 **맨 끝**에서 지운다 ───────────────────────────────────


class TestTheOldIndexIsDroppedLast:
    def test_it_is_the_very_last_statement(self):
        """⛔ 덩어리 **안**에 두면 ACCESS EXCLUSIVE 락이 커밋까지 유지돼, 표를 굽는
        내내 점포 표를 읽는 다른 세션이 전부 줄을 선다(2026-08-22c 가 적어 둔 함정).
        커밋 뒤 제 트랜잭션에서 혼자 돌면 잠금이 순식간이다."""
        text = statements(read(MIGRATION)).rstrip()
        assert text.endswith("drop index if exists {};".format(OLD_INDEX)), (
            "옛 색인 지우기가 맨 끝이 아닙니다"
        )

    def test_the_canon_no_longer_creates_it(self):
        """⛔ 정본에 남아 있으면 **새 환경에만** 186MB 짜리 색인이 생겨 라이브와 갈린다
        (형제 가드 test_schema_migration_sync 도 같은 것을 본다)."""
        assert not re.search(
            r"(?im)^create\s+(?:unique\s+)?index\s+(?:if\s+not\s+exists\s+)?%s\b"
            % OLD_INDEX, read(SCHEMA)
        ), "지운 색인이 정본에 남아 있습니다"

    def test_nothing_uses_it_anymore(self):
        """지우는 근거 — 쓰는 코드가 0건이다. 함수 본문 어디에도 이름이 없다."""
        assert OLD_INDEX not in statements(read(SCHEMA))


# ── 7. 정본 동기 · post_load 가 알고 있는가 ──────────────────────────────────


class TestSchemaMirrorsTheMigration:
    @pytest.mark.parametrize("schema", ["", "api."])
    def test_function_bodies_letter_for_letter(self, schema):
        """⛔ 정본만 살짝 다듬는 것이 곧 정본↔라이브 불일치다(2026-09-01 2차 적대검증).

        ⓘ 전 함수를 훑는 형제 가드가 따로 있다(tests/test_schema_function_drift.py).
          여기서는 이 함수 하나를 못 박아 두어, 실패 메시지가 무엇 때문인지 바로 보이게 한다.

        ⚠️ **둘이 서로 다른 파일을 본다.** 라이브의 진실은 "그 함수를 마지막으로 다시 만든
           파일"이라, public 쪽은 그것을 **찾아서** 본다(2026-09-10b 가 본문을 고쳤다).
           api 쌍둥이는 그 뒤로 아무도 안 건드렸으므로 09-09c 가 여전히 최신이다 —
           형제 test_schema_function_drift 도 두 이름을 **따로** 셈한다(bodies() :69-74).
        """
        path = MIGRATION if schema else LATEST_FN_MIGRATION
        assert fn_block(read(path), schema=schema) == fn_block(
            read(SCHEMA), schema=schema)

    def test_the_new_table_body_letter_for_letter(self):
        """⛔ 새 표의 본문이 갈리면 **새 환경과 라이브가 다른 말을 하게 된다.**"""
        assert (sql_block(read(MIGRATION), NEW_MV_HEADER)
                == sql_block(read(SCHEMA), NEW_MV_HEADER))


class TestPostLoadKnowsIt:
    def test_refresh_list_names_the_new_table(self):
        """⛔ 갱신 목록에서 빠지면 새 가게를 넣어도 **조용히** 검색에서 빠진다.

        이 표는 형제라 아무것도 여기 의존하지 않는다 — 잊어도 어디서도 안 터진다는 뜻이라,
        이 목록이 유일한 방어선이다.
        """
        assert NEW_MV in post_load.REFRESH_MVS
        assert "refresh materialized view concurrently {};".format(NEW_MV) in (
            post_load.build_refresh_sql()
        )

    def test_the_old_summary_table_is_still_first(self):
        """⛔ 새 표를 끼워 넣다 기존 순서를 흔들면 안 된다 — mv_open_sigungu 는
        mv_search_parcel 에서 만들어지므로 반드시 그 뒤여야 한다."""
        sql = post_load.build_refresh_sql()
        assert post_load.SEARCH_MV == "mv_search_parcel"
        assert sql.index("mv_search_parcel") < sql.index("mv_open_sigungu")

    def test_allowlist(self):
        assert "api." + FN in post_load.ANON_CALLABLE_ALLOWLIST


# ── 8. 가드 자신의 시험 — 죽은 줄을 **진짜로** 잡는가 ────────────────────────
#
# ⓘ 아래 셋은 파일을 **안 건드린다** — 원문을 문자열로 읽어 한 군데를 망가뜨린 **사본**을
#   만들고 그 사본에 판정을 돌린다. 그래서 "복원"이 따로 필요 없다(디스크는 처음부터
#   그대로다). 시험이 중간에 죽어도 레포에 부서진 파일이 남지 않는다.


def test_statements_really_strips_comments():
    """⛔ **주석 제거기가 헛돌면 위 시험들이 조용히 가짜 초록이 된다** — 가드가 없는
    것보다 나쁘다(막고 있다는 거짓 안심)."""
    text = read(MIGRATION)
    line = ("grant execute on function api.%s(text, int, text, int) "
            "to anon, authenticated;" % FN)
    assert line in flat(text), "전제: 원문에는 그 문장이 살아 있다"
    assert line not in flat(text.replace(line, "-- " + line)), (
        "주석으로 죽인 grant 가 여전히 '있다'고 읽힙니다 — 주석 제거가 헛돕니다"
    )


def test_code_only_strips_comment_statements_but_nothing_else():
    """⛔ `comment on … is '…'` 만 걷어야 한다. 더 걷으면 §0 의 이름 검사가 **아무것도 안
    보는** 상태가 되고(가짜 초록), 덜 걷으면 코멘트에 적어 둔 설명 때문에 영영 빨간불이다."""
    code = code_only(read(MIGRATION))
    # 걷혔는가 — 코멘트 본문에만 있는 말이 사라졌다.
    assert "형제 mv_search_parcel 과 같은 포함 규칙" not in code
    # 너무 걷지는 않았는가 — 진짜 문장들은 그대로다.
    for kept in (
        "create materialized view if not exists {} as".format(NEW_MV),
        "create or replace function api.{}(".format(FN),
        "grant execute on function api.{}(text, int, text, int)".format(FN),
        "drop index if exists {};".format(OLD_INDEX),
        "commit;",
    ):
        assert kept in code, kept


def test_returns_columns_helper_survives_parenthesised_types():
    """⛔ **형제 파일의 구현은 여기서 첫 칸만 읽고 멈춘다** — `char(19)` 의 닫는 괄호를
    `returns table` 의 끝으로 착각하기 때문이다. 그러면 칸이 열일곱 개 늘어도 초록이다."""
    sample = (
        "create or replace function f(x text)\n"
        "returns table (\n"
        "  pnu   char(19),\n"
        "  n     int,\n"
        "  names text[]\n"
        ")\n"
    )
    assert returns_columns(sample) == ("pnu", "n", "names")


def test_mutation_a_a_missing_unique_index_is_noticed():
    """돌연변이 ① 유니크 색인을 주석으로 죽인다 → 색인 가드가 뒤집혀야 한다.

    안 뒤집히면 "색인 셋을 다 만든다"는 단언이 사실은 아무것도 안 보고 있는 것이다.
    """
    text = read(MIGRATION)
    line = ("create unique index if not exists idx_mpsn_pnu     "
            "on {} (pnu);".format(NEW_MV))
    assert line in text, "전제: 원문에 그 줄이 있다"
    pat = r"(?im)^create unique index if not exists idx_mpsn_pnu\s+on %s " % NEW_MV
    assert re.search(pat, statements(text))
    assert not re.search(pat, statements(text.replace(line, "-- " + line))), (
        "주석으로 죽인 색인이 여전히 '있다'고 읽힙니다"
    )


def test_mutation_b_referencing_the_old_summary_table_is_noticed():
    """돌연변이 ② 새 표가 mv_search_parcel 에서 읽게 바꾼다 → §0·§1 가드가 잡아야 한다.

    이게 이 PR 에서 가장 되돌아가기 쉬운 실수다(옛 표를 참조하면 코드가 짧아 보인다).
    """
    text = read(MIGRATION)
    assert "from parcel pc" in text, "전제: 원문은 parcel 에서 직접 읽는다"
    broken = text.replace("from parcel pc", "from mv_search_parcel pc")

    # ① 마이그레이션 문장에 옛 표 이름이 등장한다
    assert re.search(r"\bmv_search_parcel\b", code_only(broken)) is not None
    assert re.search(r"\bmv_search_parcel\b", code_only(text)) is None, (
        "원문에서 이미 걸리고 있습니다 — 가드가 헛것을 잡고 있다는 뜻입니다"
    )
    # ② 새 표의 정의 안에도 등장한다
    stmt = statements(sql_block(broken, NEW_MV_HEADER))
    assert re.search(r"\bmv_search_parcel\b", stmt) is not None


def test_mutation_c_moving_the_drop_inside_the_commit_is_noticed():
    """돌연변이 ③ 옛 색인 지우기를 커밋 **안**으로 옮긴다 → 순서 가드가 잡아야 한다.

    옮겨도 SQL 은 멀쩡히 돈다 — 다만 표를 굽는 내내 점포 표 읽기가 전부 줄을 선다.
    라이브에 붙여 넣기 전에는 아무도 모르는 종류의 회귀라 여기서 막는다.
    """
    drop = "drop index if exists {};".format(OLD_INDEX)
    text = read(MIGRATION)
    assert statements(text).rstrip().endswith(drop), "전제: 원문은 맨 끝에 있다"

    broken = norm(text).replace(drop + "\n", "").replace(
        "\ncommit;\n", "\n" + drop + "\ncommit;\n", 1)
    sql = statements(broken).lower()
    # 옮겨졌는가 — 커밋 **앞**에 와 있다.
    assert at(r"(?m)^drop index if exists %s;" % OLD_INDEX, sql) < at(
        r"(?m)^commit;", sql), "옮기기가 안 됐습니다"
    # 그리고 §6 의 판정이 뒤집힌다 — 이게 이 시험의 본론이다.
    assert not statements(broken).rstrip().endswith(drop), (
        "덩어리 안으로 옮겼는데도 '맨 끝에 있다'고 읽힙니다 — 순서 가드가 헛돕니다"
    )


def test_mutation_d_an_edit_at_the_end_of_a_canon_block_is_noticed():
    """돌연변이 ④ 정본 블록의 **맨 끝 줄**을 고친다 → §0 해시 가드가 뒤집혀야 한다.

    ⛔ 이 파일에서 가장 중요한 가드(§0)의 급소는 해시가 아니라 **sql_block 이 어디서
       끊나**다. 일찍 끊으면 앞부분만 해시에 들어가, 뒷줄을 아무리 고쳐도 초록이다
       (가드가 없는 것보다 나쁜 거짓 안심). 그래서 하필 맨 끝 줄을 건드려 본다.
    """
    canon = read(SCHEMA)
    tail = "where exists (select 1 from building b where b.pnu = pc.pnu);"
    assert canon.count(tail) == 2, (
        "전제: 이 꼬리를 쓰는 것은 mv_search_parcel 과 새 표, 딱 둘이다"
    )
    broken = canon.replace(tail, "where true;", 1)   # 첫 번째 = mv_search_parcel
    got = sql_block(broken, CANON_HEADER["mv_search_parcel"])
    assert sha(got) != CANON_STATEMENT_SHA["mv_search_parcel"], (
        "블록 **맨 끝** 줄을 고쳤는데 해시가 그대로입니다 — sql_block 이 일찍 끊고 있습니다"
    )


# ── 9. 이름 대조는 **자르기 뒤**에 있다 (2026-09-10b · 0028 §백로그 🟡-5) ─────
#
# 옮겨도 답은 한 글자도 안 바뀐다(이름 배열은 총계·게이트·정렬 어디에도 안 쓰인다).
# 그래서 되돌아가도 **에러가 안 난다** — 조용히 느려지기만 한다(가장 늦게 발견되는 회귀).
# 그 되돌아감을 여기서 막는다.

# rows_out 의 새 lateral 이 갖춰야 할 조각들 — 요약표를 **제 기본키로** 다시 읽는다.
NAMES_LATERAL_PIECES = (
    # rows_out 에는 여태 pat 이 없었다. 없으면 컴파일 자체가 안 된다(pat.p 를 못 찾는다).
    "cross join pat",
    "from mv_parcel_store_names m2,",
    "unnest(m2.store_names) as u2(nm)",
    # ⛔ 유일 색인 idx_mpsn_pnu 로 한 줄만 집는다 — 점포 표를 되짚는 것이 아니다.
    "where m2.pnu = pg.pnu",
    "limit 3",
    "as matched_names",
)


class TestNamesAfterLimitMigration:
    """정본과 새 파일 **양쪽**을 본다 — 한쪽만 되돌아가도 드리프트다."""

    BOTH_NEW = [NEW_MIGRATION, SCHEMA]

    @pytest.mark.parametrize("path", BOTH_NEW)
    def test_matched_no_longer_builds_the_names(self, path):
        """⛔ ②matched 에서 만들면 게이트 상한(6,000땅)까지 땅마다 돌고 나서 50줄만 낸다.

        강남 '학원'은 898땅이 걸린다 — 898번 만들어 50번 쓴다. 에러는 안 난다.
        """
        block = cte_block(statements(fn_block(read(path))), "matched")
        assert "matched_names" not in block, (
            "이름 만들기가 ②matched 로 되돌아갔습니다 — 자르기 **앞**입니다"
        )

    @pytest.mark.parametrize("path", BOTH_NEW)
    def test_rows_out_builds_them_after_the_limit(self, path):
        """⛔ 그러면 그 일을 page 가 이미 잘라 둔 줄에만 한다(기본 50 · 상한 200)."""
        block = squeeze(cte_block(statements(fn_block(read(path))), "rows_out"))
        for piece in NAMES_LATERAL_PIECES:
            assert piece in block, piece

    @pytest.mark.parametrize("path", BOTH_NEW)
    def test_the_returned_columns_did_not_move(self, path):
        """⛔ 이 판의 약속은 "같은 답을 더 적은 일로"다 — 칸이 늘거나 순서가 바뀌면 약속
        위반이다(PostgreSQL 은 이름이 아니라 **자리**로 맞춘다)."""
        assert returns_columns(
            fn_block(statements(read(path)))) == RETURNED_COLUMNS

    def test_the_new_file_mirrors_the_canon(self):
        """⛔ 정본만 살짝 다듬는 것이 곧 정본↔라이브 불일치다(2026-09-01 2차 적대검증)."""
        assert fn_block(read(NEW_MIGRATION)) == fn_block(read(SCHEMA))

    def test_it_revokes_and_never_grants(self):
        """⛔ 만든 자리에서 다시 닫는다(관습 2026-09-01d:89-90).

        `create or replace` 가 권한을 보존하긴 하지만, 대시보드가 같은 함수를 다시 만들면
        Supabase 기본 권한이 anon 을 자동으로 붙인다. public 원본에는 **grant 를 주지
        않는다** — 화면은 api 쌍둥이로만 들어오고, 그 쌍둥이는 이 파일이 안 건드린다.
        """
        text = flat(read(NEW_MIGRATION))
        assert (
            "revoke all on function %s(text, int, text, int) "
            "from public, anon, authenticated;" % FN in text
        ), "만든 자리에서 다시 닫지 않았습니다"
        assert not re.search(r"grant execute on function", text), (
            "새 파일이 실행 권한을 주고 있습니다 — 이 판은 권한을 한 글자도 안 바꿉니다"
        )
        assert "api.%s" % FN not in code_only(read(NEW_MIGRATION)), (
            "쌍둥이를 다시 정의하고 있습니다 — 그러면 위 거울 시험이 보는 파일이 갈립니다"
        )

    def test_it_is_atomic(self):
        """⛔ `dbx.py -f` 는 psql 자동커밋이다 — 감싸지 않으면 함수만 바뀌고 revoke 가
        빠진 채 남을 수 있다(그 순간 public 원본이 열린 채로 선다)."""
        sql = statements(read(NEW_MIGRATION)).lower()
        assert at(r"(?m)^begin;", sql) < at(r"(?m)^create ", sql)
        commit = at(r"(?m)^commit;", sql)
        outside = [m.start() for m in re.finditer(DDL_RE, sql)
                   if m.start() > commit]
        assert outside == [], (
            "커밋 뒤로 샌 DDL 이 있습니다: {}".format([sql[p:p + 60] for p in outside])
        )
        assert commit < at(r"(?m)^notify pgrst", sql), (
            "안에 두면 롤백된 판에서도 PostgREST 에 헛알림이 간다(09-09b 선례)"
        )
        assert "concurrently" not in sql, (
            "`create index concurrently` 만은 트랜잭션 안에서 못 돈다"
        )
        assert re.search(r"(?m)^drop\s", sql) is None, (
            "이 판은 아무것도 떨어뜨리지 않는다 — create or replace 하나뿐이다"
        )

    def test_post_load_needs_no_new_entry(self):
        """ⓘ 갱신할 표도, 새 공개 호출도 안 늘었다 — `--check` 허용 총계 25 불변."""
        assert NEW_MV in post_load.REFRESH_MVS
        assert "api.%s" % FN in post_load.ANON_CALLABLE_ALLOWLIST


# ⓘ 아래 둘은 §8 과 같은 방식이다 — 파일을 안 건드리고, 원문을 문자열로 읽어 한 군데를
#   망가뜨린 **사본**에 판정을 돌린다.


def test_the_mirror_helper_really_finds_the_newest_file():
    """⛔ helper 가 옛 파일을 집으면 거울 시험이 **더 낡은 판과 비교되며 초록**이 된다 —
    가드가 있는 척만 하는 상태다(이 파일이 가장 무서워하는 가짜 초록)."""
    assert LATEST_FN_MIGRATION == NEW_MIGRATION, (
        "public {} 를 정의하는 최신 파일이 {} 로 잡혔습니다 — 기대는 {} 입니다".format(
            FN, os.path.basename(LATEST_FN_MIGRATION),
            os.path.basename(NEW_MIGRATION))
    )
    assert LATEST_FN_MIGRATION != MIGRATION, "09-09c 로 되돌아갔습니다"


def test_mutation_e_building_the_names_in_matched_again_is_noticed():
    """돌연변이 ⑤ 이름 만들기를 ②matched 로 되돌린다 → §9 가드가 뒤집혀야 한다.

    되돌려도 **답은 같고 에러도 안 난다** — 조용히 느려질 뿐이라, 글자를 보는 이 가드가
    유일한 방어선이다. 그러니 그 가드가 진짜로 보고 있는지를 여기서 확인한다.
    ⓘ 주석에 `matched_names` 라고 적어 둔 것에는 안 걸려야 한다(statements() 가 걷는다) —
      실제로 정본 ②matched 에는 "여기서 안 만든다"는 설명 주석이 그 낱말과 함께 있다.
    """
    canon = norm(read(SCHEMA))
    marker = "           agg.exact_hit\n"
    assert canon.count(marker) == 1, "전제: ②matched 의 마지막 칸이 그 한 줄이다"

    assert "matched_names" not in cte_block(
        statements(fn_block(canon)), "matched"), (
        "원문에서 이미 걸리고 있습니다 — 가드가 헛것(설명 주석)을 잡고 있다는 뜻입니다"
    )
    broken = canon.replace(
        marker,
        "           agg.exact_hit,\n"
        "           (select array_agg(u3.nm) from unnest(h.store_names) as u3(nm))"
        " as matched_names\n",
        1,
    )
    assert "matched_names" in cte_block(statements(fn_block(broken)), "matched"), (
        "②matched 로 되돌렸는데도 '없다'고 읽힙니다 — §9 가드가 헛돕니다"
    )
