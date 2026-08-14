# -*- coding: utf-8 -*-
"""district(상권 경계) ↔ rent_stat(부동산원 임대동향) 상권 이름 **후보** 생성기.

무엇을 하나
-----------
두 자료는 같은 상권을 다르게 부른다. 이 스크립트는 이름만 보고 "이어질 만한 짝"을
뽑아 사람 앞에 늘어놓는다. **확정하지 않는다** — 확정본은 사람이 고른
`scripts/seeds/district_rone_map.csv` 이고, 그것을 넣는 것은 load_rone_map.py 다.

왜 이름 경로(region_nm)에 거나
------------------------------
rent_stat 의 키는 (quarter, region_code, bld_type) 인데 **같은 상권 이름이 통계
종류마다 다른 region_code** 를 갖는다(대전은 이름 12개 vs 코드 28개). 코드 하나를
고르면 그 종류의 통계만 읽히고 나머지가 조용히 사라지므로, 종류를 가로지르는 공통
축인 `region_nm` 전체 경로("서울>강남>테헤란로")에 건다.

어떤 이름만 대상인가 (잎 상권만)
--------------------------------
R-ONE 이름은 계층이다. 서울은 3단계("서울>권역>상권") 76개, 대전은 2단계
("대전>상권") 12개 = **잎 88개**만 매핑 대상이다. 서울 2단계 5개(도심·강남·기타·
여의도마포·영등포신촌)는 **권역**이라 상위 근사용으로 남긴다 — 잎이 없는 건물이
기댈 자리가 그것이다.

⚠️ 서울 중간 단계는 "구"가 아니라 "권역"이다 (설계 시 실제로 틀렸던 지점)
------------------------------------------------------------------------
처음엔 "서울>강남>…"의 `강남` 을 강남구로 읽고 구 단위 관문을 만들려 했다. **틀렸다** —
같은 `강남` 권역 아래 `교대역`·`서래마을`·`방배역/내방역`·`양재역`이 있는데 전부
**서초구**다. 구로 걸었으면 이것들이 통째로 걸러졌다. 그래서 관문은 권역 → 허용 구
집합으로 건다(아래 SEOUL_REGION_GU). 실제로 이 관문이 잡는 것: `도심>동대문` 이
**동대문구**의 동대문구청·동대문경찰서·동대문중앙새마을금고를 끌어오는 것 —
도심 상권은 종로·중구지 동대문구가 아니다.

쓰는 법
-------
    # 재료를 파일로 주기 (DB 접속 0 — 검토·재현용)
    python scripts/build_rone_map.py --district-csv a.csv --rone-csv b.csv
    # 라이브에서 직접 읽기 (기본)
    python scripts/build_rone_map.py
    # 후보를 CSV 로 떨궈 사람이 큐레이션
    python scripts/build_rone_map.py --district-csv a.csv --rone-csv b.csv \
           --candidates-out cand.csv
"""

import argparse
import csv
import io
import os
import random
import re
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# ── 상수 ──────────────────────────────────────────────────────────────────────

# 서울 25개 자치구 이름 → 시군구코드 5자리.
# 출처: 행정표준코드관리시스템 법정동코드 앞 5자리(자치구 코드). 자치구는 1988년 이후
# 신설·폐지가 없어 이 표는 안정적이다. district CSV 실측(2026-08-14)의 서울 코드 25종과
# 정확히 일치한다 — 어긋나면 assert_gu_table_matches_data 가 잡는다.
SEOUL_GU_CODE = {
    "종로구": "11110", "중구": "11140", "용산구": "11170", "성동구": "11200",
    "광진구": "11215", "동대문구": "11230", "중랑구": "11260", "성북구": "11290",
    "강북구": "11305", "도봉구": "11320", "노원구": "11350", "은평구": "11380",
    "서대문구": "11410", "마포구": "11440", "양천구": "11470", "강서구": "11500",
    "구로구": "11530", "금천구": "11545", "영등포구": "11560", "동작구": "11590",
    "관악구": "11620", "서초구": "11650", "강남구": "11680", "송파구": "11710",
    "강동구": "11740",
}

# 서울 권역 → 그 권역의 잎 상권이 있을 수 있는 자치구.
# 각 권역에 실제로 달린 잎 이름에서 읽어낸 것이며(2026-08-14 재료 실측), 근거는 주석에
# 남긴다. `기타` 는 나머지 서울 전역을 담는 자루라 관문을 걸지 않는다(None).
SEOUL_REGION_GU = {
    # 강남대로·논현역·도산대로·신사역·압구정·청담·테헤란로·학동/강남구청역·한티역(강남구)
    # + 교대역·남부터미널·방배역/내방역·서래마을·양재말죽거리·양재역(서초구)
    "강남": ("강남구", "서초구"),
    # 광화문·북촌·서촌·종로(종로구) + 남대문·동대문·명동·방산시장·시청·을지로·충무로(중구)
    "도심": ("종로구", "중구"),
    # 공덕역(마포구) + 당산역·여의도(영등포구)
    "여의도마포": ("마포구", "영등포구"),
    # 동교/연남·망원역·홍대/합정·공덕역(마포구) + 당산역·여의도·영등포역(영등포구)
    # + 신촌/이대(서대문구)
    "영등포신촌": ("마포구", "영등포구", "서대문구"),
    # 서울 전역에 흩어진 나머지 — 관문 없음
    "기타": None,
}

SIDO_CODE = {"서울": "11", "대전": "30"}

# 이름 끝에 붙는 **시설어**. 상권 이름이 아니라 "그 자리를 가리키는 표지"라 떼어낸다.
# 예) 대전둔산초등학교 → 둔산 / 노은역3번 출구 → 노은 / 목원대네거리 정류장 → 목원대
# ⚠️ `시장` 은 떼지 않는다 — 한민시장·중리전통시장처럼 이름의 일부다.
TAIL_WORDS = (
    "관광특구", "번 출구", "출구", "정류장", "네거리", "사거리", "교차로", "육교",
    "여자고등학교", "초등학교", "중학교", "고등학교", "여고", "대학교",
    "우편취급국", "우체국", "행정복지센터", "주민센터", "보건소", "보건지소",
    "아파트", "공원", "체육센터", "체육관", "역",
)

# 정규화 뒤 이 길이 미만이면 짝짓기에 쓰지 않는다. 한 글자는 아무 데나 걸린다.
MIN_NAME_LEN = 2

# ②-b(구가 홀로 다른 후보) 경고를 사람이 **보고 넘겼다**는 표시. seed 의 note 에 이 말이
# 있어야 그 행이 확정본에 남아 있어도 된다. 근거 없이 남아 있으면 --seed 점검이 멈춘다.
GU_REVIEW_MARK = "구 경계 확인"

# 앞말 겹침(token)으로 이었을 때 **사람 확인 없이 확정**해도 되는 최저 점수.
# 점수 = 짧은 쪽 길이 / 긴 쪽 길이. 0.30 미만은 "명동남대문북창동다동무교동 ⊃ 명동"
# (0.15)처럼 한 조각만 겹치는 경우라 사람이 봐야 한다.
TOKEN_CONFIRM_MIN = 0.30

TIER_RANK = {"exact": 3, "normalized": 2, "token": 1}


# ── 순수 함수: 이름 정규화 ────────────────────────────────────────────────────


def strip_tail_words(name):
    """끝에 붙은 시설어를 **반복해서** 뗀다 ("목원대네거리 정류장" → "목원대").

    한 번만 떼면 "정류장"만 떨어지고 "네거리"가 남는다. 떼고 나서 남는 것이
    MIN_NAME_LEN 보다 짧아지면 떼지 않는다 — "대전역"에서 "역"을 떼면 "대전"만 남아
    엉뚱한 것과 붙는다.
    """
    s = name
    changed = True
    while changed:
        changed = False
        # ★ 출구 번호는 시설어를 뗀 **뒤에** 드러난다 ("노은역3번출구" → "노은역3번").
        #   여기서 다시 떼지 않으면 "노은역3번" 에서 멈춰 "노은" 과 이어지지 않는다.
        peeled = re.sub(r"\d+번$", "", s)
        if peeled != s and len(peeled) >= MIN_NAME_LEN:
            s, changed = peeled, True
        for word in TAIL_WORDS:
            if s.endswith(word) and len(s) - len(word) >= MIN_NAME_LEN:
                s = s[: -len(word)]
                s = re.sub(r"\d+$", "", s)          # "동대문역 3" 처럼 숫자만 남는 꼬리
                changed = True
    return s


def normalize(name, sido=None):
    """짝짓기용 표준형. 괄호·구두점·공백을 걷어내고 시설어를 뗀다.

    `sido` 를 주면 이름 맨 앞의 시도 이름도 뗀다 — 대전 자료는 `대전둔산초등학교`
    처럼 시도를 이름에 달고 오는데, R-ONE 쪽은 `둔산` 이라 그대로면 안 이어진다.
    단 떼고 나서 MIN_NAME_LEN 보다 짧아지면 그대로 둔다("대전역" → "역" 방지).
    """
    s = (name or "").strip()
    s = re.sub(r"\([^)]*\)", "", s)                 # 별칭 괄호는 따로 뽑아 쓴다
    s = s.replace("·", "").replace(".", "").replace(",", "").replace(" ", "")
    s = re.sub(r"\d+번$", "", s)                    # "혜화역1번" → "혜화역"
    s = strip_tail_words(s)
    if sido and s.startswith(sido) and len(s) - len(sido) >= MIN_NAME_LEN:
        s = strip_tail_words(s[len(sido):])
    return s


def alias_names(district_nm):
    """상권 이름 하나 → 짝짓기에 쓸 이름 여러 개.

    소스가 한 칸에 별칭을 같이 적어 둔다:
      · 괄호  "방산종합시장(방산시장)"            → 방산시장 (R-ONE 의 그 이름이다)
      · 쉼표  "수유전통시장(수유시장, 수유골목시장)"
      · 점    "가수원육교.가수원시장 정류장"       → 가수원시장
    괄호 안을 버리면 R-ONE 이름과 **정확히 같은 별칭**을 통째로 잃는다(방산시장이
    실제로 그랬다). 그래서 버리지 않고 후보로 올린다.
    """
    raw = (district_nm or "").strip()
    if not raw:
        return []
    out = [raw]
    base = re.sub(r"\([^)]*\)", "", raw).strip()
    if base and base != raw:
        out.append(base)
    for inner in re.findall(r"\(([^)]*)\)", raw):
        for piece in re.split(r"[,·]", inner):
            piece = piece.strip()
            if piece:
                out.append(piece)
    for piece in re.split(r"[.]", base):
        piece = piece.strip()
        if piece and piece != base:
            out.append(piece)
    seen, uniq = set(), []
    for n in out:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


def rone_alt_names(leaf):
    """R-ONE 잎 이름 → 후보 이름들. `/` 는 "둘 다"라는 뜻이다.

    "용문/한민시장" 은 용문 상권과 한민시장 상권을 함께 세는 한 줄이므로, 두 이름
    모두로 이어질 수 있어야 한다. 통째 이름도 남긴다(그대로 쓰는 자료가 있을 수 있다).
    """
    leaf = (leaf or "").strip()
    if not leaf:
        return []
    out = [leaf]
    if "/" in leaf:
        out += [p.strip() for p in leaf.split("/") if p.strip()]
    return out


# ── 순수 함수: R-ONE 이름 경로 해석 ───────────────────────────────────────────


def parse_rone_paths(region_names):
    """region_nm 목록 → (잎 목록, 상위 근사용 권역 목록).

    잎 = 서울 3단계 / 대전 2단계. 그 밖(서울 2단계 = 권역, 시도 1단계)은 잎이 아니다.
    """
    leaves, parents = [], []
    for full in region_names:
        full = (full or "").strip()
        if not full:
            continue
        parts = [p.strip() for p in full.split(">")]
        sido = parts[0]
        if sido == "서울" and len(parts) == 3:
            leaves.append({"path": full, "sido": sido, "region": parts[1], "leaf": parts[2]})
        elif sido == "대전" and len(parts) == 2:
            leaves.append({"path": full, "sido": sido, "region": None, "leaf": parts[1]})
        else:
            parents.append(full)
    return leaves, parents


def allowed_sigungu(leaf_info):
    """이 잎 상권의 district 가 있을 수 있는 시군구코드 집합. None 이면 관문 없음."""
    sido = leaf_info.get("sido")
    region = leaf_info.get("region")
    if sido != "서울":
        return None                                 # 대전은 권역 단계가 없다
    gus = SEOUL_REGION_GU.get(region, None)
    if gus is None:
        return None                                 # `기타` = 서울 전역
    return {SEOUL_GU_CODE[g] for g in gus}


def passes_gate(leaf_info, sigungu_code):
    """시·도 관문 + 서울 권역 관문. 통과 못 하면 후보에서 뺀다.

    이 관문이 없으면 `도심>동대문` 이 동대문**구**의 구청·경찰서까지 끌어온다
    (2026-08-14 실측 3건). 이름만으로는 절대 못 가르는 종류의 오답이다.
    """
    code = (sigungu_code or "").strip()
    want_sido = SIDO_CODE.get(leaf_info.get("sido"))
    if want_sido and not code.startswith(want_sido):
        return False
    allowed = allowed_sigungu(leaf_info)
    return True if allowed is None else code in allowed


# ── 순수 함수: 짝 점수 ────────────────────────────────────────────────────────


def score_pair(district_name, rone_name, sido=None):
    """이름 두 개 → (등급, 점수) 또는 None.

    등급은 셋뿐이고 뜻이 다르다:
      · exact      적힌 글자가 그대로 같다 (가장 강한 근거)
      · normalized 시설어·구두점을 떼면 같다 ("노은역3번 출구" = "노은")
      · token      한쪽이 다른 쪽의 **앞말**이다 ("수유" ⊂ "수유북부시장")

    ⚠️ 왜 "포함"이 아니라 "앞말"인가: 포함으로 열면 `면목동우체국` 이 `목동` 에 걸린다
       (2026-08-14 실측). 한국 지명은 앞에서부터 좁아지므로 앞말만 본다.
    """
    if (district_name or "").strip() == (rone_name or "").strip() and (rone_name or "").strip():
        return ("exact", 1.0)
    nd = normalize(district_name, sido)
    na = normalize(rone_name, sido)
    if len(nd) < MIN_NAME_LEN or len(na) < MIN_NAME_LEN:
        return None
    if nd == na:
        return ("normalized", 1.0)
    if nd.startswith(na) or na.startswith(nd):
        short, long_ = sorted((nd, na), key=len)
        return ("token", round(len(short) / float(len(long_)), 4))
    return None


def better(a, b):
    """후보 둘 중 나은 것. 등급이 먼저, 같으면 점수, 그래도 같으면 무승부(None)."""
    if a is None:
        return b
    if b is None:
        return a
    ka = (TIER_RANK[a["match_method"]], a["score"])
    kb = (TIER_RANK[b["match_method"]], b["score"])
    if ka > kb:
        return a
    if kb > ka:
        return b
    return None                                     # 무승부 = 사람이 봐야 한다


# ── 후보 만들기 ───────────────────────────────────────────────────────────────


def build_candidates(districts, leaves):
    """상권마다 가장 나은 R-ONE 짝을 고른다.

    돌려주는 것:
      confirmed  자동 확정 후보 (한 짝이 확실히 앞선다)
      ambiguous  애매 후보 (짝이 둘 이상 비겼거나, 앞말 겹침 점수가 낮다)
      unmatched  후보가 하나도 없는 R-ONE 잎 목록
    """
    confirmed, ambiguous = [], []
    hit_paths = set()

    for d in districts:
        best, tied = None, []
        for leaf in leaves:
            if not passes_gate(leaf, d["sigungu_code"]):
                continue
            leaf_best = None
            for alt in rone_alt_names(leaf["leaf"]):
                for dn in alias_names(d["district_nm"]):
                    got = score_pair(dn, alt, leaf["sido"])
                    if not got:
                        continue
                    cand = {
                        "district_id": d["district_id"],
                        "district_nm": d["district_nm"],
                        "sigungu_code": d["sigungu_code"],
                        "rone_region_nm": leaf["path"],
                        "leaf": leaf["leaf"],
                        "match_method": got[0],
                        "score": got[1],
                        "evidence": "{} ≈ {}".format(dn, alt),
                        "note": "",
                    }
                    leaf_best = better(leaf_best, cand) or leaf_best or cand
            if leaf_best is None:
                continue
            picked = better(best, leaf_best)
            if picked is None:                      # 무승부
                tied.append(leaf_best)
            elif picked is leaf_best:
                if best is not None:
                    tied = []
                best = leaf_best
            # picked is best → leaf_best 는 밀렸다(버린다)

        if best is None:
            continue
        hit_paths.add(best["rone_region_nm"])
        for t in tied:
            hit_paths.add(t["rone_region_nm"])

        if tied and len({r["leaf"] for r in [best] + tied}) == 1:
            # ★ 잎 **이름은 같은데 권역만 다른** 비김 = 고르는 문제가 아니다.
            #   부동산원이 bld_type 마다 서울 권역 분할을 달리해 같은 상권이 오피스는
            #   여의도마포·기타, 상가는 영등포신촌으로 갈린다(라이브 실측 2026-08-14).
            #   하나만 고르면 나머지 종류의 통계가 사라지므로 **둘 다** 확정한다
            #   (district_rone_map 의 PK 가 복합인 이유가 이것이다).
            for r in [best] + tied:
                r = dict(r)
                r["note"] = "이중 권역(오피스/상가 분할 상이)"
                # ★ 정직성: 이 규칙은 점수 관문(TOKEN_CONFIRM_MIN)을 **건너뛴다**.
                #   그러면 method 만 보고 "token 이니 그럭저럭 믿을 만하다"고 오판하게 된다.
                #   승격됐다는 사실을 행 자체에 적어 둔다.
                if r["match_method"] == "token" and r["score"] < TOKEN_CONFIRM_MIN:
                    r["note"] += " — 앞말 겹침 {} 로 원래는 사람 확인 대상이나 이중 권역 규칙으로 승격".format(
                        r["score"])
                confirmed.append(r)
        elif tied:
            best = dict(best)
            best["reason"] = "짝이 {}개로 비김: {}".format(
                len(tied) + 1,
                ", ".join(sorted({best["rone_region_nm"]}
                                 | {t["rone_region_nm"] for t in tied})))
            ambiguous.append(best)
        elif best["match_method"] == "token" and best["score"] < TOKEN_CONFIRM_MIN:
            best = dict(best)
            best["reason"] = "앞말 겹침 점수 {:.2f} < {:.2f}".format(
                best["score"], TOKEN_CONFIRM_MIN)
            ambiguous.append(best)
        else:
            confirmed.append(best)

    unmatched = [leaf["path"] for leaf in leaves if leaf["path"] not in hit_paths]
    return {"confirmed": confirmed, "ambiguous": ambiguous, "unmatched": unmatched}


def flag_minority_gu(confirmed):
    """자동 확정 후보 중 **구가 홀로 다른** 것을 짚어 낸다 (사람이 볼 것).

    왜 필요한가: `기타` 권역은 서울 전역이라 관문이 없다. 그래서 이름만 같고 딴 동네인
    상권이 조용히 섞인다 — 실측으로 잡힌 것:
      · 홍대부중(성북구) → 홍대/합정 (홍익대 사대부중이지 홍대 상권이 아니다)
      · 성신여대운정그린캠퍼스(강북구) → 성신여대 (본교 상권과 1km 넘게 떨어진 별개 캠퍼스)
      · 신월7동 골목시장(약수시장…)(양천구) → 약수역 (중구 약수와 이름만 같다)
    같은 R-ONE 상권에 붙은 다른 상권들은 한 구에 몰려 있는데 **혼자만 다른 구**면
    동명이인일 확률이 높다. 기계가 정하지 않고 사람에게 보여만 준다.
    """
    by_path = {}
    for c in confirmed:
        by_path.setdefault(c["rone_region_nm"], []).append(c)

    flagged = []
    for path, rows in by_path.items():
        counts = {}
        for r in rows:
            counts[r["sigungu_code"]] = counts.get(r["sigungu_code"], 0) + 1
        # ⚠️ 구가 전부 하나씩이면 "다수"가 없다 — 그때 억지로 고르면 아무나 지목하는
        #    헛경보가 된다(장안동: 광진·중랑·동대문 각 1개인데 둘이 잡혔었다).
        if len(counts) < 2 or max(counts.values()) < 2:
            continue
        modal = max(counts, key=lambda k: (counts[k], k))
        for r in rows:
            if counts[r["sigungu_code"]] == 1 and r["sigungu_code"] != modal:
                flagged.append(dict(r, reason="이 상권에서 혼자만 {} (나머지 다수는 {})".format(
                    r["sigungu_code"], modal)))
    return sorted(flagged, key=lambda r: (r["rone_region_nm"], r["district_nm"]))


def unreviewed_minority(flagged, seed_notes):
    """②-b 경고를 받았는데 **근거 없이 확정본에 실린** 행을 골라낸다.

    왜 경고로는 부족했나 (2026-08-14 적대검증에서 실제로 뚫림)
    ---------------------------------------------------------
    군자초등학교(동대문구 장안동 소재)가 `서울>기타>군자`(광진구)에 붙어 확정본에
    들어갔다. ②-b 는 그 행을 **정확히 경고했는데**, 사람이 눈으로 넘기고 확정해 버렸다.
    사람이 매번 안 놓치리라 기대하는 것은 방어가 아니다 — 기계가 막는다.

    통과 조건은 딱 하나: seed 의 note 에 `구 경계 확인` 이 적혀 있을 것. 경계에 걸친
    상권(신사역=강남/서초, 사당역=동작/관악처럼)은 정당한 예외라 근거를 적고 통과시키고,
    아무 말 없이 실린 행은 **막는다**. seed 에 아예 없는 행(=이미 걸러낸 것)은 정상이다.

    seed_notes: {(district_id, rone_region_nm): note}
    """
    out = []
    for f in flagged:
        key = (f["district_id"], f["rone_region_nm"])
        if key not in seed_notes:
            continue                                # 확정본에 없다 = 사람이 이미 뺐다
        if GU_REVIEW_MARK in (seed_notes[key] or ""):
            continue                                # 근거를 적고 통과시킨 예외
        out.append(f)
    return out


# ── 귀무가설 대조 ─────────────────────────────────────────────────────────────
#
# 그럴듯한 일치율이 판별력 0 일 수 있다(이 레포의 박제된 교훈). 그래서 "규칙이 아무
# 이름에나 걸리는가"를 같은 규칙으로 재 본다. 두 가지를 따로 본다 — 각각 다른 거짓말을
# 잡는다.


def shuffle_leaf_chars(leaf, rng):
    """잎 이름의 글자를 섞는다 ("테헤란로" → "란로헤테"). 길이·글자는 그대로."""
    chars = list(leaf)
    rng.shuffle(chars)
    return "".join(chars)


def null_by_scrambled_names(districts, leaves, seed=20260814, trials=20):
    """귀무 ① — 이름 글자를 섞은 가짜 R-ONE 이름으로 같은 규칙을 돌린다.

    무엇을 잡나: 정규화가 너무 헐거워 **아무 글자 조합에나** 걸리는 상태.
    실제 매칭 수가 이것과 비슷하면 우리 규칙은 이름을 보고 있는 게 아니다.
    """
    rng = random.Random(seed)
    totals = []
    for _ in range(trials):
        fake = [dict(x, leaf=shuffle_leaf_chars(x["leaf"], rng)) for x in leaves]
        got = build_candidates(districts, fake)
        totals.append(len(got["confirmed"]) + len(got["ambiguous"]))
    return sum(totals) / float(len(totals))


def null_by_shuffled_regions(districts, leaves, seed=20260814, trials=20):
    """귀무 ② — 서울 잎의 **권역만** 무작위로 바꿔 같은 규칙을 돌린다.

    무엇을 잡나: 권역 관문이 실제로는 아무것도 안 거르는 장식인 상태.
    실제와 차이가 없으면 관문을 만든 값을 못 한 것이다(그러면 이름만 남는다).
    """
    rng = random.Random(seed)
    regions = sorted(SEOUL_REGION_GU)
    totals = []
    for _ in range(trials):
        fake = [dict(x, region=rng.choice(regions)) if x["sido"] == "서울" else dict(x)
                for x in leaves]
        got = build_candidates(districts, fake)
        totals.append(len(got["confirmed"]) + len(got["ambiguous"]))
    return sum(totals) / float(len(totals))


# ── 자료 읽기 ─────────────────────────────────────────────────────────────────


def assert_gu_table_matches_data(districts):
    """서울 구 코드표가 자료와 맞는지 본다. 어긋나면 관문이 조용히 헛돈다."""
    seen = {d["sigungu_code"] for d in districts if d["sigungu_code"].startswith("11")}
    known = set(SEOUL_GU_CODE.values())
    unknown = sorted(seen - known)
    if unknown:
        raise ValueError(
            "자료에 우리 구 코드표에 없는 서울 시군구코드가 있습니다: {}. "
            "행정구역이 바뀌었을 수 있습니다 — 관문이 그 구를 통째로 걸러 버립니다.".format(
                ", ".join(unknown)))
    return True


def read_districts_csv(path):
    with io.open(path, encoding="utf-8", newline="") as f:
        rows = [{"district_id": r["district_id"].strip(),
                 "district_nm": (r["district_nm"] or "").strip(),
                 "district_type": (r.get("district_type") or "").strip(),
                 "sigungu_code": (r["sigungu_code"] or "").strip()}
                for r in csv.DictReader(f)]
    if not rows:
        raise ValueError("상권이 한 건도 없습니다: {}".format(path))
    return rows


def read_seed_notes(path):
    """확정본 CSV → {(district_id, rone_region_nm): note}."""
    with io.open(path, encoding="utf-8", newline="") as f:
        return {((r["district_id"] or "").strip(), (r["rone_region_nm"] or "").strip()):
                (r.get("note") or "").strip() for r in csv.DictReader(f)}


def read_rone_csv(path):
    with io.open(path, encoding="utf-8", newline="") as f:
        names = [(r["region_nm"] or "").strip() for r in csv.DictReader(f)]
    names = [n for n in names if n]
    if not names:
        raise ValueError("R-ONE 상권 이름이 한 건도 없습니다: {}".format(path))
    return names


def query_rows(sql):
    """psql -tA 로 여러 줄을 받아 온다 (post_load.py 와 같은 방식).

    ⚠️ 비밀번호는 환경변수로만 넘긴다 — 명령줄에 실으면 프로세스 목록에 남는다.
    """
    import dbx  # noqa: PLC0415  (CSV 모드는 DB 설정 없이도 돌아야 한다)
    args, password = dbx.parts()
    env = dict(os.environ)
    env["PGPASSWORD"] = password
    env["PGCLIENTENCODING"] = "UTF8"
    cmd = ["psql"] + args + ["-t", "-A", "-F", "\x1f", "-v", "ON_ERROR_STOP=1", "-c", sql]
    out = subprocess.check_output(cmd, env=env, stderr=subprocess.STDOUT)
    return [line.split("\x1f")
            for line in out.decode("utf-8", "replace").splitlines() if line.strip()]


def read_districts_db():
    rows = query_rows(
        "select district_id, coalesce(district_nm,''), coalesce(district_type,''), "
        "coalesce(sigungu_code,'') from district order by district_id")
    return [{"district_id": r[0], "district_nm": r[1],
             "district_type": r[2], "sigungu_code": r[3]} for r in rows]


def read_rone_db():
    rows = query_rows(
        "select distinct region_nm from rent_stat where region_nm is not null "
        "order by region_nm")
    return [r[0] for r in rows]


# ── 사람이 읽는 출력 ──────────────────────────────────────────────────────────


def print_report(result, districts, leaves, nulls):
    conf, amb, unmatched = result["confirmed"], result["ambiguous"], result["unmatched"]
    print("=" * 72)
    print("district ↔ R-ONE 상권 이름 후보")
    print("=" * 72)
    print("  상권 {:,}개 / R-ONE 잎 {}개".format(len(districts), len(leaves)))
    print()
    dual = sum(1 for c in conf if c.get("note"))
    print("① 자동 확정 후보 {:,}행 (상권 {:,}개 — 이중 권역 {:,}행 포함)".format(
        len(conf), len({c["district_id"] for c in conf}), dual))
    by_method = {}
    for c in conf:
        by_method[c["match_method"]] = by_method.get(c["match_method"], 0) + 1
    for k in ("exact", "normalized", "token"):
        if by_method.get(k):
            print("     {:<11} {:>5,}".format(k, by_method[k]))
    print()
    print("② 애매 후보 {:,}개 (사람 확정 대기)".format(len(amb)))
    for a in sorted(amb, key=lambda x: x["district_nm"])[:40]:
        print("     {:<34} → {:<26} {}".format(
            a["district_nm"][:34], a["rone_region_nm"][:26], a.get("reason", "")))
    if len(amb) > 40:
        print("     … 외 {:,}개".format(len(amb) - 40))
    print()
    minority = flag_minority_gu(conf)
    print("②-b 자동 확정됐지만 **구가 홀로 다른** 후보 {}개 (동명이인 의심 — 사람이 볼 것)"
          .format(len(minority)))
    for m in minority:
        print("     {:<30} → {:<24} {}".format(
            m["district_nm"][:30], m["rone_region_nm"][:24], m["reason"]))
    print()
    print("③ 후보가 하나도 없는 R-ONE 상권 {}개".format(len(unmatched)))
    for p in unmatched:
        print("     {}".format(p))
    print()
    print("④ 귀무가설 대조 (그럴듯한 일치율이 판별력 0 일 수 있다)")
    print("     실제 매칭 상권 수                    {:>8,}".format(len(conf) + len(amb)))
    print("     귀무① 이름 글자를 섞었을 때(평균)    {:>8.1f}".format(nulls["scrambled"]))
    print("     귀무② 권역을 무작위로 바꿨을 때(평균) {:>8.1f}".format(nulls["regions"]))
    print("     → ① 과 실제가 비슷하면: 정규화가 헐거워 **아무 글자 조합에나** 걸리는 것이다")
    print("       (규칙이 이름을 보고 있는 게 아니다).")
    print("     → ② 와 실제가 비슷하면: 우리가 적은 권역↔구 대응이 자료와 **무관**한 것이다")
    print("       (관문은 열심히 거르지만 엉뚱한 것을 거른다).")


def write_candidates_csv(path, result):
    """사람이 큐레이션할 수 있게 후보를 한 파일로 떨군다."""
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bucket", "district_id", "district_nm", "sigungu_code",
                    "rone_region_nm", "match_method", "score", "note",
                    "evidence", "reason"])
        for bucket, rows in (("confirmed", result["confirmed"]),
                             ("ambiguous", result["ambiguous"])):
            for r in sorted(rows, key=lambda x: (x["sigungu_code"], x["district_nm"],
                                                 x["rone_region_nm"])):
                w.writerow([bucket, r["district_id"], r["district_nm"], r["sigungu_code"],
                            r["rone_region_nm"], r["match_method"], r["score"],
                            r.get("note", ""), r.get("evidence", ""), r.get("reason", "")])


def main(argv=None):
    # 한국어 콘솔(cp949)에서 em-dash(—) 하나 때문에 통째로 죽지 않게 한다. 그대로 두면
    # dry-run 이 성공하고도 종료코드 1 이 나와 "seed 가 잘못됐다"로 오독된다
    # (2026-08-14 적대검증 실환경 재현). 레포의 형제 스크립트들과 같은 처방이다.
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="district ↔ R-ONE 상권 이름 후보 생성")
    p.add_argument("--district-csv", help="district 목록 CSV (없으면 DB 에서 읽는다)")
    p.add_argument("--rone-csv", help="rent_stat.region_nm 목록 CSV (없으면 DB)")
    p.add_argument("--candidates-out", help="후보를 이 CSV 로 저장(큐레이션용)")
    p.add_argument("--seed", help="확정본 CSV — ②-b 경고가 근거 없이 실려 있으면 **멈춘다**")
    p.add_argument("--null-trials", type=int, default=20, help="귀무가설 반복 횟수")
    a = p.parse_args(argv)

    try:
        districts = (read_districts_csv(a.district_csv) if a.district_csv
                     else read_districts_db())
        region_names = read_rone_csv(a.rone_csv) if a.rone_csv else read_rone_db()
        assert_gu_table_matches_data(districts)
    except (ValueError, OSError) as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1

    leaves, parents = parse_rone_paths(region_names)
    if not leaves:
        print("실패: 잎 상권이 하나도 없습니다 (이름 계층이 바뀌었을 수 있습니다).",
              file=sys.stderr)
        return 1

    result = build_candidates(districts, leaves)
    nulls = {
        "scrambled": null_by_scrambled_names(districts, leaves, trials=a.null_trials),
        "regions": null_by_shuffled_regions(districts, leaves, trials=a.null_trials),
    }
    print_report(result, districts, leaves, nulls)
    print()
    print("  상위 근사용(매핑 대상 아님) {}개: {}".format(
        len(parents), ", ".join(parents)))

    if a.candidates_out:
        write_candidates_csv(a.candidates_out, result)
        print()
        print("  후보 저장: {}".format(a.candidates_out))
    print()
    print("  이 스크립트는 **확정하지 않는다**. 확정본은 사람이 고른")
    print("  scripts/seeds/district_rone_map.csv 이고, 넣는 것은 load_rone_map.py 다.")

    if a.seed:
        try:
            seed_notes = read_seed_notes(a.seed)
        except (OSError, KeyError) as e:
            print("실패: 확정본을 읽지 못했습니다 ({}): {}".format(a.seed, e), file=sys.stderr)
            return 1
        left = unreviewed_minority(flag_minority_gu(result["confirmed"]), seed_notes)
        print()
        if left:
            print("!" * 72)
            print("[중단] ②-b 경고가 근거 없이 확정본에 남아 있습니다 — {}건".format(len(left)))
            for r in left:
                print("   {} {:<26} → {:<24} {}".format(
                    r["district_id"], r["district_nm"][:26],
                    r["rone_region_nm"][:24], r["reason"]))
            print()
            print("  이 경고를 눈으로 넘기고 확정해 실제로 오탐이 들어간 적이 있습니다")
            print("  (군자초등학교 — 동대문구 장안동 소재인데 광진구 군자 상권에 붙었다).")
            print("  고치는 법은 둘 중 하나입니다:")
            print("    · 그 행을 확정본에서 **빼거나**")
            print("    · 경계에 걸친 정당한 예외면 note 에 '{}' 이라고 근거를 적는다".format(
                GU_REVIEW_MARK))
            print("!" * 72)
            return 2
        print("  [정상] ②-b 경고 중 근거 없이 확정본에 남은 행은 없습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
