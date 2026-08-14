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
FORBIDDEN = ("SERVICE_KEY", "SECRET", "PASSWORD")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
