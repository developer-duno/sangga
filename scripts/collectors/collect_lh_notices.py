# -*- coding: utf-8 -*-
"""LH 분양·임대 **상가** 공고 → `lh_notice` 표 적재.

왜 이게 필요한가
----------------
이 서비스는 "이미 있는 건물을 들여다보는 곳"이라, 창업자가 실제로 살 수 있는 **지금 뜬
상가 공고**는 한 줄도 없었다. 그건 LH 청약센터에만 있고, 우리 화면을 다 본 사람은 결국
다른 곳으로 가서 처음부터 다시 찾는다. 공공 API 로 열려 있으니 받아 두고, 지금 살아
있는 것만 보여 준다.

무엇을 받나 (실측 2026-08-28)
-----------------------------
포털 `lhLeaseNoticeInfo1` 의 공고문 목록을 1년 창으로 훑는다. 전체 2,913건 중
**UPP_AIS_TP_CD='22'(상가) 531건**만 골라 담는다. 30번 부르면 1년이 다 훑린다
(PG_SZ=100 · 마지막 쪽은 부분).

  · 공고 식별자(PAN_ID)는 **숫자가 아니다** — '0000061158'·'BN-0001342'·'LN-…' 세 갈래.
  · 종류 4종: 23 분양ㆍ(구)임대상가(입찰) / 24 임대상가(추첨) / 43 임대상가(입찰) /
              38 임대상가(공모ㆍ심사)
  · 지역명 17종 = 현행 시도 16 + '전국'(59건).
  · 마감일은 전건 있었지만 공고일(PAN_DT)은 531건 중 181건이 빈 값이다 → NULL 허용.

⛔ 호실 목록·가격은 안 받는다 — 같은 기관의 공급정보 API 가 상가 공고에는 빈 응답을
   준다(2026-08-27 실측 2건). 상세는 공고문 주소(DTL_URL)로 보낸다.

⛔ 지우지 않는다 — 마감된 공고도 창고에 남긴다. 숨기는 일은 읽는 함수가 한다
   (`list_lh_notices`). 지우면 "이 지역에 상가 공고가 얼마나 자주 뜨는가"를 나중에 못
   센다.

왜 psql 경유인가 (REST 가 아니라)
---------------------------------
표 `lh_notice` 는 anon 에게 통째로 닫혀 있어 REST 로는 애초에 못 쓴다. 한 트랜잭션으로
넣고 관문에 걸리면 통째로 되돌리는 것도 psql 이라야 된다(load_sbiz_district.py 와 같은
방식). 새 의존성 0.

쓰는 법
-------
    python scripts/collectors/collect_lh_notices.py --dry-run   # DB 쓰기 0
    python scripts/collectors/collect_lh_notices.py             # 최근 12개월 적재
    python scripts/collectors/collect_lh_notices.py --months 24 --sql-out out.sql

적재한 뒤에는 `scripts/check_lh_notices.py` 의 `LATEST_KNOWN_NOTICE_DATE` 를 이번 판의
가장 최근 공고일로 올린다 — 그게 주간 감시의 유일한 기준선이다.
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# ── API ───────────────────────────────────────────────────────────────────────

BASE_URL = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"

# 상가 공고의 상위 유형코드. **이 값이 이 수집기의 전부다** — 이걸 잘못 짚으면 분양주택·
# 토지 공고가 상가 알림판에 섞인다. 감시 스크립트도 같은 값을 쓰고, 테스트가 둘을 대조한다.
SANGA_UPP_CD = "22"

PAGE_SIZE = 100
# 안전핀. 1년이 30쪽이라 200쪽이면 6년치도 넘는다 — 여기 걸린다는 건 "끝을 못 알아본 채
# 무한히 도는 중"이라는 뜻이라, 예산을 다 태우기 전에 멈춘다.
MAX_PAGES = 200
DEFAULT_MONTHS = 12

TIMEOUT_SEC = 60

# ⚠️ 3 이었다가 5 로 올렸다 — 2026-08-31 첫 예약 실행이 정확히 이것 때문에 실패했다
#    (run 33348733771). 그날 실측으로 드러난 것 셋:
#      ① 포털은 가끔 몇 분씩 느려진다. 같은 시각 로컬에서 1회차 504 → 2회차 성공이었다.
#         즉 **꾸준히 느린 게 아니라 들쭉날쭉**하다 — 그러면 타임아웃을 늘리는 것보다
#         한 번 더 두드리는 쪽이 듣는다.
#      ② 깃허브 러너는 미국(Azure centralus)에 있어 응답이 아예 안 와 60초를 꽉 채운다.
#         3번이면 참을성이 약 3분인데, 그날의 나쁜 구간이 최소 3분이라 통째로 갇혔다
#         (01:49:13 실패 시작 ~ 01:52:30 포기).
#      ③ 한 번 조회가 아니라 **여러 쪽을 차례로** 넘긴다. 어느 한 쪽만 3번 다 놓쳐도
#         전체가 실패하므로, 실패 확률이 쪽 수만큼 곱해진다.
#    5번이면 총 참을성이 60*5 + (5+10+20+40) = 375초 ≈ 6.3분 이라 그날의 구간을 넘긴다.
#    ⛔ 러너를 한국으로 옮기는 길은 막혀 있다(확인 2026-08-31): 지역 선택은 Azure 사설망
#       전용이라 **큰 러너(유료)+본인 Azure 구독+조직 계정**이 필요하고, 집서버(self-hosted)는
#       공개 저장소에 GitHub 이 공식으로 권하지 않는다. 그래서 참을성이 유일한 레버다.
# ⛔ 실패를 삼키는 쪽으로 고치지 말 것. job 이 '성공'으로 기록되면 형제 하트비트가
#    '마지막 성공'만 보고 멀쩡하다고 판단해, **공고를 영영 안 보는 상태**가 조용히 이어진다
#    (이 레포가 가장 여러 번 데인 형태 — 조용한 누락).
RETRY_COUNT = 5
RETRY_BACKOFF_SEC = 5

# 다시 물어봐도 답이 같은 실패 — 재시도는 시간만 버린다.
# 401·403 은 인증키 문제(등록·승인·오타), 404 는 주소가 바뀐 것. 전부 사람이 고쳐야 한다.
NO_RETRY_HTTP_CODES = frozenset({401, 403, 404})

# ── 코드표 ────────────────────────────────────────────────────────────────────

# 화면에 쓸 짧은 이름. 원문(AIS_TP_CD_NM)은 표에 따로 담으므로, 여기 없는 코드가 와도
# 원문을 그대로 쓰면 되지 화면이 빈칸이 되지는 않는다.
KIND_SHORT_NM = {
    "23": "분양 입찰",
    "24": "임대 추첨",
    "43": "임대 입찰",
    "38": "공모·심사",
}

# '전국' 공고. 지역이 없는 게 아니라 **모든 지역**이라, NULL 과 뜻이 정반대다.
NATIONWIDE_NM = "전국"

# LH 지역명 → 우리 시도코드.
#
# ⭐ 손으로 지은 표가 아니라 **라이브 `bjd_code` 실측**이다(2026-08-28):
#    활성 법정동이 있는 시도 16개의 `sido_nm` 을 그대로 옮겼고, 그 16개가 화면의
#    `src/lib/regions.ts` 목록과 정확히 같다.
SIDO_BY_NAME = {
    "서울특별시": "11",
    "전남광주통합특별시": "12",
    "부산광역시": "26",
    "대구광역시": "27",
    "인천광역시": "28",
    "대전광역시": "30",
    "울산광역시": "31",
    "세종특별자치시": "36",
    "경기도": "41",
    "충청북도": "43",
    "충청남도": "44",
    "경상북도": "47",
    "경상남도": "48",
    "제주특별자치도": "50",
    "강원특별자치도": "51",
    "전북특별자치도": "52",
}

# 옛 이름 → **지금 그 자리를 잇는 코드**.
#
# ⚠️ 옛 코드(강원 42·전북 45·전남 46·광주 29·제주 49)로 옮기지 않는다. 그 코드들은
#    `bjd_code` 에서 활성 법정동이 **0개**라(2026-08-28 실측), 그리로 옮기면 그 공고는
#    어느 지역을 골라도 영영 안 보인다 — 조용히 사라지는 쪽이다.
#    2026-08-28 현재 LH 는 이미 새 이름만 쓰지만(531건 전수), 옛 공고가 섞여 들어올 때
#    빈칸이 되지 않게 길을 열어 둔다.
LEGACY_SIDO_BY_NAME = {
    "강원도": "51",
    "전라북도": "52",
    "전라남도": "12",
    "광주광역시": "12",
    "제주도": "50",
}

# 지역명을 하나도 못 옮기면 알림판이 통째로 비는데, 표에는 행이 멀쩡히 들어가 있어
# 아무도 눈치채지 못한다. 절반을 넘기면 "새 이름 하나"가 아니라 **표가 낡은 것**이므로
# 사람이 봐야 한다.
UNKNOWN_SIDO_STOP_RATIO = 0.5

# 우리가 담는 시각의 시간축. CI·서버가 UTC 라도 같은 값이 되도록 못 박는다
# (글로벌 규칙 timezone-consistency — 로컬 의존 함수는 환경마다 답이 달라진다).
KST = datetime.timezone(datetime.timedelta(hours=9), "KST")

BATCH_ROWS = 100


# ── 순수 함수 (네트워크·DB 없음 — 테스트 대상) ────────────────────────────────


def sql_str(value):
    """SQL 문자열 리터럴. 작은따옴표는 두 번 써서 escape 한다."""
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def sql_bool(value):
    return "true" if value else "false"


def window(today=None, months=DEFAULT_MONTHS):
    """조회 창 (시작, 끝) 을 'YYYYMMDD' 로. 끝은 오늘이다.

    ⚠️ '오늘'을 로컬 시계로 정하지 않는다 — CI(UTC)와 내 PC(KST)가 하루 어긋나면
       같은 명령이 다른 창을 훑는다.
    """
    today = today or datetime.datetime.now(KST).date()
    # 달 수를 날짜로: 30.44일/달 근사가 아니라 **달력으로** 뺀다(2월·31일 문제를 피한다).
    y, m = today.year, today.month - months
    while m <= 0:
        y -= 1
        m += 12
    day = min(today.day, 28)  # 말일 차이로 창이 하루 들쭉날쭉하지 않게
    start = datetime.date(y, m, day)
    return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")


def parse_api_date(text):
    """'2026.08.27' · '20260827' · '' → 'YYYY-MM-DD' 또는 None.

    ⛔ 모르는 모양은 **조용히 None 으로 만들지 않는다.** None 은 "원본이 안 적어 줬다"는
       뜻이라, 형식이 바뀐 것과 섞이면 마감일이 통째로 사라져도 아무도 모른다.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    digits = raw.replace(".", "").replace("-", "").replace("/", "").strip()
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError(
            "날짜 모양을 모르겠습니다: {!r} — LH 가 형식을 바꿨을 수 있습니다.".format(raw[:40])
        )
    try:
        d = datetime.date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        raise ValueError("날짜로 읽을 수 없습니다: {!r}".format(raw[:40]))
    return d.isoformat()


def extract_rows(payload):
    """응답에서 공고 목록(dsList)을 꺼낸다.

    응답은 `[{"dsSch":[…]}, {"dsList":[…], "resHeader":[…]}]` 모양이다. 자리(인덱스)로
    집지 않고 **dsList 를 가진 칸**을 찾는다 — 자리로 집으면 순서가 바뀌는 날 조용히
    빈손이 된다.
    """
    if isinstance(payload, dict):
        # 포털이 오류를 낼 때 흔한 모양. 그대로 사람이 읽을 수 있게 던진다.
        raise ValueError("목록이 아니라 객체가 왔습니다: {}".format(
            json.dumps(payload, ensure_ascii=False)[:300]))
    if not isinstance(payload, list):
        raise ValueError("응답이 목록이 아닙니다 ({}).".format(type(payload).__name__))
    for part in payload:
        if isinstance(part, dict) and "dsList" in part:
            rows = part["dsList"]
            if rows is None:
                return []
            if not isinstance(rows, list):
                raise ValueError("dsList 가 목록이 아닙니다 — 응답 형식이 바뀌었습니다.")
            return rows
    raise ValueError(
        "응답에 dsList 칸이 없습니다 — 인증키가 거절됐거나 응답 형식이 바뀌었습니다: {}".format(
            json.dumps(payload, ensure_ascii=False)[:300]))


def is_sanga(rec):
    """상가 공고인가. 상위 유형코드 하나로 가른다."""
    return (rec.get("UPP_AIS_TP_CD") or "").strip() == SANGA_UPP_CD


def map_sido(cnp_nm):
    """LH 지역명 → (시도코드 또는 None, 전국인가).

    옮기지 못하면 (None, False) 다. **거짓으로 채우지 않는다** — 엉뚱한 지역에 붙은
    공고는 없느니만 못하다. 못 옮긴 이름은 부르는 쪽이 세어서 사람에게 보여 준다.
    """
    nm = (cnp_nm or "").strip()
    if not nm:
        return None, False
    if nm == NATIONWIDE_NM:
        return None, True
    if nm in SIDO_BY_NAME:
        return SIDO_BY_NAME[nm], False
    if nm in LEGACY_SIDO_BY_NAME:
        return LEGACY_SIDO_BY_NAME[nm], False
    return None, False


def short_kind(kind_cd, kind_nm_src):
    """화면용 짧은 종류 이름. 모르는 코드면 **원문을 그대로 쓴다**.

    빈칸으로 두거나 '기타'로 뭉개면, LH 가 종류를 늘린 날 그 공고들이 한 덩어리로
    보이면서 무엇이 새로 생겼는지 화면에서 가릴 수 없게 된다.
    """
    cd = (kind_cd or "").strip()
    if cd in KIND_SHORT_NM:
        return KIND_SHORT_NM[cd]
    src = (kind_nm_src or "").strip()
    if src:
        return src
    return "종류 미상"


def record_to_row(rec, where, collected_at):
    """API 한 줄 → 적재용 dict. 값 정리·검증을 여기서 끝낸다."""
    pan_id = (rec.get("PAN_ID") or "").strip()
    if not pan_id:
        raise ValueError("{}: PAN_ID 가 비어 있습니다 — 식별자 없이는 넣을 수 없습니다.".format(where))
    pan_nm = (rec.get("PAN_NM") or "").strip()
    if not pan_nm:
        raise ValueError("{}: PAN_NM(공고명)이 비어 있습니다.".format(where))

    kind_cd = (rec.get("AIS_TP_CD") or "").strip()
    kind_nm_src = (rec.get("AIS_TP_CD_NM") or "").strip()
    cnp_nm = (rec.get("CNP_CD_NM") or "").strip()
    sido_code, nationwide = map_sido(cnp_nm)

    return {
        "pan_id": pan_id,
        "pan_nm": pan_nm,
        "kind_cd": kind_cd,
        "kind_nm": short_kind(kind_cd, kind_nm_src),
        "kind_nm_src": kind_nm_src or "(원문 없음)",
        "spl_inf_tp_cd": (rec.get("SPL_INF_TP_CD") or "").strip() or None,
        "cnp_nm": cnp_nm or None,
        "sido_code": sido_code,
        "is_nationwide": nationwide,
        "pan_ss": (rec.get("PAN_SS") or "").strip() or None,
        # 공고일은 두 칸이 있다 — PAN_NT_ST_DT(게시 시작일, 전건 채워짐)를 쓰고
        # PAN_DT(빈 값 34%)로 물러선다. 빈칸이 많은 쪽을 주로 쓰면 정렬이 무너진다.
        "notice_date": parse_api_date(rec.get("PAN_NT_ST_DT")) or parse_api_date(rec.get("PAN_DT")),
        "close_date": parse_api_date(rec.get("CLSG_DT")),
        "dtl_url": (rec.get("DTL_URL") or "").strip() or None,
        "collected_at": collected_at,
    }


def unknown_sido_names(rows):
    """옮기지 못한 지역 이름 → 건수. 조용히 지나가지 않게 부르는 쪽이 보여 준다."""
    out = {}
    for r in rows:
        if r["sido_code"] is None and not r["is_nationwide"]:
            nm = r["cnp_nm"] or "(지역명 없음)"
            out[nm] = out.get(nm, 0) + 1
    return out


def assert_mapping_health(rows, stop_ratio=UNKNOWN_SIDO_STOP_RATIO):
    """지역명을 절반 넘게 못 옮겼으면 멈춘다.

    하나둘이면 "LH 가 새 이름을 썼다"이고 그건 표에 담아 두면 나중에 고칠 수 있다.
    절반을 넘으면 **우리 표가 낡은 것**이라, 그대로 넣으면 알림판이 통째로 비는데
    행 수는 멀쩡해서 아무도 눈치채지 못한다.
    """
    regional = [r for r in rows if not r["is_nationwide"]]
    if not regional:
        return True
    unknown = sum(v for v in unknown_sido_names(rows).values())
    if unknown > len(regional) * stop_ratio:
        raise ValueError(
            "지역명 {:,}건 중 {:,}건을 시도코드로 옮기지 못했습니다({:.0%}). "
            "LH 지역명 표(SIDO_BY_NAME)가 낡았을 수 있습니다 — 못 옮긴 이름: {}".format(
                len(regional), unknown, unknown / len(regional),
                ", ".join(sorted(unknown_sido_names(rows))[:8])))
    return True


def row_to_values_sql(row):
    return "({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})".format(
        sql_str(row["pan_id"]), sql_str(row["pan_nm"]),
        sql_str(row["kind_cd"]), sql_str(row["kind_nm"]), sql_str(row["kind_nm_src"]),
        sql_str(row["spl_inf_tp_cd"]), sql_str(row["cnp_nm"]),
        sql_str(row["sido_code"]), sql_bool(row["is_nationwide"]),
        sql_str(row["pan_ss"]), sql_str(row["notice_date"]), sql_str(row["close_date"]),
        sql_str(row["dtl_url"]), sql_str(row["collected_at"]))


def build_insert(chunk):
    """values 한 뭉치 → upsert 한 문장.

    ⛔ 지우고 다시 넣지 않는다(delete + insert). 마감된 옛 공고를 창고에 남기는 것이
       이 표의 설계다 — delete 를 한 번이라도 쓰면 그 설계가 조용히 뒤집힌다.
       상태·마감일은 바뀌므로 같은 PAN_ID 는 **덮어쓴다**.
    """
    return (
        "insert into lh_notice "
        "(pan_id, pan_nm, kind_cd, kind_nm, kind_nm_src, spl_inf_tp_cd, cnp_nm, "
        "sido_code, is_nationwide, pan_ss, notice_date, close_date, dtl_url, collected_at)\n"
        "select v.pan_id::text, v.pan_nm::text, v.kind_cd::text, v.kind_nm::text, "
        "v.kind_nm_src::text, v.spl::text, v.cnp::text, v.sido::char(2), v.nation::boolean, "
        "v.ss::text, v.nt::date, v.cl::date, v.url::text, v.at::timestamptz\n"
        "from (values\n{values}\n) as v(pan_id, pan_nm, kind_cd, kind_nm, kind_nm_src, spl, "
        "cnp, sido, nation, ss, nt, cl, url, at)\n"
        "on conflict (pan_id) do update set "
        "pan_nm = excluded.pan_nm, "
        "kind_cd = excluded.kind_cd, "
        "kind_nm = excluded.kind_nm, "
        "kind_nm_src = excluded.kind_nm_src, "
        "spl_inf_tp_cd = excluded.spl_inf_tp_cd, "
        "cnp_nm = excluded.cnp_nm, "
        "sido_code = excluded.sido_code, "
        "is_nationwide = excluded.is_nationwide, "
        "pan_ss = excluded.pan_ss, "
        "notice_date = excluded.notice_date, "
        "close_date = excluded.close_date, "
        "dtl_url = excluded.dtl_url, "
        "collected_at = excluded.collected_at;"
    ).format(values=",\n".join(row_to_values_sql(r) for r in chunk))


def build_sql(rows, batch_rows=BATCH_ROWS):
    """전체 적재 SQL. 한 트랜잭션 — 중간에 걸리면 통째로 되돌린다."""
    if not rows:
        raise ValueError("넣을 공고가 없습니다.")

    # 한 문장 안에 같은 식별자가 두 번 있으면 PostgreSQL 이 "ON CONFLICT DO UPDATE command
    # cannot affect row a second time" 로 트랜잭션째 죽는다. 그 메시지만으로는 원인을 알 수
    # 없으니 어느 공고가 겹쳤는지 여기서 이름을 대고 멈춘다.
    seen = {}
    for r in rows:
        seen[r["pan_id"]] = seen.get(r["pan_id"], 0) + 1
    dupes = sorted(k for k, v in seen.items() if v > 1)
    if dupes:
        raise ValueError(
            "같은 공고번호가 여러 번 나옵니다: {}{}. "
            "쪽 넘김이 겹쳤거나 원본에 중복이 있다는 뜻이라 사람이 봐야 합니다.".format(
                ", ".join(dupes[:5]),
                " 외 {}개".format(len(dupes) - 5) if len(dupes) > 5 else ""))

    stamp = rows[0]["collected_at"]

    out = ["begin;", "set local statement_timeout = '120s';"]
    for i in range(0, len(rows), batch_rows):
        out.append(build_insert(rows[i:i + batch_rows]))

    # ⚠️ 관문은 **do 블록**이라야 한다 — psql 은 select 가 몇을 돌려주든 종료코드 0 이라,
    #    "0 이어야 정상"이라고 적어 둬도 그대로 commit 된다(load_sbiz_district 와 같은 교훈).
    # 이번 판에 손댄 행 수가 넣으려던 수와 다르면 반쯤 들어간 것이다. 알림판이 반쪽이면
    # "공고가 원래 이것뿐"인지 "우리가 흘렸는지" 화면에서 절대 못 가린다.
    out.append(
        "do $$\n"
        "declare cnt int;\n"
        "begin\n"
        "  select count(*) into cnt from lh_notice where collected_at = {stamp}::timestamptz;\n"
        "  if cnt <> {want} then\n"
        "    raise exception '이번 판에 들어간 공고가 %건인데 넣으려던 것은 {want}건입니다 "
        "— 반쪽 적재를 막기 위해 통째로 되돌립니다', cnt;\n"
        "  end if;\n"
        "end $$;".format(stamp=sql_str(stamp), want=len(rows)))

    # 창고에 남은 옛 공고는 지우지 않는다(설계). 다만 몇 건이 남아 있는지는 보여 준다 —
    # 지우지 않기로 한 결정이 실제로 지켜지고 있는지 눈으로 확인하는 자리다.
    out.append(
        'select count(*) as "창고 전체", '
        # ⛔ 화면(list_lh_notices)과 **같은 자**로 센다 — 한국 날짜다. `current_date` 를
        #    쓰면 이 DB 가 UTC 라 한국 새벽 0~9시에 화면과 이 요약이 서로 다른 수를
        #    말한다(마이그레이션 2026-09-01a). 여기는 "지우지 않기로 한 결정이 지켜지는지"
        #    눈으로 보는 자리라, 어긋나는 순간 판단 근거가 오염된다.
        "count(*) filter (where close_date >= (now() at time zone 'Asia/Seoul')::date) "
        'as "지금 살아 있는 것", '
        'count(*) filter (where sido_code is null and not is_nationwide) as "지역 미상" '
        "from lh_notice;")
    out.append("commit;")
    return "\n".join(out) + "\n"


def summarize(rows):
    by_kind, by_region, by_ss = {}, {}, {}
    for r in rows:
        by_kind[r["kind_nm"]] = by_kind.get(r["kind_nm"], 0) + 1
        key = "전국" if r["is_nationwide"] else (r["cnp_nm"] or "(지역명 없음)")
        by_region[key] = by_region.get(key, 0) + 1
        by_ss[r["pan_ss"] or "(상태 없음)"] = by_ss.get(r["pan_ss"] or "(상태 없음)", 0) + 1
    dates = sorted(r["notice_date"] for r in rows if r["notice_date"])
    return {
        "total": len(rows),
        "by_kind": by_kind,
        "by_region": by_region,
        "by_status": by_ss,
        "nationwide": sum(1 for r in rows if r["is_nationwide"]),
        "unknown_sido": unknown_sido_names(rows),
        "no_close_date": sum(1 for r in rows if not r["close_date"]),
        "first_notice": dates[0] if dates else None,
        "last_notice": dates[-1] if dates else None,
    }


# ── 네트워크 ──────────────────────────────────────────────────────────────────


def page_url(service_key, page, start_dt, end_dt, page_size=PAGE_SIZE):
    """한 쪽을 달라고 하는 주소.

    ⚠️ `safe=""` 로 인증키까지 전부 인코딩한다 — 포털 키에는 `+`·`/`·`=` 가 들어 있어,
       그대로 두면 서버가 다른 글자로 읽어 403 이 난다.
    """
    q = urllib.parse.urlencode({
        "serviceKey": service_key,
        "PG_SZ": page_size,
        "PAGE": page,
        "PAN_ST_DT": start_dt,
        "PAN_ED_DT": end_dt,
    }, safe="")
    return BASE_URL + "?" + q


def mask_key(text, service_key):
    """오류 문자열에 인증키가 섞여 나가지 않게 지운다."""
    s = str(text)
    if service_key:
        s = s.replace(service_key, "***").replace(urllib.parse.quote(service_key, safe=""), "***")
    return s


def _get_json(url, timeout=TIMEOUT_SEC):
    req = urllib.request.Request(url, headers={"User-Agent": "sangga-lh-notices"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="replace"))


def get_json_with_retry(url, service_key="", attempts=RETRY_COUNT, sleep=time.sleep,
                        timeout=TIMEOUT_SEC):
    """짧은 타임아웃으로 여러 번 두드린다 — 단 다시 물어야 답이 달라질 수 있는 실패만."""
    for attempt in range(1, attempts + 1):
        try:
            return _get_json(url, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code in NO_RETRY_HTTP_CODES or attempt == attempts:
                raise
            wait = RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
            print("  응답 없음 ({}/{}) — {}초 뒤 다시: {}".format(
                attempt, attempts, wait, mask_key(e, service_key)), file=sys.stderr, flush=True)
            sleep(wait)
        except Exception as e:
            if attempt == attempts:
                raise
            wait = RETRY_BACKOFF_SEC * (2 ** (attempt - 1))
            print("  응답 없음 ({}/{}) — {}초 뒤 다시: {}".format(
                attempt, attempts, wait, mask_key(e, service_key)), file=sys.stderr, flush=True)
            sleep(wait)
    raise RuntimeError("재시도 루프가 한 번도 돌지 않았습니다 (attempts 확인).")


def fetch_sanga(service_key, start_dt, end_dt, collected_at, max_pages=MAX_PAGES,
                fetcher=None, page_size=PAGE_SIZE, verbose=True):
    """창 전체를 쪽 단위로 훑어 **상가 공고만** 모은다. (rows, 조회한 쪽 수, 전체 건수)

    끝을 아는 법: 한 쪽이 PG_SZ 보다 적게 오면 마지막 쪽이다(빈 쪽도 마찬가지).
    실측으로 1년 = 30쪽이라 30번 부르면 끝난다.
    """
    fetcher = fetcher or (lambda url: get_json_with_retry(url, service_key))
    rows, pages, all_cnt = [], 0, None
    for page in range(1, max_pages + 1):
        payload = fetcher(page_url(service_key, page, start_dt, end_dt, page_size))
        pages += 1
        recs = extract_rows(payload)
        if all_cnt is None and recs:
            raw = (recs[0].get("ALL_CNT") or "").strip()
            all_cnt = int(raw) if raw.isdigit() else None
        for i, rec in enumerate(recs, start=1):
            if not is_sanga(rec):
                continue
            rows.append(record_to_row(
                rec, "{}쪽 {}번째(공고 {})".format(page, i, (rec.get("PAN_ID") or "?").strip()),
                collected_at))
        if verbose:
            print("  {}쪽: {}건 (상가 누적 {:,}건)".format(page, len(recs), len(rows)), flush=True)
        if len(recs) < page_size:
            break
    else:
        raise ValueError(
            "{}쪽을 넘겼습니다 — 끝을 못 알아본 채 도는 중일 수 있습니다. "
            "PG_SZ·응답 형식을 확인하세요.".format(max_pages))
    return rows, pages, all_cnt


def get_api_key():
    from dotenv import load_dotenv  # noqa: PLC0415  (테스트는 키 없이도 돌아야 한다)

    load_dotenv(os.path.join(os.path.dirname(SCRIPTS_DIR), ".env"))
    key = os.environ.get("MOLIT_KEY", "").strip()
    if not key:
        raise SystemExit(
            ".env 에 MOLIT_KEY(공공데이터포털 인증키)가 없습니다.\n"
            "  LH 공고문 API 는 이 키 하나로 부릅니다.")
    return key


def main(argv=None):
    # cp949 콘솔에서 한글·특수문자(—) 출력이 UnicodeEncodeError 로 죽지 않게.
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    p = argparse.ArgumentParser(description="LH 상가 공고 → lh_notice 적재")
    p.add_argument("--months", type=int, default=DEFAULT_MONTHS,
                   help="최근 몇 개월 창을 훑을지 (기본 {})".format(DEFAULT_MONTHS))
    p.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않는다")
    p.add_argument("--sql-out", help="만들어진 SQL 을 이 파일로 저장(검토용)")
    a = p.parse_args(argv)

    if a.months < 1:
        print("--months 는 1 이상이어야 합니다.", file=sys.stderr)
        return 1

    key = get_api_key()
    start_dt, end_dt = window(months=a.months)
    collected_at = datetime.datetime.now(KST).isoformat(timespec="seconds")

    print("=" * 70)
    print("LH 상가 공고 수집 ({} ~ {})".format(start_dt, end_dt))
    print("=" * 70)

    try:
        rows, pages, all_cnt = fetch_sanga(key, start_dt, end_dt, collected_at)
    except Exception as e:
        print("수집 실패: {}".format(mask_key(e, key)), file=sys.stderr)
        return 1

    print("  부른 횟수: {}회 / 포털이 말한 전체 공고: {}".format(
        pages, "{:,}건".format(all_cnt) if all_cnt is not None else "(안 알려줌)"))

    # ⛔ 조용한 빈손 금지. 1년 창에 상가 공고가 0건인 일은 없다(실측 531건) —
    #    0 이면 인증키가 거절됐거나 유형코드가 바뀐 것이다. 성공으로 끝내면 그날부터
    #    알림판이 옛 자료만 말하는데 아무도 모른다.
    if not rows:
        print(
            "상가 공고가 한 건도 없습니다 — 정상이 아닙니다.\n"
            "  · 인증키가 거절됐거나(403) 상위 유형코드({})가 바뀌었을 수 있습니다.\n"
            "  · 전체 공고는 {}건 왔습니다.".format(
                SANGA_UPP_CD, "{:,}".format(all_cnt) if all_cnt is not None else "?"),
            file=sys.stderr)
        return 1

    try:
        assert_mapping_health(rows)
    except ValueError as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1

    s = summarize(rows)
    print("  상가 공고: {:,}건 (전국 {:,}건 포함)".format(s["total"], s["nationwide"]))
    print("  공고일 범위: {} ~ {}".format(s["first_notice"] or "?", s["last_notice"] or "?"))
    print("  마감일 없는 것: {:,}건".format(s["no_close_date"]))
    print("  종류별")
    for k, v in sorted(s["by_kind"].items(), key=lambda kv: -kv[1]):
        print("    {:<14} {:>5,}".format(k, v))
    print("  지역별")
    for k, v in sorted(s["by_region"].items(), key=lambda kv: -kv[1]):
        print("    {:<20} {:>5,}".format(k, v))
    print("  상태별")
    for k, v in sorted(s["by_status"].items(), key=lambda kv: -kv[1]):
        print("    {:<14} {:>5,}".format(k, v))

    if s["unknown_sido"]:
        print()
        print("  ⚠️ 시도코드로 옮기지 못한 지역 이름 — 이 공고들은 지역을 골라도 안 보입니다")
        for k, v in sorted(s["unknown_sido"].items(), key=lambda kv: -kv[1]):
            print("    {:<20} {:>5,}건".format(k, v))
        print("    → scripts/collectors/collect_lh_notices.py 의 SIDO_BY_NAME 에 넣으세요.")
    else:
        print("  지역명 옮기기: 전건 성공")

    try:
        sql = build_sql(rows)
    except ValueError as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1
    print("  만들어진 SQL: {:,} 글자".format(len(sql)))

    if a.sql_out:
        with open(a.sql_out, "w", encoding="utf-8", newline="\n") as f:
            f.write(sql)
        print("  SQL 저장: {}".format(a.sql_out))

    if a.dry_run:
        print()
        print("--dry-run 지정 — DB 에 아무것도 쓰지 않았습니다.")
        return 0

    import dbx  # noqa: PLC0415  (dry-run 은 DB 설정 없이도 돌아야 한다)

    rc = dbx.run_sql(sql)
    if rc != 0:
        print("적재 실패 (psql 종료코드 {}). 트랜잭션이라 아무것도 안 들어갔습니다.".format(rc),
              file=sys.stderr)
        return rc
    print()
    print("  적재 완료.")
    print("  다음: scripts/check_lh_notices.py 의 LATEST_KNOWN_NOTICE_DATE 를 {} 로 올리세요.".format(
        (s["last_notice"] or "").replace("-", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
