"""⛔ 추적 파일에 **눈에 안 보이는 문자**가 없다 (2026-10-02 신설).

왜 이 시험이 필요한가
---------------------
편집 도구가 "백슬래시 + u + 16진수 네 자리"·"백슬래시 + b" 같은 이스케이프 표기를 **실제
문자**(BOM·줄 안 바꾸는 공백·백스페이스)로 바꿔 넣는 일이 이 레포에서 되풀이됐다.
화면에는 아무것도 안 보이고 린트도 초록인데 뜻이 달라진다. 가장 아팠던 것:

  · `tests/test_api_schema_migration.py` 의 정규식 — 단어 경계 일곱 자리에 **백스페이스
    문자**가 들어가, 한 달 동안 아무것도 못 잡는 시험이 초록으로 서 있었다(2026-09-03 #114 ~ 10-02).
  · 문서·메모리·PR 본문 일곱 곳에 이스케이프 표기 대신 실제 문자가 들어갔다(2026-10-01).

그래서 `git ls-files` 가 주는 추적 파일 전부를 훑어, 금지 문자가 하나라도 있으면 빨강이다.
의도해서 쓰는 자리는 **이스케이프 표기**(파이썬·JS 문자열)로 적거나, 정말 파일에 있어야 하면
아래 `ALLOWED` 표에 이유와 함께 올린다.

⛔ **조용히 빠지는 파일이 없다.** 추적 파일은 넷 중 하나다 — 훑었다 · 바이너리 표(`BINARY`)에
   있다 · 비-UTF-8 표(`NON_UTF8`)에 있다 · 작업 폴더에서 지워졌다. 표 밖에서 NUL 바이트가
   나오거나 UTF-8 로 안 풀리면 빨강이다(글 파일에 NUL 이 섞이거나 UTF-16 으로 저장되면
   예전에는 "바이너리"로 보고 통째로 건너뛰었다 — 2026-10-02 검사관 지적).

⛔ 이 파일 자신도 훑는 대상이다 — 금지 문자를 리터럴로 적으면 스스로 빨강이 된다.
   그래서 여기서는 금지 문자를 전부 `chr(코드값)` 으로 만들고, 백슬래시도 쓰지 않는다.
"""
import fnmatch
import os
import re
import subprocess
import sys
import unicodedata

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF = "tests/" + os.path.basename(__file__)

LF = chr(10)
CR = chr(13)
TAB = chr(9)
NUL_BYTE = bytes([0])

# ── 무엇이 금지인가 ─────────────────────────────────────────────────────────────
# 목록이 아니라 **유니코드 범주**로 정한다(목록은 빠뜨린 문자가 조용히 지나간다):
#   · Cf 전부 — BOM·폭 없는 공백·방향 제어·소프트 하이픈·폭 없는 이음표·태그 문자
#   · Cc 중 줄바꿈(LF)·CR·탭을 뺀 전부 — 백스페이스·NUL·폼 피드
#   · Zs 중 보통 공백(U+0020)을 뺀 전부 — 줄 안 바꾸는 공백·전각 공백
#   · Zl·Zp — U+2028·U+2029
# 범주로는 안 잡히는데(글자·기호·결합 부호) 화면에는 안 보이는 것은 따로 적는다:
#   · 한글 채움 문자 넷 — 범주는 글자(Lo)인데 빈칸으로 보인다
#   · U+034F(결합 자소 이음표) · U+2800(빈 점자 — 빈칸으로 보인다)
#   · 변형 선택자 U+FE00~U+FE0E · U+E0100~U+E01EF
#     ⛔ **U+FE0F 는 금지하지 않는다** — 이모지 모양 선택자라 이 레포 글에 천 번 넘게 쓰인다.
HANGUL_FILLERS = (0x115F, 0x1160, 0x3164, 0xFFA0)
PLAIN_CONTROLS = (0x09, 0x0A, 0x0D)
NOT_BY_CATEGORY = frozenset(
    list(HANGUL_FILLERS)
    + [0x034F, 0x2800]
    + list(range(0xFE00, 0xFE0F))
    + list(range(0xE0100, 0xE01F0))
)
TOP = sys.maxunicode + 1


def is_forbidden(cp):
    cat = unicodedata.category(chr(cp))
    if cat == "Cf":
        return True
    if cat == "Cc":
        return cp not in PLAIN_CONTROLS
    if cat == "Zs":
        return cp != 0x20
    return cat in ("Zl", "Zp") or cp in NOT_BY_CATEGORY


def build_pattern():
    """금지 문자 전부를 문자 클래스 하나로 — 1MB 넘는 파일도 정규식 한 번에 훑는다."""
    ranges = []
    for cp in range(TOP):
        if not is_forbidden(cp):
            continue
        if ranges and ranges[-1][1] == cp - 1:
            ranges[-1][1] = cp
        else:
            ranges.append([cp, cp])
    return re.compile("[" + "".join(chr(a) + "-" + chr(b) for a, b in ranges) + "]")


FORBIDDEN = build_pattern()


def find_invisible(text):
    """글 → `[(줄, 칸, 코드값)]`. 예외를 모르는 순수 함수(줄·칸은 1부터, 칸은 글자 단위)."""
    hits = []
    line, last = 1, 0
    for m in FORBIDDEN.finditer(text):
        pos = m.start()
        line += text.count(LF, last, pos)
        last = pos
        hits.append((line, pos - text.rfind(LF, 0, pos), ord(m.group())))
    return hits


# ── 허용 예외 (표 하나) ─────────────────────────────────────────────────────────
# (경로 무늬, 코드값, 위치 조건, 이유). 무늬의 `*` 는 폴더 구분자를 넘지 않는다.
# ⛔ 한 번도 안 쓰이는 줄이 있으면 시험이 빨강이다(낡은 예외를 남기지 않는다).
# ⓘ 위치 조건은 지금 **"파일 맨 앞"(file-start) 하나만** 지원한다. 다른 자리가 필요하면
#    `POSITIONS` 에 조건을 더하고 그 조건의 양성 대조를 함께 쓴다.
ALLOWED = (
    (
        "docs/backtest/*.csv",
        0xFEFF,
        "file-start",
        "backtest_price.py 가 utf-8-sig 로 쓴다 — 엑셀이 한글 헤더를 깨지 않게",
    ),
)
POSITIONS = {
    "file-start": lambda line, col: (line, col) == (1, 1),
}

# ── 바이너리 추적 파일 (명시 제외) ──────────────────────────────────────────────
# NUL 바이트가 든 파일은 글로 훑지 않는다. ⛔ **표에 있는 것만** 그렇게 넘어간다 —
# 표 밖에서 NUL 이 나오면 빨강(글 파일에 NUL 이 섞였거나 UTF-16 으로 저장된 것일 수 있다),
# 표에 있는데 사라졌거나 더는 NUL 이 없으면 그것도 빨강(표가 낡지 않게).
BINARY = (
    "budongsan-data.skill",
    "소상공인365 사용자매뉴얼_오픈 API 신청 및 활용.pdf",
)

# ── UTF-8 로 안 풀리는 추적 파일 (명시 제외) ────────────────────────────────────
# psql 출력을 그대로 받아 둔 기록이라 인코딩이 섞여 있다(2026-09-11 성능 조사).
# ⓘ NUL 바이트가 없는 바이너리 파일을 새로 추적에 넣을 때도 여기에 올린다(NUL 이 있으면 위 BINARY 표).
# ⛔ 표에 없는데 안 풀리면 빨강(새 비-UTF-8 글 파일이 조용히 빠지지 않게),
#    표에 있는데 사라졌거나 이제 풀리면 그것도 빨강(표가 낡지 않게).
NON_UTF8 = (
    "docs/perf/2026-09-11-plpgsql-prototype/bench_buildings.out.txt",
    "docs/perf/2026-09-11-plpgsql-prototype/bench_scope.out.txt",
    "docs/perf/2026-09-11-plpgsql-prototype/bench_stores.out.txt",
    "docs/perf/2026-09-11-plpgsql-prototype/bench_wrapper.out.txt",
    "docs/perf/2026-09-11-search-index-survey/inline/facts.txt",
)

HOW_TO_FIX = (
    "고치는 법 — 파이썬·JS 문자열 안이면 이스케이프 표기로 바꾸세요(도구가 이스케이프를 실제 "
    "문자로 바꿔 넣었을 수 있습니다). md·sql·yml·json·css 처럼 이스케이프가 통하지 않는 글이면 "
    "보통 공백으로 바꾸거나 지우세요. 정말 파일에 있어야 하는 문자면 이 시험의 ALLOWED 표에 "
    "이유와 함께 올립니다(위치 조건은 지금 '파일 맨 앞'만 지원합니다)."
)


def path_matches(rel, pattern):
    a, b = rel.split("/"), pattern.split("/")
    return len(a) == len(b) and all(fnmatch.fnmatchcase(x, y) for x, y in zip(a, b))


def apply_allowed(rel, hits):
    """걸린 목록에서 허용 예외를 뺀다 → `(남은 목록, 쓰인 예외 번호 집합)`."""
    left, used = [], set()
    for line, col, cp in hits:
        for i, (pattern, allowed_cp, where, _why) in enumerate(ALLOWED):
            if cp == allowed_cp and path_matches(rel, pattern) and POSITIONS[where](line, col):
                used.add(i)
                break
        else:
            left.append((line, col, cp))
    return left, used


def format_hit(rel, line, col, cp):
    name = unicodedata.name(chr(cp), "(이름 없는 제어 문자)")
    return "{}:{}:{} U+{:04X} {}".format(rel, line, col, cp, name)


def scan_files(root, files):
    """(루트, 파일 목록) → 훑은 결과. 표(`BINARY`·`NON_UTF8`)는 모른다 — **본 대로만** 가른다.

    파일마다 넷 중 하나로 간다: `missing`(작업 폴더에 없다) · `binary`(NUL 바이트가 있다) ·
    `non_utf8`(UTF-8 로 안 풀린다) · `scanned`(글로 훑었다). 어디에도 안 들어가는 파일은 없다.
    """
    result = {"scanned": [], "binary": [], "non_utf8": [], "missing": [], "hits": [], "used": set()}
    for rel in files:
        path = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(path):
            result["missing"].append(rel)
            continue
        with open(path, "rb") as f:
            raw = f.read()
        if NUL_BYTE in raw:
            result["binary"].append(rel)
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            result["non_utf8"].append(rel)
            continue
        result["scanned"].append(rel)
        left, used = apply_allowed(rel, find_invisible(text))
        result["hits"].extend((rel, line, col, cp) for line, col, cp in left)
        result["used"] |= used
    return result


def table_drift(found, table):
    """본 것과 표를 견준다 → `(표에 없는데 본 것, 표에 있는데 못 본 것)`."""
    return sorted(set(found) - set(table)), sorted(set(table) - set(found))


def run_git(args):
    """⛔ git 을 못 부르면 건너뛰지 않고 **실패**다(CI 에도 git 이 있다)."""
    cmd = ["git", "-c", "core.quotepath=false"] + args
    try:
        done = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        pytest.fail("git 을 부르지 못했습니다(이 시험은 건너뛰지 않습니다): {!r}".format(e))
    if done.returncode != 0:
        pytest.fail(
            "git {} 가 실패했습니다(종료코드 {}): {}".format(
                " ".join(args), done.returncode, done.stderr.decode("utf-8", "replace").strip()
            )
        )
    return done.stdout.decode("utf-8")


def tracked_files():
    """`git ls-files -z` 가 주는 추적 파일(한글 이름이 있어 NUL 로 끊어 받는다)."""
    files = [f for f in run_git(["ls-files", "-z"]).split(chr(0)) if f]
    if not files:
        pytest.fail("git ls-files 가 빈 목록을 줬습니다 — 훑을 파일이 없으면 초록이 아니라 실패입니다.")
    return files


@pytest.fixture(scope="module")
def scan():
    """추적 파일 전부를 한 번 훑은 결과."""
    return scan_files(ROOT, tracked_files())


# ══ 레포 전체 ════════════════════════════════════════════════════════════════════


def test_no_invisible_chars_in_tracked_files(scan):
    """⛔ 추적 중인 글 파일 어디에도 눈에 안 보이는 문자가 없다."""
    hits = scan["hits"]
    shown = [format_hit(*h) for h in hits[:50]]
    if len(hits) > len(shown):
        shown.append("… 외 {}곳".format(len(hits) - len(shown)))
    assert not hits, "눈에 안 보이는 문자 {}곳:{}{}{}{}".format(
        len(hits), LF, LF.join("  " + s for s in shown), LF, HOW_TO_FIX
    )


def test_binary_table_matches_reality(scan):
    """⛔ NUL 바이트가 든 파일은 표에 적힌 것뿐이고, 표의 줄은 전부 지금도 그렇다."""
    unlisted, stale = table_drift(scan["binary"], BINARY)
    assert not unlisted, (
        "표에 없는 추적 파일에 NUL 바이트가 있습니다 — 이 시험이 그 파일을 못 훑습니다. 글 파일이면 "
        "NUL 을 지우거나 UTF-8 로 다시 저장하세요(PowerShell 5.1 의 `>` 는 UTF-16 으로 씁니다). "
        "진짜 바이너리면 BINARY 표에 올리세요: {}".format(unlisted)
    )
    assert not stale, (
        "BINARY 표의 줄이 낡았습니다(파일이 사라졌거나 더는 NUL 바이트가 없습니다) — "
        "표에서 지우세요: {}".format(stale)
    )


def test_non_utf8_table_matches_reality(scan):
    """UTF-8 로 안 풀리는 파일은 표에 적힌 것뿐이고, 표의 줄은 전부 지금도 그렇다."""
    unlisted, stale = table_drift(scan["non_utf8"], NON_UTF8)
    assert not unlisted, (
        "UTF-8 로 안 풀리는 추적 파일이 새로 생겼습니다 — 이 시험이 못 훑습니다. UTF-8 로 "
        "저장하거나(권장) NON_UTF8 표에 올리세요: {}".format(unlisted)
    )
    assert not stale, (
        "NON_UTF8 표의 줄이 낡았습니다(파일이 사라졌거나 이제 UTF-8 로 풀립니다) — "
        "표에서 지우세요: {}".format(stale)
    )


def test_every_allowed_entry_is_used(scan):
    """허용 예외 표에 쓰이지 않는 줄이 없다 — 낡은 예외는 다음 사고의 구멍이다."""
    unused = [ALLOWED[i] for i in range(len(ALLOWED)) if i not in scan["used"]]
    assert not unused, "한 번도 안 쓰인 허용 예외입니다 — 표에서 지우세요: {}".format(unused)


def test_everything_outside_the_tables_was_scanned(scan):
    """⛔ **훑은 집합 = 추적 − 바이너리 표 − 비-UTF-8 표 − 작업 폴더에서 지워진 것.**

    훑는 쪽이 폴더 하나를 빼먹어도(또는 대표 파일 몇 개만 훑어도) 걸린 것이 없으니 초록이다.
    그래서 목록을 **따로 한 번 더** 받아(줄 단위 — 훑는 쪽은 NUL 로 끊어 받는다) 견준다.
    """
    listing = [ln for ln in run_git(["ls-files"]).splitlines() if ln]
    on_disk = {rel for rel in listing if os.path.isfile(os.path.join(ROOT, *rel.split("/")))}
    expected = on_disk - set(BINARY) - set(NON_UTF8)
    scanned = scan["scanned"]
    assert len(scanned) == len(set(scanned)), "같은 파일을 두 번 훑었습니다."
    not_scanned, extra = table_drift(expected, scanned)
    assert not not_scanned, "훑지 않은 추적 파일 {}개: {}".format(len(not_scanned), not_scanned[:20])
    assert not extra, "목록에 없는 파일을 훑었습니다: {}".format(extra[:20])


@pytest.mark.parametrize(
    "rel",
    [
        SELF,
        "supabase/schema.sql",
        "src/App.tsx",
        "docs/알려진한계.md",
        "public/districts.geojson",
        "scripts/post_load.py",
        ".github/workflows/ci.yml",
    ],
)
def test_the_scan_really_looked(scan, rel):
    """⛔ 목록 자체가 비거나 좁아져 초록이 되는 것을 막는다 — 이 파일 자신과, 종류가 다른
    대표 파일(sql·tsx·한글 이름 md·1MB 넘는 geojson·scripts·워크플로)이 실제로 훑은 목록에 있다.

    ⓘ scripts 와 워크플로를 따로 넣은 까닭(2026-10-02 재검사): 위 "훑은 집합" 시험은 견주는
       목록도 같은 git 호출 함수로 받는다. 그 함수가 폴더 하나를 빼게 바뀌면 양쪽이 똑같이
       좁아져 초록이다 — 그 한 자리는 이 대표 파일들이 막는다."""
    assert rel in scan["scanned"], "{} 를 훑지 않았습니다(훑은 파일 {}개).".format(
        rel, len(scan["scanned"])
    )


# ══ 양성 대조 — 훑는 함수가 실제로 잡는가 ════════════════════════════════════════

FORBIDDEN_SAMPLES = {
    "bom": 0xFEFF,
    "no-break-space": 0x00A0,
    "backspace": 0x0008,
    "zero-width-space": 0x200B,
    "zero-width-joiner": 0x200D,
    "word-joiner": 0x2060,
    "soft-hyphen": 0x00AD,
    "right-to-left-override": 0x202E,
    "line-separator": 0x2028,
    "paragraph-separator": 0x2029,
    "ideographic-space": 0x3000,
    "narrow-no-break-space": 0x202F,
    "en-quad": 0x2000,
    "hangul-filler": 0x3164,
    "hangul-choseong-filler": 0x115F,
    "hangul-jungseong-filler": 0x1160,
    "halfwidth-hangul-filler": 0xFFA0,
    "nul": 0x0000,
    "form-feed": 0x000C,
    "delete": 0x007F,
    "next-line": 0x0085,
    "combining-grapheme-joiner": 0x034F,
    "braille-blank": 0x2800,
    "variation-selector-1": 0xFE00,
    "variation-selector-15": 0xFE0E,
    # 기본 평면 밖 — 정규식을 기본 평면까지만 조립하면 여기가 빠진다
    "language-tag": 0xE0001,
    "variation-selector-17": 0xE0100,
    "variation-selector-256": 0xE01EF,
}


@pytest.mark.parametrize("kind", sorted(FORBIDDEN_SAMPLES))
def test_each_forbidden_kind_is_caught(kind):
    cp = FORBIDDEN_SAMPLES[kind]
    text = "ab" + LF + "c" + chr(cp) + "d" + LF
    assert find_invisible(text) == [(2, 2, cp)]


def test_ordinary_text_is_not_caught():
    """보통 공백·탭·CR·LF·한글·이모지·가운뎃점·줄표는 안 걸린다(거짓 빨간불 방지)."""
    warning_sign = chr(0x26A0) + chr(0xFE0F)  # ⛔ 이모지 모양 선택자(U+FE0F)는 금지가 아니다
    text = (
        "plain space" + TAB + "tab" + CR + LF
        + "한글 가나다 · 가운뎃점 — 줄표 … 말줄임 → 화살표 ★ ① ㎡" + LF
        + chr(0x26D4) + " " + warning_sign + " " + chr(0x1F4BE) + " " + chr(0x1F464) + LF
        + chr(0x2801) + chr(0x0301) + chr(0xE01F0) + LF  # 금지 구간 바로 옆(점자 1점·결합 부호)
    )
    assert find_invisible(text) == []


def test_line_and_column_are_counted_in_characters():
    """줄·칸은 1부터, 칸은 바이트가 아니라 글자 단위. CRLF 파일에서도 줄이 맞는다."""
    nbsp, zwsp = chr(0x00A0), chr(0x200B)
    text = "가나" + CR + LF + nbsp + "다" + zwsp + CR + LF + CR + LF + "라" + nbsp
    assert find_invisible(text) == [(2, 1, 0x00A0), (2, 3, 0x200B), (4, 2, 0x00A0)]


def test_pattern_agrees_with_the_rule():
    """문자 클래스를 잘못 조립하면 규칙과 정규식이 조용히 갈린다 — **유니코드 끝까지** 대조한다."""
    top = sys.maxunicode + 1
    caught = {ord(ch) for ch in FORBIDDEN.findall("".join(map(chr, range(top))))}
    expected = {cp for cp in range(top) if is_forbidden(cp)}
    assert caught == expected
    assert max(caught) > 0xFFFF, "기본 평면 밖(태그 문자·변형 선택자)이 정규식에 없습니다."
    assert not FORBIDDEN.search("]^-" + chr(0x5C) + " az")


def test_hit_is_reported_as_path_line_col_codepoint_name():
    assert format_hit("a/b.py", 3, 7, 0xFEFF) == "a/b.py:3:7 U+FEFF ZERO WIDTH NO-BREAK SPACE"
    assert format_hit("a/b.py", 1, 1, 0x00A0) == "a/b.py:1:1 U+00A0 NO-BREAK SPACE"
    assert format_hit("a/b.py", 1, 1, 0x0008) == "a/b.py:1:1 U+0008 (이름 없는 제어 문자)"
    assert format_hit("a/b.py", 1, 1, 0xE0001) == "a/b.py:1:1 U+E0001 LANGUAGE TAG"


# ══ 양성 대조 — 훑기 연결부(파일 → 분류 → 걸린 목록) ═════════════════════════════


def test_scan_files_sorts_every_file_and_records_what_it_caught(tmp_path):
    """⛔ 걸린 것을 기록하는 줄이 빠지거나 폴더 하나를 건너뛰어도 레포 시험은 초록이다
    (레포에는 걸릴 것이 없으니까). 그래서 걸릴 것이 든 작은 폴더를 직접 만들어 훑는다."""
    zwsp, bom = chr(0x200B), chr(0xFEFF)
    made = {
        "src/dirty.ts": ("const a = 1;" + LF + "const b" + zwsp + " = 2;" + LF).encode("utf-8"),
        "scripts/deep/bom.py": (bom + "x = 1" + LF).encode("utf-8"),
        "docs/clean.md": ("# 제목" + CR + LF + "보통 글 · 가운뎃점" + CR + LF).encode("utf-8"),
        "docs/backtest/ok.csv": (bom + "a,b" + CR + LF).encode("utf-8"),
        # NUL 이 든 것 셋: 진짜 바이너리 · UTF-16 으로 저장된 글 · NUL 이 섞인 글
        "tool.skill": b"PK" + bytes([3, 4, 0, 0, 8, 0]),
        "docs/utf16.md": ("# title" + LF).encode("utf-16"),
        "src/with_nul.ts": ("const a = 1;" + chr(0) + zwsp + LF).encode("utf-8"),
        # UTF-8 로 안 풀리는 글(cp949 조각)
        "docs/mixed.txt": b"ok " + bytes([0xB0, 0xB3]) + b" x",
    }
    for rel, data in made.items():
        path = tmp_path.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    got = scan_files(str(tmp_path), sorted(made) + ["gone/deleted.py"])

    assert got == {
        "scanned": ["docs/backtest/ok.csv", "docs/clean.md", "scripts/deep/bom.py", "src/dirty.ts"],
        "binary": ["docs/utf16.md", "src/with_nul.ts", "tool.skill"],
        "non_utf8": ["docs/mixed.txt"],
        "missing": ["gone/deleted.py"],
        "hits": [("scripts/deep/bom.py", 1, 1, 0xFEFF), ("src/dirty.ts", 2, 8, 0x200B)],
        "used": {0},
    }


def test_table_drift_reports_both_directions():
    """표 밖에서 본 것(새로 생김)과 표에만 있는 것(낡음)을 **둘 다** 돌려준다."""
    assert table_drift(["b", "a", "x"], ("b", "c")) == (["a", "x"], ["c"])
    assert table_drift(["b", "c"], ("c", "b")) == ([], [])
    assert table_drift([], ("c",)) == ([], ["c"])
    assert table_drift(["a"], ()) == (["a"], [])


# ══ 예외 규칙 ════════════════════════════════════════════════════════════════════

BOM = chr(0xFEFF)


def test_bom_at_the_very_start_of_a_backtest_csv_is_allowed():
    hits = find_invisible(BOM + "a,b" + CR + LF + "1,2" + CR + LF)
    assert hits == [(1, 1, 0xFEFF)]
    assert apply_allowed("docs/backtest/통과구.csv", hits) == ([], {0})


def test_bom_in_the_middle_of_a_backtest_csv_is_caught():
    hits = find_invisible(BOM + "a,b" + LF + BOM + "1,2" + LF)
    assert apply_allowed("docs/backtest/통과구.csv", hits) == ([(2, 1, 0xFEFF)], {0})
    # 맨 앞에 둘이 겹쳐 있으면 둘째는 잡는다
    hits = find_invisible(BOM + BOM + "a,b" + LF)
    assert apply_allowed("docs/backtest/통과구.csv", hits) == ([(1, 2, 0xFEFF)], {0})


@pytest.mark.parametrize(
    "rel",
    [
        "scripts/backtest_price.py",
        "docs/backtest/성적표-v1.md",
        "docs/backtest/sub/x.csv",
        "docs/x.csv",
        "public/x.csv",
        "x/docs/backtest/x.csv",
    ],
)
def test_bom_at_the_start_of_any_other_file_is_caught(rel):
    hits = find_invisible(BOM + "a,b" + LF)
    assert apply_allowed(rel, hits) == ([(1, 1, 0xFEFF)], set())


def test_another_invisible_char_at_the_start_of_a_backtest_csv_is_caught():
    hits = find_invisible(chr(0x00A0) + "a,b" + LF)
    assert apply_allowed("docs/backtest/통과구.csv", hits) == ([(1, 1, 0x00A0)], set())
