# -*- coding: utf-8 -*-
"""서울시 상권분석서비스(영역-상권) SHP 내려받기.

왜 이 데이터인가
----------------
결정 0007 이 **"보여주기의 기준 = 상권"** 이라고 못박았는데 `district` 표가 0행이었다.
후보 4개를 비교해 이것을 골랐다(2026-08-14 결정):

  · 라이선스 = 공공누리 1유형(출처표시) — **상업적 이용·변경 가능** (공식 페이지 실측)
  · 1,650개 상권 / 서울 25개 구 전부 (우리가 연 30개 구 중 25개)
  · 종류 4종: 골목상권 1,090 · 전통시장 305 · 발달상권 249 · 관광특구 6
  · 경계 폴리곤 + 중심좌표 + 면적 + 시군구코드가 한 파일에 들어 있다

⚠️ **대전 5개 구는 이 자료에 없다.** 서울만 덮는다 — 대전 상권은 별도 결정 사항이다.

왜 API 가 아니라 파일인가
-------------------------
서울 열린데이터광장에 이 데이터셋의 **OpenAPI 가 없다**(공식 페이지 실측 2026-08-14).
2.07MB ZIP 다운로드가 유일한 경로다. 갱신 주기도 "비정기"라 날짜를 맞힐 수 없다
(마지막 갱신 2026-06-11). 그래서 받을 때마다 기준월 폴더에 쌓아 둔다.

왜 다운로드 인자를 페이지에서 읽어내나
--------------------------------------
포털이 파일을 갈아끼우면 `seq` 가 바뀐다. 값을 코드에 박아 두면 어느 날 조용히 **엉뚱한
파일**을 받거나 빈 응답을 받는다. 그래서 매번 상세 페이지에서 폼 인자를 읽어 쓰고,
못 찾으면 **조용히 넘어가지 않고 멈춘다**(구조가 바뀐 것이므로 사람이 봐야 한다).

쓰는 법
-------
    python scripts/collectors/fetch_seoul_district.py --probe   # 크기·형식만 확인, 저장 0
    python scripts/collectors/fetch_seoul_district.py           # data/raw/seoul_district/<YYYYMM>/

표준 라이브러리 + requests 만 쓴다.
"""

import argparse
import datetime
import io
import os
import re
import sys
import zipfile

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "seoul_district")

DATASET_PAGE = "https://data.seoul.go.kr/dataList/OA-15560/S/1/datasetView.do"
DOWNLOAD_URL = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TIMEOUT_SEC = 120

# 상세 페이지의 숨은 폼(frmFile)과 목록의 downloadFile('N') 호출에서 인자를 뽑는다.
RE_HIDDEN = re.compile(r'name="(infId|infSeq)"\s+value="([^"]*)"')
RE_SEQ = re.compile(r"downloadFile\('(\d+)'\)")

ZIP_MAGIC = b"PK\x03\x04"
MIN_VALID_BYTES = 500 * 1024  # 2026-08-14 실측 2.02MiB. 이보다 한참 작으면 오류 페이지다.

# zip 안에 반드시 있어야 하는 확장자. 하나라도 없으면 shapefile 로 못 읽는다.
REQUIRED_SUFFIXES = (".shp", ".dbf", ".prj")


def parse_download_params(html_text):
    """상세 페이지 HTML 에서 다운로드 폼 인자를 뽑는다.

    돌려주는 값: {"infId": "OA-15560", "infSeq": "3", "seq": "5"}
    구조가 바뀌어 못 찾으면 ValueError — 조용히 기본값으로 넘어가지 않는다.
    """
    found = dict(RE_HIDDEN.findall(html_text or ""))
    seqs = RE_SEQ.findall(html_text or "")
    missing = [k for k in ("infId", "infSeq") if not found.get(k)]
    if missing or not seqs:
        raise ValueError(
            "상세 페이지에서 다운로드 인자를 못 찾았습니다 (없는 것: {}). "
            "포털 화면 구조가 바뀌었을 수 있으니 사람이 확인해야 합니다.".format(
                ", ".join(missing + ([] if seqs else ["seq"]))))
    # 파일이 여러 개면 가장 큰 seq = 가장 최근 등록분
    return {"infId": found["infId"], "infSeq": found["infSeq"], "seq": max(seqs, key=int)}


def readable_member(name):
    """zip 안 한글 파일명을 사람이 읽을 수 있게 되돌린다.

    이 zip 은 파일명을 cp949 로 저장했는데 UTF-8 플래그가 없다. 그러면 zipfile 이
    규격대로 cp437 로 풀어 `╝¡┐∩╜├…` 같은 글자가 나온다 — 파일이 깨진 게 아니라
    **글자표를 잘못 고른 것**이다. 되돌리지 않으면 목록을 보고 다운로드가 실패한 줄
    오해한다(적재는 확장자로 찾으므로 기능에는 영향이 없다).
    """
    try:
        return name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def describe_zip(content):
    """받은 바이트가 쓸 만한 shapefile zip 인지 확인하고 내용을 요약한다.

    깨진 응답(로그인 페이지·오류 HTML)을 "받았다"고 착각하지 않게 하는 관문이다.
    """
    if len(content) < MIN_VALID_BYTES:
        raise ValueError("응답이 너무 작습니다({:,} B) — 오류 페이지일 가능성이 큽니다.".format(len(content)))
    if not content.startswith(ZIP_MAGIC):
        raise ValueError("zip 이 아닙니다(앞 4바이트 {!r}) — 오류 페이지일 가능성이 큽니다.".format(content[:4]))
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        # ⚠️ 보여주는 이름과 z.read() 에 넘길 이름은 다르다 — 읽기는 **원래 이름**으로.
        raw_names = [i.filename for i in z.infolist()]
        members = [(readable_member(i.filename), i.file_size) for i in z.infolist()]
        suffixes = {os.path.splitext(n)[1].lower() for n in raw_names}
        missing = [s for s in REQUIRED_SUFFIXES if s not in suffixes]
        if missing:
            raise ValueError("zip 에 {} 가 없습니다 — shapefile 이 아닙니다.".format(", ".join(missing)))
        prj = next((z.read(n).decode("utf-8", "replace")
                    for n in raw_names if n.lower().endswith(".prj")), "")
    return {"bytes": len(content), "members": members, "prj": prj}


def summarize_prj(prj_text):
    """.prj 한 줄 요약. 좌표계를 사람이 눈으로 확인할 수 있게 한다.

    ⚠️ 5181(Central Belt) 과 5186(Central Belt 2010) 은 False Northing 이 500000 / 600000
    으로 딱 10만 m 차이다. 헷갈리면 지도가 100km 밀린다 — 그래서 이 값을 찍어 준다.
    """
    name = re.search(r'PROJCS\["([^"]+)"', prj_text or "")
    north = re.search(r'False_Northing",\s*([0-9.]+)', prj_text or "")
    return "{} / False_Northing={}".format(
        name.group(1) if name else "(이름 못 읽음)",
        north.group(1) if north else "(못 읽음)")


def fetch(session=None):
    """상세 페이지 → 인자 추출 → zip 다운로드. (내용 바이트, 인자) 를 돌려준다."""
    s = session or requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    page = s.get(DATASET_PAGE, timeout=TIMEOUT_SEC)
    page.raise_for_status()
    params = parse_download_params(page.text)
    resp = s.post(DOWNLOAD_URL, data=dict(params, seqNo=""),
                  headers={"Referer": DATASET_PAGE}, timeout=TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.content, params


def main(argv=None):
    p = argparse.ArgumentParser(description="서울시 상권분석서비스(영역-상권) SHP 내려받기")
    p.add_argument("--probe", action="store_true",
                   help="크기·형식·좌표계만 확인하고 저장하지 않는다")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                   help="저장 위치 (기본: data/raw/seoul_district)")
    p.add_argument("--ym", default=datetime.date.today().strftime("%Y%m"),
                   help="기준월 폴더 이름 YYYYMM (기본: 오늘)")
    a = p.parse_args(argv)

    print("=" * 70)
    print("서울시 상권분석서비스(영역-상권) 내려받기")
    print("=" * 70)

    try:
        content, params = fetch()
        info = describe_zip(content)
    except Exception as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1

    print("  다운로드 인자 : infId={infId} infSeq={infSeq} seq={seq}".format(**params))
    print("  받은 크기     : {:,} B".format(info["bytes"]))
    print("  좌표계(.prj)  : {}".format(summarize_prj(info["prj"])))
    print("  zip 내용:")
    for name, size in info["members"]:
        print("    {:>11,} B  {}".format(size, name))

    if a.probe:
        print()
        print("--probe 지정 — 저장하지 않았습니다.")
        return 0

    out_dir = os.path.join(a.out_dir, a.ym)
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, "seoul_district_area.zip")

    # ⛔ raw 는 절대 덮어쓰지 않는다 (CLAUDE.md 절대 규칙 6 — 원본은 복구 불가).
    #    갱신이 "비정기"라 같은 달에 두 판이 올라올 수 있다. 그냥 열어 쓰면 먼저 받은
    #    판이 말없이 사라진다 — 그게 이 프로젝트에서 가장 되돌릴 수 없는 사고다.
    #    (2026-08-14 적대검증에서 잡혔다. 처음 판에는 이 관문이 없었다.)
    if os.path.exists(dest):
        with open(dest, "rb") as f:
            existing = f.read()
        if existing == content:
            print()
            print("  이미 같은 내용의 원본이 있습니다 — 그대로 둡니다: {}".format(dest))
            return 0
        print(
            "같은 자리에 **내용이 다른** 원본이 이미 있습니다: {}\n"
            "  raw 는 덮어쓰지 않습니다(절대 규칙 6 — 복구 불가).\n"
            "  기존 {:,} B / 새로 받은 {:,} B\n"
            "  --ym 으로 다른 폴더를 지정하거나, 기존 파일을 손으로 옮긴 뒤 다시 받으세요.".format(
                dest, len(existing), len(content)),
            file=sys.stderr)
        return 1

    with open(dest, "wb") as f:
        f.write(content)
    print()
    print("  저장: {}".format(dest))
    print()
    print("  다음: python scripts/collectors/load_seoul_district.py --dry-run")
    print("  💾 원본이 늘었으니 python scripts/backup_raw.py 도 잊지 마세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
