# -*- coding: utf-8 -*-
"""scripts/collectors/load_seoul_subway.py 단위 테스트 (결정 0045 PR⑥ · 적재기 1:1).

  1. 정규화 · 묶음(600m 경계 599/601 · 세 역 사슬 · 다른 이름은 안 묶임)
  2. 짝표 — 호선 짝표 · 역 짝표 map/skip · 씨앗 파일 모양
  3. 관문 ⒜~⒡ 각각 걸림 + 양성 대조 · 중복 같은 값 → 하나 / 다른 값 → 멈춤 · float→int · INFO-200 봉투 건너뜀
  4. 파일 고르기(같은 달 두 날짜 → 최신 · `_2` 꼬리)
  5. build_sql 글자(lock_timeout 위치 · upsert · 달 지우기 → 사라진 역 검사 차례 · RAISE 글의 %) · dry-run 쓰기 0
  6. 같은 달 같은 역 두 원문 줄 → 두 행(메인 결정 ⑥-1)
  7. 실자료 전수(로컬 전용 · D:/tmp/sangga-wave3/pr6-prework/raw 가 없으면 건너뜀 — 수집기 꼴 이름으로 tmp 에 복사해 돌린다)
  8. 적재 SQL 로컬 PG 실행(PostgreSQL 이 있을 때만 · psql 로 \\copy 까지 · ⑥-2 의무) — 행 수 · has_ridership · 두 번 돌려도 같음 ·
     사라진 역이 참조되면 raise 가 **실제로** 난다(양성 대조 — 참조 없으면 지워진다)
"""

import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "scripts"), os.path.join(ROOT, "scripts", "collectors")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import load_seoul_subway as L  # noqa: E402

REAL_RAW = "D:/tmp/sangga-wave3/pr6-prework/raw"
MIGRATION = sorted(__import__("glob").glob(os.path.join(ROOT, "supabase", "migrations", "*_seoul_subway.sql")))
LAT0, LNG0 = 37.5, 127.0
M_PER_DEG_LAT = 111194.93           # 6371008.8 × π / 180


def master_row(i, name, line, lat=LAT0, lng=LNG0):
    return {"BLDN_ID": "{:04d}".format(i), "BLDN_NM": name, "ROUTE": line, "LAT": str(lat), "LOT": str(lng)}


def ride_row(ym, line, sttn, on=100.0, off=90.0, job="20261003"):
    r = {"USE_MM": ym, "SBWY_ROUT_LN_NM": line, "STTN": sttn, "JOB_YMD": job}
    for c in L.ON_RAW:
        r[c] = 0.0
    for c in L.OFF_RAW:
        r[c] = 0.0
    r["HR_8_GET_ON_NOPE"] = on
    r["HR_18_GET_OFF_NOPE"] = off
    return r


LINE_MAP = {"9호선2~3단계": "9호선(연장)", "경의선": "경의중앙선", "공항철도 1호선": "공항철도1호선"}
STATION_MAP = {("창동", "경원선"): ("map", "창동", "4호선"), ("한국항공대", "경의선"): ("skip", None, None)}


def small_master():
    return [master_row(1, "서울역", "1호선"), master_row(2, "창동", "4호선", lat=LAT0 + 0.01),
            master_row(3, "잠실(송파구청)", "2호선", lat=LAT0 + 0.02),
            master_row(4, "수색", "경의중앙선", lat=LAT0 + 0.03),
            master_row(5, "녹천", "경원선", lat=LAT0 + 0.04)]          # 경원선 표기가 마스터에 있다(실자료와 같다 · 승하차 0)


def small_month(ym):
    return [ride_row(ym, "1호선", "서울역"), ride_row(ym, "4호선", "창동"), ride_row(ym, "경원선", "창동"),
            ride_row(ym, "2호선", "잠실 (송파구청)"), ride_row(ym, "경의선", "수색"),
            ride_row(ym, "경의선", "한국항공대", on=2.0, off=1.0)]


def write_raw(raw, master, months, fetched="20261102"):
    os.makedirs(os.path.join(raw, "master"), exist_ok=True)
    os.makedirs(os.path.join(raw, "ridership"), exist_ok=True)
    with open(os.path.join(raw, "master", fetched + ".json"), "w", encoding="utf-8") as f:
        json.dump({"service": "subwayStationMaster", "total": len(master), "rows": master}, f, ensure_ascii=False)
    for ym, rows in months.items():
        with open(os.path.join(raw, "ridership", "{}_{}.json".format(ym, fetched)), "w", encoding="utf-8") as f:
            json.dump({"service": "CardSubwayTime", "ym": ym, "total": len(rows), "rows": rows}, f, ensure_ascii=False)


@pytest.fixture
def loose(monkeypatch):
    """작은 가짜 자료로 관문을 지나게 문턱만 낮춘다(관문 시험은 문턱을 따로 본다)."""
    monkeypatch.setattr(L, "MASTER_ROWS", (1, 900))
    monkeypatch.setattr(L, "ROWS_PER_MONTH", (1, 700))
    monkeypatch.setattr(L, "MIN_MONTH_SUM", 1)


# ── 1. 정규화 · 묶음 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,want", [("잠실(송파구청)", "잠실"), (" 삼성 (무역센터) ", "삼성"), ("삼성", "삼성"),
                                      ("자양(뚝섬한강공원)", "자양"), ("서울 역", "서울역")])
def test_norm_name(raw, want):
    assert L.norm_name(raw) == want


def _east(m):
    """LAT0 위도에서 동쪽 m 미터의 경도."""
    import math  # noqa: PLC0415
    return LNG0 + m / (M_PER_DEG_LAT * math.cos(math.radians(LAT0)))


def test_group_boundary_599_and_601():
    near = [master_row(1, "가", "1호선"), master_row(2, "가", "2호선", lng=_east(599))]
    far = [master_row(1, "가", "1호선"), master_row(2, "가", "2호선", lng=_east(601))]
    st, split = L.build_stations(near)
    assert [s["group_id"] for s in st] == [1, 1] and split == []
    st, split = L.build_stations(far)
    assert [s["group_id"] for s in st] == [1, 2] and split == ["가"]


def test_chain_of_three_is_one_group_and_other_names_stay_apart():
    rows = [master_row(1, "가", "1호선"), master_row(2, "가", "2호선", lng=_east(500)),
            master_row(3, "가", "3호선", lng=_east(1000)), master_row(4, "나", "1호선", lng=_east(10))]
    st, split = L.build_stations(rows)
    assert [(s["station_id"], s["group_id"]) for s in st] == [("0001", 1), ("0002", 1), ("0003", 1), ("0004", 2)]
    assert split == []


def test_group_ids_follow_station_id_order():
    rows = [master_row(9, "나", "1호선"), master_row(3, "가", "1호선"), master_row(5, "가", "2호선")]
    st, _ = L.build_stations(rows)
    assert [(s["station_id"], s["group_id"]) for s in st] == [("0003", 1), ("0005", 1), ("0009", 2)]


# ── 2. 짝표 ──────────────────────────────────────────────────────────────────


def test_real_seed_files():
    line = L.read_line_seed()
    assert line == LINE_MAP
    st = L.read_station_seed()
    assert sum(1 for v in st.values() if v[0] == "map") == 6 and sum(1 for v in st.values() if v[0] == "skip") == 3
    assert st[("창동", "경원선")] == ("map", "창동", "4호선")
    assert st[("당고개", "4호선")] == ("map", "불암산", "4호선")
    assert st[("자양(뚝섬한강공원)", "7호선")] == ("skip", None, None)


@pytest.mark.parametrize("text", [
    "ride,master,note\n9호선2~3단계,9호선(연장),x\n",                      # 머리줄
    "ride_line,master_line,note\n경의선,경의중앙선,x\n경의선,중앙선,y\n",      # 중복
    "ride_line,master_line,note\n경의선,,x\n",                              # 빈 칸
])
def test_bad_line_seed_stops(tmp_path, text):
    p = tmp_path / "s.csv"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(L.GateError):
        L.read_line_seed(str(p))


@pytest.mark.parametrize("row", ["창동,경원선,skip,창동,4호선,x", "창동,경원선,map,,,x", "창동,경원선,move,창동,4호선,x"])
def test_bad_station_seed_stops(tmp_path, row):
    p = tmp_path / "s.csv"
    p.write_text("ride_sttn,ride_line,action,master_sttn,master_line,note\n" + row + "\n", encoding="utf-8")
    with pytest.raises(L.GateError):
        L.read_station_seed(str(p))


def test_resolve_station_map_then_line_map():
    key = {("창동", "4호선"): "0002", ("수색", "경의중앙선"): "0004", ("잠실", "2호선"): "0003"}
    assert L.resolve("창동", "경원선", LINE_MAP, STATION_MAP, key) == ("0002", "경원선", "map")
    assert L.resolve("수색", "경의선", LINE_MAP, STATION_MAP, key) == ("0004", "경의중앙선", "plain")
    assert L.resolve("잠실 (송파구청)", "2호선", LINE_MAP, STATION_MAP, key) == ("0003", "2호선", "plain")
    assert L.resolve("한국항공대", "경의선", LINE_MAP, STATION_MAP, key) == (None, None, "skip")
    assert L.resolve("없는역", "1호선", LINE_MAP, STATION_MAP, key) == (None, "1호선", "plain")


# ── 3. 관문 ──────────────────────────────────────────────────────────────────


def test_master_gate_positive_control():
    rows = [master_row(i, "역{}".format(i), "1호선") for i in range(784)]
    assert L.master_problems(rows) == []


@pytest.mark.parametrize("mutate,word", [
    (lambda rows: rows[:600], "700~900 밖"),
    (lambda rows: rows + [dict(rows[0], BLDN_NM="딴이름")], "BLDN_ID 중복"),
    (lambda rows: [dict(rows[0], LAT="")] + rows[1:], "빈 칸"),
    (lambda rows: [dict(rows[0], LAT="126.97", LOT="37.55")] + rows[1:], "범위"),       # 위경도를 뒤바꾼 꼴
    (lambda rows: rows + [master_row(999, "역1", "1호선")], "(정규화 이름, 호선) 중복"),
])
def test_master_gate_catches(mutate, word):
    rows = [master_row(i, "역{}".format(i), "1호선") for i in range(784)]
    assert any(word in b for b in L.master_problems(mutate(rows)))


def test_month_dedup_same_values_and_stop_on_different():
    rows, n = L.parse_month("202603", {"total": 3, "rows": [ride_row("202603", "1호선", "서울역")] * 2
                                       + [ride_row("202603", "2호선", "강남")]}, "f")
    assert n == 3 and len(rows) == 2
    with pytest.raises(L.GateError, match="값이 다릅니다"):
        L.parse_month("202603", {"total": 2, "rows": [ride_row("202603", "1호선", "서울역"),
                                                     ride_row("202603", "1호선", "서울역", on=101.0)]}, "f")


@pytest.mark.parametrize("payload", [
    {"ym": "202610", "code": "INFO-200", "total": 0, "rows": []},
    {"service": "CardSubwayTime", "ym": "202610", "total": 0, "rows": []},
    {"ym": "202610", "code": "INFO-000", "total": 5, "rows": []},
])
def test_empty_envelope_is_no_data(payload):
    assert L.parse_month("202610", payload, "f") is None


def test_month_shape_gates():
    good = ride_row("202609", "1호선", "서울역")
    with pytest.raises(L.GateError, match="USE_MM"):
        L.parse_month("202609", {"total": 1, "rows": [dict(good, USE_MM="202608")]}, "f")
    bad = dict(good)
    bad.pop("JOB_YMD")
    with pytest.raises(L.GateError, match="빠진 칸"):
        L.parse_month("202609", {"total": 1, "rows": [bad]}, "f")
    with pytest.raises(L.GateError, match="모르는 칸"):
        L.parse_month("202609", {"total": 1, "rows": [dict(good, NEW=1)]}, "f")
    assert L.parse_month("202609", {"total": 1, "rows": [good]}, "f")[1] == 1      # 양성 대조


@pytest.mark.parametrize("value,want", [(892.0, 892), ("12", 12), (0, 0), ("3.0", 3)])
def test_to_count_ok(value, want):
    assert L.to_count(value, "c", "w") == want


@pytest.mark.parametrize("value", [1.5, None, "", -1, "x", float("nan")])
def test_to_count_stops(value):
    with pytest.raises(L.GateError):
        L.to_count(value, "c", "w")


def test_job_date():
    assert L.to_job_date("20261003", "w") == "2026-10-03"
    assert L.to_job_date("", "w") is None and L.to_job_date(None, "w") is None
    for bad in ("2026-10-03", "20261340", "2026103"):
        with pytest.raises(L.GateError):
            L.to_job_date(bad, "w")


def _stats(joined, skip=0, unmatched=(), on=200_000_000, off=200_000_000):
    return {"joined": joined, "skip": skip, "unmatched": list(unmatched), "on": on, "off": off}


def test_month_gates_positive_control():
    bad, rate = L.month_problems(620, _stats(618, skip=2))
    assert bad == [] and rate == 100.0


@pytest.mark.parametrize("n,stats,word", [
    (549, _stats(549), "550~700 밖"),
    (701, _stats(701), "550~700 밖"),
    (620, _stats(619, unmatched=[("새역", "1호선")]), "짝표 밖 미매칭"),
    (620, _stats(609, skip=11), "skip 행 11"),
    (620, _stats(500, skip=0, unmatched=[]), "조인률"),
    (620, _stats(620, on=99_999_999), "100,000,000 미만"),
    (620, _stats(620, off=99_999_999), "100,000,000 미만"),
])
def test_month_gates_catch(n, stats, word):
    assert any(word in b for b in L.month_problems(n, stats)[0])


def test_ride_line_gate():
    assert L.ride_line_problems({"1호선", "경의선"}, {"1호선", "경의중앙선"}, LINE_MAP) == []
    assert "새선" in L.ride_line_problems({"1호선", "새선"}, {"1호선"}, LINE_MAP)[0]


def test_missing_months():
    assert L.missing_months(["202101", "202103"]) == ["202102"]
    assert L.missing_months(["202102"]) == ["202101"]
    assert L.missing_months([]) == []


# ── 4. 파일 고르기 ───────────────────────────────────────────────────────────


def test_pick_latest_files(tmp_path):
    for n in ("master/20261001.json", "master/20261102.json", "master/20261102_2.json", "master/x.json",
              "ridership/202609_20261005.json", "ridership/202609_20261102.json", "ridership/202608_20261005.json",
              "ridership/202613_20261005.json"):
        p = tmp_path / n
        p.parent.mkdir(exist_ok=True)
        p.write_text("{}", encoding="utf-8")
    assert os.path.basename(L.pick_master(str(tmp_path))) == "20261102_2.json"
    got = {k: os.path.basename(v) for k, v in L.pick_months(str(tmp_path)).items()}
    assert got == {"202609": "202609_20261102.json", "202608": "202608_20261005.json"}
    assert L.pick_master(str(tmp_path / "없음")) is None


# ── 5·6. 훑기 · SQL · dry-run ─────────────────────────────────────────────────


def test_scan_small_two_raw_rows_to_one_station_stay_two_rows(tmp_path, loose):
    raw = str(tmp_path / "raw")
    write_raw(raw, small_master(), {"202608": small_month("202608"), "202609": small_month("202609")})
    rep = L.scan(raw, line_map=LINE_MAP, station_map=STATION_MAP)
    assert rep["problems"] == []
    rows = rep["rows"]["202609"]
    sids = [r[1] for r in rows]
    assert sids.count("0002") == 2                       # 창동 4호선 + 창동 경원선 — 둘 다 행으로
    by_raw = {(r[2], r[3]): r for r in rows}
    assert by_raw[("경원선", "창동")][4] == "경원선" and by_raw[("4호선", "창동")][4] == "4호선"
    assert by_raw[("경의선", "수색")][4] == "경의중앙선"
    assert by_raw[("2호선", "잠실 (송파구청)")][1] == "0003"
    m = rep["months"]["202609"]
    assert (m["skip"], m["joined"], m["rate"]) == (1, 5, 100.0)
    assert len(by_raw[("1호선", "서울역")]) == len(L.RIDE_COLUMNS)
    r = by_raw[("1호선", "서울역")]
    assert (r[5], r[6], r[-1]) == (100, 90, "2026-10-03")       # 합 · 작업일


def test_build_sql_text():
    sql = L.build_sql("C:\\x\\st.csv", "C:/x/ri.csv", 784, 1240, ["202609", "202608"])
    assert sql.index("set lock_timeout = '5s';") < sql.index("begin;") < sql.index("commit;")
    assert "\\copy stage_subway_station (" in sql and "from 'C:/x/st.csv'" in sql
    assert "on conflict (station_id) do update set station_nm = excluded.station_nm" in sql
    assert "delete from subway_ridership_m where use_mm in ('202608', '202609');" in sql
    # 달 지우기 → 사라진 역 검사 → 승하차 넣기 → has_ridership 차례.
    order = [sql.index(s) for s in ("delete from subway_ridership_m where", "마스터에서 사라진 역(",
                                    "insert into subway_ridership_m (", "set has_ridership = exists")]
    assert order == sorted(order)
    # RAISE 글의 % 는 자리표시자 수와 인자 수가 맞아야 한다(글자 % 는 %%) — raise 마다 센다.
    for m in re.finditer(r"raise exception '((?:[^']|'')*)'(.*?);", sql):
        text, args = m.group(1), m.group(2)
        holes = len(re.findall(r"(?<!%)%(?!%)", text))
        assert holes == args.count(","), m.group(0)
    with pytest.raises(ValueError):
        L.build_sql("a", "b", 1, 1, [])


def test_dry_run_writes_nothing(tmp_path, loose, monkeypatch):
    raw, stage = str(tmp_path / "raw"), str(tmp_path / "stage")
    write_raw(raw, small_master(), {"202609": small_month("202609")})
    monkeypatch.setattr(L, "read_line_seed", lambda *a: LINE_MAP)
    monkeypatch.setattr(L, "read_station_seed", lambda *a: STATION_MAP)
    assert L.main(["--raw-dir", raw, "--staging-dir", stage, "--dry-run"]) == 0
    assert not os.path.exists(stage)


def test_gate_failure_is_exit_1_and_writes_nothing(tmp_path, loose, monkeypatch, capsys):
    raw, stage = str(tmp_path / "raw"), str(tmp_path / "stage")
    write_raw(raw, small_master(), {"202609": small_month("202609") + [ride_row("202609", "1호선", "새역")]})
    monkeypatch.setattr(L, "read_line_seed", lambda *a: LINE_MAP)
    monkeypatch.setattr(L, "read_station_seed", lambda *a: STATION_MAP)
    assert L.main(["--raw-dir", raw, "--staging-dir", stage]) == 1
    assert not os.path.exists(stage)
    assert "새역" in capsys.readouterr().err


def test_bad_months_argument_is_exit_2(tmp_path):
    assert L.main(["--raw-dir", str(tmp_path), "--months", "2026-09", "--dry-run"]) == 2


def test_station_seed_map_target_missing_in_master_stops(tmp_path, loose):
    raw = str(tmp_path / "raw")
    write_raw(raw, small_master(), {"202609": small_month("202609")})
    seed = dict(STATION_MAP)
    seed[("당고개", "4호선")] = ("map", "불암산", "4호선")
    rep = L.scan(raw, line_map=LINE_MAP, station_map=seed)
    assert any("불암산" in p for p in rep["problems"])


# ── 7. 실자료 전수 (로컬 전용) ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def real_rep(tmp_path_factory):
    if not os.path.isdir(REAL_RAW):
        pytest.skip("메인이 받아 둔 raw 가 없다(로컬 전용 · {})".format(REAL_RAW))
    raw = str(tmp_path_factory.mktemp("subway_raw"))
    os.makedirs(os.path.join(raw, "master"))
    os.makedirs(os.path.join(raw, "ridership"))
    shutil.copyfile(os.path.join(REAL_RAW, "station_master.json"), os.path.join(raw, "master", "20261102.json"))
    for n in os.listdir(REAL_RAW):
        m = re.match(r"ridership_(\d{6})\.json$", n)
        if m:
            shutil.copyfile(os.path.join(REAL_RAW, n), os.path.join(raw, "ridership", "{}_20261102.json".format(m.group(1))))
    return L.scan(raw)


def test_real_data_passes_every_gate(real_rep):
    assert real_rep["problems"] == []
    assert len(real_rep["months"]) == 69 and real_rep["empty"] == ["202610"] and real_rep["gaps"] == []


def test_real_data_join_and_rows(real_rep):
    ms = real_rep["months"]
    assert all(m["rate"] == 100.0 for m in ms.values())
    assert min(m["plain_rate"] for m in ms.values()) >= 98.5
    assert {ym for ym, m in ms.items() if m["raw"] != m["dedup"]} == {"202603", "202607"}
    assert min(m["dedup"] for m in ms.values()) == 604 and max(m["dedup"] for m in ms.values()) == 623
    skips = {}
    for m in ms.values():
        for k in m["skip_keys"]:
            skips[k] = skips.get(k, 0) + 1
    assert skips == {("한국항공대", "경의선"): 33, ("자양(뚝섬한강공원)", "7호선"): 31, ("초성리", "경원선"): 1}


def test_real_data_groups(real_rep):
    st = real_rep["stations"]
    assert len(st) == 784 and len({s["group_id"] for s in st}) == 657
    assert real_rep["split"] == ["신촌", "양평", "운정"]
    chungmuro = {s["line_nm"]: s["group_id"] for s in st if s["name_norm"] == "충무로"}
    assert len(set(chungmuro.values())) == 1 and {"3호선", "4호선"} <= set(chungmuro)


def test_real_data_two_raw_rows_for_one_station(real_rep):
    """⑥-1 — 202609 창동 4호선 + 창동 경원선 → 같은 마스터 역 두 행(합치지도 버리지도 않는다)."""
    rows = real_rep["rows"]["202609"]
    chang = [r for r in rows if r[3] == "창동"]
    assert sorted(r[2] for r in chang) == ["4호선", "경원선"] and len({r[1] for r in chang}) == 1


# ── 8. 적재 SQL 로컬 PG 실행 ─────────────────────────────────────────────────

SHIM = r"""
create role anon;
create role authenticated;
create domain geometry as text;
create domain geography as text;
create function st_makepoint(x double precision, y double precision) returns text language sql immutable
  as $f$ select x::text || ' ' || y::text $f$;
create function st_setsrid(g text, srid integer) returns geometry language sql immutable as $f$ select g::geometry $f$;
"""


def table_blocks(sql):
    """마이그에서 표 둘 덩어리(create table … 그 표의 revoke 줄)만 — PostGIS 전용 글자 두 곳은 흉내 판 글자로."""
    out = []
    for name in ("subway_station", "subway_ridership_m"):
        m = re.search(r"(?ms)^create\s+table\s+if\s+not\s+exists\s+" + name + r"\s*\(.*?"
                      r"^revoke\s+all\s+on\s+" + name + r"\s+from[^\n]*;", sql)
        assert m, name
        out.append(m.group(0))
    text = "\n".join(out)
    assert text.count("geometry(Point, 4326)") == 1 and text.count("using gist") == 1
    return text.replace("geometry(Point, 4326)", "geometry").replace("using gist", "using btree")


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    psycopg2 = pytest.importorskip("psycopg2")
    initdb, pg_ctl, psql = shutil.which("initdb"), shutil.which("pg_ctl"), shutil.which("psql")
    if not initdb or not pg_ctl or not psql:
        pytest.skip("로컬 PostgreSQL(initdb·pg_ctl·psql)이 없다 — CI 는 글자 시험만 본다")
    if len(MIGRATION) != 1:
        pytest.skip("마이그 파일이 하나가 아니다")
    data = str(tmp_path_factory.mktemp("pgdata"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    subprocess.run([initdb, "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-locale"],
                   check=True, capture_output=True)
    log = os.path.join(data, "log.txt")
    # ⛔ capture_output 금지 — 서버 자식이 파이프를 물려받아 run() 이 끝없이 기다린다(Windows 실측).
    subprocess.run([pg_ctl, "-D", data, "-l", log, "-w", "-t", "60", "-o",
                    "-p {} -c listen_addresses=127.0.0.1".format(port), "start"],
                   check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    try:
        conn = None
        for _ in range(30):
            try:
                conn = psycopg2.connect(host="127.0.0.1", port=port, user="postgres", dbname="postgres")
                break
            except psycopg2.OperationalError:
                time.sleep(0.5)
        assert conn is not None
        conn.autocommit = True
        yield conn, psql, port
        conn.close()
    finally:
        subprocess.run([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


def _reset(conn):
    cur = conn.cursor()
    cur.execute("drop schema if exists public cascade; create schema public;")
    cur.execute("drop role if exists anon; drop role if exists authenticated;")
    cur.execute(SHIM)
    with open(MIGRATION[0], encoding="utf-8") as f:
        cur.execute(table_blocks(f.read().replace("\r\n", "\n")))
    return cur


def _load(pg, tmp, master, months, keep=None):
    """raw 를 쓰고 훑어 staging 을 쓰고 build_sql 을 psql 로 돌린다 → psql 종료코드."""
    _conn, psql, port = pg
    raw = os.path.join(tmp, "raw")
    shutil.rmtree(raw, ignore_errors=True)
    write_raw(raw, master, months)
    rep = L.scan(raw, line_map=LINE_MAP, station_map=STATION_MAP)
    assert rep["problems"] == [], rep["problems"]
    sp, rp, n = L.write_staging(rep, os.path.join(tmp, "stage"))
    sql_path = os.path.join(tmp, "load.sql")
    with open(sql_path, "w", encoding="utf-8") as f:
        f.write(L.build_sql(sp, rp, len(rep["stations"]), n, keep or list(rep["months"])))
    env = dict(os.environ, PGCLIENTENCODING="UTF8", LC_MESSAGES="C")
    r = subprocess.run([psql, "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "-d", "postgres",
                        "-v", "ON_ERROR_STOP=1", "-q", "-f", sql_path], env=env, capture_output=True,
                       stdin=subprocess.DEVNULL, timeout=120)
    return r.returncode, r.stderr.decode("utf-8", "replace")


def _counts(conn):
    cur = conn.cursor()
    cur.execute("select (select count(*) from subway_station), "
                "(select count(*) from subway_station where has_ridership), "
                "(select count(*) from subway_ridership_m), "
                "(select string_agg(use_mm || ':' || station_id || ':' || ride_line_nm || ':' || on_sum, ',' "
                "order by use_mm, station_id, ride_line_nm) from subway_ridership_m)")
    return cur.fetchone()


def test_load_sql_runs_and_is_repeatable(pg, tmp_path, loose):
    conn = pg[0]
    _reset(conn)
    months = {"202608": small_month("202608"), "202609": small_month("202609")}
    rc, err = _load(pg, str(tmp_path), small_master(), months)
    assert rc == 0, err
    first = _counts(conn)
    assert first[:3] == (5, 4, 10)                       # 역 5 · 녹천만 승하차 없음 · 2달 × 5행(skip 1 뺌)
    assert first[3].count("0002:") == 4                  # 창동 두 원문 줄 × 2달
    cur = conn.cursor()
    cur.execute("select geom, job_ymd from subway_station s join subway_ridership_m r using (station_id) "
                "where s.station_id = '0001' order by use_mm limit 1")
    assert cur.fetchone() == ("127 37.5", datetime.date(2026, 10, 3))        # 점 = st_makepoint(lng, lat) — 경도 먼저
    rc, err = _load(pg, str(tmp_path), small_master(), months)
    assert rc == 0, err
    assert _counts(conn) == first                        # 두 번 돌려도 같다


def test_vanished_station_referenced_raises_and_unreferenced_is_deleted(pg, tmp_path, loose):
    conn = pg[0]
    _reset(conn)
    rc, err = _load(pg, str(tmp_path), small_master(),
                    {"202608": small_month("202608"), "202609": small_month("202609")})
    assert rc == 0, err
    before = _counts(conn)
    # 마스터에서 서울역(0001)이 사라지고 202609 만 다시 넣는다 — 202608 이 0001 을 가리키므로 멈춰야 한다.
    master = small_master()[1:]
    month = [r for r in small_month("202609") if r["STTN"] != "서울역"]
    rc, err = _load(pg, str(tmp_path), master, {"202609": month})
    assert rc != 0 and "마스터에서 사라진 역(0001)" in err
    assert _counts(conn) == before                       # 통째 롤백
    # 양성 대조 — 두 달 다 다시 넣으면(0001 참조 0) 0001 이 지워지고 들어간다.
    rc, err = _load(pg, str(tmp_path), master, {"202608": [r for r in small_month("202608") if r["STTN"] != "서울역"],
                                                 "202609": month})
    assert rc == 0, err
    got = _counts(conn)
    assert got[0] == 4 and "0001:" not in got[3]


def test_station_without_rows_keeps_has_ridership_false(pg, tmp_path, loose):
    conn = pg[0]
    _reset(conn)
    master = small_master() + [master_row(7, "양재시민의숲", "신분당선", lat=LAT0 + 0.05)]
    rc, err = _load(pg, str(tmp_path), master, {"202609": small_month("202609")})
    assert rc == 0, err
    cur = conn.cursor()
    cur.execute("select station_id, has_ridership from subway_station order by station_id")
    assert cur.fetchall()[-1] == ("0007", False)
