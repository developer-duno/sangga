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
- `통과구.csv`              — 구별 출시 기준선 판정(결정 0013). `scripts/load_price_gate.py`
                              가 이 파일을 읽어 DB 에 넣는다 — 통과 구 목록의 정본은
                              **이 계산의 결과뿐**이고, 손으로 구를 넣고 빼지 않는다.

유형축(L7) 검증 모드 — `--place-axis` (2026-08-19 추가)
------------------------------------------------------
1층이 왜 안 맞나(v1 MdAPE 45.2%)에 대한 답을 재는 별도 모드다. 사장님 지적 —
**"1층 상권은 도로변 상권과 상권 밀집지역이 다르다. 차나 사람이 많이 다니는 곳에 돈이
흐른다"** — 를 우리가 이미 가진 두 칸으로 근사한다: 도로접면(`parcel.road_contact`)과
상권 소속(`district` 포함 여부·종류). 둘을 곱한 9칸이 유형(place_type)이고, 새 단계 **L7
= 같은 시군구 + 같은 유형 + 같은 층대(최소 5건)** 을 L5 뒤·L6 앞에 끼운다.

⚠️ 이 모드는 **새 파일 2개만** 쓴다(`1층-유형축-검증.md`·`1층유형별지표.csv`).
   `성적표-v1.md`·`통과구.csv` 등 기존 4종은 건드리지 않는다 — 결정 0013 의 통과 구
   목록은 기본 모드의 계산에서만 나오고, 검토용 실험이 그것을 덮어쓰면 화면에 열리는
   구가 소리 없이 바뀐다.

⚠️ 이 모드만 **psql**(`SANGGA_DATABASE_URL`)을 쓴다. 상권 소속은 `st_contains` 공간
   조인이라 PostgREST 로는 읽을 수 없기 때문이다. 그래도 **읽기 전용**이다.

쓰는 법
-------
    python scripts/backtest_price.py
    python scripts/backtest_price.py --train-until 202506 --test-from 202507
    python scripts/backtest_price.py --out-dir docs/backtest
    python scripts/backtest_price.py --place-axis            # 유형축(L7) 검증

⛔ 절대 규칙 2 — 감정평가사 독점 업무를 연상시키는 표현(CLAUDE.md 금지 목록)은 이 파일
   어디에도 쓰지 않는다. 쓰는 말은 "추정·오차율·참고"뿐이다. 이 금지는 테스트
   `tests/test_backtest_price.py::test_스크립트에_금지표현이_없다` 가 매번 확인한다.
"""

import argparse
import csv
import io
import math
import os
import re
import statistics
import subprocess
import sys
import tempfile
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
MIN_SAMPLES = {"L2": 1, "L4": 3, "L5": 5, "L6": 1, "L7": 5, "BASE": 1}
RADIUS_M = {"L4": 100.0, "L5": 500.0}

# ── "돈이 흐르는 곳" 축 (L7) — `--place-axis` 모드에서만 쓴다 ────────────────
#
# 왜 만들었나: 1층은 거리로 좁혀도 잘 안 맞는다(성적표 v1 에서 MdAPE 45.2%). 사장님
# 지적 — "1층 상권은 도로변 상권과 상권 밀집지역이 다르다. 차나 사람이 많이 다니는
# 곳에 돈이 흐른다". 그 '흐름'을 우리가 이미 가진 두 칸으로 근사한다:
#   ① 도로접면(`parcel.road_contact`) — 큰길/중간/골목길
#   ② 상권 소속(`district` 안에 드는가, 든다면 밀집형인가)
# 거리로 더 좁히면 1층 표본이 말라 죽는다(같은 층·같은 도로등급 5건 이상이 15%뿐).
# 그래서 **거리 대신 유형**으로 좁힌다 — 유형 칸마다 수백 건씩 있다.
LADDER_PLACE = ("L2", "L4", "L5", "L7", "L6")
ALL_STAGES_PLACE = ("L2", "L4", "L5", "L7", "L6", "BASE")

# 밀집으로 볼 상권 종류. district_type 은 소스가 쓰는 말을 그대로 담고 있다
# (골목상권/발달상권/전통시장/관광특구 + 소진공 '주요상권').
DENSE_DISTRICT_TYPES = ("발달상권", "관광특구", "전통시장")
ROAD_GRADES = ("큰길", "중간", "골목길")
DISTRICT_CLASSES = ("밀집", "일반상권", "상권밖")
PLACE_SEP = "·"
PLACE_TYPES = tuple("{}{}{}".format(g, PLACE_SEP, c)
                    for g in ROAD_GRADES for c in DISTRICT_CLASSES)

# 유형을 못 매긴 거래(도로접면이 없거나 맹지, 필지가 parcel 에 없음)를 표본 부족과
# 구분해서 센다 — 좌표 없음(coords_missing)과 같은 이유다.
ST_PLACE_MISSING = "place_missing"

# PNU 는 숫자 19자리다. SQL 문자열에 넣기 전에 이 모양이 아닌 값은 통째로 버린다.
PNU_RE = re.compile(r"^\d{19}$")
PLACE_SQL_BATCH = 2000

# 채점
HIT_BAND = 0.20          # ±20% 적중률
SUPPRESS_BELOW = 5       # md 표에서 이 미만이면 수치 대신 "표본 부족(n)"

# 출시 기준선 — 결정 0013 §2 (사장님 재결재로 확정). 여기 있는 것이 그 기준의 정본이고,
# 통과 구 목록은 **이 계산의 결과로만** 갱신한다(손으로 구를 넣고 빼지 않는다 — 결정 0013 §4).
GATE_MAX_MDAPE = 0.30

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


def road_grade(road_contact):
    """도로접면 문자열 → 큰길 / 중간 / 골목길 / None(모름).

    `parcel.road_contact` 의 실제 값(2026-08-19 라이브 실측, 채점 대상 필지 기준):
      광대로한면·광대소각·광대세각              → **큰길**
      중로한면·중로각지·소로한면·소로각지        → **중간**
      세로한면(가)·세로한면(불)·세로각지(가/불)  → **골목길**
      맹지·지정되지않음·빈값                     → **None**

    맹지를 '골목길'로 밀어 넣지 않는다 — 차도 사람도 안 다니는 자리라 성격이 다르고,
    억지로 한 칸에 넣으면 그 칸의 성적이 오염된다. 모르는 것은 모른다고 둔다.
    """
    if not road_contact:
        return None
    s = road_contact.strip()
    if s.startswith("광대"):
        return "큰길"
    if s.startswith("중로") or s.startswith("소로"):
        return "중간"
    if s.startswith("세로"):
        return "골목길"
    return None


def district_class(district_type):
    """상권 종류 → 밀집 / 일반상권 / 상권밖.

    상권에 **안 든 것**(district_type 이 없음)만 '상권밖'이다. 처음 보는 종류 이름은
    '일반상권'으로 둔다 — 어쨌든 어느 상권 경계 안에 있다는 사실은 참이기 때문이다
    (소스가 새 종류를 추가해도 '상권밖'으로 잘못 떨어지지 않게).
    """
    if not district_type:
        return "상권밖"
    if district_type in DENSE_DISTRICT_TYPES:
        return "밀집"
    return "일반상권"


def pick_district_type(district_types):
    """한 필지가 여러 상권에 겹칠 때 어느 종류로 볼지 하나를 고른다.

    겹침은 실재한다(관광특구가 발달상권을 덮는 조합 — 결정 0011 §겹침 규칙).
    밀집형이 하나라도 있으면 밀집형을 고른다(더 강한 신호가 이긴다). 밀집형이 없으면
    이름 순으로 하나 — 어느 쪽을 골라도 '일반상권' 한 칸으로 들어가므로 결과가 같다.
    """
    dense = [t for t in district_types if t in DENSE_DISTRICT_TYPES]
    if dense:
        return sorted(dense, key=DENSE_DISTRICT_TYPES.index)[0]
    others = sorted(t for t in district_types if t)
    return others[0] if others else None


def place_type(road_contact, district_type):
    """두 축을 합친 9칸 중 하나 → '큰길·밀집' 등. 도로등급을 모르면 None."""
    grade = road_grade(road_contact)
    if grade is None:
        return None
    return "{}{}{}".format(grade, PLACE_SEP, district_class(district_type))


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
        "sigungu_place_band": defaultdict(list),
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
        # 유형을 모르는 학습 거래는 L7 후보에서만 빠진다(나머지 색인에는 그대로 있다).
        if row.get("place_type"):
            index["sigungu_place_band"][
                (row.get("sigungu_code"), row["place_type"], band)].append(price)
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


def place_missing_result():
    """L7 인데 이 거래의 유형을 못 매길 때(도로접면 없음·맹지·필지 자료 없음)."""
    return {"status": ST_PLACE_MISSING, "estimate": None, "n": 0}


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

    # L7 — 같은 구 + 같은 유형 + 같은 층대. 유형 자료를 안 붙이고 돌리면(기본 모드)
    # 이 칸은 항상 place_missing 이라 기존 사다리(L2→L4→L5→L6)에 아무 영향이 없다.
    pt = row.get("place_type")
    results["L7"] = (
        estimate_from(index["sigungu_place_band"].get((row.get("sigungu_code"), pt, band), []),
                      MIN_SAMPLES["L7"])
        if pt else place_missing_result())

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


def pick_ladder_ape(row):
    """운영 모드(사다리)의 오차. 4-1 표와 통과 구 판정이 **같은 것**을 보게 묶어 둔다."""
    return row["ladder_ape"]


def pick_base_ape(row):
    """대조군(구 평균)의 오차. 위와 같은 이유로 여기 한 곳에만 적는다."""
    return row["stage_ape"].get("BASE")


def pick_place_ape(row):
    """새 사다리(L7 를 낀 것)의 오차."""
    return row.get("place_ape")


def pick_l7_ape(row):
    """L7 단독 오차 — 사다리와 상관없이 이 단계 하나만 봤을 때."""
    return row["stage_ape"].get("L7")


def gate_pass(ladder_mdape, base_mdape, max_mdape=GATE_MAX_MDAPE):
    """결정 0013 §2 — 이 구에서 참고 시세를 화면에 내도 되는가.

    둘을 **모두** 만족해야 한다:
      ① 사다리 MdAPE ≤ 30%
      ② 같은 구에서 사다리가 BASE(구 평균)를 이긴다

    ②가 있는 이유: 금천구는 ①을 통과하지만(26.0%) 구 평균이 더 정확하다(17.6%).
    이미 화면에 있는 구 평균보다 못한 값을 "추정"이라며 얹으면 후퇴다.
    한쪽이라도 잴 수 없으면(짝지은 거래 0건 등) 통과가 아니다 — 모르면 안 낸다.
    """
    if ladder_mdape is None or base_mdape is None:
        return False
    return ladder_mdape <= max_mdape and ladder_mdape < base_mdape


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


def place_context_sql(pnus):
    """PNU 목록 → 도로접면·소속 상권 종류를 한 번에 읽는 SQL (읽기 전용).

    ⚠️ PostgREST 로는 이걸 못 한다 — 상권 소속은 `st_contains(d.geom, p.geom)` 공간
       조인이고, REST 에는 그 함수를 태울 자리가 없다. 그래서 이 한 가지만 psql 로 읽는다
       (새 함수를 DB 에 만드는 것은 쓰기라 금지).

    ⚠️ `p.pnu = want.pnu::char(19)` 로 **문자 리터럴 쪽을 캐스트**한다. 반대로 두면
       char(19) 인 컬럼이 text 로 캐스트돼 기본키 인덱스가 죽는다(메모리:
       char19-param-index-trap — 459.8ms ↔ 0.060ms).

    ⚠️ `left join district` 다 — 상권에 안 든 필지도 '상권밖'이라는 **정보**라서
       버리면 안 된다(그 칸이 표본의 절반이다).
    """
    values = ",".join("('{}')".format(p) for p in pnus)
    return (
        "with want(pnu) as (values {})\n"
        "select p.pnu,\n"
        "       coalesce(p.road_contact, ''),\n"
        "       coalesce(string_agg(distinct d.district_type, '|'), '')\n"
        "  from want\n"
        "  join parcel p on p.pnu = want.pnu::char(19)\n"
        "  left join district d on st_contains(d.geom, p.geom)\n"
        " group by p.pnu, p.road_contact\n"
        " order by p.pnu;\n".format(values))


def parse_place_rows(rows):
    """psql 출력 줄 → {pnu: {"road_contact":…, "district_types":[…]}}."""
    out = {}
    for cells in rows:
        if len(cells) < 3:
            continue
        pnu = cells[0].strip()
        road = cells[1].strip()
        types = [t for t in cells[2].split("|") if t.strip()]
        out[pnu] = {"road_contact": road or None, "district_types": sorted(types)}
    return out


def _psql_query(sql):
    """SELECT 하나를 psql 로 돌려 [[칸,…]] 로 돌려준다. **읽기 전용**.

    한글 SQL 을 `-c` 로 넘기면 Windows 콘솔 코드페이지로 인코딩돼 죽는다(2026-08-11
    실측) — `scripts/dbx.py` 와 같은 처방으로 UTF-8 임시 파일 경유다.
    """
    import dbx  # 같은 폴더의 기존 도구. 접속 문자열 해석·비밀번호 취급을 재사용한다.

    args, password = dbx.parts()
    env = dict(os.environ)
    env["PGPASSWORD"] = password           # ⚠️ 명령줄이 아니라 환경변수로
    env["PGCLIENTENCODING"] = "UTF8"
    fd, path = tempfile.mkstemp(suffix=".sql", prefix="backtest_place_")
    os.close(fd)
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(sql)
        cmd = ["psql"] + args + ["-X", "-q", "-A", "-t", "-F", "\t",
                                 "-v", "ON_ERROR_STOP=1", "-f", path]
        proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise RuntimeError("psql 조회 실패: {}".format(
                proc.stderr.decode("utf-8", "replace")[:500]))
        out = proc.stdout.decode("utf-8", "replace")
    finally:
        os.unlink(path)
    return [line.split("\t") for line in out.splitlines() if line.strip()]


def fetch_place_context(pnus):
    """채점에 쓰이는 필지들의 도로접면·상권 소속을 읽는다 → {pnu: {...}}."""
    clean = sorted({p for p in pnus if p and PNU_RE.match(p)})
    skipped = len(set(p for p in pnus if p)) - len(clean)
    if skipped:
        log("      ⚠️ PNU 모양이 19자리 숫자가 아닌 것 {:,}개는 조회에서 뺐다".format(skipped))
    context = {}
    batches = chunked(clean, PLACE_SQL_BATCH)
    for i, batch in enumerate(batches, 1):
        context.update(parse_place_rows(_psql_query(place_context_sql(batch))))
        log("      배치 {}/{} … 필지 {:,}개".format(i, len(batches), len(context)))
    return context


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


def normalize_rows(raw_rows, coords, place_context=None):
    """REST 응답을 채점이 쓰는 모양으로 — 숫자 변환 + 좌표(+유형) 부착.

    `place_context` 를 안 주면 유형 칸이 전부 None 이라 L7 은 성립하지 않는다
    (기본 모드의 성적이 이 변경 때문에 달라지지 않게 하는 장치다).
    """
    place_context = place_context or {}
    rows = []
    for r in raw_rows:
        pnu = r.get("pnu")
        ctx = place_context.get(pnu) or {}
        road_contact = ctx.get("road_contact")
        types = ctx.get("district_types") or []
        dtype = pick_district_type(types)
        rows.append({
            "tx_id": r.get("tx_id"),
            "pnu": pnu,
            "sigungu_code": r.get("sigungu_code"),
            "floor_no": int(r["floor_no"]),
            "unit_price": float(r["unit_price"]),
            "contract_ym": r.get("contract_ym"),
            "lat": coords.get(pnu, (None, None))[0],
            "lng": coords.get(pnu, (None, None))[1],
            "road_contact": road_contact,
            "district_types": types,
            "district_type": dtype,
            "road_grade": road_grade(road_contact),
            "district_class": district_class(dtype) if pnu in place_context else None,
            "place_type": place_type(road_contact, dtype),
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


def add_place_ladder(scored):
    """이미 채점된 거래에 **새 사다리**(L2→L4→L5→L7→L6) 결과를 덧붙인다.

    단계별 계산은 건드리지 않는다 — 같은 `stages` 를 순서만 달리 걸어가므로, 두 사다리
    비교가 "같은 재료를 어떻게 고르느냐"의 차이만 남는다.
    """
    for record in scored:
        code, estimate, n = walk_ladder(record["stages"], LADDER_PLACE)
        record["place_stage"] = code
        record["place_estimate"] = estimate
        record["place_n"] = n
        record["place_ape"] = (ape(estimate, record["unit_price"])
                               if code != NO_ESTIMATE else None)
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


def gate_rows(scored, sigungu_names):
    """구별 통과 판정 — 4-1 표(짝지은 비교)와 **같은 계산·같은 집합**을 쓴다.

    ⚠️ 여기서 짝짓기를 새로 구현하면 안 된다. 표의 숫자와 화면에 열리는 구 목록이
    서로 다른 계산에서 나오면, 둘이 갈라져도 아무 데서도 에러가 안 난다.
    """
    out = []
    for code, bucket in group_by(scored, lambda r: r.get("sigungu_code") or "?"):
        p = paired_metrics(bucket, pick_ladder_ape, pick_base_ape)
        out.append({
            "sigungu_code": code,
            "sigungu_nm": sigungu_names.get(code, ""),
            "n_paired": p["n_pair"],
            "ladder_mdape": p["a_mdape"],
            "base_mdape": p["b_mdape"],
            "gate_pass": gate_pass(p["a_mdape"], p["b_mdape"]),
        })
    return out


def write_gate_csv(path, scored, sigungu_names):
    """통과 구 목록 — `scripts/load_price_gate.py` 가 읽어 DB 에 넣는 **기계용** 산출물.

    사람이 읽는 다른 CSV 와 달리 머리글이 영문인 이유가 그것이다(적재기가 칸 이름으로
    읽는다). 참·거짓은 SQL 리터럴 그대로 'true'/'false' 로 적는다.
    """
    rows = gate_rows(scored, sigungu_names)
    _write_csv(path,
               ["sigungu_code", "sigungu_nm", "n_paired",
                "ladder_mdape", "base_mdape", "gate_pass"],
               [[r["sigungu_code"], r["sigungu_nm"], r["n_paired"],
                 _csv_ratio(r["ladder_mdape"]), _csv_ratio(r["base_mdape"]),
                 "true" if r["gate_pass"] else "false"] for r in rows])
    return rows


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
    # ⚠️ 4-1 의 두 pick 은 통과 구 판정(gate_rows)이 쓰는 것과 **같은 함수**다. 표의
    #    숫자와 화면에 열리는 구 목록이 다른 계산에서 나오면 갈라져도 에러가 안 난다.
    for title, pick_a, label_a in (
        ("4-1. 운영 모드(사다리) vs BASE", pick_ladder_ape, "운영 모드"),
        ("4-2. L5(반경 500m 동일층) vs BASE", lambda r: r["stage_ape"].get("L5"), "L5"),
    ):
        add("### {}".format(title))
        add("")
        add("| 구분 | 짝지은 거래 | {} MdAPE | BASE MdAPE | {} ±20% | BASE ±20% |"
            .format(label_a, label_a))
        add("|---|---|---|---|---|---|")
        pairs_all = paired_metrics(scored, pick_a, pick_base_ape)
        add(_paired_row("전체", pairs_all))
        for value, bucket in group_by(scored, lambda r: r.get("sigungu_code") or "?"):
            p = paired_metrics(bucket, pick_a, pick_base_ape)
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


# ── 유형축(L7) 검증 — 별도 산출물 ────────────────────────────────────────────
#
# ⚠️ 이 아래 코드는 `성적표-v1.md`·기존 CSV 4종을 **쓰지 않는다**. 결정 0013 의 통과 구
#    목록은 그 계산에서만 나오므로, 검토용 실험이 그 파일을 덮어쓰면 화면에 열리는 구가
#    조용히 바뀔 수 있다. 그래서 파일 이름도 경로도 겹치지 않게 새로 만든다.

PLACE_BANDS = ("1층", "2층", "3층+")
PLACE_NONE_LABEL = "(유형 없음)"


def place_key(row):
    """검증 거래의 유형 칸 이름(못 매긴 것은 한 칸으로 모은다)."""
    return row.get("place_type") or PLACE_NONE_LABEL


def place_cell(rows):
    """한 칸(층대 × 유형)의 모든 지표를 한 번에. 표·CSV 가 같은 계산을 보게 묶어 둔다."""
    old = cell_metrics(rows, pick_ladder_ape)
    new = cell_metrics(rows, pick_place_ape)
    l7 = cell_metrics(rows, pick_l7_ape)
    base = cell_metrics(rows, pick_base_ape)
    return {
        "n_total": len(rows),
        "old": old,
        "new": new,
        "l7": l7,
        "base": base,
        "pair_old": paired_metrics(rows, pick_place_ape, pick_ladder_ape),
        "pair_base": paired_metrics(rows, pick_place_ape, pick_base_ape),
    }


def place_rows_for(scored, band=None, key=None):
    """층대·유형으로 검증 거래를 고른다(둘 다 None 이면 전부)."""
    out = scored
    if band is not None:
        out = [r for r in out if floor_band(r["floor_no"]) == band]
    if key is not None:
        out = [r for r in out if place_key(r) == key]
    return out


def place_context_stats(rows):
    """유형을 못 매긴 이유를 갈라 센다 — '얼마나 못 썼나'가 아니라 '왜 못 썼나'."""
    no_parcel = sum(1 for r in rows if not r.get("district_types") and r.get("road_contact") is None
                    and r.get("district_class") is None)
    no_road = sum(1 for r in rows
                  if r.get("district_class") is not None and r.get("road_grade") is None)
    return {
        "n": len(rows),
        "typed": sum(1 for r in rows if r.get("place_type")),
        "no_parcel": no_parcel,
        "no_road": no_road,
    }


PLACE_CSV_HEADER = [
    "층대", "유형", "도로등급", "상권등급", "검증거래수",
    "L7성립수", "L7커버리지", "L7_MdAPE", "L7_적중률20",
    "새사다리성립수", "새사다리커버리지", "새사다리_MdAPE", "새사다리_적중률20",
    "기존사다리성립수", "기존사다리커버리지", "기존사다리_MdAPE", "기존사다리_적중률20",
    "짝_새vs기존_거래수", "짝_새_MdAPE", "짝_기존_MdAPE",
    "짝_새vsBASE_거래수", "짝_새_MdAPE2", "짝_BASE_MdAPE",
]


def place_csv_row(band_label, key, cell):
    # 9칸만 두 축으로 쪼갠다. '합계'·'(유형 없음)' 은 축 칸을 비워 둔다 —
    # 거기에 이름을 그대로 흘리면 엑셀에서 도로등급으로 필터할 때 섞여 들어온다.
    grade, klass = key.split(PLACE_SEP) if key in PLACE_TYPES else ("", "")
    c = cell
    return [
        band_label, key, grade, klass, c["n_total"],
        c["l7"]["n_est"], _csv_ratio(c["l7"]["coverage"]),
        _csv_ratio(c["l7"]["mdape"]), _csv_ratio(c["l7"]["hit20"]),
        c["new"]["n_est"], _csv_ratio(c["new"]["coverage"]),
        _csv_ratio(c["new"]["mdape"]), _csv_ratio(c["new"]["hit20"]),
        c["old"]["n_est"], _csv_ratio(c["old"]["coverage"]),
        _csv_ratio(c["old"]["mdape"]), _csv_ratio(c["old"]["hit20"]),
        c["pair_old"]["n_pair"], _csv_ratio(c["pair_old"]["a_mdape"]),
        _csv_ratio(c["pair_old"]["b_mdape"]),
        c["pair_base"]["n_pair"], _csv_ratio(c["pair_base"]["a_mdape"]),
        _csv_ratio(c["pair_base"]["b_mdape"]),
    ]


def write_place_csv(path, scored):
    """층대 × 유형 지표 전부. md 가 감춘 얇은 칸도 여기에는 그대로 있다."""
    keys = list(PLACE_TYPES) + [PLACE_NONE_LABEL]
    rows_out = []
    for band_label, band in [("전체", None)] + [(b, b) for b in PLACE_BANDS]:
        bucket = place_rows_for(scored, band=band)
        rows_out.append(place_csv_row(band_label, "합계", place_cell(bucket)))
        for key in keys:
            cell = place_cell([r for r in bucket if place_key(r) == key])
            if cell["n_total"]:
                rows_out.append(place_csv_row(band_label, key, cell))
    _write_csv(path, PLACE_CSV_HEADER, rows_out)
    return rows_out


def _place_compare_row(label, cell):
    c = cell
    return "| {} | {:,} | {} | {} | {} | {} | {} | {} |".format(
        label, c["n_total"],
        fmt_pct(c["old"]["coverage"]), fmt_metric(c["old"]["n_est"], c["old"]["mdape"]),
        fmt_metric(c["old"]["n_est"], c["old"]["hit20"]),
        fmt_pct(c["new"]["coverage"]), fmt_metric(c["new"]["n_est"], c["new"]["mdape"]),
        fmt_metric(c["new"]["n_est"], c["new"]["hit20"]))


PLACE_COMPARE_HEADER = (
    "| 구분 | 검증 거래 | 기존 커버리지 | 기존 MdAPE | 기존 ±20% | "
    "새 커버리지 | 새 MdAPE | 새 ±20% |\n|---|---|---|---|---|---|---|---|")


def build_place_markdown(ctx):
    """유형축 검증 문서를 문자열로 만든다(파일 쓰기는 호출부)."""
    scored = ctx["scored"]
    lines = []
    add = lines.append

    all_cell = place_cell(scored)
    f1 = place_cell(place_rows_for(scored, band="1층"))
    f2 = place_cell(place_rows_for(scored, band="2층"))
    f3 = place_cell(place_rows_for(scored, band="3층+"))
    stats = ctx["stats"]

    def pct(x):
        return round((x or 0.0) * 100)

    add("# 1층 유형축(L7) 검증 — \"돈이 흐르는 곳\"으로 좁히면 나아지나")
    add("")
    add("> 생성: {} (KST) · 스크립트: `python scripts/backtest_price.py --place-axis` · "
        "DB 읽기 전용".format(ctx["generated_at"]))
    add("> **기존 성적표(`성적표-v1.md`)와 통과 구 목록(`통과구.csv`)은 이 실행이 "
        "건드리지 않는다.** 결정 0013 의 게이트는 그 계산에서만 나온다.")
    add("> 이 문서도 **사실만 적는다.** 1층을 열지 말지는 사장님 결재 사항이다.")
    add("")

    # 0. 쉬운 설명
    add("## 0. 쉬운 설명 (여기까지만 읽으셔도 됩니다)")
    add("")
    add("**왜 다시 재나.** 지난 성적표에서 **1층이 제일 안 맞았습니다**(오차 ±{}%). "
        "그때 이유를 \"코너냐 골목이냐가 자료에 없어서\"라고 적었는데, 그게 틀렸습니다. "
        "도로에 얼마나 접했는지(`도로접면`)는 **화면에 나오는 필지의 거의 전부에 이미 "
        "들어 있고**, 상권 경계 안인지도 압니다.".format(pct(f1["old"]["mdape"])))
    add("")
    add("**무엇을 바꿨나.** 값을 어림할 때 \"몇 미터 안\"으로만 찾던 것을, 1층 같은 자리가 "
        "부족하면 **같은 구에서 \"성격이 같은 자리\"**를 찾아 쓰게 했습니다. 성격은 두 가지로 봅니다:")
    add("")
    add("1. **길** — 큰길가냐(광대로), 보통 길이냐(중로·소로), 골목이냐(세로)")
    add("2. **상권** — 사람이 몰리는 상권 안이냐(발달상권·관광특구·전통시장), 그냥 상권이냐, "
        "상권 밖이냐")
    add("")
    add("둘을 곱하면 9칸이 나옵니다(예: \"큰길·밀집\"). 같은 구·같은 층대·같은 칸의 거래 "
        "**5건 이상**이 모이면 그 중간값을 씁니다.")
    add("")
    add("**결과 — 세 줄.**")
    add("")
    add("- **1층 오차: ±{}% → ±{}%.** {}"
        .format(pct(f1["old"]["mdape"]), pct(f1["new"]["mdape"]),
                "좋아졌습니다." if (f1["new"]["mdape"] or 9) < (f1["old"]["mdape"] or 0)
                else "나아지지 않았습니다."))
    add("- **1층에서 값이 나오는 비율(커버리지): {} → {}.**"
        .format(fmt_pct(f1["old"]["coverage"]), fmt_pct(f1["new"]["coverage"])))
    worse = [band for band, cell in (("2층", f2), ("3층+", f3))
             if (cell["pair_old"]["a_mdape"] or 0) > (cell["pair_old"]["b_mdape"] or 0)]
    add("- **2층 {} → {} · 3층+ {} → {}** — 이미 잘 맞던 층은 {}."
        .format(fmt_metric(f2["old"]["n_est"], f2["old"]["mdape"]),
                fmt_metric(f2["new"]["n_est"], f2["new"]["mdape"]),
                fmt_metric(f3["old"]["n_est"], f3["old"]["mdape"]),
                fmt_metric(f3["new"]["n_est"], f3["new"]["mdape"]),
                "{} 쪽이 오히려 조금 나빠졌습니다(같은 거래로 견줬을 때)".format(
                    "·".join(worse)) if worse else "거의 그대로입니다"))
    add("")
    add("**한 줄 요약.** {}"
        .format(ctx["one_line"]))
    add("")

    # 1. 정의
    add("## 1. 새로 넣은 것 — 유형 축과 L7")
    add("")
    add("### 1-1. 두 축의 정의")
    add("")
    add("| 축 | 자료 | 값 |")
    add("|---|---|---|")
    add("| 도로등급 | `parcel.road_contact` | **큰길**=광대로한면·광대소각·광대세각 / "
        "**중간**=중로한면·중로각지·소로한면·소로각지 / **골목길**=세로한면(가·불)·세로각지(가·불) / "
        "**모름**=맹지·지정되지않음·빈값 |")
    add("| 상권등급 | `district` 안에 드는가(`st_contains`) | **밀집**=발달상권·관광특구·전통시장 / "
        "**일반상권**=그 밖의 상권(골목상권·주요상권) / **상권밖**=어느 경계에도 안 듦 |")
    add("")
    add("- 맹지를 골목길에 넣지 않는다 — 차도 사람도 안 다니는 자리라 성격이 다르다. "
        "모르는 것은 모른다고 두고 L7 을 안 쓴다(`place_missing`).")
    add("- 한 필지가 여러 상권에 겹치면(관광특구가 발달상권을 덮는 조합이 실재한다) "
        "**밀집 쪽을 고른다** — 더 강한 신호가 이긴다.")
    add("- \"상권밖\"은 결측이 아니라 **정보**다. 검증 거래의 절반 가까이가 이 칸이다.")
    add("")
    add("### 1-2. L7 정의와 사다리에서의 자리")
    add("")
    add("| 코드 | 후보 조건 | 최소 표본 |")
    add("|---|---|---|")
    add("| **L7** | **같은 시군구 + 같은 유형(9칸 중 하나) + 같은 층대** | **5** |")
    add("")
    add("- 기존 사다리: L2 → L4 → L5 → L6")
    add("- **새 사다리: L2 → L4 → L5 → L7 → L6** (가까운 근거가 먼저, 동네 평균보다는 앞)")
    add("- 즉 새 사다리는 \"반경 500m 안에 같은 층 5건이 없어서 **동네 평균으로 내려가던 거래**\"만 "
        "바꾼다. 그 앞 단계가 성립한 거래는 기존과 값이 같다.")
    add("")
    add("### 1-3. 왜 거리 대신 유형인가")
    add("")
    add("1층 200표본 실측(2026-08-19): 지금 방식(500m·같은 층)은 후보가 평균 6건이고 5건 이상 "
        "확보가 44%다. 여기에 **도로등급까지 맞추면** 평균 2건·5건 이상 **15%**로 떨어진다. "
        "거리로 더 좁히면 1층 표본이 말라 죽는다. 그래서 거리를 풀고(구 단위) 유형으로 좁혔다 — "
        "유형 칸마다 수백 건씩 있다.")
    add("")

    # 2. 커버리지
    add("## 2. 유형 자료가 얼마나 붙었나 (검증 거래 {:,}건)".format(stats["n"]))
    add("")
    add("| 구분 | 건수 | 비중 |")
    add("|---|---|---|")
    add("| 유형을 매긴 거래 | {:,} | {} |".format(
        stats["typed"], fmt_pct(stats["typed"] / stats["n"] if stats["n"] else None)))
    add("| 필지 자료 자체가 없음(`parcel` 미매칭) | {:,} | {} |".format(
        stats["no_parcel"], fmt_pct(stats["no_parcel"] / stats["n"] if stats["n"] else None)))
    add("| 필지는 있는데 도로접면이 없음·맹지 | {:,} | {} |".format(
        stats["no_road"], fmt_pct(stats["no_road"] / stats["n"] if stats["n"] else None)))
    add("")
    add("**검증 거래의 유형 분포**")
    add("")
    add("| 유형 | 전체 | 1층 | 2층 | 3층+ |")
    add("|---|---|---|---|---|")
    for key in list(PLACE_TYPES) + [PLACE_NONE_LABEL]:
        counts = [len(place_rows_for(scored, band=b, key=key)) for b in (None,) + PLACE_BANDS]
        if counts[0]:
            add("| {} | {:,} | {:,} | {:,} | {:,} |".format(key, *counts))
    add("")

    # 3. 층대별 비교
    add("## 3. 층대별 — 기존 사다리 vs 새 사다리")
    add("")
    add(PLACE_COMPARE_HEADER)
    add(_place_compare_row("전체", all_cell))
    for band in PLACE_BANDS:
        add(_place_compare_row(band, place_cell(place_rows_for(scored, band=band))))
    add("")
    add("**짝지은 비교** — 두 사다리가 **모두 값을 낸 거래만** 남겨 같은 집합에서 겨룬다.")
    add("")
    add("| 구분 | 짝지은 거래 | 새 MdAPE | 기존 MdAPE | 새 ±20% | 기존 ±20% |")
    add("|---|---|---|---|---|---|")
    add(_paired_row("전체", all_cell["pair_old"]))
    for band in PLACE_BANDS:
        add(_paired_row(band, place_cell(place_rows_for(scored, band=band))["pair_old"]))
    add("")

    # 4. 1층 집중
    add("## 4. 1층만 따로")
    add("")
    add("### 4-1. 단계별 (1층 검증 거래 {:,}건)".format(f1["n_total"]))
    add("")
    add(METRIC_HEADER)
    band_rows = place_rows_for(scored, band="1층")
    for stage in ALL_STAGES_PLACE:
        add(_metric_row(stage, cell_metrics(band_rows, lambda r, s=stage: r["stage_ape"].get(s))))
    add(_metric_row("**기존 사다리**", f1["old"]))
    add(_metric_row("**새 사다리(L7 포함)**", f1["new"]))
    add("")
    add("### 4-2. 채택 단계 분포 (1층)")
    add("")
    add("| 채택 단계 | 기존 사다리 | 새 사다리 |")
    add("|---|---|---|")
    old_dist = Counter(r["ladder_stage"] for r in band_rows)
    new_dist = Counter(r["place_stage"] for r in band_rows)
    for code in list(LADDER_PLACE) + [NO_ESTIMATE]:
        if old_dist.get(code) or new_dist.get(code):
            add("| {} | {:,} | {:,} |".format(code, old_dist.get(code, 0), new_dist.get(code, 0)))
    add("")
    add("L7 이 실제로 가로챈 거래 수 = 새 사다리의 L7 칸 **{:,}건**. 그만큼이 기존에는 "
        "L6(동네 평균)이나 `no_estimate` 였다.".format(new_dist.get("L7", 0)))
    add("")

    # 5. 유형 칸별
    add("## 5. 유형 9칸별 1층 성적")
    add("")
    add("표본이 {}건 미만인 칸은 수치 대신 `표본 부족(n)` 으로 적는다(CSV 에는 그대로 있다)."
        .format(SUPPRESS_BELOW))
    add("")
    add("| 유형 | 1층 검증 거래 | L7 성립 | L7 MdAPE | 새 사다리 MdAPE | 기존 사다리 MdAPE | "
        "짝(새 vs BASE) | 새 MdAPE | BASE MdAPE |")
    add("|---|---|---|---|---|---|---|---|---|")
    for key in list(PLACE_TYPES) + [PLACE_NONE_LABEL]:
        cell = place_cell(place_rows_for(scored, band="1층", key=key))
        if not cell["n_total"]:
            continue
        add("| {} | {:,} | {:,} | {} | {} | {} | {:,} | {} | {} |".format(
            key, cell["n_total"], cell["l7"]["n_est"],
            fmt_metric(cell["l7"]["n_est"], cell["l7"]["mdape"]),
            fmt_metric(cell["new"]["n_est"], cell["new"]["mdape"]),
            fmt_metric(cell["old"]["n_est"], cell["old"]["mdape"]),
            cell["pair_base"]["n_pair"],
            fmt_metric(cell["pair_base"]["n_pair"], cell["pair_base"]["a_mdape"]),
            fmt_metric(cell["pair_base"]["n_pair"], cell["pair_base"]["b_mdape"])))
    add("")
    add("**결정 0013 의 기준선을 이 칸들에 그대로 대 보면** (① MdAPE ≤ {:.0f}% ② 같은 집합에서 "
        "BASE(구 평균)를 이길 것):".format(GATE_MAX_MDAPE * 100))
    add("")
    add("| 유형 | 짝지은 거래 | 새 사다리 MdAPE | BASE MdAPE | 기준선 |")
    add("|---|---|---|---|---|")
    for key in list(PLACE_TYPES) + [PLACE_NONE_LABEL]:
        cell = place_cell(place_rows_for(scored, band="1층", key=key))
        p = cell["pair_base"]
        if not cell["n_total"]:
            continue
        ok = gate_pass(p["a_mdape"], p["b_mdape"])
        verdict = ("판정 불가(표본 {})".format(p["n_pair"]) if p["n_pair"] < SUPPRESS_BELOW
                   else ("통과" if ok else "미달"))
        add("| {} | {:,} | {} | {} | {} |".format(
            key, p["n_pair"], fmt_metric(p["n_pair"], p["a_mdape"]),
            fmt_metric(p["n_pair"], p["b_mdape"]), verdict))
    add("")
    add("⚠️ 이 표는 **기준을 대 본 계산 결과**일 뿐 결재가 아니다. 결정 0013 은 구 단위 게이트를 "
        "정했고, 유형 단위로 열지 말지는 정해 둔 바가 없다.")
    add("")

    # 6. 판단 재료
    add("## 6. 판단 재료 (사실만)")
    add("")
    for line in ctx["facts"]:
        add("- {}".format(line))
    add("")
    add("## 7. 이 검증의 한계")
    add("")
    add("- **집합(구분상가) 매매에 한정**된 성적이다(일반 거래는 지번이 마스킹돼 PNU 가 없다).")
    add("- **지하·옥탑은 아무 말도 하지 않는다** — 2017년부터 실거래 원본에 지하층 표기가 오지 않는다.")
    add("- 유형은 **필지 단위**다. 같은 필지 안에서 코너 점포와 안쪽 점포가 갈리는 차이는 "
        "여전히 잡지 못한다(도로접면은 필지가 어느 길에 접했나이지, 점포가 그 길에 붙었나가 아니다).")
    add("- `district` 경계는 **서울 1,650 + 대전 37**뿐이다. 대전은 소진공 주요상권만이라 "
        "'상권밖'이 실제보다 넓게 잡힐 수 있다.")
    add("- 검증 구간이 {}~ 로 짧아 구·유형으로 쪼개면 칸이 금세 얇아진다. 얇은 칸의 수치는 "
        "우연이다.".format(ctx["test_from"]))
    add("")
    add("---")
    add("")
    add("생성 파일: `1층유형별지표.csv` (층대 × 유형 전 지표 — 감춘 칸까지 그대로).")
    add("")
    return "\n".join(lines)


def build_place_facts(scored):
    """§6 판단 재료 — 문장을 손으로 베끼지 않고 같은 계산에서 뽑는다."""
    facts = []
    all_cell = place_cell(scored)
    f1 = place_cell(place_rows_for(scored, band="1층"))
    facts.append("검증 거래 **{:,}건** 중 1층 **{:,}건**.".format(
        len(scored), f1["n_total"]))
    facts.append("1층 MdAPE: 기존 사다리 **{}** → 새 사다리 **{}** "
                 "(짝지은 {:,}건에서는 기존 {} vs 새 {}).".format(
                     fmt_metric(f1["old"]["n_est"], f1["old"]["mdape"]),
                     fmt_metric(f1["new"]["n_est"], f1["new"]["mdape"]),
                     f1["pair_old"]["n_pair"],
                     fmt_metric(f1["pair_old"]["n_pair"], f1["pair_old"]["b_mdape"]),
                     fmt_metric(f1["pair_old"]["n_pair"], f1["pair_old"]["a_mdape"])))
    facts.append("1층 커버리지: 기존 {} → 새 {}.".format(
        fmt_pct(f1["old"]["coverage"]), fmt_pct(f1["new"]["coverage"])))
    facts.append("1층에서 L7 단독 성적: 성립 {:,}건 · MdAPE {} · ±20% {}.".format(
        f1["l7"]["n_est"], fmt_metric(f1["l7"]["n_est"], f1["l7"]["mdape"]),
        fmt_metric(f1["l7"]["n_est"], f1["l7"]["hit20"])))
    band1 = place_rows_for(scored, band="1층")
    l5_1 = cell_metrics(band1, lambda r: r["stage_ape"].get("L5"))
    facts.append("1층에서 **L7 단독이 L5(반경 500m·동일층) 단독과 비슷한 정확도인데 "
                 "커버리지는 두 배쯤 넓다**: L5 {} ({}) vs L7 {} ({}).".format(
                     fmt_metric(l5_1["n_est"], l5_1["mdape"]), fmt_pct(l5_1["coverage"]),
                     fmt_metric(f1["l7"]["n_est"], f1["l7"]["mdape"]),
                     fmt_pct(f1["l7"]["coverage"])))
    facts.append("1층에서 새 사다리 vs BASE(구 평균) — 짝지은 {:,}건에서 새 {} vs BASE {}. "
                 "**1층은 구 평균 자체가 만만치 않은 상대다.**".format(
                     f1["pair_base"]["n_pair"],
                     fmt_metric(f1["pair_base"]["n_pair"], f1["pair_base"]["a_mdape"]),
                     fmt_metric(f1["pair_base"]["n_pair"], f1["pair_base"]["b_mdape"])))
    gate = place_gate_summary(scored)
    facts.append("유형 9칸에 결정 0013 기준선(MdAPE {:.0f}% 이하 + BASE 를 이길 것)을 대 보면 "
                 "통과 **{}칸** / 판정 가능 {}칸 / 전체 {}칸.".format(
                     GATE_MAX_MDAPE * 100, gate["passed"], gate["judged"], gate["total"]))
    facts.append("전체(층대 무관) MdAPE: 기존 {} → 새 {} · 커버리지 {} → {}.".format(
        fmt_metric(all_cell["old"]["n_est"], all_cell["old"]["mdape"]),
        fmt_metric(all_cell["new"]["n_est"], all_cell["new"]["mdape"]),
        fmt_pct(all_cell["old"]["coverage"]), fmt_pct(all_cell["new"]["coverage"])))
    for band in PLACE_BANDS[1:]:
        cell = place_cell(place_rows_for(scored, band=band))
        facts.append("{} MdAPE: 기존 {} → 새 {} (검증 {:,}건).".format(
            band, fmt_metric(cell["old"]["n_est"], cell["old"]["mdape"]),
            fmt_metric(cell["new"]["n_est"], cell["new"]["mdape"]), cell["n_total"]))
    return facts


def place_gate_summary(scored, band="1층"):
    """유형 9칸에 결정 0013 기준선을 대 본 결과 — 통과 / 판정 가능 / 전체 칸 수."""
    passed, judged = 0, 0
    for key in PLACE_TYPES:
        p = place_cell(place_rows_for(scored, band=band, key=key))["pair_base"]
        if p["n_pair"] < SUPPRESS_BELOW:
            continue
        judged += 1
        if gate_pass(p["a_mdape"], p["b_mdape"]):
            passed += 1
    return {"passed": passed, "judged": judged, "total": len(PLACE_TYPES)}


def place_one_line(scored):
    """§0 마지막 한 줄 — 좋아졌다/아니다를 **계산 결과로만** 말한다.

    "좋아졌다"만 말하고 끝내면 안 된다. 1층은 애초에 기준선(MdAPE 30% 이하) 때문에
    닫힌 것이므로, 좋아졌더라도 그 선을 넘었는지까지 같이 말해야 결재 재료가 된다.
    """
    f1 = place_cell(place_rows_for(scored, band="1층"))
    pair = f1["pair_old"]
    old, new = pair["b_mdape"], pair["a_mdape"]
    if old is None or new is None or pair["n_pair"] < SUPPRESS_BELOW:
        return ("1층에서 두 방식이 모두 값을 낸 거래가 {}건뿐이라 아직 견줄 수 없습니다."
                .format(pair["n_pair"]))
    gate = place_gate_summary(scored)
    direction = ("조금 작습니다" if new < old else
                 "작지 않습니다" if new > old else "같습니다")
    return ("같은 1층 거래 {:,}건에서 새 방식의 오차는 ±{}%, 기존은 ±{}% — {}. "
            "다만 출시 기준선(오차 ±{:.0f}% 이하 + 구 평균보다 정확할 것)에는 {}. "
            "9칸 중 그 기준을 넘긴 칸은 **{}칸**입니다(판정할 만큼 표본이 있는 칸 {}개 기준). "
            "방향은 맞지만 이것만으로 1층을 열 수 있는 수준은 아닙니다.".format(
                pair["n_pair"], round(new * 100), round(old * 100), direction,
                GATE_MAX_MDAPE * 100,
                "**여전히 한참 못 미칩니다**" if new > GATE_MAX_MDAPE
                else "**겨우 닿았습니다**",
                gate["passed"], gate["judged"]))


def run_place(args):
    """유형축(L7) 검증 — 기존 산출물은 건드리지 않고 새 파일 2개만 쓴다."""
    base_url, key = get_supabase_config()
    headers = {"apikey": key, "Authorization": "Bearer {}".format(key)}

    log("[1/6] 실거래(집합·PNU·층·단가 보유) 읽는 중 …")
    raw = fetch_transactions(base_url, headers)
    log("      {:,}건".format(len(raw)))

    pnus = [r["pnu"] for r in raw if r.get("pnu")]

    log("[2/6] 필지 좌표 읽는 중 (100개씩) …")
    coords = fetch_parcel_coords(base_url, headers, pnus)

    log("[3/6] 도로접면·상권 소속 읽는 중 (psql·st_contains) …")
    context = fetch_place_context(pnus)
    log("      고유 PNU {:,}개 중 필지 자료 {:,}개".format(len(set(pnus)), len(context)))

    rows = normalize_rows(raw, coords, context)
    typed = sum(1 for r in rows if r["place_type"])
    log("      유형이 매겨진 거래 {:,}건 ({})".format(
        typed, fmt_pct(typed / len(rows) if rows else None)))

    log("[4/6] 시간 분할 …")
    train, test, outside = split_by_period(rows, args.train_until, args.test_from)
    log("      학습 {:,} + 검증 {:,} + 범위밖 {:,} = {:,} (전체 {:,}) → 등식 {}".format(
        len(train), len(test), len(outside),
        len(train) + len(test) + len(outside), len(rows),
        "성립" if len(train) + len(test) + len(outside) == len(rows) else "⛔ 불일치"))
    if not test:
        raise RuntimeError("검증 거래가 0건입니다 — 분할 기준을 확인하세요.")

    log("[5/6] 학습 색인 + 채점 …")
    index = build_train_index(train)
    scored = add_place_ladder(score_test_rows(test, index))

    log("[6/6] 산출물 쓰는 중 …")
    os.makedirs(args.out_dir, exist_ok=True)
    csv_path = os.path.join(args.out_dir, "1층유형별지표.csv")
    md_path = os.path.join(args.out_dir, "1층-유형축-검증.md")
    write_place_csv(csv_path, scored)

    ctx = {
        "scored": scored,
        "stats": place_context_stats(test),
        "facts": build_place_facts(scored),
        "one_line": place_one_line(scored),
        "train_until": args.train_until,
        "test_from": args.test_from,
        "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M"),
    }
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(build_place_markdown(ctx))

    f1 = place_cell(place_rows_for(scored, band="1층"))
    log("")
    log("── 요약 (유형축) ────────────────────────────────────")
    log("1층 검증 거래   : {:,}건".format(f1["n_total"]))
    log("1층 MdAPE       : 기존 {} → 새 {}".format(
        fmt_metric(f1["old"]["n_est"], f1["old"]["mdape"]),
        fmt_metric(f1["new"]["n_est"], f1["new"]["mdape"])))
    log("1층 커버리지    : 기존 {} → 새 {}".format(
        fmt_pct(f1["old"]["coverage"]), fmt_pct(f1["new"]["coverage"])))
    log("1층 짝지은 비교 : {:,}건에서 기존 {} vs 새 {}".format(
        f1["pair_old"]["n_pair"],
        fmt_metric(f1["pair_old"]["n_pair"], f1["pair_old"]["b_mdape"]),
        fmt_metric(f1["pair_old"]["n_pair"], f1["pair_old"]["a_mdape"])))
    log("")
    for path in (md_path, csv_path):
        log("생성: {}".format(path))
    return 0


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
    gate_csv = os.path.join(args.out_dir, "통과구.csv")
    md_path = os.path.join(args.out_dir, "성적표-v1.md")

    write_stage_csv(stage_csv, scored, sigungu_names)
    write_operating_csv(op_csv, scored, sigungu_names)
    write_raw_csv(raw_csv, scored, sigungu_names)
    gate_list = write_gate_csv(gate_csv, scored, sigungu_names)

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
    passed = [g for g in gate_list if g["gate_pass"]]
    log("출시 기준선 통과 구 : {}/{}개 (결정 0013 — MdAPE {:.0f}% 이하 + BASE 를 이길 것)"
        .format(len(passed), len(gate_list), GATE_MAX_MDAPE * 100))
    log("  {}".format(" · ".join("{}({})".format(g["sigungu_nm"] or "?", g["sigungu_code"])
                                 for g in passed) or "(없음)"))
    log("")
    for path in (md_path, stage_csv, op_csv, raw_csv, gate_csv):
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
    ap.add_argument("--place-axis", action="store_true",
                    help="유형축(L7) 검증 모드 — `1층-유형축-검증.md`·`1층유형별지표.csv` 만 쓴다. "
                         "기존 성적표·통과구.csv 는 건드리지 않는다.")
    args = ap.parse_args(argv)
    return run_place(args) if args.place_axis else run(args)


if __name__ == "__main__":
    sys.exit(main())
