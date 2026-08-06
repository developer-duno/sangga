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
  python scripts/download_sangkwon_history.py            # 전체(분기 파일, 2026-08-07 실측 41개 — 비분기 제외 7개는 별도)
  python scripts/download_sangkwon_history.py --limit 1  # 최신 1개만 (테스트용)

표준 라이브러리만 사용 (Python 3.12).
"""

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile

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
MIN_VALID_BYTES = 1024 * 1024  # 이어받기 판정 1차 관문: 1MB 미만이면 무조건 깨진 파일
MAX_CONSECUTIVE_FAIL = 2  # 연속 실패(재시도 소진 기준) 이 횟수면 중단
TIMEOUT_SEC = 300  # zip이 수백 MB라 넉넉히

RETRY_COUNT = 3  # 파일 1개당 최대 시도 횟수(최초 시도 포함)
RETRY_BACKOFF_BASE_SEC = 2  # 지수 백오프 밑값(2, 4초 …)

# 분기 스냅샷 파일명 패턴 (…_20251231 형태). "포천시 업소수" 같은 단발성 파일은 제외
RE_QUARTERLY = re.compile(r"_20\d{6}$")

# 과거 목록 HTML 조각 파싱용 (실측 검증된 정규식)
RE_ANCHOR = re.compile(r"<a\s+[^>]*openFileDetailPopup[^>]*>\s*([^<]+?)\s*</a>")
RE_PUBLIC_PK = re.compile(r'data-public-pk="([^"]+)"')

# Windows 금지 문자(< > : " / \ | ? *) + 제어문자. 파일명 sanitize 용.
RE_FORBIDDEN_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

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


def fetch_history_list() -> tuple:
    """포털에서 과거 분기 파일 목록을 받아 (분기 항목 리스트, 제외된 항목 이름 리스트)를 돌려준다.

    분기 패턴(RE_QUARTERLY)에 맞지 않는 항목은 조용히 버리지 않고 이름을 그대로
    돌려준다 — 실측 결과 포털 목록에 비분기 단발 파일이 섞여 있어(예: 2026-08-07
    기준 48건 중 7건), 사람이 그 이름을 보고 정말 제외해도 되는지 판정할 수 있어야 한다.
    """
    body = _post(
        URL_HIST_LIST,
        {"publicDataPk": PUBLIC_DATA_PK, "publicDataDetailPk": BASE_DETAIL_PK},
    )
    html_body = body.decode("utf-8", errors="replace")

    items = []
    excluded = []
    seen = set()
    for m in RE_ANCHOR.finditer(html_body):
        tag = m.group(0)
        name = m.group(1).strip()
        pk_match = RE_PUBLIC_PK.search(tag)
        if not pk_match:
            continue
        # 분기 스냅샷만 대상 (단발성 통계 파일은 제외 목록에 남긴다)
        if not RE_QUARTERLY.search(name):
            excluded.append(name)
            continue
        uddi = pk_match.group(1)
        if uddi in seen:
            continue
        seen.add(uddi)
        items.append({"name": name, "uddi": uddi})
    return items, excluded


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


# ── zip 완결성 검증 ───────────────────────────────────────────────────────────


def _zip_is_valid(path: str) -> bool:
    """zip이 정상적으로 열리고 전체 무결성(testzip)까지 통과하면 True.

    testzip()은 모든 항목의 CRC를 검사해 None(=이상 없음) 또는 첫 손상 항목명을
    돌려준다. 잘린 zip이 "완료"로 영구 스킵되는 걸 막는 핵심 검증.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip() is None
    except (zipfile.BadZipFile, OSError):
        return False


# ── 3단계: zip 스트리밍 다운로드 ──────────────────────────────────────────────


def download_zip(atch_file_id: str, file_detail_sn: str, name: str, dest_path: str) -> int:
    """
    zip을 1MB 청크로 스트리밍 저장한다. 저장 바이트 수를 돌려준다.
    응답 첫 4바이트가 PK가 아니면(= 다운로드 제한/캡차 HTML) 즉시 예외를 던진다.

    완결성 검증(2단계): 서버가 Content-Length를 줬다면 실제 저장 바이트 수와
    대조하고, 그 다음 zip을 실제로 열어 testzip()까지 통과해야만 os.replace로
    확정한다. 둘 중 하나라도 실패하면 .part 상태로 남기고 예외를 던진다.
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
        content_length_header = resp.headers.get("Content-Length")
        expected_bytes = int(content_length_header) if content_length_header else None

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

    if expected_bytes is not None and total != expected_bytes:
        raise RuntimeError(
            f"다운로드 불완전 — Content-Length {expected_bytes:,}바이트, "
            f"실제 저장 {total:,}바이트"
        )

    if not _zip_is_valid(tmp_path):
        raise RuntimeError("다운로드된 zip이 손상됨 (testzip 실패 또는 zip 열기 실패)")

    os.replace(tmp_path, dest_path)
    return total


def _download_one(item: dict, dest: str) -> int:
    """파일 1개를 지수 백오프 재시도(RETRY_COUNT회)와 함께 받는다.

    모든 시도가 실패하면 마지막 예외를 그대로 던진다. 재시도 사이에 남은
    .part 조각은 매번 치운다.
    """
    last_exc = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            atch_file_id, file_detail_sn = fetch_file_id(item["uddi"])
            return download_zip(atch_file_id, file_detail_sn, item["name"], dest)
        except Exception as e:
            last_exc = e
            part = dest + ".part"
            if os.path.exists(part):
                try:
                    os.remove(part)
                except OSError:
                    pass
            if attempt < RETRY_COUNT:
                backoff = RETRY_BACKOFF_BASE_SEC ** attempt
                print(
                    f"  재시도 {attempt}/{RETRY_COUNT} 실패: {e} — {backoff}초 후 재시도",
                    flush=True,
                )
                time.sleep(backoff)
    if last_exc is None:
        raise RuntimeError("재시도 루프가 한 번도 실행되지 않았습니다 (RETRY_COUNT 확인 필요).")
    raise last_exc


# ── 파일명 안전화 ─────────────────────────────────────────────────────────────


def sanitize_filename(raw_name: str) -> str:
    """포털이 준 이름을 안전한 로컬 파일명으로 바꾼다.

    순서: HTML 엔티티 해제 → 경로 성분 제거(basename) → Windows 금지문자 제거
    → 끝 공백/점 제거. 이후 호출부에서 os.path.commonpath로 SAVE_DIR 이탈 여부를
    한 번 더 확인한다(이중 방어).
    """
    name = html.unescape(raw_name)
    # 리눅스 basename은 역슬래시를 구분자로 안 봐서 Windows식 경로 성분이 살아남는다
    # (CI 리눅스 실측) — 구분자를 슬래시로 통일한 뒤 잘라 플랫폼 무관하게 만든다.
    name = name.replace("\\", "/")
    name = os.path.basename(name)
    name = RE_FORBIDDEN_FILENAME_CHARS.sub("_", name)
    name = name.strip(" .")
    if not name:
        name = "unnamed"
    return name


def resolve_dest_path(save_dir: str, safe_name: str) -> str:
    """SAVE_DIR 이탈 여부를 확인하고 최종 저장 경로를 돌려준다.

    이탈이 감지되면 ValueError를 던진다 (sanitize_filename을 거쳤어도 만약을
    대비한 이중 방어).
    """
    # 경로 구분자가 남아 있으면 그 자체로 거부 — 리눅스에선 '..\'가 구분자가 아니라
    # commonpath 검사를 통과해 버리므로(CI 실측) 플랫폼 무관 명시 검사가 먼저다.
    if "/" in safe_name or "\\" in safe_name:
        raise ValueError(f"파일명에 경로 구분자 포함: {safe_name!r}")
    save_dir_abs = os.path.abspath(save_dir)
    dest_abs = os.path.abspath(os.path.join(save_dir, safe_name + ".zip"))
    if os.path.commonpath([save_dir_abs, dest_abs]) != save_dir_abs:
        raise ValueError(f"SAVE_DIR 이탈 감지: {dest_abs}")
    return dest_abs


# ── 이어받기 판정 ─────────────────────────────────────────────────────────────


def already_downloaded(path: str) -> bool:
    """이미 받아둔 정상 zip이면 True.

    1MB 미만이면 곧바로 깨진 파일로 간주(빠른 사전 컷)하고, 그렇지 않으면
    실제로 zip을 열어 testzip()까지 통과해야 "완료"로 인정한다. 잘린 zip이
    크기만 그럴듯해서 영구 스킵되는 걸 막기 위함.
    """
    if not os.path.exists(path):
        return False
    if os.path.getsize(path) < MIN_VALID_BYTES:
        return False
    return _zip_is_valid(path)


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
        items, excluded = fetch_history_list()
    except Exception as e:
        print(f"목록 조회 실패: {e}", flush=True)
        return 1

    if not items and not excluded:
        print("파일을 하나도 찾지 못했습니다. 포털 응답 형식이 바뀌었을 수 있습니다.", flush=True)
        return 1

    total_found = len(items) + len(excluded)
    print(
        f"발견 {total_found}개 = 분기 {len(items)}개 + 제외 {len(excluded)}개",
        flush=True,
    )
    if excluded:
        print("제외된 항목(분기 패턴 _YYYYMMDD 불일치 — 사람이 판정 필요):", flush=True)
        for name in excluded:
            print(f"  - {name}", flush=True)

    if not items:
        print("분기 파일이 없어 다운로드할 대상이 없습니다.", flush=True)
        return 1

    if limit is not None:
        items = items[:limit]
        print(f"--limit {limit} → 앞에서 {len(items)}개만 처리", flush=True)

    total_count = len(items)
    ok = skipped = failed = 0
    total_bytes = 0
    consecutive_fail = 0

    for i, item in enumerate(items, start=1):
        name = item["name"]
        safe_name = sanitize_filename(name)
        try:
            dest = resolve_dest_path(SAVE_DIR, safe_name)
        except ValueError as e:
            failed += 1
            print(f"[{i}/{total_count}] {name} — 경로 안전성 위반으로 건너뜀: {e}", flush=True)
            continue

        tag = f"[{i}/{total_count}] {safe_name}"

        if already_downloaded(dest):
            size_mb = os.path.getsize(dest) / 1024 / 1024
            skipped += 1
            total_bytes += os.path.getsize(dest)
            print(f"{tag} — 스킵(이미 있음, {size_mb:.1f}MB)", flush=True)
            continue

        started = time.time()
        try:
            written = _download_one(item, dest)
        except Exception as e:
            failed += 1
            consecutive_fail += 1
            elapsed = time.time() - started
            print(f"{tag} — 실패 ({elapsed:.1f}초, {RETRY_COUNT}회 재시도 소진): {e}", flush=True)
            # 조각 파일이 남았으면 치운다
            part = dest + ".part"
            if os.path.exists(part):
                try:
                    os.remove(part)
                except OSError:
                    pass
            if consecutive_fail >= MAX_CONSECUTIVE_FAIL:
                print(
                    f"연속 {consecutive_fail}개 파일 실패 — 다운로드 제한이 걸린 것으로 보고 중단합니다.",
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

    # 연속 실패로 루프가 중단(break)되면 남은 항목은 시도조차 안 된 채 끝난다 —
    # ok+skipped+failed만 보면 이 "미시도" 항목이 조용히 사라져 보이므로 명시한다.
    not_attempted = total_count - (ok + skipped + failed)
    print("", flush=True)
    print("=" * 60, flush=True)
    print(
        f"요약: 성공 {ok} / 스킵 {skipped} / 실패 {failed} / 미시도 {not_attempted}  "
        f"(대상 {total_count}개)",
        flush=True,
    )
    print(f"총 용량: {total_bytes / 1024 / 1024 / 1024:.2f}GB", flush=True)
    print(f"저장 위치: {SAVE_DIR}", flush=True)
    print("=" * 60, flush=True)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
