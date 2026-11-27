"""Generates the Echo texture (a washed-out, glitching copy of 'you') and pack icons."""
import random
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent / "src"
rng = random.Random(2026)

SKIN, HAIR = (150, 150, 156), (52, 48, 50)
SHIRT, PANTS, SHOES = (72, 96, 102), (56, 56, 82), (38, 38, 40)


def box(px, u, v, w, h, d, color_at):
    for x in range(u, u + 2 * d + 2 * w):
        for y in range(v, v + d + h):
            if y < v + d and not (u + d <= x < u + d + 2 * w):
                continue
            c = color_at(x - u, y - v, d, h)
            j = rng.randint(-10, 10)
            px[x, y] = tuple(max(0, min(255, k + j)) for k in c) + (175,)


def echo_texture():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    px = img.load()
    box(px, 0, 0, 8, 8, 8, lambda x, y, d, h: HAIR if y < d + 2 or y < d else SKIN)
    # face: hollow eyes, no mouth
    for x in (9, 10, 13, 14):
        px[x, 12] = (8, 8, 10, 230)
        px[x, 13] = (8, 8, 10, 120)
    box(px, 16, 16, 8, 12, 4, lambda x, y, d, h: SHIRT)
    for u, v in ((40, 16), (32, 48)):
        box(px, u, v, 4, 12, 4, lambda x, y, d, h: SHIRT if y < d + 4 else SKIN)
    for u, v in ((0, 16), (16, 48)):
        box(px, u, v, 4, 12, 4, lambda x, y, d, h: SHOES if y >= d + 10 else PANTS)
    # scanlines + missing pixels: a memory that isn't quite intact
    for y in range(64):
        if rng.random() < 0.18:
            for x in range(64):
                r, g, b, a = px[x, y]
                if a:
                    px[x, y] = (min(255, r + 40), min(255, g + 40), min(255, b + 50), 90)
    for _ in range(40):
        x, y = rng.randrange(64), rng.randrange(64)
        if px[x, y][3]:
            px[x, y] = (0, 0, 0, 0)
    return img


def pack_icon():
    s = 128
    img = Image.new("RGBA", (s, s), (6, 7, 12, 255))
    d = ImageDraw.Draw(img)
    for _ in range(60):  # stars
        d.point((rng.randrange(s), rng.randrange(70)), fill=(120, 120, 140, 255))
    d.rectangle([0, 104, s, s], fill=(14, 18, 14, 255))
    # solid figure and its faded echo a step behind
    for ox, alpha in ((70, 255), (44, 90)):
        col = (200, 200, 210, alpha) if alpha < 255 else (90, 120, 126, 255)
        layer = Image.new("RGBA", (s, s))
        ld = ImageDraw.Draw(layer)
        ld.rectangle([ox, 46, ox + 14, 60], fill=col)          # head
        ld.rectangle([ox, 61, ox + 14, 82], fill=col)          # body
        ld.rectangle([ox + 1, 83, ox + 6, 104], fill=col)      # legs
        ld.rectangle([ox + 8, 83, ox + 13, 104], fill=col)
        if alpha < 255:
            ld.rectangle([ox + 3, 52, ox + 5, 54], fill=(0, 0, 0, 255))
            ld.rectangle([ox + 9, 52, ox + 11, 54], fill=(0, 0, 0, 255))
        img = Image.alpha_composite(img, layer)
    d = ImageDraw.Draw(img)
    for y in range(0, s, 4):  # VHS lines
        d.line([(0, y), (s, y)], fill=(3, 3, 6, 255))
    return img


if __name__ == "__main__":
    echo_texture().save(ROOT / "RP/textures/entity/echo.png")
    icon = pack_icon()
    icon.save(ROOT / "BP/pack_icon.png")
    icon.save(ROOT / "RP/pack_icon.png")
    print("textures written")
