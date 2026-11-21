"""Dino Run: a side-scrolling runner. Space/Up jumps (hold for a higher jump), Down ducks
(or drops faster in the air). Cacti on the ground, pterosaurs at three heights, the speed keeps
creeping up, and day slowly turns to night and back."""
import math, random

import pygame

from .. import theme as T
from .common import Game, Particles, clamp, halo, mix, shade, vgradient

BODY, BELLY, SPIKE, LINE = (139, 92, 246), (226, 196, 255), (217, 70, 239), (64, 34, 140)
CACTUS, CACTUS_D = (46, 196, 128), (22, 122, 84)
SPRITE = 1.2    # sprites are drawn this much larger than the screen unit
FLYER, FLYER_D = (251, 146, 60), (170, 80, 30)
DAY = {"top": (64, 52, 140), "bot": (236, 150, 172), "far": (126, 92, 170), "near": (88, 60, 132),
       "ground": (58, 40, 82), "line": (238, 210, 230), "cloud": (246, 214, 236)}
NIGHT = {"top": (6, 8, 26), "bot": (44, 32, 92), "far": (40, 34, 86), "near": (26, 22, 60),
         "ground": (22, 18, 40), "line": (150, 140, 200), "cloud": (70, 64, 120)}


def _ridge(rng, width, height, n, rough):
    """A repeating mountain outline (list of (x, y), y measured down from the peak line) made of
    a few sine waves with whole periods per tile, so neighbouring tiles join seamlessly."""
    waves = [(k, rng.uniform(0.4, 1.0) / k ** 0.7, rng.uniform(0, math.tau)) for k in (1, 2, 3, 5, 8)]
    raw = []
    steps = n * 6
    for i in range(steps + 1):
        x = width * i / steps
        raw.append((x, sum(a * math.sin(math.tau * k * x / width + ph) for k, a, ph in waves)))
    lo, hi = min(v for _, v in raw), max(v for _, v in raw)
    return [(x, height * (0.1 + 0.9 * (hi - v) / (hi - lo))) for x, v in raw]


class Dino(Game):
    id = "dino"
    title = "Dino Run"
    blurb = "Jump the cacti, duck the pterosaurs, run forever."
    controls = "Space / Up jump   Down duck"
    preview_view = (0.31, 0.6, 1.9)

    def __init__(self, size, top=0, preview=False):
        w, h = size
        self.sky_day = vgradient(size, DAY["top"], DAY["bot"])
        self.sky_night = vgradient(size, NIGHT["top"], NIGHT["bot"])
        rng = random.Random(11)
        u = h / 800.0
        self.far = _ridge(rng, w, 170 * u, 18, 60 * u)
        self.near = _ridge(rng, w, 120 * u, 12, 55 * u)
        self.starfield = [(rng.uniform(0, w), rng.uniform(0, h * 0.55), rng.choice((1, 1, 2))) for _ in range(90)]
        self.sun_glow = halo(int(110 * u), (255, 200, 160), 150)
        self.moon_glow = halo(int(90 * u), (160, 170, 255), 110)
        super().__init__(size, top, preview)

    def reset(self):
        super().reset()
        u = self.u
        self.gy = self.h * 0.76
        self.x = self.w * 0.13
        self.y, self.vy = 0.0, 0.0
        self.duck = False
        self.jump_held = False
        self.speed = 0.0 if not self.preview else 600 * u
        self.target = 540 * u
        self.dist = 0.0
        self.obs = []
        self.next_gap = 500 * u
        self.parts = Particles(200)
        self.clouds = [[random.uniform(0, self.w), random.uniform(self.h * 0.1, self.h * 0.4), random.uniform(0.7, 1.3)] for _ in range(5)]
        self.pebbles = [[random.uniform(0, self.w), random.uniform(6, 60) * u, random.choice((2, 3, 4))] for _ in range(36)]
        self.off_far = self.off_near = 0.0
        self.anim = 0.0
        self.flash = 0.0
        self.last_hundred = 0
        self.night = 0.0
        if self.preview:
            self.obs = [self._cactus(self.w * 0.33, 2), self._flyer(self.w * 0.47, 1)]
            self.night = 0.35
            self.y = 70 * u

    # ------------------------------------------------------------------ obstacles
    def _cactus(self, x, n=None):
        u = self.u * SPRITE
        n = n or random.choice((1, 1, 2, 2, 3))
        tall = random.random() < 0.45
        parts = []
        cx = x
        for i in range(n):
            hgt = (random.uniform(62, 82) if tall else random.uniform(44, 58)) * u
            wid = (26 if tall else 20) * u
            arms = (random.choice((-1, 1, 2)), random.uniform(0.35, 0.6))
            parts.append((cx, wid, hgt, arms))
            cx += wid + random.uniform(4, 10) * u
        return {"kind": "cactus", "x": x, "w": cx - x, "parts": parts}

    def _flyer(self, x, level=None):
        u = self.u * SPRITE
        level = random.choice((0, 1, 1, 2)) if level is None else level
        alt = (16, 56, 104)[level] * u
        return {"kind": "flyer", "x": x, "w": 52 * u, "alt": alt, "flap": random.uniform(0, 1)}

    def _spawn(self):
        u = self.u
        if self.score > 250 and random.random() < 0.27:
            self.obs.append(self._flyer(self.w + 40 * u))
        else:
            self.obs.append(self._cactus(self.w + 40 * u))
        self.next_gap = self.speed * random.uniform(0.95, 1.75) + 140 * u

    # ------------------------------------------------------------------ input / update
    def handle(self, ev):
        if super().handle(ev):
            return True
        if self.over or ev.type != "key":
            return False
        if ev.key in ("space", "up", "w") and ev.down and not ev.repeat:
            self._jump()
            return True
        return False

    def _jump(self):
        if self.y <= 0.01 and not self.duck:
            self.vy = 1180 * self.u
            self.jump_held = True
            self.parts.burst(self.x + 24 * self.u, self.gy, mix(DAY["line"], NIGHT["line"], self.night), n=8, speed=120 * self.u, life=0.35, size=4 * self.u, angle=math.pi, spread=1.2)

    def update(self, dt, inp):
        super().update(dt, inp)
        u = self.u
        self.parts.update(dt)
        self.flash = max(0.0, self.flash - dt)
        if self.over:
            return
        # speed creeps up; starts with a quick ramp
        self.target = min(1380 * u, self.target + 7.5 * u * dt)
        self.speed += (self.target - self.speed) * min(1.0, dt * 3)
        held_jump = inp.pressed("space") or inp.pressed("up") or inp.pressed("w")
        down = inp.pressed("down") or inp.pressed("s")
        # physics
        g = 3700 * u
        if self.y > 0 or self.vy > 0:
            if not held_jump and self.vy > 380 * u:
                self.vy = 380 * u            # short hop when the key is let go early
            if down:
                g *= 2.6                     # drop faster
            self.vy -= g * dt
            self.y += self.vy * dt
            if self.y <= 0:
                self.y, self.vy = 0.0, 0.0
                self.parts.burst(self.x + 24 * u, self.gy, mix(DAY["line"], NIGHT["line"], self.night), n=6, speed=90 * u, life=0.3, size=3 * u, angle=-math.pi / 2, spread=2.5)
        elif held_jump and not down:
            self._jump()
        self.duck = down and self.y <= 0.01
        # world scroll
        mv = self.speed * dt
        self.dist += mv
        self.score = int(self.dist / (42 * u))
        if self.score // 100 > self.last_hundred:
            self.last_hundred = self.score // 100
            self.flash = 0.9
        self.anim += dt * (8 + self.speed / (90 * u))
        self.off_far = (self.off_far + mv * 0.1) % self.w
        self.off_near = (self.off_near + mv * 0.25) % self.w
        for c in self.clouds:
            c[0] -= mv * 0.05 * c[2]
            if c[0] < -150 * u:
                c[0] = self.w + random.uniform(20, 200) * u
                c[1] = random.uniform(self.h * 0.1, self.h * 0.4)
        for p in self.pebbles:
            p[0] -= mv
            if p[0] < -10:
                p[0] += self.w + 20
        # day / night: 45 s of day, 25 s of night, eased 2.5 s transitions
        cyc = self.t % 70.0
        target = 0.0 if cyc < 45 else 1.0
        self.night += clamp(target - self.night, -dt / 2.5, dt / 2.5)
        # obstacles
        for o in self.obs:
            o["x"] -= mv
            if o["kind"] == "flyer":
                o["x"] -= 40 * u * dt         # flyers are a bit faster than the ground
                o["flap"] += dt * 5
        self.obs = [o for o in self.obs if o["x"] + o["w"] > -40 * u]
        if not self.obs or self.obs[-1]["x"] < self.w - self.next_gap:
            self._spawn()
        # collisions (forgiving boxes)
        dr = self._dino_rect()
        for o in self.obs:
            for r in self._obs_rects(o):
                if dr.colliderect(r):
                    self.end()
                    self.parts.burst(dr.centerx, dr.centery, SPIKE, n=26, speed=260 * u, life=0.6, size=5 * u, gravity=900 * u)
                    return

    def _dino_rect(self):
        u = self.u * SPRITE
        base = self.gy - self.y
        if self.duck:
            return pygame.Rect(self.x + 6 * u, base - 34 * u, 74 * u, 30 * u)
        return pygame.Rect(self.x + 10 * u, base - 62 * u, 42 * u, 58 * u)

    def _obs_rects(self, o):
        u = self.u * SPRITE
        if o["kind"] == "flyer":
            return [pygame.Rect(o["x"] + 6 * u, self.gy - o["alt"] - 30 * u, o["w"] - 12 * u, 22 * u)]
        out = []
        for cx, wid, hgt, _ in o["parts"]:
            out.append(pygame.Rect(cx + 3 * u, self.gy - hgt + 4 * u, wid - 6 * u, hgt - 4 * u))
        return out

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        u, w, h, k = self.u, self.w, self.h, self.night
        pal = {key: mix(DAY[key], NIGHT[key], k) for key in DAY}
        surf.blit(self.sky_day, (0, 0))
        if k > 0.01:
            self.sky_night.set_alpha(int(255 * k))
            surf.blit(self.sky_night, (0, 0))
        # stars, sun, moon
        if k > 0.05:
            for sx, sy, sz in self.starfield:
                tw = 0.6 + 0.4 * math.sin(self.t * 2 + sx)
                surf.fill(mix(pal["top"], (255, 255, 255), k * tw), (int(sx), int(sy), sz, sz))
        sun = (int(w * 0.8), int(h * 0.2 + k * h * 0.5))
        if k < 0.95:
            g = self.sun_glow
            g.set_alpha(int(255 * (1 - k)))
            surf.blit(g, (sun[0] - g.get_width() // 2, sun[1] - g.get_height() // 2))
            pygame.draw.circle(surf, mix((255, 214, 170), pal["bot"], k), sun, int(46 * u))
        moon = (int(w * 0.18), int(h * 0.18 + (1 - k) * h * 0.5))
        if k > 0.05:
            g = self.moon_glow
            g.set_alpha(int(200 * k))
            surf.blit(g, (moon[0] - g.get_width() // 2, moon[1] - g.get_height() // 2))
            pygame.draw.circle(surf, mix(pal["top"], (236, 236, 255), k), moon, int(30 * u))
            pygame.draw.circle(surf, mix(pal["top"], (200, 200, 235), k), (moon[0] - int(9 * u), moon[1] - int(6 * u)), int(7 * u))
        # clouds
        for cx, cy, sc in self.clouds:
            col = pal["cloud"]
            for dx, dy, r in ((0, 0, 22), (24, -10, 28), (52, 0, 22), (26, 6, 24)):
                pygame.draw.circle(surf, col, (int(cx + dx * u * sc), int(cy + dy * u * sc)), int(r * u * sc))
        # mountains
        self._ridge_draw(surf, self.far, self.off_far, self.gy - 40 * u, 170 * u, pal["far"])
        self._ridge_draw(surf, self.near, self.off_near, self.gy, 120 * u, pal["near"])
        # ground
        gy = int(self.gy)
        surf.fill(pal["ground"], (0, gy, w, h - gy))
        pygame.draw.line(surf, pal["line"], (0, gy), (w, gy), max(2, int(3 * u)))
        for px_, py_, sz in self.pebbles:
            surf.fill(mix(pal["ground"], pal["line"], 0.45), (int(px_), int(gy + py_), int(sz * u * 2), max(1, int(sz * u * 0.6))))
        # obstacles
        for o in self.obs:
            if o["kind"] == "cactus":
                for part in o["parts"]:
                    self._draw_cactus(surf, part, gy)
            else:
                self._draw_flyer(surf, o, gy)
        # dino
        self._draw_dino(surf, self.x, gy - self.y)
        self.parts.draw(surf, pal["ground"])
        if self.preview:
            return
        # HUD
        top = self.top + T.px(16)
        blink = self.flash > 0 and int(self.flash * 8) % 2 == 0
        f = T.font("mono-bold", 22)
        s = "%05d" % self.score
        img = f.render(s, True, T.C["text"] if not blink else T.C["accent"])
        x = w - T.px(24) - img.get_width()
        surf.blit(img, (x, top))
        hi = T.font("mono", 22).render("HI %05d" % max(self.best, self.score if self.over else self.best), True, mix(T.C["text2"], pal["top"], 0.2))
        surf.blit(hi, (x - hi.get_width() - T.px(18), top))
        if self.t < 3 and not self.over:
            self.hud_text(surf, "Space / Up to jump  ·  Down to duck", (w // 2, int(self.h * 0.32)), 18, "semibold", T.C["text"], "center")
        if self.over:
            lines = ["Score  %d" % self.score, "Best  %d" % self.best + ("  (new best!)" if self.flash_new_best else "")]
            self.overlay(surf, "Ouch!", lines, "Press Space to run again")

    def _ridge_draw(self, surf, pts, off, base, height, col):
        for tile in (0, 1):
            ox = tile * self.w - off
            poly = [(ox + x, base - height + y) for x, y in pts]
            poly += [(ox + self.w, self.gy + 2), (ox, self.gy + 2)]   # down to the ground line
            pygame.draw.polygon(surf, col, poly)

    def _draw_cactus(self, surf, part, gy):
        u = self.u * SPRITE
        cx, wid, hgt, (arm_side, arm_at) = part
        top = gy - hgt
        r = max(2, int(wid * 0.45))
        pygame.draw.rect(surf, CACTUS_D, (cx, top, wid, hgt + 2), border_radius=r)
        pygame.draw.rect(surf, CACTUS, (cx + wid * 0.12, top + 2 * u, wid * 0.62, hgt - 2 * u), border_radius=r)
        aw = wid * 0.42
        ay = top + hgt * arm_at
        sides = (-1, 1) if arm_side == 2 else (arm_side,)
        for sd in sides:
            ax = cx - aw * 1.25 if sd < 0 else cx + wid + aw * 0.25
            pygame.draw.rect(surf, CACTUS_D, (min(ax, cx) if sd < 0 else cx + wid - 2 * u, ay, aw * 1.3, aw), border_radius=int(aw / 2))
            pygame.draw.rect(surf, CACTUS_D, (ax, ay - hgt * 0.25, aw, hgt * 0.25 + aw), border_radius=int(aw / 2))
            pygame.draw.rect(surf, CACTUS, (ax + aw * 0.18, ay - hgt * 0.23, aw * 0.5, hgt * 0.22 + aw * 0.6), border_radius=int(aw / 3))
        for k in range(3):   # little spines
            yy = top + hgt * (0.25 + 0.22 * k)
            pygame.draw.line(surf, shade(CACTUS, 1.35), (cx + wid * 0.5, yy), (cx + wid * 0.5, yy + 4 * u), max(1, int(u)))

    def _draw_flyer(self, surf, o, gy):
        u = self.u * SPRITE
        x, y = o["x"], gy - o["alt"] - 18 * u
        up = math.sin(o["flap"] * math.tau) > 0
        wy = -22 if up else 16
        pygame.draw.polygon(surf, FLYER_D, [(x + 18 * u, y), (x + 30 * u, y + wy * u), (x + 38 * u, y)])
        pygame.draw.ellipse(surf, FLYER, (x + 6 * u, y - 7 * u, 40 * u, 14 * u))
        pygame.draw.polygon(surf, FLYER, [(x + 6 * u, y - 3 * u), (x - 12 * u, y + 2 * u), (x + 6 * u, y + 4 * u)])   # beak
        pygame.draw.polygon(surf, FLYER_D, [(x + 14 * u, y - 6 * u), (x + 8 * u, y - 16 * u), (x + 20 * u, y - 6 * u)])  # crest
        pygame.draw.circle(surf, (40, 20, 10), (int(x + 10 * u), int(y - 2 * u)), max(1, int(2 * u)))
        pygame.draw.polygon(surf, shade(FLYER, 1.15), [(x + 16 * u, y), (x + 26 * u, y + wy * 0.8 * u), (x + 34 * u, y)])

    def _draw_dino(self, surf, x, base):
        u = self.u * SPRITE

        def R(x0, y0, x1, y1, col, rad=6, outline=True):
            r = pygame.Rect(x + x0 * u, base + y0 * u, (x1 - x0) * u, (y1 - y0) * u)
            pygame.draw.rect(surf, col, r, border_radius=max(1, int(rad * u)))
            if outline:
                pygame.draw.rect(surf, LINE, r, width=max(1, int(2 * u)), border_radius=max(1, int(rad * u)))

        def Pg(pts, col, outline=True):
            poly = [(x + a * u, base + b * u) for a, b in pts]
            pygame.draw.polygon(surf, col, poly)
            if outline:
                pygame.draw.polygon(surf, LINE, poly, max(1, int(2 * u)))

        run = self.y <= 0.01 and not self.over
        step = int(self.anim) % 2 if run else 0
        dead = self.over
        if self.duck:
            Pg([(2, -26), (-24, -18), (2, -14)], BODY)
            for sx in (8, 20, 32, 44):
                Pg([(sx, -33), (sx + 5, -42), (sx + 10, -33)], SPIKE)
            l1, l2 = (-6, 0) if step else (0, -6)
            R(12, -16 + l1, 20, 0 + l1, BODY, 3)
            R(34, -16 + l2, 42, 0 + l2, BODY, 3)
            R(0, -34, 60, -12, BODY, 11)
            R(10, -24, 54, -12, BELLY, 6, outline=False)
            R(52, -38, 84, -18, BODY, 9)
            eye = (72, -31)
        else:
            Pg([(2, -42), (-28, -30), (2, -26)], BODY)
            for sx, sy in ((6, -47), (16, -50), (26, -53)):
                Pg([(sx, sy), (sx + 5, sy - 10), (sx + 10, sy)], SPIKE)
            if run:
                l1, l2 = (-7, 0) if step else (0, -7)
            else:
                l1 = l2 = -2 if self.y > 0 else 0
            R(8, -22 + l1, 17, 0 + l1, BODY, 3)
            R(26, -22 + l2, 35, 0 + l2, BODY, 3)
            R(0, -50, 44, -16, BODY, 13)
            R(8, -36, 40, -16, BELLY, 8, outline=False)
            R(38, -36, 46, -28, BODY, 3)       # arm
            R(28, -70, 62, -44, BODY, 10)       # head
            eye = (48, -61)
            pygame.draw.line(surf, LINE, (x + 50 * u, base - 50 * u), (x + 59 * u, base - 50 * u), max(1, int(2 * u)))
        ex, ey = x + eye[0] * u, base + eye[1] * u
        if dead:
            d = 4 * u
            pygame.draw.line(surf, LINE, (ex - d, ey - d), (ex + d, ey + d), max(2, int(2.5 * u)))
            pygame.draw.line(surf, LINE, (ex - d, ey + d), (ex + d, ey - d), max(2, int(2.5 * u)))
        else:
            pygame.draw.circle(surf, (255, 255, 255), (int(ex), int(ey)), max(2, int(5.5 * u)))
            pygame.draw.circle(surf, (24, 12, 40), (int(ex + 1.5 * u), int(ey)), max(1, int(2.7 * u)))
