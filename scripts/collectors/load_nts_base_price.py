# -*- coding: utf-8 -*-
"""국세청 "상업용건물·오피스텔 기준시가" zip → `nts_base_price` 적재 (전국 한 방, 한 트랜잭션).

무엇을 넣나
-----------
국세청이 해마다 1월 1일자로 고시하는 **㎡당 기준시가**를 호실 하나에 한 줄씩 넣는다
(2026년 판 실측 2,490,451행 · 전국 17개 시도). 원본은 공공데이터포털 3036455 의 zip 이고,
그 안에 법정동코드 사전 CSV 와 시트 5장짜리 xlsx 가 들어 있다.

⛔ **세금을 매길 때 쓰는 과세표준이지, 시장에서 사고파는 값이 아니다** — 화면에서도
   "국세청 고시 기준시가"라는 이름 그대로 쓴다(절대 규칙 2).

왜 psql(\\copy) 경유인가 (REST 가 아니라)
-----------------------------------------
249만 행이다. PostgREST 로 넣으면 배치 수천 번이 오가고, 중간에 끊기면 **반쯤 들어간 표**가
남는다. `\\copy` 는 한 연결 안에서 한 트랜잭션으로 끝나므로 실패하면 통째로 되돌아간다.
검증 관문도 DB 안에서 걸 수 있다("이 법정동코드가 실재하는가"는 서버만 안다).

⚠️ 검증 관문은 **raise exception 이라야** 한다
-----------------------------------------------
psql 은 select 가 몇 줄을 돌려주든 종료코드 0 이다. "0이어야 정상"이라고 적어 둬도 그대로
commit 된다. do 블록에서 예외를 던져야 ON_ERROR_STOP 이 걸린다(load_price_gate.py 와 같은 이유).

⚠️ zip 안 파일 이름이 깨져 보인다
---------------------------------
이 zip 은 이름을 cp949 로 적어 두고 "UTF-8 이다"라는 표시를 안 달았다(flag bit 11 = 0).
그래서 파이썬은 규격대로 cp437 로 읽어 `'╗≤╛≈...'` 같은 글자를 준다. 되돌리려면
`name.encode('cp437').decode('cp949')` 를 거쳐야 한다 — 안 거치면 "xlsx 가 없다"고 오판한다.

단위 검증 (추측 없이 실측으로 확정)
------------------------------------
`고시가격`이 ㎡당인지 총액인지 원본 어디에도 안 적혀 있다. 전 행 분포로 갈랐다:
  · 고시가격          중앙값 1,890,000원 (최소 5,000 · 최대 54,600,000)
  · 가격 × (전용+공유) 중앙값 1억 안팎
총액이라면 상가 한 칸이 189만원이라는 뜻이라 말이 안 된다 ⇒ **㎡당 단가**. 이 판정을 기억에
맡기지 않고, 적재할 때마다 중앙값이 상식 범위를 벗어나면 멈추게 해 둔다(관문 ④).

쓰는 법
-------
    python scripts/collectors/load_nts_base_price.py --dry-run    # DB 쓰기 0
    python scripts/collectors/load_nts_base_price.py --dry-run --limit 50000   # 빠른 점검
    python scripts/collectors/load_nts_base_price.py              # 적재 (한 트랜잭션)

⚙️ 연 1회 수동 갱신이다. 새 고시분을 받으면 zip 을 data/raw/nts_base_price/ 에 두고 다시
   돌리면 된다 — 같은 고시일자 행을 먼저 지우므로 여러 번 돌려도 겹치지 않는다.
"""

import argparse
import csv
import io
import os
import sys
import zipfile

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "nts_base_price")
DEFAULT_STAGING_DIR = os.path.join(PROJECT_ROOT, "data", "staging", "nts_base_price")

TABLE = "nts_base_price"

# 원본 열 15개(실측). 포털 설명은 14개까지만 적어 두었는데 **공유면적이 하나 더 있다** —
# 안 담으면 나중에 누군가 `고시가격 × 전용면적`으로 총액을 재고 공용부만큼 적게 나온다.
REQUIRED_COLUMNS = (
    "상가건물번호", "상가종류코드", "고시일자", "법정동코드", "특수지코드", "번지", "호",
    "상가건물블록주소", "상가건물동주소", "건물층구분코드", "상가건물층주소",
    "상가건물호주소", "고시가격", "전용면적", "공유면적",
)

# ── 특수지코드 → PNU 대지구분 한 글자 ────────────────────────────────────────
# 실측 distinct 3종: 일반지번 2,479,392 / 가,확정예정지번 11,008 / 산 51.
# None = **조립 불가**. 아직 지번이 확정 안 된 신축분이라 나중에 붙을 수 있으므로
# 행을 버리지 않고 pnu 만 비워 둔다.
SPECIAL_TO_LAND_CD = {
    "일반지번": "1",
    "산": "2",
    "가,확정예정지번": None,
}

# ── 건물층구분코드 → 부호 ────────────────────────────────────────────────────
# ⚠️ 실측 distinct 3종: 지상층 2,373,818 · 지하층 116,619 · **옥탑층 14**.
#    옥탑이 14행뿐이라 "지상·지하 둘뿐"으로 넘겨짚기 딱 좋은 대목이었다. 모르는 구분값은
#    NULL 로 흘려보내지 않고 **통째로 멈춘다**(조용한 오염 금지).
FLOOR_KIND_SIGN = {"지상층": 1, "지하층": -1}
ROOFTOP_KIND = "옥탑층"
ROOFTOP_FLOOR = 99          # 절대 규칙 4: 옥탑 = 99 (층 번호와 무관)

# ── 광주(29)·전남(46) → 전남광주통합특별시(12) 시군구 재코딩 ─────────────────
# ⭐ **추측이 아니라 우리 DB 의 bjd_code 로 실증한 표다.** 옛 이름에서 시도명만 떼어 낸
#    꼬리(`목포시 용당동`)로 옛 코드와 새 코드를 맞춰 보니 3,207쌍이 붙었고, 그중 3,203쌍이
#    **읍면동·리 부분을 그대로 유지**했다. 즉 바뀐 것은 시군구 코드뿐이고, 그 대응은 아래
#    27쌍으로 닫힌다(옛 코드 쪽은 1:1 — 한 옛 코드가 두 새 코드로 갈리는 일이 없다).
#
# ⚠️ 예외 4건이 있다: 옛 체계에 **같은 이름의 코드가 두 벌** 있던 리(예: 북하면 동현리 =
#    4688040001·4688040030)에서, 통합 체계는 뒤쪽 하나만 남겼다. 그래서 …001 쪽을 쓰면
#    아래 규칙으로 만든 코드가 실재하지 않는다. 여기서 예외를 지어내지 않고, **적재 SQL 이
#    bjd_code 에 실재하는지 확인해 없으면 통째로 되돌린다**(관문 ③). 규칙을 둘로 늘려
#    숨은 판단을 만드느니, 실제로 걸리는 날 사람이 보는 편이 낫다.
#
# 안 바꾸면 어떻게 되나: 이 자료의 광주 48,978행 + 전남 19,043행이 **에러 하나 없이**
# 어느 필지에도 안 붙는다. 행 수는 맞으니 아무도 눈치채지 못한다.
BJD_SIGUNGU_REMAP = {
    # 광주광역시 → 전남광주통합특별시
    "29110": "12210",   # 동구
    "29140": "12240",   # 서구
    "29155": "12270",   # 남구
    "29170": "12300",   # 북구
    "29200": "12330",   # 광산구
    # 전라남도 → 전남광주통합특별시
    "46110": "12110",   # 목포시
    "46130": "12130",   # 여수시
    "46150": "12150",   # 순천시
    "46170": "12170",   # 나주시
    "46230": "12190",   # 광양시
    "46710": "12710",   # 담양군
    "46720": "12720",   # 곡성군
    "46730": "12730",   # 구례군
    "46770": "12740",   # 고흥군
    "46780": "12750",   # 보성군
    "46790": "12760",   # 화순군
    "46800": "12770",   # 장흥군
    "46810": "12780",   # 강진군
    "46820": "12790",   # 해남군
    "46830": "12800",   # 영암군
    "46840": "12810",   # 무안군
    "46860": "12820",   # 함평군
    "46870": "12830",   # 영광군
    "46880": "12840",   # 장성군
    "46890": "12850",   # 완도군
    "46900": "12860",   # 진도군
    "46910": "12870",   # 신안군
}
REMAP_SIDO = ("29", "46")

# 조립 가능한 행(= '가,확정예정지번'이 아닌 행) 중 실제로 PNU 가 만들어진 비율의 하한.
# 이 자료는 법정동코드·번지·호가 전 행 고정 길이라 사실상 100% 여야 한다 — 떨어졌다면
# 원본 형식이 바뀐 것이지 "원래 그런 것"이 아니다.
MIN_PNU_ASSEMBLY_RATE = 0.999

# 단위 검증(관문 ④)의 상식 범위. ㎡당 단가로 읽었을 때 중앙값이 이 밖으로 나가면
# 원본이 총액으로 바뀌었거나 우리가 열을 잘못 짚은 것이다.
SANE_UNIT_PRICE_MEDIAN = (100_000, 100_000_000)

# CSV 로 넘길 열 순서 = \copy 의 열 목록 순서. 둘이 어긋나면 값이 옆 칸으로 들어간다.
CSV_COLUMNS = (
    "pnu", "bjd_code_orig", "special_cd", "bld_nm", "dong_nm", "floor_no", "ho",
    "area_m2", "common_area_m2", "price_per_m2", "kind", "notice_date",
)

PROGRESS_EVERY = 250_000


# ── 순수 함수 (파일·DB 없음 — 테스트 대상) ───────────────────────────────────


def recover_zip_name(name):
    """zip 안 파일 이름의 한글을 되살린다 (cp437 로 읽힌 cp949).

    ★ 이 한 줄이 없으면 xlsx 를 못 찾아 "원본이 비었다"고 오판한다. 되살릴 수 없는 이름은
    (진짜 UTF-8 로 적힌 zip 등) 그대로 돌려준다 — 여기서 예외를 던지면 정상 zip 이 막힌다.
    """
    try:
        return name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def find_xlsx_entry(namelist):
    """zip 이름 목록에서 기준시가 xlsx 한 개를 고른다. (원래이름, 되살린이름)"""
    hits = [(n, recover_zip_name(n)) for n in namelist
            if recover_zip_name(n).lower().endswith(".xlsx")]
    if not hits:
        raise ValueError(
            "zip 안에 xlsx 가 없습니다. 들어 있는 것: {}".format(
                ", ".join(recover_zip_name(n) for n in namelist) or "(없음)"))
    if len(hits) > 1:
        raise ValueError(
            "zip 안에 xlsx 가 {}개입니다: {} — 어느 것이 기준시가인지 사람이 정해야 합니다.".format(
                len(hits), ", ".join(h[1] for h in hits)))
    return hits[0]


def clean(value):
    """엑셀 칸 하나 → 앞뒤 공백을 뗀 문자열. 빈 칸은 None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def assert_required_columns(header, where):
    """머리글이 우리가 아는 그것인지 확인한다. 다르면 조용히 NULL 이 되지 않게 멈춘다.

    시트가 5장이고 **장마다 머리글이 따로** 있다. 한 장만 형식이 달라도 그 장이 통째로
    엉뚱한 열에서 값을 읽게 되므로 장마다 본다.
    """
    have = [(clean(c) or "").lstrip("﻿") for c in (header or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in have]
    if missing:
        raise ValueError(
            "{}: 머리글에 {} 가 없습니다 (있는 것: {}). 원본 형식이 바뀌었습니다.".format(
                where, ", ".join(missing), ", ".join(have) or "(없음)"))
    return have


def is_blank_row(row):
    """엑셀 끝에 붙는 빈 줄. 값이 하나도 없으면 건너뛴다."""
    return all(clean(c) is None for c in (row or []))


def parse_floor(floor_kind, floor_addr, where):
    """건물층구분코드 + 층주소 → 정수 층 (절대 규칙 4).

    지상 n → n / 지하 n → -n / 옥탑 → 99. **0 은 만들지 않는다** — 지하와 결측이 섞이면
    층별 집계가 조용히 오염되고, DB 에도 CHECK 로 막혀 있다.

    ⛔ 모르는 구분값·모르는 층 표기는 NULL 로 흘려보내지 않고 멈춘다. 흘려보내면 그 행은
       "층을 모르는 호실"이 되어 어느 층에도 안 쌓이는데 행 수는 맞아 아무도 못 찾는다.
    """
    kind = clean(floor_kind)
    addr = clean(floor_addr)
    if kind == ROOFTOP_KIND:
        # 옥탑은 몇 층이든 99 다(규칙이 그렇다). 층주소는 보지 않는다.
        return ROOFTOP_FLOOR
    if kind not in FLOOR_KIND_SIGN:
        raise ValueError(
            "{}: 모르는 건물층구분코드입니다: {!r}. 아는 것은 {} 뿐입니다 — "
            "원본에 새 구분이 생겼다면 사람이 규칙을 정해야 합니다.".format(
                where, kind, " · ".join(sorted(list(FLOOR_KIND_SIGN) + [ROOFTOP_KIND]))))
    if addr is None:
        raise ValueError("{}: 층주소가 비어 있습니다 (건물층구분코드는 {!r}).".format(where, kind))
    try:
        n = int(addr)
    except ValueError:
        raise ValueError("{}: 층주소가 정수가 아닙니다: {!r}.".format(where, addr[:20]))
    if n < 0:
        # 부호는 건물층구분코드가 지고 층주소는 크기만 적는다는 것이 이 자료의 규칙이다.
        # 여기에 음수가 오면 그 전제가 깨진 것이라, 곱해서 부호를 뒤집는 대신 멈춘다.
        raise ValueError(
            "{}: 층주소가 음수입니다: {!r}. 부호는 건물층구분코드({!r})가 지는 자료라 "
            "여기에 음수가 오면 형식이 바뀐 것입니다.".format(where, addr[:20], kind))
    if n == 0:
        raise ValueError(
            "{}: 층이 0 입니다. 지하와 결측이 섞이면 집계가 오염되므로 0 은 쓰지 않습니다 "
            "(절대 규칙 4).".format(where))
    return n * FLOOR_KIND_SIGN[kind]


def remap_bjd_code(bjd_code, where):
    """옛 법정동코드(광주 29·전남 46)를 우리 DB 의 통합코드(12)로 바꾼다.

    다른 시도는 그대로 돌려준다. 대응이 없는 시군구는 **멈춘다** — 조용히 그대로 두면
    그 행들이 어느 필지에도 안 붙는데 행 수는 맞아 아무도 눈치채지 못한다.
    """
    code = clean(bjd_code) or ""
    if len(code) != 10 or not code.isdigit():
        raise ValueError(
            "{}: 법정동코드가 숫자 10개가 아닙니다: {!r}.".format(where, code[:20]))
    if code[:2] not in REMAP_SIDO:
        return code
    new_sigungu = BJD_SIGUNGU_REMAP.get(code[:5])
    if new_sigungu is None:
        raise ValueError(
            "{}: 광주·전남 시군구 {!r} 의 통합코드(12) 대응을 모릅니다 (법정동코드 {}). "
            "그대로 두면 이 행은 어느 필지에도 안 붙습니다 — "
            "bjd_code 표에서 대응을 확인해 BJD_SIGUNGU_REMAP 에 추가하세요.".format(
                where, code[:5], code))
    return new_sigungu + code[5:]


def assemble_pnu(bjd_code, special_cd, bunji, ho, where):
    """PNU(19) = 법정동코드(10) + 대지구분(1) + 본번(4) + 부번(4).

    돌려주는 값이 None 이면 **조립 불가**('가,확정예정지번')다 — 오류가 아니라 사실이고,
    그 행도 표에는 들어간다(지번이 확정되는 날 붙을 수 있다).
    """
    special = clean(special_cd)
    if special not in SPECIAL_TO_LAND_CD:
        raise ValueError(
            "{}: 모르는 특수지코드입니다: {!r}. 아는 것은 {} 뿐입니다.".format(
                where, special, " · ".join(sorted(SPECIAL_TO_LAND_CD))))
    land_cd = SPECIAL_TO_LAND_CD[special]
    if land_cd is None:
        return None

    code = remap_bjd_code(bjd_code, where)
    main, sub = clean(bunji) or "", clean(ho) or ""
    for label, part in (("번지", main), ("호", sub)):
        if not part.isdigit() or len(part) > 4:
            raise ValueError(
                "{}: {}가 숫자 4개 이하가 아닙니다: {!r}. 그대로 채우면 PNU 자릿수가 "
                "어긋나 조용히 다른 필지를 가리킵니다.".format(where, label, part[:20]))
    return code + land_cd + main.zfill(4) + sub.zfill(4)


def parse_notice_date(value, where):
    """고시일자 '20260101' → '2026-01-01'."""
    text = clean(value) or ""
    if len(text) != 8 or not text.isdigit():
        raise ValueError(
            "{}: 고시일자가 YYYYMMDD 형태(숫자 8개)가 아닙니다: {!r}.".format(where, text[:20]))
    return "{}-{}-{}".format(text[:4], text[4:6], text[6:8])


def parse_number(value, label, where):
    """숫자 칸 하나. 비어 있으면 None, 숫자가 아니면 멈춘다."""
    text = clean(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError("{}: {}가 숫자가 아닙니다: {!r}.".format(where, label, text[:20]))


def record_to_row(rec, where):
    """원본 한 줄 → 적재용 dict. 값 정리·검증을 여기서 끝낸다."""
    kind = clean(rec.get("상가종류코드"))
    if kind is None:
        raise ValueError(
            "{}: 상가종류코드가 비어 있습니다 — 상가와 오피스텔을 못 가립니다.".format(where))
    # ⚠️ bjd_code_orig 는 **원본 그대로** 담는다(재코딩 전). pnu 는 바뀐 값이라, 원본을
    #    잃으면 "우리가 바꾼 것"과 "원래 그랬던 것"을 다시 못 가린다.
    return {
        "pnu": assemble_pnu(rec.get("법정동코드"), rec.get("특수지코드"),
                            rec.get("번지"), rec.get("호"), where),
        "bjd_code_orig": clean(rec.get("법정동코드")),
        "special_cd": clean(rec.get("특수지코드")),
        "bld_nm": clean(rec.get("상가건물블록주소")),
        "dong_nm": clean(rec.get("상가건물동주소")),
        "floor_no": parse_floor(rec.get("건물층구분코드"), rec.get("상가건물층주소"), where),
        "ho": clean(rec.get("상가건물호주소")),
        "area_m2": parse_number(rec.get("전용면적"), "전용면적", where),
        "common_area_m2": parse_number(rec.get("공유면적"), "공유면적", where),
        "price_per_m2": parse_number(rec.get("고시가격"), "고시가격", where),
        "kind": kind,
        "notice_date": parse_notice_date(rec.get("고시일자"), where),
    }


def iter_records(sheets):
    """[(시트이름, 줄 iterable), ...] → (어디, 원본 dict) 를 하나씩.

    ⭐ 엑셀을 모르는 순수 함수다 — 튜플 목록만 주면 되므로 openpyxl 없이도 시험할 수 있다
       (CI 에는 openpyxl 이 없다). 엑셀 읽기는 아래 read_sheets 가 따로 맡는다.
    """
    for sheet_name, rows in sheets:
        it = iter(rows)
        header = next(it, None)
        if header is None:
            raise ValueError("시트 {}: 비어 있습니다 (머리글조차 없습니다).".format(sheet_name))
        have = assert_required_columns(header, "시트 {}".format(sheet_name))
        index = {name: i for i, name in enumerate(have)}
        for lineno, row in enumerate(it, start=2):
            if is_blank_row(row):
                continue
            yield ("시트 {} {}행".format(sheet_name, lineno),
                   {c: (row[index[c]] if index[c] < len(row) else None)
                    for c in REQUIRED_COLUMNS})


class Stats(object):
    """적재 전에 사람이 눈으로 볼 요약. 관문의 근거이기도 하다."""

    def __init__(self):
        self.total = 0
        self.pnu_ok = 0
        self.pnu_blocked = 0          # '가,확정예정지번' — 조립 불가가 정상인 행
        self.by_kind = {}
        self.by_floor_kind = {}
        self.by_sido = {}
        self.floor_zero = 0           # 절대 규칙 4 위반. parse_floor 뒤의 두 번째 눈이다
        self.remapped = 0
        self.remapped_codes = set()   # 재코딩된 법정동코드(관문 ③이 실재를 확인한다)
        self.notice_dates = {}
        self.unit_prices = []
        self.totals = []

    def add(self, rec, row):
        self.total += 1
        if row["pnu"] is None:
            self.pnu_blocked += 1
        else:
            self.pnu_ok += 1
        self.by_kind[row["kind"]] = self.by_kind.get(row["kind"], 0) + 1
        fk = clean(rec.get("건물층구분코드"))
        self.by_floor_kind[fk] = self.by_floor_kind.get(fk, 0) + 1
        if row["floor_no"] == 0:
            self.floor_zero += 1
        orig = row["bjd_code_orig"] or ""
        self.by_sido[orig[:2]] = self.by_sido.get(orig[:2], 0) + 1
        self.notice_dates[row["notice_date"]] = self.notice_dates.get(row["notice_date"], 0) + 1
        if orig[:2] in REMAP_SIDO:
            self.remapped += 1
            if row["pnu"] is not None:
                self.remapped_codes.add(row["pnu"][:10])
        price, area, common = row["price_per_m2"], row["area_m2"], row["common_area_m2"]
        if price is not None:
            self.unit_prices.append(price)
            if area is not None:
                self.totals.append(price * (area + (common or 0.0)))


def percentile(values, q):
    """정렬 후 q 분위. 비어 있으면 None (평균이 아니라 분위수를 쓰는 까닭 = 꼬리가 길다)."""
    if not values:
        return None
    ordered = sorted(values)
    i = int(len(ordered) * q)
    return ordered[min(i, len(ordered) - 1)]


def assert_gates(stats):
    """적재 전 관문. 하나라도 걸리면 SQL 을 만들지 않는다 (DB 는 손도 안 댄다).

    ① 행수   — 한 줄도 못 읽었으면 형식이 바뀐 것이다
    ② 조립률 — '가지번'을 뺀 행은 사실상 100% 조립돼야 한다
    ③ 층     — 0 층은 parse_floor 가 이미 막았고, 여기서 다시 확인한다
    ④ 단위   — 고시가격이 ㎡당인지. 총액으로 바뀌면 중앙값이 상식 범위를 벗어난다
    """
    if stats.total == 0:
        raise ValueError("읽은 행이 0 입니다 — 시트 구조가 바뀌었는지 확인하세요.")

    assemblable = stats.total - stats.pnu_blocked
    rate = (stats.pnu_ok / assemblable) if assemblable else 0.0
    if rate < MIN_PNU_ASSEMBLY_RATE:
        raise ValueError(
            "PNU 조립률이 {:.3%} 입니다 (하한 {:.1%}). '가,확정예정지번'을 뺀 {:,}행 중 "
            "{:,}행만 조립됐습니다 — 법정동코드·번지 형식이 바뀌었을 수 있습니다.".format(
                rate, MIN_PNU_ASSEMBLY_RATE, assemblable, stats.pnu_ok))

    # parse_floor 가 0 을 만들지 않으므로 도달하지 않아야 하지만, 규칙을 한 군데에만 두지
    # 않는다 — 나중에 누군가 parse_floor 를 고칠 때 이것이 두 번째 눈이 된다.
    if stats.floor_zero:
        raise ValueError(
            "층이 0 인 행이 {:,}개입니다. 지하와 결측이 섞이면 층별 집계가 조용히 "
            "오염됩니다 (절대 규칙 4).".format(stats.floor_zero))

    median = percentile(stats.unit_prices, 0.5)
    if median is None:
        raise ValueError("고시가격이 있는 행이 하나도 없습니다.")
    low, high = SANE_UNIT_PRICE_MEDIAN
    if not (low <= median <= high):
        raise ValueError(
            "고시가격 중앙값이 {:,.0f}원 입니다 — ㎡당 단가라면 {:,}~{:,}원 사이라야 합니다. "
            "원본이 총액으로 바뀌었거나 열을 잘못 짚었을 수 있습니다.".format(median, low, high))
    return True


def format_report(stats):
    """dry-run 이 그대로 보여 주는 요약. 적재 뒤에도 같은 것을 본다."""
    out = []
    assemblable = stats.total - stats.pnu_blocked
    rate = (stats.pnu_ok / assemblable) if assemblable else 0.0
    out.append("  총 {:,}행".format(stats.total))
    out.append("  PNU: 조립 {:,} / 조립 불가('가,확정예정지번') {:,} / "
               "조립률 {:.3%} (하한 {:.1%})".format(
                   stats.pnu_ok, stats.pnu_blocked, rate, MIN_PNU_ASSEMBLY_RATE))
    out.append("  종류:")
    for k, v in sorted(stats.by_kind.items(), key=lambda kv: -kv[1]):
        out.append("    {:<10} {:>12,}".format(k, v))
    out.append("  건물층구분:")
    for k, v in sorted(stats.by_floor_kind.items(), key=lambda kv: -kv[1]):
        out.append("    {:<10} {:>12,}".format(k or "(빈값)", v))
    out.append("  고시일자:")
    for k, v in sorted(stats.notice_dates.items()):
        out.append("    {:<12} {:>12,}".format(k, v))
    out.append("  광주·전남 재코딩: {:,}행 / 법정동 {:,}개 (29·46 → 12)".format(
        stats.remapped, len(stats.remapped_codes)))
    out.append("  시도별(원본 법정동코드 앞 두 글자):")
    for k, v in sorted(stats.by_sido.items(), key=lambda kv: -kv[1]):
        out.append("    {:<6} {:>12,}".format(k, v))
    out.append("  단위 검증 — 고시가격(원/㎡): p25 {:,.0f} · 중앙값 {:,.0f} · p75 {:,.0f} · "
               "p99 {:,.0f}".format(
                   percentile(stats.unit_prices, 0.25) or 0,
                   percentile(stats.unit_prices, 0.5) or 0,
                   percentile(stats.unit_prices, 0.75) or 0,
                   percentile(stats.unit_prices, 0.99) or 0))
    out.append("  단위 검증 — 가격 x (전용+공유) 총액(원): p25 {:,.0f} · 중앙값 {:,.0f} · "
               "p75 {:,.0f} · p99 {:,.0f}".format(
                   percentile(stats.totals, 0.25) or 0,
                   percentile(stats.totals, 0.5) or 0,
                   percentile(stats.totals, 0.75) or 0,
                   percentile(stats.totals, 0.99) or 0))
    out.append("    → 중앙값이 백만원 단위면 ㎡당 단가, 억 단위면 총액이다. "
               "총액으로 읽히면 관문 ④가 멈춘다.")
    return "\n".join(out)


def copy_path_literal(path):
    """psql `\\copy` 에 넘길 경로. 윈도우 역슬래시를 슬래시로 바꾸고 따옴표를 이스케이프한다."""
    return path.replace("\\", "/").replace("'", "''")


def build_sql(csv_path, notice_dates, expected_rows):
    """적재 SQL. 한 트랜잭션이라 **중간에 실패하면 통째로 되돌린다.**

    반쯤 들어간 표는 "있는데 모자란" 최악의 상태다 — 화면이 조용히 낮은 중앙값을 낸다.

    ⚠️ 관문은 전부 `raise exception` 이다. psql 은 select 가 몇 줄을 돌려주든 종료코드 0
       이라, 세어서 보여 주기만 하면 그대로 commit 된다.
    """
    if not notice_dates:
        raise ValueError("고시일자를 하나도 못 읽었습니다.")
    dates_sql = ", ".join("'{}'::date".format(d) for d in sorted(notice_dates))

    return """begin;
set local statement_timeout = '7200s';

-- 같은 고시일자를 다시 넣는 경우(재적재)를 위해 먼저 지운다. 트랜잭션 안이라 뒤에서
-- 관문에 걸리면 이 삭제까지 통째로 되돌아간다.
delete from {table} where notice_date in ({dates});

\\copy {table} ({cols}) from '{csv}' with (format csv, encoding 'UTF8')

-- ── 관문 ① 행수 대조 ────────────────────────────────────────────────────────
-- CSV 가 중간에 잘려도 \\copy 는 **에러 없이** 거기까지만 넣는다. 원본에서 읽은 수와
-- 맞춰 보는 것이 그걸 잡는 유일한 방법이다.
do $$
declare cnt bigint;
begin
  select count(*) into cnt from {table} where notice_date in ({dates});
  if cnt <> {expected} then
    raise exception '넣은 행이 %개인데 원본에서 읽은 것은 {expected}개입니다 — 통째로 되돌립니다', cnt;
  end if;
end $$;

-- ── 관문 ② 층 0 ─────────────────────────────────────────────────────────────
-- CHECK 제약이 이미 막지만, 제약이 실수로 빠진 환경에서도 같은 규칙이 서게 한다.
do $$
declare cnt bigint;
begin
  select count(*) into cnt from {table} where notice_date in ({dates}) and floor_no = 0;
  if cnt > 0 then
    raise exception '층이 0 인 행 %개 — 지하와 결측이 섞이므로 통째로 되돌립니다', cnt;
  end if;
end $$;

-- ── 관문 ③ 광주·전남 재코딩이 실재하는 법정동을 가리키나 ────────────────────
-- 시군구 코드만 바꾸는 규칙이라, 옛 체계에 같은 이름의 코드가 두 벌 있던 리에서는
-- 만들어진 코드가 실재하지 않을 수 있다(적재기 머리말의 예외 4건). 그런 행이 있으면
-- 그 필지에 영영 안 붙으므로 조용히 두지 않고 되돌린다.
do $$
declare cnt bigint; sample text;
begin
  select count(*), min(left(t.pnu, 10))
    into cnt, sample
    from {table} t
   where t.notice_date in ({dates})
     and left(t.bjd_code_orig, 2) in ('29', '46')
     and t.pnu is not null
     -- ⚠️ `::char(10)` 을 빼면 안 된다. bjd_code 컬럼이 char(10) 인데 left() 결과는 text 라,
     --    그대로 견주면 **컬럼 쪽이 text 로 캐스트돼 인덱스가 죽는다**(2026-08-16b 와 같은 병).
     and not exists (select 1 from bjd_code b where b.bjd_code = left(t.pnu, 10)::char(10));
  if cnt > 0 then
    raise exception '재코딩한 법정동코드가 실재하지 않는 행 %개 (예: %) — 통째로 되돌립니다', cnt, sample;
  end if;
end $$;

-- ── 정보(막지 않는다) — 필지에 실제로 붙는 비율 ─────────────────────────────
-- 우리 parcel 표는 아직 전국을 다 담지 않았다. 여기서 낮게 나오는 것은 이 자료의 결함이
-- 아니라 우리 필지 적재 범위의 사실이라, 세어서 보여만 준다.
select count(*) as "넣은 행",
       count(*) filter (where pnu is not null) as "PNU 있는 행",
       count(*) filter (where pnu is not null
                          and exists (select 1 from parcel p where p.pnu = {table}.pnu))
         as "우리 필지에 붙는 행"
  from {table} where notice_date in ({dates});

commit;
""".format(table=TABLE, dates=dates_sql, cols=", ".join(CSV_COLUMNS),
           csv=copy_path_literal(csv_path), expected=expected_rows)


# ── 파일 읽기 (엑셀·zip — 순수 함수 바깥) ────────────────────────────────────


def newest_zip(raw_dir):
    """가장 최근에 받은 zip 을 고른다(원본명에 기준일자가 들어 있어 사전순 = 시간순)."""
    if not os.path.isdir(raw_dir):
        raise SystemExit("원본 폴더가 없습니다: {}".format(raw_dir))
    hits = sorted(n for n in os.listdir(raw_dir) if n.lower().endswith(".zip"))
    if not hits:
        raise SystemExit(
            "원본 zip 이 없습니다: {}\n"
            "  공공데이터포털 3036455 에서 받아 이 폴더에 두세요.".format(raw_dir))
    return os.path.join(raw_dir, hits[-1])


def ensure_xlsx(zip_path, staging_dir):
    """zip 안 xlsx 를 staging 으로 꺼내 놓고 그 경로를 돌려준다 (이미 있으면 그대로 쓴다).

    왜 꺼내나: openpyxl 은 파일 안을 앞뒤로 오가며 읽는데, zip 안 스트림을 되감는 일은
    압축을 처음부터 다시 푸는 것이라 몇 배로 느려진다. 한 번 꺼내 두고 쓴다.
    data/staging/ 은 .gitignore 대상이라 커밋에 딸려 가지 않는다.
    """
    with zipfile.ZipFile(zip_path) as z:
        raw_name, nice_name = find_xlsx_entry(z.namelist())
        info = z.getinfo(raw_name)
        if not os.path.isdir(staging_dir):
            os.makedirs(staging_dir)
        out = os.path.join(staging_dir, os.path.basename(nice_name))
        if os.path.exists(out) and os.path.getsize(out) == info.file_size:
            return out, nice_name
        with z.open(raw_name) as src, open(out, "wb") as dst:
            while True:
                chunk = src.read(8 * 1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
    return out, nice_name


def read_sheets(xlsx_path):
    """[(시트이름, 줄 generator), ...] 와 workbook. openpyxl 은 **여기서만** 쓴다.

    ⚠️ import 를 함수 안에서 한다 — CI 에는 openpyxl 이 없다(pyshp 와 같은 처방).
       순수 함수만 쓰는 테스트는 이 줄을 지나지 않으므로 CI 에서도 돈다.
    """
    try:
        import openpyxl  # noqa: PLC0415
    except ImportError:
        raise SystemExit(
            "openpyxl 이 필요합니다 (xlsx 를 읽는 유일한 곳):\n"
            "  python -m pip install openpyxl")
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    return [(ws.title, ws.iter_rows(values_only=True)) for ws in wb.worksheets], wb


def transform(sheets, out_csv, limit=None, progress=None):
    """원본을 훑으며 CSV 를 쓰고 요약을 모은다. (stats, 쓴 행수)

    한 행이라도 검증에 걸리면 그 줄에서 멈춘다 — 나머지를 넣고 "성공"이라고 말하면
    빠진 호실을 아무도 못 찾는다.
    """
    stats = Stats()
    written = 0
    with io.open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        for where, rec in iter_records(sheets):
            row = record_to_row(rec, where)
            stats.add(rec, row)
            writer.writerow([row[c] for c in CSV_COLUMNS])
            written += 1
            if progress and written % PROGRESS_EVERY == 0:
                progress(written)
            if limit and written >= limit:
                break
    return stats, written


def main(argv=None):
    # cp949 콘솔에서 한글·특수문자(—) 출력이 UnicodeEncodeError 로 죽지 않게 —
    # 형제 스크립트들(load_sbiz_district.py 등)과 같은 처방.
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="국세청 기준시가 zip → nts_base_price 적재")
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    p.add_argument("--zip", help="특정 zip 을 직접 지정")
    p.add_argument("--xlsx", help="이미 꺼내 둔 xlsx 를 직접 지정(개발용 — 압축 해제 생략)")
    p.add_argument("--staging-dir", default=DEFAULT_STAGING_DIR,
                   help="꺼낸 xlsx 와 만들어진 CSV 를 두는 곳 (.gitignore 대상)")
    p.add_argument("--limit", type=int,
                   help="앞에서 N행만 읽는다(빠른 점검용 — 적재에는 쓰지 말 것)")
    p.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않는다")
    p.add_argument("--sql-out", help="만들어진 SQL 을 이 파일로 저장(검토용)")
    a = p.parse_args(argv)

    print("=" * 74)
    print("국세청 상업용건물·오피스텔 기준시가 → {} 적재".format(TABLE))
    print("=" * 74)

    if a.xlsx:
        xlsx_path, nice_name = a.xlsx, os.path.basename(a.xlsx)
        print("  xlsx(직접 지정): {}".format(xlsx_path))
    else:
        zip_path = a.zip or newest_zip(a.raw_dir)
        print("  원본 zip: {}".format(zip_path))
        xlsx_path, nice_name = ensure_xlsx(zip_path, a.staging_dir)
        print("  zip 안 xlsx: {}  ({:,} bytes)".format(nice_name, os.path.getsize(xlsx_path)))

    if not os.path.isdir(a.staging_dir):
        os.makedirs(a.staging_dir)
    csv_path = os.path.join(a.staging_dir, "nts_base_price.csv")

    sheets, wb = read_sheets(xlsx_path)
    print("  시트 {}장: {}".format(len(sheets), ", ".join(s[0] for s in sheets)))
    if a.limit:
        print("  ⚠️ --limit {:,} — 앞부분만 읽습니다. 적재에는 쓰지 마세요.".format(a.limit))
    print("  읽는 중...")

    def progress(n):
        print("    {:,}행".format(n))
        sys.stdout.flush()

    try:
        stats, written = transform(sheets, csv_path, limit=a.limit, progress=progress)
    except ValueError as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1
    finally:
        try:
            wb.close()
        except Exception:
            pass

    print()
    print(format_report(stats))
    print("  중간 파일: {}  ({:,} bytes)".format(csv_path, os.path.getsize(csv_path)))

    try:
        assert_gates(stats)
    except ValueError as e:
        print()
        print("관문에 걸렸습니다: {}".format(e), file=sys.stderr)
        print("DB 에는 아무것도 쓰지 않았습니다.", file=sys.stderr)
        return 1
    print("  관문 통과 (행수 · 조립률 · 층 · 단위)")

    sql = build_sql(csv_path, stats.notice_dates, written)
    if a.sql_out:
        with io.open(a.sql_out, "w", encoding="utf-8", newline="\n") as f:
            f.write(sql)
        print("  SQL 저장: {}".format(a.sql_out))

    if a.dry_run:
        print()
        print("--dry-run 지정 — DB 에 아무것도 쓰지 않았습니다.")
        return 0

    if a.limit:
        print("--limit 은 점검용입니다. 적재하려면 --limit 없이 다시 돌리세요.", file=sys.stderr)
        return 1

    import dbx  # noqa: PLC0415  (dry-run 은 DB 설정 없이도 돌아야 한다)
    rc = dbx.run_sql(sql)
    if rc != 0:
        print("적재 실패 (psql 종료코드 {}). 트랜잭션이라 아무것도 안 들어갔습니다.".format(rc),
              file=sys.stderr)
        return rc
    print()
    print("  적재 완료.")
    print("  다음: python scripts/post_load.py   (vacuum + 요약표 갱신)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
