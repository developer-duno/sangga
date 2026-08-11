# -*- coding: utf-8 -*-
"""
scripts/collectors/convert_bldrgst_bulk.py 단위 테스트

네트워크 없이 순수 로직만 검증한다:
  1. 컬럼 대응표 — 개수·중복·PNU 조각 (틀리면 데이터가 조용히 어긋난다)
  2. make_item — 칸 수 불일치 방어
  3. make_pnu — 19자리 조립·패딩·실패
  4. parse_scope / in_scope — 범위 필터
  5. find_zip — '총괄표제부'를 '표제부'로 오인하지 않는가
  6. ShardWriter — 시군구별 분리 · dry-run은 안 쓴다
  7. convert_one — zip 픽스처로 통합 동작

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import io
import json
import os
import sys
import zipfile

import pytest

_COLLECTORS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "collectors",
)
_SCRIPTS_DIR = os.path.dirname(_COLLECTORS_DIR)
for _p in (_SCRIPTS_DIR, _COLLECTORS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import convert_bldrgst_bulk as target  # noqa: E402


# ── 1. 컬럼 대응표 ────────────────────────────────────────────────────────────
#
# 건축HUB '설명' 팝업이 준 컬럼 수(2026-08-11 실측)와 API 응답 필드 수가 같아야 한다.
# 이 숫자가 어긋나면 칸이 한 칸씩 밀려 **전혀 다른 값이 조용히 들어간다**.

EXPECTED_LEN = {"title": 77, "flr_ouln": 33, "expos_area": 39}


@pytest.mark.parametrize("kind,n", sorted(EXPECTED_LEN.items()))
def test_column_count_matches_official_spec(kind, n):
    assert len(target.COLS[kind]) == n


@pytest.mark.parametrize("kind", sorted(EXPECTED_LEN))
def test_no_duplicate_column_names(kind):
    cols = target.COLS[kind]
    dupes = [c for c in set(cols) if cols.count(c) > 1]
    assert dupes == [], "중복 필드: {}".format(dupes)


@pytest.mark.parametrize("kind", sorted(EXPECTED_LEN))
def test_pnu_parts_present_in_every_kind(kind):
    """3종 모두 PNU 19자리를 조립할 수 있어야 한다 — 이게 이 파일을 쓰는 전제다."""
    for part in target.PNU_PARTS:
        assert part in target.COLS[kind], "{}에 {} 없음".format(kind, part)


def test_title_has_fields_the_loader_actually_reads():
    """적재기가 building 행을 만들 때 쓰는 필드가 빠지면 안 된다."""
    for f in ("mgmBldrgstPk", "dongNm", "bldNm", "regstrGbCdNm",
              "useAprDay", "totArea", "grndFlrCnt", "ugrndFlrCnt", "hoCnt"):
        assert f in target.COLS["title"]


def test_flr_and_expos_have_floor_fields():
    """층 정규화 정본(floor_from_codes)이 쓰는 flrGbCd/flrNo가 있어야 한다."""
    for kind in ("flr_ouln", "expos_area"):
        assert "flrGbCd" in target.COLS[kind]
        assert "flrNo" in target.COLS[kind]
    assert "areaExctYn" in target.COLS["flr_ouln"]      # 연면적 제외분 판정
    assert "exposPubuseGbCdNm" in target.COLS["expos_area"]  # 전유/공용 판정
    assert "hoNm" in target.COLS["expos_area"]              # unit_id 생성


@pytest.mark.skipif(
    not os.path.exists(os.path.join(_SCRIPTS_DIR, "..", "data", "raw", "bldrgst",
                                    "202608", "title.jsonl")),
    reason="강남 API raw 가 없는 환경",
)
@pytest.mark.parametrize("kind", sorted(EXPECTED_LEN))
def test_columns_match_live_api_fields(kind):
    """★ 있으면 가장 강한 검증 — API 응답 필드 집합과 정확히 같은가.

    API 는 페이지 번호 rnum 을 하나 더 주는데 파일엔 없다. 그것만 빼면 같아야 한다.
    """
    path = os.path.join(_SCRIPTS_DIR, "..", "data", "raw", "bldrgst", "202608",
                        "{}.jsonl".format(kind))
    with io.open(path, encoding="utf-8") as f:
        item = json.loads(f.readline())["item"]
    api = {k for k in item if k != "rnum"}
    assert set(target.COLS[kind]) == api


# ── 2. make_item ──────────────────────────────────────────────────────────────


def test_make_item_maps_by_position():
    cells = ["v{}".format(i) for i in range(len(target.COLS["flr_ouln"]))]
    item = target.make_item("flr_ouln", cells)
    assert item["mgmBldrgstPk"] == "v0"
    assert item["flrGbCd"] == "v18"
    assert item["crtnDay"] == "v32"


def test_make_item_strips_whitespace():
    cells = ["  a  "] + [""] * (len(target.COLS["flr_ouln"]) - 1)
    assert target.make_item("flr_ouln", cells)["mgmBldrgstPk"] == "a"


@pytest.mark.parametrize("delta", [-1, 1])
def test_make_item_rejects_wrong_cell_count(delta):
    """칸이 하나만 밀려도 전 컬럼이 어긋난다 — 통째로 버려야 한다."""
    n = len(target.COLS["title"]) + delta
    assert target.make_item("title", ["x"] * n) is None


# ── 3. make_pnu ───────────────────────────────────────────────────────────────


def _item(**kw):
    base = {"sigunguCd": "11110", "bjdongCd": "18400", "platGbCd": "0",
            "bun": "0220", "ji": "0001"}
    base.update(kw)
    return base


def test_make_pnu_assembles_19_digits():
    # 파일 첫 행(11110|18400|0|0220|0001) = 서울 종로구 부암동 220-1.
    # 라이브 parcel 실측: 1111018400102200001 (창의문로 170) 이 실재하고,
    # platGbCd 를 그대로 쓴 ...002200001 은 **존재하지 않는다**.
    assert target.make_pnu(_item()) == "1111018400102200001"


def test_make_pnu_left_pads_short_parts():
    assert target.make_pnu(_item(bun="220", ji="1")) == "1111018400102200001"


# ── 3-1. platGbCd 코드 체계 (이 파일을 쓸 때 가장 크게 데인 함정) ─────────────


@pytest.mark.parametrize("plat_gb,expected_11th", [
    ("0", "1"),   # 건축HUB '0'(대지)  -> PNU '1'
    ("1", "2"),   # 건축HUB '1'(산)    -> PNU '2'
])
def test_make_pnu_translates_plat_gb_code(plat_gb, expected_11th):
    """★ platGbCd 를 그대로 쓰면 PNU 가 통째로 어긋난다.

    2026-08-11 dry-run 실측: 이 변환을 빠뜨렸더니 서울+대전 표제부 727,585행 중
    **132행만** parcel 과 맞았다(나머지는 전부 '미보유'로 조용히 버려졌다).
    """
    pnu = target.make_pnu(_item(platGbCd=plat_gb))
    assert pnu is not None and pnu[10] == expected_11th


@pytest.mark.parametrize("bad", ["", "2", "9", "x"])
def test_make_pnu_rejects_unknown_plat_gb_code(bad):
    """매핑에 없는 값이면 추측하지 않고 None — 틀린 PNU를 만드는 것보다 낫다."""
    assert target.make_pnu(_item(platGbCd=bad)) is None


def test_convert_one_separates_block_jibun_from_real_failures(tmp_path):
    """블록/특수지번(platGbCd='2')은 '정상 제외'로 따로 센다.

    번·지가 없는 구획정리·하천부지 같은 것이라 PNU가 애초에 없다. 진짜 이상
    (알 수 없는 코드)과 한 칸에 섞어 세면 다음 사람이 결함으로 오해한다.
    """
    block = _row("flr_ouln", platGbCd="2", bun="0000", ji="0000")
    weird = _row("flr_ouln", platGbCd="9")
    zp = _make_zip(tmp_path, "flr_ouln", [block, weird])
    stats, _ = target.convert_one("flr_ouln", zp, set(), (), str(tmp_path),
                                  "x", dry_run=True)
    assert stats["block_jibun"] == 1
    assert stats["bad_pnu"] == 1


@pytest.mark.parametrize("bad", [
    {"sigunguCd": ""}, {"bjdongCd": "abc"}, {"platGbCd": ""},
    {"bun": "12345"},                      # 폭 초과
    {"sigunguCd": "1111"},                 # 짧으면 패딩돼 19자리가 깨진다
])
def test_make_pnu_rejects_bad_parts(bad):
    got = target.make_pnu(_item(**bad))
    assert got is None or len(got) == 19


def test_make_pnu_short_sigungu_does_not_silently_shift():
    """시군구가 4자리면 0 패딩돼 '01111...'이 된다 — 19자리라도 틀린 값이다.

    형식만으로는 못 거르므로, 이 경우는 parcel 대조에서 걸러진다(존재하지 않는 PNU).
    이 테스트는 그 사실을 못 박아 둔다.
    """
    got = target.make_pnu(_item(sigunguCd="1111"))
    assert got == "0111118400102200001"  # 19자리지만 실재하지 않는 PNU


# ── 4. 범위 필터 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("11,30", ("11", "30")), ("30,11", ("11", "30")),
    ("11680", ("11680",)), ("all", ()), ("ALL", ()),
    ("11,11680", ("11",)),
])
def test_parse_scope(raw, expected):
    assert target.parse_scope(raw) == expected


@pytest.mark.parametrize("raw", ["", " ", "1", "11a", "116801"])
def test_parse_scope_rejects_bad(raw):
    with pytest.raises(ValueError):
        target.parse_scope(raw)


def test_in_scope():
    assert target.in_scope("1111018400002200001", ("11", "30"))
    assert target.in_scope("3017010100108230004", ("11", "30"))
    assert not target.in_scope("4113512300103580001", ("11", "30"))
    assert target.in_scope("4113512300103580001", ())  # 전국이면 전부 통과


# ── 5. find_zip ───────────────────────────────────────────────────────────────


def test_find_zip_excludes_chonggwal_pyojebu(tmp_path):
    """'총괄표제부'에도 '표제부'가 들어 있다 — 그걸 집으면 완전히 다른 파일이다."""
    for n in ("국토교통부_건축물대장_표제부 (2026년 06월).zip",
              "국토교통부_건축물대장_총괄표제부 (2026년 06월).zip"):
        open(os.path.join(str(tmp_path), n), "wb").close()
    got = target.find_zip(str(tmp_path), "title")
    assert "총괄" not in os.path.basename(got)


def test_find_zip_raises_when_absent(tmp_path):
    with pytest.raises(target.ConvertError):
        target.find_zip(str(tmp_path), "title")


# ── 6. ShardWriter ────────────────────────────────────────────────────────────


def test_shard_writer_splits_by_sigungu(tmp_path):
    w = target.ShardWriter(str(tmp_path), "title.jsonl")
    w.write("11680", {"pnu": "a"})
    w.write("30170", {"pnu": "b"})
    w.write("11680", {"pnu": "c"})
    w.close()
    assert w.counts == {"11680": 2, "30170": 1}
    p = os.path.join(str(tmp_path), "11680", "title.jsonl")
    assert len(io.open(p, encoding="utf-8").read().strip().split("\n")) == 2


def test_shard_writer_dry_run_writes_nothing(tmp_path):
    w = target.ShardWriter(str(tmp_path), "title.jsonl", dry_run=True)
    w.write("11680", {"pnu": "a"})
    w.close()
    assert w.counts == {"11680": 1}
    assert os.listdir(str(tmp_path)) == []


def test_shard_writer_overwrites_not_appends(tmp_path):
    """다시 변환하면 덮어써야 한다 — append 면 중복이 누적돼 면적 합이 부푼다."""
    for _ in range(2):
        w = target.ShardWriter(str(tmp_path), "title.jsonl")
        w.write("11680", {"pnu": "a"})
        w.close()
    p = os.path.join(str(tmp_path), "11680", "title.jsonl")
    assert len(io.open(p, encoding="utf-8").read().strip().split("\n")) == 1


# ── 7. convert_one (zip 픽스처) ───────────────────────────────────────────────


def _row(kind, **over):
    vals = dict.fromkeys(target.COLS[kind], "")
    vals.update(_item())
    vals.update(over)
    return "|".join(vals[c] for c in target.COLS[kind])


def _make_zip(tmp_path, kind, lines, name=None):
    name = name or "국토교통부_건축물대장_{} (2026년 06월).zip".format(
        target.ZIP_MARKER[kind])
    path = os.path.join(str(tmp_path), name)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mart_djy_03.txt", "\n".join(lines).encode("utf-8"))
    return path


def test_convert_one_keeps_only_parcels_in_scope(tmp_path):
    # ⚠️ PNU 는 시군구(5)+법정동(5)+대지구분(1)+번(4)+지(4) 순서로 이어 붙인 값이다.
    #    손으로 적으면 자리를 틀리기 쉬우니 make_pnu 로 만들어 쓴다(이 테스트를
    #    처음 쓸 때 실제로 한 자리를 틀려 엉뚱한 실패를 봤다).
    seoul = _row("flr_ouln")
    daejeon = _row("flr_ouln", sigunguCd="30170", bjdongCd="10100",
                   bun="0823", ji="0004")
    gyeonggi = _row("flr_ouln", sigunguCd="41135", bjdongCd="12300",
                    bun="0358", ji="0001")                       # 범위 밖
    orphan = _row("flr_ouln", bun="9999")                        # parcel 에 없음
    zp = _make_zip(tmp_path, "flr_ouln", [seoul, daejeon, gyeonggi, orphan])

    out = os.path.join(str(tmp_path), "out")
    parcels = {
        target.make_pnu(_item()),
        target.make_pnu(_item(sigunguCd="30170", bjdongCd="10100",
                              bun="0823", ji="0004")),
    }
    stats, per = target.convert_one("flr_ouln", zp, parcels, ("11", "30"),
                                    out, "202606-bulk")

    assert stats["rows"] == 4
    assert stats["kept"] == 2
    assert stats["out_of_scope"] == 1
    assert stats["not_in_parcel"] == 1
    assert dict(per) == {"11110": 1, "30170": 1}


def test_convert_one_output_shape_matches_api_collector(tmp_path):
    """★ 적재기가 읽는 모양이어야 한다: {"pnu","fetched_at","item"} 한 줄 = 한 아이템."""
    zp = _make_zip(tmp_path, "flr_ouln", [_row("flr_ouln", flrGbCd="20", flrNo="3")])
    out = os.path.join(str(tmp_path), "out")
    pnu = target.make_pnu(_item())     # 손으로 적지 않는다 — platGbCd 변환이 끼어 있다
    target.convert_one("flr_ouln", zp, {pnu}, ("11",), out, "202606-bulk")
    line = io.open(os.path.join(out, "11110", "flr_ouln.jsonl"),
                   encoding="utf-8").readline()
    obj = json.loads(line)
    assert set(obj) == {"pnu", "fetched_at", "item"}
    assert obj["pnu"] == pnu
    assert obj["fetched_at"] == "202606-bulk"
    assert obj["item"]["flrGbCd"] == "20"
    assert obj["item"]["flrNo"] == "3"


def test_convert_one_counts_column_mismatch(tmp_path):
    zp = _make_zip(tmp_path, "flr_ouln", ["a|b|c"])
    stats, _ = target.convert_one("flr_ouln", zp, set(), (), str(tmp_path),
                                  "x", dry_run=True)
    assert stats["col_mismatch"] == 1
    assert stats["kept"] == 0


def test_convert_one_dry_run_writes_no_files(tmp_path):
    zp = _make_zip(tmp_path, "flr_ouln", [_row("flr_ouln")])
    out = os.path.join(str(tmp_path), "out")
    stats, _ = target.convert_one("flr_ouln", zp, {target.make_pnu(_item())}, ("11",),
                                  out, "x", dry_run=True)
    assert stats["kept"] == 1
    assert not os.path.exists(out)
