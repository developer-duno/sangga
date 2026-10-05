# -*- coding: utf-8 -*-
"""서울시 상권분석서비스(점포-상권 · OA-15577) **연도 zip** 내려받기 — 인증키 없는 대비책 (결정 0033).

왜 대비책인가
-------------
본 경로는 열린 API(`collect_seoul_openclose.py` — 분기마다 갱신)다. 연도 zip 은 **연 1회**만
올라오고(2025년.zip 2026-05-21 게시) 인증키가 필요 없다 — 키가 막혔거나 API 가 내려간 날 쓰는
길이다. ⚠️ 지난 해 zip 이 **다시 발행된다**(2021~2024 CSV 작성일이 전부 2025-06-04 — 결정 0033
실측표) → 받을 때마다 날짜를 붙여 쌓고 덮어쓰지 않는다.

왜 seq 를 "제목 ↔ seq 대응"으로 고르나
---------------------------------------
형제 `fetch_seoul_district.py` 는 "가장 큰 seq = 가장 최근 파일"로 고르는데, 이 페이지는 **해마다
파일이 하나씩**(2021~2025 다섯 개) 걸려 있어 그 방식이면 늘 최신 해만 받는다. 그래서 목록의
`<span title="…_2024년.zip" onclick="javascript:downloadFile('19');">` 처럼 **제목에 그 해가 든
줄의 seq** 를 쓴다(2026-10-05 페이지 실측: 2025→20 · 2024→19 · 2023→18 · 2022→17 · 2021→16 —
값은 포털이 바꿀 수 있으니 코드에 박지 않는다).
또 이 페이지엔 숨은 폼이 둘이고 `infSeq` 가 **둘**이다 — `frmApiDown`(열린 API 안내 · 2)과
`frmFile`(파일 받기 · 3). 다운로드에는 **frmFile 의 값**을 쓴다(아무 `infSeq` 나 집으면 2 가 걸린다).
못 찾으면 조용히 넘어가지 않고 멈춘다(포털 구조가 바뀐 것이라 사람이 봐야 한다).

zip 안 이름이 깨져 보이는 함정
------------------------------
zip 이 이름을 cp949 로 적고 UTF-8 표시를 안 다는 일이 있다 → 파이썬이 cp437 로 읽어 `╝¡┐∩…`
같은 글자가 나온다. 보여 줄 때만 `readable_member()` 로 되돌리고, 읽기는 **원래 이름**으로 한다.

쓰는 법 (프로젝트 루트에서)
---------------------------
    python scripts/collectors/fetch_seoul_openclose_zip.py --year 2025 --probe   # 크기·내용만, 저장 0
    python scripts/collectors/fetch_seoul_openclose_zip.py --year 2025           # data/raw/seoul_openclose/zip/2025_<오늘>.zip
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
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "seoul_openclose", "zip")

DATASET_PAGE = "https://data.seoul.go.kr/dataList/OA-15577/S/1/datasetView.do"
DOWNLOAD_URL = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TIMEOUT_SEC = 120

ZIP_MAGIC = b"PK\x03\x04"
MIN_VALID_BYTES = 500 * 1024   # 2026-10-05 실측 각 2.1~2.2MB. 한참 작으면 오류 페이지다.

# frmFile 폼 하나만 잘라 그 안의 infId·infSeq 를 읽는다(frmApiDown 의 infSeq=2 를 집지 않게).
RE_FRM_FILE = re.compile(r'(?is)<form[^>]*\bname="frmFile"[^>]*>(.*?)</form>')
RE_HIDDEN = re.compile(r'name="(infId|infSeq)"\s+value="([^"]*)"')
# 목록의 <span title="…_2024년.zip" onclick="javascript:downloadFile('19');">
RE_FILE_SPAN = re.compile(r"""<span\s+title="([^"]+)"\s+onclick="javascript:downloadFile\('(\d+)'\);">""")


def parse_download_params(html_text, year):
    """상세 페이지 HTML 에서 그 해 zip 의 폼 인자를 뽑는다 → {"infId","infSeq","seq","title"}.

    ⛔ 그 해 제목이 0개거나 2개 이상이면 ValueError — 어느 파일인지 모르는 채 받지 않는다.
    """
    html_text = html_text or ""
    form = RE_FRM_FILE.search(html_text)
    found = dict(RE_HIDDEN.findall(form.group(1))) if form else {}
    missing = [k for k in ("infId", "infSeq") if not found.get(k)]
    if missing:
        raise ValueError(
            "파일 받기 폼(frmFile)에서 {} 를 못 찾았습니다 — 포털 화면 구조가 바뀌었을 수 있어 "
            "사람이 확인해야 합니다.".format(", ".join(missing)))
    tag = "_{}년.zip".format(int(year))
    hits = sorted({(t, s) for t, s in RE_FILE_SPAN.findall(html_text) if t.endswith(tag)})
    if len(hits) != 1:
        raise ValueError(
            "제목이 '…{}' 인 파일이 {}개입니다(정확히 1개여야 한다) — 목록: {}".format(
                tag, len(hits), [t for t, _ in RE_FILE_SPAN.findall(html_text)]))
    title, seq = hits[0]
    return {"infId": found["infId"], "infSeq": found["infSeq"], "seq": seq, "title": title}


def readable_member(name):
    """cp437 로 잘못 읽힌 cp949 이름을 되돌린다. 안 되면 그대로(이미 바르게 읽힌 이름)."""
    try:
        return name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def describe_zip(content):
    """쓸 만한 zip 인가(오류 HTML 을 '받았다'고 착각하지 않게) + 안의 csv 목록."""
    if len(content) < MIN_VALID_BYTES:
        raise ValueError("응답이 너무 작습니다({:,} B) — 오류 페이지일 가능성이 큽니다.".format(len(content)))
    if not content.startswith(ZIP_MAGIC):
        raise ValueError("zip 이 아닙니다(앞 4바이트 {!r}).".format(content[:4]))
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        members = [(readable_member(i.filename), i.file_size) for i in z.infolist()]
        csvs = [i.filename for i in z.infolist() if i.filename.lower().endswith(".csv")]
    if len(csvs) != 1:
        raise ValueError("zip 안 csv 가 {}개입니다(1개여야 한다): {}".format(len(csvs), members))
    return {"bytes": len(content), "members": members}


def fetch(year, session=None):
    """상세 페이지 → 그 해 인자 → zip. (바이트, 인자)."""
    s = session or requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    page = s.get(DATASET_PAGE, timeout=TIMEOUT_SEC)
    page.raise_for_status()
    params = parse_download_params(page.text, year)
    resp = s.post(DOWNLOAD_URL,
                  data={"infId": params["infId"], "infSeq": params["infSeq"],
                        "seq": params["seq"], "seqNo": ""},
                  headers={"Referer": DATASET_PAGE}, timeout=TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.content, params


def save(content, out_dir, year, ymd):
    """`<연도>_<받은날짜>.zip` 으로 저장. ⛔ 덮어쓰지 않는다 — 같은 내용이면 그대로, 다르면 멈춘다."""
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, "{}_{}.zip".format(int(year), ymd))
    if os.path.exists(dest):
        with open(dest, "rb") as f:
            if f.read() == content:
                return dest, "same"
        raise FileExistsError(
            "같은 자리에 내용이 다른 원본이 있습니다: {} — raw 는 덮어쓰지 않습니다(절대 규칙 6).".format(dest))
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(content)
    os.replace(tmp, dest)
    return dest, "new"


def main(argv=None):
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="서울시 상권분석서비스(점포-상권) 연도 zip 받기",
                                allow_abbrev=False)
    p.add_argument("--year", type=int, required=True, help="받을 해 (예: 2025)")
    p.add_argument("--probe", action="store_true", help="크기·내용만 확인하고 저장하지 않는다")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    a = p.parse_args(argv)

    try:
        content, params = fetch(a.year)
        info = describe_zip(content)
    except Exception as e:  # noqa: BLE001 — 무엇이든 사람이 봐야 한다
        print("실패: {}".format(e), file=sys.stderr)
        return 1

    print("  파일 : {}".format(params["title"]))
    print("  인자 : infId={infId} infSeq={infSeq} seq={seq}".format(**params))
    print("  크기 : {:,} B".format(info["bytes"]))
    for name, size in info["members"]:
        print("    {:>11,} B  {}".format(size, name))
    if a.probe:
        print("--probe — 저장하지 않았습니다.")
        return 0
    try:
        dest, how = save(content, a.out_dir, a.year, datetime.date.today().strftime("%Y%m%d"))
    except FileExistsError as e:
        print(str(e), file=sys.stderr)
        return 1
    print("  저장: {} ({})".format(dest, "이미 같은 내용 — 그대로 둠" if how == "same" else "새 파일"))
    print("  다음: python scripts/collectors/load_seoul_openclose.py --dry-run")
    print("  💾 원본이 늘었으니 python scripts/backup_raw.py 도 잊지 마세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
