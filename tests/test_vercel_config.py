# -*- coding: utf-8 -*-
"""
vercel.json 검증 — 정적 자산 장기 캐시 + 보안 헤더가 실제로 적용되는지 확인한다.

왜 이게 필요한가
----------------
적대검증에서 실측(2026-08-24, `curl.exe -sI .../assets/index-*.js`)으로 확정된 결함 2건:
① Vite 가 파일명에 콘텐츠 해시를 박는 `/assets/*` 파일이 매 방문 재검증(304 왕복)
   당하고 있었다 (`Cache-Control: public, max-age=0, must-revalidate`).
② 클릭재킹·MIME 스니핑 방지 보안 헤더가 0개였다.
vercel.json 의 `headers` 규칙으로 고쳤는데, JSON 파일 자체는 "왜 이 경로는 빠졌는지"
같은 설명을 못 담는다 — 그 설명은 이 테스트 파일에 남긴다.

가장 중요한 함정(반드시 이 테스트가 지켜야 함): `public/districts.geojson` 은
파일명이 고정이지만 내용은 `scripts/build_district_geojson.py` 가 다시 구울 때
바뀐다. `/assets/*` 처럼 장기 캐시를 걸면 상권 경계가 갱신돼도 브라우저가 옛 파일을
계속 붙들고 있게 된다 — 그래서 이 파일은 **의도적으로** `/assets/(.*)` 규칙 밖에
둔다(기본값 max-age=0, must-revalidate 가 정확히 맞다). 이 테스트는 그 의도가
실수로 깨지지 않는지 감시한다.
"""

import json
import re
from pathlib import Path

import pytest

VERCEL_JSON_PATH = Path(__file__).resolve().parent.parent / "vercel.json"


def load_config():
    """vercel.json 을 읽어 dict 로 반환한다."""
    with open(VERCEL_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def matched_header_values(config, path, header_key):
    """주어진 URL 경로에 실제로 적용될 특정 헤더의 값 목록을 반환한다.

    Vercel 은 `headers[].source` 를 정규식으로 다루고(공식 예시가 `/(.*)` 를 그대로
    정규식으로 씀), 그 경로에 매칭되는 규칙을 **전부** 적용한다(합집합). 이 함수는
    그 매칭 방식을 그대로 흉내 낸 순수 함수라, 실제로 Vercel 에 배포하지 않고도
    "이 경로엔 어떤 헤더가 붙는가"를 코드로 판정할 수 있다. 문자열 포함 검사가
    아니라 source 패턴을 정규식으로 컴파일해 매칭 여부를 가른다 — 그래야
    `/assets/(.*)` 가 assets 하위에만, `/(.*)` 가 모든 경로에 걸리는 것을 실제로
    증명하는 테스트가 된다.

    ⓘ 헤더 이름은 **대소문자를 무시**하고 비교한다(2026-10-03) — HTTP 헤더 이름은 대소문자를
       가리지 않아(RFC 9110 §5.1) `cache-control` 로 적어도 똑같이 붙는다. 글자 그대로 비교하면
       소문자 키로 장기 캐시가 `/(.*)` 에 붙어도 "붙은 헤더 없음"으로 읽혀 핵심 가드가 초록이었다.
       이 함수를 부르는 시험 전부가 함께 넓어진다.
    ⚠️ 못 보는 것: `source` 의 Vercel 경로 문법 중 정규식과 뜻이 다른 것(`:path*` 같은 이름 붙은
       자리) — 지금 vercel.json 은 정규식 꼴만 쓴다. `has`/`missing` 조건도 안 본다.
       이름이 다른 캐시 헤더(`CDN-Cache-Control` 등)와 앞뒤 공백이 붙은 키(`" Cache-Control"`)도
       다른 헤더로 친다.
    """
    values = []
    for rule in config.get("headers", []):
        pattern = re.compile("^" + rule["source"] + "$")
        if pattern.match(path):
            for header in rule["headers"]:
                if header["key"].lower() == header_key.lower():
                    values.append(header["value"])
    return values


def test_vercel_json_is_valid_json():
    """vercel.json 이 유효한 JSON 인가 — 문법 오류가 있으면 Vercel 배포 자체가 깨진다."""
    config = load_config()
    assert isinstance(config, dict)
    assert "headers" in config


def test_assets_rule_has_immutable_long_cache():
    """`/assets/(.*)` 규칙에 immutable + max-age=31536000(1년)이 있는가.

    Vite 가 콘텐츠 해시를 파일명에 박으므로(내용이 바뀌면 파일명도 바뀐다) 이 경로는
    불변이다 — 재검증 왕복 없이 브라우저가 영구 캐시해도 안전하다.
    """
    config = load_config()
    values = matched_header_values(config, "/assets/index-GHX9W_-e.js", "Cache-Control")
    assert len(values) == 1
    assert "max-age=31536000" in values[0]
    assert "immutable" in values[0]


def test_districts_geojson_not_matched_by_long_cache_rule():
    """⛔ 핵심 가드: districts.geojson 은 `/assets/*` 장기 캐시 규칙에 걸리면 안 된다.

    파일명은 고정인데 내용은 `build_district_geojson.py` 가 다시 구울 때 바뀐다.
    장기 캐시가 걸리면 상권 경계를 갱신해도 브라우저가 옛 지도를 계속 보여준다.
    이 파일은 `/assets/` 하위가 아니므로(공개 정적 파일은 `public/districts.geojson`
    → 배포 시 루트 `/districts.geojson`) 캐시 규칙에 안 걸리는 것이 맞는 설계다.
    """
    config = load_config()
    cache_values = matched_header_values(config, "/districts.geojson", "Cache-Control")
    assert cache_values == []


def test_catch_all_rule_does_not_leak_into_assets_only_path():
    """`/assets/(.*)` 는 assets 하위에만 매칭되고, 다른 경로엔 안 걸리는가.

    예: `/districts.geojson`, `/index.html` 은 `/assets/(.*)` 정규식과 매칭되지 않는다
    (문자열 포함이 아니라 진짜 정규식 판정이라는 것을 이 케이스로 증명한다).
    """
    config = load_config()
    for path in ("/districts.geojson", "/index.html", "/"):
        assert matched_header_values(config, path, "Cache-Control") == []


def test_security_headers_apply_to_all_paths():
    """보안 헤더 3종(nosniff·DENY·Referrer-Policy)이 전 경로 규칙(`/(.*)`)에 있는가."""
    config = load_config()
    for path in ("/", "/index.html", "/assets/index-abc123.js", "/districts.geojson"):
        assert matched_header_values(config, path, "X-Content-Type-Options") == ["nosniff"]
        assert matched_header_values(config, path, "X-Frame-Options") == ["DENY"]
        assert matched_header_values(config, path, "Referrer-Policy") == [
            "strict-origin-when-cross-origin"
        ]


def test_no_rewrites_configured():
    """rewrites(SPA 폴백)는 아직 없어야 한다 — 이 앱은 react-router 가 없다.

    지금 안 쓰는 설정을 미리 넣지 않는다(CLAUDE.md §2 Simplicity). 공유 링크 기능이
    라우터를 도입하는 PR 에서 그때 추가한다.
    """
    config = load_config()
    assert "rewrites" not in config


MIDDLEWARE_TS = Path(__file__).resolve().parent.parent / "middleware.ts"


def middleware_problems(text):
    """레포 루트 middleware.ts(Routing Middleware · 결정 0037)의 문제를 글 목록으로 낸다(빈 목록 = 정상).

    건물 주소(`/?…bld=…`)를 서버 조각으로 보내는 일은 vercel.json rewrite 가 아니라 이 파일이 한다 —
    Vercel 공식 vercel-json 문서 "The source property should NOT be a file because precedence is given
    to the filesystem prior to rewrites" — `/` 는 index.html 파일이라 rewrite 가 안 탄다.
    matcher 가 `/` 가 아니면 정적 파일·함수 주소까지 미들웨어를 탄다(SPA 폴백과 같은 위험).
    ⚠️ 못 보는 것: 판정 함수의 내용(vitest `src/lib/buildingRoute.test.ts`) · 실제 배포에서 불리는지(운영 실측).
    """
    problems = []
    if "matcher: '/'" not in text:
        problems.append("matcher 가 '/' 하나가 아님")
    if "from './src/lib/buildingRoute.js'" not in text:
        problems.append("판정을 buildingRoute.js(확장자 .js)로 부르지 않음")
    return problems


def test_middleware_exists_with_root_matcher():
    assert MIDDLEWARE_TS.is_file(), "middleware.ts 가 없음 — 건물 주소가 첫 화면 HTML 로만 나간다"
    assert middleware_problems(MIDDLEWARE_TS.read_text(encoding="utf-8")) == []


def test_control_middleware_wide_matcher_is_caught():
    """양성 대조 — matcher 를 넓히거나 확장자 없이 부르면 잡는다."""
    good = MIDDLEWARE_TS.read_text(encoding="utf-8")
    assert middleware_problems(good.replace("matcher: '/'", "matcher: '/(.*)'")) != []
    assert middleware_problems(good.replace("buildingRoute.js'", "buildingRoute'")) != []


# ── 양성 대조 — 가드가 쓰는 matched_header_values 가 키 대소문자와 무관하게 잡는가 (2026-10-03) ──
#
# 위 "붙은 헤더 = []" 단언들은 탐지가 죽어도 초록이다. 가짜 설정을 **같은 함수**에 넣어 본다.


def _fake_catch_all_cache(key):
    return {"headers": [
        {"source": "/(.*)", "headers": [{"key": key, "value": "public, max-age=31536000"}]},
    ]}


@pytest.mark.parametrize("key", ["Cache-Control", "cache-control", "CACHE-CONTROL"])
def test_long_cache_on_catch_all_is_seen_whatever_the_key_case(key):
    """`/(.*)` 에 장기 캐시가 붙으면 `/index.html`·`/districts.geojson` 에서 보여야 한다 — 키 대소문자 무관."""
    fake = _fake_catch_all_cache(key)
    for path in ("/index.html", "/districts.geojson"):
        assert matched_header_values(fake, path, "Cache-Control") == ["public, max-age=31536000"]


def test_the_asked_key_case_does_not_matter_either():
    """묻는 쪽 글자가 소문자여도 같은 결과 — 양쪽을 다 접는다."""
    fake = _fake_catch_all_cache("Cache-Control")
    assert matched_header_values(fake, "/", "cache-control") == ["public, max-age=31536000"]


def test_a_different_header_is_not_mistaken_for_cache_control():
    """대소문자만 접는다 — 이름이 다른 헤더까지 같다고 보면 안 된다."""
    fake = _fake_catch_all_cache("X-Cache-Control-Note")
    assert matched_header_values(fake, "/index.html", "Cache-Control") == []
