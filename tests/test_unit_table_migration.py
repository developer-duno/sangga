# -*- coding: utf-8 -*-
"""마이그레이션 2026-10-04b(호실 구성표 — 결정 0032 PR-U1)의 불변식을 지킨다.

여기서 막는 것은 **라이브에 붙이기 전에는 아무도 모르는** 실수다. DB 없이 SQL 글자만 본다.
이 판의 핵심 위험은 하나다 — **아파트 세대 목록·세대 면적이 공개 주소로 나가는 것**
(호실 줄의 73.39% 가 주용도 '공동주택' 건물 안이다).

  ⓐ 두 함수와 api 쌍둥이의 머리(`returns table`·`language sql`·`stable`·`security definer`·
     `set search_path`)·본문·`comment on function` 이 정본(schema.sql)과 글자 그대로 같은가.
     ⓘ 04b 뒤에 다시 만든 함수(RECREATED_LATER — list_floor_units 는 2026-10-05a 정렬)는 머리만 여기서
       대조하고, 본문·comment 의 정본 대조는 그 판의 시험(tests/test_unit_order_migration.py)이 맡는다.
       판정 블록·거르기·권한 시험은 계속 정본에도 돈다.
  ⓑ 층 종류 판정식(`kind` CTE)이 두 함수 본문에서 **글자 그대로 같은가** — 갈리면 요약은
     "세대 10"이라 적는데 목록은 그 층 세대를 내보내는 일이 생긴다. 판정식의 가지 순서와
     이름 목록을 SQL 에서 읽어 결정 0032 의 꼴(기타용도에만 오피스텔 · 공장 + 기타용도 기숙사 ·
     공동주택 건물의 부대시설뿐인 층 · 외국공관)에 돌려 본다.
  ⓒ 요약 함수가 commercial·mixed 가 아닌 층(주거·오피스텔·미상)의 면적 셋을 null 로 내는가.
  ⓓ 목록 함수가 commercial·mixed 가 아니면 0줄이고, 한 번에 최대 200줄인가.
  ⓔ 두 함수 본문 어디에도 pnu 로 거르는 조건이 없는가(같은 땅 옆 동 호실이 섞인다).
  ⓕ api 쌍둥이에만 anon·authenticated 로 grant(받는 롤까지) · public 원본은 revoke 만.
  ⓖ 마이그레이션에 표를 anon 쪽에 여는 grant 가 없고, 허용 목록에 표 unit 이 없는가.

⛔ 탐지는 이 파일 안의 작은 함수로 빼 두고, 가드 본체와 **양성 대조**(일부러 틀린 글)가 같은
   함수를 지나게 한다(레포 CLAUDE.md 2026-10-02 #190 — "없음" 단언만 있는 가드는 죽어도 초록이다).
   양성 대조에는 흔한 꼴과 변형 꼴을 함께 넣는다.
ⓘ 도우미는 형제 test_rent_floor_migration.py 에서 **복사**해 왔다 — import 하지 않는다(시험 파일끼리
   얽히면 한쪽의 고장이 다른 쪽을 조용히 가린다).
⚠️ 한계: 라이브에 적용됐는지·실제로 값이 오는지는 못 본다(CI 에 DB 가 없다). 그건 합친 뒤 공개키로
   두 api 함수를 실제로 불러 확인한다(결정 0032 PR-U1 #4).
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import post_load  # noqa: E402

MIGRATION = os.path.join(ROOT, "supabase", "migrations", "2026-10-04b_unit_table.sql")
SCHEMA = os.path.join(ROOT, "supabase", "schema.sql")

DOLLAR = re.escape(chr(36) * 2)

SUMMARY = "list_unit_floor_summary"
UNITS = "list_floor_units"
SIG = {SUMMARY: "text", UNITS: "text, int, int, int"}


def pub(name):
    """public 함수 이름 정규식 — 접두가 있어도 없어도 같은 함수다."""
    return r"(?:public\.)?" + name


def api(name):
    return r"api\." + name


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


@pytest.fixture(scope="module")
def migration():
    return read(MIGRATION)


@pytest.fixture(scope="module")
def schema():
    return read(SCHEMA)


# ── 탐지 함수 (본체와 양성 대조가 같은 함수를 지난다) ─────────────────────────


def statements(sql):
    """줄 전체 주석(`--` 로 시작하는 줄)을 걷은 실제 문장.

    ⛔ 원문을 보면 문장을 `--` 로 죽여도 글자가 남아 "있다"고 판정한다.
    """
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def code_only(text):
    """줄 끝 주석까지 걷는다(`--` 부터 줄 끝) · 블록 주석도 걷는다.

    ⚠️ 못 보는 것: 작은따옴표 글 안의 `--` 도 주석으로 보고 자른다(이 두 함수 본문에는 그런 글이
       없다).
    """
    text = re.sub(r"(?s)/\*.*?\*/", "", text)
    return "\n".join(re.sub(r"--.*$", "", ln) for ln in text.splitlines())


def flat(text):
    """공백을 한 칸으로 접는다(줄바꿈·들여쓰기 차이를 안 본다)."""
    return re.sub(r"\s+", " ", text).strip()


def function_head(sql, name_re):
    """`create [or replace] function <이름>(` 부터 `$$` 직전까지(머리). 없으면 None.

    줄머리(`^`)에 고정한다 — public 이름 정규식이 `api.<이름>` 의 뒤쪽을 집지 않게.
    """
    m = re.search(
        r"(?ims)^create\s+(?:or\s+replace\s+)?function\s+" + name_re + r"\s*\(.*?(?=" + DOLLAR + r")",
        statements(sql))
    return m.group(0) if m else None


def function_body(sql, name_re):
    """머리 뒤 `$$ … $$` 본문(주석 포함 원문). 없으면 None.

    ⓘ 줄 전체 주석은 걷은 뒤의 본문이다 — 판정식 경계 표시(`-- ▼`·`-- ▲`)는 원문에서 따로 본다
       (kind_block).
    """
    m = re.search(
        r"(?ims)^create\s+(?:or\s+replace\s+)?function\s+" + name_re + r"\s*\(.*?"
        + DOLLAR + r"(.*?)" + DOLLAR + r"\s*;",
        statements(sql))
    return m.group(1) if m else None


def raw_function_body(sql, name_re):
    """`$$ … $$` 본문 원문(줄 전체 주석도 그대로 — 라이브 pg_proc.prosrc 에 실리는 글자). 없으면 None."""
    m = re.search(
        r"(?ims)^create\s+(?:or\s+replace\s+)?function\s+" + name_re + r"\s*\(.*?"
        + DOLLAR + r"(.*?)" + DOLLAR + r"\s*;", sql)
    return m.group(1) if m else None


def function_comment(sql, name_re, sig):
    """`comment on function <이름>(<서명>) is '…';` 문장 전체. 없으면 None."""
    m = re.search(
        r"(?ims)^comment\s+on\s+function\s+" + name_re + r"\s*\(\s*" + re.escape(sig).replace(r"\ ", r"\s*")
        + r"\s*\)\s+is.*?';[ \t]*$",
        statements(sql))
    return m.group(0) if m else None


def kind_block(raw_body):
    """본문 원문에서 층 종류 판정 블록 — `kind as (` 줄부터 `-- ▲ 층 종류 판정 끝` 줄 **앞**까지.

    ⓘ 경계 표시 `-- ▼ …` 줄은 넣지 않는다(두 함수가 서로의 이름을 적어 글자가 다르다).
    ⚠️ 못 보는 것: 판정 블록 **밖**에서 floor_kind 를 다시 덮어쓰는 꼴(그건 ⓒ·ⓓ 탐지가 각자
       본다) · 경계 표시를 지우면 None(시험이 시끄럽게 빨강이 된다).
    """
    m = re.search(r"(?ms)^(\s*kind as \(\n.*?)^\s*-- ▲ 층 종류 판정 끝", raw_body or "")
    return m.group(1) if m else None


# ── 판정식 읽기 — SQL 에서 가지 순서·이름 목록을 읽어 꼴마다 돌린다 ───────────

# 판정식의 조건 글자 → 파이썬 판정. 여기 없는 조건이 SQL 에 나오면 KeyError 로 시끄럽게 빨강이다.
CONDITIONS = {
    "bf.n = 0": lambda c: c["n"] == 0,
    "bf.has_other and bf.has_counted_home_or_ot":
        lambda c: c["has_other"] and c["has_counted_home_or_ot"],
    "bf.has_other": lambda c: c["has_other"],
    "bf.has_officetel": lambda c: c["has_officetel"],
    "bf.has_home": lambda c: c["has_home"],
    "(select b.main_use from building b where b.bld_id = p_bld_id) = '공동주택'":
        lambda c: c["main_use"] == "공동주택",
    "fl.first_use ~ nm.officetel_re": lambda c: bool(c["first_use"]) and bool(re.search(c["ot_re"], c["first_use"])),
    "fl.first_use ~ nm.home_re": lambda c: bool(c["first_use"]) and bool(re.search(c["home_re"], c["first_use"])),
    "nullif(btrim(fl.first_use), '') is not null": lambda c: bool((c["first_use"] or "").strip()),
}

# 판정식이 쓰는 깃발 이름(SQL 의 `… as <이름>`).
FLAG_NAMES = ("has_home", "has_officetel", "has_other", "has_counted_home_or_ot")


def _hit(pat, s):
    return bool(re.search(pat, s or ""))


# 깃발식 글자(공백 접음) → 파이썬 계산 `(층별개요 줄들, home_re, officetel_re, skip_nm) → bool`.
# judge() 는 SQL 에서 **읽은 글자**로 여기를 찾는다 — CONDITIONS 와 같은 방식이다. 그래서
#   ① SQL 깃발식을 고치고 여기 열쇠를 안 고치면 KeyError 로 시끄럽게 빨강이고
#   ② 두 깃발의 식을 서로 바꿔 달면 파이썬도 바뀐 대로 계산해 꼴 시험이 빨강이 된다.
# ⚠️ 못 보는 것: 열쇠 글자만 SQL 과 함께 고치고 계산(lambda)은 옛 뜻 그대로 두는 꼴 — 글자와 계산이
#    한 줄에 붙어 있어 고치는 사람 눈에 띄게 둔 것이 방어선이다(CONDITIONS 와 같은 한계).
FLAG_IMPL = {
    "coalesce(bool_or(f.main_purps_nm ~ nm.home_re or coalesce(f.etc_purps, '') ~ nm.home_re), false)":
        lambda rows, home, ot, skip: any(_hit(home, m) or _hit(home, e) for m, e in rows),
    ("coalesce(bool_or(f.main_purps_nm ~ nm.officetel_re or coalesce(f.etc_purps, '') "
     "~ nm.officetel_re), false)"):
        lambda rows, home, ot, skip: any(_hit(ot, m) or _hit(ot, e) for m, e in rows),
    # 한 줄 = 한 갈래(결정 0032 :70-76) — 기타용도에 살림집·오피스텔 낱말이 있는 줄은 그 밖이 아니다.
    ("coalesce(bool_or(f.main_purps_nm !~ nm.home_re and f.main_purps_nm !~ nm.officetel_re "
     "and coalesce(f.etc_purps, '') !~ nm.home_re and coalesce(f.etc_purps, '') !~ nm.officetel_re "
     "and not (f.main_purps_nm = any (nm.skip_nm))), false)"):
        lambda rows, home, ot, skip: any(not _hit(home, m) and not _hit(ot, m)
                                         and not _hit(home, e) and not _hit(ot, e)
                                         and m not in skip for m, e in rows),
    # 섞임 판정 전용 — 치지 않는 것 줄은 없는 셈(결정 0032 :75). has_home·has_officetel 은 모든 줄 그대로.
    ("coalesce(bool_or(not (f.main_purps_nm = any (nm.skip_nm)) "
     "and (f.main_purps_nm ~ nm.home_re or f.main_purps_nm ~ nm.officetel_re "
     "or coalesce(f.etc_purps, '') ~ nm.home_re "
     "or coalesce(f.etc_purps, '') ~ nm.officetel_re)), false)"):
        lambda rows, home, ot, skip: any(m not in skip
                                         and (_hit(home, m) or _hit(ot, m) or _hit(home, e) or _hit(ot, e))
                                         for m, e in rows),
}
ROW_FILTER_SQL = ("where f.bld_id = p_bld_id and f.floor_no = fl.floor_no and not f.area_excluded "
                  "and nullif(btrim(f.main_purps_nm), '') is not null")


def parse_kind(block):
    """판정 블록 → {names, flags, row_filter, outer, inner}.

    outer·inner = [(조건 글자, 결과)] 차례대로 · 마지막 `else` 는 조건 None.
    ⚠️ 못 보는 것: 바깥 case 안에 안쪽 case 가 둘 이상인 꼴(지금은 `bf.n = 0` 가지 하나뿐) ·
       깃발 이름을 바꾼 꼴(FLAG_NAMES 로 찾다가 AttributeError — 시끄럽게 빨강).
    """
    code = flat(code_only(block))
    names = re.search(r"select '(.*?)'::text as home_re, '(.*?)'::text as officetel_re, "
                      r"array\[(.*?)\]::text\[\] as skip_nm", code)
    home_re, ot_re, skip = names.group(1), names.group(2), names.group(3)
    skip_nm = re.findall(r"'(.*?)'", skip)
    # ⓘ 깃발식 안에 다른 bool_or 가 끼지 않게 막는다 — 아니면 첫 깃발부터 길게 집는다.
    flags = {k: re.search(r"(coalesce\(bool_or\((?:(?!bool_or).)*?\), false\)) as " + k + r"\b", code).group(1)
             for k in FLAG_NAMES}
    row_filter = re.search(r"from building_floor f (where .*?) \) bf", code).group(1)
    case = re.search(r"select fl\.\*, case (.*) end as floor_kind", code).group(1)
    inner_m = re.search(r"when bf\.n = 0 then case (.*?) end ", case)
    inner_txt = inner_m.group(1)
    outer_txt = case.replace(inner_m.group(0), "when bf.n = 0 then 'FALLBACK' ")

    def branches(txt):
        out = []
        for part in re.split(r"\s*\bwhen\b\s*", " " + txt)[1:]:
            if " else " in part:
                part, other = part.split(" else ", 1)
                out.append(_branch(part))
                out.append((None, other.strip().strip("'")))
            else:
                out.append(_branch(part))
        return out

    return {"home_re": home_re, "ot_re": ot_re, "skip_nm": skip_nm, "flags": flags,
            "row_filter": row_filter, "outer": branches(outer_txt), "inner": branches(inner_txt)}


def _branch(part):
    cond, result = part.rsplit(" then ", 1)
    return cond.strip(), result.strip().strip("'")


def judge(parsed, rows, main_use=None, first_use=None):
    """층별개요 줄 [(주용도 이름, 기타용도)] → 층 종류 — SQL 에서 읽은 가지 순서·이름 목록 그대로.

    줄 거르기(연면적 제외분·빈 주용도)는 부르는 쪽이 이미 걸렀다고 본다(ROW_FILTER_SQL 대조로 SQL 쪽을 지킨다).
    """
    home, ot, skip = parsed["home_re"], parsed["ot_re"], parsed["skip_nm"]
    ctx = {"n": len(rows), "main_use": main_use, "first_use": first_use, "home_re": home, "ot_re": ot}
    # 깃발 계산은 SQL 에서 읽은 글자로 찾는다 — 모르는 글자면 KeyError(FLAG_IMPL 머리말).
    for name, sql in parsed["flags"].items():
        ctx[name] = FLAG_IMPL[sql](rows, home, ot, skip)

    def run(branches):
        for cond, result in branches:
            if cond is None or CONDITIONS[cond](ctx):
                return result
        return None

    out = run(parsed["outer"])
    return run(parsed["inner"]) if out == "FALLBACK" else out


def area_guards(body):
    """요약 함수 바깥 select 에서 면적 칸 셋이 각각 `case when <…>floor_kind in ('commercial', 'mixed')
    then … end as <칸>` 으로만 나가는가 → {칸: True/False}.

    잡는 것: 감싸개를 지운 꼴 · 허용 목록에 다른 종류(residential 등)를 넣은 꼴 · 같은 칸 이름이
    감싸개 없이 한 번 더 나가는 꼴(`as <칸>` 수와 감싼 수가 다르면 False).
    ⚠️ 못 보는 것: `fl` CTE 안의 같은 이름(그건 바깥으로 안 나간다 — 바깥 select 만 본다) ·
       칸 이름을 바꿔 내보내는 꼴(머리의 returns table 대조가 그 몫이다).
    """
    code = code_only(body or "")
    # 바깥 select = `from kind` 바로 앞의, 들여쓰기 두 칸 이하로 시작하는 마지막 select.
    end = re.search(r"(?i)\bfrom\s+kind\b", code)
    starts = [m.start() for m in re.finditer(r"(?im)^ {0,2}select\b", code[:end.start()])] if end else []
    outer = code[starts[-1]:end.start()] if starts else ""
    out = {}
    for col in ("median_area_m2", "min_area_m2", "max_area_m2"):
        guarded = re.findall(
            r"(?is)\bcase\s+when\s+(?:\w+\.)?floor_kind\s+in\s*\(\s*'commercial'\s*,\s*'mixed'\s*\)\s+then\s+"
            # ⓘ 감싸개 안이 다른 case·end 를 건너뛰지 못하게 막는다 — 아니면 옆 칸의 감싸개부터 집는다.
            r"(?:(?!\b(?:case|end)\b)[^;])*?\bend\s+as\s+" + col + r"\b", outer)
        named = re.findall(r"(?i)\bas\s+" + col + r"\b", outer)
        out[col] = bool(guarded) and len(guarded) == len(named)
    return out


def list_gates(body):
    """목록 함수 본문 → {'kind_gate', 'cap200', 'default50'}.

    kind_gate = 바깥 where 절이 **정확히** `where (?:별칭.)floor_kind in ('commercial', 'mixed')` 하나이고
    바로 뒤가 `order by` 다 — 그 사이에 다른 조건(`or …` · `and k.floor_kind <> 'mixed'` 등, 같은 줄이든
    다음 줄이든)이 끼면 False. 앞에 다른 조건을 둔 꼴(`where x and floor_kind in …`)도 False.
    cap200 = `least(p_limit, 200)` · default50 = `p_limit < 1 then 50`(빈 값도 50).
    ⚠️ 못 보는 것: 조건을 하위 질의 안에 두어 바깥 줄을 실제로 안 거르는 꼴 · limit 를 두 번 거는 꼴 ·
       join 조건(`on …`)에 거르기를 숨기는 꼴.
    """
    code = flat(code_only(body or ""))
    gate = re.search(r"(?i)\bwhere\s+(?:\w+\.)?floor_kind\s+in\s*\(\s*'commercial'\s*,\s*'mixed'\s*\)"
                     r"\s*order\s+by\b", code)
    return {
        "kind_gate": bool(gate),
        "cap200": bool(re.search(r"(?i)\blimit\s+case\s+when\s+p_limit\s+is\s+null\s+or\s+p_limit\s*<\s*1\s+then\s+50"
                                 r"\s+else\s+least\(\s*p_limit\s*,\s*200\s*\)\s+end\b", code)),
        "default50": bool(re.search(r"(?i)p_limit\s+is\s+null\s+or\s+p_limit\s*<\s*1\s+then\s+50\b", code)),
    }


def empty_ho_last(body):
    """목록 함수 본문 → 바깥 정렬이 빈 호 이름('')을 NULL 과 같이 맨 끝으로 보내는가.

    바깥 정렬 = `join kind` 뒤 첫 `order by` 부터 `limit` 직전까지. 그 안에
    `nullif(<별칭.>ho, '') [asc] nulls last` 가 있으면 True.
    ⓘ 이게 없으면 '' 는 숫자 없는 이름 묶음의 **맨 앞**에 선다(빈 글자가 가장 작은 글자라서) — 운영
       `unit.ho` 의 '' 는 0행(2026-10-04 실측)이라 지금은 해가 없지만, 적재가 바뀌면 조용히 맨 위로 온다.
    ⚠️ 못 보는 것: 다른 꼴로 같은 일을 하는 정렬(`ho = ''` 를 따로 거는 꼴 등 — 그땐 False 로 시끄럽다) ·
       nullif 를 바깥 정렬이 아닌 하위 질의 정렬 안에 둔 꼴.
    """
    code = flat(code_only(body or ""))
    m = re.search(r"(?i)\bjoin\s+kind\b.*?\border\s+by\b(.*?)\blimit\b", code)
    return bool(m) and bool(re.search(
        r"(?i)\bnullif\(\s*(?:\w+\.)?ho\s*,\s*''\s*\)\s*(?:asc\s+)?nulls\s+last\b", m.group(1)))


def pnu_filters(body):
    """본문(주석 걷음)에 pnu 낱말이 있으면 그 줄들(대소문자·따옴표 무관).

    ⚠️ 못 보는 것: 동적 SQL 로 이름을 이어 붙이는 꼴 · pnu 를 다른 함수 안에서 거르는 꼴.
    """
    return [ln.strip() for ln in code_only(body or "").splitlines() if re.search(r'(?i)(?<![\w])"?pnu"?(?![\w])', ln)]


def _grant_statements(sql):
    """주석(줄 전체·줄 끝·블록)을 걷은 뒤 `grant …;` 문장들(회수 `grant option for` 는 뺀다)."""
    return re.findall(r"(?is)(?<![\w.])grant\b(?!\s+option\s+for\b)[^;]*;", code_only(statements(sql)))


def _grantees(stmt):
    """`… to <롤>, <롤> [with grant option];` 의 받는 롤(소문자·정렬)."""
    m = re.search(r"(?is)\bto\s+(.*?)\s*(?:with\s+grant\s+option\s*)?;$", stmt.strip())
    if not m:
        return ()
    return tuple(sorted(r.strip().strip('"').lower() for r in m.group(1).split(",") if r.strip()))


def function_grants(sql):
    """`grant … on function <…두 함수>(…) to …;` → [(대상 이름, 받는 롤 묶음)].

    ⚠️ 못 보는 것: 인자 괄호 없는 꼴 · 따옴표 이름 · `on all functions in schema` · 한 grant 에 함수를
       여럿 쓴 꼴(첫 함수만 본다).
    """
    out = []
    for stmt in _grant_statements(sql):
        m = re.search(r"(?is)\bon\s+(?:function|routine)\s+((?:\w+\.)?(?:%s|%s))\s*\(" % (SUMMARY, UNITS), stmt)
        if m:
            out.append((m.group(1).lower(), _grantees(stmt)))
    return out


OPEN_ROLES = {"anon", "authenticated", "public"}


def table_open_grants(sql):
    """함수가 아닌 대상(표·뷰·스키마 통째)을 anon·authenticated·public 에 여는 grant 문장 목록.

    잡는 것: `grant select on unit to anon;` · `GRANT ALL ON TABLE public.unit TO service_role, PUBLIC;` ·
    `grant select on all tables in schema public to anon;` 처럼 대상·접두·대소문자와 무관하게.
    ⚠️ 못 보는 것: 동적 SQL · `alter default privileges`(기본 권한은 `post_load.py --check` 가 본다).
    """
    bad = []
    for stmt in _grant_statements(sql):
        if re.search(r"(?is)\bon\s+(?:function|routine)s?\b|\bon\s+all\s+(?:functions|routines)\b", stmt):
            continue
        if OPEN_ROLES & set(_grantees(stmt)):
            bad.append(flat(stmt))
    return bad


def order_problems(sql):
    """begin → 함수·comment·revoke·grant → commit → notify 순서. 어긴 것의 목록(빈 목록 = 통과)."""
    low = statements(sql).lower()
    bad = []
    begin = re.search(r"(?m)^begin\s*;", low)
    commit = re.search(r"(?m)^commit\s*;", low)
    notify = re.search(r"(?m)^notify\s+pgrst\b", low)
    if not begin or not commit:
        return ["`begin;`/`commit;` 이 없습니다"]
    ddl = [m.start() for m in re.finditer(r"(?m)^(?:create|comment on|revoke|grant|drop|alter)\b", low)]
    if not ddl:
        return ["DDL 을 못 찾았습니다"]
    if any(not (begin.start() < p < commit.start()) for p in ddl):
        bad.append("begin…commit 밖에 DDL 이 있습니다")
    if not notify:
        bad.append("`notify pgrst` 가 없습니다")
    elif notify.start() < commit.start():
        bad.append("`notify pgrst` 가 `commit;` 앞에 있습니다")
    if re.search(r"(?m)^drop\b", low):
        bad.append("drop 이 있습니다 — 이 판은 새로 만들기만 한다")
    return bad


# ── ⓐ 머리·본문·comment 글자 대조 ──────────────────────────────────────────────


NAMES = [(pub(SUMMARY), "public"), (api(SUMMARY), "api"), (pub(UNITS), "public"), (api(UNITS), "api")]

# 04b 뒤에 다른 마이그레이션이 다시 만든 함수 — 그 함수의 본문·comment 의 정본 대조는 그 판의 시험이 맡는다
# (04b 는 적용된 원장이라 고치지 않는다). 머리(returns table·서명·security definer·search_path)는 그대로라
# 여기서도 정본과 대조한다.
RECREATED_LATER = {
    pub(UNITS): "2026-10-05a — tests/test_unit_order_migration.py (호 목록 정렬)",
}


@pytest.mark.parametrize("name_re,kind", NAMES, ids=[n for n, _ in NAMES])
def test_function_head_and_body_match_the_schema(migration, schema, name_re, kind):
    mh, sh = function_head(migration, name_re), function_head(schema, name_re)
    assert mh is not None and sh is not None, "함수 머리를 못 찾았습니다 — 정규식이 헛돕니다"
    assert mh == sh, "마이그레이션의 함수 머리가 정본과 글자가 다릅니다"
    if name_re not in RECREATED_LATER:
        assert raw_function_body(migration, name_re) == raw_function_body(schema, name_re)
    low = mh.lower()
    assert "language sql" in low and "security definer" in low
    assert re.search(r"(?im)^stable\s*$", mh), "stable 한 줄이 없습니다"
    expected = "set search_path = public" if kind == "public" else "set search_path = ''"
    assert expected in low


@pytest.mark.parametrize("name", (SUMMARY, UNITS))
def test_api_twin_passes_everything_through(migration, name):
    body = flat(function_body(migration, api(name)))
    args = "p_bld_id" if name == SUMMARY else "p_bld_id, p_floor_no, p_limit, p_offset"
    assert body == "select * from public.{}({})".format(name, args)


@pytest.mark.parametrize("name", (SUMMARY, UNITS))
def test_public_comment_matches_the_schema(migration, schema, name):
    mc, sc = function_comment(migration, pub(name), SIG[name]), function_comment(schema, pub(name), SIG[name])
    assert mc is not None and sc is not None, "comment on function 을 못 찾았습니다"
    if pub(name) not in RECREATED_LATER:
        assert mc == sc, "마이그레이션의 comment 가 정본과 글자가 다릅니다"
    assert "결정 0032" in mc and "bld_id" in mc


def test_head_and_comment_detectors_catch_a_one_letter_change(migration):
    """양성 대조 — 흔한 꼴(search_path 한 글자) · 변형(security definer 빠짐 · comment 한 글자 · 죽인 줄)."""
    bad = migration.replace("set search_path = public", "set search_path = pub1ic", 1)
    assert function_head(bad, pub(SUMMARY)) != function_head(migration, pub(SUMMARY))
    no_definer = migration.replace("stable\nsecurity definer\nset search_path = public", "stable\nset search_path = public", 1)
    assert "security definer" not in function_head(no_definer, pub(SUMMARY)).lower()
    bad_c = migration.replace("결정 0032 호실 구성표 — 한 건물(bld_id)의 층마다", "결정 0032 호실 구성표 — 한 건물(bld_id)의 층머다", 1)
    assert function_comment(bad_c, pub(SUMMARY), SIG[SUMMARY]) != function_comment(migration, pub(SUMMARY), SIG[SUMMARY])
    dead = re.sub(r"(?m)^comment on function list_floor_units", "-- comment on function list_floor_units", migration)
    assert function_comment(dead, pub(UNITS), SIG[UNITS]) is None


def test_public_head_does_not_pick_the_api_twin():
    sql = ("create or replace function api.list_floor_units(p_bld_id text)\nreturns table (a text)\n"
           "language sql\nstable\nsecurity definer\nset search_path = ''\nas $$ select 1 $$;\n")
    assert function_head(sql, pub(UNITS)) is None
    assert function_head(sql, api(UNITS)) is not None


def test_the_returned_columns_are_the_contract(migration):
    """돌려주는 칸 — 결정 0032 의 표 그대로(화면 검증기가 칸 이름으로 고른다)."""
    s = flat(function_head(migration, pub(SUMMARY)))
    assert ("returns table ( floor_no smallint, unit_cnt int, median_area_m2 numeric, min_area_m2 numeric, "
            "max_area_m2 numeric, floor_kind text )") in s
    u = flat(function_head(migration, pub(UNITS)))
    assert "returns table ( ho text, excl_area_m2 numeric, total_cnt bigint )" in u
    assert "p_bld_id text, p_floor_no int, p_limit int default 50, p_offset int default 0" in u


# ── ⓑ 판정식이 두 함수에서 같은가 + 꼴마다 돌려 보기 ───────────────────────────


@pytest.mark.parametrize("which", ("migration", "schema"))
def test_the_kind_block_is_letter_for_letter_the_same(migration, schema, which):
    sql = migration if which == "migration" else schema
    a = kind_block(raw_function_body(sql, pub(SUMMARY)))
    b = kind_block(raw_function_body(sql, pub(UNITS)))
    assert a is not None and b is not None, "판정 블록을 못 찾았습니다 — 경계 표시가 사라졌나"
    assert a == b, "두 함수의 층 종류 판정식이 글자가 다릅니다"
    assert a.count("end as floor_kind") == 1


def test_kind_block_detector_sees_a_one_letter_change(migration):
    """양성 대조 — 흔한 꼴(한쪽 이름 목록 한 글자) · 변형(한쪽 가지 순서만 바꾼 꼴 · 경계 표시 지움)."""
    body_s = raw_function_body(migration, pub(SUMMARY))
    body_u = raw_function_body(migration, pub(UNITS))
    assert kind_block(body_s.replace("다세대", "다세데", 1)) != kind_block(body_u)
    swapped = body_u.replace(
        "             when bf.has_officetel then 'officetel'\n             when bf.has_home then 'residential'\n",
        "             when bf.has_home then 'residential'\n             when bf.has_officetel then 'officetel'\n", 1)
    assert swapped != body_u and kind_block(swapped) != kind_block(body_s)
    assert kind_block(body_s.replace("-- ▲ 층 종류 판정 끝", "-- 끝", 1)) is None


@pytest.fixture(scope="module")
def parsed(migration):
    return parse_kind(kind_block(raw_function_body(migration, pub(SUMMARY))))


def test_the_flag_expressions_are_what_the_python_mirror_assumes(parsed):
    """아래 꼴 시험의 파이썬 판정은 이 글자들을 대신 말한다 — 글자가 바뀌면 여기가 먼저 빨강이다."""
    assert set(parsed["flags"].values()) <= set(FLAG_IMPL), "FLAG_IMPL 에 없는 깃발식 — 파이썬 계산을 함께 고칠 것"
    assert parsed["row_filter"] == ROW_FILTER_SQL
    assert parsed["skip_nm"] == ["부대시설", "복리시설", "주차장"]
    assert parsed["ot_re"] == "오피스텔"
    words = parsed["home_re"].strip("()").split("|")
    assert words == ["아파트(?!형공장)", "공동주택", "다세대", "연립", "다가구", "단독주택", "다중주택", "기숙사",
                     "도시형생활", "주택(?!용?계단)", "(?<!비)주거(?!용?계단)", "^공관$"]
    # 가지 순서 — 결정 0032 「층 종류를 가르는 자」 표의 차례.
    assert [r for _, r in parsed["outer"]] == ["FALLBACK", "mixed", "commercial", "officetel", "residential",
                                               "residential", "commercial"]
    assert [r for _, r in parsed["inner"]] == ["officetel", "residential", "commercial", "unknown"]


@pytest.mark.parametrize("rows,main_use,first_use,expected", [
    # 신구로자이 2~4층 꼴 — 판매시설과 아파트가 한 층에
    ([("판매시설", None), ("공동주택", "아파트")], "공동주택", "판매시설", "mixed"),
    ([("제2종근린생활시설", "소매점")], "공동주택", "제2종근린생활시설", "commercial"),
    # 치지 않는 것뿐 — 공동주택 건물이면 주거, 아니면 목록 제공
    ([("부대시설", "관리사무소")], "공동주택", "부대시설", "residential"),
    ([("주차장", None), ("복리시설", "경로당")], "판매시설", "주차장", "commercial"),
    ([("오피스텔", None), ("부대시설", None)], "업무시설", "오피스텔", "officetel"),
    ([("공동주택", "아파트"), ("부대시설", None)], "공동주택", "공동주택", "residential"),
    # 한 줄 = 한 갈래 — 기타용도에만 오피스텔·기숙사가 적힌 한 줄뿐이면 그 갈래다(섞임 아님).
    #   검사관 실측: 1차 판정은 이 꼴 1,285층 · 14,633행을 섞임으로 보내 목록·면적이 나갔다.
    ([("업무시설", "오피스텔")], "업무시설", "업무시설", "officetel"),
    ([("공장", "기숙사")], "공장", "공장", "residential"),
    # 그 밖 줄이 따로 하나 더 있으면 섞인 층
    ([("업무시설", "오피스텔"), ("제2종근린생활시설", "사무소")], "업무시설", "업무시설", "mixed"),
    ([("공장", "기숙사"), ("공장", "제조업소")], "공장", "공장", "mixed"),
    # 살림집 이름 목록 경계(검사관 지적 2026-10-04)
    ([("공장", "아파트형공장")], "공장", "공장", "commercial"),
    ([("공장", "아파트형주택")], "공장", "공장", "residential"),
    ([("근린생활시설", "점포,주택")], "제1종근린생활시설", "근린생활시설", "residential"),
    ([("제2종근린생활시설", "사무소(비주거)")], "제2종근린생활시설", "제2종근린생활시설", "commercial"),
    ([("노유자시설", "노인복지주택")], "노유자시설", "노유자시설", "residential"),
    ([("업무시설", "사무실,주거시설")], "업무시설", "업무시설", "residential"),
    ([], "공동주택", "주택및점포", "residential"),
    # 치지 않는 것 줄은 섞임 판정에서 없는 셈(결정 0032 :75 · 재검사 실측 2026-10-04 — 67층이 이 줄 때문에만
    #   섞임이었다). 그 줄뿐인 층은 지금처럼 주거·오피스텔(목록이 새로 열리는 길을 만들지 않는다).
    ([("제2종근린생활시설", "소매점"), ("부대시설", "계단실,elev,복도(아파트)")], "공동주택",
     "제2종근린생활시설", "commercial"),
    ([("부대시설", "계단실,elev,복도(아파트)")], "공동주택", "부대시설", "residential"),
    ([("부대시설", "계단실,elev,복도(아파트)")], "업무시설", "부대시설", "residential"),
    ([("제2종근린생활시설", "소매점"), ("부대시설", "관리실(오피스텔)")], "업무시설",
     "제2종근린생활시설", "commercial"),
    ([("부대시설", "관리실(오피스텔)")], "업무시설", "부대시설", "officetel"),
    # 계단 이름 안의 주거·주택은 살림집이 아니다(재검사 실측 9층)
    ([("소매점", "주거계단실")], "제2종근린생활시설", "소매점", "commercial"),
    ([("제2종근린생활시설", "부동산중개사무소,주택계단실")], "공동주택", "제2종근린생활시설", "commercial"),
    # 생활편익시설은 '그 밖'(단지 안 상가) — ⛔ 주택 코드로 가르지 않는다
    ([("생활편익시설", None), ("공동주택", None)], "공동주택", "생활편익시설", "mixed"),
    ([("생활편익시설", None)], "공동주택", "생활편익시설", "commercial"),
    # '공관'은 이름 전체가 '공관'일 때만 살림집 — 외국공관·이공관은 그 밖
    ([("공관", None)], "단독주택", "공관", "residential"),
    ([("외국공관", None)], "업무시설", "외국공관", "commercial"),
    ([("교육연구시설", "이공관")], "교육연구시설", "교육연구시설", "commercial"),
    ([("단독주택", "공관")], "단독주택", "단독주택", "residential"),
    # 층별개요가 없는 층 → unit.floor_use 이름으로 · 그것도 비면 미상
    ([], "공동주택", "오피스텔", "officetel"),
    ([], "공동주택", "아파트", "residential"),
    ([], "공동주택", "소매점", "commercial"),
    ([], "공동주택", None, "unknown"),
    ([], "공동주택", "  ", "unknown"),
])
def test_the_kind_rule_on_the_decision_0032_shapes(parsed, rows, main_use, first_use, expected):
    assert judge(parsed, rows, main_use, first_use) == expected


# 운영 DB(PostgreSQL ARE)에서 SQL 의 home_re 를 이 글자들에 실제로 돌린 결과(2026-10-04 읽기 전용 실측).
# 위 판정 시험은 SQL 에서 읽은 정규식을 **파이썬 re** 로 돌리므로, 두 엔진이 이 꼴(앞보기·뒤보기 부정·
# 줄머리 고정)에서 같은 답을 내는지를 여기서 못 박는다 — 엔진이 갈리면 판정 시험이 헛통과한다.
PG_HOME_RE_TRUTH = {
    "아파트형공장": False, "아파트형주택": True, "아파트": True, "(비주거)": False, "사무소(비주거용)": False,
    "비주거(기타)": False, "사무실,주거시설": True, "주거겸용": True, "점포,주택": True, "노인복지주택": True,
    "외국공관": False, "공관": True, "업무시설": False,
    # 계단 이름 안의 주거·주택(재검사 실측 2026-10-04) — 계단 꼴 다섯은 빠지고 주택용대피소는 걸린다(알려진 한계)
    "주거계단실": False, "주택계단실": False, "주택용계단실": False, "주거용계단": False,
    "부동산중개사무소,주택계단실": False, "주택용대피소": True, "계단실,elev,복도(아파트)": True,
}


def test_python_re_agrees_with_postgres_on_the_home_names(parsed):
    got = {s: bool(re.search(parsed["home_re"], s)) for s in PG_HOME_RE_TRUTH}
    assert got == PG_HOME_RE_TRUTH


def test_parse_kind_fails_loudly_on_an_unknown_condition(parsed):
    """양성 대조 — SQL 에 파이썬이 모르는 조건이 생기면 조용히 넘어가지 않는다."""
    broken = dict(parsed)
    broken["outer"] = [("bf.has_home or true", "residential")] + parsed["outer"]
    with pytest.raises(KeyError):
        judge(broken, [("판매시설", None)])


def test_judge_fails_loudly_on_a_changed_flag_expression(parsed):
    """양성 대조 — 깃발식 글자를 바꾸면(예: '그 밖'에서 치지 않는 것 거르기를 지움) 파이썬이 옛 뜻으로
    조용히 계산하지 않는다. 예전엔 FLAG_SQL 표만 함께 고치면 계산은 옛 뜻 그대로 초록이었다."""
    broken = dict(parsed)
    broken["flags"] = dict(parsed["flags"])
    broken["flags"]["has_other"] = parsed["flags"]["has_other"].replace(
        " and not (f.main_purps_nm = any (nm.skip_nm))", "")
    assert broken["flags"]["has_other"] != parsed["flags"]["has_other"]
    with pytest.raises(KeyError):
        judge(broken, [("판매시설", None)])


def test_judge_follows_swapped_flag_expressions(parsed):
    """양성 대조 — 두 깃발의 식을 서로 바꿔 달면 파이썬도 바뀐 대로 계산한다(글자로 찾으므로).
    오피스텔 한 줄뿐인 층: 원래는 officetel, 식을 바꾸면 has_home 이 오피스텔을 보고 residential."""
    rows = [("오피스텔", None)]
    assert judge(parsed, rows, "업무시설", "오피스텔") == "officetel"
    swapped = dict(parsed)
    swapped["flags"] = dict(parsed["flags"])
    swapped["flags"]["has_home"], swapped["flags"]["has_officetel"] = (
        parsed["flags"]["has_officetel"], parsed["flags"]["has_home"])
    assert judge(swapped, rows, "업무시설", "오피스텔") == "residential"


# ── ⓒ 주거·오피스텔·미상 층은 면적 null ───────────────────────────────────────


@pytest.mark.parametrize("which", ("migration", "schema"))
def test_summary_hides_areas_outside_listable_floors(migration, schema, which):
    body = function_body(migration if which == "migration" else schema, pub(SUMMARY))
    assert area_guards(body) == {"median_area_m2": True, "min_area_m2": True, "max_area_m2": True}


def mutate(text, pattern, repl):
    """정규식으로 **딱 한 곳**을 바꾼다 — 공백·줄바꿈이 조금 달라도 같은 자리를 집고, 못 집으면
    (본문이 바뀌어 대조가 헛돌면) 이유를 적고 빨강이 된다(양성 대조가 글자 하나에 이유 없이 깨지지 않게)."""
    out, n = re.subn(pattern, repl, text, count=1)
    assert n == 1, "변이 자리를 못 찾았습니다 — 본문 모양이 바뀌었나: {!r}".format(pattern)
    return out


GUARD = r"case\s+when\s+k\.floor_kind\s+in\s*\(\s*'commercial'\s*,\s*'mixed'\s*\)\s+then\s+"


def test_area_guard_detector_catches_shapes(migration):
    """양성 대조 — 흔한 꼴(감싸개를 지움) · 변형(허용 종류에 residential 을 더함 · 대문자·별칭 없음)."""
    body = function_body(migration, pub(SUMMARY))
    unguarded = mutate(body, GUARD + r"(k\.median_area_m2)\s+end\s+as\s+median_area_m2", r"\1 as median_area_m2")
    assert area_guards(unguarded)["median_area_m2"] is False
    widened = mutate(body, GUARD + r"(k\.max_area_m2)",
                     r"case when k.floor_kind in ('commercial', 'mixed', 'residential') then \1")
    assert area_guards(widened)["max_area_m2"] is False
    upper = mutate(body, GUARD + r"(k\.min_area_m2)\s+end\s+as\s+min_area_m2",
                   r"CASE WHEN floor_kind IN ('commercial','mixed') THEN \1 END AS min_area_m2")
    assert area_guards(upper)["min_area_m2"] is True
    twice = mutate(body, r"(\s+)(k\.floor_kind\s+from\s+kind\b)", r"\1k.min_area_m2 as min_area_m2,\1\2")
    assert area_guards(twice)["min_area_m2"] is False


# ── ⓓ 목록은 commercial·mixed 층에서만 · 200 상한 ──────────────────────────────


@pytest.mark.parametrize("which", ("migration", "schema"))
def test_floor_units_gate_and_cap(migration, schema, which):
    body = function_body(migration if which == "migration" else schema, pub(UNITS))
    assert list_gates(body) == {"kind_gate": True, "cap200": True, "default50": True}


KIND_GATE = r"(where\s+k\.floor_kind\s+in\s*\(\s*'commercial'\s*,\s*'mixed'\s*\))"


@pytest.mark.parametrize("pattern,repl,key", [
    # 흔한 꼴 — 조건을 지움
    (r"\n\s*" + KIND_GATE + r"[ \t]*\n", "\n", "kind_gate"),
    # 변형 — 허용 종류를 넓힘 · or 로 우회
    (KIND_GATE, "where k.floor_kind in ('commercial', 'mixed', 'residential')", "kind_gate"),
    (KIND_GATE, r"\1 or true", "kind_gate"),
    # 변형 — 조건을 덧붙여 mixed 층 목록을 끊는다(같은 줄 · 다음 줄 — 검사관 A: 1차 가드는 둘 다 놓쳤다)
    (KIND_GATE, r"\1 and k.floor_kind <> 'mixed'", "kind_gate"),
    (KIND_GATE, "\\1\n    and k.floor_kind <> 'mixed'", "kind_gate"),
    # 변형 — 앞에 다른 조건
    (KIND_GATE, "where u.ho is not null and k.floor_kind in ('commercial', 'mixed')", "kind_gate"),
    (r"least\(\s*p_limit\s*,\s*200\s*\)", "least(p_limit, 2000)", "cap200"),
    (r"least\(\s*p_limit\s*,\s*200\s*\)", "p_limit", "cap200"),
    (r"p_limit\s*<\s*1\s+then\s+50\b", "p_limit < 1 then 5000", "default50"),
])
def test_list_gate_detector_catches_mutations(migration, pattern, repl, key):
    body = function_body(migration, pub(UNITS))
    assert list_gates(mutate(body, pattern, repl))[key] is False


@pytest.mark.parametrize("which", ("migration", "schema"))
def test_empty_ho_sorts_last_with_null(migration, schema, which):
    """빈 호 이름('')은 NULL 과 같이 목록 맨 끝(재검사 변이 M4 — `nullif` 를 되돌려도 86개가 통과했다)."""
    body = function_body(migration if which == "migration" else schema, pub(UNITS))
    assert empty_ho_last(body) is True


EMPTY_HO = r"nullif\(\s*u\.ho\s*,\s*''\s*\)\s+asc\s+nulls\s+last"


@pytest.mark.parametrize("repl,expected", [
    # 흔한 꼴 — nullif 를 되돌림('' 가 숫자 없는 이름 묶음의 맨 앞으로 간다)
    ("u.ho asc nulls last", False),
    # 변형 — 빈 값을 맨 앞으로 · 방향을 뒤집음
    ("nullif(u.ho, '') asc nulls first", False),
    ("nullif(u.ho, '') desc nulls last", False),
    # 변형 — 대문자 · 별칭 없음 · asc 생략은 같은 뜻
    ("NULLIF(ho,'') NULLS LAST", True),
])
def test_empty_ho_detector_catches_mutations(migration, repl, expected):
    body = function_body(migration, pub(UNITS))
    assert empty_ho_last(mutate(body, EMPTY_HO, repl)) is expected


# ── ⓔ pnu 로 거르지 않는다 ────────────────────────────────────────────────────


@pytest.mark.parametrize("which", ("migration", "schema"))
@pytest.mark.parametrize("name", (SUMMARY, UNITS))
def test_no_function_filters_by_pnu(migration, schema, which, name):
    body = function_body(migration if which == "migration" else schema, pub(name))
    assert body is not None
    assert pnu_filters(body) == []
    assert "un.bld_id = p_bld_id" in body


@pytest.mark.parametrize("bad", [
    "  where un.pnu = substr(p_bld_id, 1, 19)::char(19)",      # 흔한 꼴
    '  where u."PNU" = (select b.pnu from building b)',         # 변형: 따옴표·대문자
])
def test_pnu_detector_catches_shapes(bad):
    assert pnu_filters(bad), "탐지가 {!r} 를 놓쳤습니다".format(bad)


def test_pnu_detector_ignores_comments():
    assert pnu_filters("  -- ⛔ pnu 로 받지 않는다\n  select 1 /* pnu */") == []


# ── ⓕ 권한 — api 쌍둥이에만 anon·authenticated ───────────────────────────────


@pytest.mark.parametrize("which", ("migration", "schema"))
def test_only_the_api_twins_are_granted_to_exactly_anon_and_authenticated(migration, schema, which):
    sql = migration if which == "migration" else schema
    assert function_grants(sql) == [("api.list_unit_floor_summary", ("anon", "authenticated")),
                                    ("api.list_floor_units", ("anon", "authenticated"))]
    for name in (SUMMARY, UNITS):
        assert re.search(r"(?im)^revoke\s+all\s+on\s+function\s+" + name + r"\(" + re.escape(SIG[name])
                         + r"\)\s+from\s+public,\s*anon,\s*authenticated;", statements(sql))
        assert re.search(r"(?im)^revoke\s+all\s+on\s+function\s+api\." + name + r"\(" + re.escape(SIG[name])
                         + r"\)\s+from\s+public,\s*anon,\s*authenticated;", statements(sql))


@pytest.mark.parametrize("bad,expected", [
    # 흔한 꼴 — public 원본을 연다
    ("grant execute on function list_floor_units(text, int, int, int) to anon;", [("list_floor_units", ("anon",))]),
    # 변형 — 대문자·all·접두·여러 줄
    ("  GRANT ALL ON FUNCTION public.list_unit_floor_summary (text)\n    TO anon, authenticated;",
     [("public.list_unit_floor_summary", ("anon", "authenticated"))]),
    # 반대 방향 — api 쌍둥이에 public 롤을 더한다
    ("grant execute on function api.list_floor_units(text, int, int, int) to anon, authenticated, public;",
     [("api.list_floor_units", ("anon", "authenticated", "public"))]),
])
def test_function_grant_detector_sees_target_and_roles(bad, expected):
    assert function_grants(bad) == expected


# ── ⓖ 표를 여는 grant 가 없다 · 허용 목록에 unit 이 없다 ─────────────────────


def test_no_grant_opens_a_table(migration):
    assert table_open_grants(migration) == []


@pytest.mark.parametrize("bad", [
    "grant select on unit to anon;",                                        # 흔한 꼴
    "  GRANT ALL ON TABLE public.unit\n    TO service_role, PUBLIC;",       # 변형
    "grant select on all tables in schema public to authenticated;",
])
def test_table_open_grant_detector_catches_shapes(bad):
    assert table_open_grants(bad), "탐지가 {!r} 를 놓쳤습니다".format(bad)


def test_table_open_grant_detector_ignores_function_grants_and_comments():
    assert table_open_grants("grant execute on function api.list_floor_units(text, int, int, int) to anon;") == []
    assert table_open_grants("-- grant select on unit to anon;\n") == []
    assert table_open_grants("grant select on unit to service_role;") == []


def _bare(entries):
    return [e.rsplit(".", 1)[-1] for e in entries]


def test_the_allowlist_has_the_twins_and_never_the_unit_table():
    callable_bare = _bare(post_load.ANON_CALLABLE_ALLOWLIST)
    assert "api.list_unit_floor_summary" in post_load.ANON_CALLABLE_ALLOWLIST
    assert "api.list_floor_units" in post_load.ANON_CALLABLE_ALLOWLIST
    for forbidden in ("unit", "building_floor", "v_unit_current"):
        assert forbidden not in _bare(post_load.ANON_READABLE_ALLOWLIST)
        assert forbidden not in callable_bare
    # public 원본은 목록에 없다(스키마까지 본다).
    assert "public.list_unit_floor_summary" not in post_load.ANON_CALLABLE_ALLOWLIST
    assert "public.list_floor_units" not in post_load.ANON_CALLABLE_ALLOWLIST


def test_bare_name_helper_catches_a_qualified_forbidden_entry():
    """양성 대조 — 표를 목록이 실제로 쓰는 `스키마.이름` 꼴로 넣어도 잡힌다(흔한 꼴 + 변형 꼴)."""
    assert "unit" in _bare(("public.unit",))
    assert "unit" in _bare(("api.unit", "api.search_stores"))


# ── 순서 — begin … commit · notify 는 뒤 ──────────────────────────────────────


def test_the_migration_order_is_right(migration):
    assert order_problems(migration) == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda s: s.replace("\nbegin;\n", "\n", 1), "begin;`/`commit;` 이 없습니다"),
    (lambda s: s.replace("\nnotify pgrst, 'reload schema';", "", 1).replace(
        "\ncommit;\n", "\nnotify pgrst, 'reload schema';\ncommit;\n", 1), "commit;` 앞"),
    (lambda s: s.replace("\ncommit;\n", "\ncommit;\ngrant execute on function api.x(text) to anon;\n", 1),
     "밖에 DDL"),
])
def test_order_detector_catches_mutations(migration, mutate, expect):
    bad = mutate(migration)
    assert bad != migration, "변이가 적용되지 않았습니다 — 대조가 헛돕니다"
    assert any(expect in p for p in order_problems(bad)), order_problems(bad)
