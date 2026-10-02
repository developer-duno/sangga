# -*- coding: utf-8 -*-
"""LH 공고 감시 — 기준선 비교·형제(수집기) 대조·워크플로 배선을 지킨다.

이 감시가 틀리는 길은 셋이다. 전부 **에러 없이 조용히** 일어난다.

  1) 기준선 비교가 어긋난다 → 이미 받은 공고로 매주 이슈가 열리거나(소음), 새 공고를
     못 알아본다(손실). 공고는 마감이 있어 못 알아본 쪽이 곧 손실이다.
  2) 감시가 수집기와 **다른 것을 본다** → 감시는 "새 공고 없음"이라 말하는데 수집기는
     다른 자료를 담는다. 두 벌로 짜 두면 언젠가 한쪽만 고쳐지며 반드시 온다.
  3) 워크플로 배선이 빠진다 → 판정은 맞는데 아무도 안 본다.

네트워크 없이 확인한다.
"""

import datetime
import json
import os
import shutil
import subprocess

import pytest
import yaml

import check_lh_notices as chk
import collect_lh_notices as lh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "lh-notice-watch.yml")
TODAY = datetime.date(2026, 8, 28)


def notice(pan_id="A", notice_date="2026-08-28", close_date="2026-09-30", **kw):
    row = {
        "pan_id": pan_id,
        "pan_nm": "인천계양 A3블록 단지내상가",
        "kind_nm": "임대 추첨",
        "notice_date": notice_date,
        "close_date": close_date,
        "cnp_nm": "경기도",
        "is_nationwide": False,
        "dtl_url": "https://apply.lh.or.kr/x",
    }
    row.update(kw)
    return row


def found(**kw):
    """`find_new_notices` 가 내놓는 모양(이슈 본문이 받는 것). 실제 함수를 거쳐 만든다 —
    손으로 흉내 내면 두 모양이 갈라져도 테스트가 못 잡는다."""
    got = chk.find_new_notices([notice(**kw)], latest_known="20200101", today=TODAY)
    assert got, "이 표본은 새 공고로 안 잡힙니다 — 시험 전제를 확인하세요"
    return got[0]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def workflow_text():
    return read(WORKFLOW)


@pytest.fixture(scope="module")
def workflow():
    return yaml.safe_load(read(WORKFLOW))


# ── 1. 형제 대조 — 감시와 수집기가 같은 것을 본다 ─────────────────────────────


class TestSameSourceAsCollector:
    def test_endpoint_and_type_code_come_from_the_collector(self):
        """⛔ 두 벌로 두면 언젠가 한쪽만 고쳐진다 — 그날 감시는 장님이 된 채 초록불을 켠다."""
        assert chk.BASE_URL is lh.BASE_URL
        assert chk.SANGA_UPP_CD is lh.SANGA_UPP_CD

    def test_inherits_the_collectors_patience(self, monkeypatch):
        """감시는 조회기를 따로 넘기지 않는다 — 그래서 수집기 한 곳만 고치면 둘 다 낫는다.

        2026-08-31 첫 예약 실행이 재시도 3번으로는 못 버텨 실패했고, 처방은 수집기의
        RETRY_COUNT 를 올린 것뿐이었다. 그게 감시에도 먹히는 근거가 바로 이 성질이다 —
        ⛔ 감시가 제 fetcher 를 넘기기 시작하면 참을성이 두 벌로 갈라져, 수집기를 고쳐도
           감시는 그대로 일찍 포기한다(그리고 아무도 그 사실을 모른다).
        """
        used = []

        def spy(url, service_key="", **kw):
            used.append(url)
            return [{"dsSch": []}, {"dsList": []}]

        monkeypatch.setattr(lh, "get_json_with_retry", spy)
        rows, pages, _all_cnt, _s, _e = chk.fetch_recent("KEY", months=1)
        assert used, "감시가 수집기의 재시도 조회기를 쓰지 않았습니다"
        assert rows == [] and pages == 1

    def test_does_not_reimplement_parsing(self):
        """파싱 함수를 여기서 다시 정의하지 않았는지 — 이름으로 확인한다."""
        src = read(os.path.join(ROOT, "scripts", "check_lh_notices.py"))
        for banned in ("def extract_rows", "def is_sanga", "def record_to_row", "def page_url"):
            assert banned not in src, "{} 를 감시가 다시 짰습니다 — 수집기 것을 쓰세요".format(banned)

    def test_collector_opens_without_extra_packages(self):
        """⛔ 워크플로에는 설치 단계가 없다 — 수집기가 표준 라이브러리만으로 열려야 한다.

        dotenv·requests 를 모듈 맨 위에서 부르면 러너에서 import 가 죽고, 감시는
        '실패'가 아니라 아예 안 도는 것처럼 보인다.
        """
        src = read(os.path.join(ROOT, "scripts", "collectors", "collect_lh_notices.py"))
        head = src.split("# ── 순수 함수")[0]
        assert "\nfrom dotenv import" not in head
        assert "\nimport requests" not in head


# ── 2. 기준선 비교 ────────────────────────────────────────────────────────────


class TestFindNew:
    def test_only_after_the_baseline(self):
        rows = [notice("old", notice_date="2026-08-20"),
                notice("new", notice_date="2026-08-28")]
        got = chk.find_new_notices(rows, latest_known="20260827", today=TODAY)
        assert [n["pan_id"] for n in got] == ["new"]

    def test_the_baseline_day_itself_is_already_ours(self):
        """기준선 = '받아서 넣은 최신 공고일'이라, 그날 것은 이미 창고에 있다."""
        rows = [notice("same", notice_date="2026-08-27")]
        assert chk.find_new_notices(rows, latest_known="20260827", today=TODAY) == []

    def test_closed_notices_are_not_worth_telling(self):
        rows = [notice("closed", notice_date="2026-08-28", close_date="2026-08-27")]
        assert chk.find_new_notices(rows, latest_known="20260101", today=TODAY) == []

    def test_unknown_close_date_counts_as_open(self):
        """⛔ 마감일을 모르는 것과 마감된 것은 다른 말이다 — 모른다고 숨기면 살아 있는
        공고가 조용히 사라진다(읽는 함수 list_lh_notices 와 같은 판단)."""
        rows = [notice("nodate", notice_date="2026-08-28", close_date=None)]
        got = chk.find_new_notices(rows, latest_known="20260101", today=TODAY)
        assert [n["pan_id"] for n in got] == ["nodate"]

    def test_closing_today_is_still_open(self):
        rows = [notice("today", notice_date="2026-08-28", close_date="2026-08-28")]
        assert len(chk.find_new_notices(rows, latest_known="20260101", today=TODAY)) == 1

    def test_lh_own_closed_status_is_not_worth_telling_even_with_a_future_close_date(self):
        """⛔ 화면(list_lh_notices)과 같은 규칙(2026-09-01d) — LH 가 '접수마감'이라 적어
        준 것은 마감일과 무관하게 뺀다. 마감일만 보면 못 거른다: 실측으로 마감일이
        2028년(먼 미래)인데 '접수마감'(취소공고)인 것이 있었다 — 그런 공고에 "새 공고
        떴습니다"로 매주 소음 이슈가 열리면 안 된다.
        """
        rows = [notice("cancelled", notice_date="2026-08-28",
                        close_date="2028-12-31", pan_ss="접수마감")]
        assert chk.find_new_notices(rows, latest_known="20260101", today=TODAY) == []

    def test_pan_ss_missing_is_still_open(self):
        """상태 칸을 안 준 공고(구버전 API 응답 등)까지 닫힌 것으로 오판하지 않는다."""
        rows = [notice("nostat", notice_date="2026-08-28", close_date="2026-09-30")]
        assert len(chk.find_new_notices(rows, latest_known="20260101", today=TODAY)) == 1

    def test_missing_notice_date_is_skipped_not_guessed(self):
        """공고일을 모르면 기준선과 견줄 수가 없다 — 새 것이라고 우기지 않는다."""
        rows = [notice("nodate", notice_date=None)]
        assert chk.find_new_notices(rows, latest_known="20260101", today=TODAY) == []

    def test_newest_first(self):
        rows = [notice("a", notice_date="2026-08-28"), notice("b", notice_date="2026-08-30")]
        got = chk.find_new_notices(rows, latest_known="20260101", today=TODAY)
        assert [n["pan_id"] for n in got] == ["b", "a"]

    def test_nationwide_is_labelled_not_blanked(self):
        rows = [notice("n", is_nationwide=True, cnp_nm="전국")]
        got = chk.find_new_notices(rows, latest_known="20260101", today=TODAY)
        assert got[0]["region"] == "전국"

    def test_unmapped_region_says_so(self):
        rows = [notice("u", cnp_nm=None)]
        got = chk.find_new_notices(rows, latest_known="20260101", today=TODAY)
        assert got[0]["region"] == "(지역 미상)"


class TestBaselineConstant:
    def test_baseline_is_eight_digits(self):
        assert chk.LATEST_KNOWN_NOTICE_DATE.isdigit()
        assert len(chk.LATEST_KNOWN_NOTICE_DATE) == 8

    def test_baseline_is_not_in_the_future(self):
        """미래 날짜를 적어 두면 새 공고를 영영 못 알아본다 — 에러 없이 조용히."""
        assert chk.LATEST_KNOWN_NOTICE_DATE <= datetime.datetime.now(chk.KST).strftime("%Y%m%d")


# ── 3. 이슈 제목·본문 ─────────────────────────────────────────────────────────


class TestIssue:
    def test_title_carries_the_newest_date_so_a_new_batch_opens_a_new_issue(self):
        """감시 이슈들과 반대 방향의 선택이다 — 공고는 판마다 내용이 달라, 묶으면
        지난주 것에 묻힌다. 대신 같은 판으로는 두 번 안 열린다."""
        t = chk.build_issue_title([found(pan_id="a", notice_date="2026-08-30"), found(pan_id="b")])
        assert "2026-08-30" in t and "2건" in t

    def test_body_has_the_commands_in_powershell(self):
        body = chk.build_issue_body([found()])
        assert "```powershell" in body
        assert "collect_lh_notices.py" in body
        assert "post_load.py" in body

    def test_body_tells_which_baseline_to_raise(self):
        body = chk.build_issue_body([found(notice_date="2026-08-30")], latest_known="20260827")
        assert "LATEST_KNOWN_NOTICE_DATE" in body
        assert "20260830" in body
        assert "20260827" in body

    def test_body_does_not_dump_hundreds_of_rows(self):
        body = chk.build_issue_body([found(pan_id=str(i)) for i in range(40)])
        assert "외 10건" in body

    def test_pipe_in_a_name_does_not_break_the_table(self):
        body = chk.build_issue_body([found(pan_nm="A|B 상가")])
        assert "A·B 상가" in body


class TestGithubOutput:
    def test_noop_without_env(self, monkeypatch):
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        assert chk.write_github_output([notice()]) is False

    def test_writes_found_and_title(self, tmp_path, monkeypatch):
        out = tmp_path / "o.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        chk.write_github_output([found()])
        text = out.read_text(encoding="utf-8")
        assert "found=true" in text and "count=1" in text

    def test_empty_title_when_nothing_new(self, tmp_path, monkeypatch):
        out = tmp_path / "o.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        chk.write_github_output([])
        text = out.read_text(encoding="utf-8")
        assert "found=false" in text and "title=\n" in text


# ── 4. main() 흐름 ────────────────────────────────────────────────────────────


def _patch(monkeypatch, rows=None, boom=None):
    monkeypatch.setenv("MOLIT_KEY", "KEY")

    def fake(key, months=chk.DEFAULT_MONTHS):
        if boom:
            raise boom
        return rows or [], 1, 2913, "20260628", "20260828"

    monkeypatch.setattr(chk, "fetch_recent", fake)


def _fresh(**kw):
    """main() 은 실시계와 모듈 상수를 그대로 쓴다 — 그래서 날짜를 **상대값**으로 만든다.
    기준선 다음 날 공고 · 오늘+30일 마감. 고정 날짜(8/28·9/30)로 두면 기준선을 올리는
    순간(2026-09-05 실제로 터짐)이나 마감일이 지나는 순간 시험만 조용히 빨개진다."""
    base = datetime.datetime.strptime(chk.LATEST_KNOWN_NOTICE_DATE, "%Y%m%d").date()
    today = datetime.datetime.now(chk.KST).date()
    return notice(notice_date=(base + datetime.timedelta(days=1)).isoformat(),
                  close_date=(today + datetime.timedelta(days=30)).isoformat(), **kw)


class TestMain:
    def test_zero_when_nothing_new(self, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        _patch(monkeypatch, [notice(notice_date="2026-01-01")])
        assert chk.main([]) == 0
        assert "새 공고" in capsys.readouterr().out
        assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()

    def test_one_and_writes_the_issue_body_when_new(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        _patch(monkeypatch, [_fresh()])
        assert chk.main([]) == 1
        assert "인천계양" in (tmp_path / chk.ISSUE_BODY_FILE).read_text(encoding="utf-8")

    def test_two_when_the_lookup_fails(self, monkeypatch, tmp_path, capsys):
        """⛔ '새 공고가 있다'(1)와 '내가 확인을 못 했다'(2)는 서로 다른 사건이다 —
        한 코드로 뭉뚱그리면 워크플로가 엉뚱한 이슈를 연다."""
        monkeypatch.chdir(tmp_path)
        _patch(monkeypatch, boom=RuntimeError("연결 실패"))
        assert chk.main([]) == 2

    def test_two_when_the_window_is_empty(self, monkeypatch, tmp_path, capsys):
        """⛔ 조용한 빈손 금지. 두 달에 상가 공고 0건은 정상이 아니다(1년 531건 실측) —
        '새 공고 없음'으로 끝내면 그날부터 매주 헛초록이 켜진다."""
        monkeypatch.chdir(tmp_path)
        _patch(monkeypatch, [])
        assert chk.main([]) == 2
        assert "정상이 아닙니다" in capsys.readouterr().err

    def test_two_without_a_key(self, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("MOLIT_KEY", raising=False)
        monkeypatch.setattr(chk, "get_api_key", lambda: "")
        assert chk.main([]) == 2
        assert "MOLIT_KEY" in capsys.readouterr().err

    def test_two_when_reading_the_key_fails(self, monkeypatch, tmp_path, capsys):
        """⛔ 열쇠를 읽다 죽어도 2 다 — try 밖이면 파이썬 기본값 1 = '새 공고 있음'으로 샌다.
        예외 본문은 화면에 싣지 않는다(가릴 열쇠가 아직 없어 mask_key 를 못 쓴다)."""
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "gh_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        _patch(monkeypatch, [_fresh()])

        def boom():
            raise RuntimeError("열쇠값-절대-찍히면-안됨")

        monkeypatch.setattr(chk, "get_api_key", boom)
        assert chk.main([]) == 2
        said = capsys.readouterr()
        assert "[실패] 인증키를 읽는 중 RuntimeError" in said.err
        assert "열쇠값-절대-찍히면-안됨" not in said.out + said.err
        assert not out.exists() and not (tmp_path / chk.ISSUE_BODY_FILE).exists()

    def test_json_output(self, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        _patch(monkeypatch, [_fresh()])
        assert chk.main(["--json"]) == 1
        data = json.loads(capsys.readouterr().out)
        assert data["latest_known"] == chk.LATEST_KNOWN_NOTICE_DATE
        assert len(data["new"]) == 1

    def test_never_touches_the_database(self):
        """⛔ 이 감시는 창고를 건드리지 않는다 — 그래서 워크플로에 DB 열쇠가 없다."""
        src = read(os.path.join(ROOT, "scripts", "check_lh_notices.py"))
        assert "dbx" not in src
        assert "SANGGA_DATABASE_URL" not in src


# ── 4-1. 조회 뒤에 죽음 — 1(새 공고 있음)과 겹치면 워크플로가 조용히 초록 ─────────


class TestAfterLookupFailures:
    def test_judging_failure_exits_two_not_one(self, monkeypatch, tmp_path, capsys):
        """⛔ 응답 줄이 딕셔너리가 아니면(모양이 바뀜) 판정에서 죽는다 — 조회 실패와 같은
        종류라 2 다. 잡지 못하면 파이썬 기본값 1 = '새 공고 있음'으로 읽힌다."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        _patch(monkeypatch, [_fresh(), "딕셔너리가 아닌 줄"])
        assert chk.main([]) == 2
        err = capsys.readouterr().err
        assert "[실패] 응답을 판정하는 중 AttributeError" in err
        assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()

    def test_unwritable_github_output_exits_four_not_one(self, monkeypatch, tmp_path, capsys):
        """⛔ 이슈 본문 파일을 다 쓴 뒤 GITHUB_OUTPUT 에서 죽는 경로 — 기본값 1 이면 워크플로가
        통과시키는데 found 값이 없어 이슈 단계가 건너뛰어진다.

        GITHUB_OUTPUT 을 폴더로 가리켜 실제로 open 이 실패하게 만든다(윈도우·리눅스 공통).
        """
        monkeypatch.chdir(tmp_path)
        blocked = tmp_path / "gh_output_is_a_folder"
        blocked.mkdir()
        monkeypatch.setenv("GITHUB_OUTPUT", str(blocked))
        _patch(monkeypatch, [_fresh()])
        assert chk.main([]) == chk.EXIT_OUTPUT_FAILED == 4
        err = capsys.readouterr().err
        assert "[실패] 결과를 쓰는 중" in err and "알림이 안 나갔을 수 있습니다" in err
        assert (tmp_path / chk.ISSUE_BODY_FILE).exists(), "이슈 파일은 이미 써졌다 — 그래도 1 이 아니다"

    def test_unwritable_issue_body_exits_four_not_one(self, monkeypatch, tmp_path, capsys):
        """이슈 본문 파일 자리에 폴더가 있어 실제로 쓰기가 실패하는 경로."""
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "gh_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        (tmp_path / chk.ISSUE_BODY_FILE).mkdir()
        _patch(monkeypatch, [_fresh()])
        assert chk.main([]) == chk.EXIT_OUTPUT_FAILED
        assert "[실패] 결과를 쓰는 중" in capsys.readouterr().err
        assert not out.exists(), "이슈 파일에서 죽었으면 found 기록까지 가지 않는다"

    @pytest.mark.parametrize("stage", ["report", "write_issue_body", "write_github_output"])
    @pytest.mark.parametrize("as_json", [False, True], ids=["화면", "json"])
    @pytest.mark.parametrize("exc", [OSError("디스크가 가득 찼습니다"), TypeError("칸 모양이 다릅니다")],
                             ids=["OSError", "TypeError"])
    def test_any_failure_after_lookup_exits_four(self, monkeypatch, tmp_path, capsys, stage, as_json, exc):
        """조회가 끝난 뒤 화면 출력·이슈 본문 파일·GITHUB_OUTPUT 어디서 죽든 4 다(1·0 아님).

        TypeError 도 넣는 이유: 파일 오류(OSError 류)만 던지면 except 를 OSError 로 좁혀도
        초록이다 — 실제로는 모양이 다른 값(json 직렬화 실패 등)에서도 죽는다.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        _patch(monkeypatch, [_fresh()])

        def boom(*_a, **_kw):
            raise exc

        monkeypatch.setattr(chk, stage, boom)
        assert chk.main(["--json"] if as_json else []) == chk.EXIT_OUTPUT_FAILED
        assert "{}: {}".format(type(exc).__name__, exc) in capsys.readouterr().err

    def test_rows_without_any_notice_date_exit_two_not_zero(self, monkeypatch, tmp_path, capsys):
        """⛔ 줄은 있는데 공고일이 전부 비면 find_new_notices 가 다 건너뛰어 0('새 공고 없음')이
        된다 — LH 가 공고일 칸 이름을 바꾸면 매주 조용한 초록. 그래서 2 다."""
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "gh_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        _patch(monkeypatch, [notice("a", notice_date=None), notice("b", notice_date=None)])
        assert chk.main([]) == 2
        assert "공고일이 있는 줄이 0건" in capsys.readouterr().err
        assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()
        assert not out.exists(), "found 기록을 남기면 안 된다"

    @pytest.mark.parametrize("with_new, expect", [(True, 1), (False, 0)], ids=["새공고", "없음"])
    def test_some_rows_without_notice_date_judge_as_usual(self, monkeypatch, tmp_path, with_new, expect):
        """양성 대조: 공고일이 **일부만** 빈 것은 평소대로 판정한다(운영 실측상 빈 줄은 0건이지만, 한 줄이 비었다고 감시 전체를 멈추지 않는다)."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        dated = _fresh(pan_id="d") if with_new else notice("d", notice_date="2026-01-01")
        _patch(monkeypatch, [notice("x", notice_date=None), dated])
        assert chk.main([]) == expect
        assert (tmp_path / chk.ISSUE_BODY_FILE).exists() is with_new

    def test_exit_codes_are_documented(self):
        assert chk.EXIT_OUTPUT_FAILED == 4
        assert "4 = 조회는 됐는데 결과" in chk.__doc__


# ── 5. 워크플로 배선 ──────────────────────────────────────────────────────────


class TestWorkflow:
    def test_exists_and_parses(self, workflow):
        assert workflow["name"]
        assert "schedule" in workflow[True]  # yaml 이 `on:` 을 참(True)으로 읽는다

    def test_runs_weekly(self, workflow):
        crons = [c["cron"] for c in workflow[True]["schedule"]]
        assert crons == ["30 1 * * 1"]

    def test_does_not_collide_with_the_siblings(self, workflow):
        """같은 시각에 몰리면 큐가 밀릴 때 함께 드롭된다."""
        mine = {c["cron"] for c in workflow[True]["schedule"]}
        wf_dir = os.path.dirname(WORKFLOW)
        for name in os.listdir(wf_dir):
            if not name.endswith(".yml") or name == os.path.basename(WORKFLOW):
                continue
            other = yaml.safe_load(read(os.path.join(wf_dir, name)))
            sched = (other.get(True) or {}).get("schedule") or []
            assert mine.isdisjoint({c["cron"] for c in sched}), name

    def test_can_be_run_by_hand(self, workflow):
        assert "workflow_dispatch" in workflow[True]

    def test_uses_only_the_api_key(self, workflow_text):
        """⛔ 창고 열쇠는 GitHub 에 올라가지 않는다 — 이 감시는 포털에만 물어본다."""
        assert "secrets.MOLIT_KEY" in workflow_text
        assert "SANGGA_DATABASE_URL" not in workflow_text
        assert "SERVICE_KEY" not in workflow_text

    def test_missing_key_does_not_pass_silently(self, workflow_text):
        """⛔ 건너뛰어도 job 은 '성공'으로 기록된다 — 형제들 눈에는 멀쩡해 보이는 채로
        공고를 영영 안 보는 상태가 계속된다(의견함 주간 알림과 같은 처방)."""
        assert "lh-notice-setup-issue.md" in workflow_text
        assert os.path.exists(os.path.join(ROOT, ".github", "lh-notice-setup-issue.md"))

    def test_new_notice_exit_code_is_not_treated_as_a_failure(self, workflow_text):
        """종료코드 1 = '새 공고가 있다'. 이것으로 job 을 실패시키면 매주 실패 이슈가
        열려 진짜 실패와 구분이 안 된다."""
        step = [s for s in yaml.safe_load(workflow_text)["jobs"]["watch"]["steps"]
                if s.get("id") == "check"][0]
        assert 'rc" -eq 1' in step["run"]
        # ⛔ continue-on-error 로 뭉뚱그리면 **진짜 실패(2)까지 조용히 묻힌다.**
        assert not step.get("continue-on-error")
        assert 'exit "$rc"' in step["run"]

    def test_opens_an_issue_with_the_body_the_script_writes(self, workflow_text):
        assert chk.ISSUE_BODY_FILE in workflow_text

    def test_new_notice_issue_dedup_looks_at_closed_ones_too(self, workflow_text):
        """제목에 날짜가 박혀 있으므로 닫힌 것까지 봐야 한 번 닫은 판이 다시 안 열린다."""
        assert "--state all" in workflow_text

    def test_failure_is_loud(self, workflow_text):
        """감시가 실패하면 이슈가 안 열린다 — 그 사실 자체를 이슈로 만든다."""
        assert "if: failure()" in workflow_text
        assert "lh-notice-failure-issue.md" in workflow_text
        assert os.path.exists(os.path.join(ROOT, ".github", "lh-notice-failure-issue.md"))

    def test_watches_all_four_siblings(self, workflow_text):
        """⛔ 새 예약은 그물에 들어가야 하고, 그물도 새 예약을 봐야 한다(양방향)."""
        import check_watch_heartbeat as hb

        for other in hb.DEFAULT_WORKFLOWS:
            if other == os.path.basename(WORKFLOW):
                continue
            assert "--workflow {}".format(other) in workflow_text
        assert os.path.basename(WORKFLOW) in hb.DEFAULT_WORKFLOWS
        assert hb.WORKFLOW_LABELS[os.path.basename(WORKFLOW)]

    def test_weekly_threshold_applies(self):
        """주 1회 예약이므로 8일 기준(주 1회 + 하루 여유)을 그대로 쓴다."""
        import check_watch_heartbeat as hb

        assert hb.max_age_for(os.path.basename(WORKFLOW)) == hb.DEFAULT_MAX_AGE_DAYS


# ── 6. 워크플로 단계를 실제로 bash 로 돌려 본다 ──────────────────────────────
#
# 글자 검사만으로는 검사 줄을 지워도 초록이다(형제 지난 날짜 감시 2026-10-01 실측). 그래서
# 단계의 run: 글자를 꺼내 GitHub 기본 셸(`bash -e` — `shell:` 을 안 적은 단계의 기본값)로
# 돌리고, PATH 앞에 가짜 `python` 을 둔다. 네트워크·진짜 API 는 타지 않는다.
# 윈도우는 Git Bash 로 돈다(WSL 의 System32 bash 는 PATH·경로를 다르게 풀어 건너뛴다).
# 도우미는 tests/test_check_data_freshness.py 의 것을 옮겨 왔다(시험 파일끼리 import 하지 않는다).
# ⛔ CI 에서는 bash 가 없으면 건너뛰지 않고 실패한다 — 거기서 조용히 skip 되면 이 시험이 지키는
#    빈틈(이슈 파일·found 기록 검사)이 아무도 모르게 다시 열린다.


def _find_bash():
    path = shutil.which("bash")
    if not path:
        return None
    low = path.lower()
    if os.name == "nt" and ("system32" in low or "windowsapps" in low):
        return None
    return path


def _write_lf(path, text):
    """줄 끝을 LF 로 — CRLF 가 섞이면 bash 가 `\\r` 을 명령 글자로 읽는다."""
    path.write_bytes(text.encode("utf-8"))
    path.chmod(0o755)


def _run_step(workflow, name, tmp_path, fakes, env_extra):
    bash = _find_bash()
    if bash is None:
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            pytest.fail("CI 인데 bash 를 못 찾았습니다 — 워크플로 단계 실행 시험을 건너뛸 수 없습니다")
        pytest.skip("bash 가 없습니다(윈도우는 Git Bash 필요)")
    steps = [s for s in workflow["jobs"]["watch"]["steps"] if s.get("name") == name]
    assert steps, "'{}' 단계를 워크플로에서 못 찾았습니다".format(name)
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    for fname, body in fakes.items():
        _write_lf(bin_dir / fname, body)
    _write_lf(tmp_path / "step.sh", steps[0]["run"])
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env.update(env_extra)
    return subprocess.run(
        [bash, "-e", "step.sh"],
        cwd=str(tmp_path), env=env, capture_output=True, timeout=60,
    )


FAKE_PYTHON = """#!/bin/sh
# 가짜 check_lh_notices.py — 시나리오대로 이슈 본문 파일·기록을 남기고 정한 코드로 끝난다.
if [ -n "$FAKE_FILES" ]; then
  printf 'b\\n' > lh_new_notice_issue.md
fi
if [ -n "$FAKE_OUTPUT" ]; then
  printf 'found=true\\ncount=1\\ntitle=t\\n' >> "$GITHUB_OUTPUT"
fi
exit "$FAKE_RC"
"""


@pytest.mark.parametrize("rc, files, output, expect, said_part", [
    (1, True, True, 0, None),                       # 새 공고 — 이슈 파일 + found=true 둘 다 → 통과
    (1, True, False, 1, "found=true 기록이 없습니다"),  # ⛔ 이슈 파일만 → 도중에 죽음
    (1, False, True, 1, "이슈 본문 파일이 없습니다"),    # ⛔ 기록만 → 도중에 죽음
    (1, False, False, 1, "이슈 본문 파일이 없습니다"),   # 잡지 못한 예외의 기본값 1
    (0, False, False, 0, None),                     # 새 공고 없음
    (2, False, False, 2, "조회에 실패했습니다"),         # 조회 실패 → 실패 알림
    (4, True, False, 4, "결과를 쓰다 실패했습니다"),     # 결과를 쓰다 실패 → 실패 알림(조회 실패라 말하지 않음)
], ids=["1-둘다", "1-파일만", "1-기록만", "1-둘다없음", "0", "2", "4"])
def test_check_step_runs_for_real(workflow, tmp_path, rc, files, output, expect, said_part):
    gh_output = tmp_path / "gh_output"
    gh_output.write_bytes(b"")
    res = _run_step(workflow, "새 공고가 떴는지 확인", tmp_path, {"python": FAKE_PYTHON}, {
        "FAKE_RC": str(rc),
        "FAKE_FILES": "1" if files else "",
        "FAKE_OUTPUT": "1" if output else "",
        "GITHUB_OUTPUT": "gh_output",
    })
    said = res.stdout.decode("utf-8", "replace") + res.stderr.decode("utf-8", "replace")
    assert res.returncode == expect, said
    if said_part:
        assert said_part in said, said
    if rc == 4:
        assert "조회에 실패했습니다" not in said, "4 는 조회 실패가 아니다 — 다른 말로 알린다"


# ── bash 가 없을 때 가드 — CI 에서는 실패, 로컬에서만 건너뛴다 (2026-10-02) ──────
# 위 실행 시험이 CI 에서 조용히 skip 되면 지키는 빈틈이 아무도 모르게 다시 열린다.


def test_run_step_fails_on_ci_without_bash(monkeypatch, tmp_path):
    monkeypatch.setitem(globals(), "_find_bash", lambda: None)
    monkeypatch.setenv("CI", "1")
    # BaseException 으로 받는다 — 건너뜀(Skipped)이 새어 나가면 시험이 빨강이 아니라 '건너뜀'이 된다.
    with pytest.raises(BaseException) as caught:
        _run_step(None, "아무 단계", tmp_path, {}, {})
    assert caught.type is pytest.fail.Exception, caught.type


def test_run_step_fails_on_github_actions_without_bash(monkeypatch, tmp_path):
    monkeypatch.setitem(globals(), "_find_bash", lambda: None)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    # BaseException 으로 받는다 — 건너뜀(Skipped)이 새어 나가면 시험이 빨강이 아니라 '건너뜀'이 된다.
    with pytest.raises(BaseException) as caught:
        _run_step(None, "아무 단계", tmp_path, {}, {})
    assert caught.type is pytest.fail.Exception, caught.type


def test_run_step_skips_locally_without_bash(monkeypatch, tmp_path):
    monkeypatch.setitem(globals(), "_find_bash", lambda: None)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    # BaseException 으로 받는다 — 건너뜀(Skipped)이 새어 나가면 시험이 빨강이 아니라 '건너뜀'이 된다.
    with pytest.raises(BaseException) as caught:
        _run_step(None, "아무 단계", tmp_path, {}, {})
    assert caught.type is pytest.skip.Exception, caught.type
