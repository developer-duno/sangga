# -*- coding: utf-8 -*-
"""
.env 에서 브라우저가 쓸 값만 골라 .env.local 을 만든다.

왜 스크립트로 하나:
  Vite 는 `VITE_` 로 시작하는 환경변수만 브라우저 번들에 넣는다. 손으로 옮기다
  관리자 키(SERVICE_KEY)에 실수로 `VITE_` 를 붙이면 그 키가 브라우저에 그대로
  실려 누구나 DB 를 고칠 수 있게 된다. 옮길 항목을 코드로 고정해 그 사고를 막는다.

  값을 화면에 찍지 않는다 — 채팅·로그에 남으면 회수할 방법이 없다.

사용법:
    python scripts/make_env_local.py
"""

import os
import sys

# 브라우저에 내보낼 항목만. 여기 없는 키는 절대 .env.local 로 가지 않는다.
EXPORT = {
    "SANGGA_SUPABASE_URL": "VITE_SUPABASE_URL",
    "SANGGA_SUPABASE_ANON_KEY": "VITE_SUPABASE_ANON_KEY",
    # 카카오맵 JavaScript 키(결정 0010). 이 키는 원래 브라우저에 실려 나가는 공개키이고,
    # 카카오 콘솔에 등록한 도메인에서만 동작한다 — 남이 가져가도 자기 사이트에서는 안 쓰인다.
    "SANGGA_KAKAO_JS_KEY": "VITE_KAKAO_JS_KEY",
}

# 실수로라도 내보내면 안 되는 것 (이름에 이게 들어가면 즉시 중단).
#
# ⚠️ 이 검사는 **EXPORT 목록을 손대는 실수**만 막는다. 위 EXPORT 의 이름들은 코드에 박힌
#    상수라 여기에 걸릴 일이 평소엔 없다 — 그래서 이것만으로는 "칸은 맞는데 값이 관리자
#    키" 라는 진짜 사고를 못 막는다. 그 몫은 아래 looks_like_secret() 이 맡는다.
FORBIDDEN = ("SERVICE_KEY", "SECRET", "PASSWORD")

# 관리자 키를 **값의 생김새**로 알아본다 (2026-08-31 감사).
#
# 진짜 사고 경로는 이렇다: 사장님이 Supabase 대시보드에서 공개키와 관리자 키가 나란히
# 놓인 화면을 보고 `.env` 의 ANON 칸에 **관리자 키를 붙여넣는다.** 칸 이름은 그대로라
# 위 이름 검사는 통과하고, 그 값이 `VITE_` 를 달고 브라우저 번들에 실려 배포된다.
# 그 뒤로는 누구나 개발자도구로 그 키를 읽어 RLS 를 우회하고 전 테이블을 읽고 지운다.
#
# ⛔ 형식이 **두 가지**다 — 하나만 보면 반쪽이다.
#   · 새 형식(이 프로젝트가 쓰는 것, 2026-08-31 실측): 공개키 `sb_publishable_…` /
#     관리자 키 `sb_secret_…`. JWT 가 아니라 점(.)이 하나도 없다.
#   · 옛 형식: 점 두 개짜리 JWT 이고, 가운데 payload 안에 `"role":"service_role"` 이 들어 있다.
#     다른 프로젝트나 옛 문서에서 복사해 오면 이쪽이 올 수 있다.
SECRET_KEY_PREFIXES = ("sb_secret_",)
JWT_SERVICE_ROLE_MARK = '"role":"service_role"'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def looks_like_secret(value):
    """이 값이 관리자(비밀) 키처럼 생겼나 — 순수 함수라 테스트가 여기만 보면 된다.

    ⛔ 값을 **돌려주지도 찍지도 않는다.** True/False 만 낸다.
    공개키(`sb_publishable_…`)·카카오 JS 키·URL 에는 걸리지 않아야 한다.
    """
    v = str(value or "").strip()
    if not v:
        return False
    if any(v.startswith(p) for p in SECRET_KEY_PREFIXES):
        return True
    # 옛 형식(JWT): header.payload.signature. 가운데만 base64url 로 풀어 role 을 본다.
    parts = v.split(".")
    if len(parts) != 3:
        return False
    import base64
    body = parts[1]
    body += "=" * (-len(body) % 4)          # base64url 은 패딩이 빠져 있다
    try:
        payload = base64.urlsafe_b64decode(body).decode("utf-8", errors="replace")
    except Exception:
        return False                        # 못 풀면 JWT 가 아니다 — 이 검사의 소관이 아니다
    return JWT_SERVICE_ROLE_MARK in payload.replace(" ", "")


def read_env(path):
    """.env 를 dict 로. 값은 반환만 하고 출력하지 않는다."""
    out = {}
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main():
    # cp949 콘솔에서 한글·특수문자(—) 출력이 UnicodeEncodeError 로 죽지 않게 —
    # 형제 스크립트들(backup_raw.py·build_district_geojson.py)과 같은 처방.
    # ⚠️ 이 스크립트는 마지막 줄에서 죽어도 .env.local 은 이미 써진 상태라 더 헷갈린다
    #    (파일은 멀쩡한데 종료 코드만 1). 2026-08-14 실측으로 발견.
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    src = os.path.join(ROOT, ".env")
    dst = os.path.join(ROOT, ".env.local")

    if not os.path.exists(src):
        print(".env 파일이 없습니다: {}".format(src))
        return 1

    env = read_env(src)

    missing = [k for k in EXPORT if not env.get(k)]
    if missing:
        print(".env 에 다음 항목이 없습니다: {}".format(", ".join(missing)))
        return 1

    for target in EXPORT.values():
        if any(bad in target.upper() for bad in FORBIDDEN):
            print("내보내면 안 되는 이름이 목록에 있습니다: {}".format(target))
            return 1

    # 이름이 아니라 **값**을 본다 — 위 검사가 못 막는 진짜 사고 경로(위 상수 머리말 참조).
    for src_key in EXPORT:
        if looks_like_secret(env[src_key]):
            print("[중단] .env 의 {} 칸에 **관리자(비밀) 키**로 보이는 값이 들어 있습니다."
                  .format(src_key))
            print("  이대로 두면 그 키가 브라우저 번들에 실려 배포되고, 누구나 개발자도구로")
            print("  꺼내 RLS 를 우회할 수 있습니다. 공개키(sb_publishable_… 로 시작)로 바꾸세요.")
            print("  ⚠️ 값은 일부러 화면에 안 찍습니다 — 채팅·로그에 남으면 회수할 수 없습니다.")
            return 1

    lines = [
        "# scripts/make_env_local.py 가 .env 에서 만들었다 — 직접 고치지 말 것.",
        "# VITE_ 로 시작하는 값은 브라우저에 그대로 실린다. 공개키(anon)만 넣는다.",
    ]
    for src_key, vite_key in EXPORT.items():
        lines.append("{}={}".format(vite_key, env[src_key]))

    with open(dst, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")

    # 값은 찍지 않고 어떤 이름을 넣었는지만 보고한다.
    print(".env.local 생성 완료 — {}".format(", ".join(EXPORT.values())))
    print("(.gitignore 의 `.env.*` 규칙으로 커밋되지 않는다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
