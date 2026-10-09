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
