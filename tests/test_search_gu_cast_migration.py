# -*- coding: utf-8 -*-
"""마이그레이션 2026-09-10a(구 비교를 색인이 타게)의 불변식을 지킨다.

무엇을 막나
-----------
`mv_search_parcel.sigungu_code` 는 `char(5)` 인데 `pat.gu` 는 `text` 다. 그냥 견주면
PostgreSQL 이 **컬럼 쪽**을 text 로 올려 맞춰 `idx_msp_sigungu` 를 못 탄다 — 구를 골라도
표를 통째로 훑는다(라이브 실측 2026-09-10: Parallel Seq Scan 188,442행·116ms →
Index Scan 12,138행·8ms). 그래서 네 자리에 `::char(5)` 를 붙였다.

⛔ 이 결함은 **에러가 안 난다.** 답은 옛날과 글자 그대로 같고 느리기만 하다 — 사람 눈으로는
   영영 안 잡히는 종류라, 캐스트가 지워져도 아무도 모른다. 그것이 이 파일의 존재 이유다.
   (같은 병을 형제 `search_stores` 가 2026-09-09c 에서 먼저 앓았고, 그 처방을 옮겨 온 것이다.)

여기서 보는 것 (DB 없이 SQL 글자만 — CI 에는 DB 가 없다)
  1) 두 함수 본문에 `pc.sigungu_code = pat.gu::char(5)` 가 **정확히 두 번씩**,
     캐스트 없는 `= pat.gu)` 는 **0번**.
  2) `pat.gu is null or` 절반이 **함수마다 두 번 그대로** — 이 둘은 구를 안 고른 전국
     검색을 일부러 허용한다(구 없이는 답이 안 되는 `search_stores` 와 다른 점이다).
     캐스트를 붙이며 여기를 함께 손대면 **전국 검색이 조용히 막힌다.**
  3) 마이그레이션의 함수 블록이 정본(schema.sql)과 **글자 그대로** 같다 — 함수 본문
     주석은 `pg_proc.prosrc` 에 실려 라이브의 일부가 되므로, 한쪽만 다듬는 것이 곧
     정본↔라이브 드리프트다(2026-09-01 2차 적대검증).
  4) 원자성 — `begin;` 이 첫 DDL 앞, `commit;` 이 마지막 DDL 뒤, `notify pgrst` 는
     commit **뒤**, `concurrently` 는 없다(트랜잭션 안에서 못 돈다).
  5) 다시 만든 자리에서 다시 닫는다(revoke ×2) · public 을 여는 `grant` 는 0개.
  6) 가드 자신의 시험 — 캐스트 하나를 지운 **사본**에 판정을 돌려 빨간불이 나는지 본다.

ⓘ 도우미(read·norm·statements·fn_block)는 형제 test_search_stores_migration.py 에서
  **복사**해 왔다 — import 하지 않는다. 시험 파일끼리 얽히면 한쪽의 고장이 다른 쪽을
  조용히 가린다.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-09-10a_search_gu_index_cond.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

BOTH = [MIGRATION, SCHEMA]
LABEL = {MIGRATION: "마이그레이션 2026-09-10a", SCHEMA: "정본 schema.sql"}

# (함수 이름, revoke 에 적히는 인자 타입) — 철자가 갈리면 권한 가드가 헛돈다.
FUNCS = (
    ("search_scope", "text, text"),
    ("search_buildings", "text, int, text"),
)

CAST = "pc.sigungu_code = pat.gu::char(5)"
BARE = "= pat.gu)"           # 캐스트가 빠진 옛 모양
NATIONWIDE = "pat.gu is null or"

DOLLAR = chr(36) * 2


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def norm(text):
    """줄바꿈 표기(CRLF/LF)만 통일한다 — 공백·주석은 일부러 안 건드린다."""
    return text.replace("\r\n", "\n")


def statements(sql):
    """주석을 걷어낸 **실제 SQL 문장만**.

    설명 주석에 적어 둔 말이 문장으로 오해되면 코드가 망가져도 초록이 된다. 이 파일은
    특히 그렇다 — 위 ⛔ 주석에 `pat.gu is null or` 라는 말이 **글로** 적혀 있어서,
    주석을 안 걷으면 개수 세기가 통째로 헛돈다.
    """
    return "\n".join(
        line for line in norm(sql).splitlines() if not line.lstrip().startswith("--")
    )


def flat(sql):
    """주석을 걷고 **공백을 한 칸으로** 접은 것 — 권한 문장 단언은 전부 이것을 본다."""
    return re.sub(r"\s+", " ", statements(sql))


def fn_block(sql, name):
    """`create or replace function <name>(` 부터 `$$;` 까지 (머리 + 본문).

    ⛔ `(?!api\\.)` 로 api 쌍둥이를 배제한다 — 통과 함수라 본문이 한 줄뿐이고, 그걸 잡으면
       아래 개수 세기가 전부 0 이 되어 **가짜 초록**이 된다.
    """
    sql = norm(sql)
    m = re.search(
        r"(?im)^create\s+or\s+replace\s+function\s+(?!api\.)(?:public\.)?"
        + name + r"\s*\(",
        sql,
    )
    assert m, "{} 정의를 못 찾았습니다".format(name)
    end = sql.index(DOLLAR + ";", m.start())
    return sql[m.start():end]


def at(pattern, sql, last=False):
    """줄머리 정규식이 처음(또는 마지막) 나오는 **위치**."""
    found = [m.start() for m in re.finditer(pattern, sql)]
    assert found, pattern
    return found[-1] if last else found[0]


# 아래 여섯 시험이 쓰는 **판정 한 벌**. 돌연변이 시험(§5)이 이걸 그대로 태워서
# "가드가 진짜 무는지"를 증명한다 — 시험 안에서 조건을 다시 쓰면 돌연변이가 그 사본만
# 통과시켜 아무것도 증명하지 못한다.
def cast_defects(block):
    """함수 블록 하나를 보고 **어긋난 점 목록**을 돌려준다(비었으면 정상)."""
    code = statements(block)
    bad = []
    n_cast = code.count(CAST)
    if n_cast != 2:
        bad.append("`{}` 가 {}번입니다(2번이어야 합니다)".format(CAST, n_cast))
    n_bare = code.count(BARE)
    if n_bare:
        bad.append("캐스트 없는 `{}` 가 {}군데 남았습니다".format(BARE, n_bare))
    n_wide = code.count(NATIONWIDE)
    if n_wide != 2:
        bad.append("`{}` 가 {}번입니다(2번이어야 합니다 — 전국 검색 허용)"
                   .format(NATIONWIDE, n_wide))
    return bad


# ── 1. 네 자리에 캐스트가 붙어 있는가 ────────────────────────────────────────


class TestTheCastIsThere:
    @pytest.mark.parametrize("path", BOTH)
    @pytest.mark.parametrize("fn", [f for f, _ in FUNCS])
    def test_both_sites_compare_as_char5(self, path, fn):
        """⛔ 캐스트가 빠지면 색인이 Index Cond → Filter 로 떨어진다 — **에러 0**,
        답도 같고 느리기만 하다(그래서 사람이 못 잡는다)."""
        bad = cast_defects(fn_block(read(path), fn))
        assert not bad, "{} 의 {}: {}".format(LABEL[path], fn, " / ".join(bad))

    @pytest.mark.parametrize("path", BOTH)
    def test_the_finder_really_finds_a_body(self, path):
        """⛔ **파서가 헛돌면 위 시험이 조용히 초록이 된다** — 이 레포가 가장 여러 번
        데인 '가짜 초록'이다. 블록이 진짜 그 함수의 본문인지 못 박아 둔다."""
        for fn, _ in FUNCS:
            block = fn_block(read(path), fn)
            assert "mv_search_parcel" in block, (
                "{} 의 {} 블록에 mv_search_parcel 이 없습니다 — 엉뚱한 것을 뜯었습니다"
                .format(LABEL[path], fn))
            assert not block.lstrip().startswith("create or replace function api."), (
                "api 쌍둥이를 잡았습니다 — 통과 함수라 본문이 한 줄이고, 그러면 개수 "
                "세기가 전부 0 이 되어 가드가 있는 척만 합니다")


# ── 2. 전국 검색 절반은 그대로 ───────────────────────────────────────────────


class TestNationwideSearchSurvives:
    @pytest.mark.parametrize("path", BOTH)
    @pytest.mark.parametrize("fn", [f for f, _ in FUNCS])
    def test_the_null_branch_is_untouched(self, path, fn):
        """⛔ 이 둘은 구를 **안 고른 전국 검색을 일부러 허용**한다(결정 0028 에서 구를
        필수로 둔 `search_stores` 와 다른 점이다). 캐스트를 붙이며 `pat.gu is null or`
        를 함께 지우면 **전국 검색이 조용히 막힌다** — 에러가 아니라 0건이 된다."""
        code = statements(fn_block(read(path), fn))
        assert code.count(NATIONWIDE) == 2, (
            "{} 의 {}: 전국 검색 가지(`{}`)가 2번이 아닙니다"
            .format(LABEL[path], fn, NATIONWIDE))

    @pytest.mark.parametrize("path", BOTH)
    @pytest.mark.parametrize("fn", [f for f, _ in FUNCS])
    def test_the_two_halves_sit_in_the_same_condition(self, path, fn):
        """`is null` 가지와 캐스트 비교가 **한 괄호 안**에 있어야 옛 동작과 같다.

        따로 떨어지면(예: `and pat.gu is null` 을 위로 올리면) 구를 고른 검색이 통째로
        0건이 된다 — 이것도 에러 없이 조용하다.
        """
        code = statements(fn_block(read(path), fn))
        whole = "({} {})".format(NATIONWIDE, CAST)
        assert code.count(whole) == 2, (
            "{} 의 {}: `{}` 모양이 2번이 아닙니다".format(LABEL[path], fn, whole))


# ── 3. 정본과 마이그레이션이 글자 그대로 같은가 ──────────────────────────────


class TestSchemaMirrorsTheMigration:
    @pytest.mark.parametrize("fn", [f for f, _ in FUNCS])
    def test_function_blocks_letter_for_letter(self, fn):
        """⛔ 정본만 살짝 다듬는 것이 곧 정본↔라이브 불일치다(2026-09-01 2차 적대검증).
        함수 본문 주석은 `pg_proc.prosrc` 에 실려 **라이브의 일부**가 되기 때문이다.

        ⓘ 전 함수를 훑는 형제 가드가 따로 있다(tests/test_schema_function_drift.py).
          여기서는 이 둘을 못 박아 두어, 실패 메시지가 무엇 때문인지 바로 보이게 한다.
        """
        assert fn_block(read(MIGRATION), fn) == fn_block(read(SCHEMA), fn), (
            "{} 의 본문이 정본과 다릅니다 — 마이그레이션 쪽이 라이브에 실리는 것입니다. "
            "설명을 늘리고 싶으면 `create` 문 **바깥** 머리말에 적으세요.".format(fn))


# ── 4. 전부 아니면 전무 · 다시 만든 자리에서 다시 닫는가 ─────────────────────


class TestAtomicity:
    def test_begin_comes_before_the_first_ddl(self):
        """⛔ `dbx.py` 는 자동커밋이다 — 감싸지 않고 중간에 끊기면 **한 함수만 새 것**인
        상태가 남는다(에러 0 · 한쪽만 느린, 찾기 어려운 어긋남)."""
        code = statements(read(MIGRATION))
        assert at(r"(?m)^begin;", code) < at(
            r"(?im)^create\s+or\s+replace\s+function\b", code), (
            "첫 DDL 이 begin; 보다 앞에 있습니다")

    def test_commit_comes_after_the_last_ddl(self):
        code = statements(read(MIGRATION))
        last_ddl = max(
            at(r"(?im)^create\s+or\s+replace\s+function\b", code, last=True),
            at(r"(?im)^revoke\b", code, last=True),
        )
        assert last_ddl < at(r"(?m)^commit;", code), (
            "마지막 문장이 commit; 뒤에 있습니다 — 덩어리 밖으로 새어 나갔습니다")

    def test_notify_comes_after_commit(self):
        """⛔ 커밋 **뒤**여야 한다 — 롤백된 판에서 PostgREST 에 헛알림이 가면 안 된다
        (09-09b 선례). 빠지면 DB 에는 함수가 멀쩡한데 화면만 404(PGRST202) 다."""
        code = statements(read(MIGRATION))
        assert at(r"(?m)^commit;", code) < at(r"(?im)^notify\s+pgrst\b", code)

    def test_no_concurrently(self):
        """⛔ `concurrently` 만은 트랜잭션 안에서 못 돈다 — 있으면 판이 통째로 실패한다."""
        assert "concurrently" not in statements(read(MIGRATION)).lower()


class TestItClosesTheDoorAgain:
    @pytest.mark.parametrize("fn,args", FUNCS)
    def test_revoke_is_restated(self, fn, args):
        """다시 만든 자리에서 다시 닫는다(2026-09-01d·2026-08-16b 관습).

        `create or replace` 가 권한을 보존하므로 기능상 필수는 아니다 — 그래도 대시보드가
        같은 함수를 다시 만드는 날 anon 기본권한이 조용히 붙어도 여기서 걷힌다.
        """
        line = "revoke all on function {}({}) from public, anon, authenticated;".format(
            fn, args)
        assert line in flat(read(MIGRATION)), (
            "마이그레이션에 `{}` 가 없습니다".format(line))

    def test_it_never_opens_the_public_original(self):
        """⛔ 화면이 부르는 문은 api 쌍둥이 하나뿐이다 — public 원본은 2026-09-05a 로
        닫아 둔 그대로여야 한다. grant 가 한 줄이라도 있으면 그 문이 다시 열린다."""
        code = statements(read(MIGRATION))
        assert not re.search(r"(?im)^\s*grant\b", code), (
            "마이그레이션에 grant 문이 있습니다 — 이 판은 권한을 열지 않습니다")

    def test_it_does_not_touch_the_api_twins(self):
        """⛔ api 쌍둥이는 본체를 통째로 넘기는 통과 함수라 본문이 안 바뀐다. 여기서
        다시 만들면 거기 붙은 grant 를 다시 적어야 하는 일이 딸려 온다."""
        code = statements(read(MIGRATION))
        assert "api." not in code, (
            "마이그레이션이 api.* 를 건드립니다 — 이 판의 범위 밖입니다")


# ── 5. 가드 자신의 시험 — 죽은 줄을 **진짜로** 잡는가 ────────────────────────
#
# ⓘ 아래 셋은 파일을 **안 건드린다** — 원문을 문자열로 읽어 한 군데를 망가뜨린 **사본**을
#   만들고 그 사본에 판정을 돌린다. 그래서 "복원"이 따로 필요 없다(디스크는 처음부터
#   그대로다). 시험이 중간에 죽어도 레포에 부서진 파일이 남지 않는다.


@pytest.mark.parametrize("path", BOTH)
@pytest.mark.parametrize("fn", [f for f, _ in FUNCS])
def test_the_guard_catches_a_removed_cast(path, fn):
    """⛔ **가드가 진짜 무는지**를 시험 안에서 확인한다.

    캐스트를 하나만 떼면 그 자리만 조용히 느려진다 — 답은 같으므로 다른 어떤 시험도
    안 잡는다. 그래서 '하나만 뗀' 사본으로 실제 판정 경로를 태운다.
    """
    block = fn_block(read(path), fn)
    assert not cast_defects(block), "전제: 원문은 정상이어야 한다"
    tampered = block.replace(CAST, "pc.sigungu_code = pat.gu", 1)
    assert tampered != block, "전제: 사본이 실제로 달라야 한다"
    assert cast_defects(tampered), (
        "캐스트를 하나 뗐는데도 '정상'이라 합니다 — 이 파일이 아무것도 안 막고 있습니다")


@pytest.mark.parametrize("path", BOTH)
@pytest.mark.parametrize("fn", [f for f, _ in FUNCS])
def test_the_guard_catches_a_removed_nationwide_branch(path, fn):
    """전국 검색 가지를 지우는 반대 방향도 잡아야 한다 — 이쪽은 0건이 되는 쪽이다."""
    block = fn_block(read(path), fn)
    tampered = block.replace("(" + NATIONWIDE + " " + CAST + ")", CAST, 1)
    assert tampered != block, "전제: 사본이 실제로 달라야 한다"
    assert cast_defects(tampered), (
        "전국 검색 가지를 뗐는데도 '정상'이라 합니다")


def test_statements_really_strips_comments():
    """⛔ **주석 제거기가 헛돌면 위 시험들이 조용히 가짜 초록이 된다** — 이 파일은 특히
    그렇다. 정본·마이그레이션의 ⛔ 주석에 `pat.gu is null or` 가 **글로** 적혀 있어서,
    안 걷으면 개수 세기가 전부 어긋난다."""
    text = read(MIGRATION)
    line = "revoke all on function search_scope(text, text) from public, anon, authenticated;"
    assert line in flat(text), "전제: 원문에는 그 문장이 살아 있다"
    assert line not in flat(text.replace(line, "-- " + line)), (
        "주석으로 죽인 revoke 가 여전히 '있다'고 읽힙니다 — 주석 제거가 헛돕니다")
