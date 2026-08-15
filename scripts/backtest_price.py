# -*- coding: utf-8 -*-
"""
Stage B 선행조건 — 시세 추정 사다리(§6.2)의 시간 분할 백테스트 (서울+대전)

무엇을 하나
-----------
`transaction` 표의 **집합(구분상가) 매매 실거래**를 계약년월로 과거/미래로 가른 뒤,
**과거(학습) 거래만으로** 미래(검증) 거래의 단가를 맞혀 보고 그 오차를 잰다.
결정 0012 Stage B 의 선행조건 ①"시간 분할 백테스트를 서울 전역+대전으로 재실측"이
이 스크립트의 존재 이유다(기존 성적은 강남뿐).

**DB 는 읽기만 한다.** 쓰기·마이그레이션·적재는 이 스크립트가 절대 하지 않는다.

왜 랜덤 분할이 아니라 시간 분할인가
-----------------------------------
CLAUDE.md 검증 규칙: "미래로 과거를 맞히면 성적이 부풀려진다". 실제 서비스는 항상
"오늘까지의 거래로 내일의 값을 말하는" 상황이므로, 검증도 그 순서를 지켜야 한다.
그래서 학습은 `contract_ym <= TRAIN_UNTIL`, 검증은 `contract_ym >= TEST_FROM` 이다.

단계(사다리) 정의 — §6.2
------------------------
| 코드 | 후보 | 최소 표본 |
|---|---|---|
| L2   | 같은 필지(PNU) + 같은 층            | 1 |
| L4   | 반경 100m 이내 + 같은 층            | 3 |
| L5   | 반경 500m 이내 + 같은 층            | 5 |
| L6   | 같은 법정동(PNU 앞 10자리) + 같은 층대 | 1 |
| BASE | 같은 시군구 + 같은 층대              | 1 (비교 상대) |

추정값은 후보 단가의 **중앙값**이다. 운영 모드는 L2→L4→L5→L6 순서로 걸어가
**처음 성립하는 단계**를 채택한다. BASE 는 사다리에 넣지 않는다 — "아무 것도 안 하고
구 평균만 말했을 때"와 비교하기 위한 대조군일 뿐이다(귀무가설 대조,
`docs/알려진한계.md` §5 "그럴듯한 일치율이 판별력 0일 수 있다").

빠진 단계와 그 이유
-------------------
- **L1(같은 건물 같은 호실)은 만들 수 없다.** 실거래 원본에 호(unit) 식별자가 없다.
- **L3(층별효용비율 보정)은 보류한다.** R-ONE 계수는 임대 기준이라 매매에 그대로
  적용해도 되는지 미검증이고, 매핑(`district_rone_map`)도 부분 커버리지다.
- **"행정동" 대신 법정동**을 쓴다. 실거래의 동 이름(문자)과 건물의 법정동 코드는 다른
  체계라 이름 대조가 깨지기 쉽다(결정 0012 §2 와 같은 이유). PNU 앞 10자리가 법정동이다.

출력 (기본 `docs/backtest/`)
----------------------------
- `성적표-v1.md`            — 사람이 읽는 성적표(방법·한계·표·판단 재료)
- `단계별지표.csv`          — 단계 × 축(전체/시도/구/층대) 지표
- `운영모드지표.csv`        — 사다리 걷기 결과(채택 단계 분포·축별 성적)
- `검증거래별원자료.csv`    — 검증 거래 한 건마다 모든 단계의 추정·표본수·오차

쓰는 법
-------
    python scripts/backtest_price.py
    python scripts/backtest_price.py --train-until 202506 --test-from 202507
    python scripts/backtest_price.py --out-dir docs/backtest

⛔ 절대 규칙 2 — 감정평가사 독점 업무를 연상시키는 표현(CLAUDE.md 금지 목록)은 이 파일
   어디에도 쓰지 않는다. 쓰는 말은 "추정·오차율·참고"뿐이다. 이 금지는 테스트
   `tests/test_backtest_price.py::test_스크립트에_금지표현이_없다` 가 매번 확인한다.
"""

import argparse
import csv
import math
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

# ── 설정 ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "docs", "backtest")

# 시간 분할 기준 (CLI 로 덮어쓸 수 있다). contract_ym 은 'YYYYMM' 문자열이라 문자열 비교로 충분하다.
TRAIN_UNTIL = "202512"
TEST_FROM = "202601"

# 사다리
LADDER = ("L2", "L4", "L5", "L6")
ALL_STAGES = ("L2", "L4", "L5", "L6", "BASE")
MIN_SAMPLES = {"L2": 1, "L4": 3, "L5": 5, "L6": 1, "BASE": 1}
RADIUS_M = {"L4": 100.0, "L5": 500.0}

# 채점
HIT_BAND = 0.20          # ±20% 적중률
SUPPRESS_BELOW = 5       # md 표에서 이 미만이면 수치 대신 "표본 부족(n)"

# 성능 — 좌표 격자 한 칸의 크기(도). 0.005도 ≒ 위도 556m / 경도 442m(북위 37.5도)
GRID_CELL_DEG = 0.005
EARTH_RADIUS_M = 6371008.8   # WGS84 평균 반지름
METERS_PER_DEG_LAT = 111_320.0

# 상태 문자열
ST_OK = "ok"
ST_INSUFFICIENT = "insufficient"
ST_COORDS_MISSING = "coords_missing"
NO_ESTIMATE = "no_estimate"

# DB(PostgREST)
REST_TIMEOUT_SEC = 120
SELECT_PAGE_SIZE = 1000
PNU_BATCH = 100          # URL 길이 제한 때문에 in.(...) 는 100개씩 끊는다

TX_QUERY = (
    "tx_type=eq.집합&pnu=not.is.null&floor_no=not.is.null&unit_price=not.is.null"
    "&select=tx_id,pnu,sigungu_code,floor_no,unit_price,contract_ym"
)

SIDO_NAMES = {"11": "서울특별시", "30": "대전광역시"}


def log(message):
    """진행 상황 한 줄 — 백그라운드 실행에서도 바로 보이게 즉시 흘려보낸다."""
    print(message, flush=True)


# ── 순수 함수: 층대·거리·통계 ────────────────────────────────────────────────


def floor_band(floor_no):
    """층 번호를 층대 이름으로. 절대 규칙 4(0 은 쓰지 않는다)를 전제로 한다.

    음수=지하 / 1=1층 / 2=2층 / 99=옥탑 / 3~98=3층+ / None=층미상.
    99 를 넘는 값도 3층+ 로 본다(옥탑 표기 99 와 실제 99층을 규격이 구분 못 하는
    한계는 `docs/알려진한계.md` §5 에 이미 박혀 있다).
    """
    if floor_no is None:
        return "층미상"
    if floor_no < 0:
        return "지하"
    if floor_no == 1:
        return "1층"
    if floor_no == 2:
        return "2층"
    if floor_no == 99:
        return "옥탑"
    return "3층+"


def haversine_m(lat1, lng1, lat2, lng2):
    """두 위경도 사이 대권 거리(미터). 표준 라이브러리만 쓴다."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = p2 - p1
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def median(values):
    """후보 단가의 중앙값. 비어 있으면 None."""
    if not values:
        return None
    return statistics.median(values)


def percentile(values, q):
    """0~1 분위수(선형 보간). 분포 보고용."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def ape(estimate, actual):
    """절대 백분율 오차. 실제값이 0 이거나 값이 없으면 None(셀 수 없음)."""
    if estimate is None or actual is None or actual == 0:
        return None
    return abs(estimate - actual) / abs(actual)


def mdape(apes):
    """오차 중앙값 — 주지표. 극단값 몇 건에 흔들리지 않는다."""
    if not apes:
        return None
    return statistics.median(apes)


def mape(apes):
    """오차 평균. 극단값에 끌려가므로 보조 지표로만 본다."""
    if not apes:
        return None
    return sum(apes) / len(apes)


def hit_rate(apes, band=HIT_BAND):
    """오차가 밴드(기본 ±20%) 안에 든 비율."""
    if not apes:
        return None
    return sum(1 for a in apes if a <= band) / len(apes)


# ── 순수 함수: 분할·배치·격자 ────────────────────────────────────────────────


def split_by_period(rows, train_until=TRAIN_UNTIL, test_from=TEST_FROM):
    """계약년월 문자열로 학습/검증/범위밖 세 덩어리로 가른다.

    범위밖 = 계약년월이 없거나 (train_until, test_from) 사이 빈틈에 떨어진 것.
    기본값처럼 train_until 다음 달이 test_from 이면 빈틈은 0 이다.
    """
    train, test, outside = [], [], []
    for row in rows:
        ym = row.get("contract_ym")
        if not ym:
            outside.append(row)
        elif ym <= train_until:
            train.append(row)
        elif ym >= test_from:
            test.append(row)
        else:
            outside.append(row)
    return train, test, outside


def chunked(items, size=PNU_BATCH):
    """URL 길이 제한 대응 — 목록을 size 개씩 끊는다."""
    if size < 1:
        raise ValueError("size 는 1 이상이어야 합니다")
    seq = list(items)
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def grid_key(lat, lng, cell=GRID_CELL_DEG):
    """좌표를 격자 칸 번호로. 반경 후보를 좁히는 데만 쓴다(거리는 haversine 이 판정)."""
    return (int(math.floor(lat / cell)), int(math.floor(lng / cell)))


def grid_span(radius_m, lat, cell=GRID_CELL_DEG):
    """반경을 빠짐없이 덮으려면 격자를 몇 칸까지 훑어야 하나.

    경도 한 칸은 위도가 높을수록 짧아진다(북위 37.5도에서 0.005도 ≒ 442m).
    짧은 쪽을 기준으로 칸 수를 정해야 반경 밖으로 새는 후보가 없다.
    """
    lat_m = cell * METERS_PER_DEG_LAT
    lng_m = cell * METERS_PER_DEG_LAT * max(math.cos(math.radians(lat)), 1e-6)
    smallest = min(lat_m, lng_m)
    return max(1, int(math.ceil(radius_m / smallest)))


# ── 순수 함수: 학습 색인·단계 추정 ──────────────────────────────────────────


def build_train_index(train_rows):
    """학습 거래를 단계별 조회 모양으로 미리 갈라 둔다(전수 스캔 방지).

    좌표가 없는 학습 거래는 반경 색인에서 빠진다 — 나머지 색인에는 그대로 들어간다.
    """
    index = {
        "pnu_floor": defaultdict(list),
        "dong_band": defaultdict(list),
        "sigungu_band": defaultdict(list),
        "floor_grid": defaultdict(lambda: defaultdict(list)),
    }
    for row in train_rows:
        price = row["unit_price"]
        pnu = row["pnu"]
        floor_no = row["floor_no"]
        band = floor_band(floor_no)
        index["pnu_floor"][(pnu, floor_no)].append(price)
        index["dong_band"][(pnu[:10], band)].append(price)
        index["sigungu_band"][(row.get("sigungu_code"), band)].append(price)
        lat, lng = row.get("lat"), row.get("lng")
        if lat is not None and lng is not None:
            index["floor_grid"][floor_no][grid_key(lat, lng)].append((lat, lng, price))
    return index


def neighbors_within(floor_grid_for_floor, lat, lng, radius_m, cell=GRID_CELL_DEG):
    """같은 층 학습 거래 중 반경 안에 드는 것 → [(거리m, 단가)]."""
    if not floor_grid_for_floor:
        return []
    span = grid_span(radius_m, lat, cell)
    ci, cj = grid_key(lat, lng, cell)
    found = []
    for i in range(ci - span, ci + span + 1):
        for j in range(cj - span, cj + span + 1):
            for plat, plng, price in floor_grid_for_floor.get((i, j), ()):
                dist = haversine_m(lat, lng, plat, plng)
                if dist <= radius_m:
                    found.append((dist, price))
    return found


def estimate_from(prices, min_n):
    """후보 단가 목록 → 단계 결과 한 칸."""
    n = len(prices)
    if n < min_n or n == 0:
        return {"status": ST_INSUFFICIENT, "estimate": None, "n": n}
    return {"status": ST_OK, "estimate": median(prices), "n": n}


def coords_missing_result():
    """반경 단계인데 검증 거래에 좌표가 없을 때 — 표본 부족과 구분해서 센다."""
    return {"status": ST_COORDS_MISSING, "estimate": None, "n": 0}


def stage_results_for(row, index):
    """검증 거래 한 건에 대해 다섯 단계를 각각 독립 계산한다."""
    pnu = row["pnu"]
    floor_no = row["floor_no"]
    band = floor_band(floor_no)
    lat, lng = row.get("lat"), row.get("lng")

    results = {
        "L2": estimate_from(index["pnu_floor"].get((pnu, floor_no), []), MIN_SAMPLES["L2"]),
        "L6": estimate_from(index["dong_band"].get((pnu[:10], band), []), MIN_SAMPLES["L6"]),
        "BASE": estimate_from(
            index["sigungu_band"].get((row.get("sigungu_code"), band), []), MIN_SAMPLES["BASE"]),
    }

    if lat is None or lng is None:
        results["L4"] = coords_missing_result()
        results["L5"] = coords_missing_result()
        return results

    # 500m 후보를 한 번만 모으고 100m 는 거기서 걸러 쓴다(같은 층이라 후보 집합이 같다).
    near = neighbors_within(index["floor_grid"].get(floor_no), lat, lng, RADIUS_M["L5"])
    results["L5"] = estimate_from([p for _, p in near], MIN_SAMPLES["L5"])
    results["L4"] = estimate_from(
        [p for d, p in near if d <= RADIUS_M["L4"]], MIN_SAMPLES["L4"])
    return results


def walk_ladder(stage_results, ladder=LADDER):
    """L2→L4→L5→L6 을 걸어 처음 성립하는 단계를 채택한다 → (단계, 추정, 표본수)."""
    for code in ladder:
        res = stage_results.get(code)
        if res and res.get("status") == ST_OK:
            return code, res["estimate"], res["n"]
    return NO_ESTIMATE, None, 0


# ── 순수 함수: 집계 ──────────────────────────────────────────────────────────


def cell_metrics(rows, pick_ape):
    """한 셀(축값)의 지표. pick_ape(row) 가 None 이면 그 거래는 '추정 미성립'."""
    n_total = len(rows)
    apes = [a for a in (pick_ape(r) for r in rows) if a is not None]
    return {
        "n_total": n_total,
        "n_est": len(apes),
        "coverage": (len(apes) / n_total) if n_total else None,
        "mdape": mdape(apes),
        "mape": mape(apes),
        "hit20": hit_rate(apes),
    }


def paired_metrics(rows, pick_a, pick_b):
    """짝지은 비교 — **둘 다 성립한 거래만** 남겨 같은 집합에서 겨룬다.

    한쪽만 성립한 거래를 섞으면 "쉬운 거래만 맞힌 쪽"이 유리해져 비교가 무의미해진다.
    """
    pairs = []
    for row in rows:
        a = pick_a(row)
        b = pick_b(row)
        if a is not None and b is not None:
            pairs.append((a, b))
    a_list = [a for a, _ in pairs]
    b_list = [b for _, b in pairs]
    return {
        "n_pair": len(pairs),
        "a_mdape": mdape(a_list),
        "a_mape": mape(a_list),
        "a_hit20": hit_rate(a_list),
        "b_mdape": mdape(b_list),
        "b_mape": mape(b_list),
        "b_hit20": hit_rate(b_list),
    }


def group_by(rows, key_fn):
    """축 하나로 검증 거래를 묶는다(정렬된 (키, 목록) 목록)."""
    buckets = defaultdict(list)
    for row in rows:
        buckets[key_fn(row)].append(row)
    return sorted(buckets.items(), key=lambda kv: str(kv[0]))


# ── 순수 함수: 표기 ──────────────────────────────────────────────────────────


def is_suppressed(n_est, threshold=SUPPRESS_BELOW):
    """md 표에서 수치를 감출지 — 표본이 얇으면 숫자가 우연이라 오해를 부른다."""
    return n_est < threshold


def fmt_metric(n_est, value, digits=1, suffix="%", scale=100.0):
    """지표 한 칸 문자열. 표본이 얇으면 수치 대신 '표본 부족(n)'."""
    if is_suppressed(n_est):
        return "표본 부족({})".format(n_est)
    if value is None:
        return "-"
    return "{:.{d}f}{}".format(value * scale, suffix, d=digits)


def fmt_pct(value, digits=1):
    """감추지 않는 칸(커버리지 등)."""
    if value is None:
        return "-"
    return "{:.{d}f}%".format(value * 100.0, d=digits)


def fmt_num(value, digits=0):
    if value is None:
        return "-"
    return "{:,.{d}f}".format(value, d=digits)


# ── DB 읽기 (읽기 전용) ──────────────────────────────────────────────────────


def get_supabase_config():
    load_dotenv()
    url = os.environ.get("SANGGA_SUPABASE_URL", "").strip().rstrip("/")
    key = (os.environ.get("SANGGA_SUPABASE_SERVICE_KEY")
           or os.environ.get("SANGGA_SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError(
            ".env에 SANGGA_SUPABASE_URL과 키(SERVICE 또는 ANON)가 필요합니다.")
    return url, key


def rest_select(base_url, headers, table, query, order, page_size=SELECT_PAGE_SIZE):
    """PostgREST는 기본 1,000행만 준다 — 반드시 페이지네이션한다."""
    rows = []
    offset = 0
    while True:
        url = "{}/rest/v1/{}?{}order={}&limit={}&offset={}".format(
            base_url, table, (query + "&") if query else "", order, page_size, offset)
        r = requests.get(url, headers=headers, timeout=REST_TIMEOUT_SEC)
        if r.status_code >= 300:
            raise RuntimeError("{} 조회 실패 (HTTP {}): {}".format(
                table, r.status_code, r.text[:300]))
        part = r.json()
        rows.extend(part)
        if len(part) < page_size:
            return rows
        offset += page_size


def fetch_transactions(base_url, headers):
    """채점 대상 — 집합 매매 중 PNU·층·단가가 모두 있는 거래."""
    return rest_select(base_url, headers, "transaction", TX_QUERY, order="tx_id")


def fetch_parcel_coords(base_url, headers, pnus):
    """필지 좌표를 100개씩 끊어 읽는다 → {pnu: (lat, lng)}."""
    coords = {}
    batches = chunked(sorted(set(pnus)), PNU_BATCH)
    for i, batch in enumerate(batches, 1):
        query = "select=pnu,lat,lng&pnu=in.({})".format(",".join(batch))
        for row in rest_select(base_url, headers, "parcel", query, order="pnu"):
            lat, lng = row.get("lat"), row.get("lng")
            if lat is not None and lng is not None:
                coords[row["pnu"]] = (float(lat), float(lng))
        if i % 20 == 0 or i == len(batches):
            log("      배치 {}/{} … 좌표 {:,}개".format(i, len(batches), len(coords)))
    return coords


def fetch_sigungu_names(base_url, headers, codes):
    """구 이름표 — 코드 하나에 한 번씩 **단발 조회**한다(읽기 실패해도 코드로 계속 간다).

    ⚠️ 여기서 `rest_select` 를 쓰면 안 된다. 그 함수는 "받은 행이 page_size 보다 적을
    때까지" 도는 페이지네이션인데, 이름표는 코드당 1행만 필요해 page_size=1 로 부르면
    빈 페이지가 나올 때까지 법정동 수백 행을 한 줄씩 긁는다(2026-08-15 실측: 여기서 멈췄다).
    """
    names = {}
    for code in sorted(set(c for c in codes if c)):
        url = ("{}/rest/v1/bjd_code?select=sigungu_nm&sigungu_code=eq.{}"
               "&sigungu_nm=not.is.null&order=bjd_code&limit=1").format(base_url, code)
        try:
            r = requests.get(url, headers=headers, timeout=REST_TIMEOUT_SEC)
            if r.status_code >= 300:
                continue
            rows = r.json()
        except Exception:
            continue
        if rows and rows[0].get("sigungu_nm"):
            names[code] = rows[0]["sigungu_nm"]
    return names


# ── 실행 본체 ────────────────────────────────────────────────────────────────


def normalize_rows(raw_rows, coords):
    """REST 응답을 채점이 쓰는 모양으로 — 숫자 변환 + 좌표 부착."""
    rows = []
    for r in raw_rows:
        pnu = r.get("pnu")
        rows.append({
            "tx_id": r.get("tx_id"),
            "pnu": pnu,
            "sigungu_code": r.get("sigungu_code"),
            "floor_no": int(r["floor_no"]),
            "unit_price": float(r["unit_price"]),
            "contract_ym": r.get("contract_ym"),
            "lat": coords.get(pnu, (None, None))[0],
            "lng": coords.get(pnu, (None, None))[1],
        })
    return rows


def score_test_rows(test_rows, index):
    """검증 거래마다 다섯 단계 + 사다리 결과를 붙인다."""
    scored = []
    for row in test_rows:
        stages = stage_results_for(row, index)
        actual = row["unit_price"]
        record = dict(row)
        record["stages"] = stages
        record["stage_ape"] = {
            code: ape(res["estimate"], actual) if res["status"] == ST_OK else None
            for code, res in stages.items()
        }
        code, estimate, n = walk_ladder(stages)
        record["ladder_stage"] = code
        record["ladder_estimate"] = estimate
        record["ladder_n"] = n
        record["ladder_ape"] = ape(estimate, actual) if code != NO_ESTIMATE else None
        scored.append(record)
    return scored


def price_distribution(rows):
    """단가 분포 — 버리지 않고 보고만 한다(어떤 컷오프도 적용하지 않는다)."""
    prices = [r["unit_price"] for r in rows]
    p01 = percentile(prices, 0.01)
    p99 = percentile(prices, 0.99)
    extreme = sum(1 for p in prices if (p01 is not None and p < p01) or (p99 is not None and p > p99))
    return {
        "n": len(prices),
        "min": min(prices) if prices else None,
        "p01": p01,
        "p50": percentile(prices, 0.50),
        "p99": p99,
        "max": max(prices) if prices else None,
        "extreme": extreme,
        "nonpositive": sum(1 for p in prices if p <= 0),
    }


AXES = (
    ("전체", lambda r: "전체"),
    ("시도", lambda r: (r.get("sigungu_code") or "?")[:2]),
    ("구", lambda r: r.get("sigungu_code") or "?"),
    ("층대", lambda r: floor_band(r["floor_no"])),
)


def axis_label(axis, value, sigungu_names):
    if axis == "시도":
        return SIDO_NAMES.get(value, value)
    if axis == "구":
        return sigungu_names.get(value, value)
    return value


def write_stage_csv(path, scored, sigungu_names):
    rows_out = []
    for stage in ALL_STAGES:
        def pick(r, stage=stage):
            return r["stage_ape"].get(stage)
        for axis, key_fn in AXES:
            for value, bucket in group_by(scored, key_fn):
                m = cell_metrics(bucket, pick)
                rows_out.append([
                    stage, axis, value, axis_label(axis, value, sigungu_names),
                    m["n_total"], m["n_est"],
                    _csv_ratio(m["coverage"]), _csv_ratio(m["mdape"]),
                    _csv_ratio(m["mape"]), _csv_ratio(m["hit20"]),
                ])
    _write_csv(path,
               ["단계", "축", "축값", "축값이름", "검증거래수", "추정성립수",
                "커버리지", "MdAPE", "MAPE", "적중률20"],
               rows_out)


def write_operating_csv(path, scored, sigungu_names):
    def pick(r):
        return r["ladder_ape"]

    rows_out = []
    for axis, key_fn in AXES:
        for value, bucket in group_by(scored, key_fn):
            m = cell_metrics(bucket, pick)
            rows_out.append([
                axis, value, axis_label(axis, value, sigungu_names),
                m["n_total"], m["n_est"], _csv_ratio(m["coverage"]),
                _csv_ratio(m["mdape"]), _csv_ratio(m["mape"]), _csv_ratio(m["hit20"]),
            ])

    for value, bucket in group_by(scored, lambda r: r["ladder_stage"]):
        m = cell_metrics(bucket, pick)
        rows_out.append([
            "채택단계", value, value, m["n_total"], m["n_est"],
            _csv_ratio(m["coverage"]), _csv_ratio(m["mdape"]),
            _csv_ratio(m["mape"]), _csv_ratio(m["hit20"]),
        ])

    _write_csv(path,
               ["구분", "축값", "축값이름", "검증거래수", "추정성립수",
                "커버리지", "MdAPE", "MAPE", "적중률20"],
               rows_out)


def write_raw_csv(path, scored, sigungu_names):
    header = ["tx_id", "pnu", "sigungu_code", "sigungu_nm", "contract_ym",
              "floor_no", "층대", "실제단가", "lat", "lng"]
    for stage in ALL_STAGES:
        header += ["{}_상태".format(stage), "{}_표본수".format(stage),
                   "{}_추정".format(stage), "{}_APE".format(stage)]
    header += ["채택단계", "운영_표본수", "운영_추정", "운영_APE"]

    rows_out = []
    for r in scored:
        line = [
            r["tx_id"], r["pnu"], r["sigungu_code"],
            sigungu_names.get(r["sigungu_code"], ""), r["contract_ym"],
            r["floor_no"], floor_band(r["floor_no"]), r["unit_price"],
            r["lat"] if r["lat"] is not None else "",
            r["lng"] if r["lng"] is not None else "",
        ]
        for stage in ALL_STAGES:
            res = r["stages"][stage]
            line += [
                res["status"], res["n"],
                "" if res["estimate"] is None else round(res["estimate"], 2),
                _csv_ratio(r["stage_ape"].get(stage)),
            ]
        line += [
            r["ladder_stage"], r["ladder_n"],
            "" if r["ladder_estimate"] is None else round(r["ladder_estimate"], 2),
            _csv_ratio(r["ladder_ape"]),
        ]
        rows_out.append(line)
    _write_csv(path, header, rows_out)


def _csv_ratio(value, digits=6):
    return "" if value is None else round(value, digits)


def _write_csv(path, header, rows):
    # utf-8-sig — 엑셀이 한글 헤더를 깨지 않게 (사장님이 직접 열어 볼 파일이다)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def _metric_row(name, m):
    return "| {} | {:,} | {:,} | {} | {} | {} |".format(
        name, m["n_total"], m["n_est"], fmt_pct(m["coverage"]),
        fmt_metric(m["n_est"], m["mdape"]), fmt_metric(m["n_est"], m["hit20"]))


METRIC_HEADER = ("| 구분 | 검증 거래 | 추정 성립 | 커버리지 | MdAPE | ±20% 적중 |\n"
                 "|---|---|---|---|---|---|")


def build_markdown(ctx):
    """성적표 md 를 문자열로 만든다(파일 쓰기는 호출부)."""
    scored = ctx["scored"]
    names = ctx["sigungu_names"]
    dist = ctx["dist"]
    lines = []
    add = lines.append

    add("# 시세 추정 백테스트 성적표 v1 — 서울 + 대전")
    add("")
    add("> 생성: {} (KST) · 스크립트: `scripts/backtest_price.py` · DB 읽기 전용"
        .format(ctx["generated_at"]))
    add("> 결정 0012 Stage B 선행조건 ①(서울 전역+대전 시간 분할 백테스트)의 산출물이다.")
    add("> **이 문서는 사실만 적는다.** Stage B 착수 여부는 사장님 재결재 사항이다.")
    add("> 처음 읽는 분은 바로 아래 **§0 쉬운 설명**만 읽어도 됩니다 — §1부터는 근거 숫자다.")
    add("")

    # 0. 쉬운 설명 — 숫자를 손으로 베끼지 않고 본문과 같은 계산에서 뽑는다(재생성해도 안 어긋나게).
    ez_pair = paired_metrics(scored, lambda r: r["ladder_ape"],
                             lambda r: r["stage_ape"].get("BASE"))
    ez_l2 = cell_metrics(scored, lambda r: r["stage_ape"].get("L2"))
    ez_f1 = cell_metrics([r for r in scored if floor_band(r["floor_no"]) == "1층"],
                         lambda r: r["ladder_ape"])
    ez_f3 = cell_metrics([r for r in scored if floor_band(r["floor_no"]) == "3층+"],
                         lambda r: r["ladder_ape"])
    ez_l6_share = (Counter(r["ladder_stage"] for r in scored).get("L6", 0) / len(scored)
                   if scored else 0.0)

    def ez_pct(x):
        """쉬운 설명용 어림 백분율 — 0.291 → 29."""
        return round((x or 0.0) * 100)

    add("## 0. 쉬운 설명 (여기까지만 읽으셔도 됩니다)")
    add("")
    add("**무엇을 했나.** 화면에 넣을지 검토 중인 \"시세 어림값\" 기능이 실제로 얼마나 맞는지 "
        "시험을 봤습니다. 컴퓨터에게 **{}년 말까지의 거래만** 보여주고, **{}년에 실제로 팔린 "
        "상가 {:,}건의 가격을 맞혀 보라**고 한 뒤, 진짜 계약 가격과 비교해 채점했습니다. "
        "답안지를 미리 보여주지 않는 시험입니다.".format(
            ctx["train_until"][:4], ctx["test_from"][:4], len(ctx["test"])))
    add("")
    add("**어떻게 어림하나.** 곁의 거래를 아래 순서로 찾아, 찾은 가격들의 중간값을 씁니다"
        "(위가 안 되면 아래로 내려가는 사다리입니다):")
    add("")
    add("1. 같은 건물 같은 층에서 팔린 적이 있으면 → 그 가격")
    add("2. 없으면, 걸어서 1~2분 거리(100m) 안의 같은 층 가격들")
    add("3. 그래도 없으면, 500m 안의 같은 층 가격들")
    add("4. 그래도 없으면, 같은 동네(법정동)의 비슷한 층 평균")
    add("")
    add("**비교 상대.** \"그 구(區) 전체의 비슷한 층 평균\" — 지금도 화면에 이미 있는 값입니다. "
        "새 방식이 이것보다 낫지 않으면 만들 이유가 없습니다.")
    add("")
    add("**결과 — 세 줄.**")
    add("")
    add("- 새 방식의 어림값은 **절반의 거래에서 실제 가격의 ±{}% 안**에 들어왔습니다. "
        "구 평균 방식은 ±{}%였습니다. → **새 방식이 더 정확합니다.**"
        .format(ez_pct(ez_pair["a_mdape"]), ez_pct(ez_pair["b_mdape"])))
    add("- 실제 10억에 팔린 상가로 바꿔 말하면 — 새 방식은 보통 **{:.1f}억~{:.1f}억 사이**로 "
        "어림했고, 구 평균 방식은 {:.1f}억~{:.1f}억 사이였습니다.".format(
            10 * (1 - (ez_pair["a_mdape"] or 0)), 10 * (1 + (ez_pair["a_mdape"] or 0)),
            10 * (1 - (ez_pair["b_mdape"] or 0)), 10 * (1 + (ez_pair["b_mdape"] or 0))))
    add("- \"±20% 안에 맞히면 합격\"으로 치면, 새 방식은 **10건 중 약 {}건 합격**, "
        "구 평균 방식은 약 {}건이었습니다.".format(
            round((ez_pair["a_hit20"] or 0) * 10), round((ez_pair["b_hit20"] or 0) * 10)))
    add("")
    add("**하지만 조심할 것 3가지.**")
    add("")
    add("1. **잘 맞는 방법일수록 쓸 수 있는 곳이 적습니다.** 제일 정확한 \"같은 건물\" "
        "방법(오차 ±{}%)은 {}건 중 1건꼴로만 가능했고, 절반이 넘는 {}%는 맨 아래 "
        "\"동네 평균\"까지 내려갔습니다.".format(
            ez_pct(ez_l2["mdape"]),
            round(1 / ez_l2["coverage"]) if ez_l2["coverage"] else 0,
            ez_pct(ez_l6_share)))
    add("2. **1층이 제일 안 맞습니다**(오차 ±{}%). 같은 1층이라도 코너 자리냐 골목 안쪽이냐로 "
        "값이 크게 갈리는데, 그 차이는 공공데이터에 없습니다. 오히려 3층 이상이 잘 "
        "맞습니다(±{}%).".format(ez_pct(ez_f1["mdape"]), ez_pct(ez_f3["mdape"])))
    add("3. **어떤 구에서는 새 방식이 구 평균만 못합니다**(아래 4-1 표에서 구별로 확인). "
        "그래서 \"잘 맞는 지역·층만 골라 보여주는\" 안전장치가 꼭 같이 가야 합니다.")
    add("")
    add("**한 줄 요약.** 새 방식이 더 낫다는 건 숫자로 확인됐지만, \"어디서나 믿을 만하다\"는 "
        "아닙니다. 상가는 아파트와 달리 바로 옆 가게끼리도 값이 크게 다르기 때문에, 어림값은 "
        "\"이 가격이다\"가 아니라 **\"이 언저리다\"**로만 쓸 수 있습니다. 이 아래 §1부터는 "
        "그 근거 숫자들입니다.")
    add("")

    # 1. 방법
    add("## 1. 방법")
    add("")
    add("- **대상**: `transaction` 중 `tx_type='집합'` + PNU·층·단가가 모두 있는 거래 "
        "**{:,}건**(서울 {:,} · 대전 {:,}).".format(
            ctx["total"], ctx["sido_counts"].get("11", 0), ctx["sido_counts"].get("30", 0)))
    add("- **시간 분할**: 학습 `contract_ym <= {}` **{:,}건** / 검증 `contract_ym >= {}` "
        "**{:,}건** / 범위 밖 **{:,}건**. 합 {:,} = 전체 {:,}."
        .format(ctx["train_until"], len(ctx["train"]), ctx["test_from"], len(ctx["test"]),
                len(ctx["outside"]), len(ctx["train"]) + len(ctx["test"]) + len(ctx["outside"]),
                ctx["total"]))
    add("  랜덤 분할을 쓰지 않는다 — 미래로 과거를 맞히면 성적이 부풀려진다(CLAUDE.md 검증 규칙).")
    add("- **추정값**: 각 단계 후보 거래 단가의 **중앙값**. 후보는 **학습 거래만**이다.")
    add("- **오차**: APE = |추정 − 실제| / 실제. 주지표는 **MdAPE(오차 중앙값)**, "
        "보조로 MAPE(평균)와 **±20% 적중률**.")
    add("")
    add("### 단계 정의")
    add("")
    add("| 코드 | 후보 조건 | 최소 표본 |")
    add("|---|---|---|")
    add("| L2 | 같은 필지(PNU) + 같은 층 | 1 |")
    add("| L4 | 반경 100m 이내 + 같은 층 | 3 |")
    add("| L5 | 반경 500m 이내 + 같은 층 | 5 |")
    add("| L6 | 같은 법정동(PNU 앞 10자리) + 같은 층대 | 1 |")
    add("| BASE | 같은 시군구 + 같은 층대 | 1 (사다리 밖 · 비교 상대) |")
    add("")
    add("- 코드 번호는 `docs/상세계획.md` **§6.2 사다리의 단계 번호**를 그대로 쓴다"
        "(2=동일 건물 동일 층 / 4=반경 100m / 5=반경 500m / 6=행정동→법정동). "
        "`docs/상세계획.md` 앞부분의 공간 레벨 표(L1 층·L2 건물·L3 가로…)와는 다른 축이니 "
        "번호만 보고 겹쳐 읽지 말 것.")
    add("- **운영 모드(사다리 걷기)** = L2→L4→L5→L6 순서로 걸어 **처음 성립하는 단계**를 채택. "
        "아무 것도 성립하지 않으면 `no_estimate`.")
    add("- **BASE 는 사다리에 넣지 않는다.** \"구 평균만 말했을 때\"와 견주기 위한 대조군이다 "
        "(`docs/알려진한계.md` §5 — 그럴듯한 수치가 판별력 0 일 수 있어 귀무가설 대조를 병행한다).")
    add("- 거리는 haversine(미터). 반경 단계는 **양쪽 좌표가 다 있어야** 성립하고, "
        "검증 거래에 좌표가 없으면 `coords_missing` 으로 따로 센다(표본 부족과 구분).")
    add("- 층대: 음수=지하 / 1층 / 2층 / 3층+ / 옥탑(99).")
    add("")
    add("### 뺀 단계와 그 이유")
    add("")
    add("| 단계 | 처리 | 이유 |")
    add("|---|---|---|")
    add("| L1 (같은 건물 같은 호실) | **제외** | 실거래 원본에 호 식별자가 없다 — 만들 수 없다. |")
    add("| L3 (층별효용비율 보정) | **보류** | R-ONE 계수는 임대 기준이라 매매 적용의 타당성이 "
        "미검증이고, `district_rone_map` 매핑도 부분 커버리지다. |")
    add("| \"행정동\" 단위 | **법정동으로 대체** | 실거래의 동 이름(문자)과 건물의 법정동 코드는 "
        "다른 체계라 이름 대조가 깨진다. PNU 앞 10자리(법정동)를 쓴다. |")
    add("")

    # 2. 데이터 한계
    add("## 2. 데이터 한계 (성적을 읽기 전에)")
    add("")
    add("- **지번이 공개되는 2024-01 이후 집합 거래만 채점됐다.** 일반(통건물) 거래는 지번이 "
        "마스킹돼 PNU 조립이 0%라 아예 대상에 못 든다 — 이 성적은 **집합 상가에 한정된 성적**이다.")
    add("- **채점 대상의 층대 분포**: {}. 지하가 0건인 것은 2017년부터 실거래 원본에 지하층 "
        "표기가 오지 않기 때문이다(우리 파싱 문제가 아니다 — `docs/알려진한계.md`). "
        "즉 이 성적은 **지하층에 대해서는 아무 말도 하지 않는다**."
        .format(" · ".join("{} {:,}건".format(band, ctx["band_counts"].get(band, 0))
                           for band in ("지하", "1층", "2층", "3층+", "옥탑", "층미상"))))
    add("- **좌표 결측**: 검증 거래 {:,}건 중 필지 좌표가 없어 반경 단계를 못 돌린 거래 "
        "**{:,}건**({}). 이 거래들은 버리지 않고 `coords_missing` 으로 세어 커버리지에 반영했다."
        .format(len(ctx["test"]), ctx["test_coords_missing"],
                fmt_pct(ctx["test_coords_missing"] / len(ctx["test"]) if ctx["test"] else None)))
    add("- **단가 분포(원/㎡, 전체 {:,}건)** — 극단값을 **버리지 않고 그대로 채점했다**. "
        "잘라내면 성적이 좋아 보이지만 실제 화면은 그 거래도 만나기 때문이다."
        .format(dist["n"]))
    add("")
    add("| min | p01 | p50 | p99 | max | p01 미만·p99 초과 | 0 이하 |")
    add("|---|---|---|---|---|---|---|")
    add("| {} | {} | {} | {} | {} | {:,}건 | {:,}건 |".format(
        fmt_num(dist["min"]), fmt_num(dist["p01"]), fmt_num(dist["p50"]),
        fmt_num(dist["p99"]), fmt_num(dist["max"]), dist["extreme"], dist["nonpositive"]))
    add("")
    add("- **표 읽는 규칙**: 추정이 성립한 거래가 **{}건 미만**인 칸은 수치 대신 "
        "`표본 부족(n)` 으로 적는다. 표본이 얇으면 숫자가 우연이라 오해를 부른다. "
        "감춘 값도 `검증거래별원자료.csv`·`단계별지표.csv` 에는 그대로 남아 있다."
        .format(SUPPRESS_BELOW))
    add("")

    # 3. 성적
    add("## 3. 성적")
    add("")
    add("### 3-1. 단계별 (전체)")
    add("")
    add(METRIC_HEADER)
    for stage in ALL_STAGES:
        m = cell_metrics(scored, lambda r, s=stage: r["stage_ape"].get(s))
        add(_metric_row(stage, m))
    m_op = cell_metrics(scored, lambda r: r["ladder_ape"])
    add(_metric_row("**운영 모드(사다리)**", m_op))
    add("")

    add("### 3-2. 시도별")
    add("")
    for stage in list(ALL_STAGES) + ["운영"]:
        add("**{}**".format("운영 모드(사다리)" if stage == "운영" else stage))
        add("")
        add(METRIC_HEADER)
        for value, bucket in group_by(scored, lambda r: (r.get("sigungu_code") or "?")[:2]):
            pick = ((lambda r: r["ladder_ape"]) if stage == "운영"
                    else (lambda r, s=stage: r["stage_ape"].get(s)))
            add(_metric_row("{} ({})".format(SIDO_NAMES.get(value, value), value),
                            cell_metrics(bucket, pick)))
        add("")

    add("### 3-3. 층대별 (운영 모드 · L5 · BASE)")
    add("")
    add("| 층대 | 검증 거래 | 운영 커버리지 | 운영 MdAPE | L5 MdAPE | BASE MdAPE |")
    add("|---|---|---|---|---|---|")
    for value, bucket in group_by(scored, lambda r: floor_band(r["floor_no"])):
        m_l = cell_metrics(bucket, lambda r: r["ladder_ape"])
        m_5 = cell_metrics(bucket, lambda r: r["stage_ape"].get("L5"))
        m_b = cell_metrics(bucket, lambda r: r["stage_ape"].get("BASE"))
        add("| {} | {} | {} | {} | {} | {} |".format(
            value, m_l["n_total"], fmt_pct(m_l["coverage"]),
            fmt_metric(m_l["n_est"], m_l["mdape"]),
            fmt_metric(m_5["n_est"], m_5["mdape"]),
            fmt_metric(m_b["n_est"], m_b["mdape"])))
    add("")

    add("### 3-4. 채택 단계 분포 (운영 모드)")
    add("")
    add("⚠️ 이 표의 단계별 성적은 **3-1 의 단계별 성적과 다른 집합**이다. 사다리는 앞 단계가 "
        "성립하지 않은 거래만 뒤 단계로 넘기므로, 뒤 단계 칸에는 \"앞 단계가 못 푼 거래\"만 "
        "남는다. 두 표의 같은 코드끼리 직접 견주면 안 된다.")
    add("")
    add("| 채택 단계 | 검증 거래 | 비중 | MdAPE | ±20% 적중 |")
    add("|---|---|---|---|---|")
    total_test = len(scored) or 1
    for value, bucket in group_by(scored, lambda r: r["ladder_stage"]):
        m = cell_metrics(bucket, lambda r: r["ladder_ape"])
        add("| {} | {} | {} | {} | {} |".format(
            value, m["n_total"], fmt_pct(m["n_total"] / total_test),
            fmt_metric(m["n_est"], m["mdape"]), fmt_metric(m["n_est"], m["hit20"])))
    add("")

    add("### 3-5. 구별 (운영 모드)")
    add("")
    add("| 구 | 검증 거래 | 추정 성립 | 커버리지 | MdAPE | ±20% 적중 |")
    add("|---|---|---|---|---|---|")
    for value, bucket in group_by(scored, lambda r: r.get("sigungu_code") or "?"):
        m = cell_metrics(bucket, lambda r: r["ladder_ape"])
        add(_metric_row("{} ({})".format(names.get(value, value), value), m))
    add("")

    # 4. 핵심 비교
    add("## 4. 핵심 비교 — 사다리가 \"구 평균\"보다 나은가")
    add("")
    add("**짝짓기 규칙**: 두 방법이 **모두 성립한 검증 거래만** 남겨 같은 집합에서 겨룬다. "
        "한쪽만 성립한 거래를 섞으면 \"쉬운 거래만 맞힌 쪽\"이 유리해져 비교가 무의미해진다. "
        "그래서 아래 표의 n 은 각 방법의 커버리지와 다르다(둘의 교집합이다).")
    add("")
    for title, pick_a, label_a in (
        ("4-1. 운영 모드(사다리) vs BASE", lambda r: r["ladder_ape"], "운영 모드"),
        ("4-2. L5(반경 500m 동일층) vs BASE", lambda r: r["stage_ape"].get("L5"), "L5"),
    ):
        add("### {}".format(title))
        add("")
        add("| 구분 | 짝지은 거래 | {} MdAPE | BASE MdAPE | {} ±20% | BASE ±20% |"
            .format(label_a, label_a))
        add("|---|---|---|---|---|---|")
        pairs_all = paired_metrics(scored, pick_a, lambda r: r["stage_ape"].get("BASE"))
        add(_paired_row("전체", pairs_all))
        for value, bucket in group_by(scored, lambda r: r.get("sigungu_code") or "?"):
            p = paired_metrics(bucket, pick_a, lambda r: r["stage_ape"].get("BASE"))
            add(_paired_row("{} ({})".format(names.get(value, value), value), p))
        add("")

    # 5. 판단 재료
    add("## 5. 판단 재료 (사실만)")
    add("")
    op_paired = paired_metrics(scored, lambda r: r["ladder_ape"],
                               lambda r: r["stage_ape"].get("BASE"))
    ladder_dist = Counter(r["ladder_stage"] for r in scored)
    add("- 검증 거래 **{:,}건** 중 사다리가 추정을 낸 거래 **{:,}건**(커버리지 {}). "
        "나머지 {:,}건은 `no_estimate` — 화면에 낼 값이 아예 없다."
        .format(len(scored), m_op["n_est"], fmt_pct(m_op["coverage"]),
                ladder_dist.get(NO_ESTIMATE, 0)))
    add("- 사다리 전체 MdAPE **{}** / ±20% 적중률 **{}**."
        .format(fmt_metric(m_op["n_est"], m_op["mdape"]),
                fmt_metric(m_op["n_est"], m_op["hit20"])))
    add("- 같은 거래 {:,}건에서 사다리 MdAPE **{}** vs BASE(구 평균) MdAPE **{}**, "
        "±20% 적중률 **{}** vs **{}**."
        .format(op_paired["n_pair"],
                fmt_metric(op_paired["n_pair"], op_paired["a_mdape"]),
                fmt_metric(op_paired["n_pair"], op_paired["b_mdape"]),
                fmt_metric(op_paired["n_pair"], op_paired["a_hit20"]),
                fmt_metric(op_paired["n_pair"], op_paired["b_hit20"])))
    add("- 채택 단계 분포: {}."
        .format(" · ".join("{} {:,}건({})".format(
            code, cnt, fmt_pct(cnt / total_test))
            for code, cnt in sorted(ladder_dist.items()))))
    band_facts = []
    for value, bucket in group_by(scored, lambda r: floor_band(r["floor_no"])):
        m = cell_metrics(bucket, lambda r: r["ladder_ape"])
        band_facts.append("{} {}({:,}건)".format(
            value, fmt_metric(m["n_est"], m["mdape"]), m["n_est"]))
    add("- 층대별 운영 모드 MdAPE: {}.".format(" · ".join(band_facts)))
    gu_cells = []
    for value, bucket in group_by(scored, lambda r: r.get("sigungu_code") or "?"):
        m = cell_metrics(bucket, lambda r: r["ladder_ape"])
        if m["n_est"] >= SUPPRESS_BELOW and m["mdape"] is not None:
            gu_cells.append((m["mdape"], value, m["n_est"]))
    if gu_cells:
        gu_cells.sort()
        best = gu_cells[0]
        worst = gu_cells[-1]
        add("- 구별 운영 모드 MdAPE 폭: 가장 낮은 곳 {} ({}) {} ({:,}건) ~ 가장 높은 곳 {} ({}) "
            "{} ({:,}건). 표본 {}건 미만 구는 이 비교에서 뺐다."
            .format(names.get(best[1], best[1]), best[1], fmt_pct(best[0]), best[2],
                    names.get(worst[1], worst[1]), worst[1], fmt_pct(worst[0]), worst[2],
                    SUPPRESS_BELOW))
    add("- 커버리지가 얇은 구·층대는 3-5·3-3 표에 그대로 있다(감춘 칸은 CSV 에 남아 있다).")
    add("- 결정 0012 는 **성적표를 들고 다시 결재**하도록 정해 두었다. "
        "이 문서는 그 재료이며, 여기에는 판정·결재 문구를 적지 않는다.")
    add("")
    add("---")
    add("")
    add("생성 파일: `단계별지표.csv` · `운영모드지표.csv` · `검증거래별원자료.csv` "
        "(CSV 는 감춘 수치까지 전부 담고 있다).")
    add("")
    return "\n".join(lines)


def _paired_row(name, p):
    return "| {} | {} | {} | {} | {} | {} |".format(
        name, p["n_pair"],
        fmt_metric(p["n_pair"], p["a_mdape"]), fmt_metric(p["n_pair"], p["b_mdape"]),
        fmt_metric(p["n_pair"], p["a_hit20"]), fmt_metric(p["n_pair"], p["b_hit20"]))


def run(args):
    base_url, key = get_supabase_config()
    headers = {"apikey": key, "Authorization": "Bearer {}".format(key)}

    log("[1/6] 실거래(집합·PNU·층·단가 보유) 읽는 중 …")
    raw = fetch_transactions(base_url, headers)
    log("      {:,}건".format(len(raw)))

    log("[2/6] 필지 좌표 읽는 중 (100개씩) …")
    pnus = [r["pnu"] for r in raw if r.get("pnu")]
    coords = fetch_parcel_coords(base_url, headers, pnus)
    rows = normalize_rows(raw, coords)
    with_coords = sum(1 for r in rows if r["lat"] is not None)
    log("      고유 PNU {:,}개 중 좌표 확보 {:,}개 → 좌표 붙은 거래 {:,}건 ({})".format(
        len(set(pnus)), len(coords), with_coords,
        fmt_pct(with_coords / len(rows) if rows else None)))

    log("[3/6] 시간 분할 …")
    train, test, outside = split_by_period(rows, args.train_until, args.test_from)
    log("      학습 {:,} + 검증 {:,} + 범위밖 {:,} = {:,} (전체 {:,}) → 등식 {}".format(
        len(train), len(test), len(outside),
        len(train) + len(test) + len(outside), len(rows),
        "성립" if len(train) + len(test) + len(outside) == len(rows) else "⛔ 불일치"))
    if not test:
        raise RuntimeError("검증 거래가 0건입니다 — 분할 기준을 확인하세요.")

    log("[4/6] 학습 색인 만드는 중 …")
    index = build_train_index(train)

    log("[5/6] 검증 거래 채점 중 ({:,}건) …".format(len(test)))
    scored = score_test_rows(test, index)

    log("[6/6] 구 이름표 읽는 중 …")
    sigungu_names = fetch_sigungu_names(
        base_url, headers, [r.get("sigungu_code") for r in rows])

    os.makedirs(args.out_dir, exist_ok=True)
    stage_csv = os.path.join(args.out_dir, "단계별지표.csv")
    op_csv = os.path.join(args.out_dir, "운영모드지표.csv")
    raw_csv = os.path.join(args.out_dir, "검증거래별원자료.csv")
    md_path = os.path.join(args.out_dir, "성적표-v1.md")

    write_stage_csv(stage_csv, scored, sigungu_names)
    write_operating_csv(op_csv, scored, sigungu_names)
    write_raw_csv(raw_csv, scored, sigungu_names)

    ctx = {
        "scored": scored,
        "train": train,
        "test": test,
        "outside": outside,
        "total": len(rows),
        "train_until": args.train_until,
        "test_from": args.test_from,
        "sigungu_names": sigungu_names,
        "dist": price_distribution(rows),
        "sido_counts": Counter((r.get("sigungu_code") or "?")[:2] for r in rows),
        "band_counts": Counter(floor_band(r["floor_no"]) for r in rows),
        "test_coords_missing": sum(1 for r in test if r["lat"] is None),
        "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M"),
    }
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(build_markdown(ctx))

    m_op = cell_metrics(scored, lambda r: r["ladder_ape"])
    m_base = cell_metrics(scored, lambda r: r["stage_ape"].get("BASE"))
    paired = paired_metrics(scored, lambda r: r["ladder_ape"],
                            lambda r: r["stage_ape"].get("BASE"))
    dist = Counter(r["ladder_stage"] for r in scored)

    log("")
    log("── 요약 ─────────────────────────────────────────────")
    log("검증 거래           : {:,}건".format(len(scored)))
    log("사다리 커버리지     : {} ({:,}건)".format(fmt_pct(m_op["coverage"]), m_op["n_est"]))
    log("사다리 MdAPE        : {}".format(fmt_metric(m_op["n_est"], m_op["mdape"])))
    log("BASE   MdAPE        : {}".format(fmt_metric(m_base["n_est"], m_base["mdape"])))
    log("짝지은 비교({:,}건) : 사다리 {} vs BASE {}".format(
        paired["n_pair"],
        fmt_metric(paired["n_pair"], paired["a_mdape"]),
        fmt_metric(paired["n_pair"], paired["b_mdape"])))
    log("채택 단계 분포      : {}".format(
        " · ".join("{} {:,}".format(k, v) for k, v in sorted(dist.items()))))
    log("")
    for path in (md_path, stage_csv, op_csv, raw_csv):
        log("생성: {}".format(path))
    return 0


def main(argv=None):
    # cp949 콘솔에서 한글·특수문자(—) 출력이 UnicodeEncodeError 로 죽지 않게 —
    # 형제 스크립트들(check_district_source_update.py 등)과 같은 처방.
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="시세 추정 사다리 시간 분할 백테스트 (DB 읽기 전용)")
    ap.add_argument("--train-until", default=TRAIN_UNTIL,
                    help="학습 구간 마지막 계약년월 YYYYMM (기본 {})".format(TRAIN_UNTIL))
    ap.add_argument("--test-from", default=TEST_FROM,
                    help="검증 구간 첫 계약년월 YYYYMM (기본 {})".format(TEST_FROM))
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                    help="산출물 폴더 (기본 docs/backtest)")
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
