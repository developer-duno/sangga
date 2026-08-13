# -*- coding: utf-8 -*-
"""건축HUB 대용량 파일(zip) → API 수집기와 **같은 형식**의 raw JSONL로 변환.

왜 '적재기'가 아니라 '변환기'인가
--------------------------------
`load_building_ledger.py`(1,639줄)에는 건물·층·호실 생성, 층 코드 정규화 정본,
bld_id/floor_id/unit_id 규칙, 중복·절단 방어, 조인률 실측이 전부 들어 있고
테스트도 붙어 있다. 일괄 파일을 **API 수집기가 만드는 raw JSONL과 똑같은 모양**
으로 바꿔 놓으면 그 적재기를 **한 줄도 고치지 않고** 그대로 쓸 수 있다.

    fetch_bldrgst_bulk.py   건축HUB → zip (646MB·680MB·3.06GB)
    convert_bldrgst_bulk.py zip → data/raw/bldrgst_bulk_converted/<시군구>/*.jsonl   ← 이 파일
    load_building_ledger.py --raw-dir <위 폴더> → building / building_floor / unit

왜 시군구별로 쪼개나
--------------------
적재기는 raw를 통째로 메모리에 올린다(강남 1개 구 = 전유공용 107만 행에서 검증됨).
서울+대전을 한 번에 올리면 수백만 행이라 메모리가 터진다. 시군구 폴더로 나눠 두면
적재기를 `--raw-dir`로 구 단위로 돌릴 수 있고, 한 번에 드는 메모리가 강남 규모다.

`collect_progress`가 없어도 되는 이유
-------------------------------------
적재기의 `verified_latest_batch_by_pnu`는 **PNU에 fetched_at 후보가 1개뿐이면
검증을 건너뛴다.** 이 변환기는 한 번의 실행에 하나의 fetched_at만 쓰므로 항상
그 경우다(경고도 안 뜬다).

⚠️ 파일 형식 (2026-08-11 실측)
    zip 안에 .txt 1개 · `|` 구분 · **UTF-8** · 헤더 행 **없음**(첫 줄부터 데이터)
    컬럼 순서는 아래 *_COLS 에 박아 둔다 — 건축HUB '설명' 팝업의 colSn 순서다.

사용법
    python scripts/collectors/convert_bldrgst_bulk.py --dry-run          # 세기만(쓰기 0)
    python scripts/collectors/convert_bldrgst_bulk.py                    # 3종 전부 변환
    python scripts/collectors/convert_bldrgst_bulk.py --kind title
    python scripts/collectors/convert_bldrgst_bulk.py --sigungu-code 11,30
"""

import argparse
import io
import json
import os
import sys
import zipfile
from collections import Counter

import requests
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SRC_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "bldrgst_bulk", "202606")
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "bldrgst_bulk_converted")

# 적재기가 읽는 파일 이름 (collect_building_ledger.RAW_FILENAME 과 같아야 한다)
OUT_FILENAME = {
    "title": "title.jsonl",
    "flr_ouln": "flr_ouln.jsonl",
    "expos_area": "expos_area.jsonl",
}

# zip 파일명에 들어 있는 한글 조각으로 어떤 종류인지 가른다.
ZIP_MARKER = {
    "title": "표제부",
    "flr_ouln": "층별개요",
    "expos_area": "전유공용면적",
}
# '표제부'는 '총괄표제부'에도 들어 있다 — 그건 우리가 안 쓰므로 제외한다.
ZIP_EXCLUDE = {"title": ("총괄표제부",)}

# ── 컬럼 순서 → API 필드명 ────────────────────────────────────────────────────
#
# 건축HUB '설명' 팝업(POST /portal/opn/lps/idx-lgcpt-pvsn-srvc-popup.do)의 colSn
# 순서를 그대로 옮긴 것. API 응답 필드(강남 raw 실측)와 **개수가 정확히 일치**하고
# (77/33/39) 각 필드가 한 번씩만 쓰인다 — 테스트가 그 불변식을 지킨다.

TITLE_COLS = (
    "mgmBldrgstPk", "regstrGbCd", "regstrGbCdNm", "regstrKindCd", "regstrKindCdNm",
    "platPlc", "newPlatPlc", "bldNm", "sigunguCd", "bjdongCd", "platGbCd", "bun", "ji",
    "splotNm", "block", "lot", "bylotCnt", "naRoadCd", "naBjdongCd", "naUgrndCd",
    "naMainBun", "naSubBun", "dongNm", "mainAtchGbCd", "mainAtchGbCdNm",
    "platArea", "archArea", "bcRat", "totArea", "vlRatEstmTotArea", "vlRat",
    "strctCd", "strctCdNm", "etcStrct", "mainPurpsCd", "mainPurpsCdNm", "etcPurps",
    "roofCd", "roofCdNm", "etcRoof", "hhldCnt", "fmlyCnt", "heit",
    "grndFlrCnt", "ugrndFlrCnt", "rideUseElvtCnt", "emgenUseElvtCnt",
    "atchBldCnt", "atchBldArea", "totDongTotArea",
    "indrMechUtcnt", "indrMechArea", "oudrMechUtcnt", "oudrMechArea",
    "indrAutoUtcnt", "indrAutoArea", "oudrAutoUtcnt", "oudrAutoArea",
    "pmsDay", "stcnsDay", "useAprDay",
    "pmsnoYear", "pmsnoKikCd", "pmsnoKikCdNm", "pmsnoGbCd", "pmsnoGbCdNm",
    "hoCnt", "engrGrade", "engrRat", "engrEpi",
    "gnBldGrade", "gnBldCert", "itgBldGrade", "itgBldCert",
    "crtnDay", "rserthqkDsgnApplyYn", "rserthqkAblty",
)

FLR_OULN_COLS = (
    "mgmBldrgstPk", "platPlc", "newPlatPlc", "bldNm", "sigunguCd", "bjdongCd",
    "platGbCd", "bun", "ji", "splotNm", "block", "lot",
    "naRoadCd", "naBjdongCd", "naUgrndCd", "naMainBun", "naSubBun", "dongNm",
    "flrGbCd", "flrGbCdNm", "flrNo", "flrNoNm",
    "strctCd", "strctCdNm", "etcStrct", "mainPurpsCd", "mainPurpsCdNm", "etcPurps",
    "area", "mainAtchGbCd", "mainAtchGbCdNm", "areaExctYn", "crtnDay",
)

EXPOS_AREA_COLS = (
    "mgmBldrgstPk", "regstrGbCd", "regstrGbCdNm", "regstrKindCd", "regstrKindCdNm",
    "platPlc", "newPlatPlc", "bldNm", "sigunguCd", "bjdongCd", "platGbCd", "bun", "ji",
    "splotNm", "block", "lot", "naRoadCd", "naBjdongCd", "naUgrndCd",
    "naMainBun", "naSubBun", "dongNm", "hoNm",
    "flrGbCd", "flrGbCdNm", "flrNo",
    "exposPubuseGbCd", "exposPubuseGbCdNm", "mainAtchGbCd", "mainAtchGbCdNm",
    "flrNoNm", "strctCd", "strctCdNm", "etcStrct",
    "mainPurpsCd", "mainPurpsCdNm", "etcPurps", "area", "crtnDay",
)

COLS = {"title": TITLE_COLS, "flr_ouln": FLR_OULN_COLS, "expos_area": EXPOS_AREA_COLS}

# PNU 19자리 = 시군구(5) + 법정동(5) + 대지구분(1) + 번(4) + 지(4)
PNU_PARTS = ("sigunguCd", "bjdongCd", "platGbCd", "bun", "ji")
PNU_WIDTH = {"sigunguCd": 5, "bjdongCd": 5, "platGbCd": 1, "bun": 4, "ji": 4}

# ⛔ 건축HUB `platGbCd` 는 PNU 대지구분과 **코드 체계가 다르다**.
#     PNU '1'(대지) ↔ platGbCd '0'  /  PNU '2'(산) ↔ platGbCd '1'
# collect_building_ledger.PLAT_GB_CD_MAP 의 역방향이다(그쪽은 PNU→요청 파라미터,
# 여기는 파일→PNU). 이걸 빠뜨리면 **PNU가 통째로 어긋나 거의 다 parcel 미보유로
# 떨어진다** — 2026-08-11 dry-run 실측: 서울+대전 표제부 727,585행 중 통과 132행뿐.
# `docs/상세계획.md` §3.1 박스에 이미 박제돼 있던 함정이다.
PLAT_GB_TO_PNU = {"0": "1", "1": "2"}

# platGbCd '2' = **블록/특수지번**. 번·지가 전부 '0000'이고 특수지명에
# '제2토지구획정리구내'·'하천부지'·'재정비촉진구역 내' 같은 값이 들어 있다
# (2026-08-11 표본 실측). 유효 지번이 없어 PNU 19자리를 만들 수 없고, 우리 parcel 은
# 상권정보의 유효 19자리에서 왔으므로 **애초에 매칭 대상이 아니다** — 정상 제외다.
# 전국 37,378행(0.46%) · 서울+대전 588행(0.081%).
# 브이월드 일괄 CSV 도 같은 성격을 "PNU 형식 위반 33,276(특수 블록 지번)"으로 건너뛴다.
PLAT_GB_BLOCK = "2"

REST_PAGE = 1000
TIMEOUT_SEC = 120


class ConvertError(RuntimeError):
    pass


# ── 순수 로직 (네트워크·파일 없음 — 테스트 대상) ───────────────────────────────


def make_item(kind, cells):
    """`|`로 나눈 칸 목록 -> API 응답과 같은 모양의 dict.

    칸 수가 모자라면 None(칸 수 불일치는 호출부가 센다). 빈 문자열은 그대로 둔다
    — API도 빈 값을 `' '`나 `''`로 주고, 적재기의 _to_float/_to_int가 처리한다.
    """
    cols = COLS[kind]
    if len(cells) != len(cols):
        return None
    return {name: cells[i].strip() for i, name in enumerate(cols)}


def make_pnu(item):
    """item에서 PNU 19자리를 조립한다. 형식이 안 맞으면 None.

    각 조각은 왼쪽 0 패딩된 고정폭이어야 한다(번/지는 파일에 '0220'처럼 이미
    4자리로 들어 있지만, 짧게 오는 배포본을 대비해 여기서 한 번 더 맞춘다).

    ⛔ `platGbCd` 는 그대로 쓰면 안 된다 — PNU 대지구분과 코드 체계가 다르다
    (PLAT_GB_TO_PNU 주석 참조). 매핑에 없는 값이면 PNU를 만들 수 없으므로 None.
    """
    out = []
    for key in PNU_PARTS:
        raw = (item.get(key) or "").strip()
        if key == "platGbCd":
            mapped = PLAT_GB_TO_PNU.get(raw)
            if mapped is None:
                return None
            out.append(mapped)
            continue
        width = PNU_WIDTH[key]
        if not raw.isdigit() or len(raw) > width:
            return None
        out.append(raw.zfill(width))
    pnu = "".join(out)
    return pnu if len(pnu) == 19 else None


def sigungu_of(pnu):
    return pnu[:5]


def in_scope(pnu, prefixes):
    """범위 접두사 튜플에 걸리는가. 빈 튜플이면 전부 통과(전국)."""
    return (not prefixes) or pnu.startswith(prefixes)


def parse_scope(raw):
    """'11,30' -> ('11','30') / 'all' -> (). load_sangkwon_snapshot.parse_scope와 같은 규칙."""
    if (raw or "").strip().lower() == "all":
        return ()
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if not parts:
        raise ValueError("--sigungu-code 가 비었습니다.")
    for p in parts:
        if not p.isdigit() or not 2 <= len(p) <= 5:
            raise ValueError("2~5자리 숫자여야 합니다: {!r}".format(p))
    uniq = []
    for p in sorted(set(parts), key=lambda s: (len(s), s)):
        if not any(p.startswith(k) for k in uniq):
            uniq.append(p)
    return tuple(uniq)


def find_zip(src_dir, kind):
    """폴더에서 그 종류의 zip 경로를 찾는다. 없거나 여러 개면 ConvertError."""
    marker = ZIP_MARKER[kind]
    bad = ZIP_EXCLUDE.get(kind, ())
    hits = [f for f in sorted(os.listdir(src_dir))
            if f.lower().endswith(".zip") and marker in f
            and not any(b in f for b in bad)]
    if not hits:
        raise ConvertError("{} 에서 '{}' zip 을 못 찾았다".format(src_dir, marker))
    if len(hits) > 1:
        raise ConvertError("'{}' zip 이 여러 개다: {}".format(marker, hits))
    return os.path.join(src_dir, hits[0])


# ── 변환 ──────────────────────────────────────────────────────────────────────


def load_parcel_pnus(base_url, headers, prefixes):
    """parcel 테이블의 PNU 집합을 keyset 페이지네이션으로 전부 읽는다.

    ⛔ limit/offset 을 쓰면 조회 도중 INSERT 가 일어날 때 행이 밀려 누락된다
    (PR #43에서 같은 결함을 고쳤다). 마지막 PNU 기준 keyset 으로 넘긴다.
    """
    pnus = set()
    last = ""
    while True:
        q = ("parcel?select=pnu&order=pnu.asc&limit={}&pnu=gt.{}"
             .format(REST_PAGE, last))
        r = requests.get("{}/rest/v1/{}".format(base_url, q),
                         headers=headers, timeout=TIMEOUT_SEC)
        if r.status_code != 200:
            raise ConvertError("parcel 조회 실패 HTTP {}".format(r.status_code))
        rows = r.json()
        if not rows:
            break
        for row in rows:
            p = row["pnu"]
            if in_scope(p, prefixes):
                pnus.add(p)
        last = rows[-1]["pnu"]
    return pnus


class ShardWriter:
    """시군구별 JSONL 파일을 열어 두고 한 줄씩 쓴다 (핸들 재사용)."""

    def __init__(self, out_dir, filename, dry_run=False):
        self.out_dir = out_dir
        self.filename = filename
        self.dry_run = dry_run
        self.handles = {}
        self.counts = Counter()

    def write(self, sigungu, obj):
        self.counts[sigungu] += 1
        if self.dry_run:
            return
        fp = self.handles.get(sigungu)
        if fp is None:
            d = os.path.join(self.out_dir, sigungu)
            if not os.path.isdir(d):
                os.makedirs(d)
            # 'w' — 같은 종류를 다시 변환하면 덮어쓴다(append 하면 중복 누적).
            fp = open(os.path.join(d, self.filename), "w", encoding="utf-8")
            self.handles[sigungu] = fp
        fp.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def close(self):
        for fp in self.handles.values():
            fp.close()
        self.handles = {}


def convert_one(kind, zip_path, parcel_pnus, prefixes, out_dir, fetched_at,
                dry_run=False, progress_every=2_000_000):
    """zip 하나를 훑어 시군구별 JSONL 로 쓴다. 통계 dict 반환."""
    stats = Counter()
    writer = ShardWriter(out_dir, OUT_FILENAME[kind], dry_run=dry_run)
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = [i.filename for i in z.infolist()
                     if i.filename.lower().endswith(".txt")]
            if len(names) != 1:
                raise ConvertError("zip 안 .txt 가 1개가 아니다: {}".format(names))
            with z.open(names[0]) as raw:
                for line in io.TextIOWrapper(raw, encoding="utf-8", errors="replace"):
                    stats["rows"] += 1
                    if stats["rows"] % progress_every == 0:
                        print("    …{:,}행 (통과 {:,})".format(
                            stats["rows"], stats["kept"]), flush=True)
                    line = line.rstrip("\r\n")
                    if not line:
                        continue
                    item = make_item(kind, line.split("|"))
                    if item is None:
                        stats["col_mismatch"] += 1
                        continue
                    pnu = make_pnu(item)
                    if pnu is None:
                        # 블록/특수지번은 '정상 제외'다 — 진짜 이상과 섞어 세면
                        # 다음 사람이 결함으로 오해한다(PLAT_GB_BLOCK 주석 참조).
                        if (item.get("platGbCd") or "").strip() == PLAT_GB_BLOCK:
                            stats["block_jibun"] += 1
                        else:
                            stats["bad_pnu"] += 1
                        continue
                    if not in_scope(pnu, prefixes):
                        stats["out_of_scope"] += 1
                        continue
                    if pnu not in parcel_pnus:
                        stats["not_in_parcel"] += 1
                        continue
                    stats["kept"] += 1
                    writer.write(sigungu_of(pnu),
                                 {"pnu": pnu, "fetched_at": fetched_at, "item": item})
    finally:
        writer.close()
    stats["sigungu"] = len(writer.counts)
    return stats, writer.counts


def get_supabase_config():
    load_dotenv()
    url = os.environ.get("SANGGA_SUPABASE_URL")
    key = os.environ.get("SANGGA_SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise ConvertError(
            "SANGGA_SUPABASE_URL / SANGGA_SUPABASE_SERVICE_KEY 가 .env 에 없습니다.")
    return url.rstrip("/"), {"apikey": key, "Authorization": "Bearer " + key}


def main(argv=None):
    p = argparse.ArgumentParser(description="건축HUB 일괄 파일 → raw JSONL 변환")
    p.add_argument("--kind", choices=("all",) + tuple(sorted(COLS)), default="all")
    p.add_argument("--src-dir", default=DEFAULT_SRC_DIR)
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    p.add_argument("--sigungu-code", default="11,30",
                   help="범위 접두사 (기본 11,30 = 서울+대전. 'all' = 전국)")
    p.add_argument("--fetched-at", default=None,
                   help="raw 에 박을 시각. 생략하면 원본 폴더명(기준월)에서 만든다")
    p.add_argument("--dry-run", action="store_true", help="세기만 하고 파일을 안 쓴다")
    a = p.parse_args(argv)

    try:
        prefixes = parse_scope(a.sigungu_code)
    except ValueError as e:
        print("[에러] {}".format(e))
        return 2

    kinds = sorted(COLS) if a.kind == "all" else [a.kind]
    period = os.path.basename(os.path.normpath(a.src_dir))
    # 3파일에 같은 값이어야 한다 — 적재기가 (pnu, fetched_at)을 한 배치로 본다.
    fetched_at = a.fetched_at or "{}-bulk".format(period)

    print("=" * 78)
    print("건축HUB 일괄 파일 → raw JSONL 변환{}".format(" — dry-run" if a.dry_run else ""))
    print("=" * 78)
    print("  원본 폴더  {}".format(a.src_dir))
    print("  출력 폴더  {}".format(a.out_dir))
    print("  범위       {}".format("전국" if not prefixes else "+".join(prefixes)))
    print("  fetched_at {}".format(fetched_at))

    try:
        base_url, headers = get_supabase_config()
        print("\nparcel PNU 목록 조회 중…", flush=True)
        parcel_pnus = load_parcel_pnus(base_url, headers, prefixes)
        print("  대상 필지 {:,}개".format(len(parcel_pnus)))
        if not parcel_pnus:
            print("\n⛔ 범위 안에 parcel 행이 0개다 — [A] 시드를 먼저 돌려야 한다.")
            return 1

        total = Counter()
        for kind in kinds:
            zip_path = find_zip(a.src_dir, kind)
            print("\n[{}] {}".format(kind, os.path.basename(zip_path)), flush=True)
            stats, per_sgg = convert_one(kind, zip_path, parcel_pnus, prefixes,
                                         a.out_dir, fetched_at, dry_run=a.dry_run)
            print("  읽은 행       {:,}".format(stats["rows"]))
            print("  범위 밖       {:,}".format(stats["out_of_scope"]))
            print("  parcel 미보유 {:,}".format(stats["not_in_parcel"]))
            if stats["block_jibun"]:
                print("  블록/특수지번 {:,} (지번이 없어 PNU 불가 — 정상 제외)".format(
                    stats["block_jibun"]))
            if stats["bad_pnu"]:
                print("  ⚠️ PNU 조립 실패 {:,} (블록 외 — 확인 필요)".format(stats["bad_pnu"]))
            if stats["col_mismatch"]:
                print("  ⚠️ 칸 수 불일치 {:,}".format(stats["col_mismatch"]))
            print("  → 통과       {:,}행 / 시군구 {}개".format(
                stats["kept"], stats["sigungu"]))
            top = per_sgg.most_common(3)
            if top:
                print("     상위: " + ", ".join(
                    "{} {:,}".format(k, v) for k, v in top))
            total["kept"] += stats["kept"]

        print("\n" + "=" * 78)
        if a.dry_run:
            print("dry-run 이므로 파일을 쓰지 않았습니다. 통과 합계 {:,}행".format(total["kept"]))
        else:
            print("변환 완료: {:,}행. 다음:".format(total["kept"]))
            print("  python scripts/collectors/load_building_ledger.py \\")
            print("      --raw-dir {}/<시군구코드> --snapshot-ym {}".format(
                a.out_dir, period))
        print("=" * 78)
    except ConvertError as e:
        print("\n⛔ {}".format(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
