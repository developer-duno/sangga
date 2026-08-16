# -*- coding: utf-8 -*-
"""백테스트 산출물 `docs/backtest/통과구.csv` → `price_gate_sigungu` 적재 (한 트랜잭션).

무엇을 넣나
-----------
"이 구에서 참고 시세를 화면에 내도 되는가"의 **정본**이다. 판정 기준은 결정 0013 §2
(운영 MdAPE ≤ 30% **그리고** 사다리가 구 평균을 이길 것)이고, 그 판정을 실제로 내리는
곳은 `scripts/backtest_price.py` 하나뿐이다. 이 스크립트는 그 결과를 옮길 뿐 —
**여기서 구를 손으로 넣거나 빼지 않는다**(결정 0013 §4).

왜 화면·문서가 아니라 DB 한 곳인가
----------------------------------
목록을 화면 코드나 문서에 복사하면 성적표를 다시 뽑는 날 그 사본만 조용히 낡는다.
`list_open_sigungu()` 때 이미 겪은 드리프트다(확정 설계 9). 통과 구 목록의 진실은
서버 한 곳(price_gate_sigungu)이고, 화면은 `list_price_bands()` 를 통해서만 본다.

왜 psql 경유인가 (REST 가 아니라)
---------------------------------
검증 관문을 **DB 안에서** 걸어야 하기 때문이다. "이 구 코드가 실제로 열린 지역인가"는
서버가 아니면 못 본다(load_rone_map.py 와 같은 이유).

⚠️ 검증 관문은 **raise exception 이라야** 한다
-----------------------------------------------
psql 은 select 가 몇 줄을 돌려주든 종료코드 0 이다. "0이어야 정상"이라고 적어 둬도
그대로 commit 된다. do 블록에서 예외를 던져야 ON_ERROR_STOP 이 걸리고 트랜잭션이
통째로 되돌아간다(load_rone_map.py·load_sbiz_district.py 에서 같은 이유로 배운 것).

쓰는 법
-------
    python scripts/load_price_gate.py --dry-run          # DB 쓰기 0
    python scripts/load_price_gate.py --sql-out out.sql  # SQL 만 저장
    python scripts/load_price_gate.py                    # 적재
"""

import argparse
import csv
import io
import math
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_CSV = os.path.join(PROJECT_ROOT, "docs", "backtest", "통과구.csv")

REQUIRED_COLUMNS = ("sigungu_code", "sigungu_nm", "n_paired",
                    "ladder_mdape", "base_mdape", "gate_pass")
TRUE_WORDS = ("true", "t", "1", "yes")
FALSE_WORDS = ("false", "f", "0", "no")
BATCH_ROWS = 100
# 오차율이 이 값을 넘으면 비율이 아니라 퍼센트 값을 넣은 것으로 보고 거부한다
# (MdAPE 1,000% = 열 배 틀렸다는 뜻인데, 그런 성적표라면 넣을 게 아니라 다시 뽑아야 한다).
MAX_SANE_RATIO = 10.0


# ── 순수 함수 (파일·DB 없음 — 테스트 대상) ───────────────────────────────────


def sql_str(value):
    """SQL 문자열 리터럴. 작은따옴표는 두 번 써서 escape 한다."""
    if value is None or value == "":
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def sql_num(value):
    """숫자 리터럴. 없으면 null — 0 으로 바꾸면 '오차가 0'이라는 거짓말이 된다."""
    return "null" if value is None else repr(float(value))


def sql_bool(value):
    return "true" if value else "false"


def assert_required_columns(fieldnames):
    """머리글이 우리가 아는 그것인지 본다. 다르면 조용히 NULL 이 되지 않게 멈춘다.

    ⚠️ 이 CSV 는 `_write_csv` 가 utf-8-sig 로 쓴다(엑셀 대응). 첫 칸 이름 앞에 BOM 이
       붙으므로 벗겨 내지 않으면 sigungu_code 가 통째로 안 읽힌다.
    """
    have = [(f or "").strip().lstrip("﻿") for f in (fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in have]
    if missing:
        raise ValueError(
            "통과구 CSV 머리글에 {} 가 없습니다 (있는 것: {}). "
            "python scripts/backtest_price.py 로 다시 만드세요.".format(
                ", ".join(missing), ", ".join(have) or "(없음)"))
    return True


def parse_bool(text, where):
    s = (text or "").strip().lower()
    if s in TRUE_WORDS:
        return True
    if s in FALSE_WORDS:
        return False
    raise ValueError(
        "{}: gate_pass 가 {!r} 입니다. 참/거짓이라야 합니다 — 모호한 값이 들어가면 "
        "'통과가 아닌 구'가 통과로 읽힐 수 있습니다.".format(where, s[:20]))


def parse_ratio(text, where, field):
    """비율(0~1) 한 칸. 빈 값은 '잴 수 없었다' 이므로 None 이다."""
    s = (text or "").strip()
    if not s:
        return None
    try:
        value = float(s)
    except ValueError:
        raise ValueError("{}: {} 가 숫자가 아닙니다 ({!r}).".format(where, field, s[:20]))
    # float('nan')·float('inf') 는 파싱을 **통과한다.** 그대로 두면 nan 은 어떤 비교에도
    # 거짓이라 판정이 조용히 뒤집히고, SQL 로는 'nan'::numeric 이 들어가 버린다.
    if not math.isfinite(value):
        raise ValueError(
            "{}: {} 가 숫자가 아닌 특수값입니다 ({!r}). 성적표를 다시 뽑으세요."
            .format(where, field, s[:20]))
    if value < 0:
        raise ValueError("{}: {} 가 음수입니다 ({}). 오차율은 0 이상입니다."
                         .format(where, field, value))
    # 오차율은 비율(0.29 = 29%)이다. 퍼센트 값(29)을 그대로 넣은 CSV 를 못 알아채면
    # 판정 근거 칸이 조용히 거짓말을 한다(판정 자체는 assert_gate_matches_rule 이 지킨다).
    if value > MAX_SANE_RATIO:
        raise ValueError(
            "{}: {} 가 {} 입니다. 비율이 아니라 퍼센트 값을 넣은 것 같습니다 "
            "(0.29 = 29%).".format(where, field, value))
    if value > 1:
        print("경고: {} 의 {} 가 {} 입니다 — 오차율이 100% 를 넘습니다. "
              "퍼센트 값을 잘못 넣지 않았는지 확인하세요.".format(where, field, value),
              file=sys.stderr)
    return value


def record_to_row(rec, where):
    """CSV 한 줄 → 적재용 dict. 값 검사를 여기서 끝낸다."""
    code = (rec.get("sigungu_code") or "").strip()
    if len(code) != 5 or not code.isdigit():
        raise ValueError(
            "{}: sigungu_code 가 {!r} 입니다. 5자리 숫자라야 합니다 — 이 값이 곧 "
            "PNU 앞 5자리와 맞춰 보는 열쇠입니다.".format(where, code[:20]))
    n_paired = (rec.get("n_paired") or "").strip()
    if not n_paired.isdigit():
        raise ValueError("{}: n_paired 가 {!r} 입니다. 0 이상의 정수라야 합니다."
                         .format(where, n_paired[:20]))
    return {
        "sigungu_code": code,
        "sigungu_nm": (rec.get("sigungu_nm") or "").strip(),
        "n_paired": int(n_paired),
        "ladder_mdape": parse_ratio(rec.get("ladder_mdape"), where, "ladder_mdape"),
        "base_mdape": parse_ratio(rec.get("base_mdape"), where, "base_mdape"),
        "gate_pass": parse_bool(rec.get("gate_pass"), where),
    }


def assert_unique(rows):
    """같은 구가 두 번 나오면 멈춘다 — upsert 가 "cannot affect row a second time" 으로
    트랜잭션째 죽는데, 그 메시지만으로는 어느 구가 겹쳤는지 알 수 없다."""
    seen = {}
    for r in rows:
        seen[r["sigungu_code"]] = seen.get(r["sigungu_code"], 0) + 1
    dupes = sorted(k for k, v in seen.items() if v > 1)
    if dupes:
        raise ValueError("같은 sigungu_code 가 여러 번 나옵니다: {}.".format(", ".join(dupes)))
    return True


def assert_any_pass(rows):
    """관문 ② — 통과 구가 하나도 없으면 넣지 않는다.

    전부 false 인 표를 넣으면 화면에서 참고 시세가 **통째로** 사라지는데, 그건 정상적인
    판정 결과일 수도 있고 성적표가 깨져 나온 결과일 수도 있다. 둘을 구분하지 못한 채
    화면을 끄지는 않는다 — 사람이 보고 다시 부르게 한다.
    """
    if not any(r["gate_pass"] for r in rows):
        raise ValueError(
            "통과한 구가 한 곳도 없습니다. 이대로 넣으면 참고 시세가 전 지역에서 "
            "사라집니다 — 성적표(docs/backtest/성적표-v1.md)가 제대로 나왔는지 먼저 "
            "확인하세요.")
    return True


def assert_gate_matches_rule(rows):
    """★ CSV 의 gate_pass 칸을 믿지 않고 **기준선 규칙으로 다시 계산해** 대조한다.

    왜 필요한가: 이 파일은 사람이 엑셀로 열어 볼 수 있는 CSV 다. 판정 칸 한 글자만
    고치면 "통과한 적 없는 구"가 화면에 켜지는데, 그 구는 백테스트에서 구 평균에 졌던
    곳이라 **이미 있는 값보다 못한 추정**이 나간다(결정 0013 §2 의 금천구가 그 예다).
    판정의 정본은 언제나 `backtest_price.gate_pass()` 하나뿐이다.

    ⚠️ CI 는 이 경로를 안 탄다(적재는 사람이 로컬에서 돌린다). 그래서 테스트가 아니라
       적재기 자신이 막아야 한다.
    """
    import backtest_price  # noqa: PLC0415  (판정 정본. 늦은 import — dry-run 도 이 길을 탄다)

    bad = []
    for r in rows:
        want = backtest_price.gate_pass(r["ladder_mdape"], r["base_mdape"])
        if want != r["gate_pass"]:
            bad.append("{}({}) 적힌 값 {} / 규칙 {}".format(
                r["sigungu_nm"] or "?", r["sigungu_code"],
                sql_bool(r["gate_pass"]), sql_bool(want)))
    if bad:
        raise ValueError(
            "판정 칸이 기준선 규칙과 어긋납니다: {}. CSV 를 손으로 고치지 말고 "
            "python scripts/backtest_price.py 로 다시 뽑으세요(결정 0013 §4).".format(
                ", ".join(bad)))
    return True


def row_to_values_sql(row):
    return "({}, {}, {}, {}, {}, {})".format(
        sql_str(row["sigungu_code"]), sql_str(row["sigungu_nm"]),
        row["n_paired"], sql_num(row["ladder_mdape"]), sql_num(row["base_mdape"]),
        sql_bool(row["gate_pass"]))


def build_insert(chunk):
    """values 한 뭉치 → upsert 한 문장. loaded_at 은 갱신 시각이라 항상 다시 찍는다."""
    return (
        "insert into price_gate_sigungu "
        "(sigungu_code, sigungu_nm, n_paired, ladder_mdape, base_mdape, gate_pass)\n"
        "values\n{values}\n"
        "on conflict (sigungu_code) do update set "
        "sigungu_nm = excluded.sigungu_nm, "
        "n_paired = excluded.n_paired, "
        "ladder_mdape = excluded.ladder_mdape, "
        "base_mdape = excluded.base_mdape, "
        "gate_pass = excluded.gate_pass, "
        "loaded_at = now();"
    ).format(values=",\n".join(row_to_values_sql(r) for r in chunk))


def build_sigungu_gate(rows):
    """관문 ① — CSV 의 구 코드가 **실제로 열린 지역**인가.

    오타 하나(11680 → 11860)가 들어가면 그 구는 영원히 게이트에 안 걸려 참고 시세가
    조용히 안 나온다. 에러가 아니라 "그 동네는 표본이 없나 보다"로 보인다.
    열린 지역의 진실은 mv_open_sigungu 한 곳뿐이다(확정 설계 9).
    """
    codes = sorted({r["sigungu_code"] for r in rows})
    return (
        "do $$\n"
        "declare bad text;\n"
        "begin\n"
        "  select string_agg(x.code, ', ') into bad\n"
        "    from (values {values}) as x(code)\n"
        "   where not exists (select 1 from mv_open_sigungu o "
        "where o.sigungu_code = x.code);\n"
        "  if bad is not null then\n"
        "    raise exception '열린 지역 목록(mv_open_sigungu)에 없는 구 코드: % — "
        "이대로 넣으면 그 구는 게이트에 영원히 안 걸립니다(에러 없이 조용히)', bad;\n"
        "  end if;\n"
        "end $$;"
    ).format(values=", ".join("({})".format(sql_str(c)) for c in codes))


def build_pass_count_gate(rows):
    """관문 ③ — 넣은 뒤 DB 의 통과 구 수가 CSV 와 같은가.

    upsert 는 **없어진 구를 지우지 않는다.** 예전 판에서 통과였던 구가 이번 CSV 에서
    빠지면 DB 에는 true 인 채로 남고, 화면은 근거가 없어진 구에 계속 값을 낸다.
    그래서 수가 어긋나면 통째로 되돌린다 — 유령 통과 구는 조용한 오류 중 최악이다
    (결정 0013 §2 "금천구를 실수로 되살리지 말 것"이 가리키는 위험이 바로 이것).
    """
    want = sum(1 for r in rows if r["gate_pass"])
    return (
        "do $$\n"
        "declare got int;\n"
        "begin\n"
        "  select count(*) into got from price_gate_sigungu where gate_pass;\n"
        "  if got <> {want} then\n"
        "    raise exception 'DB 의 통과 구 수 % 가 CSV 의 {want} 와 다릅니다 — "
        "예전 판의 통과 구가 남아 있을 수 있습니다(upsert 는 사라진 구를 지우지 "
        "않습니다). 사라진 구를 손으로 지운 뒤 다시 넣으세요', got;\n"
        "  end if;\n"
        "end $$;"
    ).format(want=want)


def build_ghost_probe(rows):
    """CSV 에서 **사라진** 구를 세어 보여준다 (지우지는 않는다).

    왜 정보로만 두나: 사람이 일부러 뺀 것인지(그 구의 자료가 빠진 것) 이번 판에서
    실수로 빠진 것인지는 자료를 봐야 안다. 다만 그 유령이 **통과 구**라면 관문 ③ 이
    수를 세다가 먼저 멈춘다 — 위험한 유령만 막고 나머지는 알리기만 한다.
    """
    codes = sorted({r["sigungu_code"] for r in rows})
    return (
        'select count(*) as "CSV 에서 사라진 구(사람이 확인할 것 — 0 이면 그대로)"\n'
        "  from price_gate_sigungu g\n"
        " where g.sigungu_code not in ({values});"
    ).format(values=", ".join(sql_str(c) for c in codes))


def build_sql(rows, batch_rows=BATCH_ROWS):
    """전체 적재 SQL. 한 트랜잭션 — 중간에 걸리면 통째로 되돌린다.

    반쯤 들어간 게이트 표는 "어떤 구는 시세가 보이고 어떤 구는 안 보이는" 상태라,
    화면에서 보면 그냥 "표본이 없나 보다"로 보인다. 그래서 all-or-nothing 으로 간다.
    """
    if not rows:
        raise ValueError("넣을 판정이 없습니다.")
    assert_unique(rows)
    assert_gate_matches_rule(rows)
    assert_any_pass(rows)

    out = ["begin;", "set local statement_timeout = '120s';"]
    out.append(build_sigungu_gate(rows))
    for i in range(0, len(rows), batch_rows):
        out.append(build_insert(rows[i:i + batch_rows]))
    # 수 대조는 **넣은 뒤**라야 의미가 있다 — 표에 실제로 든 것을 센다.
    out.append(build_pass_count_gate(rows))
    out.append(build_ghost_probe(rows))
    out.append("commit;")
    return "\n".join(out) + "\n"


def summarize(rows):
    passed = [r for r in rows if r["gate_pass"]]
    by_sido = {}
    for r in passed:
        sido = r["sigungu_code"][:2]
        by_sido[sido] = by_sido.get(sido, 0) + 1
    return {"total": len(rows), "passed": passed, "by_sido": by_sido}


# ── 파일 읽기 ────────────────────────────────────────────────────────────────


def read_gate_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        assert_required_columns(reader.fieldnames)
        rows = [record_to_row(rec, "{}행".format(lineno))
                for lineno, rec in enumerate(reader, start=2)]
    if not rows:
        raise ValueError("통과구 CSV 에 판정이 한 건도 없습니다: {}".format(path))
    assert_unique(rows)
    return rows


def main(argv=None):
    # 한국어 콘솔(cp949)에서 em-dash(—) 하나 때문에 통째로 죽지 않게 한다. 그대로 두면
    # --dry-run 이 SQL 을 다 만들어 놓고도 종료코드 1 로 끝나 "CSV 가 잘못됐다"로
    # 오독된다(2026-08-14 적대검증 실환경 재현). 형제 스크립트들과 같은 처방이다.
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="통과구 CSV → price_gate_sigungu 적재")
    p.add_argument("--csv", default=DEFAULT_CSV)
    p.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않는다")
    p.add_argument("--sql-out", help="만들어진 SQL 을 이 파일로 저장(검토용)")
    a = p.parse_args(argv)

    print("=" * 70)
    print("price_gate_sigungu 적재 (결정 0013 — 참고 시세 출시 기준선)")
    print("=" * 70)
    print("  csv: {}".format(a.csv))

    try:
        rows = read_gate_csv(a.csv)
        sql = build_sql(rows)
    except (ValueError, OSError) as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1

    s = summarize(rows)
    print("  구 {:,}개 중 통과 {:,}개".format(s["total"], len(s["passed"])))
    for k, v in sorted(s["by_sido"].items()):
        print("    시도 {:<4} {:>3,}개".format(k, v))
    print("    {}".format(" · ".join(
        "{}({})".format(r["sigungu_nm"] or "?", r["sigungu_code"]) for r in s["passed"])))
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
