"""AI OS look: colours, fonts and small drawing helpers shared by every screen.

Sizes are designed for a 1280x800 screen; call set_scale(display.size) once and pass
design-pixel values through px() so everything grows or shrinks with the real resolution.
"""
import math, os

import pygame

FONT_DIR = os.environ.get("AIOS_FONTS", "/usr/share/fonts/aios")

# Dark, slightly blue-violet neutrals with AI OS's magenta as the accent.
C = {
    "bg":        (13, 14, 20),
    "bg2":       (18, 20, 29),      # sidebar, title bars
    "panel":     (24, 27, 38),      # cards, AI chat bubbles
    "panel2":    (32, 36, 50),      # hover, inputs
    "line":      (44, 49, 66),      # borders and dividers
    "text":      (234, 236, 244),
    "text2":     (160, 167, 186),   # secondary text
    "muted":     (108, 115, 135),
    "accent":    (217, 70, 239),    # AI OS magenta
    "accent2":   (168, 85, 247),    # violet, gradients with accent
    "accent_ink": (255, 255, 255),
    "user":      (124, 58, 237),    # the user's chat bubbles
    "cyan":      (34, 211, 238),
    "ok":        (52, 211, 153),
    "warn":      (251, 191, 36),
    "err":       (248, 113, 113),
    "term_bg":   (10, 11, 16),      # terminal windows
}

_scale = 1.0


def set_scale(size):
    """Scale the design (made for 1280x800) to the real screen size."""
    global _scale
    w, h = size
    _scale = max(0.7, min(2.0, min(w / 1280.0, h / 800.0)))
    _font_cache.clear()
    return _scale


def px(v):
    """A design-pixel length on this screen."""
    return max(1, int(round(v * _scale)))


# ---------------------------------------------------------------------------- fonts
# Interface text is Liberation Sans: the open, metric-compatible stand-in for Arial (same letter
# widths and look; Arial itself can't be shipped). It has two weights, so medium/semibold map onto them.
_FILES = {
    "regular": "LiberationSans-Regular.ttf", "medium": "LiberationSans-Regular.ttf",
    "semibold": "LiberationSans-Bold.ttf", "bold": "LiberationSans-Bold.ttf",
    "italic": "LiberationSans-Italic.ttf", "bold-italic": "LiberationSans-BoldItalic.ttf",
    "mono": "JetBrainsMono-Regular.ttf", "mono-bold": "JetBrainsMono-Bold.ttf",
}
_font_cache = {}


def font(role="regular", size=15):
    """A pygame Font. role: regular, medium, semibold, bold, mono, mono-bold. size in design pixels."""
    key = (role, size, _scale)
    f = _font_cache.get(key)
    if f is None:
        path = os.path.join(FONT_DIR, _FILES.get(role, _FILES["regular"]))
        try:
            f = pygame.font.Font(path, px(size))
        except (OSError, FileNotFoundError):
            f = pygame.font.Font(None, px(size) + 4)  # pygame's built-in font as a last resort
        _font_cache[key] = f
    return f


_text_cache = {}


def text(surface, s, pos, role="regular", size=15, color=None, anchor="topleft"):
    """Draw one line of text; anchor is any pygame.Rect position name. Returns its Rect.
    Rendered lines are kept, so redrawing the same screen doesn't render them again."""
    key = (s, role, size, color or C["text"], _scale)
    img = _text_cache.get(key)
    if img is None:
        if len(_text_cache) > 3000:
            _text_cache.clear()
        img = _text_cache[key] = font(role, size).render(s, True, color or C["text"])
    r = img.get_rect(**{anchor: pos})
    surface.blit(img, r)
    return r


def wrap(s, fnt, width):
    """Split text into lines that fit `width` pixels. Keeps the text's own line breaks."""
    out = []
    for para in s.split("\n"):
        if not para:
            out.append("")
            continue
        line = ""
        for word in para.split(" "):
            cand = word if not line else line + " " + word
            if fnt.size(cand)[0] <= width:
                line = cand
                continue
            if line:
                out.append(line)
            while fnt.size(word)[0] > width and len(word) > 1:   # break very long words
                cut = len(word)
                while cut > 1 and fnt.size(word[:cut])[0] > width:
                    cut -= 1
                out.append(word[:cut])
                word = word[cut:]
            line = word
        out.append(line)
    return out


# ---------------------------------------------------------------------------- shapes
def panel(surface, rect, color=None, radius=12, border=None, shadow=False):
    """A rounded rectangle, optionally with a 1px border and a soft drop shadow."""
    rect = pygame.Rect(rect)
    r = px(radius)
    if shadow:
        key = ("shadow", rect.w, rect.h, r)
        sh = _shape_cache.get(key)
        if sh is None:
            sh = pygame.Surface((rect.w + px(24), rect.h + px(24)), pygame.SRCALPHA)
            for i in range(6):
                a = 10 + i * 4
                pygame.draw.rect(sh, (0, 0, 0, a), sh.get_rect().inflate(-i * px(4), -i * px(4)), border_radius=r + px(8))
            _keep(key, sh)
        surface.blit(sh, (rect.x - px(12), rect.y - px(6)))
    pygame.draw.rect(surface, color or C["panel"], rect, border_radius=r)
    if border:
        pygame.draw.rect(surface, border, rect, width=1, border_radius=r)
    return rect


_shape_cache = {}


def _keep(key, surf):
    if len(_shape_cache) > 400:
        _shape_cache.clear()
    _shape_cache[key] = surf


def gradient_rect(surface, rect, c1, c2, radius=0, horizontal=True):
    """A rectangle filled with a two-colour gradient (rounded corners if radius > 0).
    Each size and colour pair is drawn once and then reused."""
    rect = pygame.Rect(rect)
    key = ("grad", rect.size, tuple(c1), tuple(c2), radius, horizontal, _scale)
    g = _shape_cache.get(key)
    if g is not None:
        surface.blit(g, rect)
        return
    g = pygame.Surface(rect.size, pygame.SRCALPHA)
    n = rect.w if horizontal else rect.h
    for i in range(max(1, n)):
        t = i / max(1, n - 1)
        col = tuple(int(c1[k] + (c2[k] - c1[k]) * t) for k in range(3))
        if horizontal:
            pygame.draw.line(g, col, (i, 0), (i, rect.h))
        else:
            pygame.draw.line(g, col, (0, i), (rect.w, i))
    if radius:
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=px(radius))
        g.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    _keep(key, g)
    surface.blit(g, rect)


def progress_bar(surface, rect, fraction, label=None):
    """AI OS's loading bar: a rounded track with a magenta-to-violet fill."""
    rect = pygame.Rect(rect)
    pygame.draw.rect(surface, C["panel2"], rect, border_radius=rect.h // 2)
    w = int(rect.w * max(0.0, min(1.0, fraction)))
    if w >= rect.h:
        gradient_rect(surface, (rect.x, rect.y, w, rect.h), C["accent"], C["accent2"], radius=rect.h // 2 / max(_scale, 0.01))
    if label:
        text(surface, label, (rect.x, rect.bottom + px(8)), "medium", 13, C["text2"])


def button(surface, rect, label, kind="normal", hover=False, icon_name=None):
    """A button. kind: 'primary' (magenta), 'normal', 'ghost', 'danger'. Returns its Rect."""
    rect = pygame.Rect(rect)
    if kind == "primary":
        gradient_rect(surface, rect, C["accent"], C["accent2"], radius=10)
        if hover:
            pygame.draw.rect(surface, (255, 255, 255), rect, width=1, border_radius=px(10))
        fg = C["accent_ink"]
    else:
        bg = {"normal": C["panel2"], "ghost": C["bg2"], "danger": (70, 30, 38)}[kind]
        if hover:
            bg = tuple(min(255, c + 14) for c in bg)
        panel(surface, rect, bg, radius=10, border=C["line"] if kind != "ghost" else None)
        fg = C["err"] if kind == "danger" else C["text"]
    f = font("semibold", 14)
    img = f.render(label, True, fg)
    x = rect.centerx - img.get_width() // 2
    if icon_name:
        isz = px(16)
        x += (isz + px(8)) // 2
        icon(surface, icon_name, (x - isz - px(8), rect.centery - isz // 2, isz, isz), fg)
    surface.blit(img, (x, rect.centery - img.get_height() // 2))
    return rect


def draw_pointer(surface, pos):
    """The mouse pointer (an arrow with a dark outline)."""
    x, y = pos
    s = px(1)
    pts = [(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12)]
    poly = [(x + a * s, y + b * s) for a, b in pts]
    pygame.draw.polygon(surface, (255, 255, 255), poly)
    pygame.draw.polygon(surface, (0, 0, 0), poly, width=max(1, s))


# ---------------------------------------------------------------------------- icons
def icon(surface, name, rect, color=None):
    """Small line icons drawn with pygame shapes. Names: chat, play, folder, file, code, python,
    shell, disc, gamepad, wifi, power, gear, plus, send, stop, close, check, warn, trash, refresh,
    sparkle, terminal, download, user, bot."""
    r = pygame.Rect(rect)
    c = color or C["text"]
    w = max(1, px(2))
    cx, cy, s = r.centerx, r.centery, min(r.w, r.h)
    L = lambda a, b: pygame.draw.line(surface, c, a, b, w)  # noqa: E731
    if name == "play":
        pygame.draw.polygon(surface, c, [(r.x + s * .28, r.y + s * .18), (r.x + s * .28, r.y + s * .82), (r.x + s * .82, cy)])
    elif name == "stop":
        pygame.draw.rect(surface, c, r.inflate(-s * .45, -s * .45), border_radius=px(2))
    elif name in ("close", "x"):
        d = s * .28
        L((cx - d, cy - d), (cx + d, cy + d)); L((cx - d, cy + d), (cx + d, cy - d))
    elif name == "plus":
        d = s * .32
        L((cx - d, cy), (cx + d, cy)); L((cx, cy - d), (cx, cy + d))
    elif name == "check":
        L((r.x + s * .2, cy), (r.x + s * .42, r.y + s * .72)); L((r.x + s * .42, r.y + s * .72), (r.x + s * .82, r.y + s * .28))
    elif name == "send":
        pygame.draw.polygon(surface, c, [(r.x + s * .12, r.y + s * .15), (r.x + s * .9, cy), (r.x + s * .12, r.y + s * .85), (r.x + s * .28, cy)])
    elif name == "chat":
        b = pygame.Rect(r.x + s * .1, r.y + s * .15, s * .8, s * .55)
        pygame.draw.rect(surface, c, b, w, border_radius=px(4))
        pygame.draw.polygon(surface, c, [(b.x + s * .2, b.bottom - 1), (b.x + s * .2, b.bottom + s * .18), (b.x + s * .42, b.bottom - 1)])
    elif name in ("folder",):
        pygame.draw.rect(surface, c, (r.x + s * .1, r.y + s * .3, s * .8, s * .55), w, border_radius=px(3))
        pygame.draw.rect(surface, c, (r.x + s * .1, r.y + s * .2, s * .35, s * .15), w, border_radius=px(2))
    elif name in ("file", "code", "python", "shell"):
        pygame.draw.rect(surface, c, (r.x + s * .2, r.y + s * .1, s * .6, s * .8), w, border_radius=px(3))
        if name == "code":
            L((r.x + s * .42, r.y + s * .4), (r.x + s * .32, cy + s * .05)); L((r.x + s * .32, cy + s * .05), (r.x + s * .42, r.y + s * .65))
            L((r.x + s * .58, r.y + s * .4), (r.x + s * .68, cy + s * .05)); L((r.x + s * .68, cy + s * .05), (r.x + s * .58, r.y + s * .65))
        elif name == "python":
            pygame.draw.circle(surface, c, (int(cx), int(cy)), int(s * .12), w)
        elif name == "shell":
            L((r.x + s * .32, r.y + s * .4), (r.x + s * .45, cy + s * .02)); L((r.x + s * .45, cy + s * .02), (r.x + s * .32, r.y + s * .62))
            L((r.x + s * .5, r.y + s * .66), (r.x + s * .68, r.y + s * .66))
        else:
            for k in (.38, .52, .66):
                L((r.x + s * .32, r.y + s * k), (r.x + s * .68, r.y + s * k))
    elif name == "terminal":
        pygame.draw.rect(surface, c, (r.x + s * .08, r.y + s * .18, s * .84, s * .64), w, border_radius=px(3))
        L((r.x + s * .24, r.y + s * .38), (r.x + s * .38, cy)); L((r.x + s * .38, cy), (r.x + s * .24, r.y + s * .62))
        L((r.x + s * .44, r.y + s * .64), (r.x + s * .7, r.y + s * .64))
    elif name == "disc":
        pygame.draw.circle(surface, c, (int(cx), int(cy)), int(s * .4), w)
        pygame.draw.circle(surface, c, (int(cx), int(cy)), max(1, int(s * .1)))
    elif name == "gamepad":
        body = pygame.Rect(r.x + s * .06, r.y + s * .3, s * .88, s * .45)
        pygame.draw.rect(surface, c, body, w, border_radius=int(s * .2))
        L((r.x + s * .24, cy + s * .02), (r.x + s * .4, cy + s * .02)); L((r.x + s * .32, cy - s * .06), (r.x + s * .32, cy + s * .1))
        pygame.draw.circle(surface, c, (int(r.x + s * .66), int(cy - s * .02)), max(1, int(s * .05)))
        pygame.draw.circle(surface, c, (int(r.x + s * .76), int(cy + s * .08)), max(1, int(s * .05)))
    elif name == "wifi":
        for k, rad in enumerate((.42, .29, .16)):
            pygame.draw.arc(surface, c, (cx - s * rad, r.y + s * .78 - s * rad, s * rad * 2, s * rad * 2), math.radians(45), math.radians(135), w)
        pygame.draw.circle(surface, c, (int(cx), int(r.y + s * .74)), max(1, int(s * .06)))
    elif name == "power":
        pygame.draw.arc(surface, c, r.inflate(-s * .25, -s * .25), math.radians(120), math.radians(420), w)
        L((cx, r.y + s * .12), (cx, cy))
    elif name == "gear":
        pygame.draw.circle(surface, c, (int(cx), int(cy)), int(s * .22), w)
        for k in range(8):
            a = k * math.pi / 4
            L((cx + math.cos(a) * s * .28, cy + math.sin(a) * s * .28), (cx + math.cos(a) * s * .4, cy + math.sin(a) * s * .4))
    elif name == "trash":
        pygame.draw.rect(surface, c, (r.x + s * .25, r.y + s * .3, s * .5, s * .58), w, border_radius=px(2))
        L((r.x + s * .18, r.y + s * .26), (r.x + s * .82, r.y + s * .26)); L((r.x + s * .4, r.y + s * .16), (r.x + s * .6, r.y + s * .16))
    elif name == "refresh":
        pygame.draw.arc(surface, c, r.inflate(-s * .3, -s * .3), math.radians(30), math.radians(320), w)
        pygame.draw.polygon(surface, c, [(r.right - s * .2, r.y + s * .2), (r.right - s * .12, r.y + s * .42), (r.right - s * .36, r.y + s * .38)])
    elif name == "warn":
        pygame.draw.polygon(surface, c, [(cx, r.y + s * .12), (r.x + s * .9, r.y + s * .86), (r.x + s * .1, r.y + s * .86)], w)
        L((cx, r.y + s * .4), (cx, r.y + s * .62)); pygame.draw.circle(surface, c, (int(cx), int(r.y + s * .74)), max(1, w))
    elif name == "download":
        L((cx, r.y + s * .12), (cx, r.y + s * .62))
        L((cx - s * .2, r.y + s * .44), (cx, r.y + s * .64)); L((cx + s * .2, r.y + s * .44), (cx, r.y + s * .64))
        L((r.x + s * .16, r.y + s * .84), (r.right - s * .16, r.y + s * .84))
    elif name == "sparkle" or name == "bot":
        for k in range(4):
            a = k * math.pi / 2
            pygame.draw.polygon(surface, c, [(cx, cy), (cx + math.cos(a - .35) * s * .18, cy + math.sin(a - .35) * s * .18),
                                             (cx + math.cos(a) * s * .46, cy + math.sin(a) * s * .46),
                                             (cx + math.cos(a + .35) * s * .18, cy + math.sin(a + .35) * s * .18)])
    elif name == "user":
        pygame.draw.circle(surface, c, (int(cx), int(r.y + s * .36)), int(s * .18), w)
        pygame.draw.arc(surface, c, (r.x + s * .18, r.y + s * .6, s * .64, s * .6), 0, math.pi, w)
    else:
        pygame.draw.circle(surface, c, (int(cx), int(cy)), int(s * .3), w)
