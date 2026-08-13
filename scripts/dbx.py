# -*- coding: utf-8 -*-
"""SANGGA_DATABASE_URL 로 SQL을 실행한다 (psql 감싸기).

왜 필요한가
-----------
Supabase REST(PostgREST)로는 **DDL·EXPLAIN·ANALYZE 를 못 한다.** 그래서 마이그레이션과
성능 진단을 매번 사람이 대시보드 SQL Editor 에 붙여넣어야 했다. 접속 문자열만 있으면
전부 자동화된다.

⚠️ 비밀번호가 **명령줄에 노출되지 않게** 한다 — psql 에 URI 를 인자로 주면 프로세스
   목록(`ps`)과 셸 기록에 남는다. 여기서는 `PGPASSWORD` 환경변수로 넘기고 나머지
   접속 정보만 인자로 준다(libpq 공식 방식).

사용
----
    python scripts/dbx.py -c "select count(*) from building"
    python scripts/dbx.py -f supabase/migrations/2026-08-11d_widen_bcr.sql
    python scripts/dbx.py --explain "select * from search_buildings('명동', 3)"
    python scripts/dbx.py --check          # 연결만 확인 (비밀번호 출력 안 함)
"""

import argparse
import io
import os
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parts():
    """SANGGA_DATABASE_URL 을 psql 인자와 PGPASSWORD 로 쪼갠다."""
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    url = os.environ.get("SANGGA_DATABASE_URL")
    if not url:
        raise SystemExit(
            "SANGGA_DATABASE_URL 이 .env 에 없습니다.\n"
            "  Supabase 대시보드 → 상단 Connect → Session pooler 의 URI 를 넣으세요.\n"
            "  (Direct connection 은 IPv6 전용이라 IPv4 환경에서 안 될 수 있습니다.)")
    u = urlparse(url)
    if not u.hostname or not u.username:
        raise SystemExit("SANGGA_DATABASE_URL 형식이 URI 가 아닙니다.")
    args = ["-h", u.hostname, "-p", str(u.port or 5432),
            "-U", unquote(u.username), "-d", (u.path or "/postgres").lstrip("/")]
    return args, unquote(u.password or "")


def run_sql(sql, quiet=False):
    """SQL 문자열을 **UTF-8 임시 파일**로 넘겨 실행한다.

    ⚠️ `psql -c "<한글 SQL>"` 로 넘기면 안 된다 — Windows 에서 인자가 콘솔 코드페이지
    (CP949)로 인코딩돼 `invalid byte sequence for encoding "UTF8"` 로 죽는다
    (2026-08-11 실제로 당함). 파일 경유는 인코딩을 우리가 정한다.
    """
    fd, path = tempfile.mkstemp(suffix=".sql", prefix="dbx_")
    os.close(fd)
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(sql)
        return run_file(path, quiet=quiet)
    finally:
        os.unlink(path)


def run_file(path, quiet=False):
    args, password = parts()
    env = dict(os.environ)
    env["PGPASSWORD"] = password          # ⚠️ 명령줄이 아니라 환경변수로
    env["PGCLIENTENCODING"] = "UTF8"
    cmd = ["psql"] + args + ["-v", "ON_ERROR_STOP=1", "-f", path]
    if quiet:
        cmd += ["-q"]
    return subprocess.call(cmd, env=env)


def main(argv=None):
    p = argparse.ArgumentParser(description="SANGGA DB 에 SQL 실행 (psql 감싸기)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("-c", "--command", help="실행할 SQL 한 줄")
    g.add_argument("-f", "--file", help="실행할 .sql 파일")
    g.add_argument("--explain", help="EXPLAIN (ANALYZE, BUFFERS) 로 감싸 실행")
    g.add_argument("--check", action="store_true", help="연결만 확인")
    a = p.parse_args(argv)

    if a.check:
        return run_sql("select current_database() as db, version();", quiet=True)
    if a.command:
        return run_sql(a.command)
    if a.file:
        if not os.path.exists(a.file):
            raise SystemExit("파일이 없습니다: {}".format(a.file))
        return run_file(a.file)
    # EXPLAIN 은 오래 걸릴 수 있다 — 기본 statement_timeout(3s)을 넘기지 않게 풀어준다.
    return run_sql("set statement_timeout = '300s';\n"
                   "explain (analyze, buffers) {};".format(a.explain))


if __name__ == "__main__":
    sys.exit(main())
