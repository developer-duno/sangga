# -*- coding: utf-8 -*-
"""
법정동코드 전체자료 적재 — 행정표준코드관리시스템(code.go.kr)

무엇을 하나:
  1. code.go.kr "법정동코드 전체자료" 다운로드 (zip, 폐지 코드 포함 전량, 키 불필요)
  2. zip 안의 txt(EUC-KR)를 파싱해 법정동코드/법정동명/폐지여부를 읽는다
  3. 법정동코드 자릿수 계층(상위 코드 행의 이름)으로 시도/시군구/읍면동/리 명을 파생시킨다
  4. Supabase(PostgREST)로 bjd_code 테이블에 배치 upsert (멱등 — 몇 번을 다시 돌려도 안전)

왜 API가 아니라 이 다운로드를 쓰나:
  data.go.kr에도 법정동코드 조회 API(StanReginCd)가 있지만 별도 활용신청·키 발급이
  필요하다. code.go.kr의 "전체자료 다운로드"는 로그인·키 없이 전량을 한 번에 받을 수
  있어 더 간단하고 안정적이다 (실측: 2026-08-07, 53,387행 = 존재 20,560 + 폐지 32,827,
  code.go.kr 목록 페이지에 표시된 "존재 20,560건"과 일치 확인).

프로토콜(실측 검증 완료, 브라우저 네트워크 탭으로 확인):
  POST https://www.code.go.kr/etc/codeFullDown.do
  Content-Type: application/x-www-form-urlencoded
  응답: zip 바이너리 (내부 txt 1개, EUC-KR, 탭 구분, 헤더 '법정동코드/법정동명/폐지여부')

이어받기(재실행 안전):
  이 스크립트는 전체를 한 번에 처리하는 작업이라(53,387행, API 호출 아님) 별도의
  collect_progress 이어받기가 필요 없다. 대신 upsert 자체가 멱등이라(Prefer:
  resolution=merge-duplicates, PK=bjd_code) 배치 중간에 실패해도 그냥 재실행하면
  이미 들어간 행은 덮어쓰기만 되고 중복은 생기지 않는다. 원본 zip도 이미 받아둔
  파일이 유효하면 재다운로드하지 않는다(already_downloaded).

사용법:
  python scripts/collectors/load_bjd_code.py            # 다운로드 + 적재
  python scripts/collectors/load_bjd_code.py --parse-only  # 다운로드+파싱만, DB 적재 생략
  python scripts/collectors/load_bjd_code.py --force-download  # 원본 zip 강제 재다운로드
"""

import datetime
import io
import os
import sys
import zipfile

import requests
from dotenv import load_dotenv

# ── 설정 ──────────────────────────────────────────────────────────────────────

DOWNLOAD_URL = "https://www.code.go.kr/etc/codeFullDown.do"
REFERER_URL = "https://www.code.go.kr/stdcode/regCodeL.do"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# 다운로드 폼(브라우저가 실제로 보내는 값을 그대로 재현. sido/sggu/umd/ri = '*'는 전국 전체)
DOWNLOAD_FORM = {
    "cPage": "1",
    "regionCd_pk": "",
    "chkWantCnt": "0",
    "reqSggCd": "",
    "reqUmdCd": "",
    "reqRiCd": "",
    "searchOk": "",
    "codeseId": "법정동코드",
    "pageSize": "10",
    "regionCd": "",
    "locataddNm": "",
    "sidoCd": "*",
    "sggCd": "*",
    "umdCd": "*",
    "riCd": "*",
    "disuseAt": "1",     # 폐지 코드도 포함
    "stdate": "",
    "enddate": "",
    "AllChkV": "AllChkV",
    "chkHigh": "1",
    "chkOrder": "1",
    "chkCrtDt": "1",
    "chkClsDt": "1",
    "chkLocatDt": "1",
    "chkLow": "1",
    "chkJumin": "1",
    "chkJijuk": "1",
}

ZIP_MAGIC = b"PK\x03\x04"
MIN_VALID_ZIP_BYTES = 100_000  # 정상 zip은 약 400KB. 이보다 작으면 깨진 응답으로 간주

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAVE_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "bjd")
ZIP_PATH = os.path.join(SAVE_DIR, "법정동코드_전체자료.zip")

BATCH_SIZE = 1000  # PostgREST 배치당 행 수
TIMEOUT_SEC = 120


# ── 1단계: 다운로드 ───────────────────────────────────────────────────────────


def already_downloaded(path: str) -> bool:
    """이미 받아둔 정상 zip이면 True (PK 헤더 + 최소 크기 + zip 무결성).

    형제 스크립트(download_sangkwon_history.py의 _zip_is_valid)와 같은 기준:
    testzip()으로 전체 항목의 CRC까지 확인해야, 크기만 그럴듯한 잘린 zip이
    "완료"로 영구 스킵되는 걸 막을 수 있다.
    """
    if not os.path.exists(path):
        return False
    if os.path.getsize(path) < MIN_VALID_ZIP_BYTES:
        return False
    with open(path, "rb") as f:
        if f.read(4) != ZIP_MAGIC:
            return False
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip() is None
    except (zipfile.BadZipFile, OSError):
        return False


def download_zip(dest_path: str) -> bytes:
    """code.go.kr에서 법정동코드 전체자료 zip을 받아 저장하고 바이트를 돌려준다."""
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": REFERER_URL,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    resp = requests.post(
        DOWNLOAD_URL, data=DOWNLOAD_FORM, headers=headers, timeout=TIMEOUT_SEC
    )
    resp.raise_for_status()
    content = resp.content
    if content[:4] != ZIP_MAGIC:
        raise RuntimeError(
            "응답이 zip이 아닙니다 (포털 안내/차단 페이지일 수 있음). "
            "첫 300바이트: " + content[:300].decode("utf-8", errors="replace")
        )

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp_path = dest_path + ".part"
    with open(tmp_path, "wb") as f:
        f.write(content)
    os.replace(tmp_path, dest_path)
    return content


def fetch_zip_bytes(force: bool = False) -> bytes:
    """이미 유효한 원본이 있으면 재사용, 없으면 새로 받는다."""
    if not force and already_downloaded(ZIP_PATH):
        with open(ZIP_PATH, "rb") as f:
            return f.read()
    return download_zip(ZIP_PATH)


# ── 2단계: 파싱 ───────────────────────────────────────────────────────────────


def _strip_prefix(full: "str | None", prefix: "str | None") -> "str | None":
    """full에서 'prefix '(공백 포함) 접두사를 잘라낸 나머지를 돌려준다.

    full이 없거나 prefix와 완전히 같으면(그 아래 단계가 없는 행) None.
    접두사가 안 맞으면(상위 코드 행과 이름이 어긋나는 원본 데이터 결함 —
    실측 2행: 폐지된 시흥군 계열) 원본을 그대로 돌려주는 대신 None.
    전체 주소 문자열을 하위 단계 이름이라고 단정하는 것도 추측이므로,
    판정 불가는 NULL로 남긴다(CLAUDE.md 절대 규칙과 같은 결).
    """
    if full is None:
        return None
    if full == prefix:
        return None
    if prefix and full.startswith(prefix + " "):
        return full[len(prefix) + 1:]
    return None


def _split_bjd_nm(bjd_code: str, code_to_name: dict) -> dict:
    """
    법정동코드 10자리의 자리별 의미(행정표준코드 규격)로 상위 코드 행의
    법정동명을 접두사 삼아 시도/시군구/읍면동/리 이름을 파생시킨다.

      시도   코드 = bjd_code[:2] + '00000000'
      시군구 코드 = bjd_code[:5] + '00000'
      읍면동 코드 = bjd_code[:8] + '00'

    공백 토큰 순서로 나누던 예전 방식은 두 가지 실측 사례에서 깨졌다(2026-08-07,
    3,634행 오매핑 확정):
      1) 시 아래 구가 있는 경우 — '경기도 용인시 처인구 포곡읍 삼계리'는
         토큰이 5개라 시군구/읍면동/리가 한 칸씩 밀린다(포곡읍이 읍면동이
         아니라 시군구 자리에, 삼계리를 포함한 나머지가 통째로 리에 들어감).
      2) 세종특별자치시처럼 시도 전용 코드 행 자체가 없는 경우 — '세종특별
         자치시'라는 이름이 시군구 코드 레벨 행(3611000000)에 바로 들어있어,
         토큰이 2개뿐인 '세종특별자치시 조치원읍'의 '조치원읍'이 시군구
         자리로 잘못 들어간다(실제로는 읍면동).

    코드 계층으로 상위 행을 직접 조회하면 두 경우 모두 자연스럽게 풀린다:
    세종은 시도 전용 코드(3600000000)가 아예 존재하지 않으므로, 시군구 코드
    행(3611000000='세종특별자치시')을 시도 이름으로 대신 쓴다.
    """
    sido_code = bjd_code[:2] + "00000000"
    sigungu_code10 = bjd_code[:5] + "00000"
    emd_code = bjd_code[:8] + "00"

    own_nm = code_to_name.get(bjd_code)
    sido_full = code_to_name.get(sido_code)
    sigungu_full = code_to_name.get(sigungu_code10)
    emd_full = code_to_name.get(emd_code)

    # 세종처럼 시도 전용 행이 없으면, 시도 정체성이 시군구 코드 레벨 행에
    # 직접 들어있다 — 그 행을 시도 이름으로 대신 쓴다.
    if sido_full is None:
        sido_full = sigungu_full
    if sido_full is None:
        sido_full = own_nm

    sido_nm = sido_full

    sigungu_nm = None
    if sigungu_full is not None and sigungu_full != sido_full:
        sigungu_nm = _strip_prefix(sigungu_full, sido_nm)

    base_for_emd = sigungu_full if sigungu_full is not None else sido_full
    emd_nm = None
    if emd_full is not None and emd_full != base_for_emd:
        emd_nm = _strip_prefix(emd_full, base_for_emd)

    base_for_ri = emd_full if emd_full is not None else base_for_emd
    ri_nm = None
    if bjd_code != emd_code and own_nm is not None:
        ri_nm = _strip_prefix(own_nm, base_for_ri)

    return {
        "sido_nm": sido_nm,
        "sigungu_nm": sigungu_nm,
        "emd_nm": emd_nm,
        "ri_nm": ri_nm,
    }


def parse_bjd_rows(zip_bytes: bytes) -> list:
    """zip 바이트를 받아 bjd_code 테이블 행(dict) 리스트로 돌려준다."""
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = zf.namelist()
    if not names:
        raise RuntimeError("zip 안에 파일이 없습니다.")
    raw = zf.read(names[0])
    # 프로토콜상 euc-kr 고정이지만(docstring 참고), 만약을 대비해 cp949로
    # 한 번 더 시도하고 그래도 안 되면 깨진 문자만 대체해 전체를 죽이지 않는다.
    try:
        text = raw.decode("euc-kr")
    except UnicodeDecodeError:
        try:
            text = raw.decode("cp949")
        except UnicodeDecodeError:
            text = raw.decode("cp949", errors="replace")

    lines = text.splitlines()
    if not lines:
        raise RuntimeError("txt 파일이 비어 있습니다.")

    header = lines[0].split("\t")
    expected_header = ["법정동코드", "법정동명", "폐지여부"]
    if [h.strip() for h in header] != expected_header:
        raise RuntimeError(
            "헤더 형식이 바뀌었습니다. 예상 {} / 실제 {}".format(expected_header, header)
        )

    parsed = []  # (bjd_code, bjd_nm, is_active) — 1차 통과: 코드/이름/존재여부만 추출
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        bjd_code, bjd_nm, disuse = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not bjd_code:
            continue
        parsed.append((bjd_code, bjd_nm, disuse == "존재"))

    # 시도/시군구/읍면동 파생에는 그 상위 코드 행의 이름이 필요하므로,
    # 전체를 한 번 더 조회 가능한 dict로 만든 뒤(2차 통과) 파생시킨다.
    code_to_name = {bjd_code: bjd_nm for bjd_code, bjd_nm, _ in parsed}

    rows = []
    for bjd_code, bjd_nm, is_active in parsed:
        row = {
            "bjd_code": bjd_code,
            "sigungu_code": bjd_code[:5],
            "bjd_nm": bjd_nm,
            "is_active": is_active,
        }
        row.update(_split_bjd_nm(bjd_code, code_to_name))
        rows.append(row)

    return rows


# ── 3단계: Supabase(PostgREST) 적재 ───────────────────────────────────────────


def get_supabase_config() -> tuple:
    """env에서 URL/서비스키를 읽는다. 값은 절대 print하지 않는다."""
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    url = os.environ.get("SANGGA_SUPABASE_URL")
    key = os.environ.get("SANGGA_SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SANGGA_SUPABASE_URL / SANGGA_SUPABASE_SERVICE_KEY가 .env에 없습니다."
        )
    return url.rstrip("/"), key


def table_exists(base_url: str, headers: dict) -> bool:
    r = requests.get(
        f"{base_url}/rest/v1/bjd_code?select=bjd_code&limit=1",
        headers=headers,
        timeout=30,
    )
    return r.status_code != 404


def upsert_rows(base_url: str, headers: dict, rows: list) -> int:
    """rows를 BATCH_SIZE 단위로 upsert. 실제로 보낸 총 행 수를 돌려준다.

    updated_at을 명시적으로 실어 보낸다 — PostgREST upsert(merge-duplicates)는
    JSON에 없는 컬럼을 SET 절에 넣지 않으므로, 컬럼 DEFAULT now()는 최초 INSERT
    에만 적용되고 재실행(UPDATE) 시에는 값이 안 갱신된다. 이 실행 전체에 같은
    시각(UTC 명시)을 써서 "이 배치가 언제 적재됐는지"가 일관되게 남는다.
    """
    upsert_headers = dict(headers)
    upsert_headers["Content-Type"] = "application/json"
    upsert_headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    sent = 0
    total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(rows), BATCH_SIZE):
        batch = [dict(row, updated_at=now_iso) for row in rows[i : i + BATCH_SIZE]]
        batch_no = i // BATCH_SIZE + 1
        r = requests.post(
            f"{base_url}/rest/v1/bjd_code",
            json=batch,
            headers=upsert_headers,
            timeout=TIMEOUT_SEC,
        )
        if r.status_code >= 300:
            raise RuntimeError(
                f"배치 {batch_no}/{total_batches} upsert 실패 "
                f"(HTTP {r.status_code}): {r.text[:500]}"
            )
        sent += len(batch)
        print(
            f"  [{batch_no}/{total_batches}] {len(batch)}행 upsert 완료 "
            f"(누적 {sent:,}/{len(rows):,})",
            flush=True,
        )
    return sent


# ── 메인 ──────────────────────────────────────────────────────────────────────


def main() -> int:
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    force_download = "--force-download" in sys.argv
    parse_only = "--parse-only" in sys.argv

    print("법정동코드 전체자료 다운로드 중...", flush=True)
    try:
        zip_bytes = fetch_zip_bytes(force=force_download)
    except Exception as e:
        print(f"[에러] 다운로드 실패: {e}", flush=True)
        return 1
    print(f"  원본 zip: {ZIP_PATH} ({len(zip_bytes) / 1024:.1f}KB)", flush=True)

    print("파싱 중...", flush=True)
    try:
        rows = parse_bjd_rows(zip_bytes)
    except Exception as e:
        print(f"[에러] 파싱 실패: {e}", flush=True)
        return 1
    active_cnt = sum(1 for r in rows if r["is_active"])
    print(
        f"  총 {len(rows):,}행 (존재 {active_cnt:,} / 폐지 {len(rows) - active_cnt:,})",
        flush=True,
    )

    if parse_only:
        print("--parse-only 지정 — DB 적재는 건너뜁니다.", flush=True)
        return 0

    print("Supabase 연결 확인 중...", flush=True)
    try:
        base_url, key = get_supabase_config()
    except RuntimeError as e:
        print(f"[에러] {e}", flush=True)
        return 1
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}

    if not table_exists(base_url, headers):
        print("", flush=True)
        print("=" * 78, flush=True)
        print("[안내] bjd_code 테이블이 아직 없습니다 (HTTP 404).", flush=True)
        print("Supabase 대시보드 → SQL Editor에서 supabase/schema.sql의", flush=True)
        print("'L0. bjd_code' 섹션을 실행한 뒤 이 스크립트를 다시 실행하세요.", flush=True)
        print("=" * 78, flush=True)
        return 2

    print(f"적재 시작 (배치 {BATCH_SIZE}행 단위)...", flush=True)
    try:
        sent = upsert_rows(base_url, headers, rows)
    except RuntimeError as e:
        print(f"[에러] {e}", flush=True)
        return 1

    print("", flush=True)
    print("=" * 60, flush=True)
    print(f"완료: 원본 {len(rows):,}행 -> 적재 {sent:,}행", flush=True)
    print("=" * 60, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
