# -*- coding: utf-8 -*-
"""
층 표기 정규화 모듈
====================

소상공인 상권정보(층정보 컬럼), 건축물대장 층별개요 등 소스마다 제각각인
층 표기를 정수로 통일한다. `anthropic-skills:budongsan-data` 스킬 규격을
따르며, 상권정보 2026Q1 전국 17개 CSV의 층정보 컬럼 실측값 345종(결측률
54.75%, 2026-08-07 실측)을 기준으로 설계했다.

규격 (스킬 + 프로젝트 CLAUDE.md, 절대 규칙):
    지상 n층 = n
    지하 n층 = -n
    옥탑     = 99
    불명     = None   (0을 쓰지 않는다 — 지하/결측 오염 방지, DB CHECK 제약)

이 파일은 표준 라이브러리만 사용한다 (의존성 없음).
"""

import re
from typing import Optional


# 옥탑/옥상 층 코드 (규격 고정값)
ROOFTOP = 99

# 3자리 이상 숫자(100 이상)를 애매값으로 볼 기준선.
# 근거: 실측 345종 중 "101", "B103", "15015" 같은 값들은 "층+호"가 이어붙은
# 표기(예: 101 = 1층 1호, B103 = 지하1층 03호)로 보는 것이 물리적으로 가장
# 합리적이다 — 상가 건물에 실제 101층·지하103층이 존재할 수 없기 때문이다.
# 다만 이걸 자동으로 "// 100"해서 층을 뽑아내는 건 확증 없는 임의 추측이라
# CLAUDE.md 절대 규칙("판정 불가는 None. 절대 0이나 임의 추측 금지")에 걸린다.
# 그래서 100 이상 숫자는 전부 판정 불가로 보고 None을 반환한다.
AMBIGUOUS_THRESHOLD = 100

# 반지하/반지층 — 국토교통부·한국부동산원 자료에서도 반지하를 지하 범주로
# 분류하는 관행이 일반적이다. 정확히 몇 층인지는 알 수 없지만 "지하 방향"
# 이라는 사실은 분명하므로, 가장 얕은 지하인 -1로 매핑한다. (규격에 명시된
# 케이스는 아니라 이 파일의 판단 — 근거를 여기 docstring에 남긴다.)
BANJIHA_FLOOR = -1

# 지하 약칭 — '지1층'·'지4'처럼 '지' 바로 뒤에 숫자가 오는 표기.
# 건축물대장 층별개요·전유공용면적의 flrNoNm에서 '지1층'(지하1층)·'지4-지3'
# (지하4층~지하3층) 형태로 실제 관측된다(2026-08-07 강남구 실측). '지상2층'은
# '지' 뒤가 '상'이라 걸리지 않고, 방향 표시만 있고 숫자가 없는 '지'도 걸리지
# 않는다(그건 아래 숫자 추출 단계에서 None이 된다).
_UNDER_ABBR_RE = re.compile(r"^\s*지\s*\d")

# 복합 표기("1,2층" · "1~3층")에서 여러 층이 나오면 대표층으로 무엇을
# 고를지 정하는 값. 상가는 통상 접수(출입구)가 가장 낮은 층에 있으므로
# 최저층을 대표층으로 삼는다. (스킬 규격에 명시 없음 — 이 파일의 판단.)
_COMPOUND_SPLIT_RE = re.compile(r"[,/·、]|~|-(?!\d*$)")


def _split_with_delims(s: str):
    """s를 _COMPOUND_SPLIT_RE로 쪼개되, 각 조각 앞의 구분자도 함께 돌려준다.

    반환: [(직전 구분자 또는 첫 조각이면 None, 조각 문자열), ...]
    지하 문맥을 뒷조각에 물려줄지(force_under)는 "어떤 구분자로 이어졌는가"에
    따라 달라지므로(아래 normalize_floor 참고), 구분자 정보를 조각과 함께
    들고 있어야 한다.
    """
    parts = []
    pos = 0
    prev_delim = None
    for m in _COMPOUND_SPLIT_RE.finditer(s):
        parts.append((prev_delim, s[pos:m.start()]))
        prev_delim = m.group()
        pos = m.end()
    parts.append((prev_delim, s[pos:]))
    return parts


def _extract_single(token: str, force_under: bool = False) -> Optional[int]:
    """콤마/물결표로 쪼갠 조각 하나를 정수 층으로 변환한다. (내부 헬퍼)

    force_under: 복합 표기 전체에 "지하"/"B" 접두가 붙어 있어(예: "지하1~3층")
        각 조각에 개별 표시가 없어도 지하로 봐야 하는 경우 True.
    """
    s = token.strip()
    if not s:
        return None

    # 옥탑 / 옥상 / R(Rooftop)
    if "옥탑" in s or "옥상" in s:
        return ROOFTOP
    if re.match(r"^R\d*$", s, re.IGNORECASE):
        return ROOFTOP

    # 반지하 / 반지층 (규격 외 판단 — 위 BANJIHA_FLOOR 설명 참고)
    if "반지하" in s or "반지층" in s or s == "반":
        return BANJIHA_FLOOR

    # 지하 판별: "지하" 포함 / '지1층' 같은 지하 약칭 / B 로 시작(B1, B2 등) /
    # 앞에 마이너스 부호 / 복합 표기 전체의 지하 문맥(force_under)을 물려받은 경우
    is_under = bool(
        "지하" in s
        or _UNDER_ABBR_RE.match(s)
        or re.match(r"^\s*B", s, re.IGNORECASE)
        or s.strip().startswith("-")
        or force_under
    )

    # 숫자 추출 (앞자리 0 포함 가능 — int() 변환 시 자동 제거됨)
    m = re.search(r"\d+", s)
    if not m:
        # "지" 처럼 지하/지상 여부만 있고 숫자가 없는 경우 몇 층인지
        # 확정할 수 없다 — None (임의로 지하1층 등으로 추측하지 않는다).
        return None

    n = int(m.group())

    # 0 금지 (절대 규칙) — 결측/지하와 섞이면 집계가 오염된다.
    if n == 0:
        return None

    # 100 이상 = 층+호 복합 표기로 의심되는 애매값 (위 AMBIGUOUS_THRESHOLD 설명)
    if n >= AMBIGUOUS_THRESHOLD:
        return None

    return -n if is_under else n


def normalize_floor(raw) -> Optional[int]:
    """
    제각각인 층 표기를 정수로 통일한다.

    지상 n층 → n / 지하 n층 → -n / 옥탑 → 99 / 판정 불가 → None (0 금지).

    복합 표기("1,2층", "1~3층" 등 여러 층을 한 칸에 적은 경우)는 스킬
    규격에 정해진 방식이 없어, 이 함수는 대표층 = 최저층(지상 기준으로는
    가장 작은 층, 지하가 섞여 있으면 지하를 우선해 가장 얕은 지하)을
    선택한다 — 상가는 보통 가장 낮은 층에 출입구/접수가 있기 때문이다.
    판정 가능한 조각이 하나도 없으면 None.

    지하 문맥 전파는 '~'(범위)로 이어진 조각에만 적용한다. ','·'/' 같은
    열거 구분자는 각 조각이 서로 다른 층을 나열한 것이라 조각 자체의
    표기를 존중한다 — "지하1층,2층"은 지하1층과 2층(지상) 두 곳을 나열한
    것이지 지하1층·지하2층이 아니다.

    Args:
        raw: 원본 층 표기 문자열 (None 허용, 다른 타입도 str() 변환 시도)

    Returns:
        정수 층 (지상=양수, 지하=음수, 옥탑=99) 또는 None(불명)

    예시:
        >>> normalize_floor("3층"), normalize_floor("지하2층"), normalize_floor("B1")
        (3, -2, -1)
        >>> normalize_floor("옥탑"), normalize_floor(""), normalize_floor("0")
        (99, None, None)
        >>> normalize_floor("101"), normalize_floor("지"), normalize_floor("반지층")
        (None, None, -1)
        >>> normalize_floor("지1층"), normalize_floor("지상2층")   # '지N'은 지하 약칭
        (-1, 2)
        >>> normalize_floor("1,2층"), normalize_floor("지하1~3층")
        (1, -3)
    """
    if raw is None:
        return None

    s = str(raw).strip()
    if not s or s in {"-", "없음", "nan", "None", "NaN"}:
        return None

    # 복합 표기 분리 (콤마·슬래시·가운뎃점·물결표·범위 하이픈)
    # 순수 음수 표기("-1")까지 쪼개지지 않도록 뒤에 숫자만 남는 하이픈은
    # 제외한다 (_COMPOUND_SPLIT_RE의 음수 전방탐색 참고).
    raw_parts = [(delim, p) for delim, p in _split_with_delims(s) if p.strip()]
    if len(raw_parts) <= 1:
        return _extract_single(s)

    # "지하1~3층"처럼 맨 앞에만 지하/B 표시가 있고 뒷조각("3층")엔 표시가
    # 없어도, 범위('~')로 이어진 뒷조각까지는 그 문맥을 물려준다. 다만
    # ','·'/'로 이어진 조각(열거)은 물려받지 않고 자기 표기를 그대로 쓴다.
    global_under = bool(
        re.match(r"^\s*(지하|B)", s, re.IGNORECASE) or _UNDER_ABBR_RE.match(s))

    floors = []
    for delim, p in raw_parts:
        force = global_under and delim == "~"
        f = _extract_single(p, force_under=force)
        if f is not None:
            floors.append(f)
    if not floors:
        return None

    # 대표층 = 최저층. 지하(음수)가 섞여 있으면 더 깊은 지하가 "최저"이므로
    # min()이 자연스럽게 그걸 고른다 (예: [1,2] → 1 / [-1,-3] → -3).
    # 단, 옥탑(99)이 섞여 있으면 옥탑을 최저층으로 고르는 건 부적절하므로
    # 옥탑이 아닌 값이 있으면 그중 최저를, 전부 옥탑이면 99를 그대로 낸다.
    non_rooftop = [f for f in floors if f != ROOFTOP]
    return min(non_rooftop) if non_rooftop else ROOFTOP


def floor_label(floor: Optional[int]) -> str:
    """정규화된 층 정수를 사람이 읽는 표기로 되돌린다."""
    if floor is None:
        return "층 정보 없음"
    if floor == ROOFTOP:
        return "옥탑"
    if floor < 0:
        return "지하 {}층".format(abs(floor))
    return "{}층".format(floor)


if __name__ == "__main__":
    cases = [
        "1", "3층", "B1", "지하2층", "-1", "1F", "옥탑", "", None, "B2F",
        "지하 1 층", "0", "지", "반", "반지층", "101", "B103", "15015",
        "1,2층", "1~3층", "지하1~3층",
        "지1층", "지상2층", "지4-지3", "지5~지3, 지1",
    ]
    for c in cases:
        f = normalize_floor(c)
        print("  {!r:>14} -> {!r:>6}  ({})".format(c, f, floor_label(f)))
