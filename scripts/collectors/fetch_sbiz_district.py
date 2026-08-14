# -*- coding: utf-8 -*-
"""소상공인시장진흥공단 "주요상권현황" CSV 내려받기 (공공데이터포털 15090955).

왜 이 자료인가
--------------
결정 0008 로 채운 `district` 1,650개는 **서울시 자료라 서울뿐**이다. 우리가 연 30개 구
중 대전 5개 구는 상권 경계가 통째로 없다("준비 중"으로 표시된다). 이 자료는 전국
1,227개 상권을 담고 있고 그중 **대전(시도코드 30)이 37개**다 — 대전을 채우는 유일한
공공 경로다(2026-08-14 실측).

자료 생김새 (실측)
------------------
  · CSV 1개, 30.5MB, **cp949**
  · 머리글: 상권번호,상권명,유형구분,시도코드,시도명,시군구코드,시군구명,
            상권좌표수,상권좌표,데이터기준일자
  · `상권좌표` 한 칸이 13만 자를 넘는다 → 읽을 때 csv.field_size_limit 를 올려야 한다
    (적재기 load_sbiz_district.py 가 처리한다)

⚠️ 왜 두 번이 아니라 **세 번** 부르나 (여기가 함정이다)
-------------------------------------------------------
포털의 "다운로드" 버튼이 부르는 주소는 파일을 주지 않는다:

  ① 상세 페이지 HTML          → 파일 식별자 `uddi:…` 를 읽는다
  ② selectFileDataDownload.do → **파일이 아니라 JSON 메타**가 온다
                                (여기서 atchFileId·fileDetailSn 을 읽는다)
  ③ fileDownload.do           → 이게 진짜 CSV 다

②를 파일로 착각하면 30MB 대신 몇 KB 짜리 JSON 을 저장해 놓고 "받았다"고 넘어간다.
로그인은 필요 없고 User-Agent 헤더만 있으면 된다(2026-08-14 실측).

쓰는 법
-------
    python scripts/collectors/fetch_sbiz_district.py --probe   # 크기·이름만 확인, 저장 0
    python scripts/collectors/fetch_sbiz_district.py           # data/raw/sbiz_district/

표준 라이브러리 + requests 만 쓴다.
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import unquote

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "sbiz_district")

PUBLIC_DATA_PK = "15090955"
DATASET_PAGE = "https://www.data.go.kr/data/{}/fileData.do".format(PUBLIC_DATA_PK)
META_URL = "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do"
DOWNLOAD_URL = "https://www.data.go.kr/cmm/cmm/fileDownload.do"

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = (30, 300)
CHUNK = 1024 * 1024

# 2026-08-14 실측 30.5MB. 오류 페이지·JSON 메타는 수십 KB 라 이 선에서 걸린다.
MIN_VALID_BYTES = 1024 * 1024
DEFAULT_MAX_MB = 200.0

# 서버가 이름을 안 주면 쓸 이름. 원본명(…_20240101.csv)이 기준일자를 담고 있어
# 되도록 그대로 쓰되, 못 읽었을 때 파일이 이름 없이 사라지지는 않게 한다.
FALLBACK_NAME = "sbiz_major_district.csv"

# 상세 페이지에 박힌 파일 식별자. `uddi:` + UUID + (선택) `_배포일시`.
RE_UDDI = re.compile(r"uddi:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                     r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?:_\d+)?")

ENCODING = "cp949"
REQUIRED_HEADER = ("상권번호", "상권명", "유형구분", "시도코드", "시도명",
                   "시군구코드", "시군구명", "상권좌표수", "상권좌표", "데이터기준일자")


# ── 순수 함수 (네트워크·디스크 없음 — 테스트 대상) ───────────────────────────


def parse_uddi(html_text):
    """상세 페이지 HTML 에서 파일 식별자(`uddi:…`)를 뽑는다.

    못 찾으면 ValueError — 조용히 기본값으로 넘어가면 **엉뚱한 파일**을 받는다.
    여러 개면 맨 앞(=목록 첫 파일, 이 데이터셋은 CSV 한 개뿐)을 쓴다.
    """
    hits = RE_UDDI.findall(html_text or "")
    if not hits:
        raise ValueError(
            "상세 페이지에서 파일 식별자(uddi:…)를 못 찾았습니다. "
            "포털 화면 구조가 바뀌었거나 응답이 오류 페이지입니다 — 사람이 확인해야 합니다.")
    seen = []
    for h in hits:
        if h not in seen:
            seen.append(h)
    return seen[0]


def parse_file_download_args(meta_text):
    """②의 **JSON 메타**에서 진짜 다운로드 인자를 뽑는다.

    이 응답을 파일로 착각하는 것이 이 수집기의 가장 큰 함정이라, 파일처럼 생긴
    응답(=JSON 이 아님)이 오면 앞부분을 붙여 에러를 낸다.
    """
    text = (meta_text or "").strip()
    try:
        meta = json.loads(text)
    except ValueError:
        raise ValueError(
            "다운로드 메타가 JSON 이 아닙니다 — 앞부분: {!r}. "
            "포털이 절차를 바꿨을 수 있습니다.".format(text[:200]))
    if not isinstance(meta, dict):
        raise ValueError("다운로드 메타가 객체가 아닙니다: {!r}".format(text[:200]))

    file_id = str(meta.get("atchFileId") or "").strip()
    detail_sn = str(meta.get("fileDetailSn") or "").strip()
    missing = [k for k, v in (("atchFileId", file_id), ("fileDetailSn", detail_sn)) if not v]
    if missing:
        raise ValueError(
            "다운로드 메타에 {} 가 없습니다 (받은 키: {}). 포털 응답 형식이 바뀌었습니다.".format(
                ", ".join(missing), ", ".join(sorted(meta))))
    return {"atchFileId": file_id, "fileDetailSn": detail_sn}


def safe_filename(name, fallback=FALLBACK_NAME):
    """서버가 준 이름에서 경로를 떼어 낸다.

    이름에 `..\\` 나 `/` 가 섞여 오면 엉뚱한 자리에 쓴다. 파일명만 남긴다.
    """
    cleaned = (name or "").strip().strip('"').replace("\\", "/")
    cleaned = cleaned.split("/")[-1].strip()
    if not cleaned or cleaned in (".", ".."):
        return fallback
    return cleaned


def filename_from_disposition(disposition, fallback=FALLBACK_NAME):
    """Content-Disposition 에서 파일 이름을 읽는다.

    한글 이름이 percent-encoding 으로 오거나, requests 가 헤더를 latin-1 로 풀어
    `¼ÒŰ...` 처럼 깨져 보인다. 되돌리지 않으면 저장된 파일 이름을 사람이 못 읽는다
    (기능에는 영향이 없지만, 다음 세션이 "이게 뭐지" 하게 된다).
    """
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", disposition or "")
    if not m:
        return fallback
    name = unquote(m.group(1))
    if any(ord(ch) > 127 for ch in name) and all(ord(ch) < 256 for ch in name):
        raw = name.encode("latin-1", "ignore")
        for enc in ("utf-8", "cp949"):
            try:
                name = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    return safe_filename(name, fallback)


def assert_csv_shape(content):
    """받은 바이트가 우리가 아는 그 CSV 인지 확인한다.

    오류 페이지·JSON 메타를 "받았다"고 넘기면, 적재기가 0행을 넣고도 성공처럼 끝난다.
    """
    if len(content) < MIN_VALID_BYTES:
        raise ValueError(
            "응답이 너무 작습니다({:,} B). 실측 30.5MB 라 이건 오류 페이지이거나 "
            "②의 JSON 메타를 파일로 착각한 것입니다.".format(len(content)))
    head = content[:4096].decode(ENCODING, "replace")
    first_line = head.splitlines()[0] if head.splitlines() else ""
    columns = [c.strip().strip('"') for c in first_line.split(",")]
    missing = [c for c in REQUIRED_HEADER if c not in columns]
    if missing:
        raise ValueError(
            "머리글에 {} 가 없습니다 (읽은 머리글: {!r}). 소스 형식이 바뀌었습니다.".format(
                ", ".join(missing), first_line[:200]))
    return {"bytes": len(content), "columns": columns}


def human(n):
    if n is None:
        return "알 수 없음"
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return "{:.2f} {}".format(f, unit)
        f /= 1024


# ── 네트워크 ─────────────────────────────────────────────────────────────────


def new_session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})
    return s


def fetch(session=None, probe=False, max_mb=DEFAULT_MAX_MB):
    """①→②→③ 세 걸음. (내용 바이트, 정보) 를 돌려준다.

    probe=True 면 ③의 **헤더까지만** 보고 본문을 받지 않는다(내용은 None).
    """
    s = session or new_session()

    page = s.get(DATASET_PAGE, timeout=TIMEOUT)
    page.raise_for_status()
    uddi = parse_uddi(page.text)

    meta = s.get(META_URL,
                 params={"publicDataPk": PUBLIC_DATA_PK, "publicDataDetailPk": uddi},
                 headers={"Referer": DATASET_PAGE}, timeout=TIMEOUT)
    meta.raise_for_status()
    args = parse_file_download_args(meta.text)

    resp = s.get(DOWNLOAD_URL, params=args, headers={"Referer": DATASET_PAGE},
                 stream=True, timeout=TIMEOUT)
    try:
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        clen = resp.headers.get("content-length")
        size = int(clen) if clen and clen.isdigit() else None
        fname = filename_from_disposition(resp.headers.get("content-disposition", ""))
        info = {"uddi": uddi, "args": args, "content_type": ctype,
                "size": size, "filename": fname}

        if "text/html" in ctype.lower():
            raise ValueError(
                "파일이 아니라 HTML 이 왔습니다(content-type={!r}) — 절차가 바뀌었습니다.".format(ctype))
        if size is not None and size > max_mb * 1024 * 1024:
            raise ValueError(
                "파일이 상한 {:.0f}MB 를 넘습니다({}) — 받지 않았습니다.".format(max_mb, human(size)))
        if probe:
            return None, info

        got = bytearray()
        for chunk in resp.iter_content(CHUNK):
            if not chunk:
                continue
            got.extend(chunk)
            if len(got) > max_mb * 1024 * 1024:
                raise ValueError("받는 도중 상한 {:.0f}MB 초과 — 중단했습니다.".format(max_mb))
        return bytes(got), info
    finally:
        resp.close()


def main(argv=None):
    # cp949 콘솔에서 한글·특수문자(—) 출력이 UnicodeEncodeError 로 죽지 않게 —
    # 형제 스크립트들(backup_raw.py 등)과 같은 처방(2026-08-14 사실검증에서 누락 발견).
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="소상공인시장진흥공단 주요상권현황 CSV 내려받기")
    p.add_argument("--probe", action="store_true",
                   help="크기·이름·형식만 확인하고 저장하지 않는다")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                   help="저장 위치 (기본: data/raw/sbiz_district)")
    p.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB,
                   help="이 크기를 넘으면 중단 (기본 {:.0f})".format(DEFAULT_MAX_MB))
    a = p.parse_args(argv)

    print("=" * 70)
    print("소상공인시장진흥공단 주요상권현황(15090955) 내려받기")
    print("=" * 70)

    try:
        content, info = fetch(probe=a.probe, max_mb=a.max_mb)
    except Exception as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1

    print("  파일 식별자 : {}".format(info["uddi"]))
    print("  다운로드 인자: atchFileId={atchFileId} fileDetailSn={fileDetailSn}".format(**info["args"]))
    print("  응답 형식   : {}".format(info["content_type"] or "(안 알려줌)"))
    print("  파일 이름   : {}".format(info["filename"]))
    print("  파일 크기   : {}".format(human(info["size"])))

    if a.probe:
        print()
        print("--probe 지정 — 본문을 받지도, 저장하지도 않았습니다.")
        return 0

    assert content is not None  # probe 는 위에서 이미 리턴했다 (정적 분석용 못박기)
    try:
        shape = assert_csv_shape(content)
    except ValueError as e:
        print("실패: {}".format(e), file=sys.stderr)
        return 1
    print("  받은 크기   : {} / 열 {}개".format(human(shape["bytes"]), len(shape["columns"])))

    os.makedirs(a.out_dir, exist_ok=True)
    dest = os.path.join(a.out_dir, info["filename"])

    # ⛔ raw 는 절대 덮어쓰지 않는다 (CLAUDE.md 절대 규칙 6 — 원본은 복구 불가).
    #    이 자료는 갱신 주기가 정해져 있지 않아 같은 이름으로 다른 판이 올 수 있다.
    #    그냥 열어 쓰면 먼저 받은 판이 말없이 사라진다 — 되돌릴 수 없는 사고다.
    #    우회 옵션(--force)은 **일부러 만들지 않는다**. 있으면 결국 쓰게 된다.
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
            "  기존 파일을 손으로 옮긴 뒤 다시 받으세요.".format(
                dest, len(existing), len(content)),
            file=sys.stderr)
        return 1

    with open(dest, "wb") as f:
        f.write(content)
    print()
    print("  저장: {}".format(dest))
    print()
    print("  다음: python scripts/collectors/load_sbiz_district.py --dry-run")
    print("  💾 원본이 늘었으니 python scripts/backup_raw.py 도 잊지 마세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
