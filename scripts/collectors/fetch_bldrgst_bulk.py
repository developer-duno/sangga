# -*- coding: utf-8 -*-
"""건축HUB 대용량 건축물대장 파일 1종을 받는다 (표제부/층별개요/전유공용면적).

배경
----
건축물대장을 API로 전국 수집하면 211일이 걸린다(`docs/decisions/0005`). 건축HUB가
같은 데이터를 **대용량 파일**로 월 단위 제공하므로 그쪽이 압도적으로 빠르다.
목록·컬럼 정의는 비로그인으로 열리며, 3종 모두 PNU 19자리를 조립할 수 있는
`시군구_코드·법정동_코드·대지_구분_코드·번·지`를 갖고 있다(2026-08-10 실측).

동작
----
1. 목록 페이지를 열어 세션 쿠키와 CSRF 토큰을 얻는다.
2. 이용 이력을 남긴다(사이트가 다운로드 전에 호출하는 절차 그대로).
3. 다운로드를 **스트리밍으로 열어 헤더(크기·파일명)만 먼저 확인**한다.
   `--max-gb`를 넘으면 본문을 받지 않고 중단한다(기본 12GB).
4. 통과하면 `data/raw/bldrgst_bulk/<기준월>/` 아래에 저장한다.

사용
----
    python scripts/collectors/fetch_bldrgst_bulk.py --probe          # 크기만 확인(저장 0)
    python scripts/collectors/fetch_bldrgst_bulk.py --kind title     # 표제부 받기
    python scripts/collectors/fetch_bldrgst_bulk.py --kind flr_ouln --max-gb 20

⚠️ 파일 ID는 매월 바뀐다. `--list`로 현재 목록을 다시 읽어 확인할 것.
"""
from __future__ import print_function

import argparse
import os
import re
import sys
import time
from urllib.parse import unquote

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "https://www.hub.go.kr"
LIST_URL = BASE + "/portal/opn/lps/idx-lgcpt-pvsn-srvc-list.do"
HSTRY_URL = BASE + "/portal/opn/lps/idx-srvc-hstry-insert.do"
DOWN_URL = BASE + "/cmm/fms/fileOpnDown.do"

TASK_SE_CD = "03"  # 건축물대장

# 우리가 쓰는 3종. opnTaskCd 는 고정, 파일 ID(srvrFileNm)는 매월 바뀐다.
KINDS = {
    "title": ("0303", "표제부"),
    "flr_ouln": ("0304", "층별개요"),
    "expos_area": ("0306", "전유공용면적"),
}

# 이용목적 코드 — 사이트 팝업의 라디오 값. 3 = 참고자료.
PRPS_CD = "3"

DEFAULT_MAX_GB = 12.0
CHUNK = 1024 * 1024
TIMEOUT = (30, 300)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class BulkError(RuntimeError):
    pass


def new_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    return s


def open_list(session, task_se_cd=TASK_SE_CD, page_size=40):
    """목록 페이지 HTML과 CSRF 토큰을 돌려준다."""
    r = session.get(LIST_URL, params={"opnLgcptTaskSeCd": task_se_cd,
                                      "pageCountPerPage": page_size},
                    timeout=TIMEOUT)
    r.raise_for_status()
    html = r.text
    # 토큰은 <meta name="_csrf" content="..."> 로 온다 (페이지 JS 전역이 아니라 meta).
    name = re.search(
        r'<meta\s+name="_csrf_parameter"\s+content="([^"]+)"', html)
    token = re.search(r'<meta\s+name="_csrf"\s+content="([^"]+)"', html)
    if not (name and token):
        raise BulkError("CSRF 토큰을 못 찾았다 — 페이지 구조가 바뀌었을 수 있다")
    return html, name.group(1), token.group(1)


def parse_entries(html):
    """목록 HTML에서 (opnTaskCd, 서비스명, 파일ID) 목록을 뽑는다."""
    out = []
    for m in re.finditer(
            r"fnDownloadPop\('(\d+)','(\d+)','([^']+)'\)", html):
        task_se, task_cd, file_id = m.groups()
        out.append({"opnLgcptTaskSeCd": task_se, "opnTaskCd": task_cd,
                    "srvrFileNm": file_id})
    # 서비스명은 별도 태그라 순서로 짝짓는다 (목록 순서 = 버튼 순서)
    titles = re.findall(r'<p class="tit">([^<]+)</p>', html)
    for i, e in enumerate(out):
        e["srvcNm"] = titles[i].strip() if i < len(titles) else ""
    return out


def pick(entries, task_cd):
    """해당 opnTaskCd 중 가장 최신(목록 상단) 항목."""
    for e in entries:
        if e["opnTaskCd"] == task_cd:
            return e
    raise BulkError("opnTaskCd={} 항목이 목록에 없다".format(task_cd))


def insert_history(session, entry, csrf_name, csrf_token):
    """사이트가 다운로드 직전에 호출하는 이용 이력 기록."""
    data = {"opnLgcptTaskSeCd": entry["opnLgcptTaskSeCd"],
            "opnTaskCd": entry["opnTaskCd"],
            "opnPrcusePrpsCd": PRPS_CD,
            csrf_name: csrf_token}
    r = session.post(HSTRY_URL, data=data,
                     headers={"X-Requested-With": "XMLHttpRequest",
                              "Referer": LIST_URL},
                     timeout=TIMEOUT)
    return r.status_code


def filename_from(resp, fallback):
    disp = resp.headers.get("content-disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", disp)
    if m:
        try:
            return unquote(m.group(1))
        except Exception:
            return m.group(1)
    return fallback


def human(n):
    if n is None:
        return "알 수 없음"
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return "{:.2f} {}".format(f, unit)
        f /= 1024


def download(session, entry, csrf_name, csrf_token, out_dir,
             max_gb=DEFAULT_MAX_GB, probe=False):
    data = {"srvrFileNm": entry["srvrFileNm"], csrf_name: csrf_token}
    resp = session.post(DOWN_URL, data=data,
                        headers={"Referer": LIST_URL},
                        stream=True, timeout=TIMEOUT)
    try:
        if resp.status_code != 200:
            raise BulkError("다운로드 응답 HTTP {} — 본문 앞부분: {}".format(
                resp.status_code, resp.text[:200].replace("\n", " ")))

        ctype = resp.headers.get("content-type", "")
        clen = resp.headers.get("content-length")
        size = int(clen) if clen and clen.isdigit() else None
        fname = filename_from(resp, entry["srvrFileNm"])

        print("  응답 형식 : {}".format(ctype))
        print("  파일 이름 : {}".format(fname))
        print("  파일 크기 : {}{}".format(
            human(size), "" if size else " (서버가 크기를 안 알려줌)"))

        if "text/html" in ctype.lower():
            raise BulkError(
                "파일이 아니라 HTML이 왔다 — 로그인이 필요하거나 절차가 다르다")

        if size and size > max_gb * 1024 ** 3:
            raise BulkError(
                "{} 는 상한 {:.0f}GB 를 넘는다 — 중단(--max-gb 로 조정)".format(
                    human(size), max_gb))

        if probe:
            print("  → --probe 모드: 본문을 받지 않고 종료한다")
            return None

        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        path = os.path.join(out_dir, fname)
        tmp = path + ".part"

        got = 0
        t0 = time.time()
        last = 0.0
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(CHUNK):
                if not chunk:
                    continue
                f.write(chunk)
                got += len(chunk)
                now = time.time()
                if now - last >= 5:
                    last = now
                    spd = got / max(now - t0, 0.001) / 1024 ** 2
                    pct = ("{:.1f}%".format(got * 100.0 / size)
                           if size else "?")
                    print("    {} / {}  {}  {:.1f} MB/s".format(
                        human(got), human(size), pct, spd))
                if got > max_gb * 1024 ** 3:
                    raise BulkError(
                        "받는 도중 상한 {:.0f}GB 초과 — 중단".format(max_gb))
        os.rename(tmp, path)
        print("  저장 완료 : {}  ({})".format(path, human(got)))
        return path
    finally:
        resp.close()


def main(argv=None):
    p = argparse.ArgumentParser(description="건축HUB 대용량 건축물대장 파일 받기")
    p.add_argument("--kind", choices=sorted(KINDS), default="title",
                   help="받을 종류 (기본 title=표제부)")
    p.add_argument("--probe", action="store_true",
                   help="크기·형식만 확인하고 저장하지 않는다")
    p.add_argument("--list", action="store_true",
                   help="현재 목록만 출력하고 끝낸다")
    p.add_argument("--max-gb", type=float, default=DEFAULT_MAX_GB,
                   help="이 크기를 넘으면 중단 (기본 {:.0f})".format(DEFAULT_MAX_GB))
    p.add_argument("--out-dir",
                   default=os.path.join(PROJECT_ROOT, "data", "raw", "bldrgst_bulk"),
                   help="저장 폴더")
    a = p.parse_args(argv)

    s = new_session()
    print("목록 조회 …")
    html, csrf_name, csrf_token = open_list(s)
    entries = parse_entries(html)
    print("  건축물대장 항목 {}건 · CSRF 파라미터 '{}'".format(len(entries), csrf_name))

    if a.list:
        for e in entries:
            print("  {:<6} {:<28} {}".format(
                e["opnTaskCd"], e["srvcNm"], e["srvrFileNm"]))
        return 0

    task_cd, ko = KINDS[a.kind]
    entry = pick(entries, task_cd)
    print("\n대상: {} (opnTaskCd={})".format(entry["srvcNm"] or ko, task_cd))
    print("  파일 ID  : {}".format(entry["srvrFileNm"]))

    code = insert_history(s, entry, csrf_name, csrf_token)
    print("  이용이력 : HTTP {}".format(code))

    out_dir = a.out_dir
    m = re.search(r"(\d{4})\s*년\s*(\d{2})\s*월", entry["srvcNm"] or "")
    if m:
        out_dir = os.path.join(out_dir, m.group(1) + m.group(2))

    print("\n다운로드 …")
    try:
        download(s, entry, csrf_name, csrf_token, out_dir,
                 max_gb=a.max_gb, probe=a.probe)
    except BulkError as e:
        print("\n⛔ {}".format(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
