# -*- coding: utf-8 -*-
"""
링크 미리보기 그림(Open Graph) `public/og-image.png` 1200×630 을 만든다.

👤 2026-10-09 G 건물 둘 · 글꼴 = 윈도우 맑은 고딕 · 로컬 전용(CI 안 돎)

왜 스크립트로 하나:
  카카오톡·메신저·검색 결과가 링크를 펼칠 때 보여 주는 그림이다. 손으로 그리면
  다음에 고칠 사람이 같은 그림을 다시 만들 수 없다 — 도형 좌표·색·글자를 코드로 둔다.
  왼쪽 도형은 `public/favicon.svg` 의 rect 아홉 개를 32 격자에서 그대로 비례 확대한 것이라,
  파비콘을 바꾸면 아래 `FAVICON_RECTS` 도 함께 고친다.

  ⛔ 글자는 그림 안에 박힌다 — 열린 지역(서울·대전)이 늘면 `SUBTITLE` 을 고치고 다시 돌린다
     (index.html 설명 글·src/lib/seo.ts 와 함께 · .claude/rules/feature-notes.md 「검색·AI 노출 머리글」).
  ⓘ Pillow 는 pyproject 에 없다 — 이 스크립트만 쓴다(시험은 PNG 머리 바이트로 크기만 본다).
     없으면: python -m pip install pillow
  ⓘ 외부 서비스 0 · 글꼴 파일은 레포에 넣지 않는다.

사용법 (프로젝트 루트에서):
    python scripts/make_og_image.py
"""

import os
import sys

OUT_PATH = os.path.join("public", "og-image.png")
WIDTH, HEIGHT = 1200, 630
SCALE = 2  # 두 배로 그린 뒤 줄여 도형 가장자리를 매끄럽게(안티앨리어싱)

BG = "#f7f7f8"
BLUE = "#2f5fd0"
WHITE = "#ffffff"
SAND = "#f3e7cf"
INK = "#1c1d21"
MUTED = "#6b6d76"

FONT_REGULAR = "C:/Windows/Fonts/malgun.ttf"
FONT_BOLD = "C:/Windows/Fonts/malgunbd.ttf"

TITLE = "상가 층별 스택뷰"
SUBTITLE = "서울·대전 상가 건물을 층별·업종별로 — 공공데이터"
URL_TEXT = "sangga-one.vercel.app"

TITLE_PX = 92
SUBTITLE_PX = 44
URL_PX = 32
MIN_TITLE_PX = 64

ICON_PX = 360  # 32 격자 → 360px (배율 11.25)
MARGIN = 56
GAP = 48  # 도형과 글자 사이
# ⓘ 제목 92px 은 폭 708px 라 도형 360px 옆(남는 폭 680px)에 안 들어간다 → 아래 맞춤이 88px 로 줄인다.

# public/favicon.svg 의 rect 아홉 개 (x, y, w, h, rx, 색) — 32 격자 좌표 그대로.
FAVICON_RECTS = (
    (0, 0, 32, 32, 7, BLUE),
    (6, 6, 9, 20, 1, WHITE),
    (17, 13, 9, 13, 1, WHITE),
    (8.5, 9, 4, 2, 0, BLUE),
    (8.5, 13, 4, 2, 0, BLUE),
    (8.5, 17, 4, 2, 0, BLUE),
    (19.5, 16, 4, 2, 0, BLUE),
    (19.5, 20, 4, 2, 0, BLUE),
    (6, 26, 20, 2, 0, SAND),
)


def wrap_words(draw, text, font, max_w):
    """띄어쓰기 단위로 끊어 max_w 안에 들어가는 줄 목록을 만든다."""
    lines, cur = [], ""
    for word in text.split(" "):
        trial = word if not cur else f"{cur} {word}"
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def main():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow 가 없습니다 — python -m pip install pillow", file=sys.stderr)
        return 2
    for path in (FONT_REGULAR, FONT_BOLD):
        if not os.path.exists(path):
            print(f"글꼴이 없습니다: {path} (윈도우 맑은 고딕 필요)", file=sys.stderr)
            return 2

    s = SCALE
    img = Image.new("RGB", (WIDTH * s, HEIGHT * s), BG)
    draw = ImageDraw.Draw(img)

    # ── 왼쪽: 파비콘과 같은 도형 ─────────────────────────────────────────────
    k = ICON_PX / 32 * s
    ox = MARGIN * s
    oy = (HEIGHT - ICON_PX) // 2 * s
    for x, y, w, h, rx, color in FAVICON_RECTS:
        box = (ox + x * k, oy + y * k, ox + (x + w) * k - 1, oy + (y + h) * k - 1)
        if rx:
            draw.rounded_rectangle(box, radius=rx * k, fill=color)
        else:
            draw.rectangle(box, fill=color)

    # ── 오른쪽: 글자 ────────────────────────────────────────────────────────
    tx = (MARGIN + ICON_PX + GAP) * s
    max_w = (WIDTH - MARGIN) * s - tx
    top = (HEIGHT - ICON_PX) // 2 * s
    bottom = top + ICON_PX * s

    title_px = TITLE_PX
    while True:
        title_font = ImageFont.truetype(FONT_BOLD, title_px * s)
        if draw.textlength(TITLE, font=title_font) <= max_w or title_px <= MIN_TITLE_PX:
            break
        title_px -= 2
    sub_font = ImageFont.truetype(FONT_REGULAR, SUBTITLE_PX * s)
    url_font = ImageFont.truetype(FONT_REGULAR, URL_PX * s)

    # 제목: 도형 윗선에 글자 윗선을 맞춘다.
    tb = draw.textbbox((0, 0), TITLE, font=title_font)
    y = top - tb[1]
    draw.text((tx, y), TITLE, font=title_font, fill=INK)
    y = top + (tb[3] - tb[1]) + 40 * s

    sub_lines = wrap_words(draw, SUBTITLE, sub_font, max_w)
    line_h = int(SUBTITLE_PX * 1.45) * s
    for line in sub_lines:
        sb = draw.textbbox((0, 0), line, font=sub_font)
        draw.text((tx, y - sb[1]), line, font=sub_font, fill=INK)
        y += line_h

    # 주소: 도형 아랫선에 글자 아랫선을 맞춘다.
    ub = draw.textbbox((0, 0), URL_TEXT, font=url_font)
    draw.text((tx, bottom - ub[3]), URL_TEXT, font=url_font, fill=MUTED)

    # 넘침 점검 — 글자 상자 하나라도 그림 밖이면 멈춘다.
    widest = max(
        draw.textlength(TITLE, font=title_font),
        max(draw.textlength(line, font=sub_font) for line in sub_lines),
        draw.textlength(URL_TEXT, font=url_font),
    )
    if tx + widest > WIDTH * s or y - line_h + SUBTITLE_PX * s > bottom - (ub[3] - ub[1]):
        print("글자가 자리를 넘칩니다 — 크기·줄바꿈을 조정하세요", file=sys.stderr)
        return 1

    out = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
    out.save(OUT_PATH, format="PNG", optimize=True)
    size = os.path.getsize(OUT_PATH)
    print(
        f"{OUT_PATH} {WIDTH}x{HEIGHT} · {size:,}바이트 · 제목 {title_px}px · "
        f"설명 {len(sub_lines)}줄"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
