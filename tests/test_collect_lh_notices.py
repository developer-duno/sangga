# -*- coding: utf-8 -*-
"""LH 상가 공고 수집기 — 파싱·지역 옮기기·관문·upsert 를 지킨다.

여기서 막는 것은 **에러 없이 조용히 틀리는 종류**다. 이 수집기가 틀리는 길은 넷이다.

  1) 상가가 아닌 공고(분양주택·토지)가 섞여 들어온다 → 알림판이 남의 것으로 채워진다.
  2) 날짜 모양이 바뀌었는데 조용히 NULL 이 된다 → 마감일이 사라져 다 지난 공고가 계속 뜬다.
  3) 지역명을 못 옮기는데 아무도 모른다 → 행 수는 멀쩡한데 알림판이 빈다.
  4) 반쯤 들어간다 → "공고가 원래 이것뿐"인지 "우리가 흘렸는지" 화면에서 못 가린다.
  5) 포털이 잠깐 느린데 너무 일찍 포기한다 → 그 주 감시가 통째로 실패하고, 새 공고를
     못 본다. 2026-08-31 첫 예약 실행이 정확히 이것이었다.

전부 네트워크·DB 없이 확인한다(CI 에는 둘 다 없다).
"""

import datetime
import urllib.error

import pytest

import collect_lh_notices as lh

TODAY = datetime.date(2026, 8, 28)
STAMP = "2026-08-28T12:00:00+09:00"


def rec(**kw):
    """API 한 줄의 기본 모양(실측 값에서 뜬 것)."""
    base = {
        "PAN_ID": "BN-0001342",
        "PAN_NM": "인천계양 A3블록 단지내상가 수의계약 공고",
        "AIS_TP_CD": "23",
        "AIS_TP_CD_NM": "분양ㆍ(구)임대상가(입찰)",
        "UPP_AIS_TP_CD": "22",
        "UPP_AIS_TP_NM": "상가",
        "SPL_INF_TP_CD": "220",
        "CNP_CD_NM": "경기도",
        "PAN_SS": "공고중",
        "PAN_NT_ST_DT": "2026.08.26",
        "PAN_DT": "",
        "CLSG_DT": "2026.12.31",
        "DTL_URL": "https://apply.lh.or.kr/x",
        "ALL_CNT": "2913",
    }
    base.update(kw)
    return base


def row(**kw):
    return lh.record_to_row(rec(**kw), "시험", STAMP)


# ── 1. 상가만 고른다 ──────────────────────────────────────────────────────────


class TestSangaOnly:
    def test_upper_code_22_is_sanga(self):
        assert lh.is_sanga(rec()) is True

    @pytest.mark.parametrize("code", ["05", "06", "", "2", "220"])
    def test_everything_else_is_not(self, code):
        """⛔ '22 로 시작하나'가 아니라 **정확히 22 인가**로 가른다.

        공급정보 구분코드가 '220'·'221' 이라, 앞자리 비교로 짰다면 그것들이 통과한다.
        """
        assert lh.is_sanga(rec(UPP_AIS_TP_CD=code)) is False

    def test_missing_field_is_not_sanga(self):
        r = rec()
        del r["UPP_AIS_TP_CD"]
        assert lh.is_sanga(r) is False


# ── 2. 날짜 — 모르는 모양은 조용히 넘기지 않는다 ──────────────────────────────


class TestParseDate:
    @pytest.mark.parametrize("raw,want", [
        ("2026.08.27", "2026-08-27"),
        ("20260827", "2026-08-27"),
        ("2026-08-27", "2026-08-27"),
        (" 2026.08.27 ", "2026-08-27"),
    ])
    def test_known_shapes(self, raw, want):
        assert lh.parse_api_date(raw) == want

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_empty_is_none(self, raw):
        """원본이 안 적어 준 것 = None. 실측 531건 중 PAN_DT 가 181건 비어 있다."""
        assert lh.parse_api_date(raw) is None

    @pytest.mark.parametrize("raw", ["2026", "26.08.27", "2026년 8월", "abcdefgh"])
    def test_unknown_shape_raises(self, raw):
        """⛔ 모르는 모양을 None 으로 만들면 '안 적어 준 것'과 구분이 안 된다.

        그러면 LH 가 형식을 바꾼 날 마감일이 통째로 사라지는데 에러가 하나도 안 난다.
        """
        with pytest.raises(ValueError):
            lh.parse_api_date(raw)

    def test_impossible_date_raises(self):
        """13월 32일 같은 값도 잡는다 — 자릿수만 세면 통과한다."""
        with pytest.raises(ValueError):
            lh.parse_api_date("20261332")


# ── 3. 지역 옮기기 ────────────────────────────────────────────────────────────


class TestMapSido:
    @pytest.mark.parametrize("nm,code", [
        ("서울특별시", "11"),
        ("대전광역시", "30"),
        ("경기도", "41"),
        ("전남광주통합특별시", "12"),
        ("강원특별자치도", "51"),
        ("전북특별자치도", "52"),
    ])
    def test_current_names(self, nm, code):
        assert lh.map_sido(nm) == (code, False)

    def test_nationwide_is_not_null(self):
        """⛔ '전국'은 지역이 없는 게 아니라 **모든 지역**이다 — NULL 과 뜻이 정반대다."""
        assert lh.map_sido("전국") == (None, True)

    @pytest.mark.parametrize("nm,code", [
        ("강원도", "51"), ("전라북도", "52"), ("전라남도", "12"), ("광주광역시", "12"),
    ])
    def test_legacy_names_go_to_the_living_code(self, nm, code):
        """⛔ 옛 코드(42·45·46·29)로 옮기면 그 공고는 어느 지역에서도 안 보인다.

        `bjd_code` 실측: 그 코드들은 활성 법정동이 0개다(2026-08-28).
        """
        assert lh.map_sido(nm) == (code, False)

    @pytest.mark.parametrize("nm", ["", None, "화성특별시", "Gyeonggi-do"])
    def test_unknown_name_is_null_not_a_guess(self, nm):
        """모르면 비워 둔다 — 엉뚱한 지역에 붙은 공고는 없느니만 못하다."""
        assert lh.map_sido(nm) == (None, False)

    def test_table_matches_the_screen_region_list(self):
        """⛔ 화면의 시도 목록(src/lib/regions.ts)과 코드 집합이 같아야 한다.

        어긋나면 우리가 담은 공고에 화면이 절대 못 닿는 코드가 생긴다.
        """
        import os
        import re

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "src", "lib", "regions.ts"), encoding="utf-8") as f:
            ts = f.read()
        screen = set(re.findall(r"code:\s*'(\d{2})'", ts))
        assert set(lh.SIDO_BY_NAME.values()) == screen
        # 옛 이름이 가리키는 코드도 화면이 아는 것이어야 한다.
        assert set(lh.LEGACY_SIDO_BY_NAME.values()) <= screen


class TestMappingHealth:
    def test_one_unknown_name_is_reported_not_fatal(self):
        """새 이름 하나쯤은 담아 두고 나중에 고치면 된다 — 대신 세어서 보여 준다."""
        rows = [row(), row(PAN_ID="A", CNP_CD_NM="화성특별시")]
        assert lh.unknown_sido_names(rows) == {"화성특별시": 1}
        assert lh.assert_mapping_health(rows) is True

    def test_mostly_unknown_stops_everything(self):
        """⛔ 절반을 넘으면 표가 낡은 것이다 — 그대로 넣으면 알림판이 통째로 빈다."""
        rows = [row(PAN_ID=str(i), CNP_CD_NM="화성특별시") for i in range(3)] + [row()]
        with pytest.raises(ValueError, match="옮기지 못했습니다"):
            lh.assert_mapping_health(rows)

    def test_nationwide_only_is_fine(self):
        """전국 공고만 있는 판은 '못 옮긴 것'이 아니다 — 0으로 나누지도 않는다."""
        rows = [row(CNP_CD_NM="전국")]
        assert lh.assert_mapping_health(rows) is True


# ── 4. 한 줄 → 적재용 dict ────────────────────────────────────────────────────


class TestRecordToRow:
    def test_keeps_both_the_short_name_and_the_original(self):
        r = row()
        assert r["kind_nm"] == "분양 입찰"
        assert r["kind_nm_src"] == "분양ㆍ(구)임대상가(입찰)"

    @pytest.mark.parametrize("cd,short", [
        ("23", "분양 입찰"), ("24", "임대 추첨"), ("43", "임대 입찰"), ("38", "공모·심사"),
    ])
    def test_all_four_measured_kinds(self, cd, short):
        assert lh.short_kind(cd, "원문") == short

    def test_unknown_kind_falls_back_to_the_original_text(self):
        """⛔ '기타'로 뭉개면 LH 가 종류를 늘린 날 무엇이 새로 생겼는지 화면에서 못 가린다."""
        assert lh.short_kind("99", "임대상가(새 방식)") == "임대상가(새 방식)"
        assert lh.short_kind("99", "") == "종류 미상"

    def test_notice_date_prefers_the_field_that_is_always_filled(self):
        """PAN_DT 는 34% 가 빈 값이다 — 그쪽을 주로 쓰면 정렬이 무너진다."""
        assert row()["notice_date"] == "2026-08-26"
        assert row(PAN_NT_ST_DT="", PAN_DT="20260101")["notice_date"] == "2026-01-01"
        assert row(PAN_NT_ST_DT="", PAN_DT="")["notice_date"] is None

    def test_id_is_not_forced_into_a_number(self):
        """실측 식별자 세 갈래 — 숫자로 바꿔 담았다면 절반이 깨졌다."""
        for pid in ("0000061158", "BN-0001342", "LN-0000123"):
            assert row(PAN_ID=pid)["pan_id"] == pid

    def test_missing_id_stops(self):
        with pytest.raises(ValueError, match="PAN_ID"):
            row(PAN_ID="")

    def test_missing_name_stops(self):
        with pytest.raises(ValueError, match="PAN_NM"):
            row(PAN_NM="   ")

    def test_blank_optional_fields_become_null_not_empty_string(self):
        r = row(SPL_INF_TP_CD="", PAN_SS="", DTL_URL="", CNP_CD_NM="")
        assert r["spl_inf_tp_cd"] is None
        assert r["pan_ss"] is None
        assert r["dtl_url"] is None
        assert r["cnp_nm"] is None


# ── 5. 응답 껍데기 ────────────────────────────────────────────────────────────


class TestExtractRows:
    def test_finds_dslist_by_name_not_by_position(self):
        """자리로 집으면 순서가 바뀌는 날 조용히 빈손이 된다."""
        payload = [{"dsList": [rec()], "resHeader": []}, {"dsSch": []}]
        assert len(lh.extract_rows(payload)) == 1

    def test_empty_list_is_the_end_of_pages(self):
        """실측: 마지막 쪽을 넘기면 dsList 가 빈 목록으로 온다(오류가 아니다)."""
        assert lh.extract_rows([{"dsSch": []}, {"dsList": [], "resHeader": []}]) == []

    def test_missing_dslist_raises(self):
        """인증키 거절·형식 변경을 '공고 0건'으로 삼키지 않는다."""
        with pytest.raises(ValueError, match="dsList"):
            lh.extract_rows([{"dsSch": []}])

    def test_error_object_is_shown_to_the_human(self):
        with pytest.raises(ValueError, match="객체"):
            lh.extract_rows({"resultCode": "30", "resultMsg": "SERVICE KEY IS NOT REGISTERED"})


# ── 6. 창 계산 ────────────────────────────────────────────────────────────────


class TestWindow:
    def test_twelve_months_back(self):
        assert lh.window(today=TODAY, months=12) == ("20250828", "20260828")

    def test_crosses_the_year_boundary(self):
        assert lh.window(today=datetime.date(2026, 2, 3), months=6) == ("20250803", "20260203")

    def test_end_of_month_does_not_wobble(self):
        """31일에 6개월을 빼도 존재하지 않는 날짜(2026-02-31)를 만들지 않는다."""
        start, end = lh.window(today=datetime.date(2026, 8, 31), months=6)
        assert start == "20260228" and end == "20260831"

    def test_uses_kst_not_the_local_clock(self):
        """⛔ CI(UTC)와 내 PC(KST)가 하루 어긋나면 같은 명령이 다른 창을 훑는다."""
        assert lh.KST.utcoffset(None) == datetime.timedelta(hours=9)


# ── 7. 쪽 넘김 ────────────────────────────────────────────────────────────────


class TestFetchSanga:
    def _pages(self, pages):
        calls = []

        def fake(url):
            calls.append(url)
            idx = len(calls) - 1
            return [{"dsSch": []}, {"dsList": pages[idx] if idx < len(pages) else []}]

        return fake, calls

    def test_stops_on_a_partial_page(self):
        """한 쪽이 PG_SZ 보다 적게 오면 마지막 쪽이다 — 한 번 더 부르지 않는다."""
        full = [rec(PAN_ID=str(i)) for i in range(3)]
        fake, calls = self._pages([full])
        rows, pages, all_cnt = self._run(fake, page_size=3)
        assert len(calls) == 2 and pages == 2  # 3건(가득) → 다음 쪽 0건 → 끝
        assert len(rows) == 3 and all_cnt == 2913

    def _run(self, fake, page_size=100):
        return lh.fetch_sanga("KEY", "20250828", "20260828", STAMP,
                              fetcher=fake, page_size=page_size, verbose=False)

    def test_filters_out_non_sanga_on_every_page(self):
        page = [rec(PAN_ID="a"), rec(PAN_ID="b", UPP_AIS_TP_CD="05"), rec(PAN_ID="c")]
        fake, _ = self._pages([page])
        rows, _, _ = self._run(fake)
        assert [r["pan_id"] for r in rows] == ["a", "c"]

    def test_gives_up_before_burning_the_quota(self):
        """⛔ 끝을 못 알아본 채 도는 상태에서 예산을 다 태우지 않는다."""
        def endless(_url):
            return [{"dsList": [rec(PAN_ID="x")] * 2}]

        with pytest.raises(ValueError, match="넘겼습니다"):
            lh.fetch_sanga("KEY", "20250828", "20260828", STAMP,
                           max_pages=3, fetcher=endless, page_size=2, verbose=False)

    def test_url_encodes_the_key(self):
        """포털 키에는 +·/·= 가 들어 있다 — 그대로 두면 서버가 다른 글자로 읽어 403 이 난다."""
        url = lh.page_url("a+b/c=", 2, "20250828", "20260828")
        assert "a%2Bb%2Fc%3D" in url
        assert "PAGE=2" in url and "PAN_ST_DT=20250828" in url

    def test_error_text_never_carries_the_key(self):
        assert "SECRET" not in lh.mask_key("failed for key=SECRET", "SECRET")


# ── 8. 참을성 — 포털이 잠깐 느릴 때 넘어간다 ──────────────────────────────────


class TestRetryPatience:
    """2026-08-31 첫 예약 실행이 **여기서** 죽었다 (run 33348733771).

    포털은 가끔 몇 분씩 들쭉날쭉해진다. 그때 한 번 더 두드리면 통과하는데, 참을성이 그
    구간보다 짧으면 통째로 갇힌다 — 그날 로컬은 1회차 504 → 2회차 성공이었고, 깃허브
    러너는 60초 타임아웃 3번이 전부 그 구간 안에 들어가 실패했다.

    ⛔ 이 구간에는 그날까지 시험이 **한 줄도 없었다.** 다른 시험들이 fetcher 를 끼워 넣어
       재시도를 통째로 건너뛰었기 때문이다 — 그래서 라이브에서 처음 터졌다.
    """

    @staticmethod
    def _die(_url, timeout=None):
        raise TimeoutError("timed out")

    def test_survives_a_bad_patch_that_ends_before_we_give_up(self, monkeypatch):
        """마지막 한 번에 살아나도 성공이다 — 3번이던 시절엔 이 상황이 곧 실패였다."""
        calls = []

        def flaky(url, timeout=None):
            calls.append(url)
            if len(calls) < lh.RETRY_COUNT:
                raise TimeoutError("timed out")
            return {"ok": 1}

        monkeypatch.setattr(lh, "_get_json", flaky)
        assert lh.get_json_with_retry("u", sleep=lambda _s: None) == {"ok": 1}
        assert len(calls) == lh.RETRY_COUNT

    def test_retries_a_gateway_timeout(self, monkeypatch):
        """504 는 다시 물으면 답이 달라진다 — 2026-08-31 로컬 1회차가 정확히 이것이었다."""
        calls = []

        def flaky(url, timeout=None):
            calls.append(url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(url, 504, "Gateway Timeout", None, None)
            return {"ok": 1}

        monkeypatch.setattr(lh, "_get_json", flaky)
        assert lh.get_json_with_retry("u", sleep=lambda _s: None) == {"ok": 1}
        assert len(calls) == 2

    def test_total_patience_outlasts_the_outage_we_actually_saw(self):
        """실측된 나쁜 구간이 최소 3분(01:49:13~01:52:30)이다 — 그보다 짧으면 또 갇힌다.

        ⛔ 이 시험은 숫자를 지키는 게 아니라 **이유**를 지킨다. RETRY_COUNT 를 되돌리면
           여기가 먼저 빨개진다.
        """
        waits = [lh.RETRY_BACKOFF_SEC * (2 ** i) for i in range(lh.RETRY_COUNT - 1)]
        total = lh.TIMEOUT_SEC * lh.RETRY_COUNT + sum(waits)
        assert total >= 360, "참을성이 {}초뿐입니다 — 실측된 3분 장애를 못 넘깁니다".format(total)

    def test_waits_longer_between_each_knock(self, monkeypatch):
        """쉬지 않고 연달아 두드리면 느려진 서버를 더 밀어붙일 뿐이다."""
        monkeypatch.setattr(lh, "_get_json", self._die)
        waits = []
        with pytest.raises(TimeoutError):
            lh.get_json_with_retry("u", sleep=waits.append)
        assert waits == [lh.RETRY_BACKOFF_SEC * (2 ** i) for i in range(lh.RETRY_COUNT - 1)]

    def test_gives_up_loudly_when_the_portal_is_really_down(self, monkeypatch):
        """⛔ 조용히 넘기지 않는다.

        실패를 삼켜 '성공'으로 기록하면 형제 하트비트가 '마지막 성공'만 보고 멀쩡하다고
        판단해, **공고를 영영 안 보는 상태**가 조용히 이어진다.
        """
        monkeypatch.setattr(lh, "_get_json", self._die)
        with pytest.raises(TimeoutError):
            lh.get_json_with_retry("u", sleep=lambda _s: None)

    @pytest.mark.parametrize("code", sorted(lh.NO_RETRY_HTTP_CODES))
    def test_does_not_retry_what_will_not_change(self, monkeypatch, code):
        """401·403·404 는 사람이 고쳐야 하는 것 — 참을성을 늘려도 여기는 한 번뿐이다."""
        calls = []

        def refused(url, timeout=None):
            calls.append(url)
            raise urllib.error.HTTPError(url, code, "refused", None, None)

        monkeypatch.setattr(lh, "_get_json", refused)
        with pytest.raises(urllib.error.HTTPError):
            lh.get_json_with_retry("u", sleep=lambda _s: None)
        assert calls == ["u"]


# ── 9. SQL — 한 트랜잭션 · 지우지 않는다 · 반쪽이면 되돌린다 ──────────────────


class TestBuildSql:
    def test_wraps_in_one_transaction(self):
        sql = lh.build_sql([row()])
        assert sql.startswith("begin;")
        assert sql.strip().endswith("commit;")

    def test_never_deletes(self):
        """⛔ 마감된 옛 공고를 남기는 것이 이 표의 설계다 — delete 가 한 번이라도 들어가면
        그 설계가 조용히 뒤집힌다."""
        sql = lh.build_sql([row(), row(PAN_ID="B")]).lower()
        assert "delete" not in sql
        assert "truncate" not in sql

    def test_summary_counts_alive_in_korean_calendar(self):
        """⛔ 적재기 요약의 '지금 살아 있는 것'은 화면(list_lh_notices)과 **글자 그대로
        같은 자**로 센다 — 한국 날짜 **+** LH 자체 마감 상태(2026-09-01d) 둘 다.

        이 DB 는 UTC 라 `current_date` 를 쓰면 한국 새벽 0~9시에 화면과 이 요약이 서로 다른
        수를 말한다(마이그레이션 2026-09-01a). 여기는 "마감된 것도 지우지 않는다"는 결재가
        지켜지는지 **눈으로 보는 자리**라, 어긋나는 순간 판단 근거 자체가 오염된다.
        2026-08-31 감사 전까지 이 줄을 지키는 시험이 하나도 없어 조용히 어긋나 있었다.

        ⛔ 2026-09-01 재감사에서 시간대만 맞춰 두고 '접수마감' 상태 필터가 빠진 채였다는
        것이 드러났다(라이브 67 vs 65). 이 시험이 시간대만 보고 있으면 다음에도 같은
        틈을 못 잡는다 — 그래서 두 조각을 **함께** 요구한다.
        """
        sql = lh.build_sql([row()])
        assert "지금 살아 있는 것" in sql
        assert "Asia/Seoul" in sql
        # 주석이 아니라 **실제 문장**에 옛 방식이 남아 있지 않은지 본다.
        statements = "\n".join(
            ln for ln in sql.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "close_date >= current_date" not in statements
        # ⛔ 화면과 같은 두 조각이 실제 문장에 있는지 — 없으면 다음번 규칙 변경 때
        #    이 요약만 조용히 낡는다(2026-09-01 사고의 재발 방지).
        assert "접수마감" in statements
        assert "close_date is null or" in statements

    def test_upserts_on_pan_id(self):
        """상태·마감일은 바뀐다 — 같은 공고는 덮어써야 한다."""
        sql = lh.build_sql([row()])
        assert "on conflict (pan_id) do update set" in sql
        for col in ("pan_ss", "close_date", "collected_at", "sido_code", "is_nationwide"):
            assert "{} = excluded.{}".format(col, col) in sql

    def test_duplicate_ids_stop_with_a_name(self):
        """같은 식별자가 한 문장에 두 번 있으면 PostgreSQL 이 트랜잭션째 죽는다 —
        그 메시지만으로는 원인을 못 찾으니 여기서 이름을 대고 멈춘다."""
        with pytest.raises(ValueError, match="BN-0001342"):
            lh.build_sql([row(), row()])

    def test_empty_input_stops(self):
        with pytest.raises(ValueError):
            lh.build_sql([])

    def test_half_load_gate_is_a_raising_block_not_a_select(self):
        """⛔ psql 은 select 가 몇을 돌려주든 종료코드 0 이다 — do 블록에서 예외를 던져야
        ON_ERROR_STOP 이 걸리고 통째로 되돌아간다(load_sbiz_district 와 같은 교훈)."""
        sql = lh.build_sql([row(), row(PAN_ID="B")])
        assert "do $$" in sql
        assert "raise exception" in sql
        assert "collected_at = '{}'::timestamptz".format(STAMP) in sql
        assert "넣으려던 것은 2건" in sql

    def test_quotes_are_escaped(self):
        sql = lh.build_sql([row(PAN_NM="LH's 상가")])
        assert "'LH''s 상가'" in sql

    def test_nulls_go_in_as_null_not_the_word(self):
        sql = lh.build_sql([row(CNP_CD_NM="전국", CLSG_DT="")])
        assert ", null, true," in sql  # sido_code=null, is_nationwide=true

    def test_batches_do_not_change_the_row_count(self):
        rows = [row(PAN_ID=str(i)) for i in range(5)]
        sql = lh.build_sql(rows, batch_rows=2)
        assert sql.count("insert into lh_notice") == 3
        assert "넣으려던 것은 5건" in sql


# ── 10. 요약 ───────────────────────────────────────────────────────────────────


class TestSummarize:
    def test_counts_what_the_human_needs_to_see(self):
        rows = [row(), row(PAN_ID="B", CNP_CD_NM="전국"),
                row(PAN_ID="C", CNP_CD_NM="화성특별시", CLSG_DT="")]
        s = lh.summarize(rows)
        assert s["total"] == 3
        assert s["nationwide"] == 1
        assert s["unknown_sido"] == {"화성특별시": 1}
        assert s["no_close_date"] == 1
        assert s["by_kind"]["분양 입찰"] == 3
