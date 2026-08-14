# -*- coding: utf-8 -*-
"""
scripts/load_rone_map.py 단위 테스트

DB 없이 검증한다:
  1. 값 검사      — ★ 빈 rone_region_nm 은 거부한다("모른다"는 행을 빼는 것으로 적는다)
  2. 중복 차단    — 같은 상권이 두 번이면 upsert 가 트랜잭션째 죽는다. 파이썬이 먼저 막는다
  3. ★ 관문 ①    — 모든 R-ONE 이름이 rent_stat 에 실존하는지 **DB 안에서** 본다
  4. ★ 관문 ②    — 모든 district_id 가 district 에 실존하는지 본다
  5. 유령 감지    — seed 에서 사라진 매핑은 **지우지 않고 세어서** 보여준다
  6. SQL 조립     — 한 트랜잭션, 배치, upsert, 작은따옴표 escape
  7. seed 실물    — 레포에 든 확정본이 스스로 통과하는가 (형식 회귀 방지)

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import io
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import load_rone_map as L  # noqa: E402


def row(did="3120197", nm="서울>강남>테헤란로", method="manual", note=""):
    return {"district_id": did, "rone_region_nm": nm, "match_method": method, "note": note}


# ── 1. 값 검사 ───────────────────────────────────────────────────────────────


def test_required_columns():
    with pytest.raises(ValueError) as e:
        L.assert_required_columns(["district_id", "rone_region_nm"])
    assert "match_method" in str(e.value)


def test_empty_region_name_is_rejected():
    """★ 빈 값이 들어가면 조인이 조용히 성립해 엉뚱한 임대료가 붙는다."""
    with pytest.raises(ValueError) as e:
        L.record_to_row({"district_id": "D1", "rone_region_nm": "  ",
                         "match_method": "manual"}, "3행")
    assert "3행" in str(e.value)


def test_unknown_match_method_is_rejected():
    with pytest.raises(ValueError) as e:
        L.record_to_row({"district_id": "D1", "rone_region_nm": "대전>둔산",
                         "match_method": "guess"}, "3행")
    assert "guess" in str(e.value)


def test_record_to_row_trims():
    got = L.record_to_row({"district_id": " D1 ", "rone_region_nm": " 대전>둔산 ",
                           "match_method": " manual ", "note": " 왜 "}, "3행")
    assert got == {"district_id": "D1", "rone_region_nm": "대전>둔산",
                   "match_method": "manual", "note": "왜"}


# ── 2. 중복 차단 ─────────────────────────────────────────────────────────────


def test_duplicate_pair_is_blocked_with_names():
    """같은 **쌍**이 겹치면 upsert 가 트랜잭션째 죽는다 — 미리 이름을 대고 멈춘다."""
    with pytest.raises(ValueError) as e:
        L.assert_unique([row(did="D1", nm="대전>둔산"), row(did="D1", nm="대전>둔산")])
    assert "D1" in str(e.value)


def test_same_district_with_two_paths_is_allowed():
    """★ district 단독 중복은 **정상**이다 — bld_type 마다 권역 분할이 달라 경로가 둘이다."""
    assert L.assert_unique([
        row(did="D1", nm="서울>여의도마포>공덕역"),
        row(did="D1", nm="서울>영등포신촌>공덕역"),
    ]) is True


def test_repo_seed_has_the_known_dual_paths():
    """★ 실측으로 확인된 이중 경로 4종이 seed 에 **양쪽 다** 들어 있어야 한다.

    한쪽만 들어가면 그 상권의 오피스(또는 상가) 통계가 조용히 사라진다.
    """
    rows = L.read_seed(L.DEFAULT_SEED)
    by_leaf = {}
    for r in rows:
        by_leaf.setdefault(r["rone_region_nm"].split(">")[-1], set()).add(r["rone_region_nm"])
    for leaf, want in (("공덕역", 2), ("당산역", 2), ("여의도", 2), ("홍대/합정", 2)):
        assert len(by_leaf.get(leaf, ())) == want, (leaf, by_leaf.get(leaf))


# ── 3~5. ★ 관문 ─────────────────────────────────────────────────────────────


def test_name_gate_raises_inside_sql():
    """★ select 로 세기만 하면 psql 종료코드가 0 이라 그대로 commit 된다."""
    sql = L.build_name_gate([row(nm="대전>둔산")])
    assert "raise exception" in sql
    assert "rent_stat" in sql
    assert "'대전>둔산'" in sql


def test_district_gate_raises_inside_sql():
    sql = L.build_district_gate([row(did="sbiz-10446")])
    assert "raise exception" in sql
    assert "from district d" in sql
    assert "'sbiz-10446'" in sql


def test_ghost_probe_counts_but_does_not_delete():
    """유령은 **정보**다. 지우면 실수 한 번에 매핑이 조용히 사라진다."""
    sql = L.build_ghost_probe([row(did="D1")])
    assert sql.lstrip().startswith("select count(*)")
    assert "delete" not in sql.lower()


def test_ghost_probe_counts_pairs_not_districts():
    """★ district 로만 세면 이중 경로 중 **한 줄만** 사라져도 안 보인다."""
    sql = L.build_ghost_probe([row(did="D1", nm="서울>여의도마포>공덕역")])
    assert "(m.district_id, m.rone_region_nm) not in" in sql
    assert "('D1', '서울>여의도마포>공덕역')" in sql


def test_overlap_gate_catches_double_counting():
    """★ 관문 ③ — 한 상권이 **같은 종류·같은 분기**에서 경로 둘에 닿으면 멈춘다.

    이중 경로를 허용한 근거는 "종류가 다르면 경로도 다르다"는 실측이다. 그 전제가
    깨지면 임대료가 두 번 잡히는데, 에러가 아니라 **숫자가 조용히 틀린다**.

    ⚠️ 이 테스트가 보는 것은 SQL 의 **모양**뿐이다(CI 에는 DB 가 없다). 실제 판정은
       라이브에서 psql 이 한다 — 그래서 `raise exception` 인지까지 확인한다
       (select 로 세기만 하면 psql 종료코드가 0 이라 그대로 commit 된다).
    """
    sql = L.build_overlap_gate()
    assert "raise exception" in sql
    assert "join rent_stat r on r.region_nm = m.rone_region_nm" in sql
    assert "group by m.district_id, r.bld_type, r.quarter" in sql
    assert "having count(distinct r.region_code) > 1" in sql


def test_overlap_gate_is_wired_into_build_sql():
    """★ 관문을 만들어 놓고 **안 부르면** 아무것도 안 지킨다 — 배선까지 본다."""
    sql = L.build_sql([row()])
    assert "having count(distinct r.region_code) > 1" in sql
    assert sql.index("insert into district_rone_map") < sql.index(
        "having count(distinct r.region_code) > 1"), (
        "겹침 관문은 넣은 뒤라야 표에 실제로 든 것을 검사한다")


def test_gates_come_before_any_insert():
    """관문이 insert 뒤에 오면 오타가 든 행이 먼저 들어갔다가 되돌려진다 — 순서가 중요하다."""
    sql = L.build_sql([row()])
    assert sql.index("rent_stat") < sql.index("insert into district_rone_map")
    assert sql.index("from district d") < sql.index("insert into district_rone_map")


# ── 6. SQL 조립 ──────────────────────────────────────────────────────────────


def test_sql_is_one_transaction():
    sql = L.build_sql([row()])
    assert sql.startswith("begin;")
    assert sql.rstrip().endswith("commit;")


def test_sql_batches():
    rows = [row(did="D{}".format(i)) for i in range(250)]
    sql = L.build_sql(rows, batch_rows=100)
    assert sql.count("insert into district_rone_map") == 3


def test_sql_upserts_on_the_composite_key():
    """★ 충돌 대상이 district_id 단독이면 이중 경로 둘째 줄이 첫째를 **덮어쓴다**."""
    sql = L.build_sql([row()])
    assert "on conflict (district_id, rone_region_nm) do update set" in sql
    assert "match_method = excluded.match_method" in sql


def test_quote_escaping():
    assert L.sql_str("a'b") == "'a''b'"
    assert L.sql_str("") == "null"


def test_empty_note_becomes_null_not_empty_string():
    """빈 문자열은 '적었는데 내용이 없다'로 읽힌다. 안 적은 것은 NULL 이라야 한다."""
    sql = L.build_sql([row(note="")])
    assert "'manual', null)" in sql


def test_build_sql_refuses_empty():
    with pytest.raises(ValueError):
        L.build_sql([])


# ── 7. 레포에 든 확정본 자체를 검사한다 ──────────────────────────────────────


def test_repo_seed_parses_and_builds():
    """★ seed 는 사람이 손으로 고치는 파일이다. 형식이 깨지면 여기서 먼저 걸린다."""
    rows = L.read_seed(L.DEFAULT_SEED)
    assert len(rows) > 100, "확정본이 너무 적습니다 — 파일이 잘렸을 수 있습니다"
    sql = L.build_sql(rows)
    assert sql.startswith("begin;") and sql.rstrip().endswith("commit;")


def test_repo_seed_paths_look_like_full_paths():
    """region_code 가 아니라 **이름 전체 경로**여야 한다 (bld_type 마다 코드가 다르다)."""
    for r in L.read_seed(L.DEFAULT_SEED):
        assert ">" in r["rone_region_nm"], r
        assert r["rone_region_nm"].split(">")[0] in ("서울", "대전"), r
        assert r["rone_region_nm"] == r["rone_region_nm"].strip()


def test_repo_seed_manual_rows_carry_a_reason():
    """근거 없는 manual 은 다음 사람이 검증할 수 없다."""
    bad = [r["district_id"] for r in L.read_seed(L.DEFAULT_SEED)
           if r["match_method"] == "manual" and not r["note"]]
    assert not bad, "근거(note)가 빈 manual 매핑: {}".format(bad)


def test_repo_seed_dropped_the_gunja_false_positive():
    """★ 적대검증이 잡은 오탐. 군자초등학교(3110223)는 동대문구 장안동 소재라
    광진구 군자 상권이 아니다 — 다시 들어오면 여기서 걸린다."""
    ids = {r["district_id"] for r in L.read_seed(L.DEFAULT_SEED)}
    assert "3110223" not in ids


def test_repo_seed_low_score_token_rows_admit_they_were_promoted():
    """★ 점수 0.30 미만인데 token 으로 적힌 행은 **이중 권역 규칙으로 승격**된 것이다.

    그 사실이 note 에 없으면 다음 사람이 method 만 보고 "token 이니 그럭저럭"이라고
    신뢰도를 오판한다.
    """
    bad = []
    for r in L.read_seed(L.DEFAULT_SEED):
        if r["match_method"] != "token" or "앞말 겹침 " not in r["note"]:
            continue
        score = float(r["note"].split("앞말 겹침 ")[1].split(" ")[0])
        if score < 0.30 and "승격" not in r["note"]:
            bad.append((r["district_id"], r["rone_region_nm"], score))
    assert not bad, "승격 사실이 안 적힌 저겹침 token 행: {}".format(bad)


def test_seed_file_is_utf8_without_bom():
    with io.open(L.DEFAULT_SEED, "rb") as f:
        head = f.read(3)
    assert head != b"\xef\xbb\xbf", "BOM 이 붙으면 첫 컬럼 이름이 안 읽힌다"
