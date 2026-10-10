# -*- coding: utf-8 -*-
"""
사이트맵 굽기 — 건물마다 검색에 따로 나오게(결정 0037 · 👤 결정 ② 이름 + 호실 정보 있는 건물).

    python scripts/build_sitemap.py --dry-run   # DB 를 읽고 개수·파일 수만 출력(쓰기 0)
    python scripts/build_sitemap.py             # public/ 에 사이트맵을 굽는다 → 커밋

만드는 것(전부 public/ · LF · 결정적 — 같은 DB 면 같은 바이트):
  - sitemap-home.xml          첫 화면 주소 하나(lastmod 없음)
  - sitemap-buildings-N.xml   건물 주소(N = 1, 2, … · 파일당 ≤ 50,000 — 구글 상한)
  - sitemap.xml               색인(sitemapindex) — home 먼저, 건물 파일 차례대로, 절대 주소

언제 돌리나: 건축물대장·호실을 다시 적재한 뒤 한 번(post_load.py 다음) → 커밋 → 배포 →
  `python scripts/indexnow_ping.py`(빙·네이버) · 구글은 서치콘솔이 sitemap.xml 을 다시 읽는다.

⛔ 건물 주소 꼴은 화면이 쓰는 `?sgg=<pnu 앞 5자리>&bld=<id>` 그대로(👤 결정 ④) — XML 안에서 `&` 는 `&amp;`.
⛔ lastmod 를 적지 않는다 — 건물마다 정확한 수정일이 없다(구글: 정확할 때만).
⛔ 대상 = 맨 위 상수 TARGET_WHERE(이름 + 층 행 + 비주거 호실 · 👤 2026-10-09 13,324동) — 얇은 페이지 대량 생성 금지.
   대상 밖(이름은 있으나 비주거 층 없음)은 함수가 noindex 를 단다(src/lib/buildingHead.ts 같은 정규식).
⛔ SQL 에 한글이 있어 psql -c 가 아니라 UTF-8 임시 파일(-f)로 보낸다 — -c 인자는 윈도우에서 cp949 로 넘어간다.
⚠️ 쓰기 전 옛 sitemap-buildings-*.xml 은 지운다(건물이 줄어 파일 수가 줄면 남은 옛 파일이 색인 밖에 떠돈다).
"""

import argparse
import io
import os
import re
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import dbx  # noqa: E402  (같은 폴더의 접속 정보 해석기를 그대로 쓴다 — post_load.py 와 같은 길)

# ★ 사이트맵에 싣는 건물의 조건 — 여기 둘만 고치면 된다(👤 2026-10-09 19:1x 재결정 — 13,324동).
#   이름 있음 + 층 행(v_building_floor_stack) 있음(층 행 0 이면 함수가 404) + 비주거 호실이 하나라도 있음.
#   ⛔ RESIDENTIAL_RE 는 src/lib/buildingHead.ts 의 RESIDENTIAL_RE 와 글자까지 같아야 한다
#      (tests/test_build_sitemap.py 가 대조 — 함수는 그 정규식으로 대상 밖 건물에 noindex 를 단다).
#   ⛔ 한글이 들어 있어 psql -c 로 못 보낸다(윈도우가 인자를 cp949 로 넘긴다) → fetch_rows 는 UTF-8 파일(-f).
RESIDENTIAL_RE = (
    "(주택|주거|아파트|다세대|연립|기숙사|주차|기계|전기|계단|승강|옥탑|부속|창고|관리|경비|대피|"
    "물탱크|펌프|발전|보일러|쓰레기|분리수거)"
)
TARGET_WHERE = (
    "b.display_nm is not null "
    "and exists (select 1 from v_building_floor_stack s where s.bld_id = b.bld_id) "
    "and exists (select 1 from unit u where u.bld_id = b.bld_id "
    "and u.floor_use is not null and u.floor_use !~ '" + RESIDENTIAL_RE + "')"
)

ROOT = os.path.dirname(SCRIPTS_DIR)
PUBLIC_DIR = os.path.join(ROOT, "public")

SITE = "https://sangga-one.vercel.app/"
CHUNK_SIZE = 50000  # 구글 사이트맵 파일당 상한
HOME_FILE = "sitemap-home.xml"
INDEX_FILE = "sitemap.xml"
BUILDING_FILE = "sitemap-buildings-{}.xml"
BUILDING_FILE_RE = re.compile(r"^sitemap-buildings-(\d+)\.xml$")
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

BLD_RE = re.compile(r"^\d{19}_\d{1,32}$")  # src/lib/urlState.ts 의 BLD_RE 와 같다
PNU_RE = re.compile(r"^\d{19}$")

TARGET_SQL = "select b.bld_id, b.pnu from building b where " + TARGET_WHERE + " order by b.bld_id"


def building_loc(bld_id, pnu):
    """건물의 정식 주소(이스케이프 전). 꼴이 틀리면 ValueError — 틀린 주소를 사이트맵에 싣지 않는다."""
    if not BLD_RE.match(bld_id or ""):
        raise ValueError("건물 번호 꼴이 아님: {!r}".format(bld_id))
    if not PNU_RE.match(pnu or ""):
        raise ValueError("필지 번호 꼴이 아님: {!r}".format(pnu))
    return "{}?sgg={}&bld={}".format(SITE, pnu[:5], bld_id)


def chunk(items, size=CHUNK_SIZE):
    """목록을 size 개씩 자른다(빈 목록이면 빈 목록)."""
    return [items[i:i + size] for i in range(0, len(items), size)]


def render_urlset(locs):
    """주소 목록 → urlset XML(한 줄에 주소 하나 · lastmod 없음)."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="{}">'.format(NS)]
    lines += ["  <url><loc>{}</loc></url>".format(escape(loc)) for loc in locs]
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def render_index(files):
    """파일 이름 목록 → sitemapindex XML(절대 주소 · 준 차례 그대로)."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<sitemapindex xmlns="{}">'.format(NS)]
    lines += ["  <sitemap><loc>{}</loc></sitemap>".format(escape(SITE + f)) for f in files]
    lines.append("</sitemapindex>")
    return "\n".join(lines) + "\n"


def build_files(rows):
    """(bld_id, pnu) 목록 → {파일 이름: 내용}. 건물은 bld_id 차례로 정렬한다(결정적)."""
    locs = [building_loc(b, p) for b, p in sorted(rows)]
    files = {HOME_FILE: render_urlset([SITE])}
    names = []
    for i, part in enumerate(chunk(locs), start=1):
        name = BUILDING_FILE.format(i)
        files[name] = render_urlset(part)
        names.append(name)
    files[INDEX_FILE] = render_index([HOME_FILE] + names)
    return files


def parse_rows(out):
    """psql -tA 출력(`bld_id|pnu` 줄들) → [(bld_id, pnu)]. 빈 줄은 버린다."""
    rows = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split("|")
        if len(parts) != 2:
            raise ValueError("예상 밖의 줄: {!r}".format(ln))
        rows.append((parts[0], parts[1]))
    return rows


def fetch_rows():
    """DB 에서 대상 건물을 읽는다(읽기만). 접속은 post_load.query_one 과 같고, SQL 은 dbx.run_sql 처럼
    UTF-8 임시 파일(-f)로 넘긴다 — 대상 조건에 한글 정규식이 있어 -c 로는 cp949 로 깨진다."""
    args, password = dbx.parts()
    env = dict(os.environ)
    env["PGPASSWORD"] = password  # ⚠️ 명령줄 노출 금지
    env["PGCLIENTENCODING"] = "UTF8"
    fd, path = tempfile.mkstemp(suffix=".sql", prefix="sitemap_")
    os.close(fd)
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            # 찬 캐시에서 대상 고르기가 기본 제한 2분을 넘는다(2026-10-10 실측) — 이 접속에서만 15분.
            # -q 는 SET 줄을 출력에 안 남긴다(parse_rows 는 'bld|pnu' 줄만 받는다).
            f.write("set statement_timeout = '900s';\n" + TARGET_SQL + ";\n")
        cmd = ["psql"] + args + ["-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-f", path]
        out = subprocess.check_output(cmd, env=env, stderr=subprocess.STDOUT)
    finally:
        os.unlink(path)
    return parse_rows(out.decode("utf-8", "replace"))


def existing_building_files(public_dir):
    """public/ 의 sitemap-buildings-N.xml 이름을 N 차례로(9 다음 10)."""
    found = [f for f in os.listdir(public_dir) if BUILDING_FILE_RE.match(f)]
    return sorted(found, key=lambda f: int(BUILDING_FILE_RE.match(f).group(1)))


def write_files(files, public_dir):
    """옛 건물 파일을 지우고 새로 쓴다(LF)."""
    for old in existing_building_files(public_dir):
        os.remove(os.path.join(public_dir, old))
    for name, text in files.items():
        with io.open(os.path.join(public_dir, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description="사이트맵 굽기(결정 0037)")
    ap.add_argument("--dry-run", action="store_true", help="DB 를 읽고 개수·파일 수만 출력(쓰기 0)")
    a = ap.parse_args(argv)

    rows = fetch_rows()
    files = build_files(rows)
    n_files = len(files) - 2
    size = sum(len(t.encode("utf-8")) for t in files.values())
    print("대상 건물 {:,}동 → 건물 파일 {}개 · 전체 {:,}바이트".format(len(rows), n_files, size))
    if a.dry_run:
        print("(미리보기 — 아무것도 쓰지 않았습니다)")
        return 0
    write_files(files, PUBLIC_DIR)
    print("썼습니다: {}".format(", ".join(sorted(files))))
    print("다음: 커밋 → 배포 → python scripts/indexnow_ping.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
