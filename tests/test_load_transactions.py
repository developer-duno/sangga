# -*- coding: utf-8 -*-
"""
scripts/collectors/load_transactions.py 단위 테스트

라이브 API·Supabase 없이 검증한다:
  1. s / to_int / to_float   — 같은 필드가 str·int·float로 섞여 오는 실측 대응
  2. parse_deal_amount       — 만원 단위 콤마 문자열 -> 원 (틀리면 시세가 1만분의 1)
  3. normalize_floor         — 지하 음수 그대로, 0은 절대 안 만든다
  4. split_jibun / make_pnu  — 지번 -> PNU 19자리, 마스킹은 조립 불가
  5. build_emd_lookup        — 폐지 코드보다 현행 코드 우선
  6. make_tx_id              — 같은 raw면 같은 값, 같은 조합이 여럿이면 seq로 가른다
  7. build_transaction(s)    — 필드 매핑·해제 제외·조합 중복 처리
  8. latest_batch            — 재수집으로 쌓인 옛 배치 제거
  9. assert_* / parse_args

conftest.py를 새로 만들지 않기 위해 sys.path 조작은 이 파일 안에서만 한다.
"""

import json
import os
import sys

import pytest

_COLLECTORS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "collectors",
)
_SCRIPTS_DIR = os.path.dirname(_COLLECTORS_DIR)
for _p in (_SCRIPTS_DIR, _COLLECTORS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import load_transactions as target  # noqa: E402


# ── 픽스처 (2026-08-08 라이브 실측 값 그대로) ────────────────────────────────

ITEM = {
    "buildYear": 1993, "buildingAr": 28.8, "buildingType": "집합",
    "buildingUse": "제1종근린생활", "cdealDay": " ", "cdealType": " ",
    "dealAmount": "136,000", "dealDay": 25, "dealMonth": 6, "dealYear": 2026,
    "floor": 1, "jibun": "716", "landUse": "제3종일반주거",
    "plottageAr": " ", "sggCd": 11680, "umdNm": "일원동",
}
EMD = {"일원동": "1168010800", "역삼동": "1168010100"}


def raw(item, deal_ym="202606", fetched_at="2026-08-08T00:00:00+09:00"):
    return {"sigungu_code": "11680", "deal_ym": deal_ym,
            "fetched_at": fetched_at, "item": item}


# ── 1. 타입 정규화 (JSON이 같은 필드를 str·int·float로 섞어 준다) ────────────


@pytest.mark.parametrize("raw_v,expected", [
    (716, "716"), ("716", "716"), (" 716 ", "716"), (None, ""), (28.8, "28.8"),
])
def test_s_normalizes_any_type(raw_v, expected):
    assert target.s(raw_v) == expected


def test_to_int_handles_str_int_and_commas():
    assert target.to_int("1,234") == 1234
    assert target.to_int(1234) == 1234
    assert target.to_int("28.8") == 28
    assert target.to_int("") is None and target.to_int(None) is None
    assert target.to_int("없음") is None


def test_to_float_handles_blank_and_text():
    assert target.to_float(28.8) == 28.8
    assert target.to_float("28.8") == 28.8
    assert target.to_float(" ") is None
    assert target.to_float("x") is None


# ── 2. 거래금액 ──────────────────────────────────────────────────────────────


def test_parse_deal_amount_converts_man_won_to_won():
    """'136,000'은 13.6억이다 — 만원을 안 곱하면 금액이 1만분의 1이 된다."""
    assert target.parse_deal_amount("136,000") == 1_360_000_000


def test_parse_deal_amount_accepts_int_form():
    """실측상 18건은 dealAmount가 int로 온다."""
    assert target.parse_deal_amount(350) == 3_500_000


def test_parse_deal_amount_blank_is_none():
    assert target.parse_deal_amount(" ") is None
    assert target.parse_deal_amount(None) is None


# ── 3. 층 ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw_v,expected", [
    (1, 1), ("1", 1), (-1, -1), ("-2", -2), ("-3", -3), (15, 15),
])
def test_normalize_floor_keeps_sign(raw_v, expected):
    """지하는 API가 이미 음수로 준다 — 우리 규칙과 그대로 일치한다."""
    assert target.normalize_floor(raw_v) == expected


@pytest.mark.parametrize("raw_v", ["", " ", None, 0, "0"])
def test_normalize_floor_never_returns_zero(raw_v):
    """0은 절대 만들지 않는다 (절대 규칙 4 / DB CHECK chk_tx_floor)."""
    assert target.normalize_floor(raw_v) is None


# ── 4. 지번 -> PNU ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("jibun,expected", [
    ("716", (False, 716, 0)),
    (716, (False, 716, 0)),          # int로 오는 실측 케이스
    ("14-1", (False, 14, 1)),
    ("산3-2", (True, 3, 2)),
])
def test_split_jibun_parses_forms(jibun, expected):
    assert target.split_jibun(jibun) == expected


@pytest.mark.parametrize("jibun", ["6**", "9*", "", " ", None, "1-2-3", "abc"])
def test_split_jibun_rejects_masked_and_bad(jibun):
    """마스킹('6**')은 2024-01 이전·통건물의 기본 형태다 — 조립 불가로 다뤄야 한다."""
    assert target.split_jibun(jibun) is None


def test_make_pnu_assembles_19_digits():
    pnu = target.make_pnu("1168010800", "716")
    assert pnu == "1168010800" + "1" + "0716" + "0000"
    assert len(pnu) == 19


def test_make_pnu_uses_2_for_san():
    assert target.make_pnu("1168010800", "산3-2")[10] == "2"


def test_make_pnu_none_when_masked_or_bad_code():
    assert target.make_pnu("1168010800", "6**") is None
    assert target.make_pnu(None, "716") is None
    assert target.make_pnu("116801", "716") is None


# ── 5. 법정동 룩업 ───────────────────────────────────────────────────────────


def test_build_emd_lookup_prefers_active_code():
    """폐지 코드도 테이블에 남아 있다 — 실거래는 현행 표기로 오므로 현행이 맞다."""
    rows = [
        {"bjd_code": "1168010799", "sigungu_code": "11680", "emd_nm": "일원동", "is_active": False},
        {"bjd_code": "1168010800", "sigungu_code": "11680", "emd_nm": "일원동", "is_active": True},
    ]
    assert target.build_emd_lookup(rows, "11680")["일원동"] == "1168010800"


def test_build_emd_lookup_skips_other_sigungu_and_blank():
    rows = [
        {"bjd_code": "1144012300", "sigungu_code": "11440", "emd_nm": "서교동", "is_active": True},
        {"bjd_code": "1168010800", "sigungu_code": "11680", "emd_nm": "", "is_active": True},
    ]
    assert target.build_emd_lookup(rows, "11680") == {}


# ── 6. tx_id ─────────────────────────────────────────────────────────────────


def test_make_tx_id_is_stable_across_runs():
    assert target.make_tx_id(ITEM, 0) == target.make_tx_id(dict(ITEM), 0)


def test_make_tx_id_is_stable_across_type_variants():
    """같은 값이 str로 오든 int로 오든 같은 거래다 — 다른 id가 되면 중복 적재된다."""
    a = target.make_tx_id(ITEM, 0)
    b = target.make_tx_id(dict(ITEM, jibun="716", dealDay="25", sggCd="11680", floor="1"), 0)
    assert a == b


def test_make_tx_id_separates_same_combination():
    """같은 날 같은 값 거래가 32건 실재한다 — seq가 없으면 한 건으로 뭉개진다."""
    ids = {target.make_tx_id(ITEM, i) for i in range(32)}
    assert len(ids) == 32


def test_make_tx_id_differs_when_a_field_differs():
    assert target.make_tx_id(ITEM, 0) != target.make_tx_id(dict(ITEM, dealAmount="200,000"), 0)


# ── 7. 변환 ──────────────────────────────────────────────────────────────────


def test_is_canceled_reads_cdeal_type():
    assert target.is_canceled(dict(ITEM, cdealType="O")) is True
    assert target.is_canceled(ITEM) is False


def test_contract_ym_zero_pads_month():
    assert target.contract_ym(ITEM) == "202606"
    assert target.contract_ym(dict(ITEM, dealMonth=12)) == "202612"
    assert target.contract_ym(dict(ITEM, dealMonth=13)) is None
    assert target.contract_ym(dict(ITEM, dealYear="")) is None


def test_build_transaction_maps_every_field():
    rec, why = target.build_transaction(ITEM, EMD, 0)
    assert why == "적재"
    assert rec["pnu"] == "1168010800" + "1" + "0716" + "0000"
    assert rec["sigungu_code"] == "11680"
    assert rec["emd_nm"] == "일원동"
    assert rec["floor_no"] == 1
    assert rec["bld_area_m2"] == 28.8
    assert rec["land_area_m2"] is None          # plottageAr이 공백
    assert rec["price_won"] == 1_360_000_000
    assert rec["contract_ym"] == "202606"
    assert rec["contract_day"] == 25
    assert rec["build_year"] == 1993
    assert rec["tx_type"] == "집합"
    assert rec["main_use"] == "제1종근린생활"
    assert rec["bld_id"] is None and rec["bld_nm"] is None


def test_build_transaction_keeps_row_when_pnu_unassemblable():
    """통건물은 PNU가 원천 불가지만 지역·금액·면적은 유효하다 — 버리지 않는다."""
    rec, why = target.build_transaction(dict(ITEM, buildingType="일반", jibun="6**"), EMD, 0)
    assert why == "적재" and rec["pnu"] is None
    assert rec["price_won"] == 1_360_000_000


def test_build_transaction_rejects_rows_without_price_or_ym():
    assert target.build_transaction(dict(ITEM, dealAmount=""), EMD, 0)[0] is None
    assert target.build_transaction(dict(ITEM, dealYear=""), EMD, 0)[0] is None
    assert target.build_transaction(dict(ITEM, sggCd="116"), EMD, 0)[0] is None


def test_build_transactions_excludes_canceled_by_default():
    rows = [raw(ITEM), raw(dict(ITEM, cdealType="O", dealDay=26))]
    recs, stats = target.build_transactions(rows, EMD)
    assert len(recs) == 1
    assert stats["counts"]["해제 거래 제외"] == 1


def test_build_transactions_can_include_canceled():
    rows = [raw(ITEM), raw(dict(ITEM, cdealType="O", dealDay=26))]
    recs, _ = target.build_transactions(rows, EMD, include_canceled=True)
    assert len(recs) == 2


def test_build_transactions_gives_unique_ids_to_identical_deals():
    """같은 조합 32건이 와도 32행으로 살아남아야 한다 (실측 사례)."""
    rows = [raw(ITEM) for _ in range(32)]
    recs, _ = target.build_transactions(rows, EMD)
    assert len(recs) == 32
    assert len({r["tx_id"] for r in recs}) == 32
    target.assert_unique(recs, "tx_id")


def test_build_transactions_id_order_does_not_depend_on_raw_order():
    """raw 줄 순서가 달라져도 같은 id 집합이 나와야 한다 — 재수집 때 중복 적재 방지."""
    a = [raw(ITEM), raw(dict(ITEM, dealDay=26)), raw(dict(ITEM, dealAmount="200,000"))]
    b = list(reversed(a))
    ida = {r["tx_id"] for r in target.build_transactions(a, EMD)[0]}
    idb = {r["tx_id"] for r in target.build_transactions(b, EMD)[0]}
    assert ida == idb


def test_build_transactions_counts_pnu_success_and_failure():
    rows = [raw(ITEM), raw(dict(ITEM, jibun="6**", dealDay=26))]
    _, stats = target.build_transactions(rows, EMD)
    assert stats["counts"]["PNU 조립 성공"] == 1
    assert stats["counts"]["PNU 조립 실패"] == 1


# ── 8. latest_batch ──────────────────────────────────────────────────────────


def test_latest_batch_drops_older_duplicate_batch():
    old = raw(ITEM, fetched_at="2026-08-01T00:00:00+09:00")
    new = raw(dict(ITEM, dealDay=26), fetched_at="2026-08-08T00:00:00+09:00")
    kept = target.latest_batch([old, new])
    assert kept == [new]


def test_latest_batch_keeps_all_rows_of_same_batch():
    a = raw(ITEM)
    b = raw(dict(ITEM, dealDay=26))
    assert len(target.latest_batch([a, b])) == 2


def test_count_raw_rows_by_ym_counts_only_that_sigungu():
    rows = [raw(ITEM, deal_ym="202605"), raw(ITEM, deal_ym="202605"),
            raw(ITEM, deal_ym="202606"),
            dict(raw(ITEM, deal_ym="202605"), sigungu_code="11440")]
    assert target.count_raw_rows_by_ym(rows, "11680") == {"202605": 2, "202606": 1}


def test_latest_batch_is_per_month():
    """달이 다르면 서로 영향을 주지 않는다."""
    a = raw(ITEM, deal_ym="202605", fetched_at="2026-08-01T00:00:00+09:00")
    b = raw(ITEM, deal_ym="202606", fetched_at="2026-08-08T00:00:00+09:00")
    assert len(target.latest_batch([a, b])) == 2


# ── 8-1. fetch_done_row_counts / verified_latest_batch (독립 코드리뷰 지적 — B2) ──
#
# latest_batch는 (시군구, 계약년월)마다 fetched_at 최댓값만 본다. append_jsonl은
# 한 회차의 아이템을 한 줄씩 순차로 쓰므로(collect_one_month), 그 루프 도중
# 프로세스가 죽으면 "가장 늦은 배치"가 일부 행만 쓰인 채로 남을 수 있는데도
# 그게 그대로 선택된다(load_building_ledger.py와 같은 결함). verified_latest_batch는
# collect_progress가 기록한 "완료 시점 행수"로 후보를 검증해 이 함정을 막는다.

T1 = "2026-08-07T10:00:00+09:00"
T2 = "2026-08-08T10:00:00+09:00"
PERIOD_YM = "202606"


def test_fetch_done_row_counts_maps_period_key_to_row_count(monkeypatch):
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [
        {"period_key": "202605", "row_count": 40},
        {"period_key": "202606", "row_count": None},   # 결측은 버린다
    ])
    assert target.fetch_done_row_counts("https://x.supabase.co", {}, "11680") == {"202605": 40}


def test_fetch_done_row_counts_filters_to_collector_scope_and_done(monkeypatch):
    queries = []
    monkeypatch.setattr(
        target, "rest_select",
        lambda base, h, table, query, **kw: (queries.append((table, query)) or []))
    target.fetch_done_row_counts("https://x.supabase.co", {}, "11680")
    table, query = queries[0]
    assert table == "collect_progress"
    assert "collector=eq.{}".format(target.RTMS_COLLECTOR) in query
    assert "scope_key=eq.11680" in query
    assert "status=eq.done" in query


def test_verified_latest_batch_falls_back_when_newest_batch_incomplete():
    """최신 배치(T2)가 크래시로 1건만 쓰였으면, 온전한 옛 배치(T1)로 되돌아간다."""
    rows = [
        raw(ITEM, deal_ym=PERIOD_YM, fetched_at=T1),
        raw(dict(ITEM, dealDay=26), deal_ym=PERIOD_YM, fetched_at=T1),
        raw(dict(ITEM, dealDay=27), deal_ym=PERIOD_YM, fetched_at=T1),
        raw(ITEM, deal_ym=PERIOD_YM, fetched_at=T2),   # 크래시로 1건만 쓰임
    ]
    # T1이 온전히 끝났을 때 collect_progress에 저장된 행수
    done_counts = {("11680", PERIOD_YM): 3}

    kept = target.verified_latest_batch(rows, done_counts)

    assert len(kept) == 3
    assert {r["fetched_at"] for r in kept} == {T1}


def test_verified_latest_batch_keeps_current_behavior_for_single_batch():
    """배치가 1개뿐인 (시군구,계약월)(대다수 정상 케이스)는 done_counts와 무관하게 그대로 채택한다."""
    rows = [raw(ITEM, deal_ym=PERIOD_YM), raw(dict(ITEM, dealDay=26), deal_ym=PERIOD_YM)]
    assert target.verified_latest_batch(rows, {}) == rows


def test_verified_latest_batch_warns_when_no_batch_matches(capsys):
    """done_counts에 그 (시군구,계약월) 기록이 아예 없으면 최신 배치를 쓰되 경고한다."""
    rows = [
        raw(ITEM, deal_ym=PERIOD_YM, fetched_at=T1),
        raw(ITEM, deal_ym=PERIOD_YM, fetched_at=T2),
    ]
    kept = target.verified_latest_batch(rows, {})   # done_counts에 그 조합 없음
    assert {r["fetched_at"] for r in kept} == {T2}   # 검증 불가 -> 그래도 최신을 쓴다
    assert "확인할 수 없어" in capsys.readouterr().out


# ── 9. 불변식 / CLI ──────────────────────────────────────────────────────────


def test_assert_no_zero_floor_raises():
    with pytest.raises(RuntimeError, match="층 0"):
        target.assert_no_zero_floor([{"floor_no": 0}])


def test_assert_unique_raises_on_duplicate():
    with pytest.raises(RuntimeError, match="중복"):
        target.assert_unique([{"tx_id": "A"}, {"tx_id": "A"}])


def test_read_jsonl_counts_broken_lines(tmp_path):
    p = os.path.join(str(tmp_path), "11680.jsonl")
    with open(p, "w", encoding="utf-8") as fp:
        fp.write(json.dumps(raw(ITEM), ensure_ascii=False) + "\n")
        fp.write("{깨진 줄\n")
        fp.write("\n")
    rows, broken = target.read_jsonl(p)
    assert len(rows) == 1 and broken == 1


def test_read_jsonl_missing_file_is_empty():
    assert target.read_jsonl("없는파일.jsonl") == ([], 0)


def test_parse_args_defaults_and_overrides():
    o = target.parse_args([])
    assert o["sigungu_code"] == target.DEFAULT_SIGUNGU_CODE
    assert o["dry_run"] is False and o["include_canceled"] is False
    o2 = target.parse_args(["--sigungu-code", "11440", "--dry-run", "--include-canceled"])
    assert o2["sigungu_code"] == "11440" and o2["dry_run"] and o2["include_canceled"]


def test_parse_args_missing_value():
    with pytest.raises(ValueError, match="뒤에 값이 필요"):
        target.parse_args(["--sigungu-code"])


def test_parse_args_rejects_unknown_flag_like_help():
    """--help 를 조용히 무시하면 dry_run=False 인 실제 실행이 되어버린다(2026-08-08 실사고)."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--help"])


def test_parse_args_rejects_typo_does_not_silently_set_dry_run():
    """--dryrun(오타)이 --dry-run으로 조용히 넘어가면 실제 실행이 되어버린다."""
    with pytest.raises(ValueError, match="알 수 없는 인자"):
        target.parse_args(["--dryrun"])


# ── 10. 그룹 내부 seq 안정화 (_stable_group_order) ────────────────────────────
#
# make_tx_id의 seq는 build_transactions가 그룹 안 항목에 매기는 "몇 번째인가"다.
# 예전엔 raw 파일에 실린 순서(=API 응답 배열 순서, 재수집마다 달라질 수 있다)를
# 그대로 썼다. 지금은 그룹핑에 안 쓰인 나머지 필드값으로 결정적 정렬을 한다 —
# 같은 항목 집합이면 raw 물리적 순서가 바뀌어도 항상 같은 tx_id가 나와야 한다.


def test_build_transactions_group_seq_is_order_independent_when_member_missing():
    """그룹 멤버 하나가 빠진(해제 등) 뒤에도, 남은 항목의 tx_id는 raw 물리적
    순서가 아니라 내용으로만 결정된다 — 재수집 때 API가 배열 순서를 바꿔 줘도
    같은 결과가 나와야 재적재가 안전하다."""
    a = dict(ITEM, buildYear=1990)   # 그룹핑 10필드는 같고, 그룹핑에 안 쓰인
    c = dict(ITEM, buildYear=2000)   # buildYear만 다르다 (B가 빠진 뒤의 A·C 상황)

    order1 = target.build_transactions([raw(a), raw(c)], EMD)[0]
    order2 = target.build_transactions([raw(c), raw(a)], EMD)[0]

    id_by_year1 = {r["build_year"]: r["tx_id"] for r in order1}
    id_by_year2 = {r["build_year"]: r["tx_id"] for r in order2}
    assert id_by_year1 == id_by_year2


def test_stable_group_order_sorts_by_remaining_fields():
    a = dict(ITEM, buildYear=2000)
    b = dict(ITEM, buildYear=1990)
    ordered = target._stable_group_order([a, b])
    assert [item["buildYear"] for item in ordered] == [1990, 2000]


# ── 11. delete_stale_transactions (해제로 그룹 멤버가 빠지면 옛 tx_id가 DB에
#         영구히 남는다 — 이게 이 세션이 고치는 결함의 핵심) ─────────────────

SGG = "11680"
YM = "202606"


class _FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def _progress_says_complete(monkeypatch, counts):
    """collect_progress가 "이 계약월들은 done이고 row_count가 이렇다"고 답하게 만든다."""
    monkeypatch.setattr(target, "fetch_done_row_counts", lambda *a, **kw: dict(counts))


def _fake_delete(sink, status=204):
    def _delete(url, params=None, headers=None, timeout=None):
        sink.append(params)
        return _FakeResponse(status, text="err")
    return _delete


def _call(records, raw_counts, sigungu=SGG, **kw):
    return target.delete_stale_transactions(
        "https://x.supabase.co", {}, records, sigungu, raw_counts, **kw)


def test_delete_stale_transactions_deletes_only_ids_missing_from_new_set(monkeypatch):
    """해제로 B가 빠져 C의 seq가 밀리면(A-0,C-1), 옛 A-0/B-1/C-2 중 C가 쓰던
    A-0(계속 유지)·B-1(자연 소멸)은 그대로고, 원래 C의 옛 tx_id(...-2)만 지운다."""
    _progress_says_complete(monkeypatch, {YM: 2})
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [
        {"tx_id": "keep-0"}, {"tx_id": "keep-1"}, {"tx_id": "orphan-2"},
    ])
    sent = []
    monkeypatch.setattr(target.requests, "delete", _fake_delete(sent))

    records = [{"tx_id": "keep-0"}, {"tx_id": "keep-1"}]
    assert _call(records, {YM: 2}) == 1
    assert sent[0]["tx_id"] == 'in.("orphan-2")'


def test_delete_stale_transactions_scopes_query_to_sigungu_and_verified_yms(monkeypatch):
    """조회 자체를 그 시군구·검증된 계약월로 좁힌다 — 범위 밖은 SELECT도 안 한다."""
    _progress_says_complete(monkeypatch, {YM: 1})
    queries = []

    def fake_select(base_url, headers, table, query, **kw):
        queries.append((table, query))
        return []

    monkeypatch.setattr(target, "rest_select", fake_select)
    assert _call([{"tx_id": "keep-0"}], {YM: 1}) == 0
    table, query = queries[0]
    assert table == "transaction"
    assert "sigungu_code=eq.{}".format(SGG) in query
    assert "contract_ym=in.({})".format(YM) in query


def test_delete_stale_transactions_sends_nothing_when_all_rows_still_exist(monkeypatch):
    _progress_says_complete(monkeypatch, {YM: 1})
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [{"tx_id": "keep-0"}])

    def boom(*a, **kw):
        raise AssertionError("지울 행이 없으면 DELETE를 보내면 안 된다")

    monkeypatch.setattr(target.requests, "delete", boom)
    assert _call([{"tx_id": "keep-0"}], {YM: 1}) == 0


def test_delete_stale_transactions_empty_records_touches_no_network(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("빈 입력에 네트워크를 건드리면 안 된다")

    monkeypatch.setattr(target, "fetch_done_row_counts", boom)
    monkeypatch.setattr(target, "rest_select", boom)
    monkeypatch.setattr(target.requests, "delete", boom)
    assert _call([], {}) == 0


def test_delete_stale_transactions_chunks_deletes(monkeypatch):
    _progress_says_complete(monkeypatch, {YM: 1})
    monkeypatch.setattr(target, "rest_select",
                        lambda *a, **kw: [{"tx_id": "OLD{}".format(i)} for i in range(5)])
    sent = []
    monkeypatch.setattr(target.requests, "delete", _fake_delete(sent))

    assert _call([{"tx_id": "NEW"}], {YM: 1}, delete_chunk=2) == 5
    assert len(sent) == 3          # 2 + 2 + 1


def test_delete_stale_transactions_wraps_network_error(monkeypatch):
    _progress_says_complete(monkeypatch, {YM: 1})
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [{"tx_id": "OLD"}])

    def boom(url, params=None, headers=None, timeout=None):
        raise target.requests.exceptions.ConnectionError("연결 끊김")

    monkeypatch.setattr(target.requests, "delete", boom)
    with pytest.raises(RuntimeError, match="다시 실행하면"):
        _call([{"tx_id": "NEW"}], {YM: 1})


def test_delete_stale_transactions_raises_on_bad_status(monkeypatch):
    _progress_says_complete(monkeypatch, {YM: 1})
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [{"tx_id": "OLD"}])
    monkeypatch.setattr(target.requests, "delete", _fake_delete([], status=400))
    with pytest.raises(RuntimeError, match="옛 행 삭제"):
        _call([{"tx_id": "NEW"}], {YM: 1})


# ── 11-1. dry-run 미리보기 (SELECT는 하되 DELETE는 0 — 사장님 요구사항) ────────


def test_delete_stale_transactions_dry_run_previews_without_deleting(monkeypatch, capsys):
    _progress_says_complete(monkeypatch, {YM: 2})
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [
        {"tx_id": "keep-0"}, {"tx_id": "orphan-1"},
    ])

    def boom(*a, **kw):
        raise AssertionError("dry-run은 실제 DELETE를 보내면 안 된다")

    monkeypatch.setattr(target.requests, "delete", boom)
    deleted = _call([{"tx_id": "keep-0"}], {YM: 2}, dry_run=True)
    assert deleted == 0
    assert "정리 대상" in capsys.readouterr().out


# ── 11-2. 범위 밖은 절대 안 지워진다 (가장 중요한 안전장치) ───────────────────


def test_delete_stale_transactions_skips_ym_when_raw_row_count_mismatches(monkeypatch):
    """raw가 잘렸거나 일부 손상돼 이번에 센 행수가 done_counts와 다르면, 그
    계약월은 손대지 않는다(원본이 불완전한데 지우면 멀쩡한 행이 사라진다)."""
    _progress_says_complete(monkeypatch, {YM: 10})   # 수집 당시 10행
    monkeypatch.setattr(target, "rest_select", lambda *a, **kw: [{"tx_id": "OLD"}])

    def boom(*a, **kw):
        raise AssertionError("원본이 불완전하면 그 계약월은 SELECT도 하면 안 된다")

    monkeypatch.setattr(target, "rest_select", boom)
    monkeypatch.setattr(target.requests, "delete", boom)
    assert _call([{"tx_id": "NEW"}], {YM: 7}) == 0   # 지금 raw엔 7행뿐


def test_delete_stale_transactions_skips_ym_not_marked_done(monkeypatch):
    """collect_progress에 done으로 안 찍힌 계약월은 삭제 범위에서 뺀다."""
    _progress_says_complete(monkeypatch, {})   # done 목록이 비어 있음

    def boom(*a, **kw):
        raise AssertionError("done이 아닌 계약월을 지우면 안 된다")

    monkeypatch.setattr(target, "rest_select", boom)
    monkeypatch.setattr(target.requests, "delete", boom)
    assert _call([{"tx_id": "NEW"}], {YM: 3}) == 0


def test_delete_stale_transactions_never_touches_other_sigungu_or_ym(monkeypatch):
    """다른 시군구·검증 안 된 계약월의 옛 행은 이 함수의 SELECT 조회 문자열에
    조차 나타나지 않는다 — 대형 데이터 사고(범위 밖 삭제)의 1차 방어선."""
    _progress_says_complete(monkeypatch, {YM: 1, "202607": 999})  # 202607은 raw_row_counts에 없음
    queries = []

    def fake_select(base_url, headers, table, query, **kw):
        queries.append(query)
        return [{"tx_id": "keep-0"}]

    monkeypatch.setattr(target, "rest_select", fake_select)
    assert _call([{"tx_id": "keep-0"}], {YM: 1}, sigungu="11680") == 0
    query = queries[0]
    assert "sigungu_code=eq.11680" in query
    assert "202607" not in query
    assert "11440" not in query
