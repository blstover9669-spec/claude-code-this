"""Shared pieces for AI OS's games: the Game base class, particles, HUD text and overlays."""
import json, math, os, random

import pygame

from .. import theme as T

SCORES = os.path.join(os.environ.get("AIOS_RUN", "/run/aios"), "game-scores.json")


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    """Blend two RGB colours (t=0 -> c1, t=1 -> c2)."""
    t = clamp(t, 0.0, 1.0)
    return (int(c1[0] + (c2[0] - c1[0]) * t), int(c1[1] + (c2[1] - c1[1]) * t), int(c1[2] + (c2[2] - c1[2]) * t))


def shade(c, k):
    """Scale a colour's brightness (k<1 darker, k>1 lighter), clamped."""
    return (min(255, int(c[0] * k)), min(255, int(c[1] * k)), min(255, int(c[2] * k)))


def vgradient(size, top, bottom):
    """A surface filled with a vertical gradient."""
    w, h = size
    s = pygame.Surface((w, h))
    for y in range(h):
        s.fill(mix(top, bottom, y / max(1, h - 1)), (0, y, w, 1))
    return s


def _falloff(radius, steps):
    for i in range(steps):
        r = radius * (1 - i / steps)
        yield max(1, int(r)), (1 - r / radius) ** 2       # brighter towards the middle


def glow(radius, color, strength=110):
    """A soft round light for ADDITIVE blits (blit(..., special_flags=pygame.BLEND_ADD)).
    The colour is pre-multiplied into a black surface, so only the glow adds light."""
    d = radius * 2
    s = pygame.Surface((d, d))
    s.fill((0, 0, 0))
    k = strength / 255.0
    for r, f in _falloff(radius, max(8, radius // 2)):
        pygame.draw.circle(s, (int(color[0] * f * k), int(color[1] * f * k), int(color[2] * f * k)), (radius, radius), r)
    return s


def halo(radius, color, strength=160):
    """A soft round halo for normal (alpha-blended) blits; surface alpha via set_alpha() still works."""
    d = radius * 2
    s = pygame.Surface((d, d), pygame.SRCALPHA)
    for r, f in _falloff(radius, max(8, radius // 2)):
        pygame.draw.circle(s, (*color, int(strength * f)), (radius, radius), r)
    return s


# ---------------------------------------------------------------------------- best scores
def load_best(gid):
    try:
        with open(SCORES) as fh:
            return int(json.load(fh).get(gid, 0))
    except (OSError, ValueError, AttributeError):
        return 0


def save_best(gid, score):
    try:
        try:
            with open(SCORES) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
        data[gid] = int(score)
        os.makedirs(os.path.dirname(SCORES), exist_ok=True)
        tmp = SCORES + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, SCORES)
    except OSError:
        pass


# ---------------------------------------------------------------------------- particles
class Particles:
    """Cheap particles: points that fly, slow down and fade towards the background colour."""

    def __init__(self, limit=420):
        self.p = []
        self.limit = limit

    def burst(self, x, y, color, n=18, speed=220.0, life=0.6, size=3, gravity=0.0, angle=None, spread=math.tau, drag=1.6):
        for _ in range(n):
            if len(self.p) >= self.limit:
                self.p.pop(0)
            a = (random.uniform(0, math.tau) if angle is None else angle + random.uniform(-spread / 2, spread / 2))
            v = speed * random.uniform(0.25, 1.0)
            lt = life * random.uniform(0.6, 1.2)
            self.p.append([x, y, math.cos(a) * v, math.sin(a) * v, lt, lt, color, size * random.uniform(0.6, 1.3), gravity, drag])

    def update(self, dt):
        keep = []
        for q in self.p:
            q[4] -= dt
            if q[4] <= 0:
                continue
            f = max(0.0, 1.0 - q[9] * dt)
            q[2] *= f
            q[3] = q[3] * f + q[8] * dt
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            keep.append(q)
        self.p = keep

    def draw(self, surf, bg=(0, 0, 0), dx=0, dy=0):
        fill = surf.fill
        for x, y, _, _, lt, ml, col, size, _, _ in self.p:
            t = lt / ml
            s = max(1, int(size * (0.4 + 0.6 * t)))
            fill(mix(bg, col, min(1.0, t * 1.4)), (int(x + dx) - s // 2, int(y + dy) - s // 2, s, s))


# ---------------------------------------------------------------------------- base class
class Game:
    """Base for the games. size: the area to draw in; top: pixels at the top kept free for the
    loading screen's progress strip (put the HUD below it); preview: draw a still for a menu card."""
    id = "game"
    title = "Game"
    blurb = ""
    controls = ""
    preview_view = (0.5, 0.5, 1.0)   # menu-card preview: centre x, centre y (fractions), zoom

    def __init__(self, size, top=0, preview=False):
        self.size = size
        self.w, self.h = size
        self.top = top
        self.preview = preview
        self.u = self.h / 800.0           # 1.0 on an 800-pixel-tall screen
        self.best = 0 if preview else load_best(self.id)
        self.flash_new_best = False
        self.reset()

    # -- lifecycle
    def reset(self):
        self.score = 0
        self.over = False
        self.over_t = 0.0
        self.t = 0.0

    def end(self):
        if self.over:
            return
        self.over = True
        self.over_t = 0.0
        self.flash_new_best = self.score > self.best and self.score > 0
        if self.score > self.best:
            self.best = int(self.score)
            if not self.preview:
                save_best(self.id, self.best)

    def handle(self, ev):
        """Discrete input. The base class restarts after game over on Space/Enter."""
        if self.over and ev.type == "key" and ev.down and not ev.repeat and ev.key in ("space", "return", "up", "w"):
            if self.over_t > 0.45:
                self.reset()
            return True
        if self.over and ev.type == "mouse_button" and ev.down and ev.button == 1 and self.over_t > 0.45:
            self.reset()
            return True
        return False

    def update(self, dt, inp):
        self.t += dt
        if self.over:
            self.over_t += dt

    def draw(self, surf):
        pass

    # -- helpers for subclasses
    def U(self, v):
        return max(1, int(v * self.u))

    def hud_text(self, surf, s, pos, size=18, role="semibold", color=None, anchor="topleft"):
        f = T.font(role, size)
        col = color or T.C["text"]
        img = f.render(s, True, col)
        sh = f.render(s, True, (0, 0, 0))
        r = img.get_rect(**{anchor: pos})
        surf.blit(sh, (r.x + 2, r.y + 2))
        surf.blit(img, r)
        return r

    def overlay(self, surf, title, lines=(), hint="", accent=None):
        """A dimmed, rounded card in the middle of the screen (game over and the like)."""
        w = T.px(460)
        f_t, f_l, f_h = T.font("bold", 34), T.font("regular", 16), T.font("semibold", 15)
        h = T.px(46) + f_t.get_height() + len(lines) * (f_l.get_height() + T.px(6)) + (f_h.get_height() + T.px(18) if hint else 0)
        card = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(card, (12, 13, 20, 225), card.get_rect(), border_radius=T.px(18))
        pygame.draw.rect(card, (*(accent or T.C["accent"]), 200), card.get_rect(), width=max(1, T.px(2)), border_radius=T.px(18))
        y = T.px(22)
        img = f_t.render(title, True, T.C["text"])
        card.blit(img, ((w - img.get_width()) // 2, y))
        y += img.get_height() + T.px(10)
        for ln in lines:
            img = f_l.render(ln, True, T.C["text2"])
            card.blit(img, ((w - img.get_width()) // 2, y))
            y += img.get_height() + T.px(6)
        if hint:
            y += T.px(10)
            pulse = 0.65 + 0.35 * math.sin(self.t * 5)
            img = f_h.render(hint, True, mix(T.C["text2"], accent or T.C["accent"], pulse))
            card.blit(img, ((w - img.get_width()) // 2, y))
        surf.blit(card, ((self.w - w) // 2, (self.h - h) // 2))
