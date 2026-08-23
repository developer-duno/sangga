# -*- coding: utf-8 -*-
"""
scripts/check_district_source_update.py 1:1 단위 테스트.

네트워크는 전부 monkeypatch로 막는다(실제 포털에 접속하지 않음).
공용 설정 파일(conftest.py 등) 없이 이 파일 안에서 import 경로를 직접 해결한다.
"""

import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import check_district_source_update as chk  # noqa: E402


# ── 실측 HTML 조각 (2026-08-15 라이브에서 그대로 떠 온 것) ────────────────────

# 소진공: "등록일"이 "수정일" 바로 앞에 **같은 모양**으로 있다 — 여기에 낚이면
# 감시가 2021년 날짜를 붙들고 영영 변화를 못 본다.
SBIZ_HTML = (
    '등록일</strong> <div class="value">2021-09-29</div> </li> '
    '<li class="half"> <strong class="key">수정일</strong> '
    '<div class="value">2025-08-12</div> </li> '
    '<li class="half"> <strong class="key">기타 유의사항</strong>'
)

# 서울: 라벨 앞뒤 공백이 없는 판과 있는 판이 둘 다 실측됐다.
SEOUL_HTML_A = (
    '<th scope="row">데이터 갱신일</th> <td><span class="en">2026.06.11.</span></td>'
)
SEOUL_HTML_B = (
    '<tr><th scope="row"> 데이터 갱신일 </th> '
    '<td><span class="en">2026.06.11.</span></td> </tr>'
)


# ── 소진공 수정일 뽑기 ────────────────────────────────────────────────────────


def test_parse_sbiz_takes_update_not_register_date():
    """등록일(2021-09-29)이 앞에 있어도 수정일을 집어야 한다."""
    assert chk.parse_sbiz_update_date(SBIZ_HTML) == "2025-08-12"


def test_parse_sbiz_tolerates_newlines():
    """실제 HTML 은 태그 사이에 개행·들여쓰기가 들어간다."""
    html = (
        '<strong class="key">수정일</strong>\n'
        '            <div class="value">2026-01-15</div>\n'
    )
    assert chk.parse_sbiz_update_date(html) == "2026-01-15"


def test_parse_sbiz_raises_when_label_missing():
    """못 찾은 걸 조용히 넘기면 감시가 장님이 된 채 초록불만 켜진다."""
    with pytest.raises(ValueError) as e:
        chk.parse_sbiz_update_date('<div class="value">2025-08-12</div>')
    assert "수정일" in str(e.value)


def test_parse_sbiz_raises_on_empty():
    with pytest.raises(ValueError):
        chk.parse_sbiz_update_date("")


# ── 서울 갱신일 뽑기 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("html", [SEOUL_HTML_A, SEOUL_HTML_B])
def test_parse_seoul_handles_both_variants(html):
    assert chk.parse_seoul_update_date(html) == "2026-06-11"


def test_parse_seoul_pads_single_digit_month_and_day():
    """`2026.6.1.` 도 같은 자(YYYY-MM-DD)로 맞춰야 두 원천을 나란히 비교할 수 있다."""
    html = '<th scope="row">데이터 갱신일</th><td><span class="en">2026.6.1.</span></td>'
    assert chk.parse_seoul_update_date(html) == "2026-06-01"


def test_parse_seoul_tolerates_newlines():
    html = (
        '<tr>\n  <th scope="row">데이터 갱신일</th>\n'
        '  <td>\n    <span class="en">2025.12.31.</span>\n  </td>\n</tr>'
    )
    assert chk.parse_seoul_update_date(html) == "2025-12-31"


def test_parse_seoul_raises_when_label_missing():
    with pytest.raises(ValueError) as e:
        chk.parse_seoul_update_date('<td><span class="en">2026.06.11.</span></td>')
    assert "갱신일" in str(e.value)


def test_parse_seoul_raises_on_empty():
    with pytest.raises(ValueError):
        chk.parse_seoul_update_date("")


# ── 변화 고르기 ───────────────────────────────────────────────────────────────


KNOWN = {"sbiz": "2025-08-12", "seoul": "2026-06-11"}


def test_find_changes_empty_when_same():
    assert chk.find_changes(dict(KNOWN), KNOWN) == []


def test_find_changes_one_side_only():
    got = chk.find_changes({"sbiz": "2026-01-15", "seoul": "2026-06-11"}, KNOWN)
    assert [(c["key"], c["known"], c["current"]) for c in got] == [
        ("sbiz", "2025-08-12", "2026-01-15")
    ]


def test_find_changes_both_sides_keep_fixed_order():
    """순서가 흔들리면 제목이 달라져 중복 방지(제목 비교)가 깨진다."""
    got = chk.find_changes({"sbiz": "2026-01-15", "seoul": "2026-07-01"}, KNOWN)
    assert [c["key"] for c in got] == ["sbiz", "seoul"]


def test_find_changes_catches_date_going_backwards():
    """포털이 날짜를 되돌려도(재게시) 사람이 봐야 할 사건이다 — 부등호가 아니라 != 다."""
    got = chk.find_changes({"sbiz": "2020-01-01", "seoul": "2026-06-11"}, KNOWN)
    assert len(got) == 1 and got[0]["current"] == "2020-01-01"


def test_find_changes_ignores_missing_source():
    """한쪽만 조회된 상황에서 없는 쪽을 '변경'으로 잘못 알리지 않는다."""
    assert chk.find_changes({"sbiz": "2025-08-12"}, KNOWN) == []


# ── 이슈 제목·본문 ────────────────────────────────────────────────────────────


def test_issue_title_contains_new_dates():
    """제목에 새 날짜가 박혀야 같은 갱신으로 이슈가 두 번 열리지 않는다(중복 방지 키)."""
    changes = chk.find_changes({"sbiz": "2026-01-15", "seoul": "2026-06-11"}, KNOWN)
    t = chk.build_issue_title(changes)
    assert t == "상권 원천 갱신: 소진공 2026-01-15"


def test_issue_title_is_deterministic_for_both():
    changes = chk.find_changes({"sbiz": "2026-01-15", "seoul": "2026-07-01"}, KNOWN)
    assert chk.build_issue_title(changes) == "상권 원천 갱신: 소진공 2026-01-15, 서울 2026-07-01"


def test_issue_body_has_the_commands_for_the_changed_source_only():
    changes = chk.find_changes({"sbiz": "2026-01-15", "seoul": "2026-06-11"}, KNOWN)
    body = chk.build_issue_body(changes)
    assert "fetch_sbiz_district.py" in body
    assert "load_sbiz_district.py" in body
    # 안 바뀐 쪽 받는 명령까지 넣으면 쓸데없는 재적재를 시킨다
    assert "fetch_seoul_district.py" not in body
    # 서울(11) 거부 주의가 빠지면 정본이 둘로 갈라진다
    assert "거부" in body


def test_issue_body_has_common_followup_steps():
    changes = chk.find_changes({"sbiz": "2026-01-15", "seoul": "2026-07-01"}, KNOWN)
    body = chk.build_issue_body(changes)
    assert "fetch_seoul_district.py" in body
    assert "district_rone_map.csv" in body
    assert "build_district_geojson.py" in body
    assert "post_load.py" in body
    assert "backup_raw.py" in body
    # 기준선을 올리라는 안내가 두 상수를 모두 짚어야 한다
    assert "SBIZ_KNOWN_UPDATE" in body
    assert "SEOUL_KNOWN_UPDATE" in body


def test_issue_body_commands_run_in_powershell():
    """사장님 터미널은 PowerShell 이다 — `cd /d/sangga` 는 거기서 안 된다(2026-08-22).

    코드펜스 라벨도 함께 맞춘다. 나머지 줄은 전부 `python …` 호출이라 PowerShell 에서
    그대로 돈다(bash 전용 문법은 이 본문에 없다).
    """
    changes = chk.find_changes({"sbiz": "2026-01-15", "seoul": "2026-07-01"}, KNOWN)
    body = chk.build_issue_body(changes)
    assert r"cd D:\sangga" in body
    assert "/d/sangga" not in body
    assert "```bash" not in body


def test_issue_body_shows_old_and_new_dates():
    changes = chk.find_changes({"sbiz": "2026-01-15", "seoul": "2026-06-11"}, KNOWN)
    body = chk.build_issue_body(changes)
    assert "2025-08-12" in body and "2026-01-15" in body


# ── GITHUB_OUTPUT ────────────────────────────────────────────────────────────


def test_write_github_output_noop_without_env(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    changes = chk.find_changes({"sbiz": "2026-01-15"}, KNOWN)
    assert chk.write_github_output(changes) is False


def test_write_github_output_writes_found_true(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    chk.write_github_output(chk.find_changes({"sbiz": "2026-01-15"}, KNOWN))
    text = out.read_text(encoding="utf-8")
    assert "found=true" in text
    assert "title=상권 원천 갱신: 소진공 2026-01-15" in text


def test_write_github_output_writes_found_false(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    chk.write_github_output([])
    text = out.read_text(encoding="utf-8")
    assert "found=false" in text
    # 빈 제목이어야 다음 단계가 이슈를 열지 않는다
    assert "title=\n" in text


# ── main() 흐름 ───────────────────────────────────────────────────────────────


def _patch_fetch(monkeypatch, sbiz=None, seoul=None):
    """네트워크를 타지 않게 조회 함수 두 개를 갈아끼운다."""
    monkeypatch.setattr(
        chk, "fetch_sbiz_update_date", lambda: sbiz or chk.SBIZ_KNOWN_UPDATE
    )
    monkeypatch.setattr(
        chk, "fetch_seoul_update_date", lambda: seoul or chk.SEOUL_KNOWN_UPDATE
    )


def test_main_reports_no_change(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch)
    assert chk.main([]) == 0
    assert "변경                : 없음" in capsys.readouterr().out
    # 변경이 없으면 이슈 본문 파일을 만들지 않는다
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_writes_issue_body_when_changed(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, sbiz="2026-01-15")
    assert chk.main([]) == 0
    body = (tmp_path / chk.ISSUE_BODY_FILE).read_text(encoding="utf-8")
    assert "2026-01-15" in body
    assert "fetch_sbiz_district.py" in body


def test_main_fails_when_portal_unreachable(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)

    def boom():
        raise RuntimeError("연결 실패")

    monkeypatch.setattr(chk, "fetch_sbiz_update_date", boom)
    monkeypatch.setattr(chk, "fetch_seoul_update_date", boom)
    assert chk.main([]) == 1
    assert "상권 원천 조회 실패" in capsys.readouterr().err
    assert not (tmp_path / chk.ISSUE_BODY_FILE).exists()


def test_main_fails_when_page_structure_changed(monkeypatch, capsys, tmp_path):
    """파싱 실패(ValueError)도 '변경 없음'이 아니라 **실패**여야 한다."""
    monkeypatch.chdir(tmp_path)

    def boom():
        raise ValueError("'수정일' 칸을 못 찾았습니다")

    monkeypatch.setattr(chk, "fetch_sbiz_update_date", boom)
    monkeypatch.setattr(chk, "fetch_seoul_update_date", lambda: chk.SEOUL_KNOWN_UPDATE)
    assert chk.main([]) == 1


def test_main_json_output(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _patch_fetch(monkeypatch, sbiz="2026-01-15")
    assert chk.main(["--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["known"]["sbiz"] == chk.SBIZ_KNOWN_UPDATE
    assert data["current"]["sbiz"] == "2026-01-15"
    assert [c["key"] for c in data["changes"]] == ["sbiz"]


def test_main_does_not_touch_network(monkeypatch, tmp_path):
    """테스트가 실수로 진짜 포털을 두드리지 않는지 못을 박는다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    def forbidden(*a, **k):
        raise AssertionError("테스트가 네트워크를 탔습니다")

    monkeypatch.setattr(chk.urllib.request, "urlopen", forbidden)
    _patch_fetch(monkeypatch)
    assert chk.main([]) == 0


# ── 감시 워크플로우 자체 점검 (조용한 실패 방지) ─────────────────────────────

# 이 감시의 진짜 실패 모드는 "갱신을 못 알아보는 것"이 아니라 **감시가 죽었는데 아무도
# 모르는 것**이다. 2026-08-10 형제 감시의 예약 실행이 죽은 걸 나흘 뒤에야 알았다.
# 아래 두 가지가 사라지면 알림 경로가 통째로 조용해지므로 여기서 붙잡는다.

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "district-source-watch.yml")
FAILURE_BODY_PATH = os.path.join(REPO_ROOT, ".github", "district-watch-failure-issue.md")


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_workflow_opens_an_issue_when_the_watch_itself_fails():
    wf = _read_text(WORKFLOW_PATH)
    assert "if: failure()" in wf, "실패해도 조용하면 원천 갱신을 통째로 놓친다"
    # 실패 알림도 결국 이슈로 나가야 사람 눈에 띈다
    assert wf.count("gh issue create") >= 2, "갱신 알림 + 실패 알림 두 갈래여야 한다"


def test_workflow_uses_the_issue_body_this_script_writes():
    """스크립트가 쓰는 파일명과 워크플로우가 읽는 파일명이 어긋나면 이슈가 빈 채로 열린다."""
    assert chk.ISSUE_BODY_FILE in _read_text(WORKFLOW_PATH)


def test_workflow_does_not_collide_with_the_sibling_cron():
    """같은 시각에 몰리면 큐가 밀릴 때 둘이 함께 드롭된다."""
    wf = _read_text(WORKFLOW_PATH)
    sibling = _read_text(
        os.path.join(REPO_ROOT, ".github", "workflows", "sangkwon-quarterly-watch.yml")
    )
    assert 'cron: "30 0 * * 1"' in wf
    assert 'cron: "30 0 * * 1"' not in sibling


def test_failure_issue_body_file_exists_and_tells_the_human_what_to_do():
    """워크플로우가 이 파일을 그대로 읽어 이슈 본문으로 쓴다 — 사라지면 알림이 실패한다."""
    assert ".github/district-watch-failure-issue.md" in _read_text(WORKFLOW_PATH)
    body = _read_text(FAILURE_BODY_PATH)
    assert "check_district_source_update.py" in body, "내 PC에서 확인할 명령이 있어야 한다"
    assert "SBIZ_KNOWN_UPDATE" in body, "기준선 올리는 걸 잊으면 다음 갱신을 못 본다"
    assert "SEOUL_KNOWN_UPDATE" in body


# ── 기준선·주소 자체 점검 ─────────────────────────────────────────────────────


@pytest.mark.parametrize("value", [chk.SBIZ_KNOWN_UPDATE, chk.SEOUL_KNOWN_UPDATE])
def test_known_update_is_a_valid_date(value):
    """기준선을 손으로 올리다 오타가 나면 감시가 매주 헛알림을 낸다."""
    assert len(value) == 10 and value[4] == "-" and value[7] == "-", value
    y, m, d = value.split("-")
    assert y.isdigit() and m.isdigit() and d.isdigit(), value
    assert y.startswith("20"), value
    assert "01" <= m <= "12", value
    assert "01" <= d <= "31", value


def test_dataset_pages_match_the_fetchers():
    """주소가 형제 수집기와 갈라지면 엉뚱한 페이지를 감시하게 된다."""
    for path, url in (
        (os.path.join(REPO_ROOT, "scripts", "collectors", "fetch_sbiz_district.py"), chk.SBIZ_PAGE),
        (os.path.join(REPO_ROOT, "scripts", "collectors", "fetch_seoul_district.py"), chk.SEOUL_PAGE),
    ):
        src = _read_text(path)
        # 소진공 쪽은 데이터셋 번호를 format 으로 끼워 넣으므로 번호로 대조한다
        needle = url if url in src else url.rsplit("/", 2)[1]
        assert needle in src, path
