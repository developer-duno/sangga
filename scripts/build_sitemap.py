# -*- coding: utf-8 -*-
"""
사이트맵 굽기 — 건물마다 검색에 따로 나오게(결정 0037 · 👤 결정 ② 이름 + 호실 정보 있는 건물)
+ 구 입구 허브 목록 파일(결정 0043 — 같은 대상 목록을 구마다 나눠 굽는다).

    python scripts/build_sitemap.py --dry-run   # DB 를 읽고 개수·파일 수만 출력(쓰기 0)
    python scripts/build_sitemap.py             # public/ 에 사이트맵·허브 파일을 굽는다 → 커밋

만드는 것(전부 public/ · LF · 결정적 — 같은 DB 면 같은 바이트):
  - sitemap-home.xml          첫 화면 주소 하나(lastmod 없음)
  - sitemap-hubs.xml          구 입구 허브 주소(`?sgg=<5자리>` · 허브 파일이 있는 구만 · 결정 0043)
  - sitemap-buildings-N.xml   건물 주소(N = 1, 2, … · 파일당 ≤ 50,000 — 구글 상한)
  - sitemap.xml               색인(sitemapindex) — home 먼저, 허브, 건물 파일 차례대로, 절대 주소
  - hub/<sgg>.json            구마다 허브에 실을 건물의 **재료**(결정 0043) — 서버 조각 `api/hub.ts` 가
                              요청 때 읽어 글을 만든다(요청 때 DB 0). 열린 구이고 대상 건물이 1동 이상인 구만.

언제 돌리나: 건축물대장·호실을 다시 적재한 뒤 한 번(post_load.py 다음) → 커밋 → 배포 →
  `python scripts/indexnow_ping.py`(빙·네이버) · 구글은 서치콘솔이 sitemap.xml 을 다시 읽는다.

⛔ 건물 주소 꼴은 화면이 쓰는 `?sgg=<pnu 앞 5자리>&bld=<id>` 그대로(👤 결정 ④) — XML 안에서 `&` 는 `&amp;`.
⛔ lastmod 를 적지 않는다 — 건물마다 정확한 수정일이 없다(구글: 정확할 때만).
⛔ 대상 = 맨 위 상수 TARGET_WHERE(이름(글자 하나 이상 · 👤 2026-10-19) + 층 행 + 비주거 호실 · 👤 2026-10-09 13,324동) — 얇은 페이지 대량 생성 금지.
   대상 밖(이름은 있으나 비주거 층 없음)은 함수가 noindex 를 단다(src/lib/buildingHead.ts 같은 정규식).
   허브에 싣는 건물 = 이 대상 그대로(사이트맵 건물 = 허브 건물 · 열린 구 밖이면 허브에서만 빠지고 개수를 알린다).
⛔ 허브 파일에는 **재료만** 담는다(뷰와 같은 칸 · `list_parcel_buildings` 결과 그대로) — 이름·동 구분 글은
   TS(`src/lib/hubHead.ts` → buildingHead.ts 의 `dongSuffix`)가 만든다. 파이썬에 그 판정을 다시 쓰지 않는다.
⛔ SQL 에 한글이 있어 psql -c 가 아니라 UTF-8 임시 파일(-f)로 보낸다 — -c 인자는 윈도우에서 cp949 로 넘어간다.
⚠️ 쓰기 전 옛 sitemap-buildings-*.xml · hub/*.json 은 지운다(줄어들면 남은 옛 파일이 색인 밖에 떠돈다).
"""

import argparse
import io
import json
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

# ★ 사이트맵에 싣는 건물의 조건 — 여기 셋만 고치면 된다(👤 2026-10-09 19:1x 재결정 — 13,324동).
#   이름 있음(글자 하나 이상 — 아래 NAME_LETTER_RE) + 층 행(v_building_floor_stack) 있음(층 행 0 이면 함수가 404) + 비주거 호실이 하나라도 있음.
#   ⛔ RESIDENTIAL_RE 는 src/lib/buildingHead.ts 의 RESIDENTIAL_RE 와 글자까지 같아야 한다
#      (tests/test_build_sitemap.py 가 대조 — 함수는 그 정규식으로 대상 밖 건물에 noindex 를 단다).
#   ⛔ 한글이 들어 있어 psql -c 로 못 보낸다(윈도우가 인자를 cp949 로 넘긴다) → fetch_rows 는 UTF-8 파일(-f).
RESIDENTIAL_RE = (
    "(주택|주거|아파트|다세대|연립|기숙사|주차|기계|전기|계단|승강|옥탑|부속|창고|관리|경비|대피|"
    "물탱크|펌프|발전|보일러|쓰레기|분리수거)"
)
# 👤 2026-10-27 — 단지 공용 공간·유치원·어린이집·노인시설만 있는 건물도 검색에서 뺀다(화면은 그대로) ·
#   단 이름에 '상가'가 든 건물은 남긴다(단지 안 상가동이 대장에 '부대시설'로만 적힌 일 — 아남아파트상가동 등).
#   ⛔ 두 상수도 src/lib/buildingHead.ts 의 AMENITY_RE·SHOP_NAME_RE 와 글자까지 같아야 한다(tests/test_build_sitemap.py 대조).
AMENITY_RE = "(부대|복리|마을공동|화장실|유치원|어린이집|보육|노인)"
SHOP_NAME_RE = "(상가)"
# 이름에 글자(한글 음절·자모 · 영문 · 한자)가 하나 이상 — 「.」「1」「---------」 같은 이름은 사이트맵·허브에서 뺀다
#   (👤 2026-10-19 — 구글에 「. — 강남구 …」 같은 제목이 안 나가게 · 그 건물의 화면·첫 HTML·noindex 규칙은 그대로).
#   ⓘ 범위를 `\uXXXX` 로 적는다(PostgreSQL 정규식·파이썬 re 둘 다 같은 뜻 — 소스에 드문 글자를 직접 쓰지 않는다).
#   가-힣 · ㄱ-ㅣ(호환 자모) · A-Za-z · 한자(확장 A · 기본 · 호환).
NAME_LETTER_RE = r"[\uac00-\ud7a3\u3131-\u3163A-Za-z\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
TARGET_WHERE = (
    "b.display_nm is not null "
    "and b.display_nm ~ '" + NAME_LETTER_RE + "' "
    "and exists (select 1 from v_building_floor_stack s where s.bld_id = b.bld_id) "
    "and exists (select 1 from unit u where u.bld_id = b.bld_id "
    "and u.floor_use is not null and u.floor_use !~ '" + RESIDENTIAL_RE + "' "
    "and (u.floor_use !~ '" + AMENITY_RE + "' or b.display_nm ~ '" + SHOP_NAME_RE + "'))"
)

ROOT = os.path.dirname(SCRIPTS_DIR)
PUBLIC_DIR = os.path.join(ROOT, "public")

SITE = "https://sangga-one.vercel.app/"
CHUNK_SIZE = 50000  # 구글 사이트맵 파일당 상한
HOME_FILE = "sitemap-home.xml"
HUBS_FILE = "sitemap-hubs.xml"
INDEX_FILE = "sitemap.xml"
BUILDING_FILE = "sitemap-buildings-{}.xml"
BUILDING_FILE_RE = re.compile(r"^sitemap-buildings-(\d+)\.xml$")
HUB_DIR = "hub"
HUB_FILE_RE = re.compile(r"^(\d{5})\.json$")
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

BLD_RE = re.compile(r"^\d{19}_\d{1,32}$")  # src/lib/urlState.ts 의 BLD_RE 와 같다
PNU_RE = re.compile(r"^\d{19}$")
SGG_RE = re.compile(r"^\d{5}$")
SIDO_RE = re.compile(r"^\d{2}$")

# 대상 건물(뷰 v_floor_stack 과 같은 재료 칸) + 열린 구 목록을 **한 번의 질의**로 읽는다(대상 고르기가 찬 캐시 약 10분).
#   - 건물 줄: bld_nm = building.display_nm(뷰 bld_nm 과 같은 칸) · road_addr = parcel.road_addr(뷰와 같은 칸) ·
#     bld_cnt = 같은 땅 동 수(뷰 bld_cnt_in_pnu 와 같은 셈) · sib = 같은 땅에 2동 이상일 때만
#     list_parcel_buildings(pnu) 의 (bld_id, bld_nm, dong_nm) 을 함수 차례 그대로(서버 조각이 부르는 그 함수 · 새 함수 정의 0).
#   - 구 줄: mv_open_sigungu(화면 지역 고르기의 진실) 의 시·도 코드·시군구 코드·이름.
#   ⛔ jsonb 로 낸다 — json_agg 의 글은 원소 사이에 줄바꿈을 넣어 한 줄 = 한 행이 깨진다.
TARGET_SQL = (
    "with t as (select b.bld_id, b.pnu, b.display_nm from building b where " + TARGET_WHERE + "), "
    "c as (select u.pnu, (select count(*)::int from building b2 where b2.pnu = u.pnu) as n "
    "from (select distinct pnu from t) u), "
    "sib as (select m.pnu, jsonb_agg(jsonb_build_object('bld_id', l.bld_id, 'bld_nm', l.bld_nm, "
    "'dong_nm', l.dong_nm) order by l.ord) as rows "
    "from (select pnu from c where c.n > 1) m cross join lateral list_parcel_buildings(m.pnu) with ordinality "
    "as l(bld_id, bld_nm, dong_nm, total_area_m2, floor_cnt, min_floor, max_floor, has_roof, ord) "
    "group by m.pnu) "
    "select jsonb_build_object('k', 'b', 'bld_id', t.bld_id, 'pnu', t.pnu, 'bld_nm', t.display_nm, "
    "'road_addr', p.road_addr, 'bld_cnt', c.n, 'sib', sib.rows)::text "
    "from t join c on c.pnu = t.pnu left join parcel p on p.pnu = t.pnu left join sib on sib.pnu = t.pnu "
    "union all "
    "select jsonb_build_object('k', 'g', 'sgg', m.sigungu_code, 'sido', m.sido_code, 'nm', m.sigungu_nm)::text "
    "from mv_open_sigungu m"
)


def building_loc(bld_id, pnu):
    """건물의 정식 주소(이스케이프 전). 꼴이 틀리면 ValueError — 틀린 주소를 사이트맵에 싣지 않는다."""
    if not BLD_RE.match(bld_id or ""):
        raise ValueError("건물 번호 꼴이 아님: {!r}".format(bld_id))
    if not PNU_RE.match(pnu or ""):
        raise ValueError("필지 번호 꼴이 아님: {!r}".format(pnu))
    return "{}?sgg={}&bld={}".format(SITE, pnu[:5], bld_id)


def hub_loc(sgg):
    """구 입구 허브의 정식 주소(결정 0043 — 지금 구 입구 주소 그대로)."""
    if not SGG_RE.match(sgg or ""):
        raise ValueError("시군구 코드 꼴이 아님: {!r}".format(sgg))
    return "{}?sgg={}".format(SITE, sgg)


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


def build_files(rows, hub_sggs=()):
    """(bld_id, pnu) 목록 + 허브 시군구 코드 → {파일 이름: 내용}. 건물은 bld_id 차례, 허브는 코드 차례(결정적).
    허브가 하나도 없으면 sitemap-hubs.xml 을 만들지 않는다(빈 urlset 을 색인에 싣지 않는다)."""
    locs = [building_loc(b, p) for b, p in sorted(rows)]
    files = {HOME_FILE: render_urlset([SITE])}
    names = [HOME_FILE]
    hubs = sorted(hub_sggs)
    if hubs:
        files[HUBS_FILE] = render_urlset([hub_loc(s) for s in hubs])
        names.append(HUBS_FILE)
    for i, part in enumerate(chunk(locs), start=1):
        name = BUILDING_FILE.format(i)
        files[name] = render_urlset(part)
        names.append(name)
    files[INDEX_FILE] = render_index(names)
    return files


def _opt_str(v):
    return v is None or isinstance(v, str)


def build_hubs(buildings, gus):
    """대상 건물 재료 + 열린 구 목록 → ({sgg: 허브 dict}, 열린 구 밖이라 허브에서 빠진 건물 수).

    허브 dict = {sgg, sido_code, sigungu_nm, buildings: [{bld_id, pnu, bld_nm, road_addr, bld_cnt}] (bld_id 차례),
                 parcels: {pnu: [{bld_id, bld_nm, dong_nm}] (함수 차례 그대로)}} — 같은 땅 2동 이상인 땅만 parcels 에.
    대상 건물이 1동 이상인 열린 구만 낸다. 꼴이 틀리면 ValueError(틀린 재료를 굽지 않는다)."""
    open_gu = {}
    for g in gus:
        sgg, sido, nm = g.get("sgg"), g.get("sido"), g.get("nm")
        if not SGG_RE.match(sgg or "") or not SIDO_RE.match(sido or "") or sgg[:2] != sido:
            raise ValueError("열린 구 줄 꼴이 아님: {!r}".format(g))
        if not isinstance(nm, str) or not nm.strip():
            raise ValueError("시군구 이름이 비었음: {!r}".format(g))
        open_gu[sgg] = (sido, nm.strip())
    hubs = {}
    outside = 0
    for b in sorted(buildings, key=lambda x: x["bld_id"]):
        building_loc(b["bld_id"], b["pnu"])  # 꼴 확인(사이트맵과 같은 관문)
        if not (_opt_str(b.get("bld_nm")) and _opt_str(b.get("road_addr"))):
            raise ValueError("이름·도로명 칸이 글이 아님: {!r}".format(b))
        cnt = b.get("bld_cnt")
        if not isinstance(cnt, int) or cnt < 1:
            raise ValueError("같은 땅 동 수가 1 이상 정수가 아님: {!r}".format(b))
        sgg = b["pnu"][:5]
        if sgg not in open_gu:
            outside += 1
            continue
        sido, nm = open_gu[sgg]
        hub = hubs.setdefault(sgg, {"sgg": sgg, "sido_code": sido, "sigungu_nm": nm, "buildings": [], "parcels": {}})
        hub["buildings"].append({
            "bld_id": b["bld_id"], "pnu": b["pnu"], "bld_nm": b.get("bld_nm"),
            "road_addr": b.get("road_addr"), "bld_cnt": cnt,
        })
        sib = b.get("sib")
        if cnt > 1 and sib is not None and b["pnu"] not in hub["parcels"]:
            if not isinstance(sib, list):
                raise ValueError("같은 땅 동 목록이 배열이 아님: {!r}".format(b))
            rows = []
            for s in sib:
                if not (isinstance(s, dict) and BLD_RE.match(s.get("bld_id") or "")
                        and _opt_str(s.get("bld_nm")) and _opt_str(s.get("dong_nm"))):
                    raise ValueError("같은 땅 동 줄 꼴이 아님: {!r}".format(s))
                rows.append({"bld_id": s["bld_id"], "bld_nm": s.get("bld_nm"), "dong_nm": s.get("dong_nm")})
            hub["parcels"][b["pnu"]] = rows
    return hubs, outside


def render_hub(hub):
    """허브 dict → JSON 글(키 정렬 · 공백 없음 · 한글 그대로 · 끝 LF — 같은 입력 = 같은 바이트)."""
    return json.dumps(hub, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def build_hub_files(hubs):
    """{sgg: 허브 dict} → {"hub/<sgg>.json": 내용}."""
    return {"{}/{}.json".format(HUB_DIR, sgg): render_hub(hubs[sgg]) for sgg in sorted(hubs)}


def parse_rows(out):
    """psql -tA 출력(한 줄에 jsonb 하나) → (건물 줄 목록, 구 줄 목록). 빈 줄은 버린다."""
    buildings, gus = [], []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except ValueError:
            raise ValueError("예상 밖의 줄: {!r}".format(ln[:200]))
        kind = obj.get("k") if isinstance(obj, dict) else None
        if kind == "b":
            buildings.append(obj)
        elif kind == "g":
            gus.append(obj)
        else:
            raise ValueError("예상 밖의 줄: {!r}".format(ln[:200]))
    return buildings, gus


def fetch_rows():
    """DB 에서 대상 건물·열린 구를 읽는다(읽기만). 접속은 post_load.query_one 과 같고, SQL 은 dbx.run_sql 처럼
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
            # -q 는 SET 줄을 출력에 안 남긴다(parse_rows 는 jsonb 줄만 받는다).
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


def existing_hub_files(public_dir):
    """public/hub/ 의 <5자리>.json 이름(코드 차례). 폴더가 없으면 빈 목록."""
    d = os.path.join(public_dir, HUB_DIR)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if HUB_FILE_RE.match(f))


def write_files(files, public_dir, hub_files=None):
    """옛 건물 파일·옛 허브 파일을 지우고 새로 쓴다(LF). hub_files 가 None 이면 허브 폴더·허브 사이트맵은 건드리지 않는다.
    허브가 0개인 굽기면(색인에 허브 사이트맵이 안 실린다) 옛 sitemap-hubs.xml 도 지운다 — 색인 밖에 떠돌지 않게."""
    for old in existing_building_files(public_dir):
        os.remove(os.path.join(public_dir, old))
    if hub_files is not None:
        for old in existing_hub_files(public_dir):
            os.remove(os.path.join(public_dir, HUB_DIR, old))
        if hub_files:
            os.makedirs(os.path.join(public_dir, HUB_DIR), exist_ok=True)
        stale = os.path.join(public_dir, HUBS_FILE)
        if HUBS_FILE not in files and os.path.isfile(stale):
            os.remove(stale)
    merged = dict(files)
    merged.update(hub_files or {})
    for name, text in merged.items():
        with io.open(os.path.join(public_dir, *name.split("/")), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description="사이트맵·구 허브 굽기(결정 0037·0043)")
    ap.add_argument("--dry-run", action="store_true", help="DB 를 읽고 개수·파일 수만 출력(쓰기 0)")
    a = ap.parse_args(argv)

    buildings, gus = fetch_rows()
    rows = [(b["bld_id"], b["pnu"]) for b in buildings]
    hubs, outside = build_hubs(buildings, gus)
    files = build_files(rows, hubs.keys())
    hub_files = build_hub_files(hubs)
    n_files = len([f for f in files if BUILDING_FILE_RE.match(f)])
    size = sum(len(t.encode("utf-8")) for t in files.values())
    hub_size = sum(len(t.encode("utf-8")) for t in hub_files.values())
    print("대상 건물 {:,}동 → 건물 파일 {}개 · 전체 {:,}바이트".format(len(rows), n_files, size))
    print("구 허브 {}개 · 허브 파일 합 {:,}바이트(가장 큰 것 {:,}바이트)".format(
        len(hub_files), hub_size, max([len(t.encode("utf-8")) for t in hub_files.values()] or [0])))
    if outside:
        print("[주의] 열린 구 밖 대상 건물 {:,}동 — 사이트맵에는 있고 허브에는 없습니다".format(outside))
    if a.dry_run:
        print("(미리보기 — 아무것도 쓰지 않았습니다)")
        return 0
    write_files(files, PUBLIC_DIR, hub_files)
    print("썼습니다: {} · hub/*.json {}개".format(", ".join(sorted(files)), len(hub_files)))
    print("다음: 커밋 → 배포 → python scripts/indexnow_ping.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
