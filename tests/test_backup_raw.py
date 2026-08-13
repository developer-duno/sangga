# -*- coding: utf-8 -*-
"""
scripts/backup_raw.py 1:1 단위 테스트.

공용 설정 파일(conftest.py 등) 없이 이 파일 안에서 import 경로를 직접 해결한다
(tests/test_normalize_floor.py와 동일한 방식).
"""

import json
import ntpath
import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import backup_raw  # noqa: E402
from backup_raw import (  # noqa: E402
    MANIFEST_NAME,
    build_manifest,
    build_robocopy_command,
    check_destination,
    compare_counts,
    free_space_bytes,
    human_size,
    parse_args,
    scan_source,
    sha256_of,
    verify_backup,
)


def _write(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


# ── 1. 삭제 전파 금지 (가장 중요한 안전장치) ────────────────────────────────


class TestNoMirrorFlag:
    """robocopy 인자에 /MIR 이 들어가면 안 된다.

    /MIR 은 원본에서 사라진 파일을 백업에서도 지운다. 원본을 실수로 날린 뒤
    백업이 한 번 돌면 재수집 불가능한 과거 분기 zip까지 함께 사라진다.
    "미러링이 더 깔끔하다"는 이유로 되돌리는 것을 막기 위한 회귀 테스트다.
    """

    def test_mirror_flag_is_absent(self):
        cmd = build_robocopy_command("src", "dst", "log.txt")
        assert "/MIR" not in cmd
        assert "/PURGE" not in cmd  # /PURGE 도 대상에서 삭제한다

    def test_recursive_copy_flag_is_present(self):
        cmd = build_robocopy_command("src", "dst", "log.txt")
        assert "/E" in cmd

    def test_retry_is_bounded(self):
        """기본 재시도는 100만 회다. 읽기 실패 하나에 사실상 멈춘 것처럼 보인다."""
        cmd = build_robocopy_command("src", "dst", "log.txt")
        assert "/R:2" in cmd
        assert "/W:5" in cmd

    def test_source_and_dest_order(self):
        cmd = build_robocopy_command("SRC", "DST", "L.log")
        assert cmd[0] == "robocopy"
        assert cmd[1] == "SRC"
        assert cmd[2] == "DST"

    def test_log_path_is_passed(self):
        cmd = build_robocopy_command("src", "dst", r"C:\a\b.log")
        assert r"/LOG:C:\a\b.log" in cmd

    def test_dot_directories_excluded(self):
        """결함 4 — 다른 세션이 .omc를 cwd로 써서 남긴 도구 상태 파일이 원본
        백업에 섞이면 안 된다. 되돌리면(/XD 제거) 이 테스트가 빨간불이 된다."""
        cmd = build_robocopy_command("src", "dst", "log.txt")
        assert "/XD" in cmd
        assert cmd[cmd.index("/XD") + 1] == ".*"


# ── 2. 인자 파싱 ────────────────────────────────────────────────────────────


class TestParseArgs:
    def test_defaults(self):
        opts = parse_args([])
        assert opts["dry_run"] is False
        assert opts["verify"] is False
        assert opts["dest"].endswith("sangga-raw-backup")
        assert opts["source"].endswith(os.path.join("data", "raw"))

    def test_dry_run_flag(self):
        assert parse_args(["--dry-run"])["dry_run"] is True

    def test_verify_flag(self):
        assert parse_args(["--verify"])["verify"] is True

    def test_unknown_arg_raises(self):
        """오타를 조용히 무시하면 '확인만'이 '실제 실행'으로 바뀐다."""
        with pytest.raises(ValueError) as e:
            parse_args(["--dryrun"])
        assert "알 수 없는 인자" in str(e.value)

    def test_help_is_rejected_not_silently_ignored(self):
        with pytest.raises(ValueError):
            parse_args(["--help"])

    def test_value_flag_without_value_raises(self):
        with pytest.raises(ValueError) as e:
            parse_args(["--dest"])
        assert "값이 필요합니다" in str(e.value)

    def test_empty_value_raises(self):
        with pytest.raises(ValueError) as e:
            parse_args(["--dest", "   "])
        assert "비어 있습니다" in str(e.value)

    def test_custom_dest_and_source(self):
        opts = parse_args(["--dest", "E:/bk", "--source", "/tmp/raw"])
        assert opts["dest"] == "E:/bk"
        assert opts["source"] == "/tmp/raw"

    def test_dry_run_with_verify_is_rejected(self):
        """--verify 는 백업본을 읽는 동작이라 --dry-run 과 뜻이 충돌한다."""
        with pytest.raises(ValueError):
            parse_args(["--dry-run", "--verify"])


# ── 3. 원본 조사 ────────────────────────────────────────────────────────────


class TestScanSource:
    def test_lists_files_with_sizes(self, tmp_path):
        _write(str(tmp_path / "a.txt"), b"abc")
        _write(str(tmp_path / "sub" / "b.bin"), b"xxxxx")
        entries = scan_source(str(tmp_path))
        assert entries == [("a.txt", 3), ("sub/b.bin", 5)]

    def test_relative_paths_use_forward_slash(self, tmp_path):
        """매니페스트는 OS에 상관없이 같은 키를 써야 대조가 된다."""
        _write(str(tmp_path / "x" / "y" / "z.txt"))
        entries = scan_source(str(tmp_path))
        assert entries[0][0] == "x/y/z.txt"

    def test_empty_directory(self, tmp_path):
        assert scan_source(str(tmp_path)) == []

    def test_result_is_sorted(self, tmp_path):
        for name in ("c.txt", "a.txt", "b.txt"):
            _write(str(tmp_path / name))
        assert [rel for rel, _ in scan_source(str(tmp_path))] == ["a.txt", "b.txt", "c.txt"]

    def test_dot_directories_are_excluded(self, tmp_path):
        """결함 4 — 다른 세션이 .omc를 cwd로 써서 남긴 도구 상태 파일이 원본
        파일 목록(=매니페스트·1차 대조의 대상)에 섞이면 안 된다. 되돌리면
        (dirnames 가지치기 제거) 이 테스트가 빨간불이 된다."""
        _write(str(tmp_path / "a.txt"), b"real")
        _write(str(tmp_path / ".omc" / "state" / "x.json"), b"tool state")
        entries = scan_source(str(tmp_path))
        assert entries == [("a.txt", 4)]

    def test_dot_directory_at_top_level_is_pruned_before_descending(self, tmp_path):
        """os.walk의 dirnames 가지치기가 실제로 하위 폴더까지 안 내려가게 하는지."""
        _write(str(tmp_path / ".omc" / "state" / "deep" / "y.txt"), b"xx")
        _write(str(tmp_path / "sub" / "b.txt"), b"y")
        entries = scan_source(str(tmp_path))
        assert entries == [("sub/b.txt", 1)]


# ── 4. 크기 표기 ────────────────────────────────────────────────────────────


class TestHumanSize:
    def test_bytes(self):
        assert human_size(0) == "0B"
        assert human_size(512) == "512B"

    def test_kilobytes(self):
        assert human_size(1024) == "1.0KB"

    def test_megabytes(self):
        assert human_size(1024 * 1024 * 3) == "3.0MB"

    def test_gigabytes(self):
        assert human_size(1024 ** 3 * 15) == "15.0GB"


# ── 5. 해시 ────────────────────────────────────────────────────────────────


class TestSha256:
    def test_known_value_of_empty_file(self, tmp_path):
        p = tmp_path / "empty"
        _write(str(p), b"")
        assert sha256_of(str(p)) == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_content_change_changes_hash(self, tmp_path):
        p = tmp_path / "f"
        _write(str(p), b"aaa")
        first = sha256_of(str(p))
        _write(str(p), b"aab")
        assert sha256_of(str(p)) != first

    def test_large_file_read_in_chunks(self, tmp_path):
        """청크 경계에서 내용이 누락되지 않는지 (chunk_size보다 큰 파일)."""
        p = tmp_path / "big"
        _write(str(p), b"z" * (1024 * 1024 + 7))
        assert sha256_of(str(p), chunk_size=1024) == sha256_of(str(p), chunk_size=64 * 1024)


# ── 6. 1차 대조 (개수·크기) ─────────────────────────────────────────────────


class TestCompareCounts:
    def test_all_present(self, tmp_path):
        src, dst = tmp_path / "s", tmp_path / "d"
        _write(str(src / "a.txt"), b"abc")
        _write(str(dst / "a.txt"), b"abc")
        missing, mismatch = compare_counts(scan_source(str(src)), str(dst))
        assert missing == [] and mismatch == []

    def test_detects_missing_file(self, tmp_path):
        src, dst = tmp_path / "s", tmp_path / "d"
        _write(str(src / "a.txt"), b"abc")
        os.makedirs(str(dst), exist_ok=True)
        missing, mismatch = compare_counts(scan_source(str(src)), str(dst))
        assert missing == ["a.txt"] and mismatch == []

    def test_detects_size_mismatch(self, tmp_path):
        src, dst = tmp_path / "s", tmp_path / "d"
        _write(str(src / "a.txt"), b"abcdef")
        _write(str(dst / "a.txt"), b"abc")
        missing, mismatch = compare_counts(scan_source(str(src)), str(dst))
        assert missing == [] and mismatch == ["a.txt"]

    def test_nested_path_is_resolved(self, tmp_path):
        src, dst = tmp_path / "s", tmp_path / "d"
        _write(str(src / "sub" / "a.txt"), b"ab")
        _write(str(dst / "sub" / "a.txt"), b"ab")
        missing, mismatch = compare_counts(scan_source(str(src)), str(dst))
        assert missing == [] and mismatch == []

    def test_same_size_different_content_is_not_caught(self, tmp_path):
        """크기 대조로는 내용 손상을 못 잡는다 — 그래서 --verify(해시)가 따로 있다."""
        src, dst = tmp_path / "s", tmp_path / "d"
        _write(str(src / "a.txt"), b"aaa")
        _write(str(dst / "a.txt"), b"bbb")
        missing, mismatch = compare_counts(scan_source(str(src)), str(dst))
        assert missing == [] and mismatch == []


# ── 7. 매니페스트 왕복 + 손상 탐지 ──────────────────────────────────────────


class TestManifestRoundTrip:
    def _prepare(self, tmp_path):
        src, dst = tmp_path / "s", tmp_path / "d"
        _write(str(src / "a.txt"), b"hello")
        _write(str(src / "sub" / "b.txt"), b"world!")
        entries = scan_source(str(src))
        manifest = build_manifest(str(src), entries)
        os.makedirs(str(dst), exist_ok=True)
        for rel, _size in entries:
            _write(str(dst / rel), open(str(src / rel), "rb").read())
        with open(os.path.join(str(dst), MANIFEST_NAME), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)
        return str(src), str(dst)

    def test_manifest_shape(self, tmp_path):
        src = tmp_path / "s"
        _write(str(src / "a.txt"), b"hello")
        m = build_manifest(str(src), scan_source(str(src)))
        assert m["file_count"] == 1
        assert m["total_bytes"] == 5
        assert m["files"]["a.txt"]["size"] == 5
        assert len(m["files"]["a.txt"]["sha256"]) == 64
        assert "generated_at_kst" in m

    def test_verify_passes_on_intact_backup(self, tmp_path):
        _src, dst = self._prepare(tmp_path)
        _manifest, missing, corrupt = verify_backup(dst)
        assert missing == [] and corrupt == []

    def test_verify_detects_silent_corruption(self, tmp_path):
        """크기는 그대로인 채 내용만 바뀐 손상 — 1차 대조는 못 잡는 종류."""
        _src, dst = self._prepare(tmp_path)
        _write(os.path.join(dst, "a.txt"), b"HELLO")  # 5바이트 그대로
        _manifest, missing, corrupt = verify_backup(dst)
        assert missing == [] and corrupt == ["a.txt"]

    def test_verify_detects_deleted_file(self, tmp_path):
        _src, dst = self._prepare(tmp_path)
        os.remove(os.path.join(dst, "sub", "b.txt"))
        _manifest, missing, corrupt = verify_backup(dst)
        assert missing == ["sub/b.txt"] and corrupt == []

    def test_verify_without_manifest_raises(self, tmp_path):
        dst = tmp_path / "d"
        os.makedirs(str(dst), exist_ok=True)
        with pytest.raises(RuntimeError) as e:
            verify_backup(str(dst))
        assert "해시 목록이 없습니다" in str(e.value)


# ── 8. 대상 드라이브 확인 ───────────────────────────────────────────────────


class TestCheckDestination:
    def test_existing_path_passes(self, tmp_path):
        check_destination(str(tmp_path / "not-created-yet"))  # 예외가 없으면 통과

    def test_missing_drive_raises(self, monkeypatch):
        """외장 드라이브를 안 꽂은 채 실행하면 조용히 성공해선 안 된다.

        check_destination은 os.path.splitdrive로 드라이브 문자를 뽑아 그 드라이브가
        마운트돼 있는지 본다. POSIX(CI=Ubuntu)에는 드라이브 개념이 없어 splitdrive가
        항상 빈 문자열을 돌려주고, 그러면 검사 자체가 조용히 no-op된다 — 그래서
        예전엔 os.name=='nt'가 아니면 통째로 스킵했다(CI에서 이 안전장치가 한 번도
        안 돎).

        여기서는 os.path.splitdrive를 표준 라이브러리 ntpath(윈도우 경로 규칙)로
        바꿔치기해, 실행 OS와 무관하게 '윈도우처럼 드라이브 문자를 해석했을 때
        그 드라이브가 없으면 막는다'는 실제 로직을 그대로 실행시킨다. Q: 드라이브는
        이 프로젝트가 실제로 쓰는 외장 SSD 문자(F:)와 다른, 존재할 리 없는 문자다.
        """
        monkeypatch.setattr(backup_raw.os.path, "splitdrive", ntpath.splitdrive)
        with pytest.raises(RuntimeError) as e:
            check_destination(r"Q:\sangga-raw-backup")
        assert "연결" in str(e.value)


class TestFreeSpace:
    def test_returns_positive_for_existing_dir(self, tmp_path):
        free = free_space_bytes(str(tmp_path))
        assert free is not None and free > 0

    def test_walks_up_to_existing_parent(self, tmp_path):
        """대상 폴더는 아직 없을 수 있다 — 상위로 거슬러 올라가 재야 한다."""
        free = free_space_bytes(str(tmp_path / "a" / "b" / "c"))
        assert free is not None and free > 0
