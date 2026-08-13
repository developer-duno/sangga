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

# delete_stale_transactions가 옛 tx_id를 정리할 때 쓰는 청크 크기.
# load_building_ledger.py의 STALE_PNU_CHUNK/STALE_DELETE_CHUNK와 같은 관례
# (URL 길이·요청 크기를 적당히 쪼갠다).
STALE_YM_CHUNK = 200
STALE_DELETE_CHUNK = 100

# collect_transactions.py의 COLLECTOR와 반드시 같은 문자열이어야 한다 — 두
# 스크립트는 서로 import하지 않는 관례라 상수를 각자 갖되 값을 맞춘다
# (load_building_ledger.py의 BLDRGST_COLLECTOR와 같은 관례).
RTMS_COLLECTOR = "rtms_commercial"


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

    ⚠️ 한계 (실측으로 정정 — 예전 문서는 틀렸었다): seq는 `build_transactions`가
    같은 그룹(조합) 안의 항목을 **내용으로 결정적 정렬**(`_stable_group_order`)한
    뒤 매긴다 — 이건 "raw 줄 순서가 재수집마다 달라져도 같은 결과가 나오게"만
    해줄 뿐, **그룹 멤버 수 자체가 바뀌면(해제로 하나 빠지는 등) seq는 여전히
    0..N-1로 재압축된다.** 즉 그룹이 3개(A,B,C)에서 2개(A,C)로 줄면 C는
    seq=2였다가 seq=1이 되어 **새 tx_id를 받는다** — 이건 정렬 방식과 무관하게
    "몇 번째"라는 정의 자체의 구조적 한계라 막을 수 없다. 그 결과 옛 tx_id(예:
    A-2)는 DB에 아무도 갱신 안 한 채 영구히 남을 수 있다 — 이 문제는 여기서
    막지 않고, `delete_stale_transactions`가 upsert 뒤에 "이번 빌드에 없는 옛
    tx_id"를 (시군구, 검증된 계약월) 범위 안에서 지워 해소한다.
    """
    key = "|".join(s(item.get(f)) for f in (
        "sggCd", "umdNm", "jibun", "dealYear", "dealMonth", "dealDay",
        "dealAmount", "buildingAr", "floor", "buildingType",
    ))
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return "{}-{}".format(digest, seq)


def _stable_group_order(items):
    """같은 조합(그룹) 안 항목들에 결정적 순서를 매긴다 (make_tx_id의 seq 근거).

    그룹핑 키(sggCd·umdNm·jibun·dealYear/Month/Day·dealAmount·buildingAr·floor·
    buildingType 10개)는 그룹 안 전원이 이미 동일하므로, 그룹핑에 **쓰이지 않은
    나머지 필드값 전부**를 정렬 키로 삼는다. raw 줄이 API 응답 배열의 물리적
    순서(재수집 때 달라질 수 있다)를 그대로 따르던 예전 방식과 달리, 항목
    자신의 내용만으로 순서가 정해지므로 같은 항목 집합이면 raw 파일 순서가
    바뀌어도 같은 seq가 나온다.

    남은 필드값까지 전부 같은 완전 동일 항목끼리는 tie — Python sort는 안정
    정렬이라 원래 리스트 순서로 묶인다. 이 경우는 무해하다: 두 항목이 tx_id를
    빼면 완전히 같은 내용이라 어느 쪽이 어느 seq를 받아도 결과 레코드는 같다.
    """
    return sorted(
        items,
        key=lambda item: tuple("{}={}".format(k, s(item.get(k))) for k in sorted(item.keys())),
    )


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


def verified_latest_batch(rows, done_counts):
    """latest_batch를 collect_progress.row_count로 검증해 안전하게 고른다.

    latest_batch는 (시군구, 계약년월)마다 fetched_at 최댓값만 본다. append_jsonl은
    한 회차의 아이템을 한 줄씩 순차로 쓰므로(collect_one_month), 그 쓰기 루프
    도중 프로세스가 죽으면 "가장 늦은 배치"가 일부 행만 쓰인 채로 raw에 남을 수
    있다. 그래도 latest_batch는 "시각이 가장 늦다"는 이유만으로 그 불완전한
    배치를 고르고, 온전했던 옛 배치를 밀어낸다(load_building_ledger.py의
    latest_batch_by_pnu와 같은 결함, 독립 코드리뷰 지적).

    done_counts는 (sigungu_code, deal_ym) -> row_count — 그 조합이 마지막으로
    온전히 끝났을 때 collect_progress에 저장된 행수다(fetch_done_row_counts가
    돌려주는 period_key 기준 dict를 호출부가 이 키 형태로 감싸 넘긴다). 후보
    fetched_at을 최신순으로 훑으며 그 배치의 행수가 done_counts와 일치하는 첫
    후보를 채택한다. 후보가 1개뿐이면(대다수 정상 케이스) 검증을 건너뛰고
    그대로 채택한다 — latest_batch와 동작·성능이 그대로다. 끝까지 일치하는
    후보가 없으면 최신 배치를 쓰되 조용히 넘어가지 않고 경고를 출력한다.
    """
    candidates = defaultdict(set)
    batch_counts = Counter()
    for r in rows:
        key = (r.get("sigungu_code"), r.get("deal_ym"))
        fetched_at = r.get("fetched_at") or ""
        candidates[key].add(fetched_at)
        batch_counts[(key, fetched_at)] += 1

    chosen = {}
    unverifiable = 0
    for key, fetched_ats in candidates.items():
        ordered = sorted(fetched_ats, reverse=True)
        if len(ordered) == 1:
            chosen[key] = ordered[0]
            continue
        expected = done_counts.get(key)
        picked = None
        if expected is not None:
            for fetched_at in ordered:
                if batch_counts[(key, fetched_at)] == expected:
                    picked = fetched_at
                    break
        if picked is None:
            picked = ordered[0]
            unverifiable += 1
        chosen[key] = picked

    if unverifiable:
        print("  [경고] {:,}개 (시군구,계약월) 조합은 여러 배치 중 어느 것이 온전한지 "
              "collect_progress로 확인할 수 없어 최신 배치를 그대로 씁니다.".format(
                  unverifiable), flush=True)

    return [r for r in rows
            if (r.get("fetched_at") or "") == chosen.get(
                (r.get("sigungu_code"), r.get("deal_ym")))]


def count_raw_rows_by_ym(raw_rows, sigungu_code):
    """이번 raw(검증된 배치 — verified_latest_batch를 거친 뒤)에서, 그 시군구의
    계약월(deal_ym)별 실제 행수.

    delete_stale_transactions가 `fetch_done_row_counts`(collect_progress가 기록한
    "수집 완료 시점 행수")와 대조해 "이번 실행이 그 계약월을 온전히 다시
    계산했는지" 판정하는 근거로 쓴다(load_building_ledger.py의
    count_raw_rows_by_pnu와 같은 역할 — 범위 단위만 PNU 대신 계약월).
    """
    counts = Counter()
    for r in raw_rows:
        if s(r.get("sigungu_code")) == s(sigungu_code):
            counts[s(r.get("deal_ym"))] += 1
    return dict(counts)


def build_transactions(raw_rows, emd_lookup, include_canceled=False):
    """raw 행 목록 -> (transaction dict 목록, 통계).

    그룹(조합) **사이**의 순서는 `sorted(grouped)`로, 그룹 **안**의 일련번호는
    `_stable_group_order`로 매긴다 — 어느 쪽도 raw 줄의 물리적(삽입) 순서에
    기대지 않는다. 단, 이건 "같은 항목 집합이면 항상 같은 tx_id가 나온다"만
    보장할 뿐 "항목이 하나 빠져도(해제 등) 옛 tx_id가 유지된다"는 보장은 아니다
    — 그건 seq 재압축이라는 구조적 한계라 여기서 못 막는다(make_tx_id 참조).
    실제로 남는 옛 행은 `delete_stale_transactions`가 정리한다.
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
        for seq, item in enumerate(_stable_group_order(grouped[key])):
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


def _pgrst_in_list(values):
    """PostgREST in.(...) 필터 문자열을 만든다. 각 값을 큰따옴표로 감싼다.

    tx_id는 해시+seq라 콤마·따옴표를 가질 일이 없지만, load_building_ledger.py의
    같은 이름 헬퍼와 관례를 맞춰 항상 감싼다(방어적 습관 — 언젠가 식별자 규칙이
    바뀌어도 안전하게).
    """
    quoted = ['"{}"'.format(str(v).replace("\\", "\\\\").replace('"', '\\"'))
              for v in values]
    return "in.({})".format(",".join(quoted))


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


def fetch_done_row_counts(base_url, headers, sigungu_code):
    """수집 완료(status='done') 계약년월(period_key) -> 수집 시점 row_count 매핑.

    verified_latest_batch가 "이번 raw로 그 달을 온전히 다시 계산했는가"를
    판정하는 근거다(load_building_ledger.py의 동명 함수와 같은 역할 —
    scope_key가 PNU 대신 시군구코드, period_key가 계약월인 점만 다르다).
    row_count가 비어 있는 행은 판정 근거가 없으므로 아예 뺀다.
    """
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=period_key,row_count&collector=eq.{}&scope_key=eq.{}&status=eq.done".format(
            RTMS_COLLECTOR, sigungu_code),
        order="period_key",
    )
    return {
        r["period_key"]: r["row_count"]
        for r in rows
        if r.get("period_key") and r.get("row_count") is not None
    }


def delete_stale_transactions(base_url, headers, records, sigungu_code, raw_row_counts,
                              dry_run=False, ym_chunk=STALE_YM_CHUNK,
                              delete_chunk=STALE_DELETE_CHUNK):
    """이번 빌드에 없는 옛 transaction 행을 지운다 (make_tx_id의 seq 재압축 결함 처방).

    ⚠️ 삭제 범위 = **정확히 이 실행의 시군구(sigungu_code) × "이번 raw가 온전히
    대표한다고 확인된" 계약월(contract_ym)만**이다. 다른 시군구나, 확인 안 된
    계약월의 행은 SELECT 조회 대상에도 안 들어가므로 절대 지워지지 않는다
    (load_building_ledger.py의 delete_stale_units/_delete_stale_rows와 완전히
    같은 원칙 — PNU 범위 한정 대신 시군구·계약월 범위 한정).

    "확인됨"의 기준: raw_row_counts(이번 raw에서 실제로 센 계약월별 행수 —
    count_raw_rows_by_ym 참조)가 collect_progress에 저장된 "수집 완료 시점
    행수"(fetch_done_row_counts)와 **정확히 일치**하는 계약월만 후보로 삼는다.
    일치 안 하거나 done 기록이 아예 없으면(원본이 일부 손상됐거나 raw_dir가
    부분집합일 수 있다) 그 계약월은 통째로 정리 대상에서 뺀다 — 모르면
    지우지 않는다.

    keep = 이번 빌드로 만든 전체 tx_id 집합. 해제(cdealType='O')로 빠진 거래는
    build_transactions가 애초에 레코드를 만들지 않으므로 keep에 안 들어가고,
    그래서 그 거래가 갖고 있던 옛 tx_id가 정리 대상에 잡힌다 — 이게 바로 이
    함수가 고치는 결함(재적재 때 표본 수가 조용히 부풀려지는 문제)의 해소책이다.

    호출 순서 전제 — 반드시 upsert 뒤에 부른다. 먼저 지우고 적재하다 중간에
    죽으면 데이터가 사라지지만, 적재 후 지우면 최악의 경우 중복이 잠깐 남을
    뿐이라 다시 실행하면 정리된다.

    dry_run=True면 지울 행 수를 세어(SELECT까지는 수행) 미리 보여주기만 하고
    실제 DELETE 요청은 보내지 않는다 — 반환값도 0이다(쓰기 0 보장).

    반환: 실제로 지운 행 수(dry_run=True면 항상 0).
    """
    if not records:
        return 0

    keep = {r["tx_id"] for r in records}
    done_counts = fetch_done_row_counts(base_url, headers, sigungu_code)
    yms = sorted(
        ym for ym, cnt in raw_row_counts.items()
        if done_counts.get(ym) == cnt
    )
    skipped = len(raw_row_counts) - len(yms)
    if skipped:
        print("  [transaction] 원본 완전성 미확인 계약월 {:,}개는 정리 대상에서 제외 "
              "(collect_progress done + row_count 일치인 계약월만 정리)".format(skipped),
              flush=True)
    if not yms:
        print("  [transaction] 정리 가능한 계약월 없음 — 옛 행 정리를 건너뜁니다", flush=True)
        return 0

    stale = []
    for i in range(0, len(yms), ym_chunk):
        part = yms[i:i + ym_chunk]
        rows = rest_select(
            base_url, headers, "transaction",
            "select=tx_id&sigungu_code=eq.{}&contract_ym=in.({})".format(
                sigungu_code, ",".join(part)),
            order="tx_id",
        )
        stale.extend(r["tx_id"] for r in rows if r["tx_id"] not in keep)

    if not stale:
        print("  [transaction] 정리할 옛 행 없음", flush=True)
        return 0

    if dry_run:
        print("  [transaction] --dry-run — 정리 대상 {:,}행 (실제 삭제는 하지 않습니다)".format(
            len(stale)), flush=True)
        return 0

    deleted = 0
    total_batches = (len(stale) + delete_chunk - 1) // delete_chunk
    for i in range(0, len(stale), delete_chunk):
        part = stale[i:i + delete_chunk]
        batch_no = i // delete_chunk + 1
        try:
            r = requests.delete(
                "{}/rest/v1/transaction".format(base_url),
                params={"tx_id": _pgrst_in_list(part)},
                headers=headers, timeout=TIMEOUT_SEC,
            )
        except requests.RequestException as e:
            raise RuntimeError(
                "transaction 옛 행 삭제 {}/{} 중 네트워크 오류: {}. 적재 자체는 끝났으므로 "
                "같은 명령을 다시 실행하면 남은 옛 행부터 정리합니다.".format(
                    batch_no, total_batches, e)
            )
        if r.status_code >= 300:
            raise RuntimeError(
                "transaction 옛 행 삭제 {}/{} 실패 (HTTP {}): {}. 적재 자체는 끝났으므로 "
                "같은 명령을 다시 실행하면 남은 옛 행부터 정리합니다.".format(
                    batch_no, total_batches, r.status_code, r.text[:300])
            )
        deleted += len(part)
        print("  [transaction] 옛 행 정리 {}/{} 배치 {}행 (누적 {:,}/{:,})".format(
            batch_no, total_batches, len(part), deleted, len(stale)), flush=True)
    return deleted


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


def _reject_unknown_args(argv, bool_flags, value_flags):
    """모르는 인자를 만나면 즉시 멈춘다.

    왜: 예전에는 인식 못 하는 인자를 조용히 무시하고 실행을 계속했다. 그래서
    `--help` 를 붙이면 dry_run=False 인 **실제 실행**이 되어 라이브 DB 쓰기가
    나갔고(2026-08-08 실제 발생), `--dryrun`·`--limitt 50` 같은 오타는
    "소량 시험"이 "전량 실행"으로 바뀐다. 조용한 오작동보다 시끄러운 중단이 낫다.
    """
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in value_flags:
            i += 2          # 값 하나를 건너뛴다 (값 누락은 기존 검사가 잡는다)
            continue
        if a in bool_flags:
            i += 1
            continue
        raise ValueError(
            "알 수 없는 인자: {!r}\n  쓸 수 있는 인자: {}".format(
                a, " ".join(sorted(set(bool_flags) | set(value_flags)))
            )
        )


def parse_args(argv):
    _reject_unknown_args(
        argv,
        bool_flags=("--dry-run", "--include-canceled"),
        value_flags=("--sigungu-code", "--raw-dir"),
    )
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

    try:
        base_url, key = get_supabase_config()
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1
    headers = {"apikey": key, "Authorization": "Bearer {}".format(key)}

    # raw가 재수집으로 여러 배치를 갖고 있으면, "가장 늦은 fetched_at"만 보는
    # latest_batch는 수집 도중 죽어 일부만 쓰인 배치를 온전한 배치로 착각할 수
    # 있다(B2, load_building_ledger.py와 같은 결함). collect_progress의 완료
    # 시점 행수로 검증해 안전한 배치를 고른다.
    try:
        done_row_counts = fetch_done_row_counts(base_url, headers, sigungu)
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1
    done_counts = {(sigungu, period_key): cnt for period_key, cnt in done_row_counts.items()}
    raw_rows = verified_latest_batch(raw_rows, done_counts)

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

    # delete_stale_transactions의 삭제 범위(시군구 × 검증된 계약월)를 정하는
    # 근거 — verified_latest_batch를 거친 이번 raw_rows에서 실제로 센 값이다.
    raw_row_counts = count_raw_rows_by_ym(raw_rows, sigungu)

    if opts["dry_run"]:
        print("")
        try:
            delete_stale_transactions(
                base_url, headers, records, sigungu, raw_row_counts, dry_run=True)
        except RuntimeError as e:
            print("[에러] 정리 대상 미리보기 실패: {}".format(e))
            return 1
        print("")
        print("--dry-run 지정 — DB 적재를 건너뜁니다.")
        return 0

    try:
        assert_table_exists(base_url, headers, "transaction")
        print("")
        print("적재 시작...", flush=True)
        sent = upsert_batch(base_url, headers, "transaction", records)
        # 적재 뒤에 정리한다 — 해제 등으로 그룹 멤버가 줄면 seq가 재압축돼 옛
        # tx_id가 남는다(make_tx_id 참조). 먼저 지우면 도중에 실패했을 때
        # 데이터가 사라지지만, 적재 후 지우면 최악의 경우 중복이 잠깐 남을
        # 뿐이라 재실행으로 정리된다.
        deleted = delete_stale_transactions(
            base_url, headers, records, sigungu, raw_row_counts)
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    print("")
    print("=" * 78)
    print("적재 완료: transaction {:,}행 (옛 행 정리 {:,}행)".format(sent, deleted))
    print("=" * 78)

    try:
        print_join_report(base_url, headers, records, sigungu)
    except RuntimeError as e:
        print("[에러] 매칭 실측 실패: {}".format(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
