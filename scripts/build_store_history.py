# -*- coding: utf-8 -*-
"""이 자리 가게 이력 — 로컬 zip 을 한 번 읽어 가게마다 한 줄의 결과표(csv + meta)를 굽는다 (결정 0045 PR④).

왜 로컬에서 굽나
----------------
DB 의 `unit_business` 는 최근 4분기만 둔다(2026-10-28 👤 「4분기 보관」). 옛 분기는 DB 에 두지 않고,
`data/raw/sangkwon_zips/` 의 소진공 상가(상권)정보 zip(2015Q4~ 분기마다 하나)을 **한 번 읽어** 가게 이력
결과표만 만든다(👤 결정 0045 ⑤-1 — 2017Q4 이후 · 서울+대전). DB 는 열지 않고 외부 호출도 0 이다.
만든 csv 는 git 에 넣지 않는다(`.gitignore` 의 `data/derived/`) → `scripts/collectors/load_store_history.py` 가 적재한다.

zip 읽는 규칙 (2026-10-31 조사 C 실측)
--------------------------------------
  · 분기 = zip 이름 속 날짜(`(20\\d{6})\\.zip`) — 분기말 달(3·6·9·12)이면 그 달, 아니면 바로 앞 분기말.
    `…_20251030.zip` → 202509 · `상가(상권)정보_20260630.zip` → 202606 · `…_20151231.zip` → 201512.
    ⛔ 파일 **이름순으로 읽지 않는다** — 2026Q2 zip 만 `상가(상권)정보_…` 로 시작해 차례가 뒤섞인다(날짜순으로 정렬).
    (`load_sangkwon_snapshot.detect_snapshot_ym` 은 csv 이름의 `_YYYYMM.csv` 를 읽는 다른 규칙이라 재사용하지 않는다.)
  · 2017Q3(201709)는 **늘 읽지 않는다** — 시·도 구분 없는 전국 4조각 + 옛 번호 체계(번호가 그 분기에 통째 끊긴다).
  · 2018Q2~2022Q4 는 zip 안에 zip 이 한 겹 더 — 한 단계만 푼다.
  · 2023-06·09 zip 안 파일 이름은 cp437 로 풀린 글자 → `encode('cp437').decode('cp949')` 로 되돌린다(알려진한계 §2).
  · 한 분기 · 한 시·도에 csv 가 **정확히 1개**(이름에 시·도 이름 · '필독' 제외)가 아니면 멈춘다.
  · 글자 인코딩은 첫 줄로 utf-8-sig → cp949 를 고른다(섞여 있다) · 본문은 errors='replace'.
  · 쓰는 칸 = 상가업소번호 · 상호명 · 지번코드(19자리 = PNU) · 층정보 — 머리줄에서 이름으로 찾는다(없으면 멈춤).

가게 사슬 규칙 (👤 결정 0045 ⑤-2 · 함정 5 ①~⑥ · 메인 풀이 ⓒⓓⓔⓕ)
-------------------------------------------------------------------
  ① 상가업소번호로 잇는다(이웃 분기 95~99% 가 같은 번호).
  ② 번호가 **끝난 사슬**(그 분기에 번호가 사라짐)에 한해, 다음 분기 새 번호 중 같은 (pnu, floor_no, 정규화 상호)가
     정확히 하나일 때만 잇는다 — ⓒ 끝난 사슬 쪽도 그 열쇠에 **정확히 하나**여야 한다(둘이면 고를 근거가 없다).
  ③ floor_no 가 None(층 모름)이면 잇지 않는다.
  ④ 상호 정규화 = 공백 전부 제거(U+3000 포함) + 전각 ASCII(U+FF01~FF5E) → 반각 · 괄호·기호·대소문자는 그대로.
  ⑤ 사슬의 값(상호·층·pnu)은 **마지막 분기 값**.
  ⑥ 한 분기라도 빠지면 잇지 않는다 — 빠졌다 돌아온 번호는 **새 사슬**.
  ⓓ 이웃 분기 = 처리 목록에서 바로 앞 분기(201709 를 건너뛰므로 재현 모드에선 201706 → 201712 가 이웃).
  ⓔ 한 분기 안에서 같은 번호가 두 줄이면 첫 줄만 쓰고 센다 · ⓕ 지번코드가 19자리 숫자가 아니면 건너뛰고 센다.

결과 csv 칸 (머리줄 있음 · utf-8)
---------------------------------
  pnu,floor_no,biz_name,biz_no_last,first_ym,last_ym,seen_cnt,is_current,n_links,truncated
  · floor_no 빈 칸 = 층 모름 · is_current = last_ym 이 마지막 분기 · truncated = first_ym 이 첫 분기(그 전은 모른다)
  · seen_cnt 는 **자료에 보인 분기 수**이지 영업 기간이 아니다 · 안 보임 ≠ 폐업.

쓰는 법 (프로젝트 루트에서)
---------------------------
    python scripts/build_store_history.py --reproduce-c     # 조사 C 재현(대전 42분기 · 통과/실패 · 파일 쓰기 0)
    python scripts/build_store_history.py                   # data/derived/store_history/<오늘>.csv + .meta.json
    → python scripts/collectors/load_store_history.py --dry-run → 실적재 → post_load.py · --check
  ⛔ 운영 순서(결정 0045 표지 예외): 상권 새 분기 전국 모드 적재 → 이 빌드 → 이력 적재 → post_load.py.
  ⛔ 결과표는 매 분기 **통째 다시 굽는다**(증분 없음 · 결정 0045 「새 분기 보관 방침」).
"""

import argparse
import collections
import csv
import datetime
import hashlib
import io
import json
import os
import re
import statistics
import sys
import time
import zipfile

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from normalize_floor import normalize_floor  # noqa: E402  (층 정규화 정본 — 재구현 금지)

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_ZIP_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "sangkwon_zips")
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "data", "derived", "store_history")

SIDO_NAMES = {"11": "서울", "30": "대전"}
DEFAULT_SIDO = ("11", "30")
DEFAULT_START_YM = "201712"
SKIP_YMS = frozenset({"201709"})          # 2017Q3 — 번호 체계 단절 · 시·도 구분 없음(늘 읽지 않는다)

REPRO_SIDO = "30"                         # 조사 C 재현 = 대전 · 2015Q4~ · 2017Q3 뺌
REPRO_START_YM = "201512"

COLUMNS = ("상가업소번호", "상호명", "지번코드", "층정보")
OUT_COLUMNS = ("pnu", "floor_no", "biz_name", "biz_no_last", "first_ym", "last_ym",
               "seen_cnt", "is_current", "n_links", "truncated")
RE_ZIP_DATE = re.compile(r"(20\d{6})\.zip$", re.IGNORECASE)
RE_YM = re.compile(r"^\d{4}(03|06|09|12)$")
RE_PNU = re.compile(r"^\d{19}$")          # scripts/build_sitemap.py PNU_RE 와 같은 글
FIELD_SIZE_LIMIT = 10 ** 7
SKIP_NAME_MARK = "필독"

# 조사 C(2026-10-31 · 대전 42분기 · 오늘 가게 80,704) — (중앙값, 8분기 이상 %, 1분기째 %, 전부 %)
C_VALUES = {
    "번호만": (19, 65.6, 12.7, 25.0),
    "번호 + 땅·층·상호": (21, 67.9, 11.4, 26.6),
}
# 메인 풀이 ⓑ — 번호만 = 읽기 파이프라인 검증(±0 · ±0.3pp) · 규칙 = 결정 0045 원문 「21 · 67.9 ±2」
REPRO_K1_MEDIAN = 19
REPRO_K1_PCT8 = 65.6
REPRO_K1_PCT8_TOL = 0.3
REPRO_RULE_MEDIAN = (19, 23)
REPRO_RULE_PCT8 = (65.9, 69.9)


class BuildError(RuntimeError):
    """zip 모양이 기대와 다름 — 결과 파일을 쓰지 않는다."""


# ── 분기 · zip 고르기 ────────────────────────────────────────────────────────


def zip_quarter(name):
    """zip 이름 → 분기 코드 YYYYMM(분기말 달). 이름에 날짜가 없으면 None."""
    m = RE_ZIP_DATE.search(os.path.basename(name))
    if not m:
        return None
    d = m.group(1)
    year, month = int(d[:4]), int(d[4:6])
    if not 1 <= month <= 12:
        return None
    qm = month - month % 3
    if qm == 0:
        year, qm = year - 1, 12
    return "{:04d}{:02d}".format(year, qm)


def quarter_add(ym, n):
    """분기 코드에 n 분기를 더한다(201712 + 1 → 201803)."""
    idx = int(ym[:4]) * 4 + int(ym[4:]) // 3 - 1 + n
    return "{:04d}{:02d}".format(idx // 4, (idx % 4 + 1) * 3)


def list_quarter_zips(zip_dir):
    """[(분기, 경로)] — zip 이름 속 **날짜순**. 날짜 없는 zip · 같은 분기 둘이면 멈춘다."""
    found = []
    for name in os.listdir(zip_dir):
        if not name.lower().endswith(".zip"):
            continue
        m = RE_ZIP_DATE.search(name)
        ym = zip_quarter(name)
        if not m or ym is None:
            raise BuildError("zip 이름에 날짜(20YYMMDD)가 없습니다: {}".format(name))
        found.append((m.group(1), ym, os.path.join(zip_dir, name)))
    found.sort()
    seen = collections.Counter(ym for _d, ym, _p in found)
    dup = sorted(ym for ym, n in seen.items() if n > 1)
    if dup:
        raise BuildError("같은 분기 zip 이 둘 이상입니다: {}".format(dup))
    return [(ym, path) for _d, ym, path in found]


def select_quarters(zips, start_ym, end_ym):
    """start~end 사이(201709 늘 뺌) — 처리 목록에서 이웃 분기는 달력으로도 이웃이어야 한다(201709 만 건너뜀)."""
    picked = [(ym, p) for ym, p in zips if start_ym <= ym <= end_ym and ym not in SKIP_YMS]
    for (a, _pa), (b, _pb) in zip(picked, picked[1:]):
        expect = quarter_add(a, 1)
        while expect in SKIP_YMS:
            expect = quarter_add(expect, 1)
        if b != expect:
            raise BuildError("분기 zip 이 빠졌습니다: {} 다음이 {} 이어야 하는데 {} 입니다".format(a, expect, b))
    return picked


# ── zip 안 csv 읽기 ──────────────────────────────────────────────────────────


def fix_name(name):
    """cp437 로 풀린 한글 파일 이름을 되돌린다(2023-06·09 zip). 안 되면 그대로."""
    try:
        return name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def list_csv_members(zf):
    """열린 ZipFile → [(보이는 이름, 여는 함수)] — csv 만 · 안쪽 zip 은 한 단계 푼다(보이는 이름 = 바깥>안)."""
    out = []
    for info in zf.infolist():
        name = fix_name(info.filename)
        if info.is_dir() or not name:
            continue
        low = name.lower()
        if low.endswith(".csv"):
            out.append((name, lambda zf=zf, info=info: zf.open(info)))
        elif low.endswith(".zip"):
            inner = zipfile.ZipFile(io.BytesIO(zf.read(info)))
            for j in inner.infolist():
                n2 = fix_name(j.filename)
                if not j.is_dir() and n2.lower().endswith(".csv"):
                    out.append((name + ">" + n2, lambda inner=inner, j=j: inner.open(j)))
    return out


def pick_sido_csv(members, sido_name, ym):
    """이름에 시·도 이름이 든 csv('필독' 제외)가 정확히 1개여야 한다."""
    cands = [m for m in members if sido_name in m[0] and SKIP_NAME_MARK not in m[0]]
    if len(cands) != 1:
        raise BuildError("{} 분기 {} csv 가 {}개입니다(정확히 1개여야 한다): {}".format(
            ym, sido_name, len(cands), [c[0] for c in cands]))
    return cands[0]


def pick_encoding(first_line):
    """첫 줄 바이트로 utf-8-sig → cp949 를 고른다."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            first_line.decode(enc)
            return enc
        except UnicodeDecodeError:
            pass
    return "cp949"


def normalize_name(name):
    """상호 정규화(규칙 ④) — 공백 전부 제거(U+3000 포함) + 전각 ASCII → 반각. 괄호·기호·대소문자는 그대로."""
    s = "".join(name.split())
    return "".join(chr(ord(c) - 0xFEE0) if "！" <= c <= "～" else c for c in s)


def read_quarter_rows(opener, where):
    """csv 하나 → (줄 목록, 셈). 줄 = (biz_no, pnu, floor_no, name_raw, name_norm).

    머리줄에 네 칸이 없으면 멈춘다 · 칸 수가 머리보다 적은 줄은 건너뛴다(short) ·
    ⓕ 지번코드가 19자리 숫자가 아니면 건너뛴다(bad_pnu) · ⓔ 같은 번호 두 번째 줄부터 건너뛴다(dup_biz_no).
    """
    raw = opener()
    try:
        enc = pick_encoding(raw.readline())
    finally:
        raw.close()
    counts = {"read": 0, "short": 0, "bad_pnu": 0, "dup_biz_no": 0}
    rows, seen = [], set()
    with io.TextIOWrapper(opener(), encoding=enc, errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        head = [h.strip() for h in next(reader, [])]
        missing = [c for c in COLUMNS if c not in head]
        if missing:
            raise BuildError("{}: 머리줄에 칸이 없습니다 {}".format(where, missing))
        i_biz, i_name, i_pnu, i_floor = (head.index(c) for c in COLUMNS)
        width = len(head)
        for r in reader:
            counts["read"] += 1
            if len(r) < width:
                counts["short"] += 1
                continue
            pnu = r[i_pnu].strip()
            if not RE_PNU.match(pnu):
                counts["bad_pnu"] += 1
                continue
            biz = r[i_biz].strip()
            if biz in seen:
                counts["dup_biz_no"] += 1
                continue
            seen.add(biz)
            name = r[i_name].strip()
            rows.append((biz, pnu, normalize_floor(r[i_floor]), name, normalize_name(name)))
    return rows, counts


# ── 사슬 ─────────────────────────────────────────────────────────────────────


class Chain:
    __slots__ = ("pnu", "floor_no", "name_raw", "name_norm", "biz_no_last",
                 "first_ym", "last_ym", "seen_cnt", "n_links", "pnu_lvl", "pnu_move")

    def __init__(self, ym, row):
        self.biz_no_last, self.pnu, self.floor_no, self.name_raw, self.name_norm = row
        self.first_ym = self.last_ym = ym
        self.seen_cnt = 1
        self.n_links = 0
        self.pnu_lvl = 0          # 땅 번호가 바뀐 가장 넓은 폭(0 안 바뀜 · 1 같은 시군구 · 2 같은 시·도 · 3 다른 시·도)
        self.pnu_move = None      # 그 가장 넓은 바뀜의 (앞 pnu, 뒤 pnu) — 보고 예시용


PNU_LEVELS = ((1, "same_sgg", "같은 시군구"), (2, "other_sgg", "다른 시군구·같은 시·도"), (3, "other_sido", "다른 시·도"))


def pnu_change_level(old, new):
    """땅 번호 바뀜의 폭 — 0 같음 · 1 앞 5자리(시군구) 같음 · 2 앞 2자리(시·도) 같음 · 3 시·도도 다름."""
    if old == new:
        return 0
    if old[:5] == new[:5]:
        return 1
    if old[:2] == new[:2]:
        return 2
    return 3


def link_key(pnu, floor_no, name_norm):
    """보조 열쇠(규칙 ②③) — 층 모름이면 None(잇지 않는다)."""
    if floor_no is None:
        return None
    return (pnu, floor_no, name_norm)


class ChainBook:
    """한 시·도의 사슬 장부. step() 을 분기 오름차순으로 부른다. link=False 면 「번호만」(3단 끔)."""

    def __init__(self, link=True):
        self.link = link
        self.chains = []
        self.alive = {}          # biz_no → 직전 분기까지 살아 있는 사슬
        self.pnu_changed = 0

    def _extend(self, chain, ym, row):
        biz, pnu, floor_no, name_raw, name_norm = row
        if chain.pnu != pnu:
            self.pnu_changed += 1
            lvl = pnu_change_level(chain.pnu, pnu)
            if lvl > chain.pnu_lvl:
                chain.pnu_lvl, chain.pnu_move = lvl, (chain.pnu, pnu)
        chain.biz_no_last, chain.pnu, chain.floor_no = biz, pnu, floor_no
        chain.name_raw, chain.name_norm = name_raw, name_norm
        chain.last_ym = ym
        chain.seen_cnt += 1

    def step(self, ym, rows):
        """한 분기 줄 → 장부 갱신. 셈 dict(rows · continued · ended · new · linked)를 돌려준다."""
        nxt, fresh, continued = {}, [], 0
        # 1단 — 번호로 잇는다(규칙 ①)
        for row in rows:
            chain = self.alive.get(row[0])
            if chain is not None:
                self._extend(chain, ym, row)
                nxt[row[0]] = chain
                continued += 1
            else:
                fresh.append(row)
        # 2단 — 끝난 사슬(직전 분기까지 살았는데 1단에서 안 이어짐)
        ended = [c for b, c in self.alive.items() if b not in nxt]
        # 3단 — 끝난 사슬 1 · 새 번호 줄 1 이 같은 (pnu, 층, 정규화 상호)일 때만 잇는다(규칙 ②③ · ⓒ)
        used, linked = set(), 0
        if self.link and ended and fresh:
            by_end = collections.defaultdict(list)
            for c in ended:
                k = link_key(c.pnu, c.floor_no, c.name_norm)
                if k is not None:
                    by_end[k].append(c)
            by_new = collections.defaultdict(list)
            for i, row in enumerate(fresh):
                k = link_key(row[1], row[2], row[4])
                if k is not None:
                    by_new[k].append(i)
            for k, idxs in by_new.items():
                if len(idxs) != 1:
                    continue
                cands = by_end.get(k)
                if not cands:
                    continue
                if len(cands) != 1:
                    continue
                chain, row = cands[0], fresh[idxs[0]]
                self._extend(chain, ym, row)
                chain.n_links += 1
                nxt[row[0]] = chain
                used.add(idxs[0])
                linked += 1
        # 4단 — 남은 새 번호 줄은 새 사슬 · 5단 — 안 이어진 사슬은 끝난 채 남는다(규칙 ⑥)
        new = 0
        for i, row in enumerate(fresh):
            if i in used:
                continue
            chain = Chain(ym, row)
            self.chains.append(chain)
            nxt[row[0]] = chain
            new += 1
        self.alive = nxt
        return {"rows": len(rows), "continued": continued, "ended": len(ended) - linked,
                "new": new, "linked": linked}

    def current(self):
        return list(self.alive.values())


# ── 결과 ─────────────────────────────────────────────────────────────────────


def out_rows(chains, start_ym, end_ym):
    """사슬 → 결과 줄(A5 칸 차례) · 줄 차례 = pnu · 지금 보임 먼저 · seen_cnt 내림 · 층(모름 끝) · 번호."""
    rows = []
    for c in chains:
        rows.append((c.pnu, c.floor_no, c.name_raw, c.biz_no_last, c.first_ym, c.last_ym,
                     c.seen_cnt, c.last_ym == end_ym, c.n_links, c.first_ym == start_ym))
    rows.sort(key=lambda r: (r[0], not r[7], -r[6], r[1] is None, r[1] if r[1] is not None else 0, r[3], r[5]))
    return rows


def pnu_change_stats(chains, n_quarters_end):
    """땅 번호가 바뀐 사슬을 폭(같은 시군구 · 다른 시군구·같은 시·도 · 다른 시·도)으로 나눈다 — 측정만(규칙과 무관).

    → {열쇠: {"chains", "current", "seen_pct"}} + 다른 시·도 예 3건. seen_pct = 그 폭의 지금 보이는 사슬 seen_cnt 합 ÷
    전체 지금 보이는 사슬 seen_cnt 합(%). 한 사슬이 여러 번 바뀌면 가장 넓은 폭 하나로 센다.
    """
    cur_total = sum(c.seen_cnt for c in chains if c.last_ym == n_quarters_end) or 1
    out = {}
    for lvl, key, _label in PNU_LEVELS:
        hit = [c for c in chains if c.pnu_lvl == lvl]
        cur = [c for c in hit if c.last_ym == n_quarters_end]
        out[key] = {"chains": len(hit), "current": len(cur),
                    "seen_pct": sum(c.seen_cnt for c in cur) / cur_total * 100}
    far = sorted((c for c in chains if c.pnu_lvl == 3), key=lambda c: (-c.seen_cnt, c.biz_no_last))[:3]
    examples = [(c.name_raw, c.pnu_move[0], c.pnu_move[1], c.first_ym, c.last_ym, c.seen_cnt) for c in far]
    return out, examples


def csv_cells(row):
    pnu, floor_no, name, biz, first, last, seen, cur, links, trunc = row
    return [pnu, "" if floor_no is None else str(floor_no), name, biz, first, last, str(seen),
            "t" if cur else "f", str(links), "t" if trunc else "f"]


def write_result(rows, path):
    """결과 csv 를 쓰고 (바이트, sha256) 를 돌려준다."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(OUT_COLUMNS)
        for r in rows:
            w.writerow(csv_cells(r))
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return os.path.getsize(path), h.hexdigest()


def meta_path_for(csv_path):
    base, _ext = os.path.splitext(csv_path)
    return base + ".meta.json"


def tenure_stats(seen_counts, n_quarters):
    """지금 보이는 가게의 seen_cnt 목록 → 중앙값 · 8분기 이상 % · 1분기째 % · 전부 %."""
    if not seen_counts:
        return {"n": 0, "median": None, "pct8": 0.0, "pct1": 0.0, "pct_full": 0.0}
    n = len(seen_counts)
    return {
        "n": n,
        "median": statistics.median(seen_counts),
        "pct8": sum(1 for x in seen_counts if x >= 8) / n * 100,
        "pct1": sum(1 for x in seen_counts if x == 1) / n * 100,
        "pct_full": sum(1 for x in seen_counts if x >= n_quarters) / n * 100,
    }


def judge_reproduction(k1, rule):
    """메인 풀이 ⓑ — (통과?, 이유 목록). k1·rule = tenure_stats 결과."""
    why = []
    if k1["median"] != REPRO_K1_MEDIAN:
        why.append("번호만 중앙값 {} ≠ {}".format(k1["median"], REPRO_K1_MEDIAN))
    if abs(k1["pct8"] - REPRO_K1_PCT8) > REPRO_K1_PCT8_TOL + 1e-9:
        why.append("번호만 8분기 이상 {:.2f}% 가 {}±{} 밖".format(k1["pct8"], REPRO_K1_PCT8, REPRO_K1_PCT8_TOL))
    lo, hi = REPRO_RULE_MEDIAN
    if rule["median"] is None or not lo <= rule["median"] <= hi:
        why.append("규칙 중앙값 {} 가 {}~{} 밖".format(rule["median"], lo, hi))
    lo, hi = REPRO_RULE_PCT8
    if not lo - 1e-9 <= rule["pct8"] <= hi + 1e-9:
        why.append("규칙 8분기 이상 {:.2f}% 가 {}~{} 밖".format(rule["pct8"], lo, hi))
    return (not why), why


# ── 읽기 반복 ────────────────────────────────────────────────────────────────


def run_quarters(quarters, sidos, books, log=print):
    """분기마다 zip 을 한 번 열고 시·도마다 csv 하나를 읽어 장부(books[sido] = [ChainBook…])에 넣는다.

    → 셈 합계 dict(read · short · bad_pnu · dup_biz_no). 한 분기 줄만 메모리에 둔다(캐시 없음).
    """
    csv.field_size_limit(FIELD_SIZE_LIMIT)
    total = collections.Counter()
    for ym, path in quarters:
        t0 = time.time()
        with zipfile.ZipFile(path) as zf:
            members = list_csv_members(zf)
            for sido in sidos:
                name, opener = pick_sido_csv(members, SIDO_NAMES[sido], ym)
                rows, counts = read_quarter_rows(opener, "{}:{}".format(os.path.basename(path), name))
                total.update(counts)
                for book in books[sido]:
                    st = book.step(ym, rows)
                log("  {} {} 줄 {:,} · 이어짐 {:,} · 끝남 {:,} · 새 {:,} · 3단 {:,} · {:.1f}초".format(
                    ym, SIDO_NAMES[sido], st["rows"], st["continued"], st["ended"], st["new"], st["linked"],
                    time.time() - t0))
    return dict(total)


# ── 메인 ─────────────────────────────────────────────────────────────────────


def parse_sido(text):
    out = tuple(s.strip() for s in text.split(",") if s.strip())
    bad = [s for s in out if s not in SIDO_NAMES]
    if not out or bad:
        raise BuildError("--sido 는 {} 중에서: {!r}".format(sorted(SIDO_NAMES), text))
    return out


def reproduce_c(zips, end_ym, limit, log=print):
    """--reproduce-c — 대전 42분기 · 두 규칙 표 · 판정. → exit 코드."""
    quarters = select_quarters(zips, REPRO_START_YM, end_ym)
    if limit:
        quarters = quarters[:limit]
    k1, rule = ChainBook(link=False), ChainBook(link=True)
    log("조사 C 재현 — 대전 · {}~{} · {}분기(201709 뺌)".format(quarters[0][0], quarters[-1][0], len(quarters)))
    run_quarters(quarters, (REPRO_SIDO,), {REPRO_SIDO: [k1, rule]}, log=log)
    n_q = len(quarters)
    s_k1 = tenure_stats([c.seen_cnt for c in k1.current()], n_q)
    s_rule = tenure_stats([c.seen_cnt for c in rule.current()], n_q)
    log("")
    log("오늘 가게(마지막 분기에 보이는 사슬) 번호만 {:,} · 규칙 {:,}".format(s_k1["n"], s_rule["n"]))
    log("| 규칙 | 중앙값 | 8분기 이상 | 1분기째 | {}분기 전부 | 조사 C (중앙값 · 8+ · 1 · 전부) |".format(n_q))
    for label, s in (("번호만", s_k1), ("번호 + 땅·층·상호", s_rule)):
        c = C_VALUES[label]
        log("| {} | {} | {:.1f}% | {:.1f}% | {:.1f}% | {} · {}% · {}% · {}% |".format(
            label, s["median"], s["pct8"], s["pct1"], s["pct_full"], *c))
    ok, why = judge_reproduction(s_k1, s_rule)
    log("규칙 n_links 합 {:,} · pnu 바뀜 {:,}".format(sum(c.n_links for c in rule.chains), rule.pnu_changed))
    log("판정: {}{}".format("통과" if ok else "실패", "" if ok else " — " + " · ".join(why)))
    return 0 if ok else 1


def build(zips, sidos, start_ym, end_ym, limit, out_path, today, log=print):
    """운영 모드 — 결과 csv + meta. → meta dict."""
    t0 = time.time()
    quarters = select_quarters(zips, start_ym, end_ym)
    if not quarters:
        raise BuildError("{}~{} 사이에 읽을 zip 이 없습니다".format(start_ym, end_ym))
    partial = bool(limit)
    if limit:
        quarters = quarters[:limit]
    first, last = quarters[0][0], quarters[-1][0]
    books = {s: [ChainBook(link=True)] for s in sidos}
    log("가게 이력 빌드 — {} · {}~{} · {}분기{}".format(
        "+".join(SIDO_NAMES[s] for s in sidos), first, last, len(quarters), " (partial)" if partial else ""))
    counts = run_quarters(quarters, sidos, books, log=log)
    chains = [c for s in sidos for c in books[s][0].chains]
    rows = out_rows(chains, first, last)
    size, digest = write_result(rows, out_path)
    current = [r for r in rows if r[7]]
    pk = collections.Counter((r[3], r[5]) for r in rows)
    moves, far = pnu_change_stats(chains, last)
    meta = {
        "built_on": today.isoformat(), "start_ym": first, "end_ym": last, "sido": list(sidos),
        "quarters": len(quarters), "rows": len(rows), "current_rows": len(current),
        "n_links": sum(r[8] for r in rows), "pnu_changed": sum(books[s][0].pnu_changed for s in sidos),
        "pnu_changed_same_sgg": moves["same_sgg"]["chains"],
        "pnu_changed_other_sgg": moves["other_sgg"]["chains"],
        "pnu_changed_other_sido": moves["other_sido"]["chains"],
        "dup_biz_no": counts.get("dup_biz_no", 0), "bad_pnu": counts.get("bad_pnu", 0),
        "partial": partial, "sha256": digest,
    }
    with io.open(meta_path_for(out_path), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    st = tenure_stats([r[6] for r in current], len(quarters))
    per_pnu = collections.Counter(r[0] for r in rows)
    per_pnu_cur = collections.Counter(r[0] for r in current)
    log("")
    log("사슬 {:,}(지금 보임 {:,}) · n_links 합 {:,} · pnu 바뀜 {:,} · 중복 번호 {:,} · 나쁜 pnu {:,} · 짧은 줄 {:,}".format(
        len(rows), len(current), meta["n_links"], meta["pnu_changed"], meta["dup_biz_no"], meta["bad_pnu"],
        counts.get("short", 0)))
    log("지금 보이는 사슬 seen_cnt 중앙값 {} · 8분기 이상 {:.1f}% · {}분기 전부(truncated) {:.1f}%".format(
        st["median"], st["pct8"], len(quarters), sum(1 for r in current if r[9]) / max(len(current), 1) * 100))
    log("(biz_no_last, last_ym) 겹침 {:,}(0 이어야 한다 — 한 분기에 같은 번호는 한 줄)".format(
        sum(1 for n in pk.values() if n > 1)))
    log("땅 번호가 바뀐 사슬(가장 넓은 폭 하나로 셈 · 바뀜 횟수 {:,}):".format(meta["pnu_changed"]))
    for _lvl, key, label in PNU_LEVELS:
        m = moves[key]
        log("  {} — 사슬 {:,} · 그중 지금 보임 {:,} · 지금 보이는 사슬 seen_cnt 합의 {:.2f}%".format(
            label, m["chains"], m["current"], m["seen_pct"]))
    for name, a, b, f_ym, l_ym, seen in far:
        log("  다른 시·도 예: {} · {} → {} · {}~{} · {}분기".format(name, a, b, f_ym, l_ym, seen))
    log("필지별 줄 수 최대 5: " + " · ".join(
        "{} {}줄(지금 {})".format(p, n, per_pnu_cur.get(p, 0)) for p, n in per_pnu.most_common(5)))
    log("csv {} · {:,}바이트 · meta {} · {:.0f}초".format(out_path, size, meta_path_for(out_path), time.time() - t0))
    return meta


def log_flush(*args):
    """긴 실행(약 15분)이 로그 파일에 바로바로 찍히게."""
    print(*args, flush=True)


def main(argv=None):
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="가게 이력 결과표 굽기(로컬 zip → csv + meta · DB 0)",
                                allow_abbrev=False)
    p.add_argument("--zip-dir", default=DEFAULT_ZIP_DIR)
    p.add_argument("--out", default=None, help="기본 data/derived/store_history/<오늘 YYYYMMDD>.csv")
    p.add_argument("--sido", default=",".join(DEFAULT_SIDO))
    p.add_argument("--start-ym", default=DEFAULT_START_YM)
    p.add_argument("--end-ym", default=None, help="기본 = zip 중 가장 늦은 분기")
    p.add_argument("--reproduce-c", action="store_true", help="조사 C 재현(대전 42분기 · 파일 쓰기 0 · 통과 0/실패 1)")
    p.add_argument("--limit-quarters", type=int, default=0, help="앞에서 N분기만(meta partial)")
    a = p.parse_args(argv)

    try:
        for label, v in (("--start-ym", a.start_ym), ("--end-ym", a.end_ym)):
            if v is not None and not RE_YM.match(v):
                raise BuildError("{} 는 YYYYMM(분기말 달)이어야 합니다: {!r}".format(label, v))
        if a.limit_quarters < 0:
            raise BuildError("--limit-quarters 는 0 이상")
        zips = list_quarter_zips(a.zip_dir)
        if not zips:
            raise BuildError("zip 이 없습니다: {}".format(a.zip_dir))
        end_ym = a.end_ym or zips[-1][0]
        if a.reproduce_c:
            return reproduce_c(zips, end_ym, a.limit_quarters, log=log_flush)
        sidos = parse_sido(a.sido)
        today = datetime.date.today()
        out = a.out or os.path.join(DEFAULT_OUT_DIR, today.strftime("%Y%m%d") + ".csv")
        build(zips, sidos, a.start_ym, end_ym, a.limit_quarters, out, today, log=log_flush)
    except (BuildError, OSError, zipfile.BadZipFile) as e:
        print("실패 — 결과 파일을 끝까지 쓰지 못했습니다: {}".format(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
