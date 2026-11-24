"""Generates the Hollow's entity texture and pack icons (deterministic)."""
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent / "src"
rng = random.Random(1313)

SKIN = (206, 201, 190)
CLOTH = (34, 31, 36)
VOID = (6, 5, 7)


def jitter(c, amt=14):
    d = rng.randint(-amt, amt)
    return tuple(max(0, min(255, v + d)) for v in c) + (255,)


def fill_box(img, u, v, w, h, d, color, amt=14):
    """Fill the full box-UV region of a cube with noisy color."""
    px = img.load()
    for x in range(u, u + 2 * d + 2 * w):
        for y in range(v, v + d + h):
            if y < v + d and not (u + d <= x < u + d + 2 * w):
                continue  # unused corners of the box-UV layout
            px[x, y] = jitter(color, amt)


def entity_texture():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    px = img.load()
    # head 6x8x6 @ (0,0)
    fill_box(img, 0, 0, 6, 8, 6, SKIN)
    # sparse dark hair strands on top of head
    for _ in range(9):
        px[rng.randint(6, 11), rng.randint(0, 5)] = jitter(VOID, 6)
    # face (front) = x 6..11, y 6..13
    for (x, y) in [(7, 8), (7, 9), (7, 10), (10, 8), (10, 9), (10, 10), (7, 11), (10, 11)]:
        px[x, y] = VOID + (255,)
    px[7, 12] = (40, 4, 6, 255)    # tear streaks
    px[10, 12] = (40, 4, 6, 255)
    px[7, 8] = (235, 235, 225, 255)  # pinprick pupil
    for y in range(11, 14):  # long mouth
        px[8, y] = VOID + (255,)
        px[9, y] = VOID + (255,)
    px[8, 13] = (70, 6, 8, 255)
    px[9, 13] = (70, 6, 8, 255)
    # eye-socket shading
    for (x, y) in [(6, 8), (8, 8), (6, 9), (11, 8), (9, 8), (11, 9)]:
        r, g, b, a = px[x, y]
        px[x, y] = (r - 45, g - 45, b - 40, 255)

    # torso 6x16x3 @ (24,0): tattered dark robe
    fill_box(img, 24, 0, 6, 16, 3, CLOTH, 8)
    for _ in range(18):  # rot/tears
        px[rng.randint(24, 41), rng.randint(3, 18)] = jitter((60, 55, 58), 10)
    # ribs peeking through on front (x 27..32, y 3..18)
    for y in (6, 8, 10):
        for x in range(28, 32):
            px[x, y] = jitter(SKIN, 10)
    # neck 2x3x2 @ (44,0)
    fill_box(img, 44, 0, 2, 3, 2, SKIN)

    # arms 2x24x2 @ (0,16),(8,16): pale with long black fingers
    for u in (0, 8):
        fill_box(img, u, 16, 2, 24, 2, SKIN)
        for x in range(u, u + 8):
            for y in range(16 + 2 + 18, 16 + 2 + 24):
                px[x, y] = jitter(VOID, 6)
        for x in range(u, u + 8):  # ragged sleeves
            for y in range(18, 18 + rng.randint(4, 8)):
                px[x, y] = jitter(CLOTH, 8)
    # legs 2x20x2 @ (16,20),(24,20)
    for u in (16, 24):
        fill_box(img, u, 20, 2, 20, 2, (150, 146, 138))
        for x in range(u, u + 8):
            for y in range(22, 22 + rng.randint(4, 9)):
                px[x, y] = jitter(CLOTH, 8)
    return img


def pack_icon(tag):
    s = 256
    img = Image.new("RGBA", (s, s), (8, 8, 10, 255))
    d = ImageDraw.Draw(img)
    # faint fog
    for _ in range(4000):
        x, y = rng.randrange(s), rng.randrange(s)
        g = rng.randint(10, 26)
        d.point((x, y), fill=(g, g, g + 2, 255))
    # pale face
    d.rectangle([68, 40, 188, 200], fill=SKIN + (255,))
    d.rectangle([84, 88, 112, 150], fill=VOID + (255,))
    d.rectangle([144, 88, 172, 150], fill=VOID + (255,))
    d.rectangle([92, 96, 98, 102], fill=(240, 240, 230, 255))
    d.rectangle([118, 160, 138, 200], fill=VOID + (255,))
    d.rectangle([90, 150, 96, 176], fill=(70, 6, 8, 255))
    d.rectangle([150, 150, 156, 176], fill=(70, 6, 8, 255))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    return img.resize((128, 128), Image.NEAREST)


if __name__ == "__main__":
    tex = ROOT / "RP/textures/entity/watcher.png"
    entity_texture().save(tex)
    pack_icon("BP").save(ROOT / "BP/pack_icon.png")
    pack_icon("RP").save(ROOT / "RP/pack_icon.png")
    print("textures written")
