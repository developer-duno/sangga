# -*- coding: utf-8 -*-
"""
scripts/make_env_local.py 1:1 단위 테스트.

이 스크립트가 존재하는 이유는 **관리자 키가 브라우저 번들에 실리는 사고**를 막는 것이다.
그러니 그 목적이 무너지는 자리를 집요하게 본다.

여기서 특히 지키는 것
---------------------
  · **이름이 아니라 값을 본다.** 2026-08-31 감사 전까지 이 스크립트의 유일한 검사는
    `EXPORT.values()`(코드에 박힌 상수 3개)에 금지어가 들었는지였다 — 상수를 상수와
    견주는 것이라 **한 번도 발동할 수 없는** 죽은 분기였다. 진짜 사고 경로("칸은 맞는데
    값이 관리자 키")는 통째로 무방비였다.
  · **형식이 둘이다.** 새 형식 `sb_secret_…`(이 프로젝트가 쓰는 것)과 옛 형식
    JWT(`"role":"service_role"`). 하나만 막으면 반쪽이다.
  · **오탐이 나면 안 된다.** 공개키(`sb_publishable_…`)·카카오 JS 키·URL 은 통과해야
    한다 — 여기서 잘못 막으면 사장님이 이 스크립트를 안 쓰고 손으로 옮기게 되고,
    그게 바로 이 스크립트가 막으려던 그 사고다.
  · **값은 어떤 경로로도 화면에 안 나온다.**
"""

import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import make_env_local as mel  # noqa: E402


# ── 1. looks_like_secret — 값의 생김새로 관리자 키를 알아본다 ────────────────


def _jwt(payload_json):
    """옛 형식(JWT) 을 흉내 낸다. 서명은 검사하지 않으므로 아무 글자나 둔다."""
    import base64

    def b64(s):
        return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")

    return "{}.{}.{}".format(b64('{"alg":"HS256","typ":"JWT"}'), b64(payload_json), "sig")


@pytest.mark.parametrize("value", [
    "sb_secret_abcdefghijklmnopqrstuv",                       # 새 형식 관리자 키
    "  sb_secret_abcdefghijklmnopqrstuv  ",                   # 앞뒤 공백이 있어도
])
def test_새형식_관리자키는_잡는다(value):
    assert mel.looks_like_secret(value) is True


def test_옛형식_service_role_JWT도_잡는다():
    assert mel.looks_like_secret(_jwt('{"iss":"supabase","role":"service_role"}')) is True


def test_옛형식_JWT_라도_공백이_섞인_role_을_잡는다():
    """대시보드에서 복사한 값이 다시 직렬화되며 공백이 들어갈 수 있다."""
    assert mel.looks_like_secret(_jwt('{"iss":"supabase", "role": "service_role"}')) is True


@pytest.mark.parametrize("value", [
    "sb_publishable_abcdefghijklmnopqrstuv",                  # 새 형식 공개키 — 통과해야 한다
    "https://xxxx.supabase.co",                               # URL
    "0123456789abcdef0123456789abcdef",                       # 카카오 JS 키(32자, 점 없음)
    "",                                                       # 빈 값
    None,                                                     # 아예 없음
])
def test_공개키_URL_카카오키는_막지_않는다(value):
    assert mel.looks_like_secret(value) is False


def test_옛형식_anon_JWT는_막지_않는다():
    assert mel.looks_like_secret(_jwt('{"iss":"supabase","role":"anon"}')) is False


def test_점이_셋이지만_JWT가_아니면_조용히_통과():
    """이 검사의 소관이 아닌 값에 대해 예외를 던지지 않는다 —
    스크립트가 죽으면 사장님이 손으로 옮기게 되고, 그게 더 위험하다."""
    assert mel.looks_like_secret("가.나.다") is False


# ── 2. main() — 관리자 키가 들어 있으면 .env.local 을 만들지 않는다 ──────────


def _run(tmp_path, monkeypatch, env_text):
    """가짜 .env 를 만들고 그 폴더를 ROOT 로 삼아 main() 을 돌린다."""
    (tmp_path / ".env").write_text(env_text, encoding="utf-8")
    monkeypatch.setattr(mel, "ROOT", str(tmp_path))
    return mel.main(), tmp_path / ".env.local"


_GOOD = (
    "SANGGA_SUPABASE_URL=https://xxxx.supabase.co\n"
    "SANGGA_SUPABASE_ANON_KEY=sb_publishable_aaaaaaaaaaaaaaaaaaaaaa\n"
    "SANGGA_KAKAO_JS_KEY=0123456789abcdef0123456789abcdef\n"
)


def test_정상_키면_파일을_만든다(tmp_path, monkeypatch):
    code, out = _run(tmp_path, monkeypatch, _GOOD)
    assert code == 0
    assert out.exists()
    assert "VITE_SUPABASE_ANON_KEY=sb_publishable_" in out.read_text(encoding="utf-8")


def test_ANON_칸에_관리자키가_있으면_중단하고_파일을_안_만든다(tmp_path, monkeypatch, capsys):
    """⛔ 이 테스트가 이 파일의 존재 이유다. 되돌리면(값 검사 삭제) 빨간불이 된다."""
    bad = _GOOD.replace("sb_publishable_aaaaaaaaaaaaaaaaaaaaaa",
                        "sb_secret_bbbbbbbbbbbbbbbbbbbbbb")
    code, out = _run(tmp_path, monkeypatch, bad)
    assert code == 1
    assert not out.exists(), ".env.local 이 만들어지면 안 된다"
    said = capsys.readouterr().out
    assert "SANGGA_SUPABASE_ANON_KEY" in said          # 어느 칸인지 알려준다
    assert "sb_secret_bbbb" not in said                # ⛔ 값은 절대 안 찍는다


def test_옛형식_service_role_JWT를_ANON_칸에_넣어도_중단한다(tmp_path, monkeypatch):
    bad = _GOOD.replace("sb_publishable_aaaaaaaaaaaaaaaaaaaaaa",
                        _jwt('{"iss":"supabase","role":"service_role"}'))
    code, out = _run(tmp_path, monkeypatch, bad)
    assert code == 1
    assert not out.exists()


def test_이미_있던_env_local_을_덮어쓰지_않고_남긴다(tmp_path, monkeypatch):
    """중단은 **쓰기 전에** 일어나야 한다 — 반쯤 쓰고 죽으면 더 나쁘다."""
    (tmp_path / ".env.local").write_text("VITE_SUPABASE_ANON_KEY=이전값\n", encoding="utf-8")
    bad = _GOOD.replace("sb_publishable_aaaaaaaaaaaaaaaaaaaaaa",
                        "sb_secret_bbbbbbbbbbbbbbbbbbbbbb")
    code, out = _run(tmp_path, monkeypatch, bad)
    assert code == 1
    assert out.read_text(encoding="utf-8") == "VITE_SUPABASE_ANON_KEY=이전값\n"
