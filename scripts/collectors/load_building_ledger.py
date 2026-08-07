# -*- coding: utf-8 -*-
"""
건축물대장 raw JSONL → Supabase 적재 (building + building_floor + unit) + §5.6 조인률 실측 보고

collect_building_ledger.py가 받아둔 raw(표제부·층별개요·전유공용면적)를 읽어
building/building_floor/unit 테이블을 채우고, `docs/상세계획.md` §5.6 "건축물대장 조인
성공률"을 실제로 재서 보고한다. raw는 읽기만 한다 (CLAUDE.md 수집 규칙: raw 불변).

무엇을 하나:
  1. building — 표제부 한 행 = 건물 하나.
       bld_id = PNU + '_' + mgmBldrgstPk(관리건축물대장PK)   ← schema.sql 갱신 필요
     동명칭이 아니라 대장PK로 식별한다. 이유 둘:
       (a) 같은 (PNU, 동명칭)이라도 서로 다른 대장(별동·재건축 이력 등)이 실재한다
           (11 에이전트 적대검증 실측 — 강남구 라이브 raw 23그룹·30건).
       (b) 동명칭 텍스트는 정부 데이터가 갱신되면 바뀔 수 있어 영속 키로 부적합.
     대장PK는 실측(2026-08-08, 라이브 raw 461,027행 전량 스트리밍) 결측 0행이고
     (PNU, 대장PK) 조합이 건물과 1:1이므로 이 값 자체를 bld_id에 직접 쓴다 —
     "몇 번째 수집인가"·"같은 PNU에 다른 어떤 건물이 있는가"에 좌우되지 않는
     영속 식별자가 된다(적대검증 Critical 수정: 예전 순번 방식은 재수집 때
     새 대장PK가 섞여 들어오면 정렬 순번이 흔들려 기존 unit들의 FK가 조용히
     다른 건물로 넘어가는 결함이 있었다). 대장PK가 비어 있는 행만
     make_bld_id(pnu, dongNm) 폴백을 쓴다 — build_buildings() 참조.
  2. building_floor — 층별개요 한 행 = 그 층의 한 용도 구획.
       floor_id = bld_id + 층 + 용도코드 + 세부용도 + 플래그2   ← make_floor_id
     unit(호실)과 달리 **모든 건물**에 있다 — 전유공용면적은 집합건물에만 있어
     강남 실측 1,083/5,903 = 18.35%에서 막히지만 층별개요는 5,903/5,903 = 100%다.
     그래서 §8.6 층별 스택 뷰는 "호실 쌓기"가 아니라 "층 쌓기"로 만들고, 그 유일한
     재료가 이 테이블이다. 같은 키가 여러 줄로 오면 면적을 합산한다(build_floors).
  3. unit — 전유공용면적 중 전유(exposPubuseGbCd='1') 행만 모아
     (건물, 층, 호) 단위로 area를 합산해 excl_area_m2를 만든다. 공용부는 제외한다
     (공용을 더하면 전용면적이 아니라 분양면적이 돼버린다).
     floor_use는 층별개요의 (건물, 층) -> mainPurpsCdNm 룩업으로 채운다.
  4. 적재 후 §5.6 조인률을 실측해 출력한다 (목표 90%+) — 수집이 아직 진행
     중이면(collect_progress에 pending/failed가 남아 있으면) 잠정치임을 먼저
     알린다.

층 코드 매핑 (이 소스의 정본 — scripts/normalize_floor.py는 문자열 파서라
여기선 쓰지 않는다. 건축HUB는 flrGbCd+flrNo로 이미 구조화돼 있어 파싱이 불필요):
    flrGbCd '10'(지하) -> -flrNo
    flrGbCd '20'(지상) -> +flrNo
    flrGbCd '30'(옥탑) -> ROOFTOP(99, normalize_floor 정본 재사용)
    flrGbCd '21'/'22'(복수층 하층/상층) -> flrNo 그대로 (부호까지 — floor_from_codes 참고)
    그 외 코드 / flrNo가 0·결측 -> None (경고 카운트)
  0은 절대 만들지 않는다 — CLAUDE.md 절대 규칙 4, DB CHECK(chk_floor_not_zero).

raw 중복 방어:
  수집기가 PNU 단위 원자적 append를 하므로 정상 흐름에선 중복이 안 생기지만,
  혹시 같은 PNU가 두 번 수집돼 raw에 두 배치가 쌓였다면 면적 합이 부풀어 오른다.
  그래서 PNU마다 fetched_at이 가장 늦은 배치 한 벌만 채택한다(2차 방어선).

사용법:
  python scripts/collectors/load_building_ledger.py --dry-run
  python scripts/collectors/load_building_ledger.py
  python scripts/collectors/load_building_ledger.py --raw-dir data/raw/bldrgst/202609 --snapshot-ym 202606
"""

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

import requests
from dotenv import load_dotenv

# ── 설정 ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# scripts/ 를 sys.path에 넣어 normalize_floor를 import (재구현 금지 — 정본 재사용,
# load_sangkwon_snapshot.py와 동일한 관례).
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from normalize_floor import ROOFTOP  # noqa: E402

DEFAULT_PERIOD_KEY = "202608"
DEFAULT_SIGUNGU_CODE = "11680"   # 강남구 (§0.2 파일럿)
DEFAULT_SNAPSHOT_YM = "202603"   # 강남 2026Q1 상권정보 스냅샷 (§5.6 지표 ②의 분모)

RAW_TITLE = "title.jsonl"
RAW_FLR_OULN = "flr_ouln.jsonl"
RAW_EXPOS_AREA = "expos_area.jsonl"

# 동명칭이 빈 문자열인 건물(단일동 일반건축물에서 흔함)의 bld_id 꼬리표.
MAIN_DONG_TOKEN = "MAIN"

# 층 구분 코드 (건축HUB flrGbCd, 2026-08-07 실측)
FLR_GB_UNDER = "10"    # 지하
FLR_GB_GROUND = "20"   # 지상
FLR_GB_ROOFTOP = "30"  # 옥탑
# 복수층 — 한 호실이 아래위 두 층을 쓰는 경우. 하층/상층 행이 짝으로 온다.
FLR_GB_MULTI = ("21", "22")  # 21=복수층(하층) / 22=복수층(상층)
ROOFTOP_FLOOR = ROOFTOP  # normalize_floor.ROOFTOP(99) 재사용 — 이 파일에서 재정의하지 않는다

# 전유/공용 구분 (exposPubuseGbCd). 전용면적은 전유만 더한다.
EXPOS_GB_PRIVATE = "1"

# 층별개요 areaExctYn — '1'이면 연면적 산정 제외분(계단실·물탱크실·옥탑 등).
# 데이터 근거(2026-08-07 강남 raw 63,053행): 층별개요 면적을 전부 더하면 표제부
# 연면적과 ±1% 일치가 64.1%인데, 이 행들을 빼면 82.6%로 오른다. 부속건축물까지
# 빼면 81.7%로 도로 떨어져 부속은 연면적에 포함됨이 확인됐다.
AREA_EXCLUDED_YN = "1"

# 층별개요 mainAtchGbCd — '0' 주건축물 / '1' 부속건축물.
MAIN_ATCH_ANNEX = "1"

# 주차 대수 4종 (옥내자주식/옥내기계식/옥외자주식/옥외기계식)
PARKING_FIELDS = ("indrAutoUtcnt", "indrMechUtcnt", "oudrAutoUtcnt", "oudrMechUtcnt")

# 집합건물 여부 (regstrGbCd 1=일반 / 2=집합)
REGSTR_GB_JIPHAP = "2"

# PNU 대지구분(11번째 글자) 정상값 — '1'=대지, '2'=산. 산지는 건축물이 없는 경우가 많다.
PLAT_GB_LAND = "1"
PLAT_GB_MOUNTAIN = "2"

BATCH_SIZE = 1000
SELECT_PAGE_SIZE = 1000
TIMEOUT_SEC = 120

# 유령 행 정리(delete_stale_units)에서 URL 하나에 담을 값 개수. PostgREST의
# in.(...)은 URL 쿼리스트링이라 값이 많으면 URL 길이 제한에 걸린다. PNU는
# 19자리 고정이라 넉넉히, unit_id는 호실명(한글·기호)이 붙어 길고 가변이라 짧게.
STALE_PNU_CHUNK = 200
STALE_DELETE_CHUNK = 100

# §5.6 목표선 (docs/상세계획.md)
JOIN_RATE_TARGET = 90.0

# 이 수집기의 collect_progress.collector 값. collect_building_ledger.COLLECTOR와
# 반드시 같은 문자열이어야 한다 — 두 스크립트는 서로 import하지 않는 관례라
# 상수를 각자 갖되 값을 맞춘다(공유 모듈을 새로 만들면 다른 수집기 작업과 충돌).
BLDRGST_COLLECTOR = "bldrgst"

# 전유공용면적 raw 행이 이 값에 도달하면 collect_building_ledger.py의 페이지
# 상한(NUM_OF_ROWS=100 x MAX_PAGES=100)에 걸려 절단됐을 가능성이 있다.
EXPOS_ROW_TRUNCATION_CAP = 10_000

# upsert 충돌 해소 정책. building·unit은 재실행 때 최신 대장 내용으로 갱신돼야
# 하므로 merge-duplicates (append-only 테이블인 unit_business와 성격이 다르다).
TABLE_UPSERT_RESOLUTION = {
    "building": "merge-duplicates",
    "unit": "merge-duplicates",
    "building_floor": "merge-duplicates",
}


# ── 순수 로직 (네트워크·DB 없음 — 테스트 대상) ─────────────────────────────────


def _to_float(raw):
    """빈 값/파싱 불가는 None. 그 외 float 변환."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(raw):
    """빈 값/파싱 불가는 None. '3.0' 같은 실수 표기도 int로 받아준다."""
    f = _to_float(raw)
    if f is None:
        return None
    return int(f)


def make_bld_id(pnu, dong_nm):
    """PNU + '_' + (동명칭 또는 'MAIN') — 대장PK(mgmBldrgstPk)가 없을 때만 쓰는 폴백.

    동명칭은 표제부에서 빈 문자열로 오는 경우가 흔하다(단일동 건물). 빈 값을 그대로
    이어붙이면 PNU 뒤에 '_'만 남아 사람이 읽기 어렵고, 공백만 든 값과도 구분이
    안 되므로 'MAIN'으로 통일한다.

    정상 경로의 bld_id는 make_bld_id_from_pk()가 만든다 — 대장PK가 실측상
    거의 항상 있기 때문이다(build_buildings() 참조). 이 함수는 대장PK가
    비어 있는 방어적 케이스에만 호출된다.
    """
    dong = (dong_nm or "").strip()
    return "{}_{}".format(pnu, dong or MAIN_DONG_TOKEN)


def _normalize_pk(raw):
    """mgmBldrgstPk 원본값(실측상 int, 방어적으로 문자열도 허용)을 문자열로 통일.

    없으면(None) 빈 문자열 — is None으로만 판정한다("or" 패턴은 정수 0이 legit한
    PK일 가능성을 결측으로 오판할 수 있어 피한다).
    """
    if raw is None:
        return ""
    return str(raw).strip()


def make_bld_id_from_pk(pnu, mgm_pk):
    """bld_id = PNU + '_' + mgmBldrgstPk(관리건축물대장PK) — 정상 경로의 식별자.

    이 값은 raw 안에 같은 PNU의 다른 건물이 무엇이 있든, 몇 번째 수집이든
    항상 같다(PNU + 대장PK만으로 결정되고 다른 행에 의존하지 않는다). 예전
    "정렬 순번" 방식은 재수집 때 새 대장PK가 섞여 들어오면 순번이 흔들려
    기존 unit들의 FK가 조용히 다른 건물로 넘어가는 결함이 있었다(적대검증
    Critical, 확신도 85 — 2026-08-08).
    """
    return "{}_{}".format(pnu, mgm_pk)


def make_unit_id(bld_id, floor_no, ho):
    """unit_id = bld_id + '_' + 층 + '_' + 호 (schema.sql 주석 규격).

    층이 판정 불가면 'NA'를 넣는다 — 0을 쓰지 않는다(절대 규칙 4). ho는 호출부
    (build_units)에서 이미 공백 정규화를 마친 값을 그대로 받는다 — 여기서 다시
    다르게 자르면 그룹 키(ho)와 unit_id의 호 표기가 어긋날 수 있다(수정 4).
    """
    floor_token = "NA" if floor_no is None else str(floor_no)
    return "{}_{}_{}".format(bld_id, floor_token, ho or "")


def make_floor_id(bld_id, floor_no, main_purps_cd, etc_purps, area_excluded, is_annex):
    """building_floor의 PK. bld_id + 층 + 용도코드 + 세부용도 + 플래그 2개.

    왜 이 조합인가: 층별개요 원본에는 행을 1:1로 가리킬 자연키가 없다. 강남
    실측(2026-08-07, 63,053행)에서 (건물·층·용도코드·세부용도·제외여부·부속구분)을
    전부 합쳐도 713그룹이 중복이다 — 같은 층에 같은 이름의 일반음식점 구획이 7개
    있는 식이다. 남은 후보는 rnum(응답 내 순번)뿐인데 이건 영속 키로 못 쓴다:
    순번의 정의상 대장에 행이 하나만 추가·삭제돼도 그 뒤가 통째로 밀려, 같은 구획이
    다음 수집 때 다른 키를 갖는다(밀림 자체는 필연이고 실제 갱신 빈도는 아직 측정
    안 했다 — 어느 쪽이든 키로 쓸 이유가 없다).
    그래서 unit과 같은 해법을 쓴다: **같은 키는 면적을 합산**하고 몇 줄이 합쳐졌는지
    src_row_cnt로 남긴다(build_floors).

    층이 판정 불가면 'NA' — 0을 쓰지 않는다(절대 규칙 4, make_unit_id와 같은 관례).
    세부용도(etcPurps)는 호출부에서 공백을 제거한 값을 그대로 받는다 — 여기서 다시
    자르면 그룹 키와 PK의 표기가 어긋난다(make_unit_id의 ho와 같은 함정).
    """
    floor_token = "NA" if floor_no is None else str(floor_no)
    return "{}_{}_{}_{}_{}{}".format(
        bld_id, floor_token, main_purps_cd or "", etc_purps or "",
        "X" if area_excluded else "I",   # eXcluded / Included (연면적 산정)
        "A" if is_annex else "M",        # Annex / Main (부속·주건축물)
    )


def parse_use_apr_day(raw):
    """useAprDay(YYYYMMDD 문자열) -> 'YYYY-MM-DD'. 빈값·형식 이상은 None.

    실측상 ''(빈 문자열)과 0이 섞여 들어오고, 달력에 없는 날짜(20241350 등)도
    가능하므로 실제 날짜로 파싱되는지까지 확인한다.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def floor_from_codes(flr_gb_cd, flr_no):
    """건축HUB (flrGbCd, flrNo) -> 정수 층. 판정 불가는 None (0은 절대 안 나온다).

    지하 '10' -> -n / 지상 '20' -> +n / 옥탑 '30' -> ROOFTOP_FLOOR(99).
    옥탑은 flrNo가 무엇이든 규격 고정값을 쓴다(층수가 아니라 분류값).

    복수층 '21'(하층)·'22'(상층)은 flrNo를 부호까지 그대로 층으로 쓴다. 이
    두 코드는 방향(지하/지상)을 코드가 아니라 flrNo 부호가 들고 있다 — 공식
    층구분코드표(건축HUB 층별개요 명세)는 코드 의미만 정의하고 flrNo 부호
    규약은 아예 정의하지 않으므로, 아래 실측을 근거로 삼는다(2026-08-07,
    강남구 raw 202608):
      - **하층/상층 짝의 연속성**: 같은 (건물, 호)의 21행·22행 186쌍 중
        185쌍이 (n, n+1) 연속이다. flrNo가 층과 무관한 값이라면 이런 분포가
        나올 수 없다 — 이게 이 결정의 핵심 근거다.
      - **부호를 지우면 모순이 생긴다**: 유일한 음수 행(flrNo=-1,
        flrNoNm='복수층(하층)-1')의 짝은 22/flrNo=1이다. abs()를 하면 하층과
        상층이 둘 다 1층이 되어 "복층"이 성립하지 않는다. 부호를 살려야
        지하1층~지상1층 복층이 되고, 그 건물의 층별개요도 정확히 [-1, 1, 2]다.
        (다만 음수 표본이 1건뿐이라, raw가 늘면 재확인할 것.)
      - **이름표 일치**: flrNoNm이 '복수층(하층)4'·'복수층(하층)-1'처럼 flrNo를
        부호까지 그대로 담고 있다. 487행 중 이름표가 값과 모순되는 행은 1건뿐
        (아래 참고).
    ⚠️ **근거로 쓰지 말 것 — 층별개요 실재층 대조**: "복원한 층이 그 건물에
    실제로 있는 층인가"를 대조하면 486/487(99.8%)이 나오지만, 이건 아무것도
    증명하지 못한다. 적대검증에서 flrNo 대신 그 건물 층 범위의 **난수**를
    300회 넣어도 100% 일치가 나왔다 — 이 건물들은 층 목록이 촘촘해 어떤 값이든
    실재 층에 걸린다. 같은 함정을 다시 파지 않도록 여기 남긴다.
    참고로 유일한 모순 행(PNU 1168010300112800000, 이름표 '지5~지3,지1'인데
    flrGbCd=21·flrNo=1)은 exposPubuseGbCd='2'(공용)라 unit 테이블에 애초에
    반영되지 않고, 값 자체도 그 동의 grndFlrCnt=0을 넘어 물리적으로 불가능한
    소스 오류다. 실제 unit에 반영되는 전유 441행에서는 확인된 오류가 0건이다.
    flrNo가 0인 행은 방향도 층수도 없어 그대로 None이다(이름표에 '1~5층',
    '지5~지3, 지1' 같은 범위가 섞여 한 층으로 환원 자체가 불가).
    ⚠️ 알려진 한계: flrNo의 절대값이 99면 ROOFTOP_FLOOR(옥탑) 표식과 구분되지
    않는다. 이는 "옥탑=99" 규격 자체의 한계로 지상 '20' 경로에도 똑같이 있다
    (강남 실측 최대 |flrNo|=35라 현재 영향 0건). 고층 지역 확장 시 재검토.

    나머지 코드는 공식 층구분코드표(00 미지정 / 40 각층) 기준으로 의도적
    None이다 — '40' 각층은 단일 층으로 환원 자체가 불가하고(EV·계단 등,
    flrNo=0으로 옴), '00'은 미지정. 추측 매핑 금지 원칙(CLAUDE.md)에 따른다.
    """
    code = "" if flr_gb_cd is None else str(flr_gb_cd).strip()
    if code == FLR_GB_ROOFTOP:
        return ROOFTOP_FLOOR
    if code in FLR_GB_MULTI:
        n = _to_int(flr_no)
        # 0/결측은 None (절대 규칙 4). 부호는 flrNo가 들고 있으므로 abs()하지 않는다.
        return n or None
    if code not in (FLR_GB_UNDER, FLR_GB_GROUND):
        return None
    n = _to_int(flr_no)
    if n is None or n == 0:
        return None
    n = abs(n)
    return -n if code == FLR_GB_UNDER else n


def sum_parking(item):
    """주차 4종 합. 전부 결측이면 None, 일부만 있으면 있는 것만 더한다."""
    values = [_to_int(item.get(f)) for f in PARKING_FIELDS]
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present)


def _is_jiphap(item):
    """regstrGbCd로 집합건물 여부 판정 (건물 레코드·전유부/층별개요 행 양쪽에서 재사용).

    코드값(regstrGbCd)으로 비교한다 — 로컬라이즈된 이름(regstrGbCdNm)은 인코딩·
    공백 변형에 취약해 코드 비교가 더 안전하다(resolve_bld_id 후보 좁히기 ②에서
    행 자신이 들고 있는 이 값과 건물의 이 값을 직접 대조한다).
    """
    return str(item.get("regstrGbCd") or "").strip() == REGSTR_GB_JIPHAP


def build_building_record(pnu, item):
    """표제부 item -> building 테이블 upsert용 dict.

    여기서 만드는 bld_id는 base_id(동 단위)일 뿐이다 — build_buildings()가
    대장PK 순번을 반영해 최종 bld_id로 덮어쓴다.
    """
    dong = (item.get("dongNm") or "").strip()
    return {
        "bld_id": make_bld_id(pnu, dong),
        "pnu": pnu,
        "dong_nm": dong or None,
        "bld_nm": (item.get("bldNm") or "").strip() or None,
        "total_area_m2": _to_float(item.get("totArea")),
        "ground_floors": _to_int(item.get("grndFlrCnt")),
        "under_floors": _to_int(item.get("ugrndFlrCnt")),
        "approve_date": parse_use_apr_day(item.get("useAprDay")),
        "main_use": (item.get("mainPurpsCdNm") or "").strip() or None,
        "bcr": _to_float(item.get("bcRat")),
        "far": _to_float(item.get("vlRat")),
        "parking_cnt": sum_parking(item),
        "is_jiphap": _is_jiphap(item),
    }


def read_jsonl(path):
    """raw JSONL을 [{"pnu","fetched_at","item"}, ...]로 읽는다. 없으면 빈 목록.

    깨진 줄(JSON 파싱 실패)은 건너뛰고 개수만 세어 두 번째 반환값으로 돌려준다.
    """
    rows = []
    broken = 0
    if not os.path.exists(path):
        return rows, broken
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                broken += 1
                continue
            if isinstance(obj, dict) and obj.get("pnu") and isinstance(obj.get("item"), dict):
                rows.append(obj)
            else:
                broken += 1
    return rows, broken


def latest_batch_by_pnu(rows):
    """PNU마다 fetched_at이 가장 늦은 배치의 행만 남긴다 (중복 수집 2차 방어선).

    같은 PNU를 두 번 수집하면 raw에 두 배치가 쌓이는데, 그대로 두면 전용면적
    합계가 두 배로 부풀어 오른다. 배치 = 같은 (pnu, fetched_at) 묶음.
    """
    latest = {}
    for row in rows:
        pnu = row["pnu"]
        fetched_at = row.get("fetched_at") or ""
        if pnu not in latest or fetched_at > latest[pnu]:
            latest[pnu] = fetched_at
    return [r for r in rows if (r.get("fetched_at") or "") == latest[r["pnu"]]]


def build_buildings(title_rows):
    """표제부 raw 행 -> (bld_id -> building dict, 통계).

    bld_id는 원칙적으로 make_bld_id_from_pk(pnu, mgmBldrgstPk) — 대장PK 자체가
    영속 식별자이므로 raw 안에 같은 PNU의 다른 건물이 무엇이 있든, 몇 번째
    수집이든 항상 같다(적대검증 Critical 수정 — 예전 "정렬 순번" 방식은 재수집
    때 새 대장PK가 섞여 들어오면 순번이 흔들려 기존 unit들의 FK가 조용히 다른
    건물로 넘어가는 결함이 있었다).

    실측(2026-08-08, 라이브 raw 461,027행 전량 스트리밍): mgmBldrgstPk 결측
    0행(title/flr_ouln/expos_area 전부), (PNU, 대장PK) 고유 조합 5,903개 =
    building 행수와 정확히 일치, 한 대장PK가 서로 다른 동명칭을 갖는 경우
    0건 — (PNU, 대장PK)가 건물과 1:1이라는 근거.

    대장PK가 비어 있는(현재 raw는 0행이지만 방어) 행만 make_bld_id(pnu, dongNm)
    폴백을 쓴다. 같은 bld_id가 여러 행으로 중복 등장하면(raw에 같은 건물이
    두 번 실린 경우) 첫 행만 채택하고 나머지는 duplicated_bld_id로만 센다.

    반환: records(bld_id -> building dict), stats(rows, duplicated_bld_id,
          pk_missing_fallback, buildings_by_pnu, pnu_with_building)
    """
    records = {}
    buildings_by_pnu = defaultdict(list)
    duplicated = 0
    pk_missing = 0

    for row in title_rows:
        pnu = row["pnu"]
        item = row["item"]
        mgm_pk = _normalize_pk(item.get("mgmBldrgstPk"))
        if mgm_pk:
            bld_id = make_bld_id_from_pk(pnu, mgm_pk)
        else:
            bld_id = make_bld_id(pnu, item.get("dongNm"))
            pk_missing += 1

        if bld_id in records:
            duplicated += 1
            continue

        rec = build_building_record(pnu, item)
        rec["bld_id"] = bld_id
        records[bld_id] = rec
        buildings_by_pnu[pnu].append(bld_id)

    return records, {
        "rows": len(title_rows),
        "duplicated_bld_id": duplicated,
        "pk_missing_fallback": pk_missing,
        "buildings_by_pnu": dict(buildings_by_pnu),
        "pnu_with_building": set(buildings_by_pnu.keys()),
    }


def _narrow_by(pool, buildings, key_fn, row_value):
    """pool(bld_id 목록)을 key_fn(building) == row_value 인 것만 남겨 좁힌다.

    정확히 1개로 좁혀지면 그 bld_id를, 아니면 (None, 다음 단계에 넘길 pool)을
    돌려준다. 아무것도 안 남으면(0개) 이 속성으로는 판단할 근거가 없다는
    뜻이므로 원래 pool을 그대로 유지한다 — "모른다"를 "다르다"로 취급해
    후보를 통째로 날리지 않는다(CLAUDE.md 추측 매핑 금지의 연장).
    """
    narrowed = [c for c in pool if key_fn(buildings[c]) == row_value]
    if len(narrowed) == 1:
        return narrowed[0], narrowed
    return None, (narrowed if narrowed else pool)


def resolve_bld_id(pnu, dong_nm, mgm_pk, bld_nm, is_jiphap, buildings, buildings_by_pnu):
    """층별개요·전유부 행 하나를 building에 귀속시킨다. (bld_id, 사유) — 못 찾으면 (None, 사유).

    우선순위:
      ① (pnu, 대장PK) 직접 조회 — bld_id가 이제 이 조합만으로 결정되므로
         (make_bld_id_from_pk), 후보를 만들어 buildings에 있는지 확인하면
         끝난다. 실측(2026-08-08): 층별개요는 표제부와 대장PK가 100% 일치해
         이 경로가 사실상 전부를 처리한다. 전유공용면적의 mgmBldrgstPk는
         표제부와 다른 값 공간(전유부 자체의 관리번호)이라 이 경로는 거의
         항상 no-op이다(실측: 매칭 0/392,070) — 그래도 시도 자체는 무해하다.
      ② 그 PNU에 건물이 하나뿐이면 그걸로 확정(모호성 자체가 없다).
      ③ 후보가 2개 이상이면 "후보 좁히기"로 유일해질 때까지 단계적으로
         거른다 — 전부 *행이 실제로 들고 있는 값끼리 비교*이지 추측이 아니다:
           (a) 동명칭 일치 (공백 정규화, 공란도 유효한 비교값)
           (b) 대장구분(집합/일반, regstrGbCd) 일치
           (c) 건물명(bldNm) 일치
         각 단계는 남은 후보 중에서 정확히 1개로 좁혀질 때만 확정하고, 그
         전 단계에서 걸러진 후보 집합을 다음 단계로 넘긴다(순차 좁히기).
         끝까지 유일해지지 않으면 임의로 고르지 않고 스킵한다(2차 적대검증
         Critical 수정 — 예전에는 base_id 문자열이 우연히 일치하면 모호성
         체크 없이 그 건물로 단정해 조용히 오귀속했다. 실측 강남구: 표제부
         기준 건물 2개 이상인 PNU 117개 중 동명칭으로 못 가르는 23개·15,656행
         가운데 (a)가 14,748행, (b)가 639행을 추가로 해소하고, 진짜 판정
         불가는 269행뿐이다).
    """
    normalized_pk = _normalize_pk(mgm_pk)
    if normalized_pk:
        candidate = make_bld_id_from_pk(pnu, normalized_pk)
        if candidate in buildings:
            return candidate, "대장PK 매칭"

    candidates = buildings_by_pnu.get(pnu) or []
    if not candidates:
        return None, "표제부에 해당 PNU 건물 없음"
    if len(candidates) == 1:
        return candidates[0], "PNU 단일 건물로 귀속"

    pool = candidates

    dong = (dong_nm or "").strip()
    hit, pool = _narrow_by(pool, buildings, lambda b: (b.get("dong_nm") or ""), dong)
    if hit:
        return hit, "동명칭 일치"

    hit, pool = _narrow_by(pool, buildings, lambda b: b.get("is_jiphap"), bool(is_jiphap))
    if hit:
        return hit, "대장구분(집합/일반) 일치"

    name = (bld_nm or "").strip()
    hit, pool = _narrow_by(pool, buildings, lambda b: (b.get("bld_nm") or ""), name)
    if hit:
        return hit, "건물명 일치"

    return None, "동명칭·대장구분·건물명으로도 유일하게 좁혀지지 않음(귀속 불가)"


def build_floor_use_lookup(flr_rows, buildings, buildings_by_pnu):
    """층별개요 raw 행 -> {(bld_id, floor_no): 주용도명}, 통계.

    bld_id는 반드시 build_units와 같은 규칙(resolve_bld_id)으로 정한다(대장PK
    우선, 그다음 동명칭). 같은 (건물, 층)이 여러 번 나오면 첫 값을 유지한다
    (대장상 같은 층이 여러 줄로 쪼개진 경우 — 주용도는 대표값 하나면 충분).
    """
    lookup = {}
    floor_unmapped = Counter()
    resolve_reasons = Counter()
    unresolved = 0
    for row in flr_rows:
        item = row["item"]
        floor_no = floor_from_codes(item.get("flrGbCd"), item.get("flrNo"))
        if floor_no is None:
            floor_unmapped["flrGbCd={!r} flrNo={!r}".format(
                item.get("flrGbCd"), item.get("flrNo"))] += 1
            continue
        bld_id, reason = resolve_bld_id(
            row["pnu"], item.get("dongNm"), item.get("mgmBldrgstPk"),
            item.get("bldNm"), _is_jiphap(item), buildings, buildings_by_pnu)
        resolve_reasons[reason] += 1
        if bld_id is None:
            unresolved += 1
            continue
        purpose = (item.get("mainPurpsCdNm") or "").strip() or None
        if purpose is None:
            continue
        lookup.setdefault((bld_id, floor_no), purpose)
    return lookup, {
        "rows": len(flr_rows),
        "floor_unmapped": floor_unmapped,
        "resolve_reasons": resolve_reasons,
        "unresolved": unresolved,
    }


def build_floors(flr_rows, buildings, buildings_by_pnu):
    """층별개요 raw 행 -> (building_floor dict 목록, 통계).

    한 행 = "그 층의 한 용도 구획"이다. 원본은 한 층이 용도별로 여러 줄로 쪼개져
    오므로(실측: 어느 4층 하나가 사무소·일반음식점 5개·예식장 4개·복도·계단 등
    19줄) 층 하나로 뭉치지 않고 그대로 담는다 — 뭉치는 건 뷰(v_building_floor_stack)로
    언제든 되지만 버린 세부는 되살릴 수 없다.

    같은 (건물, 층, 용도코드, 세부용도, 연면적제외, 부속구분) 키가 여러 줄로 오면
    면적을 합산하고 합쳐진 줄 수를 src_row_cnt에 남긴다 — 원본에 행을 1:1로 가리킬
    자연키가 없기 때문이다(make_floor_id 참조). build_units가 (건물, 층, 호)에
    쓰는 것과 같은 해법이다.

    ⚠️ 이 함수는 unit.floor_use를 채우는 build_floor_use_lookup과 **별개**다.
    같은 raw를 두 번 훑지만 목적이 다르다 — 룩업은 층당 대표 용도 하나(첫 값)만
    필요하고, 여기는 구획을 전부 보존한다. 룩업의 "첫 값" 규칙을 "면적 최대"로
    바꾸면 라이브 unit.floor_use 값이 바뀌므로 이번 범위에서 건드리지 않는다.

    건물 귀속은 build_units와 반드시 같은 규칙(resolve_bld_id)을 쓴다. 실측
    (2026-08-07 강남 raw 63,053행): 대장PK 매칭 100%, 귀속 실패 0건.
    """
    grouped = {}
    stats = Counter()
    floor_unmapped = Counter()
    resolve_reasons = Counter()

    for row in flr_rows:
        item = row["item"]
        stats["rows"] += 1

        floor_no = floor_from_codes(item.get("flrGbCd"), item.get("flrNo"))
        if floor_no is None:
            floor_unmapped["flrGbCd={!r} flrNo={!r}".format(
                item.get("flrGbCd"), item.get("flrNo"))] += 1
        # 층 판정 불가여도 행 자체는 살린다(floor_no=NULL 허용 — 절대 규칙 4).
        # 스택에 쌓을 자리가 없을 뿐이라 v_building_floor_stack이 걸러낸다.

        pnu = row["pnu"]
        bld_id, reason = resolve_bld_id(
            pnu, item.get("dongNm"), item.get("mgmBldrgstPk"),
            item.get("bldNm"), _is_jiphap(item), buildings, buildings_by_pnu)
        resolve_reasons[reason] += 1
        if bld_id is None:
            stats["건물 귀속 실패로 스킵"] += 1
            continue

        purps_cd = str(item.get("mainPurpsCd") or "").strip() or None
        # 세부용도는 여기서 한 번만 공백 정규화한다 — 그룹 키와 floor_id가 항상
        # 같은 표기를 쓰게 하려는 것(build_units의 ho와 같은 이유).
        etc = "".join(str(item.get("etcPurps") or "").split()) or None
        excluded = str(item.get("areaExctYn") or "").strip() == AREA_EXCLUDED_YN
        annex = str(item.get("mainAtchGbCd") or "").strip() == MAIN_ATCH_ANNEX

        key = (bld_id, floor_no, purps_cd, etc, excluded, annex)
        area = _to_float(item.get("area"))

        if key not in grouped:
            grouped[key] = {
                "floor_id": make_floor_id(bld_id, floor_no, purps_cd, etc, excluded, annex),
                "bld_id": bld_id,
                "pnu": pnu,
                "floor_no": floor_no,
                "flr_gb_nm": (item.get("flrGbCdNm") or "").strip() or None,
                "flr_no_nm": (item.get("flrNoNm") or "").strip() or None,
                "main_purps_cd": purps_cd,
                "main_purps_nm": (item.get("mainPurpsCdNm") or "").strip() or None,
                "etc_purps": etc,
                "strct_nm": (item.get("strctCdNm") or "").strip() or None,
                "area_m2": None,
                "area_excluded": excluded,
                "is_annex": annex,
                "src_row_cnt": 0,
            }
        rec = grouped[key]
        rec["src_row_cnt"] += 1
        if area is not None:
            rec["area_m2"] = area if rec["area_m2"] is None else rec["area_m2"] + area
            stats["면적 합산 행"] += 1
        else:
            stats["area 결측"] += 1

    floors = list(grouped.values())
    stats["층 구획"] = len(floors)
    stats["연면적 제외분"] = sum(1 for f in floors if f["area_excluded"])
    stats["부속건축물"] = sum(1 for f in floors if f["is_annex"])
    stats["여러 줄이 합쳐진 구획"] = sum(1 for f in floors if f["src_row_cnt"] > 1)
    return floors, {
        "counts": stats,
        "floor_unmapped": floor_unmapped,
        "resolve_reasons": resolve_reasons,
    }


def build_units(expos_rows, buildings, buildings_by_pnu, floor_use_lookup):
    """전유공용면적 raw 행 -> (unit dict 목록, 통계).

    전유(exposPubuseGbCd='1')만 (건물, 층, 호)로 묶어 area를 합산한다. 호실
    이름(hoNm)은 여기서 한 번만 정규화한다 — 내부 공백까지 제거해 그룹 키와
    unit_id가 항상 같은 표기를 쓰게 한다('101 호'와 '101호'가 다른 그룹으로
    갈라지면 같은 PK를 만들면서도 면적이 나뉘어 저장되는 조용한 버그가 된다,
    수정 4).
    """
    grouped = {}
    stats = Counter()
    floor_unmapped = Counter()
    resolve_reasons = Counter()

    for row in expos_rows:
        item = row["item"]
        stats["rows"] += 1

        if str(item.get("exposPubuseGbCd") or "").strip() != EXPOS_GB_PRIVATE:
            stats["공용 등 제외"] += 1
            continue

        floor_no = floor_from_codes(item.get("flrGbCd"), item.get("flrNo"))
        if floor_no is None:
            floor_unmapped["flrGbCd={!r} flrNo={!r}".format(
                item.get("flrGbCd"), item.get("flrNo"))] += 1
        # 층 판정 불가여도 호실 자체는 살린다 (floor_no=NULL 허용 — 절대 규칙 4)

        pnu = row["pnu"]
        bld_id, reason = resolve_bld_id(
            pnu, item.get("dongNm"), item.get("mgmBldrgstPk"),
            item.get("bldNm"), _is_jiphap(item), buildings, buildings_by_pnu)
        resolve_reasons[reason] += 1
        if bld_id is None:
            stats["건물 귀속 실패로 스킵"] += 1
            continue

        ho = "".join((item.get("hoNm") or "").split()) or None
        key = (bld_id, floor_no, ho)
        area = _to_float(item.get("area"))

        if key not in grouped:
            grouped[key] = {
                "unit_id": make_unit_id(bld_id, floor_no, ho),
                "bld_id": bld_id,
                "pnu": pnu,
                "floor_no": floor_no,
                "ho": ho,
                "excl_area_m2": None,
                "floor_use": floor_use_lookup.get((bld_id, floor_no)),
            }
        if area is not None:
            current = grouped[key]["excl_area_m2"]
            grouped[key]["excl_area_m2"] = area if current is None else current + area
            stats["면적 합산 행"] += 1
        else:
            stats["area 결측"] += 1

    units = list(grouped.values())
    stats["전유 호실"] = len(units)
    stats["floor_use 채움"] = sum(1 for u in units if u["floor_use"])
    return units, {
        "counts": stats,
        "floor_unmapped": floor_unmapped,
        "resolve_reasons": resolve_reasons,
    }


def assert_no_zero_floor(records, field="floor_no"):
    """층 0이 한 건이라도 있으면 즉시 멈춘다 (절대 규칙 4 / DB CHECK 사전 차단)."""
    bad = [r for r in records if r.get(field) == 0]
    if bad:
        raise RuntimeError(
            "층 0인 행이 {}건 있습니다 — 층 매핑 로직을 확인하세요 (예: {}).".format(
                len(bad), bad[0])
        )
    return len(records)


def assert_unique(records, field):
    """records의 field 값이 전부 유일한지 확인한다 — 업서트 직전 PK 충돌 사전 차단.

    building은 bld_id, unit은 unit_id가 대상. dict에서 만든 값이라 이론상
    대개 유일하지만, base_id 뒤에 대장PK 순번을 이어붙이는 방식(build_buildings)
    이나 호 표기 정규화(build_units)가 우연히 다른 조합과 같은 문자열을 만들
    가능성을 사전에 잡는다(예: 동명칭이 우연히 'MAIN_2'인 건물과 순번 2가 붙은
    건물의 충돌).
    """
    seen = set()
    dup = None
    for r in records:
        v = r.get(field)
        if v in seen:
            dup = v
            break
        seen.add(v)
    if dup is not None:
        raise RuntimeError(
            "{} 값이 중복된 행이 있습니다 (예: {!r}) — upsert 전에 반드시 해결해야 합니다.".format(
                field, dup)
        )
    return len(records)


def classify_missing_pnu(pnu, pnu_in_raw_title, pnu_with_building, pending_pnus, failed_pnus):
    """building이 안 붙은 PNU의 사유를 분류한다 (§5.6 보고용).

    pending/failed는 조인 성공률(b) 분모에서 제외해야 하는 두 바구니다 — 아직
    안 걷었거나(pending) 실패해서 재시도 대기 중인(failed) PNU를 "정규화 로직이
    깨졌다"는 증거로 잘못 세면 안 된다.
    """
    if pnu in pnu_with_building:
        return None
    if pnu[10:11] == PLAT_GB_MOUNTAIN:
        return "산(대지구분 2) — 건축물 없는 임야가 대부분"
    if pnu[10:11] != PLAT_GB_LAND:
        return "대지구분 코드 미지원 — 수집 대상 제외"
    if pnu in pending_pnus:
        return "미수집(pending)"
    if pnu in failed_pnus:
        return "수집 실패(failed, 재시도 대상)"
    if pnu not in pnu_in_raw_title:
        return "표제부 raw에 아이템 없음 (API 무데이터 또는 미수집)"
    return "수집 완료했으나 API 무데이터"


def join_rate(matched, total):
    """total이 0이면 측정 불가 — 0.0으로 슬쩍 채우면 '0% 미달'로 잘못 읽힌다."""
    return (matched * 100.0 / total) if total else None


def find_truncated_pnu(expos_rows, cap=EXPOS_ROW_TRUNCATION_CAP):
    """전유공용면적 raw 행이 PNU당 cap(기본 10,000)에 도달한 PNU 목록(정렬).

    collect_building_ledger.py의 페이지 상한(NUM_OF_ROWS=100 x MAX_PAGES=100)에
    실제로 걸렸을 가능성이 있다는 뜻 — 그 PNU는 전유행이 잘렸을 수 있으므로
    재수집 검토 대상으로 특정할 수 있게 리포트에 노출한다.
    """
    counts = Counter(row["pnu"] for row in expos_rows)
    return sorted(pnu for pnu, cnt in counts.items() if cnt >= cap)


# ── Supabase(PostgREST) ──────────────────────────────────────────────────────


def get_supabase_config():
    """env에서 URL/서비스키를 읽는다. 값은 절대 print하지 않는다."""
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    url = os.environ.get("SANGGA_SUPABASE_URL")
    key = os.environ.get("SANGGA_SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SANGGA_SUPABASE_URL / SANGGA_SUPABASE_SERVICE_KEY가 .env에 없습니다."
        )
    return url.rstrip("/"), key


def rest_select(base_url, headers, table, query, page_size=SELECT_PAGE_SIZE, order="pnu"):
    """PostgREST select를 offset/limit로 끝까지 훑어 dict 목록을 돌려준다.

    order를 항상 붙인다 — 정렬 없는 limit/offset 페이지네이션은 PostgreSQL이
    반환 순서를 보장하지 않아 페이지 경계에서 행이 누락되거나 중복될 수 있다
    (collect_building_ledger.py가 이미 페이지네이션 쿼리마다 order를 넣는 관례).
    네트워크 오류는 재실행하면 이어서 처리되도록 안내를 붙여 RuntimeError로
    바꾼다.
    """
    rows = []
    offset = 0
    while True:
        url = "{}/rest/v1/{}?{}&order={}&limit={}&offset={}".format(
            base_url, table, query, order, page_size, offset)
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            raise RuntimeError(
                "{} 조회 중 네트워크 오류: {}. 같은 명령을 다시 실행하면 이어서 "
                "처리됩니다.".format(table, e)
            )
        if r.status_code >= 300:
            raise RuntimeError("{} 조회 실패 (HTTP {}): {}".format(
                table, r.status_code, r.text[:300]))
        chunk = r.json()
        if not isinstance(chunk, list):
            raise RuntimeError("{} 조회 응답 형식 이상: {!r}".format(table, str(chunk)[:200]))
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size
    return rows


def upsert_batch(base_url, headers, table, rows, batch_size=BATCH_SIZE):
    """rows를 batch_size 단위로 table에 upsert. 실제로 보낸 행 수를 돌려준다.

    네트워크 오류는 "이미 올라간 배치는 그대로, 같은 명령을 다시 실행하면
    이어서 채운다"는 안내와 함께 RuntimeError로 바꾼다 — 64개 배치 중 하나가
    타임아웃으로 죽어도 traceback만 남기고 끝나지 않게 한다.
    """
    resolution = TABLE_UPSERT_RESOLUTION.get(table)
    if resolution is None:
        raise ValueError(
            "{}: TABLE_UPSERT_RESOLUTION에 정의되지 않은 테이블입니다 — "
            "충돌 해소 정책을 먼저 정의하세요.".format(table)
        )
    upsert_headers = dict(headers)
    upsert_headers["Content-Type"] = "application/json"
    upsert_headers["Prefer"] = "resolution={},return=minimal".format(resolution)

    sent = 0
    total_batches = (len(rows) + batch_size - 1) // batch_size
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        batch_no = i // batch_size + 1
        try:
            r = requests.post(
                "{}/rest/v1/{}".format(base_url, table),
                json=batch, headers=upsert_headers, timeout=TIMEOUT_SEC,
            )
        except requests.RequestException as e:
            raise RuntimeError(
                "{} 배치 {}/{} upsert 중 네트워크 오류: {}. 이미 올라간 배치는 그대로입니다. "
                "같은 명령을 다시 실행하면 이어서 채웁니다.".format(
                    table, batch_no, total_batches, e)
            )
        if r.status_code >= 300:
            raise RuntimeError(
                "{} 배치 {}/{} upsert 실패 (HTTP {}): {}. 이미 올라간 배치는 그대로입니다. "
                "같은 명령을 다시 실행하면 이어서 채웁니다.".format(
                    table, batch_no, total_batches, r.status_code, r.text[:500]
                )
            )
        sent += len(batch)
        print("  [{}] {}/{} 배치 {}행 (누적 {:,}/{:,})".format(
            table, batch_no, total_batches, len(batch), sent, len(rows)), flush=True)
    return sent


def _pgrst_in_list(values):
    """PostgREST in.(...) 필터 문자열을 만든다. 각 값을 큰따옴표로 감싼다.

    unit_id에는 호실명이 그대로 들어가 한글·공백·콤마·괄호가 섞일 수 있다.
    감싸지 않으면 값 안의 콤마가 구분자로 읽혀 엉뚱한 행이 지워진다.
    """
    quoted = ['"{}"'.format(str(v).replace("\\", "\\\\").replace('"', '\\"'))
              for v in values]
    return "in.({})".format(",".join(quoted))


def delete_stale_units(base_url, headers, unit_records, period_key, raw_row_counts,
                       truncated_pnus,
                       pnu_chunk=STALE_PNU_CHUNK, delete_chunk=STALE_DELETE_CHUNK):
    """계산 결과에 없는 옛 unit 행을 지운다 (_delete_stale_rows의 unit용 껍데기).

    왜 unit에 필요한가: unit_id에 층이 들어간다(make_unit_id -> bld_id_층_호).
    층 판정 규칙이 바뀌면 같은 호실의 unit_id가 통째로 바뀐다 — 복수층 복원 전
    '..._NA_501호'였던 행이 복원 후 '..._5_501호'가 되는 식이다. 적재는 upsert뿐이라
    새 행만 생기고 옛 행은 남아, 같은 호실이 두 줄이 되어 전용면적이 이중 집계된다.
    """
    return _delete_stale_rows(
        base_url, headers, "unit", "unit_id", unit_records, period_key,
        raw_row_counts, truncated_pnus, pnu_chunk, delete_chunk)


def delete_stale_floors(base_url, headers, floor_records, period_key, raw_row_counts,
                        truncated_pnus,
                        pnu_chunk=STALE_PNU_CHUNK, delete_chunk=STALE_DELETE_CHUNK):
    """계산 결과에 없는 옛 building_floor 행을 지운다 (_delete_stale_rows의 층용 껍데기).

    왜 층에도 필요한가: floor_id에 층·용도코드·세부용도가 들어간다(make_floor_id).
    층 판정이나 용도 표기가 바뀌면 키가 바뀌어 옛 행이 남고, 그러면 같은 층 면적이
    v_building_floor_stack에서 이중으로 더해진다 — unit과 정확히 같은 함정이다.

    ⚠️ truncated_pnus는 전유공용면적(expos_area)의 페이지 절단 목록이라 층별개요와
    직접 관계가 없다. 그래도 그대로 넘겨 그 PNU들을 정리 대상에서 빼는 쪽을 택했다 —
    옛 행이 남는 것(면적 이중 집계, 재실행으로 정리됨)보다 멀쩡한 행이 지워지는 쪽이
    훨씬 비싸기 때문이다. 보수적으로 트는 것이 이 함수 전체의 설계 기조다.
    """
    return _delete_stale_rows(
        base_url, headers, "building_floor", "floor_id", floor_records, period_key,
        raw_row_counts, truncated_pnus, pnu_chunk, delete_chunk)


def _delete_stale_rows(base_url, headers, table, id_field, records, period_key,
                       raw_row_counts, truncated_pnus, pnu_chunk, delete_chunk):
    """원본이 온전함이 확인된 PNU 범위 안에서, 계산 결과에 없는 옛 행을 지운다.

    unit·building_floor 공용 — 두 테이블 모두 PK에 층 등 "계산으로 정해지는 값"이
    들어가서 규칙이 바뀌면 키가 통째로 바뀌고 옛 행이 남는다. 정리 규칙이 갈라지면
    한쪽만 조용히 이중 집계되므로 로직을 하나로 둔다(호출부는 delete_stale_units /
    delete_stale_floors).

    ⚠️ 삭제 범위를 정하는 규칙이 이 함수의 전부다. "raw에 그 PNU 행이 있다"만
    으로는 부족하다 — 그 PNU를 **이번에 온전히 다시 계산했다**는 보장이 없으면
    멀쩡한 라이브 행이 "이제 없는 행"으로 오인돼 지워진다. 실제로 두 경로가
    있다(독립 코드리뷰 지적, 2026-08-07):
      (1) raw 파일 일부 손상 — read_jsonl은 깨진 줄을 세고 건너뛴 뒤 나머지를
          그대로 처리하므로, 그 PNU는 "행이 있긴 한데 일부만" 있는 상태가 된다.
      (2) `--raw-dir`로 작은/오래된 폴더를 지정 — 이 옵션은 upsert 전용이던
          시절엔 무해했지만(최악이 '덜 채움'), 삭제가 붙은 뒤로는 파괴적이다.
      (3) 전유공용면적 응답이 페이지 상한(10,000행)에서 잘린 PNU — 재수집 때
          API가 같은 부분집합을 준다는 보장이 없어, 이전에 정상 적재됐던 행이
          "이번 raw에 없다"는 이유만으로 지워질 수 있다. row_count도 잘린 값이
          그대로 저장돼 있어 (2)의 대조로는 걸러지지 않는다.
    그래서 PNU마다 아래 세 조건을 **전부** 만족할 때만 삭제 범위에 넣는다:
      - collect_progress(collector='bldrgst', period_key)에서 status='done'
      - 그 행의 row_count == 이번 raw에서 센 그 PNU의 행 수(raw_row_counts)
      - truncated_pnus(find_truncated_pnu 결과)에 들어 있지 않을 것
    row_count는 수집기가 저장한 "API가 준 아이템 수의 합"이라 raw가 잘리거나
    폴더가 부분집합이면 즉시 어긋난다(2026-08-07 실측: 강남 5,375개 PNU 전부
    정확히 일치, 불일치 0건 — 판정 기준으로 쓸 수 있음이 확인됐다).
    조건을 못 채운 PNU는 조용히 넘어가지 않고 개수를 출력한다.

    호출 순서 전제 — 반드시 upsert 뒤에 부른다. 먼저 지우고 적재하다 중간에
    죽으면 데이터가 사라지지만, 적재 후 지우면 최악의 경우 중복이 남을 뿐이라
    다시 실행하면 정리된다.

    반환: 지운 행 수.
    """
    if not records:
        return 0

    keep = {r[id_field] for r in records}
    candidates = {r["pnu"] for r in records}
    done_counts = fetch_done_row_counts(base_url, headers, period_key)
    truncated = set(truncated_pnus or ())
    pnus = sorted(
        p for p in candidates
        if p not in truncated
        and done_counts.get(p) is not None
        and done_counts[p] == raw_row_counts.get(p, 0)
    )
    skipped = len(candidates) - len(pnus)
    if skipped:
        print("  [{}] 원본 완전성 미확인 PNU {:,}개는 정리 대상에서 제외 "
              "(collect_progress done + row_count 일치인 PNU만 정리)".format(table, skipped),
              flush=True)
    if not pnus:
        print("  [{}] 정리 가능한 PNU 없음 — 옛 행 정리를 건너뜁니다".format(table), flush=True)
        return 0

    stale = []
    for i in range(0, len(pnus), pnu_chunk):
        part = pnus[i:i + pnu_chunk]
        rows = rest_select(
            base_url, headers, table,
            "select={}&pnu=in.({})".format(id_field, ",".join(part)),
            order=id_field,
        )
        stale.extend(r[id_field] for r in rows if r[id_field] not in keep)

    if not stale:
        print("  [{}] 정리할 옛 행 없음".format(table), flush=True)
        return 0

    deleted = 0
    total_batches = (len(stale) + delete_chunk - 1) // delete_chunk
    for i in range(0, len(stale), delete_chunk):
        part = stale[i:i + delete_chunk]
        batch_no = i // delete_chunk + 1
        try:
            r = requests.delete(
                "{}/rest/v1/{}".format(base_url, table),
                params={id_field: _pgrst_in_list(part)},
                headers=headers, timeout=TIMEOUT_SEC,
            )
        except requests.RequestException as e:
            raise RuntimeError(
                "{} 옛 행 삭제 {}/{} 중 네트워크 오류: {}. 적재 자체는 끝났으므로 "
                "같은 명령을 다시 실행하면 남은 옛 행부터 정리합니다.".format(
                    table, batch_no, total_batches, e)
            )
        if r.status_code >= 300:
            raise RuntimeError(
                "{} 옛 행 삭제 {}/{} 실패 (HTTP {}): {}. 적재 자체는 끝났으므로 "
                "같은 명령을 다시 실행하면 남은 옛 행부터 정리합니다.".format(
                    table, batch_no, total_batches, r.status_code, r.text[:300])
            )
        deleted += len(part)
        print("  [{}] 옛 행 정리 {}/{} 배치 {}행 (누적 {:,}/{:,})".format(
            table,
            batch_no, total_batches, len(part), deleted, len(stale)), flush=True)
    return deleted


def assert_tables_exist(base_url, headers, tables):
    """적재를 시작하기 전에 대상 테이블이 라이브에 있는지 먼저 확인한다.

    왜 필요한가: upsert는 building -> building_floor -> unit 순서라, 새 테이블이
    아직 안 만들어진 DB에 돌리면 **건물만 들어가고 층에서 멈춰 호실이 빠진** 어중간한
    상태가 된다. 데이터가 깨지진 않지만(재실행하면 정리된다) 원인을 찾는 데 시간이
    든다. 아무것도 건드리기 전에 막고, 무엇을 해야 하는지까지 알려주는 편이 낫다.
    """
    missing = []
    for table in tables:
        try:
            r = requests.get(
                "{}/rest/v1/{}".format(base_url, table),
                params={"select": "*", "limit": "1"},
                headers=headers, timeout=TIMEOUT_SEC,
            )
        except requests.RequestException as e:
            raise RuntimeError("Supabase 연결 실패({}): {}".format(table, e))
        # PostgREST는 없는 테이블에 404를 준다 (권한 문제면 401/403).
        if r.status_code == 404:
            missing.append(table)
        elif r.status_code >= 300:
            raise RuntimeError("{} 조회 실패 (HTTP {}): {}".format(
                table, r.status_code, r.text[:200]))
    if missing:
        raise RuntimeError(
            "라이브 DB에 테이블이 없습니다: {}\n"
            "       Supabase 대시보드 → SQL Editor → New query 에서\n"
            "       supabase/migrations/2026-08-07_building_floor.sql 전체를 붙여넣고 Run 하세요.\n"
            "       (여러 번 실행해도 안전합니다. 기존 데이터는 건드리지 않습니다.)".format(
                ", ".join(missing))
        )


def rest_count(base_url, headers, table, query):
    """PostgREST HEAD 요청으로 정확한 행 수를 돌려준다 (Content-Range 헤더)."""
    h = dict(headers)
    h["Prefer"] = "count=exact"
    try:
        r = requests.head(
            "{}/rest/v1/{}?{}".format(base_url, table, query), headers=h, timeout=60
        )
    except requests.RequestException as e:
        raise RuntimeError(
            "{} count 조회 중 네트워크 오류: {}. 같은 명령을 다시 실행하면 이어서 "
            "처리됩니다.".format(table, e)
        )
    if r.status_code not in (200, 206):
        raise RuntimeError("{} count 조회 실패 (HTTP {}): {}".format(
            table, r.status_code, r.text[:300]))
    content_range = r.headers.get("Content-Range", "")
    if "/" not in content_range:
        raise RuntimeError("{}: Content-Range 헤더 형식 이상: {!r}".format(table, content_range))
    return int(content_range.split("/")[-1])


def fetch_pnu_set(base_url, headers, table, query):
    """table에서 pnu 컬럼만 전량 읽어 set으로 돌려준다."""
    rows = rest_select(base_url, headers, table, query, order="pnu")
    return {r["pnu"] for r in rows if r.get("pnu")}


def fetch_pnu_list(base_url, headers, table, query, order="pnu"):
    """table에서 pnu 컬럼만 전량 읽어 목록으로 돌려준다 (행 단위 비율 계산용)."""
    rows = rest_select(base_url, headers, table, query, order=order)
    return [r.get("pnu") for r in rows]


def fetch_progress_status_sets(base_url, headers, period_key):
    """collect_progress(collector='bldrgst', period_key=...)의 status별 PNU 집합.

    수집 커버리지(§5.6 지표 (a))와 조인 성공률 분모 보정(pending/failed 제외,
    classify_missing_pnu)에 함께 쓰인다.
    """
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=scope_key,status&collector=eq.{}&period_key=eq.{}".format(
            BLDRGST_COLLECTOR, period_key),
        order="scope_key",
    )
    sets = defaultdict(set)
    for r in rows:
        status = r.get("status")
        pnu = r.get("scope_key")
        if status and pnu:
            sets[status].add(pnu)
    return sets


def fetch_done_row_counts(base_url, headers, period_key):
    """수집 완료(status='done') PNU -> 수집 시점 row_count 매핑.

    delete_stale_units가 "이번 raw로 그 PNU를 온전히 다시 계산했는가"를
    판정하는 근거다. row_count가 비어 있는 행은 판정 근거가 없으므로 아예
    빼서, 그런 PNU는 삭제 범위에 들어가지 않게 한다(모르면 지우지 않는다).
    """
    rows = rest_select(
        base_url, headers, "collect_progress",
        "select=scope_key,row_count&collector=eq.{}&period_key=eq.{}&status=eq.done".format(
            BLDRGST_COLLECTOR, period_key),
        order="scope_key",
    )
    return {
        r["scope_key"]: r["row_count"]
        for r in rows
        if r.get("scope_key") and r.get("row_count") is not None
    }


# ── 보고 출력 ────────────────────────────────────────────────────────────────


def print_transform_report(raw_dir, broken_lines, bld_stats, flr_stats, floor_stats,
                           unit_stats, building_count, floor_count, unit_count,
                           truncated_pnus):
    print("=" * 78)
    print("건축물대장 raw → building/building_floor/unit 변환 결과")
    print("=" * 78)
    print("raw 폴더: {}".format(raw_dir))
    print("")
    print("[ raw 행 수 ]")
    print("    표제부(title)            {:>10,}행".format(bld_stats["rows"]))
    print("    층별개요(flr_ouln)       {:>10,}행".format(flr_stats["rows"]))
    print("    전유공용면적(expos_area) {:>10,}행".format(unit_stats["counts"]["rows"]))
    if any(broken_lines.values()):
        print("    [경고] 파싱 불가로 건너뛴 줄: {}".format(
            ", ".join("{} {}줄".format(k, v) for k, v in broken_lines.items() if v)))

    if flr_stats["unresolved"]:
        print("    [경고] 건물 귀속 실패로 floor_use에 못 넣은 층별개요 행: {:,}행".format(
            flr_stats["unresolved"]))

    print("")
    print("[ building ] {:,}행 (would-upsert)".format(building_count))
    if bld_stats["duplicated_bld_id"]:
        print("    같은 bld_id 재등장(raw 중복 행): {:,}건 (첫 행 유지)".format(
            bld_stats["duplicated_bld_id"]))
    print("    대장PK 결측 — 동명칭 폴백: {:,}건 (실측상 0건이 정상)".format(
        bld_stats["pk_missing_fallback"]))
    print("    building이 붙은 PNU: {:,}개".format(len(bld_stats["pnu_with_building"])))

    print("")
    print("[ building_floor ] {:,}행 (would-upsert) — §8.6 층별 스택 뷰의 재료".format(floor_count))
    fcounts = floor_stats["counts"]
    for label in ("건물 귀속 실패로 스킵", "면적 합산 행", "area 결측",
                  "여러 줄이 합쳐진 구획", "연면적 제외분", "부속건축물"):
        print("    {:<22} {:>10,}".format(label, fcounts[label]))
    print("    건물 귀속 사유:")
    for reason, cnt in floor_stats["resolve_reasons"].most_common():
        print("      - {}: {:,}건".format(reason, cnt))

    print("")
    print("[ unit ] {:,}행 (would-upsert)".format(unit_count))
    counts = unit_stats["counts"]
    for label in ("공용 등 제외", "건물 귀속 실패로 스킵", "면적 합산 행", "area 결측",
                  "floor_use 채움"):
        print("    {:<22} {:>10,}".format(label, counts[label]))
    print("    건물 귀속 사유:")
    for reason, cnt in unit_stats["resolve_reasons"].most_common():
        print("      - {}: {:,}건".format(reason, cnt))

    print("")
    print("[ 층 코드 매핑 경고 ] (flrGbCd/flrNo -> None. 0은 절대 만들지 않는다)")
    total_unmapped = (sum(flr_stats["floor_unmapped"].values())
                      + sum(unit_stats["floor_unmapped"].values()))
    if not total_unmapped:
        print("    없음")
    else:
        print("    층별개요 {:,}건 / 전유부 {:,}건".format(
            sum(flr_stats["floor_unmapped"].values()),
            sum(unit_stats["floor_unmapped"].values())))
        merged = Counter()
        merged.update(flr_stats["floor_unmapped"])
        merged.update(unit_stats["floor_unmapped"])
        for value, cnt in merged.most_common(10):
            print("      - {}: {:,}건".format(value, cnt))

    print("")
    print("[ 전유공용면적 {:,}행(페이지 상한) 도달 PNU ] 절단 의심 — 재수집 검토 대상".format(
        EXPOS_ROW_TRUNCATION_CAP))
    if not truncated_pnus:
        print("    없음")
    else:
        print("    {:,}개".format(len(truncated_pnus)))
        for pnu in truncated_pnus:
            print("      - {}".format(pnu))
    print("=" * 78)


def print_join_report(sigungu_code, snapshot_ym, parcel_total, done_total, join_matched,
                      ub_total, ub_covered, ub_join_matched, missing_reasons):
    print("")
    print("=" * 78)
    print("§5.6 건축물대장 조인률 실측 — {} / 상권 스냅샷 {}".format(sigungu_code, snapshot_ym))
    print("=" * 78)

    coverage_rate = join_rate(done_total, parcel_total)
    pending = coverage_rate is not None and coverage_rate < 100.0
    if pending:
        print("⚠ 수집 {:.2f}% 진행 중 — §5.6 최종 판정 보류(잠정치)".format(coverage_rate))
        print("")

    print("[ (a) 수집 커버리지 ] collect_progress done / parcel 전체  (진척도 — 판정 없음)")
    if coverage_rate is None:
        print("    측정 불가 (분모 0 — sigungu_code 필터 확인)")
    else:
        print("    {:,} / {:,}  ->  {:.2f}%".format(done_total, parcel_total, coverage_rate))

    join_rate_value = join_rate(join_matched, done_total)
    print("[ (b) 조인 성공률 ] done PNU 중 building이 1개 이상 붙은 비율  "
          "(목표 {:.0f}%+, §5.6 판정 대상)".format(JOIN_RATE_TARGET))
    if join_rate_value is None:
        print("    측정 불가 (분모 0 — done PNU가 없음)")
    else:
        print("    {:,} / {:,}  ->  {:.2f}%  [{}]".format(
            join_matched, done_total, join_rate_value,
            "달성" if join_rate_value >= JOIN_RATE_TARGET else "미달 — 원인 확인 필요"))

    # ② 점포 PNU 기준 — unit_business 행이 어느 PNU에 속하는지만 본다(그 PNU에 층·호
    # 단위로 실제 조인되는지는 별개 문제. 호실 축 커버리지는 감사 지적 #7의 별도
    # 과제라 여기서는 이름만 정확히 하고 넘어간다). ①과 같은 구조로 진척도(a)와
    # 판정 대상(b)을 분리한다 — 안 그러면 "아직 덜 걷었을 뿐"인 상태가 "미달"로
    # 잘못 찍혀 멀쩡한 정규화 로직을 재점검하러 가게 만든다(수정 3).
    if pending:
        print("⚠ 수집 {:.2f}% 진행 중 — ② 판정도 보류(잠정치)".format(coverage_rate))
        print("")

    ub_coverage_rate = join_rate(ub_covered, ub_total)
    print("[ ② (a) 점포 PNU 기준 커버리지 ] unit_business 행 중 done PNU에 속한 비율  "
          "(진척도 — 판정 없음, 점포 PNU 존재 여부만 확인 — 층·호 단위 조인 아님)")
    if ub_coverage_rate is None:
        print("    측정 불가 (분모 0 — snapshot_ym/시군구 필터 확인)")
    else:
        print("    {:,} / {:,}  ->  {:.2f}%".format(ub_covered, ub_total, ub_coverage_rate))

    ub_join_rate_value = join_rate(ub_join_matched, ub_covered)
    print("[ ② (b) 점포 PNU 기준 조인률 ] done PNU에 속한 점포 행 중 building이 붙은 비율  "
          "(목표 {:.0f}%+, §5.6 판정 대상)".format(JOIN_RATE_TARGET))
    if ub_join_rate_value is None:
        print("    측정 불가 (분모 0 — done PNU에 속한 점포 행이 없음)")
    else:
        print("    {:,} / {:,}  ->  {:.2f}%  [{}]".format(
            ub_join_matched, ub_covered, ub_join_rate_value,
            "달성" if ub_join_rate_value >= JOIN_RATE_TARGET else "미달 — 원인 확인 필요"))

    if missing_reasons:
        print("")
        print("[ building이 안 붙은 PNU 사유별 ] 총 {:,}개".format(sum(missing_reasons.values())))
        for reason, cnt in missing_reasons.most_common():
            print("    - {}: {:,}개".format(reason, cnt))
    print("=" * 78)


# ── 메인 ──────────────────────────────────────────────────────────────────────


def parse_args(argv):
    opts = {
        "raw_dir": None,
        "period_key": DEFAULT_PERIOD_KEY,
        "sigungu_code": DEFAULT_SIGUNGU_CODE,
        "snapshot_ym": DEFAULT_SNAPSHOT_YM,
        "dry_run": "--dry-run" in argv,
    }
    for flag, key in (
        ("--raw-dir", "raw_dir"),
        ("--period-key", "period_key"),
        ("--sigungu-code", "sigungu_code"),
        ("--snapshot-ym", "snapshot_ym"),
    ):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise ValueError("{} 뒤에 값이 필요합니다.".format(flag))
            opts[key] = argv[i + 1]
    if opts["raw_dir"] is None:
        opts["raw_dir"] = os.path.join(
            PROJECT_ROOT, "data", "raw", "bldrgst", opts["period_key"])
    return opts


def load_raw(raw_dir):
    """raw 3종을 읽어 (title, flr, expos, broken 카운트)를 돌려준다.

    각 파일은 PNU별 최신 배치만 남긴다(latest_batch_by_pnu — 중복 수집 방어).
    """
    title, b1 = read_jsonl(os.path.join(raw_dir, RAW_TITLE))
    flr, b2 = read_jsonl(os.path.join(raw_dir, RAW_FLR_OULN))
    expos, b3 = read_jsonl(os.path.join(raw_dir, RAW_EXPOS_AREA))
    broken = {RAW_TITLE: b1, RAW_FLR_OULN: b2, RAW_EXPOS_AREA: b3}
    return (
        latest_batch_by_pnu(title),
        latest_batch_by_pnu(flr),
        latest_batch_by_pnu(expos),
        broken,
    )


def count_raw_rows_by_pnu(*row_lists):
    """PNU별 raw 행 수 (최신 배치 기준, 넘겨받은 목록 전부를 합산).

    collect_progress.row_count(수집기가 저장한 "그 PNU에서 API가 준 아이템 수의
    합")와 대조해 **이번 실행이 그 PNU를 온전히 다시 계산했는지** 판정하는 데
    쓴다 — delete_stale_units가 삭제해도 되는 범위를 정하는 근거다.
    """
    counts = Counter()
    for rows in row_lists:
        for row in rows:
            counts[row["pnu"]] += 1
    return counts


def transform(raw_dir):
    """raw 폴더 -> (building 목록, unit 목록, building_floor 목록, 보고용 통계 묶음)."""
    title_rows, flr_rows, expos_rows, broken = load_raw(raw_dir)
    buildings, bld_stats = build_buildings(title_rows)
    # 층별개요·전유부 모두 같은 건물 귀속 규칙(resolve_bld_id)을 쓴다 — 키가 어긋나면
    # floor_use가 조용히 NULL로 남는다.
    floor_use, flr_stats = build_floor_use_lookup(
        flr_rows, buildings, bld_stats["buildings_by_pnu"])
    floors, floor_stats = build_floors(
        flr_rows, buildings, bld_stats["buildings_by_pnu"])
    units, unit_stats = build_units(
        expos_rows, buildings, bld_stats["buildings_by_pnu"], floor_use)

    building_records = list(buildings.values())
    assert_no_zero_floor(units)
    assert_no_zero_floor(floors)
    assert_unique(building_records, "bld_id")
    assert_unique(units, "unit_id")
    assert_unique(floors, "floor_id")

    return building_records, units, floors, {
        "broken": broken,
        "bld_stats": bld_stats,
        "flr_stats": flr_stats,
        "floor_stats": floor_stats,
        "unit_stats": unit_stats,
        "pnu_in_raw_title": {r["pnu"] for r in title_rows},
        "truncated_pnus": find_truncated_pnu(expos_rows),
        "raw_row_counts": count_raw_rows_by_pnu(title_rows, flr_rows, expos_rows),
    }


def report_join_rate(base_url, headers, sigungu_code, snapshot_ym, period_key, pnu_in_raw_title):
    """§5.6 조인률을 DB 실측으로 재서 출력한다.

    수집 커버리지(진행 중이면 잠정치)와 조인 성공률을 분리한다 — 안 그러면
    "아직 다 못 걷었을 뿐"인 상황을 "정규화 로직이 깨졌다"로 잘못 결론짓고
    이미 검증된 PNU 조립·층 정규화를 다시 뜯게 된다(§5.6 오판 방지, 수정 2).
    """
    parcel_pnus = fetch_pnu_set(
        base_url, headers, "parcel", "select=pnu&pnu=like.{}*".format(sigungu_code))
    building_pnus = fetch_pnu_set(
        base_url, headers, "building", "select=pnu&pnu=like.{}*".format(sigungu_code))
    status_sets = fetch_progress_status_sets(base_url, headers, period_key)
    done_pnus = status_sets.get("done", set()) & parcel_pnus
    pending_pnus = status_sets.get("pending", set()) & parcel_pnus
    failed_pnus = status_sets.get("failed", set()) & parcel_pnus

    missing_reasons = Counter()
    for pnu in parcel_pnus - building_pnus:
        reason = classify_missing_pnu(
            pnu, pnu_in_raw_title, building_pnus, pending_pnus, failed_pnus)
        if reason:
            missing_reasons[reason] += 1

    join_matched = len(done_pnus & building_pnus)

    ub_total = rest_count(
        base_url, headers, "unit_business",
        "select=biz_no&snapshot_ym=eq.{}&pnu=like.{}*".format(snapshot_ym, sigungu_code))
    ub_pnus = fetch_pnu_list(
        base_url, headers, "unit_business",
        "select=pnu&snapshot_ym=eq.{}&pnu=like.{}*".format(snapshot_ym, sigungu_code),
        order="snapshot_ym,biz_no")
    # ② (a) 커버리지 분모=ub_total, 분자=done PNU에 속한 행. ② (b) 조인률은
    # done PNU에 속한 행만을 모집단으로 삼아야 한다 — 아직 안 걷은 PNU의 점포
    # 행까지 분모에 넣으면 "미수집"이 "정규화 실패"로 잘못 찍힌다(수정 3).
    ub_covered = sum(1 for p in ub_pnus if p in done_pnus)
    ub_join_matched = sum(1 for p in ub_pnus if p in done_pnus and p in building_pnus)

    print_join_report(sigungu_code, snapshot_ym, len(parcel_pnus), len(done_pnus), join_matched,
                      ub_total, ub_covered, ub_join_matched, missing_reasons)


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

    raw_dir = opts["raw_dir"]
    if not os.path.isdir(raw_dir):
        print("[에러] raw 폴더를 찾을 수 없습니다: {}".format(raw_dir))
        print("       먼저 python scripts/collectors/collect_building_ledger.py 를 실행하세요.")
        return 1

    print("raw 읽는 중: {}".format(raw_dir), flush=True)
    try:
        building_records, unit_records, floor_records, stats = transform(raw_dir)
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    print_transform_report(raw_dir, stats["broken"], stats["bld_stats"], stats["flr_stats"],
                           stats["floor_stats"], stats["unit_stats"], len(building_records),
                           len(floor_records), len(unit_records), stats["truncated_pnus"])

    if opts["dry_run"]:
        print("")
        print("--dry-run 지정 — DB 적재·조인률 실측을 건너뜁니다.")
        return 0

    if not building_records:
        print("[에러] 적재할 building 행이 없습니다. raw 폴더를 확인하세요.")
        return 1

    print("")
    print("Supabase 연결 확인 중...", flush=True)
    try:
        base_url, key = get_supabase_config()
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1
    headers = {"apikey": key, "Authorization": "Bearer {}".format(key)}

    # 아무것도 건드리기 전에 대상 테이블 존재부터 확인한다 — 반쯤 적재된 상태 방지.
    try:
        assert_tables_exist(base_url, headers, ("building", "building_floor", "unit"))
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    print("적재 시작... (building -> building_floor -> unit 순서, "
          "두 자식 테이블의 bld_id FK 때문에 순서 고정)", flush=True)
    try:
        bld_sent = upsert_batch(base_url, headers, "building", building_records)
        floor_sent = upsert_batch(base_url, headers, "building_floor", floor_records)
        unit_sent = upsert_batch(base_url, headers, "unit", unit_records)
        # 적재 뒤에 정리한다 — 층·용도 판정이 바뀌면 PK가 바뀌어 옛 행이 남는다.
        floor_deleted = delete_stale_floors(
            base_url, headers, floor_records,
            opts["period_key"], stats["raw_row_counts"], stats["truncated_pnus"])
        unit_deleted = delete_stale_units(
            base_url, headers, unit_records,
            opts["period_key"], stats["raw_row_counts"], stats["truncated_pnus"])
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    print("")
    print("=" * 78)
    print("적재 완료: building {:,}행 / building_floor {:,}행 / unit {:,}행".format(
        bld_sent, floor_sent, unit_sent))
    print("           (옛 행 정리: building_floor {:,}행 / unit {:,}행)".format(
        floor_deleted, unit_deleted))
    print("=" * 78)

    print("")
    print("§5.6 조인률 실측 중... (DB 기준)", flush=True)
    try:
        report_join_rate(base_url, headers, opts["sigungu_code"], opts["snapshot_ym"],
                         opts["period_key"], stats["pnu_in_raw_title"])
    except RuntimeError as e:
        print("[에러] 조인률 실측 실패: {}".format(e))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
