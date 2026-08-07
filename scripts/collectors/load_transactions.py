# -*- coding: utf-8 -*-
"""
상업업무용 실거래가 raw JSONL → Supabase 적재 (transaction) + §5.6 PNU 조립률 실측 보고

collect_transactions.py가 받아둔 raw를 읽어 transaction 테이블을 채우고,
`docs/상세계획.md` §5.6의 "실거래 → PNU 조립 성공률"을 실제로 재서 보고한다.
raw는 읽기만 한다 (CLAUDE.md 수집 규칙: raw 불변).

무엇을 하나:
  1. PNU 조립 — 실거래가 API에는 PNU가 없다(§4). 법정동명(umdNm)을 bjd_code로
     10자리 코드로 바꾸고, 지번(jibun)을 본번/부번으로 갈라 19자리를 만든다.
  2. 금액·면적·층 정규화 — 만원 단위 콤마 문자열을 원(bigint)으로, 층은 정수로.
  3. tx_id 생성 — 같은 raw를 몇 번을 적재해도 같은 값이 나오게(멱등).
  4. 적재 후 §5.6 조립률을 실측해 출력한다.

⚠️ 라이브 실측으로 확정한 것들 (2026-08-08, 강남 20년 23,599건) — 재조사 불필요:

  **① 지번 공개는 2024-01부터다.** 2023-12까지는 지번이 100% 마스킹('6**')이라
     PNU 조립이 원천 불가하다. 2024-01에 갑자기 68.6%가 정상으로 바뀐다(제도 변경).
     연도별 정상 비율: 2006~2023 전부 0.0% / 2024 63.7% / 2025 71.4% / 2026 73.6%.
     → **과거 백필(§5.3 3단계)로 받는 데이터에는 PNU를 붙일 수 없다.** 지역 단가
       시계열에는 쓸 수 있지만 필지·건물 단위 분석에는 못 쓴다. 백필 우선순위를
       정할 때 이 사실을 근거로 삼을 것.
     → 다행히 §5.3이 "시세 추정에는 최근 24개월만 쓴다"고 못박아 둬서, 정작 중요한
       구간은 전부 공개 범위 안이다.

  **② 통건물(일반)은 언제나 마스킹된다.** 2024-01 이후에도 일반 885건 전부
     마스킹이다. §5.6의 "통건물 조립 성공률은 낮을 것"의 답은 "낮은 게 아니라 0%".
     그래도 지역·면적·금액은 유효하므로 pnu NULL로 적재한다(스키마가 NULL 허용).

  **③ 2024-01 이후 집합건물 조립률 99.8% / 그중 parcel 매칭 92.3%** (목표 90%+).

  **④ JSON 응답의 필드 타입이 뒤죽박죽이다.** 같은 필드가 어떤 행은 문자열,
     어떤 행은 숫자로 온다 — jibun(str 23,030 / int 569), floor(str 12,099 /
     int 11,500), plottageAr(str/float/int), dealAmount(str 23,581 / int 18),
     buildYear·buildingAr·sggCd도 마찬가지. **반드시 str()로 감싸고 다뤄야 한다** —
     안 그러면 `'*' in jibun`에서 터지거나 조용히 어긋난다(실제로 분석 중 터졌다).

  **⑤ 지하층은 음수로 온다** ('-1'·'-2'·'-3', 1,435건). 우리 층 규칙과 그대로
     일치한다. 0층은 23,599건 중 0건. 층 결측은 51.3%(통건물이 대부분).

  **⑥ tx_id를 필드 조합 해시로만 만들면 안 된다.** (동·지번·날짜·금액·면적·층·유형)을
     전부 합쳐도 1,508조합 3,794행이 중복이다 — 같은 건물에서 같은 날 같은 값으로
     32건이 한꺼번에 팔리는 경우가 실재한다(분양·일괄매각). 그래서 조합 안에서의
     일련번호를 붙인다(make_tx_id 참조).

사용법:
  python scripts/collectors/load_transactions.py --dry-run
  python scripts/collectors/load_transactions.py
  python scripts/collectors/load_transactions.py --sigungu-code 11440
"""

import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

import requests
from dotenv import load_dotenv

# ── 설정 ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_SIGUNGU_CODE = "11680"   # 강남구 (§0.2 파일럿)
RAW_SUBDIR = "rtms"

# 지번이 공개되기 시작한 달. 이 전 거래는 PNU 조립이 원천 불가하다(위 ① 참조).
JIBUN_DISCLOSED_FROM_YM = "202401"

BATCH_SIZE = 1000
SELECT_PAGE_SIZE = 1000
TIMEOUT_SEC = 120

# §5.6 목표선
JOIN_RATE_TARGET = 90.0

TABLE_UPSERT_RESOLUTION = {
    "transaction": "merge-duplicates",
}


# ── 순수 로직 (네트워크·DB 없음 — 테스트 대상) ─────────────────────────────────


def s(value):
    """어떤 타입으로 오든 문자열로 정규화한다 (위 ④ — 타입이 행마다 다르다)."""
    return "" if value is None else str(value).strip()


def to_int(raw):
    """정수로. 빈값·형식 이상은 None."""
    t = s(raw).replace(",", "")
    if not t:
        return None
    try:
        return int(float(t))
    except ValueError:
        return None


def to_float(raw):
    t = s(raw).replace(",", "")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_deal_amount(raw):
    """거래금액 -> 원(bigint). API는 **만원 단위 + 콤마 문자열**로 준다.

    '136,000' -> 1,360,000,000원. 만원을 곱하지 않으면 금액이 1만분의 1이 되고,
    그 위에 세운 ㎡단가·시세 추정이 통째로 틀어진다.
    """
    t = s(raw).replace(",", "")
    if not t:
        return None
    try:
        man = int(float(t))
    except ValueError:
        return None
    return man * 10_000


def normalize_floor(raw):
    """층 -> 정수. 지하는 API가 이미 음수로 준다(위 ⑤).

    0은 절대 만들지 않는다 (CLAUDE.md 절대 규칙 4 / DB CHECK chk_tx_floor).
    실측상 0층은 0건이지만, 들어오면 결측으로 본다 — 지하와 결측이 섞이면 안 된다.
    """
    n = to_int(raw)
    if n is None or n == 0:
        return None
    return n


def split_jibun(raw):
    """지번 -> (산 여부, 본번, 부번). 마스킹·빈값·형식 이상은 None.

    '716' -> (False, 716, 0) / '14-1' -> (False, 14, 1) / '산3-2' -> (True, 3, 2)
    '6**' -> None  (2024-01 이전과 통건물은 이 형태다 — 위 ①②)
    """
    t = s(raw)
    if not t or "*" in t:
        return None
    is_san = t.startswith("산")
    body = t.lstrip("산").strip()
    bon, _, bu = body.partition("-")
    bon, bu = bon.strip(), (bu.strip() or "0")
    if not bon.isdigit() or not bu.isdigit():
        return None
    if len(bon) > 4 or len(bu) > 4:
        return None
    return is_san, int(bon), int(bu)


def make_pnu(bjd_code, jibun):
    """법정동코드(10) + 지번 -> PNU 19자리. 조립 불가면 None.

    PNU = 법정동코드(10) + 대지구분(1: 대지 / 2: 산) + 본번(4) + 부번(4).
    """
    code = s(bjd_code)
    if len(code) != 10 or not code.isdigit():
        return None
    parts = split_jibun(jibun)
    if parts is None:
        return None
    is_san, bon, bu = parts
    return "{}{}{:04d}{:04d}".format(code, "2" if is_san else "1", bon, bu)


def build_emd_lookup(bjd_rows, sigungu_code):
    """(bjd_code 행 목록) -> {읍면동명: 법정동코드}. 현행 코드를 우선한다.

    폐지 코드도 남겨 두는 테이블이라(§L0) 같은 이름이 현행·폐지 둘 다 있을 수 있다.
    실거래는 지금 시점의 주소 표기로 오므로 현행(is_active) 코드가 맞다.
    """
    lookup = {}
    for row in bjd_rows:
        if s(row.get("sigungu_code")) != s(sigungu_code):
            continue
        name = s(row.get("emd_nm"))
        code = s(row.get("bjd_code"))
        if not name or len(code) != 10:
            continue
        if row.get("is_active") or name not in lookup:
            lookup[name] = code
    return lookup


def make_tx_id(item, seq):
    """실거래 한 건의 영속 식별자. 같은 raw면 몇 번을 적재해도 같은 값이 나온다.

    필드 조합만으로는 유일해지지 않는다 — (동·지번·계약일·금액·면적·층·유형)을
    전부 합쳐도 강남 20년치에서 1,508조합 3,794행이 중복이다(같은 건물에서 같은
    날 같은 값으로 32건이 팔린 사례가 실재한다: 분양·일괄매각). 그래서 **그 조합
    안에서 몇 번째인가**(seq)를 뒤에 붙인다.

    ⚠️ 한계: 나중에 같은 조합의 거래가 하나 더 늘면 seq가 밀려 새 tx_id가 생기고
    옛 행이 남는다. 실거래는 과거가 바뀌지 않아 위험이 낮지만, 해제(cdealType)로
    빠지는 경우는 있으므로 재적재 시에는 그 시군구·그 계약년월 범위를 통째로
    다시 계산해 넣는 것을 전제로 한다.
    """
    key = "|".join(s(item.get(f)) for f in (
        "sggCd", "umdNm", "jibun", "dealYear", "dealMonth", "dealDay",
        "dealAmount", "buildingAr", "floor", "buildingType",
    ))
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return "{}-{}".format(digest, seq)


def is_canceled(item):
    """해제 신고된 거래인지. 시세 추정에서 반드시 빼야 한다(실측 4.0%)."""
    return s(item.get("cdealType")).upper() == "O"


def contract_ym(item):
    """계약년월 'YYYYMM'. 만들 수 없으면 None."""
    y, m = to_int(item.get("dealYear")), to_int(item.get("dealMonth"))
    if y is None or m is None or not 1 <= m <= 12:
        return None
    return "{:04d}{:02d}".format(y, m)


def build_transaction(item, emd_lookup, seq):
    """실거래 item 하나 -> transaction 테이블 upsert용 dict. 못 만들면 (None, 사유)."""
    ym = contract_ym(item)
    if ym is None:
        return None, "계약년월 없음"
    price = parse_deal_amount(item.get("dealAmount"))
    if price is None:
        return None, "거래금액 없음"
    sigungu = s(item.get("sggCd"))
    if len(sigungu) != 5 or not sigungu.isdigit():
        return None, "시군구코드 이상"

    emd_nm = s(item.get("umdNm")) or None
    pnu = make_pnu(emd_lookup.get(emd_nm), item.get("jibun")) if emd_nm else None

    return {
        "tx_id": make_tx_id(item, seq),
        "pnu": pnu,
        "bld_id": None,          # 실거래에는 건물 식별자가 없다 — 층·면적으로는 특정 불가
        "sigungu_code": sigungu,
        "emd_nm": emd_nm,
        "bld_nm": None,          # API가 건물명을 주지 않는다 (실측 확인)
        "floor_no": normalize_floor(item.get("floor")),
        "bld_area_m2": to_float(item.get("buildingAr")),
        "land_area_m2": to_float(item.get("plottageAr")),
        "price_won": price,
        "contract_ym": ym,
        "contract_day": to_int(item.get("dealDay")),
        "build_year": to_int(item.get("buildYear")),
        "tx_type": s(item.get("buildingType")) or None,
        "main_use": s(item.get("buildingUse")) or None,
    }, "적재"


def read_jsonl(path):
    """raw JSONL을 읽는다. 깨진 줄은 건너뛰고 개수만 센다."""
    rows, broken = [], 0
    if not os.path.exists(path):
        return rows, broken
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                broken += 1
    return rows, broken


def latest_batch(rows):
    """(시군구, 계약년월)마다 fetched_at이 가장 늦은 배치만 남긴다.

    raw는 append이므로 같은 달을 두 번 수집하면 두 배치가 쌓인다. 그대로 적재하면
    같은 거래가 두 번 세어져 건수·통계가 부풀어 오른다(2차 방어선 — 수집기가
    이미 원자적 append를 하지만, 재수집 자체는 정상 동작이라 여기서 걸러야 한다).
    """
    newest = {}
    for r in rows:
        k = (r.get("sigungu_code"), r.get("deal_ym"))
        f = r.get("fetched_at") or ""
        if k not in newest or f > newest[k]:
            newest[k] = f
    return [r for r in rows
            if (r.get("fetched_at") or "") == newest.get(
                (r.get("sigungu_code"), r.get("deal_ym")))]


def build_transactions(raw_rows, emd_lookup, include_canceled=False):
    """raw 행 목록 -> (transaction dict 목록, 통계).

    같은 (조합) 안에서의 일련번호는 **정렬된 순서**로 매긴다 — raw 줄 순서에
    의존하면 재수집 때 순서가 달라져 같은 거래에 다른 tx_id가 붙는다.
    """
    stats = Counter()
    reasons = Counter()
    grouped = defaultdict(list)

    for r in raw_rows:
        item = r.get("item") or {}
        stats["rows"] += 1
        if not include_canceled and is_canceled(item):
            stats["해제 거래 제외"] += 1
            continue
        key = "|".join(s(item.get(f)) for f in (
            "sggCd", "umdNm", "jibun", "dealYear", "dealMonth", "dealDay",
            "dealAmount", "buildingAr", "floor", "buildingType"))
        grouped[key].append(item)

    records = []
    for key in sorted(grouped):
        for seq, item in enumerate(grouped[key]):
            rec, why = build_transaction(item, emd_lookup, seq)
            reasons[why] += 1
            if rec is None:
                stats["변환 실패"] += 1
                continue
            records.append(rec)
            if rec["pnu"]:
                stats["PNU 조립 성공"] += 1
            else:
                stats["PNU 조립 실패"] += 1
            if rec["floor_no"] is not None:
                stats["층 있음"] += 1

    stats["적재 대상"] = len(records)
    return records, {"counts": stats, "reasons": reasons}


def assert_no_zero_floor(records):
    bad = [r for r in records if r.get("floor_no") == 0]
    if bad:
        raise RuntimeError(
            "층 0인 행이 {}건 있습니다 — 층 매핑을 확인하세요 (예: {}).".format(len(bad), bad[0]))
    return len(records)


def assert_unique(records, field="tx_id"):
    seen = set()
    for r in records:
        v = r.get(field)
        if v in seen:
            raise RuntimeError(
                "{} 값이 중복된 행이 있습니다 ({!r}) — upsert 전에 해결해야 합니다.".format(field, v))
        seen.add(v)
    return len(records)


def join_rate(matched, total):
    return (matched / total * 100) if total else 0.0


# ── Supabase(PostgREST) ──────────────────────────────────────────────────────


def get_supabase_config():
    load_dotenv()
    url = os.environ.get("SANGGA_SUPABASE_URL", "").strip().rstrip("/")
    key = (os.environ.get("SANGGA_SUPABASE_SERVICE_KEY")
           or os.environ.get("SANGGA_SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError(".env에 SANGGA_SUPABASE_URL과 키가 필요합니다.")
    return url, key


def rest_select(base_url, headers, table, query, page_size=SELECT_PAGE_SIZE, order="bjd_code"):
    rows, offset = [], 0
    while True:
        url = "{}/rest/v1/{}?{}order={}&limit={}&offset={}".format(
            base_url, table, (query + "&") if query else "", order, page_size, offset)
        r = requests.get(url, headers=headers, timeout=TIMEOUT_SEC)
        if r.status_code >= 300:
            raise RuntimeError("{} 조회 실패 (HTTP {}): {}".format(
                table, r.status_code, r.text[:300]))
        part = r.json()
        rows.extend(part)
        if len(part) < page_size:
            return rows
        offset += page_size


def upsert_batch(base_url, headers, table, rows, batch_size=BATCH_SIZE):
    resolution = TABLE_UPSERT_RESOLUTION.get(table)
    if resolution is None:
        raise RuntimeError("{} 테이블의 upsert 충돌 정책이 정의돼 있지 않습니다.".format(table))
    sent = 0
    total = (len(rows) + batch_size - 1) // batch_size
    for i in range(0, len(rows), batch_size):
        part = rows[i:i + batch_size]
        no = i // batch_size + 1
        try:
            r = requests.post(
                "{}/rest/v1/{}".format(base_url, table),
                headers=dict(headers, **{
                    "Content-Type": "application/json",
                    "Prefer": "resolution={},return=minimal".format(resolution),
                }),
                data=json.dumps(part, ensure_ascii=False).encode("utf-8"),
                timeout=TIMEOUT_SEC,
            )
        except requests.RequestException as e:
            raise RuntimeError("{} 저장 {}/{} 중 네트워크 오류: {}".format(table, no, total, e))
        if r.status_code >= 300:
            raise RuntimeError("{} 저장 {}/{} 실패 (HTTP {}): {}".format(
                table, no, total, r.status_code, r.text[:300]))
        sent += len(part)
        print("  [{}] {}/{} 배치 {:,}행 (누적 {:,}/{:,})".format(
            table, no, total, len(part), sent, len(rows)), flush=True)
    return sent


def assert_table_exists(base_url, headers, table):
    """적재 전에 대상 테이블이 라이브에 있는지 확인한다 (반쯤 적재 방지)."""
    r = requests.get("{}/rest/v1/{}".format(base_url, table),
                     params={"select": "*", "limit": "1"},
                     headers=headers, timeout=TIMEOUT_SEC)
    if r.status_code == 404:
        raise RuntimeError(
            "라이브 DB에 '{}' 테이블이 없습니다.\n"
            "       Supabase 대시보드 → SQL Editor에서 supabase/schema.sql을 먼저 적용하세요.".format(table))
    if r.status_code >= 300:
        raise RuntimeError("{} 조회 실패 (HTTP {}): {}".format(table, r.status_code, r.text[:200]))


# ── 보고 ─────────────────────────────────────────────────────────────────────


def print_transform_report(raw_path, broken, stats, record_count, records):
    counts = stats["counts"]
    print("=" * 78)
    print("실거래 raw → transaction 변환 결과")
    print("=" * 78)
    print("raw 파일: {}".format(raw_path))
    if broken:
        print("  [경고] 파싱 불가로 건너뛴 줄: {:,}".format(broken))
    print("")
    print("[ raw ] {:,}행".format(counts["rows"]))
    print("    해제 거래 제외        {:>8,}  (cdealType='O' — 시세 오염 방지)".format(
        counts["해제 거래 제외"]))
    print("    변환 실패            {:>8,}".format(counts["변환 실패"]))
    print("")
    print("[ transaction ] {:,}행 (would-upsert)".format(record_count))
    print("    PNU 조립 성공        {:>8,}  ({:.1f}%)".format(
        counts["PNU 조립 성공"], join_rate(counts["PNU 조립 성공"], record_count)))
    print("    PNU 조립 실패        {:>8,}  (지번 마스킹 — 2024-01 이전·통건물)".format(
        counts["PNU 조립 실패"]))
    print("    층 있음              {:>8,}  ({:.1f}%)".format(
        counts["층 있음"], join_rate(counts["층 있음"], record_count)))

    by_type = Counter(r["tx_type"] for r in records)
    print("    거래유형: " + " / ".join("{} {:,}".format(k, v) for k, v in by_type.most_common()))

    recent = [r for r in records if r["contract_ym"] >= JIBUN_DISCLOSED_FROM_YM]
    if recent:
        ok = sum(1 for r in recent if r["pnu"])
        print("")
        print("[ 지번 공개 구간({}~) ] {:,}행".format(JIBUN_DISCLOSED_FROM_YM, len(recent)))
        print("    PNU 조립 성공        {:>8,}  ({:.1f}%)".format(ok, join_rate(ok, len(recent))))
        jip = [r for r in recent if r["tx_type"] == "집합"]
        if jip:
            jok = sum(1 for r in jip if r["pnu"])
            verdict = "달성" if join_rate(jok, len(jip)) >= JOIN_RATE_TARGET else "미달"
            print("    집합만 보면          {:>8,}  ({:.1f}%)  [{}] 목표 {:.0f}%+".format(
                jok, join_rate(jok, len(jip)), verdict, JOIN_RATE_TARGET))
    print("=" * 78)


def print_join_report(base_url, headers, records, sigungu_code):
    """조립한 PNU가 실제로 parcel에 있는지 실측한다 (§5.6)."""
    parcels = {r["pnu"] for r in rest_select(
        base_url, headers, "parcel",
        "select=pnu&pnu=like.{}*".format(sigungu_code), order="pnu")}
    with_pnu = [r for r in records if r["pnu"]]
    matched = sum(1 for r in with_pnu if r["pnu"] in parcels)
    print("")
    print("=" * 78)
    print("§5.6 실거래 → 필지 매칭 실측")
    print("=" * 78)
    print("  parcel(그 시군구)          {:>8,}개".format(len(parcels)))
    print("  PNU가 붙은 거래            {:>8,}건".format(len(with_pnu)))
    print("  그중 parcel에 있는 거래     {:>8,}건  ({:.1f}%)".format(
        matched, join_rate(matched, len(with_pnu))))
    print("")
    print("  ※ parcel은 상권정보(점포가 있는 필지)에서 왔다 — 점포가 없는 건물의")
    print("     거래는 조립에 성공해도 parcel에 없을 수 있다. 이건 결함이 아니다.")
    print("=" * 78)


# ── 메인 ─────────────────────────────────────────────────────────────────────


def parse_args(argv):
    opts = {
        "sigungu_code": DEFAULT_SIGUNGU_CODE,
        "raw_dir": None,
        "dry_run": "--dry-run" in argv,
        "include_canceled": "--include-canceled" in argv,
    }
    for flag, key in (("--sigungu-code", "sigungu_code"), ("--raw-dir", "raw_dir")):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise ValueError("{} 뒤에 값이 필요합니다.".format(flag))
            opts[key] = argv[i + 1]
    if opts["raw_dir"] is None:
        opts["raw_dir"] = os.path.join(PROJECT_ROOT, "data", "raw", RAW_SUBDIR)
    return opts


def main():
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        opts = parse_args(sys.argv[1:])
    except ValueError as e:
        print("[에러] {}".format(e))
        return 2

    sigungu = opts["sigungu_code"]
    path = os.path.join(opts["raw_dir"], "{}.jsonl".format(sigungu))
    raw_rows, broken = read_jsonl(path)
    if not raw_rows:
        print("[에러] raw가 비어 있습니다: {}".format(path))
        print("       먼저 python scripts/collectors/collect_transactions.py 를 실행하세요.")
        return 1
    raw_rows = latest_batch(raw_rows)

    try:
        base_url, key = get_supabase_config()
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1
    headers = {"apikey": key, "Authorization": "Bearer {}".format(key)}

    print("법정동코드 읽는 중...", flush=True)
    bjd = rest_select(base_url, headers, "bjd_code",
                      "select=bjd_code,sigungu_code,emd_nm,is_active&sigungu_code=eq.{}".format(
                          sigungu))
    emd_lookup = build_emd_lookup(bjd, sigungu)
    print("  법정동 {}개".format(len(emd_lookup)))

    records, stats = build_transactions(raw_rows, emd_lookup, opts["include_canceled"])
    try:
        assert_no_zero_floor(records)
        assert_unique(records, "tx_id")
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    print_transform_report(path, broken, stats, len(records), records)

    if opts["dry_run"]:
        print("")
        print("--dry-run 지정 — DB 적재를 건너뜁니다.")
        return 0

    try:
        assert_table_exists(base_url, headers, "transaction")
        print("")
        print("적재 시작...", flush=True)
        sent = upsert_batch(base_url, headers, "transaction", records)
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    print("")
    print("=" * 78)
    print("적재 완료: transaction {:,}행".format(sent))
    print("=" * 78)

    try:
        print_join_report(base_url, headers, records, sigungu)
    except RuntimeError as e:
        print("[에러] 매칭 실측 실패: {}".format(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
