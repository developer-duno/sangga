# -*- coding: utf-8 -*-
"""마이그레이션 2026-08-24a(건물 스펙 4칸)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙여 넣기 전에는 아무도 모르는 종류의 실수**다.
DB 없이 SQL 글자만 본다(CI 에는 DB 가 없다) — 대신 아래 넷은 글자만으로 확실히 잡힌다.

  1) `api` 쌍둥이를 다시 안 만듦
     → 뷰의 `select *` 는 **만들 때의 칼럼 목록으로 굳는다.** public 뷰에 칼럼을
       덧붙여도 쌍둥이는 옛 칼럼만 낸다. 에러가 아니라 **조용한 누락**이라, 화면은
       네 칸을 전부 "미상"으로 그리고 아무도 이유를 모른다(2026-08-22 실측 불변식).
  2) 쌍둥이 재생성이 public 교체보다 **먼저** 옴
     → 순서가 뒤집히면 쌍둥이가 옛 칼럼 목록을 다시 굳힌다. 1)과 증상이 똑같다.
  3) `notify pgrst, 'reload schema';` 누락
     → 새 칼럼이 스키마 캐시에 안 잡혀 다음 재시작까지 옛 응답이 계속 온다.
  4) 정본(schema.sql) 미동기 / 기존 칼럼 순서 훼손
     → 한쪽만 고쳐도 에러가 안 나고, 새 환경만 다르게 만들어진다.

⚠️ 한계: 값이 실제로 실려 오는지는 못 본다. 그건 라이브에서만 확인된다
   (마이그레이션 §5 검산 쿼리가 그 자리이고, 그것이 머지 조건이다).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(
    ROOT, "supabase", "migrations", "2026-08-24a_building_spec_cols.sql"
)
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

# 이번에 덧붙인 네 칸. 순서까지 이 순서 그대로여야 한다(뷰 끝에 이 차례로 붙는다).
NEW_COLS = ("total_area_m2", "far", "bcr", "parking_cnt")

# 덧붙이기 **전**의 마지막 칼럼. 새 칸은 반드시 이 뒤에 온다.
LAST_OLD_COL = "st.stores"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def migration():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


def floor_stack_block(sql):
    """public.v_floor_stack 의 select 목록만 잘라낸다.

    파일 전체에서 문자열을 찾으면 주석·검산 쿼리에 걸려 뷰가 망가져도 통과한다
    (test_display_name_sql_sync.py 가 같은 이유로 같은 방식을 쓴다).
    """
    head = "create or replace view v_floor_stack as"
    i = sql.find(head)
    if i < 0:
        return None
    j = sql.find("from v_building_floor_stack", i)
    return sql[i : j if j > 0 else len(sql)]


class TestNewColumns:
    @pytest.mark.parametrize("label", ["migration", "schema"])
    def test_four_columns_are_appended_after_the_old_ones(self, migration, schema, label):
        sql = migration if label == "migration" else schema
        block = floor_stack_block(sql)
        assert block, "{}: v_floor_stack 뷰 정의를 못 찾았습니다".format(label)
        # 가드가 헛돌지 않는지 먼저 — 옛 칼럼이 실제로 잡혀 있어야 한다.
        assert LAST_OLD_COL in block, (
            "{}: 잘라낸 블록에 옛 칼럼이 없습니다 — 자르는 위치가 틀렸습니다".format(label)
        )
        tail = block.split(LAST_OLD_COL, 1)[1]
        pos = []
        for col in NEW_COLS:
            m = re.search(r"(?m)^\s*b\.{}\b".format(re.escape(col)), tail)
            assert m, (
                "{}: v_floor_stack 이 b.{} 를 안 내보냅니다 — 화면의 그 칸이 영영 미상이 됩니다"
                .format(label, col)
            )
            pos.append(m.start())
        assert pos == sorted(pos), (
            "{}: 새 칼럼 순서가 {} 와 다릅니다 — 정본과 마이그레이션이 갈라집니다"
            .format(label, list(NEW_COLS))
        )

    def test_old_columns_keep_their_order(self, migration):
        """`create or replace view` 는 기존 칼럼의 이름·순서를 못 바꾼다.

        바꿔 적으면 라이브에서 그 자리가 통째로 실패한다(붙여 넣기 전에는 안 보인다).
        """
        block = floor_stack_block(migration)
        old = [
            "s.bld_id",
            "s.pnu",
            "s.floor_no",
            "s.floor_label",
            "s.floor_area_m2",
            "s.floor_area_gross_m2",
            "s.segment_cnt",
            "s.main_use",
            "s.uses",
            "b.display_nm as bld_nm",
            "b.approve_date",
            "b.is_jiphap",
            "p.road_addr",
            "p.road_contact",
            "pb.bld_cnt_in_pnu",
            "st.store_cnt",
            "st.stores",
        ]
        at = -1
        for col in old:
            i = block.find(col)
            assert i > at, (
                "기존 칼럼 순서가 어긋났습니다({}) — create or replace 가 라이브에서 거절합니다"
                .format(col)
            )
            at = i

    def test_view_is_replaced_not_dropped(self, migration):
        """drop 하면 그 사이 화면이 통째로 죽고 권한·주석도 같이 날아간다.

        ⓘ 머리말 주석에 인용된 `drop view …`(되돌리기 설명)는 실행문이 아니므로
          줄 맨 앞에서 시작하는 문장만 본다.
        """
        assert not re.search(r"(?im)^\s*drop\s+view", migration), (
            "실행문에 drop view 가 있습니다 — 칼럼 추가는 create or replace 로만 합니다"
        )


class TestApiTwin:
    def test_twin_is_recreated(self, migration):
        assert re.search(
            r"(?im)^create\s+or\s+replace\s+view\s+api\.v_floor_stack\s+as\s+"
            r"select\s+\*\s+from\s+public\.v_floor_stack",
            migration,
        ), (
            "api 쌍둥이를 다시 안 만듭니다 — 뷰의 select * 는 만들 때 굳으므로 "
            "화면(스키마 api)은 새 4칸을 영영 못 봅니다"
        )

    def test_twin_comes_after_the_public_view(self, migration):
        """순서가 뒤집히면 쌍둥이가 **옛** 칼럼 목록을 다시 굳힌다."""
        public_at = migration.find("create or replace view v_floor_stack as")
        twin_at = migration.find("create or replace view api.v_floor_stack")
        assert public_at != -1 and twin_at != -1
        assert public_at < twin_at, (
            "api 쌍둥이를 public 뷰보다 먼저 만듭니다 — 옛 칼럼 목록이 그대로 굳습니다"
        )

    def test_twin_revokes_before_granting(self, migration):
        """grant 는 더하기라, 자동으로 붙은 쓰기 권한을 못 걷어낸다(2026-08-22 라이브 사례)."""
        revoke = migration.find("revoke all on api.v_floor_stack")
        grant = migration.find("grant select on api.v_floor_stack")
        assert revoke != -1 and grant != -1, "api 쌍둥이의 revoke/grant 짝이 없습니다"
        assert revoke < grant, "api 쌍둥이는 회수를 먼저 하고 줘야 합니다"

    def test_tells_postgrest_to_reload(self, migration):
        assert "notify pgrst, 'reload schema';" in migration, (
            "스키마 캐시 리로드를 안 알리면 다음 재시작까지 새 칼럼이 안 잡힙니다"
        )


class TestSchemaSqlHasTheSameThing:
    def test_schema_notes_the_twin_trap(self, schema):
        """정본에도 함정이 적혀 있어야 한다 — 다음에 칼럼을 더하는 사람이 같은 데 빠진다."""
        i = schema.find("create or replace view api.v_floor_stack")
        assert i != -1, "정본에 api 쌍둥이가 없습니다"
        head = schema[max(0, i - 600) : i]
        assert "굳는다" in head, (
            "정본의 api 쌍둥이 위에 '`select *` 는 만들 때 굳는다' 경고가 없습니다 — "
            "다음 칼럼 추가 때 같은 함정에 다시 빠집니다"
        )

    def test_view_comment_warns_about_zero(self, schema):
        """0 이 "0" 이 아니라 "미기재"라는 사실은 DB 주석에도 남아야 한다.

        화면 코드만 아는 사실은, SQL 로 직접 집계하는 다음 사람에게는 없는 사실이다.
        """
        i = schema.find("comment on view v_floor_stack is")
        assert i != -1, "정본에 v_floor_stack 주석이 없습니다"
        body = schema[i : i + 1200]
        assert "대장 미기재" in body, "뷰 주석에 0=미기재 경고가 없습니다"
        for col in NEW_COLS:
            assert col in body, "뷰 주석이 {} 를 언급하지 않습니다".format(col)
