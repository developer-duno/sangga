# -*- coding: utf-8 -*-
"""dbx.parts() 의 「이 폴더에 .env 가 없다」 힌트 시험 (2단 마무리 규칙화, 2026-11-01).

git 워크트리·검사관 사본(clone --shared)에서 빌드·적재 스크립트를 돌리면 .env 가 없어
SANGGA_DATABASE_URL 오류로 멈춘다. 본 폴더에는 .env 가 늘 있으니 「.env 없음」이 곧 워크트리·사본이다.
처방(합친 뒤 본 폴더에서)을 오류 문구가 스스로 말하게 했다. DB·네트워크 0.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import dbx  # noqa: E402

FIRST_LINE = "SANGGA_DATABASE_URL 이 .env 에 없습니다."


def _message(monkeypatch, root):
    """root 를 프로젝트 루트로 흉내 내고 parts() 가 내는 SystemExit 메시지를 돌려 준다."""
    monkeypatch.setattr(dbx, "PROJECT_ROOT", str(root))
    # 앞선 시험이 load_dotenv 로 os.environ 에 넣어 뒀을 수 있다 — 지우지 않으면 SystemExit 가 안 난다.
    monkeypatch.delenv("SANGGA_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        dbx.parts()
    return str(exc.value)


def test_no_env_file_adds_hint(tmp_path, monkeypatch):
    # 양성: .env 가 없는 폴더(워크트리·사본).
    msg = _message(monkeypatch, tmp_path)
    assert ".env 파일이 없습니다" in msg
    assert "본 폴더" in msg


def test_existing_env_file_has_no_hint(tmp_path, monkeypatch):
    # 음성: 빈 .env 가 있는 폴더(본 폴더) — load_dotenv 가 읽어도 변수는 없다. 문구 변화 0.
    (tmp_path / ".env").write_bytes(b"")
    msg = _message(monkeypatch, tmp_path)
    assert ".env 파일이 없습니다" not in msg
    assert "본 폴더" not in msg


def test_first_line_kept_in_both_cases(tmp_path, monkeypatch):
    without_env = tmp_path / "wt"
    without_env.mkdir()
    with_env = tmp_path / "main"
    with_env.mkdir()
    (with_env / ".env").write_bytes(b"")
    for root in (without_env, with_env):
        assert _message(monkeypatch, root).splitlines()[0] == FIRST_LINE
