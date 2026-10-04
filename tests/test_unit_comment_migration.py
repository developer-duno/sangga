# -*- coding: utf-8 -*-
"""2026-10-04c — v_unit_current 뷰 설명 글이 정본(schema.sql)과 글자 그대로 같은가.

설명 글은 드리프트 가드(`test_schema_function_drift.py` — 함수 `$$` 본문만)도 `--check`
도 안 본다. 그래서 08-13b 가 라이브에 넣은 마지막 문장을 정본이 빠뜨린 채 한 달 넘게
남아 있었다(이 마이그레이션이 함께 고친다). 같은 일이 다시 생기지 않게 둘을 대조한다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "supabase" / "migrations" / "2026-10-04c_unit_comment.sql"
SCHEMA = ROOT / "supabase" / "schema.sql"

_COMMENT_RE = re.compile(r"comment on view v_unit_current is\s*((?:'(?:[^']|'')*'\s*)+);", re.S)


def comment_text(sql: str) -> str:
    """`comment on view v_unit_current is '…' '…';` 의 글을 이어 붙여 돌려준다(마지막 것)."""
    found = _COMMENT_RE.findall(sql)
    assert found, "v_unit_current 설명 글을 못 찾았습니다"
    parts = re.findall(r"'((?:[^']|'')*)'", found[-1])
    return "".join(parts)


def test_comment_matches_schema_letter_for_letter():
    mig = comment_text(MIGRATION.read_text(encoding="utf-8"))
    canon = comment_text(SCHEMA.read_text(encoding="utf-8"))
    assert mig == canon


def test_old_pilot_count_is_not_stated_as_current():
    text = comment_text(SCHEMA.read_text(encoding="utf-8"))
    # 63,717 은 남되 "처음 실측"한 옛 규모로만 — "63,717행 100%" 꼴(현재 규모처럼 읽힘)은 없다.
    assert "63,717행 100%" not in text
    assert "강남 파일럿 63,717행" in text
    assert "린트 0010" in text


def test_detector_catches_a_drift():
    """양성 대조 — 한 글자만 달라도 대조가 잡는가."""
    mig = MIGRATION.read_text(encoding="utf-8")
    # ⓘ 머리말에도 같은 낱말이 있어 설명 글에만 있는 조각으로 바꾼다.
    altered = mig.replace("2026-10-04 호실 표는 2,950,009행", "2026-10-04 호실 표는 2,950,008행", 1)
    assert altered != mig
    assert comment_text(altered) != comment_text(SCHEMA.read_text(encoding="utf-8"))


def test_migration_does_not_rebuild_the_view():
    code = "\n".join(
        line for line in MIGRATION.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--")
    ).lower()
    assert "create or replace view" not in code
    assert "drop " not in code
