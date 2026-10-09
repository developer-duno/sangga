"""파비콘 「건물 둘」 세트 생성 (👤 2026-10-09 G · PROGRESS 「2026-10-09 (5)」).

실행(로컬 전용 · Pillow 필요 · CI 에선 안 돈다):  python scripts/make_favicon.py public
만드는 것 = favicon.ico(16·32·48) · apple-touch-icon.png(180) · icon-192.png · icon-512.png · icon-512-maskable.png
⛔ SHAPES 는 public/favicon.svg 의 rect 아홉 개와 **글자 그대로 같은 좌표**(32 격자)다 — 모양을 바꾸면 SVG 와
   이 표를 함께 고치고, scripts/make_og_image.py 의 도형도 같은 좌표다. 외부 아이콘 서비스에 올리지 않는다.
"""

import os
import sys

from PIL import Image, ImageDraw

BLUE = (0x2F, 0x5F, 0xD0, 255)
WHITE = (255, 255, 255, 255)
SAND = (0xF3, 0xE7, 0xCF, 255)

# (x, y, w, h, rx, color) — public/favicon.svg 와 글자 그대로 같은 좌표
SHAPES = [
    (0, 0, 32, 32, 7, BLUE),
    (6, 6, 9, 20, 1, WHITE),
    (17, 13, 9, 13, 1, WHITE),
    (8.5, 9, 4, 2, 0, BLUE),
    (8.5, 13, 4, 2, 0, BLUE),
    (8.5, 17, 4, 2, 0, BLUE),
    (19.5, 16, 4, 2, 0, BLUE),
    (19.5, 20, 4, 2, 0, BLUE),
    (6, 26, 20, 2, 0, SAND),
]


def render(px: int) -> Image.Image:
    """32 격자를 8배로 그린 뒤 줄여 가장자리를 부드럽게 한다."""
    k = 8
    im = Image.new("RGBA", (32 * k, 32 * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x, y, w, h, rx, c in SHAPES:
        box = [x * k, y * k, (x + w) * k - 1, (y + h) * k - 1]
        if rx:
            d.rounded_rectangle(box, radius=rx * k, fill=c)
        else:
            d.rectangle(box, fill=c)
    return im.resize((px, px), Image.LANCZOS)


def main(out: str) -> None:
    os.makedirs(out, exist_ok=True)
    for name, px in [("apple-touch-icon.png", 180), ("icon-192.png", 192), ("icon-512.png", 512)]:
        render(px).save(os.path.join(out, name), optimize=True)
    render(48).save(os.path.join(out, "favicon.ico"), format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    # 홈 화면용은 OS 가 모서리를 깎으므로 파란 바탕을 꽉 채운 판(maskable)도 둔다
    px = 512
    im = Image.new("RGBA", (px, px), BLUE)
    inner = render(int(px * 0.8))
    off = (px - inner.width) // 2
    im.alpha_composite(inner, (off, off))
    im.save(os.path.join(out, "icon-512-maskable.png"), optimize=True)
    print("ok")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "public")
