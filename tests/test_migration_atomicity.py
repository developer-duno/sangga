# -*- coding: utf-8 -*-
"""마이그레이션을 ``begin;`` … ``commit;`` 으로 감쌌는가 — **파일별이 아니라 전부**.

규칙(결정 0027:131, 2026-09-09 신설): 뷰·함수를 **지우고 다시 만드는** 마이그레이션은
``begin;`` … ``commit;`` 로 감싼다. ``scripts/dbx.py -f`` 는 psql 자동커밋
(``--single-transaction`` 없음)이라 문장 하나씩 커밋된다 — 중간에 끊기면 **지워진 채**
남고, 그 뷰·함수에 기대던 카드가 라이브에서 통째로 사라진다.

이 규칙은 지금까지 **파일별 시험 두 개**(2026-09-09b 는
``tests/test_tx_yearly_migration.py`` 의 ``TestTheRebuildIsAtomic``, 2026-09-09c 는
``tests/test_search_stores_migration.py`` 의 ``TestTheMigrationIsAtomic``)에만 걸려
있었다. 즉 **다음 마이그레이션을 쓰는 사람이 기억해야만** 지켜졌다 — 그러라고 만든
규칙이 아니다. 이 파일은 같은 판정을 **앞으로 생길 파일 전부**에 자동으로 건다.

무엇을 보나 (범위):

  ① 파일 이름이 ``2026-09-09`` **이상**이고
  ② 주석을 걷어낸 본문에 줄머리 ``drop`` 문장이 **있는** 마이그레이션.

왜 ①인가 — 그 앞의 파일들은 **이미 라이브에 적용된 역사**라 고치지 않는다. 여기에
알려진 옛 빚이 하나 있다: ``2026-09-05b_permit_stale_cnt.sql:56-57`` 은
``drop function if exists …`` 두 줄이 **있는데도** 감싸지 않았다. 이 파일이 가드에서
빠지는 이유는 "drop 이 없어서"가 아니라 **날짜 정책** 때문이다(고치지 않는다).

왜 ②인가 — ``create or replace`` 만 하는 판(예: ``2026-09-09a_tx_yearly.sql``)은
중간에 끊겨도 **반쪽으로 죽을 것이 없다**. 옛것이 그대로 살아 있거나 새것으로 바뀌었을
뿐이라, 감싸지 않은 것이 사실과 어긋나지 않는다. 규칙을 "모든 파일"로 넓히면 그런
파일까지 빨간불이 되고, 그러면 사람이 가드를 느슨하게 고친다.

⚠️ 걷어내는 주석은 `--` 줄과 `comment on … is '…'` 의 글뿐이다. `/* … */` 블록 주석과
   `$$ … $$` 안의 동적 SQL 문자열은 안 걷는다 — 이 레포 마이그레이션 **전부**에 그 둘은
   **0건**이고(관습이 `--` 뿐이다), 설령 생겨도 판정은 "감싸라"는 **안전한 쪽**으로
   틀린다(빠뜨리는 쪽이 아니다). 동적 SQL 을 쓰기 시작하면 그때 여기를 넓힌다.
   ⚠️ 반대로 **들여쓴** DDL(`  drop …`)은 줄머리 판정에서 빠져 **면제 쪽으로** 틀릴 수 있어서
   DDL·예외 정규식은 앞 공백을 허용한다(2026-09-10 사후 검증에서 보강).

무엇을 판정하나:

  1) 첫 DDL **앞**에 ``begin;``
  2) 마지막 DDL **뒤**에 ``commit;`` — 단 **하나의 예외**가 있다(아래)
  3) ``notify pgrst`` 를 쓴다면 ``commit;`` **뒤**에(안에 두면 롤백된 판에서도 헛알림)
  4) ``begin``…``commit`` 덩어리 안에 ``concurrently`` 없음(트랜잭션 안에서 못 돈다)

⛔ **예외는 딱 하나, 좁게**: 커밋 **뒤**에 남아도 되는 DDL 은 ``drop index if exists …;``
   뿐이다. ``2026-09-09c_search_stores.sql:469`` 이 옛 색인 ``idx_ub_name`` 을 그렇게
   지운다 — 덩어리 **안**에 두면 ACCESS EXCLUSIVE 락이 커밋까지 유지돼, 새 표를 굽는
   내내 점포 표 읽기가 전부 줄을 선다(2026-08-22c 가 적어 둔 함정). 그 파일의 형제
   시험(``test_search_stores_migration.py`` §5·§6)이 같은 예외를 같은 모양으로 적어
   두었고, 여기서는 그것을 **이름 없이** 일반화한다.

ⓘ 도우미(``read``·``norm``·``statements``·``code_only``)는 형제
  ``test_search_stores_migration.py`` 에서 **복사**해 왔다 — import 하지 않는다.
  시험 파일끼리 얽히면 한쪽의 고장이 다른 쪽을 조용히 가린다(형제 파일도 같은 이유로
  복사한다고 적어 두었다).

ⓘ 파일별 시험 둘은 **그대로 둔다**. 중복이 아니다 — 그쪽은 그 파일 고유의 규칙(옛 색인이
  맨 끝인가, 사슬을 안 건드렸는가)까지 함께 본다.
"""

import glob
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS = os.path.join(ROOT, "supabase", "migrations")

# 규칙이 태어난 날. 파일 이름이 이것 **이상**인 것만 본다(위 docstring ①).
RULE_BORN = "2026-09-09"

# 형제 파일들과 **같은** DDL 정의를 쓴다(test_search_stores_migration.py §5).
DDL = r"(?m)^\s*(alter |analyze |comment on |create |drop |grant |revoke )"

# ⛔ 커밋 뒤에 남아도 되는 **유일한** 모양. 이보다 넓히면 "덩어리 밖으로 새는 DDL" 이
#    그만큼 조용히 통과한다.
RE_TRAILING_OK = re.compile(r"(?m)^\s*drop index if exists [^;]+;")

# `comment on … is '…';` 한 문장. 여러 줄에 걸치고, 끝은 항상 `';` 다.
RE_COMMENT_STMT = re.compile(r"(?ims)^comment\s+on\s+.*?';\s*$")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def norm(text):
    """줄바꿈 표기(CRLF/LF)만 통일한다 — 공백·주석은 일부러 안 건드린다."""
    return text.replace("\r\n", "\n")


def statements(sql):
    """주석을 걷어낸 **실제 SQL 문장만** (줄바꿈은 그대로 — `(?m)^…` 정규식용).

    설명 주석에 적어 둔 말이 문장으로 오해되면 코드가 망가져도 초록이 된다.
    """
    return "\n".join(
        line for line in norm(sql).splitlines() if not line.lstrip().startswith("--")
    )


def code_only(sql):
    """주석 **그리고 `comment on … is '…'` 문장까지** 걷어낸 것.

    ⛔ 왜 따로 필요한가: `comment on` 의 본문은 사람이 읽는 **글**인데 SQL 로는 엄연한
       문장이라 `statements()` 에 그대로 남는다. 그 글 안에 "drop …" 으로 시작하는 줄이
       한 번이라도 들어가면 **감쌀 필요가 없는 파일이 감시 대상으로 둔갑**한다. 그래서
       "이 파일을 볼 것인가"(②)는 이쪽으로 판정한다.
       (순서 판정은 형제 시험과 **글자 그대로 같게** `statements()` 로 본다 — 같은 파일을
        두 가드가 다르게 판정하면 그게 더 나쁘다.)
    """
    return RE_COMMENT_STMT.sub("", statements(sql))


def _first(pattern, sql):
    """줄머리 정규식이 처음 나오는 **위치**. 없으면 None."""
    m = re.search(pattern, sql)
    return m.start() if m else None


def needs_wrapping(sql):
    """②판정 — 주석을 걷은 본문에 줄머리 `drop` 문장이 있나."""
    return re.search(r"(?m)^drop ", code_only(sql)) is not None


def check(sql):
    """어긴 것을 **사람이 읽을 문장의 목록**으로 돌려준다(빈 목록 = 통과).

    범위 밖(②에 안 걸리는 파일)이면 아무것도 안 본다 — 그건 통과가 아니라 **면제**라,
    시험에서는 `needs_wrapping()` 으로 그 사실을 따로 못 박는다.
    """
    if not needs_wrapping(sql):
        return []

    low = statements(sql).lower()
    bad = []

    begin = _first(r"(?m)^begin;", low)
    commit = _first(r"(?m)^commit;", low)
    if begin is None:
        bad.append("`begin;` 이 없습니다 — drop 이 있는 판은 감싸야 합니다")
    if commit is None:
        bad.append("`commit;` 이 없습니다 — drop 이 있는 판은 감싸야 합니다")
    if begin is None or commit is None:
        return bad

    ddl = [m.start() for m in re.finditer(DDL, low)]
    if not ddl:
        bad.append("DDL 을 하나도 못 찾았습니다 — 판정기가 헛돌고 있습니다")
        return bad

    if begin > ddl[0]:
        bad.append("`begin;` 이 첫 DDL 뒤에 있습니다: {!r}".format(
            low[ddl[0]:ddl[0] + 60]))

    for pos in [p for p in ddl if p > commit]:
        if not RE_TRAILING_OK.match(low, pos):
            bad.append("`commit;` 뒤에 남은 DDL 이 있습니다: {!r}".format(
                low[pos:pos + 60]))

    notify = _first(r"(?m)^notify pgrst", low)
    if notify is not None and notify < commit:
        bad.append("`notify pgrst` 가 `commit;` 앞에 있습니다 — 롤백된 판에서도 알림이 갑니다")

    # ④ 는 코멘트 **본문**에 그 낱말이 적혀 있어도 괜찮아야 하므로 code_only 로 본다
    #    (형제 09-09c 는 파일 전체에 낱말이 없다고 못 박지만, 여기서는 앞으로 생길 파일을
    #     보는 일반 가드라 "설명에 적는 것"까지 막으면 헛것을 잡는다).
    code = code_only(sql).lower()
    c_begin = _first(r"(?m)^begin;", code)
    c_commit = _first(r"(?m)^commit;", code)
    if c_begin is not None and c_commit is not None:
        if "concurrently" in code[c_begin:c_commit]:
            bad.append(
                "`begin`…`commit` 안에 `concurrently` 가 있습니다 — 트랜잭션 안에서 못 돕니다")

    return bad


def dated_files():
    """이름이 규칙이 태어난 날 **이상**인 마이그레이션(②는 아직 안 본다)."""
    return sorted(
        p for p in glob.glob(os.path.join(MIGRATIONS, "*.sql"))
        if os.path.basename(p) >= RULE_BORN
    )


def guarded_files():
    """①②를 모두 만족해 이 가드가 **실제로 보는** 파일."""
    return [p for p in dated_files() if needs_wrapping(read(p))]


def names(paths):
    return [os.path.basename(p) for p in paths]


# ── 1. 지금 나무는 깨끗한가 ──────────────────────────────────────────────────


@pytest.mark.parametrize("path", guarded_files(), ids=names(guarded_files()))
def test_every_guarded_migration_is_atomic(path):
    assert check(read(path)) == [], os.path.basename(path)


# ── 2. 범위가 우리가 생각하는 그것인가 (가정이 아니라 증명) ──────────────────


class TestTheScopeIsProven:
    """⛔ 범위를 안 못 박으면 **아무 파일도 안 보면서 초록**이 될 수 있다(가짜 초록).

    그래서 "무엇을 보고 무엇을 건너뛰는지"를 이름으로 적어 둔다.
    """

    def test_it_looks_at_something_at_all(self):
        assert guarded_files(), (
            "보는 파일이 0개입니다 — glob 경로나 RULE_BORN 이 어긋났습니다"
        )

    def test_the_two_known_files_are_in_scope(self):
        got = names(guarded_files())
        assert "2026-09-09b_tx_yearly_area.sql" in got
        assert "2026-09-09c_search_stores.sql" in got

    def test_a_file_without_drop_is_skipped_not_passed(self):
        """09-09a 는 날짜로는 들어오지만 `create or replace` 만 해서 **면제**다."""
        a = os.path.join(MIGRATIONS, "2026-09-09a_tx_yearly.sql")
        assert a in dated_files()
        assert not needs_wrapping(read(a))
        assert a not in guarded_files()
        # 같은 날 뒤에 들어온 2026-09-10a·10b 도 `create or replace` 뿐이라 면제다 — 여기 못 박아
        # 두어야 "고려했나 놓쳤나"를 다음 사람이 안 묻는다(2026-09-10 사후 검증).
        for name in ("2026-09-10a_search_gu_index_cond.sql",
                     "2026-09-10b_search_stores_names_after_limit.sql"):
            f = os.path.join(MIGRATIONS, name)
            assert f in dated_files(), name
            assert not needs_wrapping(read(f)), name
            assert f not in guarded_files(), name

    def test_the_old_unwrapped_drop_is_excluded_by_date_only(self):
        """⛔ 05b 는 **drop 이 있는데도 안 감싼** 알려진 옛 빚이다(이미 적용된 역사).

        빠지는 이유가 "drop 이 없어서"가 아니라 **날짜**임을 여기서 못 박는다 — 그래야
        다음 사람이 "저건 왜 통과했지?" 를 다시 조사하지 않는다.
        """
        b = os.path.join(MIGRATIONS, "2026-09-05b_permit_stale_cnt.sql")
        assert os.path.exists(b)
        assert needs_wrapping(read(b)), "전제: 05b 에는 drop 문장이 있다"
        assert b not in dated_files(), "05b 가 날짜 정책으로 빠져야 합니다"
        assert check(read(b)), "전제: 감쌌다면 이 시험의 전제가 낡은 것이다"


# ── 3. 판정기 자신의 시험 — 죽은 줄을 **진짜로** 잡는가 ──────────────────────
#
# ⓘ 아래는 파일을 **안 건드린다** — 원문을 문자열로 읽어 한 군데를 망가뜨린 **사본**에
#   판정을 돌린다. 디스크는 처음부터 그대로다.

B = os.path.join(MIGRATIONS, "2026-09-09b_tx_yearly_area.sql")
C = os.path.join(MIGRATIONS, "2026-09-09c_search_stores.sql")

NO_DROP = (
    "create or replace function f(x text)\n"
    "returns int language sql as $$ select 1 $$;\n"
    "notify pgrst, 'reload schema';\n"
)

BARE_DROP = (
    "drop view if exists v;\n"
    "create view v as select 1;\n"
    "notify pgrst, 'reload schema';\n"
)


def test_mutation_a_removing_begin_is_noticed():
    """돌연변이 ① 09-09b 에서 `begin;` 을 지운다 → 빨간불이 나야 한다."""
    text = norm(read(B))
    assert check(text) == [], "전제: 원문은 통과한다"
    broken = text.replace("\nbegin;\n", "\n", 1)
    assert "\nbegin;\n" not in broken, "지우기가 안 됐습니다"
    assert check(broken), "`begin;` 을 지웠는데도 통과합니다 — 판정기가 헛돕니다"


def test_mutation_b_a_bare_drop_and_recreate_is_noticed():
    """돌연변이 ② 감싸지 않은 drop+재생성 → 빨간불."""
    assert needs_wrapping(BARE_DROP)
    bad = check(BARE_DROP)
    assert bad, "감싸지 않은 drop 이 통과합니다"
    assert any("begin;" in m for m in bad), bad


def test_mutation_c_a_file_without_drop_is_out_of_scope():
    """돌연변이 ③ drop 이 없으면 **아예 안 본다**(면제 — 통과와 구별해 못 박는다)."""
    assert not needs_wrapping(NO_DROP)
    assert check(NO_DROP) == []


def test_mutation_d_notify_before_commit_is_noticed():
    """돌연변이 ④ `notify` 를 커밋 **안**으로 옮긴다 → 빨간불."""
    notify = "notify pgrst, 'reload schema';\n"
    text = norm(read(B))
    assert notify in text, "전제: 원문에 notify 가 있다"
    broken = text.replace(notify, "").replace("\ncommit;\n", "\n" + notify + "commit;\n", 1)
    low = statements(broken).lower()
    assert _first(r"(?m)^notify pgrst", low) < _first(r"(?m)^commit;", low), "옮기기가 안 됐습니다"
    assert check(broken), "notify 가 커밋 안으로 들어갔는데도 통과합니다"


def test_mutation_e_concurrently_inside_the_block_is_noticed():
    """돌연변이 ⑤ 덩어리 안에 `create index concurrently` → 빨간불.

    ⛔ 이건 SQL 이 **통째로 실패**하는 종류라, 라이브에 붙여 넣기 전에 잡아야 한다.
    """
    text = norm(read(B))
    broken = text.replace(
        "\ncommit;\n", "\ncreate index concurrently idx_x on t (a);\ncommit;\n", 1)
    assert "concurrently" in broken, "끼워 넣기가 안 됐습니다"
    bad = check(broken)
    assert bad, "덩어리 안의 concurrently 가 통과합니다"
    assert any("concurrently" in m for m in bad), bad


def test_mutation_f_the_trailing_exception_is_narrow():
    """돌연변이 ⑥ 커밋 **뒤**에 색인 지우기 말고 **다른** DDL 을 둔다 → 빨간불.

    ⛔ 예외가 "커밋 뒤면 뭐든 괜찮다"로 넓어지면, 덩어리 밖으로 새는 DDL 이 그만큼 조용히
       통과한다. 09-09c 의 `drop index if exists …` 하나만 봐 줘야 한다.
    """
    text = norm(read(C))
    assert check(text) == [], "전제: 원문(커밋 뒤 색인 지우기 하나)은 통과한다"
    broken = text.rstrip() + "\ndrop table if exists t;\n"
    bad = check(broken)
    assert bad, "커밋 뒤의 `drop table` 이 통과합니다 — 예외가 너무 넓습니다"
    assert any("commit;" in m for m in bad), bad


def test_statements_really_strips_comments():
    """⛔ **주석 제거기가 헛돌면 위 시험들이 조용히 가짜 초록이 된다.**"""
    # ⓘ 머리말 주석에도 "begin;" 이라는 **낱말**이 적혀 있다 — 그래서 줄 통째로 겨눈다.
    text = norm(read(B))
    assert _first(r"(?m)^begin;", statements(text)) is not None, "전제: 원문에 begin 문장이 있다"
    killed = text.replace("\nbegin;\n", "\n-- begin;\n", 1)
    assert _first(r"(?m)^begin;", statements(killed)) is None, (
        "주석으로 죽인 `begin;` 이 여전히 '있다'고 읽힙니다 — 주석 제거가 헛돕니다"
    )
    assert check(killed), "주석으로 죽였는데도 판정기가 통과시킵니다"


def test_code_only_ignores_prose_inside_comment_statements():
    """⛔ `comment on` 본문에 적힌 **글**이 문장으로 오해되면, 감쌀 필요가 없는 파일이
    감시 대상으로 둔갑한다(형제 파일이 2026-09-01 에 겪은 것의 반대 얼굴)."""
    prose = (
        "create or replace view v as select 1;\n"
        "comment on view v is\n"
        "  '이 뷰를 갈아엎을 때는\n"
        "drop view v; 부터 적어야 한다는 옛 메모';\n"
    )
    assert re.search(r"(?m)^drop ", statements(prose)), "전제: 주석만 걷으면 그 글이 남는다"
    assert not needs_wrapping(prose), (
        "코멘트 **본문**의 글을 drop 문장으로 읽었습니다 — 헛것을 잡고 있습니다"
    )
