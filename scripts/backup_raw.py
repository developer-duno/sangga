# -*- coding: utf-8 -*-
"""
data/raw 원본 데이터를 외부 저장소로 백업한다.

왜 필요한가:
    `data/raw`는 .gitignore 대상이라 git에 없다. 그 안의
    `sangkwon_zips/` 과거 분기 zip은 포털에서 내려간 뒤에는 **다시 받을 수 없다**.
    지금 구조에서는 이 PC의 디스크 하나가 고장나면 통째로 소멸한다(단일 장애점).

설계 판단 (바꾸기 전에 읽을 것):

    1. **robocopy /MIR 을 쓰지 않는다.**
       /MIR 은 원본에서 사라진 파일을 백업에서도 지운다. 원본을 실수로 날린 뒤
       이 스크립트가 한 번 돌면 백업까지 같이 사라진다. 재수집 불가 데이터에는
       치명적이라, 삭제를 전파하지 않는 /E (추가·갱신만) 를 쓴다.
       그 대가로 원본에서 지운 파일이 백업에 남아 용량이 늘지만,
       "지워진 게 남는 것"이 "남아야 할 게 지워지는 것"보다 훨씬 낫다.

    2. **복사만으로는 백업이 아니다.**
       복사된 파일이 나중에 조용히 깨질 수 있다(실제로 백업 대상 드라이브에는
       과거 파일시스템 오류의 흔적인 FOUND.000 폴더가 있다). 그래서 원본의
       SHA-256 목록을 함께 저장하고, `--verify` 로 백업본을 실제로 다시 읽어
       대조한다.

    3. **대상 드라이브가 없으면 즉시 멈춘다.**
       외장 드라이브를 꽂지 않은 채 실행하면, 확인 없이는 엉뚱한 위치에 폴더를
       만들어 "백업했다"는 착각만 남는다.

사용법:
    python scripts/backup_raw.py --dry-run    # 무엇을 복사할지만 확인 (쓰기 0)
    python scripts/backup_raw.py              # 백업 실행 + 해시 목록 생성
    python scripts/backup_raw.py --verify     # 백업본을 다시 읽어 해시 대조
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

# 백업 대상 기본값 — 외장 SSD. 프로젝트가 있는 드라이브와 물리적으로 분리돼야 한다.
DEFAULT_DEST = r"F:\sangga-raw-backup"

# 원본 위치 (레포 루트 기준)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE = os.path.join(REPO_ROOT, "data", "raw")

MANIFEST_NAME = "manifest-sha256.json"
LOG_DIR_NAME = "_backup_logs"

KST = timezone(timedelta(hours=9))

# robocopy 종료 코드는 비트 플래그다. 8 이상만 실제 실패.
#   0=변화 없음 1=복사함 2=대상에만 있는 파일 4=불일치 8=복사 실패 16=치명적 오류
ROBOCOPY_FAIL_THRESHOLD = 8


def today_kst():
    return datetime.now(KST)


# ── 인자 파싱 ────────────────────────────────────────────────────────────────


def _reject_unknown_args(argv, bool_flags, value_flags):
    """인식 못 하는 인자를 조용히 무시하지 않고 에러로 멈춘다.

    왜: `--dryrun` 같은 오타가 무시되면 "확인만"이 "실제 실행"으로 바뀐다.
    수집기(collect_building_ledger.py)에서 실제로 겪은 사고라 같은 방식으로 막는다.
    """
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in value_flags:
            i += 2
            continue
        if a in bool_flags:
            i += 1
            continue
        raise ValueError(
            "알 수 없는 인자: {!r}\n  쓸 수 있는 인자: {}".format(
                a, " ".join(sorted(set(bool_flags) | set(value_flags)))
            )
        )


def parse_args(argv):
    _reject_unknown_args(
        argv,
        bool_flags=("--dry-run", "--verify"),
        value_flags=("--dest", "--source"),
    )
    opts = {
        "dest": DEFAULT_DEST,
        "source": DEFAULT_SOURCE,
        "dry_run": "--dry-run" in argv,
        "verify": "--verify" in argv,
    }
    for flag, key in (("--dest", "dest"), ("--source", "source")):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise ValueError("{} 뒤에 값이 필요합니다.".format(flag))
            value = argv[i + 1]
            if not value.strip():
                raise ValueError("{} 값이 비어 있습니다.".format(flag))
            opts[key] = value
    if opts["dry_run"] and opts["verify"]:
        raise ValueError("--dry-run 과 --verify 는 함께 쓸 수 없습니다.")
    return opts


# ── 원본 조사 ────────────────────────────────────────────────────────────────


def scan_source(source):
    """원본의 파일 목록을 (상대경로, 바이트) 로 모은다. 상대경로는 항상 / 구분자."""
    entries = []
    for dirpath, _dirnames, filenames in os.walk(source):
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, source).replace("\\", "/")
            entries.append((rel, os.path.getsize(full)))
    entries.sort()
    return entries


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "{:.1f}{}".format(n, unit) if unit != "B" else "{}B".format(n)
        n /= 1024.0
    return "{:.1f}TB".format(n)


def sha256_of(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 대상 확인 ────────────────────────────────────────────────────────────────


def check_destination(dest):
    """대상 드라이브가 실제로 연결돼 있는지 확인한다.

    왜: 외장 드라이브를 꽂지 않은 채 실행하면 robocopy 가 엉뚱한 위치에 폴더를
    만들고 성공으로 끝난다. "백업했다"는 착각이 백업 없음보다 위험하다.
    """
    drive = os.path.splitdrive(os.path.abspath(dest))[0]
    if drive and not os.path.isdir(drive + os.sep):
        raise RuntimeError(
            "백업 대상 드라이브에 접근할 수 없습니다: {}\n"
            "  외장 드라이브가 연결돼 있는지 확인하세요.".format(drive)
        )


def free_space_bytes(path):
    """대상 경로가 속한 볼륨의 여유 공간. 확인 불가 시 None.

    대상 폴더는 아직 없을 수 있으므로, 존재하는 상위 폴더까지 거슬러 올라가서 잰다.
    """
    probe = os.path.abspath(path)
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None


# ── 복사 ────────────────────────────────────────────────────────────────────


def build_robocopy_command(source, dest, log_path):
    """robocopy 인자를 만든다.

    /E   하위 폴더 포함(빈 폴더도). **/MIR 이 아니다** — 위 설계 판단 1 참조.
    /R:2 /W:5   읽기 실패 시 2회만 재시도(기본값은 100만 회라 사실상 멈춘 것처럼 보인다)
    /NFL /NDL   파일·폴더 목록은 로그 파일에만, 화면에는 요약만
    /NP  퍼센트 표시 생략(로그가 제어문자로 더러워진다)
    """
    return [
        "robocopy",
        source,
        dest,
        "/E",
        "/R:2",
        "/W:5",
        "/NFL",
        "/NDL",
        "/NP",
        "/TEE",
        "/LOG:{}".format(log_path),
    ]


def run_robocopy(source, dest, log_path):
    cmd = build_robocopy_command(source, dest, log_path)
    proc = subprocess.run(cmd, shell=False)
    code = proc.returncode
    if code >= ROBOCOPY_FAIL_THRESHOLD:
        raise RuntimeError(
            "robocopy 실패 (종료 코드 {}). 로그를 확인하세요: {}".format(code, log_path)
        )
    return code


# ── 검증 ────────────────────────────────────────────────────────────────────


def compare_counts(source_entries, dest):
    """개수·총 크기만 빠르게 대조한다(해시 없이). 빠진 파일 목록을 돌려준다."""
    missing = []
    size_mismatch = []
    for rel, size in source_entries:
        target = os.path.join(dest, rel.replace("/", os.sep))
        if not os.path.isfile(target):
            missing.append(rel)
        elif os.path.getsize(target) != size:
            size_mismatch.append(rel)
    return missing, size_mismatch


def build_manifest(source, source_entries):
    files = {}
    total = len(source_entries)
    for idx, (rel, size) in enumerate(source_entries, 1):
        full = os.path.join(source, rel.replace("/", os.sep))
        print("  해시 계산 {}/{}  {}".format(idx, total, rel), flush=True)
        files[rel] = {"size": size, "sha256": sha256_of(full)}
    return {
        "generated_at_kst": today_kst().isoformat(),
        "source": os.path.abspath(source),
        "file_count": len(files),
        "total_bytes": sum(v["size"] for v in files.values()),
        "files": files,
    }


def verify_backup(dest):
    """백업본을 실제로 다시 읽어 해시를 대조한다.

    왜: 복사 직후엔 멀쩡해도 저장 매체에서 조용히 깨질 수 있다. 개수·크기 대조는
    그런 손상을 못 잡는다(크기는 그대로인 채 내용만 바뀌기 때문).
    """
    manifest_path = os.path.join(dest, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        raise RuntimeError(
            "해시 목록이 없습니다: {}\n"
            "  먼저 `python scripts/backup_raw.py` 로 백업을 한 번 실행하세요.".format(
                manifest_path
            )
        )
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    files = manifest.get("files", {})
    missing, corrupt = [], []
    total = len(files)
    for idx, (rel, info) in enumerate(sorted(files.items()), 1):
        target = os.path.join(dest, rel.replace("/", os.sep))
        print("  검증 {}/{}  {}".format(idx, total, rel), flush=True)
        if not os.path.isfile(target):
            missing.append(rel)
            continue
        if sha256_of(target) != info["sha256"]:
            corrupt.append(rel)
    return manifest, missing, corrupt


# ── 실행 ────────────────────────────────────────────────────────────────────


def main():
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        opts = parse_args(sys.argv[1:])
    except ValueError as e:
        print("[에러] {}".format(e))
        return 2

    source = opts["source"]
    dest = opts["dest"]

    print("=" * 78)
    print("data/raw 백업")
    print("=" * 78)
    print("  원본 : {}".format(os.path.abspath(source)))
    print("  대상 : {}".format(os.path.abspath(dest)))
    print()

    if not os.path.isdir(source):
        print("[에러] 원본 폴더가 없습니다: {}".format(os.path.abspath(source)))
        return 1

    # --verify 는 원본을 건드리지 않고 백업본만 읽는다.
    if opts["verify"]:
        try:
            check_destination(dest)
            manifest, missing, corrupt = verify_backup(dest)
        except (RuntimeError, ValueError) as e:
            print("[에러] {}".format(e))
            return 1
        print()
        print("  해시 목록 생성 시각 : {}".format(manifest.get("generated_at_kst")))
        print("  대조한 파일         : {}개".format(manifest.get("file_count")))
        print("  사라진 파일         : {}개".format(len(missing)))
        print("  내용이 깨진 파일    : {}개".format(len(corrupt)))
        for rel in (missing + corrupt)[:20]:
            print("    - {}".format(rel))
        if missing or corrupt:
            print()
            print("[판정] 백업이 온전하지 않습니다. 다시 백업하세요.")
            return 1
        print()
        print("[판정] 백업본 전량이 원본과 일치합니다.")
        return 0

    entries = scan_source(source)
    total_bytes = sum(size for _rel, size in entries)
    print("  파일 {}개 / {}".format(len(entries), human_size(total_bytes)))

    by_top = {}
    for rel, size in entries:
        top = rel.split("/")[0] if "/" in rel else "(최상위)"
        by_top[top] = by_top.get(top, 0) + size
    for top, size in sorted(by_top.items(), key=lambda kv: -kv[1]):
        print("    {:<20} {}".format(top, human_size(size)))
    print()

    try:
        check_destination(dest)
    except RuntimeError as e:
        print("[에러] {}".format(e))
        return 1

    free = free_space_bytes(dest)
    if free is not None:
        print("  대상 여유 공간 : {}".format(human_size(free)))
        if free < total_bytes:
            print(
                "[에러] 여유 공간이 원본보다 작습니다 ({} < {}).".format(
                    human_size(free), human_size(total_bytes)
                )
            )
            return 1

    if opts["dry_run"]:
        print()
        print("--dry-run 지정 — 복사·해시 계산을 건너뜁니다.")
        print("  실제 실행: python scripts/backup_raw.py")
        return 0

    log_dir = os.path.join(dest, LOG_DIR_NAME)
    os.makedirs(log_dir, exist_ok=True)
    stamp = today_kst().strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(log_dir, "robocopy-{}.log".format(stamp))

    print()
    print("복사 중... (로그: {})".format(log_path), flush=True)
    try:
        code = run_robocopy(source, dest, log_path)
    except (RuntimeError, FileNotFoundError) as e:
        print("[에러] {}".format(e))
        return 1
    print("  robocopy 종료 코드 {} (8 미만이면 정상)".format(code))

    missing, size_mismatch = compare_counts(entries, dest)
    print()
    print("  1차 대조 (개수·크기)")
    print("    빠진 파일     : {}개".format(len(missing)))
    print("    크기 다른 파일: {}개".format(len(size_mismatch)))
    for rel in (missing + size_mismatch)[:20]:
        print("      - {}".format(rel))
    if missing or size_mismatch:
        print()
        print("[판정] 복사가 완전하지 않습니다. 로그를 확인하세요: {}".format(log_path))
        return 1

    print()
    print("해시 목록 생성 중... (원본을 다시 읽습니다)", flush=True)
    manifest = build_manifest(source, entries)
    manifest_path = os.path.join(dest, MANIFEST_NAME)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    summary = {
        "finished_at_kst": today_kst().isoformat(),
        "source": os.path.abspath(source),
        "dest": os.path.abspath(dest),
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "robocopy_exit_code": code,
        "robocopy_log": log_path,
    }
    with open(
        os.path.join(log_dir, "summary-{}.json".format(stamp)), "w", encoding="utf-8"
    ) as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 78)
    print("[완료] 파일 {}개 / {} 백업".format(len(entries), human_size(total_bytes)))
    print("  해시 목록 : {}".format(manifest_path))
    print("  실행 기록 : {}".format(log_dir))
    print()
    print("  다음에 백업이 멀쩡한지 확인하려면:")
    print("    python scripts/backup_raw.py --verify")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
