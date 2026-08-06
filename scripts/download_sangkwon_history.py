# -*- coding: utf-8 -*-
"""
소상공인시장진흥공단 상가(상권)정보 — 공공데이터포털 "주기성 과거 데이터" 일괄 다운로드.

CLAUDE.md 절대규칙 6번: 분기 스냅샷은 소급 불가. 지금 받아두지 않으면 영원히 못 받는다.
이 스크립트는 포털의 과거 파일 목록(분기별 zip)을 통째로 내려받아 보관한다.

프로토콜(실측 검증 완료):
  1단계  POST /tcs/dss/selectHistAndCsvData.do     → 과거 파일 목록 HTML 조각
  2단계  POST /tcs/dss/selectFileDataDownload.do   → 분기별 실제 파일 ID(atchFileId) JSON
  3단계  GET  /cmm/cmm/fileDownload.do             → zip 바이너리 스트림

사용법:
  python scripts/download_sangkwon_history.py            # 전체(분기 파일 42개)
  python scripts/download_sangkwon_history.py --limit 1  # 최신 1개만 (테스트용)

표준 라이브러리만 사용 (Python 3.12).
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

# ── 설정 ──────────────────────────────────────────────────────────────────────

# 상권정보 데이터셋 식별자 (포털 고정값)
PUBLIC_DATA_PK = "15083033"
BASE_DETAIL_PK = "uddi:6a450671-390c-4b6d-979c-fa056a627084"

URL_HIST_LIST = "https://www.data.go.kr/tcs/dss/selectHistAndCsvData.do"
URL_FILE_INFO = "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do"
URL_DOWNLOAD = "https://www.data.go.kr/cmm/cmm/fileDownload.do"

# 이 헤더가 없으면 포털이 응답을 거부한다 (실측 확인). 로그인·쿠키는 불필요.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# 저장 위치: 프로젝트 루트/data/raw/sangkwon_zips/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "sangkwon_zips")

SLEEP_SEC = 9  # 파일 사이 대기(서버 예의 + 다운로드 제한 회피). 사장님 지정값
CHUNK_SIZE = 1024 * 1024  # 1MB 단위 스트리밍 저장
MIN_VALID_BYTES = 1024 * 1024  # 이어받기 판정: 1MB 미만이면 깨진 파일로 간주
MAX_CONSECUTIVE_FAIL = 2  # 연속 실패 이 횟수면 중단
TIMEOUT_SEC = 300  # zip이 수백 MB라 넉넉히

# 분기 스냅샷 파일명 패턴 (…_20251231 형태). "포천시 업소수" 같은 단발성 파일은 제외
RE_QUARTERLY = re.compile(r"_20\d{6}$")

# 과거 목록 HTML 조각 파싱용 (실측 검증된 정규식)
RE_ANCHOR = re.compile(r"<a\s+[^>]*openFileDetailPopup[^>]*>\s*([^<]+?)\s*</a>")
RE_PUBLIC_PK = re.compile(r'data-public-pk="([^"]+)"')

ZIP_MAGIC = b"PK\x03\x04"


# ── 공통 HTTP 도우미 ──────────────────────────────────────────────────────────


def _post(url: str, form: dict) -> bytes:
    """POST 폼 요청 후 응답 바디를 그대로 돌려준다."""
    data = urllib.parse.urlencode(form, encoding="utf-8").encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "*/*",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        return resp.read()


# ── 1단계: 과거 파일 목록 ─────────────────────────────────────────────────────


def fetch_history_list() -> list:
    """포털에서 과거 분기 파일 목록을 받아 [{name, uddi}] 리스트로 돌려준다."""
    body = _post(
        URL_HIST_LIST,
        {"publicDataPk": PUBLIC_DATA_PK, "publicDataDetailPk": BASE_DETAIL_PK},
    )
    html = body.decode("utf-8", errors="replace")

    items = []
    seen = set()
    for m in RE_ANCHOR.finditer(html):
        tag = m.group(0)
        name = m.group(1).strip()
        pk_match = RE_PUBLIC_PK.search(tag)
        if not pk_match:
            continue
        # 분기 스냅샷만 대상 (단발성 통계 파일 제외)
        if not RE_QUARTERLY.search(name):
            continue
        uddi = pk_match.group(1)
        if uddi in seen:
            continue
        seen.add(uddi)
        items.append({"name": name, "uddi": uddi})
    return items


# ── 2단계: 파일 ID 조회 ───────────────────────────────────────────────────────


def fetch_file_id(uddi: str) -> tuple:
    """분기 uddi로 실제 다운로드용 (atchFileId, fileDetailSn)를 조회한다."""
    body = _post(
        URL_FILE_INFO,
        {
            "publicDataPk": PUBLIC_DATA_PK,
            "publicDataDetailPk": uddi,
            "atchFileId": "",
            "fileDetailSn": "1",
            "publicDataTyCode": "PR0051",
        },
    )
    info = json.loads(body.decode("utf-8", errors="replace"))
    if not info.get("status"):
        raise RuntimeError(f"파일 ID 조회 실패(status=false): {info}")
    atch_file_id = info.get("atchFileId")
    if not atch_file_id:
        raise RuntimeError(f"atchFileId 없음: {info}")
    return atch_file_id, str(info.get("fileDetailSn") or "1")


# ── 3단계: zip 스트리밍 다운로드 ──────────────────────────────────────────────


def download_zip(atch_file_id: str, file_detail_sn: str, name: str, dest_path: str) -> int:
    """
    zip을 1MB 청크로 스트리밍 저장한다. 저장 바이트 수를 돌려준다.
    응답 첫 4바이트가 PK가 아니면(= 다운로드 제한/캡차 HTML) 즉시 예외를 던진다.
    """
    query = urllib.parse.urlencode(
        {"atchFileId": atch_file_id, "fileDetailSn": file_detail_sn, "dataNm": name},
        encoding="utf-8",
    )
    req = urllib.request.Request(
        f"{URL_DOWNLOAD}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        method="GET",
    )

    tmp_path = dest_path + ".part"
    total = 0
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        head = resp.read(4)
        if head[:4] != ZIP_MAGIC:
            # zip이 아니다 = 서버가 HTML(제한 안내/캡차 등)을 돌려준 것.
            # 계속 두드리면 차단되므로 앞부분을 보여주고 중단시킨다.
            rest = resp.read(496)
            snippet = (head + rest).decode("utf-8", errors="replace")
            raise RuntimeError("zip 아님 — 응답 앞부분 500바이트:\n" + snippet)

        with open(tmp_path, "wb") as f:
            f.write(head)
            total += len(head)
            while True:
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)

    os.replace(tmp_path, dest_path)
    return total


# ── 이어받기 판정 ─────────────────────────────────────────────────────────────


def already_downloaded(path: str) -> bool:
    """이미 받아둔 정상 zip이면 True (첫 4바이트 PK + 1MB 이상)."""
    if not os.path.exists(path):
        return False
    if os.path.getsize(path) < MIN_VALID_BYTES:
        return False
    with open(path, "rb") as f:
        return f.read(4) == ZIP_MAGIC


# ── 메인 ──────────────────────────────────────────────────────────────────────


def main() -> int:
    # 한글 파일명 출력이 인코딩 때문에 죽거나 깨지지 않게.
    # 로그 파일로 리다이렉트된 경우(백그라운드 실행)엔 UTF-8로 고정한다.
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 >= len(sys.argv):
            print("--limit 뒤에 개수를 적어야 합니다.", flush=True)
            return 2
        limit = int(sys.argv[idx + 1])

    os.makedirs(SAVE_DIR, exist_ok=True)

    print("과거 파일 목록 조회 중...", flush=True)
    try:
        items = fetch_history_list()
    except Exception as e:
        print(f"목록 조회 실패: {e}", flush=True)
        return 1

    if not items:
        print("분기 파일을 하나도 찾지 못했습니다. 포털 응답 형식이 바뀌었을 수 있습니다.", flush=True)
        return 1

    print(f"분기 파일 {len(items)}개 발견", flush=True)
    if limit is not None:
        items = items[:limit]
        print(f"--limit {limit} → 앞에서 {len(items)}개만 처리", flush=True)

    total_count = len(items)
    ok = skipped = failed = 0
    total_bytes = 0
    consecutive_fail = 0

    for i, item in enumerate(items, start=1):
        name = item["name"]
        dest = os.path.join(SAVE_DIR, name + ".zip")
        tag = f"[{i}/{total_count}] {name}"

        if already_downloaded(dest):
            size_mb = os.path.getsize(dest) / 1024 / 1024
            skipped += 1
            total_bytes += os.path.getsize(dest)
            print(f"{tag} — 스킵(이미 있음, {size_mb:.1f}MB)", flush=True)
            continue

        started = time.time()
        try:
            atch_file_id, file_detail_sn = fetch_file_id(item["uddi"])
            written = download_zip(atch_file_id, file_detail_sn, name, dest)
        except Exception as e:
            failed += 1
            consecutive_fail += 1
            elapsed = time.time() - started
            print(f"{tag} — 실패 ({elapsed:.1f}초): {e}", flush=True)
            # 조각 파일이 남았으면 치운다
            part = dest + ".part"
            if os.path.exists(part):
                try:
                    os.remove(part)
                except OSError:
                    pass
            if consecutive_fail >= MAX_CONSECUTIVE_FAIL:
                print(
                    f"연속 {consecutive_fail}회 실패 — 다운로드 제한이 걸린 것으로 보고 중단합니다.",
                    flush=True,
                )
                break
            print(f"{SLEEP_SEC}초 대기 후 다음 파일...", flush=True)
            time.sleep(SLEEP_SEC)
            continue

        consecutive_fail = 0
        ok += 1
        total_bytes += written
        elapsed = time.time() - started
        print(
            f"{tag} — 완료 {written / 1024 / 1024:.1f}MB, {elapsed:.1f}초", flush=True
        )

        if i < total_count:
            time.sleep(SLEEP_SEC)

    print("", flush=True)
    print("=" * 60, flush=True)
    print(
        f"요약: 성공 {ok} / 스킵 {skipped} / 실패 {failed}  "
        f"(대상 {total_count}개)",
        flush=True,
    )
    print(f"총 용량: {total_bytes / 1024 / 1024 / 1024:.2f}GB", flush=True)
    print(f"저장 위치: {SAVE_DIR}", flush=True)
    print("=" * 60, flush=True)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
