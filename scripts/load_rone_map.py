# -*- coding: utf-8 -*-
"""seed CSV → `district_rone_map` 적재 (한 트랜잭션).

무엇을 넣나
-----------
`scripts/seeds/district_rone_map.csv` — 사람이 확정한 "이 상권의 임대료는 부동산원의
어느 줄에서 읽는가" 목록이다. 후보를 만드는 것은 build_rone_map.py 고, **확정본은
이 CSV** 이며, 넣는 것이 이 스크립트다.

왜 psql 경유인가 (REST 가 아니라)
---------------------------------
검증 관문을 **DB 안에서** 걸어야 하기 때문이다. "이 R-ONE 이름이 rent_stat 에 실제로
있나"는 서버가 아니면 못 본다. REST 로 넣으면 오타 하나가 조용히 들어가 조인이 영원히
0건이 되고, 에러가 없으니 아무도 모른다.

⚠️ 검증 관문은 **raise exception 이라야** 한다
-----------------------------------------------
psql 은 select 가 몇 줄을 돌려주든 종료코드 0 이다. "0이어야 정상"이라고 적어 둬도
그대로 commit 된다. do 블록에서 예외를 던져야 ON_ERROR_STOP 이 걸리고 트랜잭션이
통째로 되돌아간다(load_sbiz_district.py 에서 같은 이유로 배운 것).

쓰는 법
-------
    python scripts/load_rone_map.py --dry-run          # DB 쓰기 0
    python scripts/load_rone_map.py --sql-out out.sql  # SQL 만 저장
    python scripts/load_rone_map.py                    # 적재
"""

import argparse
import csv
import io
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_SEED = os.path.join(SCRIPTS_DIR, "seeds", "district_rone_map.csv")

REQUIRED_COLUMNS = ("district_id", "rone_region_nm", "match_method", "note")
VALID_METHODS = ("exact", "normalized", "token", "manual")
BATCH_ROWS = 100


# ── 순수 함수 (파일·DB 없음 — 테스트 대상) ───────────────────────────────────


def sql_str(value):
    """SQL 문자열 리터럴. 작은따옴표는 두 번 써서 escape 한다."""
    if value is None or value == "":
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def assert_required_columns(fieldnames):
    """머리글이 우리가 아는 그것인지 본다. 다르면 조용히 NULL 이 되지 않게 멈춘다."""
    have = [(f or "").strip().lstrip("﻿") for f in (fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in have]
    if missing:
        raise ValueError(
            "seed CSV 머리글에 {} 가 없습니다 (있는 것: {}).".format(
                ", ".join(missing), ", ".join(have) or "(없음)"))
    return True


def record_to_row(rec, where):
    """CSV 한 줄 → 적재용 dict. 값 검사를 여기서 끝낸다."""
    did = (rec.get("district_id") or "").strip()
    nm = (rec.get("rone_region_nm") or "").strip()
    method = (rec.get("match_method") or "").strip()
    if not did:
        raise ValueError("{}: district_id 가 비어 있습니다.".format(where))
    # "모른다"는 빈 값이 아니라 **행을 빼는 것**으로 적는다 — 이 규칙이 이 표의 존재
    # 이유다(district_rone_map 표 주석 참조).
    if not nm:
        raise ValueError(
            "{}: rone_region_nm 이 비어 있습니다. "
            "'모른다'는 빈 값이 아니라 **행을 빼는 것**으로 적습니다 — 빈 값이 들어가면 "
            "조인이 조용히 성립해 엉뚱한 임대료가 붙습니다.".format(where))
    if method not in VALID_METHODS:
        raise ValueError(
            "{}: match_method 가 {!r} 입니다. {} 중 하나여야 합니다 — "
            "어떻게 이었는지가 나중에 '이 매핑을 얼마나 믿을 수 있나'의 유일한 근거입니다."
            .format(where, method[:20], "/".join(VALID_METHODS)))
    return {"district_id": did, "rone_region_nm": nm, "match_method": method,
            "note": (rec.get("note") or "").strip()}


def assert_unique(rows):
    """같은 **(상권, 이름 경로) 쌍**이 두 번 나오면 멈춘다.

    ⚠️ 쌍이 겹치면 PostgreSQL 이 "ON CONFLICT DO UPDATE command cannot affect row a
    second time" 로 **트랜잭션째** 죽는데, 그 메시지만으로는 어느 줄이 겹쳤는지 알 수
    없다. 여기서 이름을 대고 멈춘다.

    ⚠️ **district_id 단독 중복은 정상이다.** 부동산원이 bld_type 마다 서울 권역 분할을
    달리해 같은 상권이 경로 둘(오피스=여의도마포·기타 / 상가=영등포신촌)을 갖는다
    (라이브 실측 2026-08-14). 그래서 PK 가 복합이고, 여기서도 쌍으로만 본다.
    """
    seen = {}
    for r in rows:
        key = (r["district_id"], r["rone_region_nm"])
        seen[key] = seen.get(key, 0) + 1
    dupes = sorted(k for k, v in seen.items() if v > 1)
    if dupes:
        raise ValueError(
            "같은 (district_id, rone_region_nm) 쌍이 여러 번 나옵니다: {}{}.".format(
                ", ".join("{} → {}".format(*k) for k in dupes[:5]),
                " 외 {}개".format(len(dupes) - 5) if len(dupes) > 5 else ""))
    return True


def row_to_values_sql(row):
    return "({}, {}, {}, {})".format(
        sql_str(row["district_id"]), sql_str(row["rone_region_nm"]),
        sql_str(row["match_method"]), sql_str(row["note"]))


def build_insert(chunk):
    """values 한 뭉치 → upsert 한 문장."""
    return (
        "insert into district_rone_map "
        "(district_id, rone_region_nm, match_method, note)\n"
        "values\n{values}\n"
        "on conflict (district_id, rone_region_nm) do update set "
        "match_method = excluded.match_method, "
        "note = excluded.note;"
    ).format(values=",\n".join(row_to_values_sql(r) for r in chunk))


def build_name_gate(rows):
    """관문 ① — seed 의 R-ONE 이름이 rent_stat 에 **실제로 있는가**.

    오타 하나("서울>강남>테헤란로 " 처럼 꼬리 공백까지)가 들어가면 조인이 영원히 0건이
    되는데 에러는 안 난다. 이 표를 만드는 이유가 그 조인이므로, 없으면 아예 안 넣는다.
    """
    names = sorted({r["rone_region_nm"] for r in rows})
    return (
        "do $$\n"
        "declare bad text;\n"
        "begin\n"
        "  select string_agg(x.nm, ', ') into bad\n"
        "    from (values {values}) as x(nm)\n"
        "   where not exists (select 1 from rent_stat r where r.region_nm = x.nm);\n"
        "  if bad is not null then\n"
        "    raise exception 'rent_stat 에 없는 R-ONE 상권 이름: % — "
        "이대로 넣으면 조인이 영원히 0건인데 에러는 안 납니다', bad;\n"
        "  end if;\n"
        "end $$;"
    ).format(values=", ".join("({})".format(sql_str(n)) for n in names))


def build_district_gate(rows):
    """관문 ② — seed 의 상권이 district 에 **실제로 있는가**.

    외래키가 겹으로 지키지만, FK 위반 메시지는 "어느 값이 문제인지"를 안 알려준다.
    상권 코드는 소스가 바뀌면 통째로 갈리므로(서울 숫자 vs `sbiz-` 접두) 여기서
    이름을 대고 멈춘다.
    """
    ids = sorted({r["district_id"] for r in rows})
    return (
        "do $$\n"
        "declare bad text;\n"
        "begin\n"
        "  select string_agg(x.id, ', ') into bad\n"
        "    from (values {values}) as x(id)\n"
        "   where not exists (select 1 from district d where d.district_id = x.id);\n"
        "  if bad is not null then\n"
        "    raise exception 'district 에 없는 상권 코드: % — "
        "상권 자료를 먼저 적재했는지 확인하세요', bad;\n"
        "  end if;\n"
        "end $$;"
    ).format(values=", ".join("({})".format(sql_str(i)) for i in ids))


def build_overlap_gate():
    """★ 관문 ③ — 이중 경로가 **같은 통계 종류에서 겹치면** 멈춘다.

    이중 경로를 허용한 근거는 "종류가 다르면 경로도 다르다"는 실측이다(오피스는
    여의도마포·기타, 상가는 영등포신촌). 그 전제가 깨져 **한 상권 + 한 종류 + 한 분기**에
    두 경로가 동시에 닿으면, 임대료가 **두 번 잡힌다** — 평균이든 합이든 조용히 틀린다.
    자료가 바뀌는 순간(부동산원이 권역을 다시 나누는 순간) 여기서 걸린다.

    세는 단위를 **분기까지** 내리는 이유: region_code 는 분기마다 갈릴 수 있어서
    분기를 안 묶으면 정상적인 코드 변경을 겹침으로 오해한다.
    """
    return (
        "do $$\n"
        "declare bad text;\n"
        "begin\n"
        "  select string_agg(t.txt, ' / ') into bad from (\n"
        "    select m.district_id || ' [' || r.bld_type || ' ' || r.quarter || '] → '\n"
        "           || string_agg(distinct r.region_code, ',') as txt\n"
        "      from district_rone_map m\n"
        "      join rent_stat r on r.region_nm = m.rone_region_nm\n"
        "     group by m.district_id, r.bld_type, r.quarter\n"
        "    having count(distinct r.region_code) > 1\n"
        "  ) t;\n"
        "  if bad is not null then\n"
        "    raise exception '한 상권이 같은 통계 종류에서 경로 둘에 동시에 닿습니다: % — "
        "임대료가 이중으로 잡힙니다(이중 경로는 종류가 갈릴 때만 허용됩니다)', bad;\n"
        "  end if;\n"
        "end $$;"
    )


def build_ghost_probe(rows):
    """seed 에서 **사라진** 매핑을 세어 보여준다 (지우지는 않는다).

    왜 정보로만 두나: 사람이 일부러 뺀 것인지(잘못된 매핑을 거둔 것) 이번 판에서
    실수로 빠진 것인지는 자료를 봐야 안다. 여기서 막으면 정상적인 정정 때마다 적재가
    통째로 실패하고, 여기서 지우면 실수 한 번에 매핑이 조용히 사라진다.

    ⚠️ **쌍**으로 센다. district_id 로만 세면 이중 경로 중 한 줄이 사라져도 안 보인다.
    """
    pairs = sorted({(r["district_id"], r["rone_region_nm"]) for r in rows})
    return (
        'select count(*) as "seed 에서 사라진 매핑(사람이 확인할 것 — 0 이면 그대로)"\n'
        "  from district_rone_map m\n"
        " where (m.district_id, m.rone_region_nm) not in ({values});"
    ).format(values=", ".join("({}, {})".format(sql_str(i), sql_str(n))
                              for i, n in pairs))


def build_sql(rows, batch_rows=BATCH_ROWS):
    """전체 적재 SQL. 한 트랜잭션 — 중간에 걸리면 통째로 되돌린다.

    반쯤 들어간 매핑표는 "어떤 상권은 임대료가 붙고 어떤 상권은 안 붙는" 상태라,
    화면에서 보면 그냥 "표본이 없나 보다"로 보인다. 그래서 all-or-nothing 으로 간다.
    """
    if not rows:
        raise ValueError("넣을 매핑이 없습니다.")
    assert_unique(rows)

    out = ["begin;", "set local statement_timeout = '600s';"]
    out.append(build_name_gate(rows))
    out.append(build_district_gate(rows))
    for i in range(0, len(rows), batch_rows):
        out.append(build_insert(rows[i:i + batch_rows]))
    # 겹침 관문은 **넣은 뒤**라야 의미가 있다 — 표에 실제로 든 것을 rent_stat 과 맞춰 본다.
    # 걸리면 트랜잭션째 되돌아가므로 반쯤 든 상태가 남지 않는다.
    out.append(build_overlap_gate())
    out.append(build_ghost_probe(rows))
    out.append("commit;")
    return "\n".join(out) + "\n"


def summarize(rows):
    by_method, by_region, by_sido = {}, {}, {}
    for r in rows:
        by_method[r["match_method"]] = by_method.get(r["match_method"], 0) + 1
        by_region[r["rone_region_nm"]] = by_region.get(r["rone_region_nm"], 0) + 1
        sido = r["rone_region_nm"].split(">")[0]
        by_sido[sido] = by_sido.get(sido, 0) + 1
    return {"total": len(rows), "by_method": by_method,
            "regions": len(by_region), "by_sido": by_sido, "by_region": by_region}


# ── 파일 읽기 ────────────────────────────────────────────────────────────────


def read_seed(path):
    with io.open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert_required_columns(reader.fieldnames)
        rows = [record_to_row(rec, "{}행".format(lineno))
                for lineno, rec in enumerate(reader, start=2)]
    if not rows:
        raise ValueError("seed 에 매핑이 한 건도 없습니다: {}".format(path))
    assert_unique(rows)
    return rows


def main(argv=None):
    # 한국어 콘솔(cp949)에서 em-dash(—) 하나 때문에 통째로 죽지 않게 한다. 그대로 두면
    # --dry-run 이 SQL 을 다 만들어 놓고도 종료코드 1 로 끝나 "seed 가 잘못됐다"로
    # 오독된다(2026-08-14 적대검증 실환경 재현). 형제 스크립트들과 같은 처방이다.
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="seed CSV → district_rone_map 적재")
    p.add_argument("--seed", default=DEFAULT_SEED)
    p.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않는다")
    p.add_argument("--sql-out", help="만들어진 SQL 을 이 파일로 저장(검토용)")
    a = p.parse_args(argv)

    print("=" * 70)
    print("district_rone_map 적재")
    print("=" * 70)
    print("  seed: {}".format(a.seed))

    try:
        rows = read_seed(a.seed)
        sql = build_sql(rows)
    except (ValueError, OSError) as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1

    s = summarize(rows)
    print("  매핑 {:,}건 / R-ONE 상권 {}개".format(s["total"], s["regions"]))
    for k in ("exact", "normalized", "token", "manual"):
        if s["by_method"].get(k):
            print("    {:<11} {:>5,}".format(k, s["by_method"][k]))
    for k, v in sorted(s["by_sido"].items()):
        print("    {:<11} {:>5,}".format(k, v))
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
        print("적재 실패 (psql 종료코드 {}). 트랜잭션이라 아무것도 안 들어갔습니다."
              .format(rc), file=sys.stderr)
        return rc
    print()
    print("  적재 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
