# -*- coding: utf-8 -*-
"""신선도 표(get_data_freshness)가 큰 표를 색인 없이 훑지 않는가.

왜 이 시험이 있나 (2026-09-27 라이브 실측)
------------------------------------------
화면 아래 "이 자료는 언제 것인가" 표는 함수 하나가 자료 열 갈래의 최댓값을 구해 준다.
그중 `max(t.updated_at) from parcel t` 한 줄만 **2.2~3.1초**였다(나머지는 10~75ms).
parcel 111만 행에 updated_at 을 받치는 색인이 없어 전수를 훑었고, anon 의 제한이 3초라
표가 통째로 사라질 수 있는 자리였다. 마이그레이션 2026-09-27b 가 색인을 걸었다.

같은 일이 다시 나는 길은 둘이다 — ① 누가 새 자료 줄을 더하면서 큰 표의 색인 없는 칸을
max() 한다 ② 누가 받치던 색인을 지운다. 둘 다 에러가 안 나고 화면만 느려지다 사라진다.

무엇을 지키나
-------------
ⓐ 정본의 public get_data_freshness 본문에서 `max(t.<칸>)`·`min(t.<칸>) … from <표> t` 쌍을
   **전부** 뽑는다(0개거나, 본문의 `max(`·`min(` 개수와 안 맞으면 빨강 — 뽑기가 헛돌면 아무것도
   안 보면서 초록이 된다). count(*)·sum·avg 는 색인으로 못 줄이므로 대상이 아니다(RE_AGG 주석)
ⓑ 쌍마다 그 표에 **첫 칸이 그 칸인** btree 색인이 정본에 있거나, 명시 예외(실측 사유)에 있어야 한다
   (부분 색인은 조건이 정확히 `칸 is not null` 일 때만 친다 — has_leading_index 주석)
ⓒ 예외 목록에 정본에 없는 쌍이 남으면 빨강(낡은 예외가 다음 사람을 속인다)
ⓓ 마이그레이션 2026-09-27b 는 SET statement_timeout 한 줄(첫 색인 앞) + 색인 셋(parcel·building·
   transaction) 전부 concurrently · if not exists 이고 begin/commit 이 없다
ⓔ 돌연변이 — 위 판정기가 실제로 빨강을 내는지 사본 문자열로 확인한다

⛔ 주석 안의 `create index …` 는 색인으로 치지 않는다(설명에 인용한 글이 색인 대신 초록을 낸다).
ⓘ 도우미는 다른 시험 파일에서 import 하지 않는다 — 시험끼리 얽히면 한쪽 고장이 다른 쪽을 가린다.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")
MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-09-27b_parcel_updated_at_index.sql")

# 색인 없이 두어도 되는 쌍 — **실측 사유와 함께만** 적는다.
# 새 자료 줄을 더했는데 큰 표라면 여기에 적지 말고 색인을 건다.
EXCEPTIONS = {
    ("district", "computed_at"): "수천 행 이하(1,687개), 11.7ms 실측 2026-09-27",
    ("lh_notice", "collected_at"): "수천 행 이하, 11.2ms 실측 2026-09-27",
    ("price_gate_sigungu", "loaded_at"): "수천 행 이하(구 단위), 10.9ms 실측 2026-09-27",
}

RE_FN = re.compile(
    r"(?ims)^create\s+or\s+replace\s+function\s+(?:public\.)?get_data_freshness\s*\(\s*\)"
    r".*?\$\$(.*?)\$\$\s*;"
)
# max 뿐 아니라 min 도 본다(2026-09-27 P11) — 둘 다 btree 한쪽 끝 한 행으로 끝나는 집계라
# 색인이 있으면 몇 ms, 없으면 전수다. ⓘ count(*)·sum·avg 는 대상이 아니다 — 색인이 있어도
# 행을 전부 세거나 더해야 해서(index-only scan 도 전수) 색인으로 못 줄인다. 그런 줄을 큰 표에
# 더하는 것은 이 가드가 아니라 설계에서 막을 일이다.
RE_AGG = r"(?:max|min)"
RE_PAIR = re.compile(
    r"(?is)\b" + RE_AGG + r"\(\s*t\.(\w+)\s*\)(.*?)\bfrom\s+(?:public\.)?(\w+)\s+t\b")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def norm(text):
    return text.replace("\r\n", "\n")


def strip_comment_lines(sql):
    """줄 전체가 `--` 주석인 줄을 걷어낸다(색인·문장 판정용)."""
    return "\n".join(
        line for line in norm(sql).splitlines() if not line.lstrip().startswith("--"))


def strip_all_comments(sql):
    """함수 본문용 — 줄 끝 주석까지 걷어낸다(본문의 문자열에는 `--` 가 없다)."""
    return "\n".join(re.sub(r"--.*$", "", line) for line in norm(sql).splitlines())


def freshness_body(schema):
    """public get_data_freshness 의 본문(주석 제거). 못 찾으면 None.

    ⛔ api.get_data_freshness 는 public 것을 부르기만 하므로 보지 않는다 —
       정규식이 `api.` 접두를 받지 않는 것이 그 뜻이다.
    """
    m = RE_FN.search(norm(schema))
    return strip_all_comments(m.group(1)) if m else None


def freshness_pairs(body):
    """본문의 (표, 칸) 쌍 목록 — 적힌 순서대로."""
    pairs = []
    for m in RE_PAIR.finditer(body):
        if re.search(r"(?i)\b" + RE_AGG + r"\(", m.group(2)):
            # 다음 max/min 까지 넘어가 버린 것 — 이 줄의 from 을 못 찾았다는 뜻이다.
            pairs.append(("?", m.group(1)))
            continue
        pairs.append((m.group(3).lower(), m.group(1).lower()))
    return pairs


def _only_not_null(pred, col):
    """부분 색인 조건이 정확히 `col is not null` 인가(바깥 괄호·따옴표·공백은 무시)."""
    p = re.sub(r"\s+", " ", pred.replace('"', "")).strip().lower()
    while p.startswith("(") and p.endswith(")"):
        p = p[1:-1].strip()
    return p == "{} is not null".format(col.lower())


def has_leading_index(schema, table, col):
    """정본(주석 줄 제외)에 첫 칸이 col 인 btree 색인이 table 에 있나.

    ⛔ 부분 색인(`… where <조건>`)은 표 전체의 max/min 을 받치지 못하므로 치지 않는다
       (2026-09-27 P11). 단 하나 예외 — 조건이 정확히 `col is not null` 이면 인정한다:
       PostgreSQL 의 min/max 최적화(planagg.c build_minmax_path)는 `col IS NOT NULL` 조건을
       스스로 붙여 `order by col limit 1` 로 바꾸므로 그 부분 색인이 증명돼 쓰인다
       (max/min 은 null 을 어차피 안 센다). 그 밖의 조건은 전부 인정하지 않는다.
    """
    pat = (
        r"(?im)^create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?"
        r"(?:if\s+not\s+exists\s+)?\w+\s+on\s+(?:only\s+)?(?:public\.)?"
        + re.escape(table)
        + r"\s+(?:using\s+btree\s*)?\(\s*"
        + re.escape(col)
        + r"\s*[,)]"
    )
    code = strip_comment_lines(schema)
    for m in re.finditer(pat, code):
        end = code.find(";", m.end())
        rest = code[m.end():] if end < 0 else code[m.end():end]
        w = re.search(r"(?is)\bwhere\b(.*)$", rest)
        if w is None or _only_not_null(w.group(1), col):
            return True
    return False


def has_leading_primary_key(schema, table, col):
    """정본(주석 줄 제외)의 `create table … <table> (` 안에 **표 제약** `primary key (<col>, …)` 가
    있어 그 첫 칸이 col 인가 — 좁은 예외(2026-10-05b · 결정 0033).

    기본키도 btree 색인이다(PostgreSQL 은 기본키마다 고유 btree 색인을 만든다). 첫 칸이 col 이면
    max(col)/min(col) 을 그 색인 한쪽 끝 한 행으로 끝낸다 — 같은 색인을 `create index` 로 또
    만들면 쓰기만 두 배가 된다(district_openclose 168만 행).

    잡는 꼴: 줄머리의 `primary key (<col>, …)` · `constraint <이름> primary key (<col>, …)`(대소문자·공백 무관).
    못 보는 것(전부 빨강 쪽 — 안전하게 틀린다): 칸 정의 끝의 `<col> … primary key`(한 칸 기본키) ·
    `alter table … add primary key` — 그런 꼴로 받치면 이 가드가 빨강을 내니 그때 넓힌다.
    """
    code = strip_comment_lines(schema)
    m = re.search(
        r"(?ims)^create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?" + re.escape(table)
        + r"\s*\((.*?)^\);", code)
    if not m:
        return False
    return re.search(
        r"(?im)^\s*(?:constraint\s+\w+\s+)?primary\s+key\s*\(\s*" + re.escape(col) + r"\s*[,)]",
        m.group(1)) is not None


def problems(schema, exceptions=None):
    """어긴 것을 사람이 읽을 문장 목록으로 돌려준다(빈 목록 = 통과)."""
    exceptions = EXCEPTIONS if exceptions is None else exceptions
    body = freshness_body(schema)
    if body is None:
        return ["정본에서 public get_data_freshness 본문을 못 찾았습니다 — 판정기가 헛돕니다"]

    pairs = freshness_pairs(body)
    bad = []
    if not pairs:
        bad.append("본문에서 max/min(t.칸) … from 표 t 쌍을 하나도 못 뽑았습니다 — 판정기가 헛돕니다")
        return bad
    n_max = len(re.findall(r"(?i)\b" + RE_AGG + r"\(", body))
    if n_max != len(pairs):
        bad.append("본문의 max(/min( 는 {}개인데 뽑은 쌍은 {}개입니다 — 뽑기가 한 줄을 놓칩니다".format(
            n_max, len(pairs)))

    for table, col in pairs:
        if table == "?":
            bad.append("max/min(t.{}) 의 from 표를 못 찾았습니다 — `from <표> t` 모양인지 보세요".format(col))
            continue
        if (has_leading_index(schema, table, col) or has_leading_primary_key(schema, table, col)
                or (table, col) in exceptions):
            continue
        bad.append(
            "{}.{}: 새 자료 줄이 큰 표를 색인 없이 훑는다 — 색인을 걸거나 "
            "예외에 실측 사유와 함께 적어라".format(table, col))

    live = set(pairs)
    for key in sorted(exceptions):
        if key not in live:
            bad.append("예외 {}.{} 는 정본 get_data_freshness 에 더는 없습니다 — 낡은 예외를 지우세요".format(
                *key))
        # 예외는 "색인이 없어도 된다"는 사유다 — 이미 색인·기본키가 받치면 그 사유가 쓸모없다
        # (2026-10-06 · rent_stat.quarter 가 기본키 첫 칸인데 예외로 남아 있었다).
        if has_leading_index(schema, *key) or has_leading_primary_key(schema, *key):
            bad.append("예외 {}.{} 는 이미 색인·기본키가 받칩니다 — 낡은 예외를 지우세요".format(*key))
    return bad


# 마이그레이션 2026-09-27b 가 거는 색인 셋 — (이름, 표, 칸).
MIGRATION_INDEXES = [
    ("idx_parcel_updated_at", "parcel", "updated_at"),
    ("idx_building_updated_at", "building", "updated_at"),
    ("idx_tx_contract_ym", "transaction", "contract_ym"),
]
RE_SET_TIMEOUT = re.compile(r"(?m)^set\s+statement_timeout\s*=\s*'\d+s'\s*;")


def migration_problems(sql):
    """마이그레이션 2026-09-27b 규칙(ⓓ) 위반 목록.

    SET 한 줄(dbx 연결 제한 2분에 concurrently 가 끊기면 invalid 색인이 남는다)이
    첫 create index 보다 앞에 있고, 색인 셋이 전부 concurrently · if not exists 이며,
    begin/commit 이 없어야 한다.
    """
    code = strip_comment_lines(sql).lower()
    bad = []
    m_set = RE_SET_TIMEOUT.search(code)
    m_first = re.search(r"(?m)^create\s+index\b", code)
    if not m_set:
        bad.append("`set statement_timeout = '…s';` 가 없습니다 — dbx 연결 제한 2분에 끊기면 invalid 색인이 남습니다")
    elif m_first and m_set.start() > m_first.start():
        bad.append("`set statement_timeout` 이 첫 create index 보다 뒤에 있습니다")
    for name, table, col in MIGRATION_INDEXES:
        pat = (
            r"(?m)^create\s+index\s+concurrently\s+if\s+not\s+exists\s+" + name + r"\s+"
            r"on\s+(?:public\.)?" + table + r"\s*\(\s*" + col + r"\s*\)\s*;")
        if not re.search(pat, code):
            bad.append("`create index concurrently if not exists {} on {} ({});` 가 없습니다".format(
                name, table, col))
    if re.search(r"(?m)^\s*(begin|commit)\s*;", code):
        bad.append("begin/commit 이 있습니다 — concurrently 는 트랜잭션 안에서 못 돕니다")
    return bad


# ── 1. 지금 나무는 깨끗한가 ──────────────────────────────────────────────────


def test_schema_freshness_pairs_are_indexed_or_excepted():
    assert problems(read(SCHEMA)) == []


def test_pairs_really_are_extracted():
    """ⓐ 가짜 초록 방지 — 열 갈래 중 max 를 쓰는 줄이 실제로 뽑혀 나오는가."""
    pairs = freshness_pairs(freshness_body(read(SCHEMA)))
    assert len(pairs) >= 10, pairs
    assert ("parcel", "updated_at") in pairs
    # ⓘ '점포·업종' 줄은 2026-10-07a(결정 0035)부터 max() 가 아니라 표지 한 줄
    #    (`select r.published_ym::text from snapshot_release r`)을 읽는다 — 훑을 표가 없다.
    assert ("unit_business", "snapshot_ym") not in pairs
    assert ("district_openclose", "quarter") in pairs


def test_every_exception_has_a_reason():
    for key, reason in EXCEPTIONS.items():
        assert isinstance(reason, str) and reason.strip(), key


def test_parcel_updated_at_is_indexed_in_schema():
    assert has_leading_index(read(SCHEMA), "parcel", "updated_at")


def test_migration_is_concurrent_and_unwrapped():
    assert migration_problems(read(MIGRATION)) == []


# ── 2. 돌연변이 — 판정기가 실제로 빨강을 내는가 ─────────────────────────────

PARCEL_IDX = "create index if not exists idx_parcel_updated_at on parcel (updated_at);"
PARCEL_MAX_LINE = "from parcel t),"


def _schema():
    s = norm(read(SCHEMA))
    assert PARCEL_IDX in s, "전제: 정본에 parcel 색인 줄이 있다"
    assert PARCEL_MAX_LINE in s, "전제: 정본 본문에 parcel 줄이 있다"
    return s


def _add_pair(schema, snippet):
    """본문의 parcel 줄 뒤에 새 자료 줄 하나를 끼운다."""
    broken = schema.replace(
        PARCEL_MAX_LINE,
        PARCEL_MAX_LINE + "\n           'none', 'x'\n    union all\n    select 11, 'x', 'x',\n"
        "           (" + snippet + "),",
        1)
    assert snippet in broken, "끼워 넣기가 안 됐습니다"
    return broken


def test_mutation_removing_parcel_index_is_noticed():
    broken = _schema().replace(PARCEL_IDX + "\n", "", 1)
    assert PARCEL_IDX not in broken, "지우기가 안 됐습니다"
    bad = problems(broken)
    assert any("parcel.updated_at" in m for m in bad), bad


def test_mutation_commented_index_does_not_count():
    broken = _schema().replace(PARCEL_IDX, "-- " + PARCEL_IDX, 1)
    bad = problems(broken)
    assert any("parcel.updated_at" in m for m in bad), bad


def test_mutation_new_unindexed_column_on_parcel_is_noticed():
    broken = _add_pair(_schema(), "select max(t.foo)::text from parcel t")
    bad = problems(broken)
    assert any("parcel.foo" in m for m in bad), bad


def test_mutation_new_pair_not_in_exceptions_is_noticed():
    broken = _add_pair(_schema(), "select max(t.updated_at)::text from unit_business t")
    bad = problems(broken)
    assert any("unit_business.updated_at" in m for m in bad), bad


def test_mutation_stale_exception_is_noticed():
    stale = dict(EXCEPTIONS)
    stale[("gone_table", "gone_col")] = "옛 사유"
    bad = problems(_schema(), stale)
    assert any("gone_table.gone_col" in m for m in bad), bad


def test_mutation_missing_function_is_noticed():
    broken = _schema().replace(
        "create or replace function get_data_freshness()",
        "create or replace function get_data_freshness_x()", 1)
    assert problems(broken), "함수를 못 찾았는데 통과합니다"


def test_mutation_non_btree_index_does_not_count():
    broken = _schema().replace(
        PARCEL_IDX,
        "create index if not exists idx_parcel_updated_at on parcel using brin (updated_at);", 1)
    bad = problems(broken)
    assert any("parcel.updated_at" in m for m in bad), bad


def _mig_stmt(name, table, col):
    return "create index concurrently if not exists {} on {} ({});".format(name, table, col)


def test_mutation_migration_wrapped_in_transaction_is_noticed():
    sql = norm(read(MIGRATION))
    stmt = _mig_stmt(*MIGRATION_INDEXES[0])
    assert stmt in sql, "전제: 마이그레이션에 그 문장이 있다"
    broken = sql.replace(stmt, "begin;\n" + stmt + "\ncommit;", 1)
    assert any("begin/commit" in m for m in migration_problems(broken))


@pytest.mark.parametrize("name,table,col", MIGRATION_INDEXES)
def test_mutation_migration_without_concurrently_is_noticed(name, table, col):
    """세 문장 각각에서 concurrently 를 빼면 그 이름으로 빨강이 난다."""
    sql = norm(read(MIGRATION))
    stmt = _mig_stmt(name, table, col)
    assert stmt in sql, "전제: 마이그레이션에 그 문장이 있다"
    broken = sql.replace(stmt, stmt.replace(" concurrently", "", 1), 1)
    assert broken != sql, "바꾸기가 안 됐습니다"
    bad = migration_problems(broken)
    assert any(name in m for m in bad), bad


def test_mutation_migration_without_statement_timeout_is_noticed():
    sql = norm(read(MIGRATION))
    broken = RE_SET_TIMEOUT.sub("", sql.lower(), count=1)
    assert not RE_SET_TIMEOUT.search(strip_comment_lines(broken)), "지우기가 안 됐습니다"
    bad = migration_problems(broken)
    assert any("statement_timeout" in m for m in bad), bad


@pytest.mark.parametrize("table,col,line", [
    ("building", "updated_at",
     "create index if not exists idx_building_updated_at on building (updated_at);"),
    ("transaction", "contract_ym",
     "create index if not exists idx_tx_contract_ym on transaction (contract_ym);"),
])
def test_mutation_removing_new_schema_index_is_noticed(table, col, line):
    s = _schema()
    assert line in s, "전제: 정본에 그 색인 줄이 있다"
    broken = s.replace(line + "\n", "", 1)
    assert line not in broken, "지우기가 안 됐습니다"
    bad = problems(broken)
    assert any("{}.{}".format(table, col) in m for m in bad), bad


# ── 3. 2026-09-27 P11 — 부분 색인·min() 구멍 ─────────────────────────────────

PARCEL_IDX_HEAD = "create index if not exists idx_parcel_updated_at on parcel (updated_at)"


@pytest.mark.parametrize("where", [
    "where pnu like '11%'",
    "where updated_at > '2026-01-01'",
    "where updated_at is not null and pnu like '11%'",
    "where updated_at is null",
    "where pnu is not null",
])
def test_mutation_partial_index_does_not_count(where):
    """부분 색인은 표 전체의 max 를 못 받친다 → parcel.updated_at 빨간불."""
    broken = _schema().replace(PARCEL_IDX, PARCEL_IDX_HEAD + "\n  " + where + ";", 1)
    assert where in broken, "바꾸기가 안 됐습니다"
    bad = problems(broken)
    assert any("parcel.updated_at" in m for m in bad), bad


@pytest.mark.parametrize("where", [
    "where updated_at is not null",
    "where (updated_at is not null)",
    'WHERE "updated_at"  IS NOT NULL',
])
def test_partial_index_on_not_null_only_still_counts(where):
    """조건이 `칸 is not null` 뿐이면 planagg 가 같은 조건을 붙이므로 받친다 → 초록."""
    ok = _schema().replace(PARCEL_IDX, PARCEL_IDX_HEAD + " " + where + ";", 1)
    assert where in ok, "바꾸기가 안 됐습니다"
    assert problems(ok) == []


def test_mutation_min_on_unindexed_column_is_noticed():
    broken = _add_pair(_schema(), "select min(t.foo)::text from parcel t")
    bad = problems(broken)
    assert any("parcel.foo" in m for m in bad), bad


def test_mutation_min_on_indexed_column_is_fine():
    ok = _add_pair(_schema(), "select min(t.updated_at)::text from parcel t")
    assert ("parcel", "updated_at") in freshness_pairs(freshness_body(ok))
    assert problems(ok) == []


def test_count_is_not_a_target():
    """count(*) 는 색인으로 못 줄이므로 쌍으로 뽑지 않는다(개수 대조도 안 흔들린다)."""
    ok = _add_pair(_schema(), "select count(*)::text from parcel t")
    assert problems(ok) == []


# ── 4. 2026-10-05b — 첫 칸이 quarter 인 기본키도 받친다(좁은 예외 · 결정 0033) ─────────

OC_PK = "  primary key (quarter, district_id, svc_induty_cd)"


def test_openclose_quarter_is_backed_by_its_primary_key():
    s = _schema()
    assert ("district_openclose", "quarter") in freshness_pairs(freshness_body(s))
    assert not has_leading_index(s, "district_openclose", "quarter"), \
        "전제: 같은 색인을 create index 로 또 만들지 않았다"
    assert has_leading_primary_key(s, "district_openclose", "quarter")
    assert ("district_openclose", "quarter") not in EXCEPTIONS


@pytest.mark.parametrize("pk", [
    "  PRIMARY KEY ( quarter , district_id, svc_induty_cd)",
    "  constraint district_openclose_pkey primary key (quarter, district_id, svc_induty_cd)",
])
def test_primary_key_variants_still_count(pk):
    """양성 대조 — 흔한 꼴 + 변형 꼴(대문자·공백·이름 붙인 제약)."""
    s = _schema()
    assert OC_PK in s, "전제: 정본에 그 기본키 줄이 있다"
    ok = s.replace(OC_PK, pk, 1)
    assert has_leading_primary_key(ok, "district_openclose", "quarter")
    assert problems(ok) == []


@pytest.mark.parametrize("pk", [
    "  primary key (district_id, quarter, svc_induty_cd)",      # quarter 가 첫 칸이 아니다
    "  -- primary key (quarter, district_id, svc_induty_cd)",   # 주석은 기본키가 아니다
    "  unique (quarter, district_id, svc_induty_cd)",           # 기본키가 아니다(좁은 예외)
])
def test_mutation_primary_key_not_leading_is_noticed(pk):
    s = _schema()
    broken = s.replace(OC_PK, pk, 1)
    assert broken != s
    bad = problems(broken)
    assert any("district_openclose.quarter" in m for m in bad), bad


def test_primary_key_of_another_table_does_not_count():
    """rent_stat 의 기본키(첫 칸 quarter)가 district_openclose 를 받친다고 보지 않는다."""
    s = _schema()
    broken = s.replace(OC_PK, "  primary key (district_id, quarter, svc_induty_cd)", 1)
    assert not has_leading_primary_key(broken, "district_openclose", "quarter")
    assert has_leading_primary_key(broken, "rent_stat", "quarter")


# ── 5. 2026-10-06 — 이미 받쳐진 쌍을 예외에 두면 낡은 예외 ──────────────────────────


@pytest.mark.parametrize("key", [
    ("rent_stat", "quarter"),     # 흔한 꼴 — 기본키 첫 칸이 받친다
    ("parcel", "updated_at"),     # 변형 꼴 — create index 가 받친다
])
def test_mutation_exception_already_backed_is_noticed(key):
    """양성 대조 — 받쳐진 쌍을 예외 표에 넣으면 '낡은 예외' 빨강."""
    s = _schema()
    assert key in freshness_pairs(freshness_body(s)), "전제: 본문에 그 쌍이 있다"
    stale = dict(EXCEPTIONS)
    stale[key] = "옛 사유"
    bad = problems(s, stale)
    assert any("예외 {}.{} 는 이미 색인·기본키가 받칩니다".format(*key) in m for m in bad), bad


def test_remaining_exceptions_are_not_backed():
    """남은 예외는 정말 색인·기본키가 없는 쌍이다(새 검사가 오탐하지 않는다)."""
    s = _schema()
    assert ("rent_stat", "quarter") not in EXCEPTIONS
    assert len(EXCEPTIONS) == 3
    for key in EXCEPTIONS:
        assert not has_leading_index(s, *key), key
        assert not has_leading_primary_key(s, *key), key
    assert not [m for m in problems(s) if "이미 색인·기본키가 받칩니다" in m]
