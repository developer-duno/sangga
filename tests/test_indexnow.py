"""IndexNow 열쇠 파일·알림 스크립트 가드 (2026-10-09).

지키는 것: ① public/<key>.txt 가 있고 **파일 이름 = 내용 = 스크립트 상수** ② 열쇠가 규격(8~128자 · a-z A-Z 0-9 -)
③ 본문의 host·keyLocation 이 정식 주소와 맞고, 남의 주소는 거부 ④ --dry-run 은 네트워크 0.
양성 대조: 열쇠 내용이 다르면 main 이 1 로 끝난다 · 남의 주소는 ValueError.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import indexnow_ping as ip  # noqa: E402

KEY_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def test_key_file_name_content_and_constant_agree():
    assert ip.KEY_FILE.is_file(), ip.KEY_FILE
    assert ip.KEY_FILE.name == f"{ip.KEY}.txt"
    raw = ip.KEY_FILE.read_bytes()
    assert raw.decode("utf-8") == ip.KEY, "열쇠 파일은 열쇠 글자만(줄바꿈·BOM 없이)"
    assert KEY_RE.match(ip.KEY), ip.KEY


def test_only_one_key_file_in_public():
    found = [p for p in (ROOT / "public").glob("*.txt") if KEY_RE.match(p.stem) and p.stem == p.read_text(encoding="utf-8").strip()]
    assert [p.name for p in found] == [f"{ip.KEY}.txt"]


def test_body_points_to_canonical_host():
    body = ip.build_body([ip.SITE])
    assert body["host"] == "sangga-one.vercel.app"
    assert body["keyLocation"] == f"{ip.SITE}{ip.KEY}.txt"
    assert body["key"] == ip.KEY
    assert body["urlList"] == [ip.SITE]


def test_control_foreign_url_is_rejected():
    with pytest.raises(ValueError):
        ip.build_body(["https://sangga-git-x.vercel.app/"])
    with pytest.raises(ValueError):
        ip.build_body([ip.SITE, "http://sangga-one.vercel.app/"])


def test_dry_run_does_not_touch_network(monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("dry-run 인데 네트워크를 건드림")
    monkeypatch.setattr(ip.urllib.request, "urlopen", boom)
    assert ip.main(["--dry-run"]) == 0
    assert "[dry-run]" in capsys.readouterr().out


def test_control_wrong_key_file_content_stops(monkeypatch, tmp_path):
    fake = tmp_path / f"{ip.KEY}.txt"
    fake.write_text("other", encoding="utf-8")
    monkeypatch.setattr(ip, "KEY_FILE", fake)
    assert ip.main(["--dry-run"]) == 1


# ── --from-sitemap · 1만 개씩 나눠 보내기 (2026-10-10) ──────────────────────────────

def _write_sitemap(path: Path, locs: list[str]) -> Path:
    items = "".join(f"<url><loc>{u}</loc></url>" for u in locs)
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>',
        encoding="utf-8",
    )
    return path


def _urls(n: int) -> list[str]:
    return [f"{ip.SITE}?bld={i}" for i in range(n)]  # '&' 없음 — _write_sitemap 은 이스케이프하지 않는다


@pytest.fixture
def fake_ping(monkeypatch):
    """ping 을 가짜로(네트워크 0) · sleep 은 끈다. calls 에 덩어리별 주소 목록이 쌓인다."""
    calls: list[list[str]] = []
    codes = {"seq": [200]}  # 호출 순서대로 돌려줄 코드(모자라면 마지막 값)

    def _ping(urls, timeout=20.0):
        calls.append(list(urls))
        seq = codes["seq"]
        return seq[min(len(calls) - 1, len(seq) - 1)]

    monkeypatch.setattr(ip, "ping", _ping)
    monkeypatch.setattr(ip.time, "sleep", lambda s: None)
    return calls, codes


def test_read_sitemap_urls_unescapes_amp_and_keeps_order(tmp_path):
    sm = _write_sitemap(tmp_path / "sm.xml", [
        f"{ip.SITE}?sgg=11680&amp;bld=B2", f"{ip.SITE}?sgg=11680&amp;bld=A1",
    ])
    assert ip.read_sitemap_urls(sm) == [f"{ip.SITE}?sgg=11680&bld=B2", f"{ip.SITE}?sgg=11680&bld=A1"]


def test_main_from_sitemap_merges_dedupes_and_skips_default_site(tmp_path, fake_ping):
    calls, _ = fake_ping
    a = _write_sitemap(tmp_path / "a.xml", [f"{ip.SITE}?x=1", f"{ip.SITE}?x=2"])
    b = _write_sitemap(tmp_path / "b.xml", [f"{ip.SITE}?x=2", f"{ip.SITE}?x=3"])
    assert ip.main(["--from-sitemap", str(a), "--from-sitemap", str(b), f"{ip.SITE}?x=0"]) == 0
    # 위치 인자가 먼저 · 중복은 처음 것만 · 기본값 SITE 는 안 들어간다
    assert calls == [[f"{ip.SITE}?x=0", f"{ip.SITE}?x=1", f"{ip.SITE}?x=2", f"{ip.SITE}?x=3"]]


def test_main_without_any_url_pings_default_site(fake_ping):
    calls, _ = fake_ping
    assert ip.main([]) == 0
    assert calls == [[ip.SITE]]


def test_chunks_boundaries():
    assert [len(c) for c in ip.chunks(list(range(10001)), ip.MAX_PER_POST)] == [10000, 1]
    assert [len(c) for c in ip.chunks(list(range(10000)), ip.MAX_PER_POST)] == [10000]
    assert ip.MAX_PER_POST == 10000  # 규격 값 고정


def test_main_splits_25000_into_three_posts(tmp_path, fake_ping, capsys):
    calls, _ = fake_ping
    sm = _write_sitemap(tmp_path / "big.xml", _urls(25000))
    assert ip.main(["--from-sitemap", str(sm)]) == 0
    assert [len(c) for c in calls] == [10000, 10000, 5000]
    out = capsys.readouterr().out
    assert "보낼 주소 25000개 · 덩어리 3개(1만 개씩)" in out
    assert out.count("덩어리 ") >= 4 and "덩어리 3/3: 응답 200" in out
    assert out.count("bld=") == 2  # 첫·끝 주소만 — 2.5만 줄을 뿜지 않는다


def test_main_small_list_prints_full_body(fake_ping, capsys):
    ip.main([f"{ip.SITE}?x=1", f"{ip.SITE}?x=2"])
    assert '"urlList"' in capsys.readouterr().out


def test_dry_run_with_sitemap_sends_nothing(tmp_path, fake_ping, capsys):
    calls, _ = fake_ping
    sm = _write_sitemap(tmp_path / "big.xml", _urls(25000))
    assert ip.main(["--from-sitemap", str(sm), "--dry-run"]) == 0
    assert calls == []
    assert "[dry-run] 보내지 않음" in capsys.readouterr().out


@pytest.mark.parametrize("bad_code", [400, 403, 422, 429])
def test_stop_after_first_chunk_on_stop_codes(tmp_path, fake_ping, bad_code):
    calls, codes = fake_ping
    codes["seq"] = [bad_code]
    sm = _write_sitemap(tmp_path / "big.xml", _urls(25000))
    assert ip.main(["--from-sitemap", str(sm)]) == 1
    assert len(calls) == 1


def test_connection_failure_exits_2(tmp_path, fake_ping):
    calls, codes = fake_ping
    codes["seq"] = [200, -1, 200]
    sm = _write_sitemap(tmp_path / "big.xml", _urls(25000))
    assert ip.main(["--from-sitemap", str(sm)]) == 2
    assert len(calls) == 3  # 연결 실패는 멈춤 코드가 아니다 — 나머지는 시도


def test_other_response_exits_1(fake_ping):
    _, codes = fake_ping
    codes["seq"] = [500]
    assert ip.main([f"{ip.SITE}?x=1"]) == 1


def test_control_foreign_url_in_sitemap_stops_before_sending(tmp_path, fake_ping):
    calls, _ = fake_ping
    locs = _urls(30) + ["https://example.com/other"]
    sm = _write_sitemap(tmp_path / "mixed.xml", locs)
    with pytest.raises(ValueError):
        ip.main(["--from-sitemap", str(sm)])
    assert calls == []
