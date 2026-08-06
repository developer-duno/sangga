# -*- coding: utf-8 -*-
"""
normalize_floor() 전수 적용 리포트
====================================

scripts/floor_values_2026q1.txt (2026Q1 상권정보 전국 CSV 층정보 컬럼
distinct 345종 + 빈도)에 normalize_floor()를 실제로 돌려, 빈도 가중
커버리지와 미커버(None) 상위 값을 보여준다. 읽기 전용 — raw 데이터/원본
집계 파일을 수정하지 않는다.

실행:
    PYTHONIOENCODING=utf-8 python scripts/floor_coverage_report.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from normalize_floor import normalize_floor  # noqa: E402

VALUES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "floor_values_2026q1.txt")


def main():
    total_freq = 0
    mapped_freq = 0
    none_freq = 0
    mapped_types = 0
    none_types = 0
    none_entries = []  # (freq, raw, )
    zero_leak = []  # 혹시라도 0을 반환하면 절대 규칙 위반이므로 별도 수집

    with open(VALUES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            freq_str, raw = line.split("\t", 1)
            freq = int(freq_str)
            total_freq += freq

            result = normalize_floor(raw)

            if result == 0:
                zero_leak.append((freq, raw))

            if result is None:
                none_freq += freq
                none_types += 1
                none_entries.append((freq, raw))
            else:
                mapped_freq += freq
                mapped_types += 1

    none_entries.sort(key=lambda x: -x[0])

    print("=" * 70)
    print("normalize_floor() 전수 적용 리포트 — 2026Q1 상권정보 층정보 345종")
    print("=" * 70)
    print("")
    print("[ 종 수 기준 ]")
    print("  정수 매핑 성공: {}종 / 전체 {}종".format(mapped_types, mapped_types + none_types))
    print("  None(불명)    : {}종".format(none_types))
    print("")
    print("[ 빈도 가중 커버리지 (실제 행 수 기준 — 이게 진짜 중요한 지표) ]")
    print("  매핑 성공: {:,}건 / 전체 {:,}건 -> {:.4f}%".format(
        mapped_freq, total_freq, mapped_freq * 100.0 / total_freq))
    print("  None    : {:,}건 / 전체 {:,}건 -> {:.4f}%".format(
        none_freq, total_freq, none_freq * 100.0 / total_freq))
    print("")
    print("[ 0 반환 여부 (절대 규칙 위반 검사 — 0건이어야 정상) ]")
    print("  0을 반환한 raw값 수: {}".format(len(zero_leak)))
    for freq, raw in zero_leak:
        print("    freq={} raw={!r}".format(freq, raw))
    print("")
    print("[ None(미커버) 상위 10종 — 빈도순 ]")
    print("  {:<8} {:<10} {}".format("빈도", "원시값", "결과"))
    for freq, raw in none_entries[:10]:
        print("  {:<8} {!r:<10} {}".format(freq, raw, normalize_floor(raw)))
    print("")
    print("[ None(미커버) 전체 목록 — {}종 ]".format(len(none_entries)))
    for freq, raw in none_entries:
        print("  freq={:<8} raw={!r}".format(freq, raw))


if __name__ == "__main__":
    main()
