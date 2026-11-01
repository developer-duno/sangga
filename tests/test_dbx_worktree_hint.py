# -*- coding: utf-8 -*-
"""dbx.parts() 의 「git 워크트리라 .env 가 없다」 힌트 시험 (2단 마무리 규칙화, 2026-11-01).

워크트리에서 빌드·적재 스크립트를 돌리면 .env 가 없어 SANGGA_DATABASE_URL 오류로 멈춘다.
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


def test_worktree_git_file_adds_hint(tmp_path, monkeypatch):
    # 양성: 워크트리의 .git 은 「gitdir: …」 한 줄짜리 파일이다.
    (tmp_path / ".git").write_text("gitdir: /somewhere/.git/worktrees/x\n", encoding="utf-8")
    msg = _message(monkeypatch, tmp_path)
    assert "워크트리" in msg
    assert "본 폴더" in msg


def test_main_checkout_git_dir_has_no_hint(tmp_path, monkeypatch):
    # 음성: 본 폴더의 .git 은 폴더 — 문구 변화 0.
    (tmp_path / ".git").mkdir()
    msg = _message(monkeypatch, tmp_path)
    assert "워크트리" not in msg
    assert "본 폴더" not in msg


def test_first_line_kept_in_both_cases(tmp_path, monkeypatch):
    as_file = tmp_path / "wt"
    as_file.mkdir()
    (as_file / ".git").write_text("gitdir: /somewhere/.git/worktrees/x\n", encoding="utf-8")
    as_dir = tmp_path / "main"
    as_dir.mkdir()
    (as_dir / ".git").mkdir()
    for root in (as_file, as_dir):
        assert _message(monkeypatch, root).splitlines()[0] == FIRST_LINE
