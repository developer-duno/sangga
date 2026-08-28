# -*- coding: utf-8 -*-
"""건축HUB 인허가 기본개요 zip → `arch_permit` 적재 (전국 한 방, 한 트랜잭션).

무엇을 넣나 — "곧 올라오는 건물"
--------------------------------
건축 허가를 받았지만 **아직 사용승인이 안 난** 건물이다. 인허가 기본개요 한 줄에
허가일·착공일·사용승인일이 같이 들어 있어서, **사용승인일이 빈 칸이면 아직 안 지어진
건물**이라는 뜻이 된다. 여기에 "최근 허가분"만 남기면 곧 생길 건물 목록이 된다.

  · 원본        건축HUB 대용량 파일, 분류 01 · opnTaskCd 0101 (전국·월간)
                `python scripts/collectors/fetch_bldrgst_bulk.py --kind permit-basis`
  · 2026-07 판  438,460,281 bytes zip · 안에 `mart_kcy_01.txt` 1개 · **6,498,901행**
  · 적재 대상   사용승인일 빈 값 **그리고** 허가일 2023-01-01 이상 → 실측 **556,551행**

⚠️ **월 1회 수동 갱신이다.** 건축HUB 일괄 파일은 **최근 3개월치만** 남으므로(메모리
   c-levers 실측) 받아 둔 zip 은 `python scripts/backup_raw.py` 로 반드시 백업한다.

왜 용도로 안 거르고 다 넣나
---------------------------
"상가"만 골라 넣으면 나중에 그 집합을 넓히거나 좁힐 때 **원본이 없어 다시 못 만든다**
(위의 3개월 보관). 표에는 미준공·최근 허가분을 통째로 담고, "무엇을 상가로 볼지"는
읽는 함수(`count_nearby_permits`) 한 곳에서만 정한다. 556,551행은 그래도 작다.

⛔ 함정 ① — `대지_구분_코드`는 PNU 대지구분과 코드가 다르다
------------------------------------------------------------
파일의 '0'이 PNU '1'(대지), '1'이 PNU '2'(산)다. 그대로 붙이면 PNU 가 통째로 어긋나
거의 다 남의 필지를 가리킨다. 이 레포는 같은 함정을 대장 변환기에서 이미 겪었으므로
(`convert_bldrgst_bulk.PLAT_GB_TO_PNU`, 2026-08-11 실측 727,585행 중 통과 132행) **그
매핑을 그대로 가져다 쓴다** — 사본을 만들면 언젠가 한쪽만 고쳐진다.

실측 분포(전국 6,498,901행): '0' 6,237,245 · '1' 169,259 · '2' 77,290(블록/특수지번) ·
빈값 15,097 · '3' 2 · '5' 8. 뒤의 넷은 지번이 없어 PNU 를 만들 수 없다 — 행은 담되
pnu 를 비워 둔다(버리지 않는다).

⛔ 함정 ② — 날짜 칸에 쓰레기가 섞여 있다
-----------------------------------------
원본에는 `'1999'`·`'1995 530'`·`'199301'`·`'2001 4 6'` 같은 옛 행이 있다. 그래서
**글자 비교로 거르면 안 된다** — `'9902' >= '20230101'` 은 글자로는 참이라 1990년대
행이 "최근 허가"로 딸려 들어온다(실측: 글자 비교로 세면 94행이 더 붙었다).
날짜로 바꿔 본 뒤 비교한다. 형식이 이상한 허가일은 **오류가 아니라 범위 밖**이다
(2023년 이후라고 말할 수 없는 값이므로) — 대신 몇 행인지 리포트에 적어 보여 준다.
반대로 **담기로 한 행 안**에 이상한 날짜가 있으면 그건 멈춘다(관문 ③).

⛔ 함정 ③ — 관리_허가대장_PK 는 bigint 에 안 들어간다
------------------------------------------------------
실측 길이 분포에 **22자리**가 794,704행 있다(`1000000000000000045934`). bigint 최대는
19자리라 그대로 넣으면 넘친다. 원본 정의도 VARCHAR(33)이므로 **text** 로 담는다.

쓰는 법
-------
    python scripts/collectors/load_arch_permits.py --dry-run     # DB 쓰기 0 (관문 리포트)
    python scripts/collectors/load_arch_permits.py               # 적재 (한 트랜잭션)

같은 기준월을 다시 넣으면 그 기준월 행을 먼저 지우므로 여러 번 돌려도 겹치지 않는다.
"""

import argparse
import csv
import datetime
import io
import os
import sys
import zipfile
from collections import Counter

COLLECTORS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(COLLECTORS_DIR)
for _p in (SCRIPTS_DIR, COLLECTORS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ⛔ 대지구분 매핑·블록지번 판정을 **사본으로 만들지 않는다** — 대장 변환기가 이미 실측으로
#    확정해 둔 것이고, 두 벌이 되면 언젠가 한쪽만 고쳐진다.
from convert_bldrgst_bulk import PLAT_GB_BLOCK, make_pnu  # noqa: E402

PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "arch_permit")
DEFAULT_STAGING_DIR = os.path.join(PROJECT_ROOT, "data", "staging", "arch_permit")

TABLE = "arch_permit"

# 원본 열 41개. 건축HUB '설명' 팝업(opnTaskCd=0101)의 colSn 순서 그대로이며, 2026-07 판
# 첫 줄들과 개수가 정확히 일치한다(41칸). 이름은 같은 자료의 API 필드명을 따른다 —
# 그래야 `convert_bldrgst_bulk.make_pnu` 가 손대지 않고 그대로 돈다.
PERMIT_COLS = (
    "mgmPmsrgstPk", "platPlc", "bldNm", "sigunguCd", "bjdongCd", "platGbCd", "bun", "ji",
    "splotNm", "block", "lot",
    "jimokCdNm", "jiyukCdNm", "jiguCdNm", "guyukCdNm",
    "jimokCd", "jiyukCd", "jiguCd", "guyukCd",
    "archGbCd", "archGbCdNm",
    "platArea", "archArea", "bcRat", "totArea", "vlRatEstmTotArea", "vlRat",
    "mainBldCnt", "atchBldCnt",
    "mainPurpsCd", "mainPurpsCdNm",
    "hhldCnt", "hoCnt", "fmlyCnt", "totPkngCnt",
    "stcnsSchedDay", "stcnsDelayDay", "realStcnsDay", "archPmsDay", "useAprDay", "crtnDay",
)

# 담기로 한 행 안에서 날짜여야 하는 칸들(관문 ③이 보는 대상).
DAY_FIELDS = ("realStcnsDay", "archPmsDay", "useAprDay", "crtnDay")

# 최근 허가분의 기준선. 이보다 오래된 허가는 "곧 올라온다"고 부르기 어렵다
# (2023 이후만 남겨도 55만 행이다 — 더 넓히면 옛 미준공 행이 대부분이 된다).
MIN_PERMIT_DAY = datetime.date(2023, 1, 1)

# 블록/특수지번을 뺀 나머지가 실제로 PNU 로 조립되는 비율의 하한.
# 실측 99.72%(빈값·'3'·'5' 같은 낯선 대지구분 15,107행이 분모에 남아 있어서 100% 는 아니다).
# 이 아래로 떨어지면 원본 형식이 바뀐 것이지 "원래 그런 것"이 아니다.
MIN_PNU_ASSEMBLY_RATE = 0.99

# CSV 로 넘길 열 순서 = \copy 의 열 목록 순서. 둘이 어긋나면 값이 옆 칸으로 들어간다.
CSV_COLUMNS = (
    "mgm_pmsrgst_pk", "pnu", "sigungu_cd", "plat_plc", "arch_gb_nm",
    "main_purps_cd", "main_purps_nm", "tot_area",
    "arch_pms_day", "real_stcns_day", "use_apr_day", "crtn_day", "loaded_ym",
)

PROGRESS_EVERY = 1_000_000
MAX_SAMPLES = 5


# ── 순수 함수 (파일·DB 없음 — 테스트 대상) ───────────────────────────────────


def make_item(cells):
    """`|`로 나눈 칸 목록 → 원본 필드 dict. 칸 수가 다르면 None(호출부가 센다)."""
    if len(cells) != len(PERMIT_COLS):
        return None
    return {name: cells[i].strip() for i, name in enumerate(PERMIT_COLS)}


def parse_day(value):
    """날짜 칸 하나 → (date 또는 None, 종류).

    종류는 'blank'(빈 값) · 'ok' · 'bad'(형식 이상) 셋이다. **셋을 구별하는 것이 요점**이다:
      · blank 인 사용승인일 = 아직 안 지어졌다 (우리가 찾는 것)
      · bad 인 사용승인일   = 지어지긴 했는데 날짜를 모른다 (우리가 찾는 것이 **아니다**)
    둘을 뭉개면 이미 다 지은 건물이 "곧 올라온다"고 화면에 뜬다.
    """
    text = (value or "").strip()
    if not text:
        return None, "blank"
    if len(text) != 8 or not text.isdigit():
        return None, "bad"
    try:
        return datetime.date(int(text[:4]), int(text[4:6]), int(text[6:8])), "ok"
    except ValueError:
        # 20230230 처럼 자릿수는 맞는데 달력에 없는 날. 여기서 안 걸면 \copy 가 통째로 실패한다.
        return None, "bad"


def is_target(item, min_day=MIN_PERMIT_DAY):
    """적재 대상인가. (통과여부, 사유) — 사유는 리포트 항목 이름이다.

    ⛔ 글자로 비교하지 않는다 — `'9902' >= '20230101'` 은 글자로는 참이라 1990년대
       쓰레기 행이 최근 허가로 딸려 들어온다(실측 94행).
    """
    _, ua_kind = parse_day(item.get("useAprDay"))
    if ua_kind != "blank":
        # 'ok'(준공됨)든 'bad'(준공 날짜가 이상함)든, 빈 값이 아니면 미준공이 아니다.
        return False, "use_approved"
    pms, pms_kind = parse_day(item.get("archPmsDay"))
    if pms_kind == "bad":
        # 오류가 아니라 **범위 밖**이다 — 2023년 이후라고 말할 수 없는 값이므로.
        return False, "permit_day_bad"
    if pms is None or pms < min_day:
        return False, "permit_day_old"
    return True, None


def parse_area(value):
    """연면적 → (float 또는 None, 정상 여부). 비어 있으면 (None, True)."""
    text = (value or "").strip()
    if not text:
        return None, True
    try:
        return float(text), True
    except ValueError:
        return None, False


def day_str(value):
    """CSV 에 넣을 'YYYY-MM-DD'. 빈 값은 None(= \\copy 에서 NULL)."""
    d, kind = parse_day(value)
    return d.isoformat() if kind == "ok" else None


def loaded_ym_of(path):
    """zip 이 놓인 폴더 이름(기준월 6자리)을 읽는다. 아니면 ValueError."""
    ym = os.path.basename(os.path.dirname(os.path.abspath(path)))
    if len(ym) != 6 or not ym.isdigit():
        raise ValueError(
            "기준월을 폴더 이름에서 못 읽었습니다: {!r}. "
            "zip 은 data/raw/arch_permit/<YYYYMM>/ 아래에 두거나 --loaded-ym 을 주세요.".format(ym))
    return ym


def make_row(item, loaded_ym):
    """원본 한 줄 → 적재용 dict. 값 변환만 하고 검증 결과는 Stats 가 모은다."""
    area, _ = parse_area(item.get("totArea"))
    return {
        "mgm_pmsrgst_pk": item.get("mgmPmsrgstPk") or None,
        # ⛔ 그대로 붙이지 말 것 — 대지구분 코드 체계가 다르다(머리말 함정 ①).
        "pnu": make_pnu(item),
        "sigungu_cd": item.get("sigunguCd") or None,
        "plat_plc": item.get("platPlc") or None,
        "arch_gb_nm": item.get("archGbCdNm") or None,
        "main_purps_cd": item.get("mainPurpsCd") or None,
        "main_purps_nm": item.get("mainPurpsCdNm") or None,
        "tot_area": area,
        "arch_pms_day": day_str(item.get("archPmsDay")),
        "real_stcns_day": day_str(item.get("realStcnsDay")),
        # 담는 행은 전부 빈 값이다(그것이 곧 '미준공'이다). 칸을 남겨 두는 이유는 표만 보고도
        # 그 뜻을 알 수 있게 하기 위해서다 — SQL 관문이 "전부 NULL 인가"를 다시 확인한다.
        "use_apr_day": day_str(item.get("useAprDay")),
        "crtn_day": day_str(item.get("crtnDay")),
        "loaded_ym": loaded_ym,
    }


def month_end(loaded_ym):
    """기준월의 마지막 날. 허가일이 이보다 뒤면 원본 오타다(그 달까지의 자료이므로).

    ⚠️ '오늘'로 재지 않는다 — 돌리는 날에 따라 답이 달라지면 같은 파일에서 다른 리포트가
       나온다(시간대·실행 시각 의존 금지).
    """
    if not (len(loaded_ym or "") == 6 and loaded_ym.isdigit()):
        raise ValueError("기준월이 6자리 숫자가 아닙니다: {!r}".format(loaded_ym))
    year, month = int(loaded_ym[:4]), int(loaded_ym[4:6])
    if month == 12:
        return datetime.date(year, 12, 31)
    return datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)


class Stats(object):
    """적재 전에 사람이 눈으로 볼 요약. 관문의 근거이기도 하다."""

    def __init__(self, max_day=None):
        # 이 날짜보다 뒤인 허가일은 원본 오타다. 세어서 보여만 준다(막지 않는다) —
        # 아래 format_report 주석 참조.
        self.max_day = max_day
        self.future_permit = 0
        self.future_samples = []
        self.rows = 0                 # 원본 전체 행수 (전국)
        self.col_mismatch = 0
        self.skipped = Counter()      # 사유별로 몇 행을 뺐나
        self.kept = 0
        self.pnu_ok = 0
        self.pnu_block = 0            # 블록/특수지번 — 지번이 없어 조립 불가가 **정상**
        self.pnu_bad = 0
        self.pnu_bad_gb = Counter()
        self.bad_days = Counter()     # 담은 행 안의 이상한 날짜 (관문 ③)
        self.bad_day_samples = []
        self.bad_area = 0
        self.bad_area_samples = []
        self.pk_missing = 0
        self.started = 0              # 실제 착공일이 있는 행
        self.by_purps = Counter()
        self.purps_nm = {}
        self.by_sido = Counter()
        self.by_permit_year = Counter()

    def add(self, item, row, where):
        self.kept += 1
        if not row["mgm_pmsrgst_pk"]:
            self.pk_missing += 1
        gb = item.get("platGbCd") or ""
        if row["pnu"] is not None:
            self.pnu_ok += 1
        elif gb == PLAT_GB_BLOCK:
            self.pnu_block += 1
        else:
            self.pnu_bad += 1
            self.pnu_bad_gb[gb or "(빈값)"] += 1
        for field in DAY_FIELDS:
            if parse_day(item.get(field))[1] == "bad":
                self.bad_days[field] += 1
                if len(self.bad_day_samples) < MAX_SAMPLES:
                    self.bad_day_samples.append(
                        "{}: {}={!r}".format(where, field, (item.get(field) or "")[:20]))
        if not parse_area(item.get("totArea"))[1]:
            self.bad_area += 1
            if len(self.bad_area_samples) < MAX_SAMPLES:
                self.bad_area_samples.append(
                    "{}: totArea={!r}".format(where, (item.get("totArea") or "")[:20]))
        if row["real_stcns_day"]:
            self.started += 1
        pms, kind = parse_day(item.get("archPmsDay"))
        if self.max_day is not None and kind == "ok" and pms > self.max_day:
            self.future_permit += 1
            if len(self.future_samples) < MAX_SAMPLES:
                self.future_samples.append(
                    "{}: {}".format(where, item.get("archPmsDay")))
        code = row["main_purps_cd"] or ""
        self.by_purps[code] += 1
        self.purps_nm.setdefault(code, row["main_purps_nm"] or "")
        self.by_sido[(row["sigungu_cd"] or "")[:2]] += 1
        self.by_permit_year[(row["arch_pms_day"] or "")[:4]] += 1

    @property
    def assemblable(self):
        """조립을 기대할 수 있는 분모 = 담은 행 − 블록/특수지번."""
        return self.kept - self.pnu_block

    @property
    def pnu_rate(self):
        return (self.pnu_ok / self.assemblable) if self.assemblable else 0.0


def assert_gates(stats):
    """적재 전 관문. 하나라도 걸리면 SQL 을 만들지 않는다 (DB 는 손도 안 댄다).

    ① 행수     — 원본을 못 읽었거나 담을 것이 하나도 없으면 형식이 바뀐 것이다
    ② 칸 수    — 41칸이 아닌 줄이 있으면 열 순서가 통째로 밀렸을 수 있다
    ③ 날짜     — **담기로 한 행 안**에 형식 이상이 있으면 멈춘다(범위 밖 행은 여기 안 온다)
    ④ 연면적   — 숫자가 아닌 값이 있으면 멈춘다(조용히 NULL 이 되면 아무도 못 찾는다)
    ⑤ 조립률   — 블록지번을 뺀 행은 사실상 다 조립돼야 한다
    """
    if stats.rows == 0:
        raise ValueError("원본에서 읽은 행이 0 입니다 — zip 안 파일 형식을 확인하세요.")
    if stats.kept == 0:
        raise ValueError(
            "담을 행이 0 입니다. 사용승인일이 빈 값이고 허가일이 {} 이상인 행이 하나도 "
            "없다는 뜻이라, 열 순서가 밀렸을 가능성이 큽니다.".format(MIN_PERMIT_DAY))
    if stats.col_mismatch:
        raise ValueError(
            "칸 수가 {}개가 아닌 줄이 {:,}개입니다 — 원본 열 구성이 바뀌었습니다. "
            "그대로 담으면 값이 옆 칸으로 들어갑니다.".format(
                len(PERMIT_COLS), stats.col_mismatch))
    if stats.bad_days:
        raise ValueError(
            "담기로 한 행 안에 날짜 형식이 이상한 칸이 있습니다: {} — 통째로 멈춥니다.\n"
            "  예: {}".format(
                dict(stats.bad_days), " / ".join(stats.bad_day_samples) or "(없음)"))
    if stats.bad_area:
        raise ValueError(
            "연면적이 숫자가 아닌 행이 {:,}개입니다 — 조용히 NULL 로 흘리지 않고 멈춥니다.\n"
            "  예: {}".format(stats.bad_area, " / ".join(stats.bad_area_samples)))
    if stats.pnu_rate < MIN_PNU_ASSEMBLY_RATE:
        raise ValueError(
            "PNU 조립률이 {:.3%} 입니다 (하한 {:.1%}). 블록/특수지번을 뺀 {:,}행 중 "
            "{:,}행만 조립됐습니다 — 대지구분·번지 형식이 바뀌었을 수 있습니다. "
            "낯선 대지구분: {}".format(
                stats.pnu_rate, MIN_PNU_ASSEMBLY_RATE, stats.assemblable, stats.pnu_ok,
                dict(stats.pnu_bad_gb) or "(없음)"))
    return True


def format_report(stats, top_purps=20):
    """dry-run 이 그대로 보여 주는 요약. 적재 뒤에도 같은 것을 본다.

    ⚠️ **원본 전체 행수를 반드시 함께 찍는다.** 통과 행수만 보여 주면, 원본이 반쯤 잘려
       들어와도 "55만 행 담았습니다"가 그럴듯해 보인다.
    """
    out = []
    out.append("  원본 전체        {:,}행 (전국)".format(stats.rows))
    for reason, label in (("use_approved", "사용승인이 났다(이미 지어짐)"),
                          ("permit_day_bad", "허가일 형식 이상 → 범위 밖"),
                          ("permit_day_old", "허가일이 {} 미만이거나 빈 값".format(
                              MIN_PERMIT_DAY))):
        out.append("    − {:<34} {:>10,}".format(label, stats.skipped.get(reason, 0)))
    out.append("  → 적재 대상      {:,}행  (미준공 + 최근 허가)".format(stats.kept))
    out.append("     실제 착공한 것 {:,}행".format(stats.started))
    out.append("  PNU: 조립 {:,} / 블록·특수지번 {:,}(지번 없음 — 정상) / 실패 {:,} {}".format(
        stats.pnu_ok, stats.pnu_block, stats.pnu_bad, dict(stats.pnu_bad_gb) or ""))
    out.append("     조립률 {:.3%} (하한 {:.1%}, 분모는 블록지번 제외 {:,}행)".format(
        stats.pnu_rate, MIN_PNU_ASSEMBLY_RATE, stats.assemblable))
    if stats.pk_missing:
        out.append("  ⚠️ 허가대장 PK 가 빈 행 {:,}".format(stats.pk_missing))
    out.append("  허가 연도:")
    for year, n in sorted(stats.by_permit_year.items()):
        out.append("    {:<6} {:>10,}".format(year or "(빈값)", n))
    if stats.future_permit:
        # ⚠️ 막지 않는다. 날짜만 오타일 뿐 **실재하는 미준공 허가**라, 버리면 진짜 건물이
        #    사라진다. 대신 몇 행인지 눈에 보이게 해 둔다(2026-07 판 실측 70행 = 0.013%).
        out.append("    ⚠️ 기준월 이후 허가일 {:,}행 — 원본 오타로 보인다(버리지 않고 담는다). "
                   "예: {}".format(stats.future_permit, " / ".join(stats.future_samples)))
    out.append("  주용도 상위 {}:".format(top_purps))
    for code, n in stats.by_purps.most_common(top_purps):
        out.append("    {:<8} {:<26} {:>10,}".format(
            code or "(빈값)", stats.purps_nm.get(code, ""), n))
    out.append("  시도별(시군구코드 앞 두 글자):")
    for code, n in sorted(stats.by_sido.items(), key=lambda kv: -kv[1]):
        out.append("    {:<6} {:>10,}".format(code or "(빈값)", n))
    return "\n".join(out)


def copy_path_literal(path):
    """psql `\\copy` 에 넘길 경로. 윈도우 역슬래시를 슬래시로 바꾸고 따옴표를 이스케이프한다."""
    return path.replace("\\", "/").replace("'", "''")


def build_sql(csv_path, loaded_ym, expected_rows):
    """적재 SQL. 한 트랜잭션이라 **중간에 실패하면 통째로 되돌린다.**

    ⚠️ 관문은 전부 `raise exception` 이라야 한다 — psql 은 select 가 몇 줄을 돌려주든
       종료코드 0 이라, 세어서 보여 주기만 하면 그대로 commit 된다.
    """
    if not (len(loaded_ym) == 6 and loaded_ym.isdigit()):
        raise ValueError("기준월이 6자리 숫자가 아닙니다: {!r}".format(loaded_ym))
    if expected_rows <= 0:
        raise ValueError("담을 행이 0 이라 SQL 을 만들지 않습니다.")

    return """begin;
set local statement_timeout = '7200s';

-- 같은 기준월을 다시 넣는 경우(월 1회 갱신)를 위해 먼저 지운다. 트랜잭션 안이라 뒤에서
-- 관문에 걸리면 이 삭제까지 통째로 되돌아간다.
delete from {table} where loaded_ym = '{ym}';

\\copy {table} ({cols}) from '{csv}' with (format csv, encoding 'UTF8')

-- ── 관문 ① 행수 대조 ────────────────────────────────────────────────────────
-- CSV 가 중간에 잘려도 \\copy 는 **에러 없이** 거기까지만 넣는다. 원본에서 읽은 수와
-- 맞춰 보는 것이 그걸 잡는 유일한 방법이다.
do $$
declare cnt bigint;
begin
  select count(*) into cnt from {table} where loaded_ym = '{ym}';
  if cnt <> {expected} then
    raise exception '넣은 행이 %개인데 원본에서 읽은 것은 {expected}개입니다 — 통째로 되돌립니다', cnt;
  end if;
end $$;

-- ── 관문 ② 이 표는 '아직 안 지어진 건물'만 담는다 ───────────────────────────
-- 사용승인일이 있는 행이 섞이면 화면이 이미 다 지은 건물을 "곧 올라온다"고 말한다.
-- 읽는 함수가 `use_apr_day is null` 로 다시 거르지만, 규칙을 한 군데에만 두지 않는다.
do $$
declare cnt bigint;
begin
  select count(*) into cnt from {table} where loaded_ym = '{ym}' and use_apr_day is not null;
  if cnt > 0 then
    raise exception '사용승인일이 있는 행 %개가 섞였습니다 — 통째로 되돌립니다', cnt;
  end if;
end $$;

-- ── 정보(막지 않는다) — 필지에 실제로 붙는 비율 ─────────────────────────────
-- 우리 parcel 표는 아직 전국을 다 담지 않았다. 여기서 낮게 나오는 것은 이 자료의 결함이
-- 아니라 우리 필지 적재 범위의 사실이라, 세어서 보여만 준다.
select count(*) as "넣은 행",
       count(*) filter (where pnu is not null) as "PNU 있는 행",
       count(*) filter (where pnu is not null
                          and exists (select 1 from parcel p where p.pnu = {table}.pnu))
         as "우리 필지에 붙는 행",
       count(*) filter (where real_stcns_day is not null) as "실제 착공한 행"
  from {table} where loaded_ym = '{ym}';

commit;

-- 갓 넣은 표는 통계도 가시성 지도도 없다. `analyze` 만으로는 부족하다 — 가시성 지도가
-- 비어 있으면 커버링 인덱스를 만들어 두고도 행마다 힙을 다시 읽는다(post_load.py 머리말의
-- 실측: Heap Fetches 232,890 → 0). 트랜잭션 안에서는 못 돌리므로 commit 뒤에 둔다.
vacuum (analyze) {table};
""".format(table=TABLE, ym=loaded_ym, cols=", ".join(CSV_COLUMNS),
           csv=copy_path_literal(csv_path), expected=expected_rows)


# ── 파일 읽기 (zip — 순수 함수 바깥) ──────────────────────────────────────────


def newest_zip(raw_dir):
    """가장 최근 기준월 폴더의 zip 하나를 고른다 (폴더명이 YYYYMM 이라 사전순 = 시간순)."""
    if not os.path.isdir(raw_dir):
        raise SystemExit(
            "원본 폴더가 없습니다: {}\n"
            "  python scripts/collectors/fetch_bldrgst_bulk.py --kind permit-basis".format(
                raw_dir))
    hits = []
    for root, _dirs, files in os.walk(raw_dir):
        for name in files:
            if name.lower().endswith(".zip"):
                hits.append(os.path.join(root, name))
    if not hits:
        raise SystemExit(
            "원본 zip 이 없습니다: {}\n"
            "  python scripts/collectors/fetch_bldrgst_bulk.py --kind permit-basis".format(
                raw_dir))
    return sorted(hits)[-1]


def open_text(zip_path):
    """zip 안 .txt 1개를 글자 스트림으로 연다. 1개가 아니면 멈춘다."""
    z = zipfile.ZipFile(zip_path)
    names = [i.filename for i in z.infolist() if i.filename.lower().endswith(".txt")]
    if len(names) != 1:
        z.close()
        raise SystemExit("zip 안 .txt 가 1개가 아닙니다: {}".format(names))
    return z, io.TextIOWrapper(z.open(names[0]), encoding="utf-8", errors="replace")


def transform(lines, out_csv, loaded_ym, limit=None, progress=None):
    """원본 줄을 훑으며 CSV 를 쓰고 요약을 모은다. (stats, 쓴 행수)

    ⭐ zip 을 모르는 함수다 — 줄 목록만 주면 되므로 테스트에서 그냥 리스트를 넘긴다.
    """
    stats = Stats(max_day=month_end(loaded_ym))
    written = 0
    with io.open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        for lineno, line in enumerate(lines, start=1):
            stats.rows += 1
            if progress and stats.rows % PROGRESS_EVERY == 0:
                progress(stats.rows, stats.kept)
            line = line.rstrip("\r\n")
            if not line:
                continue
            item = make_item(line.split("|"))
            if item is None:
                stats.col_mismatch += 1
                continue
            ok, reason = is_target(item)
            if not ok:
                stats.skipped[reason] += 1
                continue
            row = make_row(item, loaded_ym)
            stats.add(item, row, "{}행".format(lineno))
            writer.writerow([row[c] for c in CSV_COLUMNS])
            written += 1
            if limit and written >= limit:
                break
    return stats, written


def main(argv=None):
    # cp949 콘솔에서 한글·특수문자(—) 출력이 UnicodeEncodeError 로 죽지 않게 —
    # 형제 스크립트들(load_nts_base_price.py 등)과 같은 처방.
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="건축인허가 기본개요 zip → arch_permit 적재")
    p.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    p.add_argument("--zip", help="특정 zip 을 직접 지정")
    p.add_argument("--loaded-ym", help="기준월 6자리(생략하면 zip 이 놓인 폴더 이름)")
    p.add_argument("--staging-dir", default=DEFAULT_STAGING_DIR,
                   help="만들어진 CSV 를 두는 곳 (.gitignore 대상)")
    p.add_argument("--limit", type=int,
                   help="앞에서 N행만 담는다(빠른 점검용 — 적재에는 쓰지 말 것)")
    p.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않는다")
    p.add_argument("--sql-out", help="만들어진 SQL 을 이 파일로 저장(검토용)")
    a = p.parse_args(argv)

    print("=" * 74)
    print("건축인허가 기본개요 → {} 적재{}".format(TABLE, " — dry-run" if a.dry_run else ""))
    print("=" * 74)

    zip_path = a.zip or newest_zip(a.raw_dir)
    print("  원본 zip : {}  ({:,} bytes)".format(zip_path, os.path.getsize(zip_path)))
    try:
        loaded_ym = a.loaded_ym or loaded_ym_of(zip_path)
    except ValueError as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 2
    print("  기준월   : {}".format(loaded_ym))
    print("  대상 규칙: 사용승인일 빈 값 + 허가일 {} 이상".format(MIN_PERMIT_DAY))

    if not os.path.isdir(a.staging_dir):
        os.makedirs(a.staging_dir)
    csv_path = os.path.join(a.staging_dir, "arch_permit.csv")
    if a.limit:
        print("  ⚠️ --limit {:,} — 앞부분만 읽습니다. 적재에는 쓰지 마세요.".format(a.limit))
    print("  읽는 중...")

    def progress(rows, kept):
        print("    {:,}행 (담은 것 {:,})".format(rows, kept))
        sys.stdout.flush()

    z, lines = open_text(zip_path)
    try:
        stats, written = transform(lines, csv_path, loaded_ym,
                                   limit=a.limit, progress=progress)
    finally:
        z.close()

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
    print("  관문 통과 (행수 · 칸 수 · 날짜 · 연면적 · 조립률)")

    sql = build_sql(csv_path, loaded_ym, written)
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
