"""Space Shooter: a 2D vertical shooter. Arrows/WASD move, Space fires (hold for auto-fire).

Waves of drones, weavers, divers and tanks, with a boss every fifth wave. Destroyed ships
sometimes drop power-ups: W (spread shot), S (shield) and + (an extra life).
"""
import math, random

import pygame

from .. import theme as T
from .common import Game, Particles, clamp, glow, mix, shade, vgradient

BG_TOP, BG_BOTTOM = (6, 5, 20), (24, 10, 40)
HULL, WING, COCKPIT = (139, 92, 246), (217, 70, 239), (125, 230, 255)
ENEMY = {
    "drone": (255, 128, 92), "weaver": (52, 211, 153), "diver": (251, 191, 36),
    "tank": (236, 72, 153), "boss": (220, 38, 70),
}


class Enemy:
    __slots__ = ("kind", "x", "y", "x0", "hp", "maxhp", "r", "t", "phase", "vx", "vy", "fire",
                 "pts", "flash", "state", "ty", "st")

    def __init__(self, kind, x, y, u, d, wave):
        self.kind, self.x, self.y, self.x0 = kind, x, y, x
        self.t, self.phase, self.flash, self.state, self.st = 0.0, random.uniform(0, math.tau), 0.0, 0, 0.0
        self.vx = self.vy = 0.0
        self.ty = 0.0
        if kind == "drone":
            self.hp, self.r, self.pts = 1, 17 * u, 100
            self.vy = 125 * u * d
            self.fire = random.uniform(3.0, 6.0) if wave >= 6 else 1e9
        elif kind == "weaver":
            self.hp, self.r, self.pts = 2, 19 * u, 150
            self.vy = 82 * u * d
            self.fire = random.uniform(1.2, 2.8)
        elif kind == "diver":
            self.hp, self.r, self.pts = 1, 16 * u, 200
            self.vy = 230 * u
            self.fire = 1e9
        elif kind == "tank":
            self.hp, self.r, self.pts = 6 + wave // 3, 31 * u, 400
            self.vy = 62 * u
            self.vx = random.choice((-1, 1)) * 85 * u
            self.fire = random.uniform(1.0, 2.0)
        else:  # boss
            self.hp, self.r, self.pts = 70 + 18 * (wave // 5 - 1), 72 * u, 3000
            self.vy = 70 * u
            self.fire = 2.0
        self.maxhp = self.hp


class Shooter(Game):
    id = "shooter"
    title = "Space Shooter"
    blurb = "Blast through waves of alien ships and their boss."
    controls = "Arrows / WASD move   Space fire"
    preview_view = (0.5, 0.53, 1.45)

    def __init__(self, size, top=0, preview=False):
        w, h = size
        u = h / 800.0
        self.bg = vgradient(size, BG_TOP, BG_BOTTOM)
        for (fx, fy, rad, col) in ((0.2, 0.25, 0.38, (120, 40, 200)), (0.85, 0.6, 0.42, (200, 30, 140)), (0.45, 0.9, 0.3, (40, 80, 200))):
            g = glow(int(h * rad), col, 70)
            self.bg.blit(g, (int(w * fx - g.get_width() / 2), int(h * fy - g.get_height() / 2)), special_flags=pygame.BLEND_ADD)
        rnd = random.Random(7)
        for _ in range(int(w * h / 9000)):
            c = rnd.randint(50, 120)
            self.bg.fill((c, c, c + 20), (rnd.randrange(w), rnd.randrange(h), 1, 1))
        self.stars = []
        for layer, (count, speed, sz, br) in enumerate(((70, 26, 1, 120), (45, 64, 2, 180), (22, 140, 2, 255))):
            for _ in range(int(count * w / 1280)):
                self.stars.append([random.uniform(0, w), random.uniform(0, h), speed * u, max(1, int(sz * u)), br, layer])
        self.g_shot = glow(max(4, int(12 * u)), (90, 200, 255), 255)
        self.g_ebul = glow(max(4, int(12 * u)), (255, 120, 40), 255)
        self.g_eng = glow(max(4, int(16 * u)), (255, 140, 60), 255)
        super().__init__(size, top, preview)

    # ------------------------------------------------------------------ state
    def reset(self):
        super().reset()
        u = self.u
        self.px, self.py = self.w / 2, self.h * 0.84
        self.vx = self.vy = 0.0
        self.lives, self.inv, self.shield = 3, 2.0, 0
        self.weapon, self.weapon_t, self.cool = 1, 0.0, 0.0
        self.shots, self.ebullets, self.enemies, self.powerups, self.rings = [], [], [], [], []
        self.parts = Particles(500)
        self.wave, self.queue, self.wave_clock, self.gap = 0, [], 0.0, 0.0
        self.banner, self.banner_t, self.banner_sub = "", 0.0, ""
        self.shake = 0.0
        self.ox = self.oy = 0
        self.dead_t = 0.0
        if self.preview:
            self._preview_scene()
        else:
            self._next_wave()

    def _preview_scene(self):
        u = self.u
        self.inv = 0.0
        for kind, fx, fy in (("tank", 0.5, 0.22), ("drone", 0.22, 0.32), ("drone", 0.78, 0.3), ("weaver", 0.32, 0.5), ("diver", 0.7, 0.48)):
            e = Enemy(kind, self.w * fx, self.h * fy, u, 1.0, 1)
            self.enemies.append(e)
        for k in range(5):
            self.shots.append([self.px + (k % 2 * 2 - 1) * 9 * u, self.py - (60 + 70 * k) * u, 0.0, -900 * u])
        self.ebullets.append([self.w * 0.5, self.h * 0.42, 0, 0, 5 * u])
        self.rings.append([self.w * 0.62, self.h * 0.36, 34 * u, 40 * u, 0.2, 0.5])
        self.parts.burst(self.w * 0.62, self.h * 0.36, ENEMY["drone"], n=26, speed=0, life=1.0, size=5 * u)
        for q in self.parts.p:
            a = random.uniform(0, math.tau); r = random.uniform(4, 30) * u
            q[0] += math.cos(a) * r; q[1] += math.sin(a) * r

    def _next_wave(self):
        self.wave += 1
        n, w, u = self.wave, self.w, self.u
        q, t = [], 1.2
        if n % 5 == 0:
            q.append((t, "boss", w / 2))
            self.banner_sub = "Boss incoming!"
        else:
            self.banner_sub = ""
            pats = ["line", "stream"] + (["weavers"] if n >= 2 else []) + (["divers"] if n >= 3 else []) + (["tank"] if n >= 4 else [])
            for _ in range(2 + min(4, n // 2)):
                p = random.choice(pats)
                if p == "line":
                    k = min(8, 4 + n // 2)
                    for i in range(k):
                        q.append((t, "drone", w * (i + 1) / (k + 1)))
                elif p == "stream":
                    x = random.uniform(w * 0.15, w * 0.85)
                    for i in range(5 + n // 3):
                        q.append((t + i * 0.32, "drone", x))
                elif p == "weavers":
                    for i in range(2 + n // 4):
                        q.append((t + i * 0.5, "weaver", random.uniform(w * 0.2, w * 0.8)))
                elif p == "divers":
                    for i in range(3 + n // 4):
                        q.append((t + i * 0.45, "diver", random.uniform(w * 0.1, w * 0.9)))
                else:
                    for i in range(1 + n // 7):
                        q.append((t + i * 0.8, "tank", random.uniform(w * 0.25, w * 0.75)))
                t += max(1.3, 2.6 - n * 0.08)
        self.queue = sorted(q)
        self.wave_clock = 0.0
        self.banner, self.banner_t = "WAVE %d" % n, 2.0

    # ------------------------------------------------------------------ update
    def handle(self, ev):
        return super().handle(ev)

    def update(self, dt, inp):
        super().update(dt, inp)
        u, w, h = self.u, self.w, self.h
        for s in self.stars:
            s[1] += s[2] * dt
            if s[1] > h:
                s[0], s[1] = random.uniform(0, w), -2
        self.parts.update(dt)
        for r in self.rings:
            r[4] += dt
        self.rings = [r for r in self.rings if r[4] < r[5]]
        self.shake = max(0.0, self.shake - dt * 2.2)
        amp = self.shake * 14 * u
        self.ox, self.oy = (random.uniform(-amp, amp), random.uniform(-amp, amp)) if amp > 0.5 else (0, 0)
        self.banner_t = max(0.0, self.banner_t - dt)
        if self.over:
            self._move_enemies(dt)
            return

        # player movement with a little inertia
        ax = (inp.pressed("right") or inp.pressed("d")) - (inp.pressed("left") or inp.pressed("a"))
        ay = (inp.pressed("down") or inp.pressed("s")) - (inp.pressed("up") or inp.pressed("w"))
        sp = 540 * u
        k = min(1.0, dt * 14)
        self.vx += (ax * sp - self.vx) * k
        self.vy += (ay * sp - self.vy) * k
        self.px = clamp(self.px + self.vx * dt, 24 * u, w - 24 * u)
        self.py = clamp(self.py + self.vy * dt, h * 0.35, h - 30 * u)
        self.inv = max(0.0, self.inv - dt)
        if self.weapon_t > 0:
            self.weapon_t -= dt
            if self.weapon_t <= 0:
                self.weapon = 1

        # firing
        self.cool -= dt
        if inp.pressed("space") and self.cool <= 0:
            self._fire()

        # spawning
        self.wave_clock += dt
        while self.queue and self.queue[0][0] <= self.wave_clock:
            _, kind, x = self.queue.pop(0)
            d = 1.0 + 0.07 * (self.wave - 1)
            e = Enemy(kind, x, -40 * u if kind != "boss" else -90 * u, u, d, self.wave)
            if kind == "diver":
                e.ty = random.uniform(h * 0.12, h * 0.32)
            elif kind == "tank":
                e.ty = random.uniform(h * 0.14, h * 0.24)
            elif kind == "boss":
                e.ty = h * 0.22
            self.enemies.append(e)
        if not self.queue and not self.enemies:
            self.gap += dt
            if self.gap > 1.0:
                self.gap = 0.0
                self._next_wave()

        # shots
        for s in self.shots:
            s[0] += s[2] * dt
            s[1] += s[3] * dt
        self.shots = [s for s in self.shots if -30 * u < s[1] < h + 30 and -30 < s[0] < w + 30]
        for b in self.ebullets:
            b[0] += b[2] * dt
            b[1] += b[3] * dt
        self.ebullets = [b for b in self.ebullets if -40 < b[1] < h + 40 and -40 < b[0] < w + 40]
        for p in self.powerups:
            p[1] += 120 * u * dt
            p[3] += dt
        self.powerups = [p for p in self.powerups if p[1] < h + 40]

        self._move_enemies(dt)
        self._collide()

    def _fire(self):
        u = self.u
        v = -950 * u
        x, y = self.px, self.py - 22 * u
        if self.weapon == 1:
            self.shots.append([x, y, 0.0, v])
        elif self.weapon == 2:
            self.shots += [[x - 9 * u, y + 4 * u, 0.0, v], [x + 9 * u, y + 4 * u, 0.0, v]]
        else:
            self.shots += [[x, y, 0.0, v], [x - 10 * u, y + 4 * u, -170 * u, v], [x + 10 * u, y + 4 * u, 170 * u, v]]
        self.cool = 0.13 if self.weapon == 1 else 0.11

    def _aim(self, e, speed, spread=0.0):
        a = math.atan2(self.py - e.y, self.px - e.x) + spread
        return [e.x, e.y + e.r * 0.6, math.cos(a) * speed, math.sin(a) * speed, 5 * self.u]

    def _move_enemies(self, dt):
        u, w, h = self.u, self.w, self.h
        alive = []
        for e in self.enemies:
            e.t += dt
            e.flash = max(0.0, e.flash - dt)
            k = e.kind
            if k == "drone":
                e.y += e.vy * dt
                e.x = e.x0 + math.sin(e.t * 2.2 + e.phase) * 42 * u
            elif k == "weaver":
                e.y += e.vy * dt
                e.x = clamp(e.x0 + math.sin(e.t * 1.5 + e.phase) * 150 * u, 20 * u, w - 20 * u)
            elif k == "diver":
                if e.state == 0:
                    e.y += e.vy * dt
                    if e.y >= e.ty:
                        e.state, e.st = 1, 0.0
                elif e.state == 1:
                    e.st += dt
                    e.x = e.x0 + math.sin(e.t * 40) * 2 * u
                    if e.st > 0.55:
                        a = math.atan2(self.py - e.y, self.px - e.x)
                        sp = 560 * u * (1 + 0.05 * self.wave)
                        e.vx, e.vy, e.state = math.cos(a) * sp, math.sin(a) * sp, 2
                else:
                    e.x += e.vx * dt
                    e.y += e.vy * dt
            elif k == "tank":
                if e.y < e.ty:
                    e.y += e.vy * dt
                else:
                    e.x += e.vx * dt
                    if e.x < 40 * u or e.x > w - 40 * u:
                        e.vx = -e.vx
                        e.x = clamp(e.x, 40 * u, w - 40 * u)
                    e.y += 6 * u * dt
            else:  # boss
                if e.y < e.ty:
                    e.y += e.vy * dt
                else:
                    e.x = w / 2 + math.sin(e.t * 0.65) * w * 0.3
            # enemy fire (not after the player is gone)
            if not self.over and e.y > 0:
                e.fire -= dt
                if e.fire <= 0:
                    self._enemy_fire(e)
            if -120 * u < e.y < h + 80 * u and -120 * u < e.x < w + 120 * u:
                alive.append(e)
        self.enemies = alive

    def _enemy_fire(self, e):
        u = self.u
        sp = (240 + 8 * self.wave) * u
        if e.kind == "drone":
            self.ebullets.append([e.x, e.y + e.r, 0.0, sp, 5 * u])
            e.fire = random.uniform(3.0, 6.0)
        elif e.kind == "weaver":
            self.ebullets.append(self._aim(e, sp))
            e.fire = random.uniform(2.2, 3.6)
        elif e.kind == "tank":
            for s in (-0.25, 0.0, 0.25):
                self.ebullets.append(self._aim(e, sp * 0.9, s))
            e.fire = 2.0
        elif e.kind == "boss":
            e.state = (e.state + 1) % 3
            if e.state == 0:
                for i in range(5):
                    self.ebullets.append(self._aim(e, sp * 1.1, (i - 2) * 0.12))
                e.fire = 1.1
            elif e.state == 1:
                n = 16
                off = e.t
                for i in range(n):
                    a = off + i * math.tau / n
                    self.ebullets.append([e.x, e.y, math.cos(a) * sp * 0.75, math.sin(a) * sp * 0.75, 6 * u])
                e.fire = 1.4
            else:
                for i in range(9):
                    a = math.pi / 2 + (i - 4) * 0.16
                    self.ebullets.append([e.x, e.y + e.r * 0.5, math.cos(a) * sp, math.sin(a) * sp, 5 * u])
                e.fire = 1.6

    def _explode(self, x, y, color, big=False):
        u = self.u
        self.parts.burst(x, y, color, n=40 if big else 18, speed=(420 if big else 260) * u, life=0.9 if big else 0.55, size=(6 if big else 4) * u)
        self.parts.burst(x, y, (255, 240, 200), n=12 if big else 6, speed=(260 if big else 150) * u, life=0.35, size=3 * u)
        self.rings.append([x, y, 8 * u, (120 if big else 46) * u, 0.0, 0.5 if big else 0.35])

    def _collide(self):
        u = self.u
        # player shots vs enemies
        for e in self.enemies:
            if e.hp <= 0:
                continue
            rr = (e.r + 5 * u) ** 2
            for s in self.shots:
                if s[1] < -1000:
                    continue
                if (s[0] - e.x) ** 2 + (s[1] - e.y) ** 2 < rr:
                    s[1] = -10000           # used up
                    e.hp -= 1
                    e.flash = 0.06
                    self.parts.burst(s[0], s[1] if s[1] > -1000 else e.y + e.r, (180, 230, 255), n=3, speed=120 * u, life=0.2, size=3 * u)
                    if e.hp <= 0:
                        self.score += e.pts
                        big = e.kind in ("tank", "boss")
                        self._explode(e.x, e.y, ENEMY[e.kind], big)
                        if e.kind == "boss":
                            self.shake = 1.0
                            for _ in range(2):
                                self.powerups.append([e.x + random.uniform(-40, 40) * u, e.y, random.choice("WS"), 0.0])
                            self.powerups.append([e.x, e.y, "+", 0.0])
                        elif random.random() < (0.35 if e.kind == "tank" else 0.07):
                            self.powerups.append([e.x, e.y, random.choice("WWSS+"), 0.0])
                        break
        self.shots = [s for s in self.shots if s[1] > -1000]
        self.enemies = [e for e in self.enemies if e.hp > 0]

        # power-ups
        keep = []
        for p in self.powerups:
            if (p[0] - self.px) ** 2 + (p[1] - self.py) ** 2 < (28 * u) ** 2:
                if p[2] == "W":
                    self.weapon, self.weapon_t = min(3, self.weapon + 1), 12.0
                elif p[2] == "S":
                    self.shield = 1
                else:
                    self.lives = min(5, self.lives + 1)
                self.score += 50
                self.parts.burst(p[0], p[1], T.C["cyan"], n=16, speed=200 * u, life=0.5, size=4 * u)
            else:
                keep.append(p)
        self.powerups = keep

        # things hitting the player
        if self.inv > 0:
            return
        pr = 11 * u
        hit = False
        for b in self.ebullets:
            if (b[0] - self.px) ** 2 + (b[1] - self.py) ** 2 < (pr + b[4]) ** 2:
                b[1] = 1e9
                hit = True
                break
        if not hit:
            for e in self.enemies:
                if (e.x - self.px) ** 2 + (e.y - self.py) ** 2 < (pr + e.r * 0.8) ** 2:
                    if e.kind != "boss":
                        e.hp = 0
                        self._explode(e.x, e.y, ENEMY[e.kind])
                    hit = True
                    break
            self.enemies = [e for e in self.enemies if e.hp > 0]
        if hit:
            self.ebullets = [b for b in self.ebullets if b[1] < 1e8]
            if self.shield:
                self.shield = 0
                self.inv = 1.0
                self.parts.burst(self.px, self.py, T.C["cyan"], n=24, speed=260 * u, life=0.5, size=4 * u)
                return
            self.lives -= 1
            self.shake = 0.7
            self._explode(self.px, self.py, WING, big=self.lives <= 0)
            if self.lives <= 0:
                self.end()
            else:
                self.inv = 2.0
                self.weapon, self.weapon_t = max(1, self.weapon - 1), self.weapon_t

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        u, ox, oy = self.u, self.ox, self.oy
        surf.blit(self.bg, (0, 0))
        fill = surf.fill
        for x, y, _, sz, br, layer in self.stars:
            fill((br, br, min(255, br + 30)), (int(x), int(y), sz, sz + (sz if layer == 2 else 0)))

        # power-ups
        for x, y, kind, t in self.powerups:
            self._draw_powerup(surf, x + ox, y + oy, kind, t)
        # enemies
        for e in self.enemies:
            self._draw_enemy(surf, e, ox, oy)
        # bullets
        g = self.g_ebul
        gw = g.get_width() // 2
        for x, y, _, _, r in self.ebullets:
            surf.blit(g, (int(x + ox) - gw, int(y + oy) - gw), special_flags=pygame.BLEND_ADD)
            pygame.draw.circle(surf, (255, 170, 80), (int(x + ox), int(y + oy)), int(r))
            pygame.draw.circle(surf, (255, 245, 200), (int(x + ox), int(y + oy)), max(1, int(r * 0.45)))
        g = self.g_shot
        gw = g.get_width() // 2
        lw = max(2, int(3 * u))
        for x, y, vx, vy in self.shots:
            sx, sy = int(x + ox), int(y + oy)
            surf.blit(g, (sx - gw, sy - gw), special_flags=pygame.BLEND_ADD)
            dx = vx / max(1.0, abs(vy)) * 16 * u
            pygame.draw.line(surf, (110, 210, 255), (sx, sy), (sx - dx, sy + 16 * u), lw)
            pygame.draw.line(surf, (235, 250, 255), (sx, sy), (sx - dx * 0.5, sy + 8 * u), max(1, lw // 2))
        # player
        if not (self.over and self.lives <= 0):
            if self.inv <= 0 or int(self.t * 12) % 2 == 0 or self.preview:
                self._draw_ship(surf, self.px + ox, self.py + oy, u)
            if self.shield:
                rr = int((30 + 2 * math.sin(self.t * 6)) * u)
                pygame.draw.circle(surf, (90, 220, 255), (int(self.px + ox), int(self.py + oy)), rr, max(1, int(2 * u)))
        # effects
        for x, y, r0, r1, t, life in self.rings:
            k = t / life
            col = mix((255, 230, 180), BG_BOTTOM, k)
            pygame.draw.circle(surf, col, (int(x + ox), int(y + oy)), int(r0 + (r1 - r0) * k), max(1, int(3 * u * (1 - k))))
        self.parts.draw(surf, BG_BOTTOM, ox, oy)

        if self.preview:
            return
        self._draw_hud(surf)
        if self.banner_t > 0 and not self.over:
            a = min(1.0, self.banner_t / 0.4, (2.0 - self.banner_t) / 0.3 + 0.0)
            col = mix(BG_BOTTOM, T.C["text"], a)
            self.hud_text(surf, self.banner, (self.w // 2, int(self.h * 0.4)), 46, "bold", col, "center")
            if self.banner_sub:
                self.hud_text(surf, self.banner_sub, (self.w // 2, int(self.h * 0.4) + T.px(44)), 20, "semibold", mix(BG_BOTTOM, T.C["warn"], a), "center")
        if self.over:
            lines = ["Score  %s" % format(int(self.score), ","), "Best  %s" % format(int(self.best), ","), "You reached wave %d" % self.wave]
            if self.flash_new_best:
                lines[1] += "  (new best!)"
            self.overlay(surf, "Game over", lines, "Press Space to play again")

    def _draw_hud(self, surf):
        top = self.top + T.px(14)
        self.hud_text(surf, format(int(self.score), ","), (T.px(22), top), 26, "bold")
        self.hud_text(surf, "BEST %s" % format(int(self.best), ","), (T.px(22), top + T.px(34)), 13, "medium", T.C["text2"])
        self.hud_text(surf, "WAVE %d" % self.wave, (self.w // 2, top + T.px(4)), 16, "semibold", T.C["text2"], "midtop")
        x = self.w - T.px(28)
        for _ in range(self.lives):
            self._draw_ship(surf, x, top + T.px(16), self.u * 0.55, flame=False)
            x -= T.px(30)
        if self.shield:
            self.hud_text(surf, "SHIELD", (self.w - T.px(22), top + T.px(36)), 12, "semibold", T.C["cyan"], "topright")
        if self.weapon > 1:
            w = T.px(90) * max(0.0, self.weapon_t) / 12.0
            r = pygame.Rect(self.w - T.px(112), top + T.px(56), T.px(90), T.px(5))
            pygame.draw.rect(surf, T.C["panel2"], r, border_radius=r.h)
            pygame.draw.rect(surf, WING, (r.x, r.y, int(w), r.h), border_radius=r.h)
            self.hud_text(surf, "SPREAD x%d" % self.weapon, (r.right, r.bottom + T.px(4)), 11, "semibold", WING, "topright")

    def _draw_ship(self, surf, x, y, u, flame=True):
        def P(pts):
            return [(x + a * u, y + b * u) for a, b in pts]
        if flame:
            fl = random.uniform(10, 20)
            for ex in (-9, 9):
                pygame.draw.polygon(surf, (255, 150, 50), P([(ex - 4, 14), (ex + 4, 14), (ex, 14 + fl)]))
                pygame.draw.polygon(surf, (255, 240, 170), P([(ex - 2, 14), (ex + 2, 14), (ex, 14 + fl * 0.55)]))
            g = self.g_eng
            surf.blit(g, (int(x - g.get_width() / 2), int(y + 10 * u)), special_flags=pygame.BLEND_ADD)
        pygame.draw.polygon(surf, shade(WING, 0.8), P([(0, -6), (26, 12), (22, 18), (6, 10), (-6, 10), (-22, 18), (-26, 12)]))
        pygame.draw.polygon(surf, HULL, P([(0, -28), (9, -6), (11, 14), (0, 9), (-11, 14), (-9, -6)]))
        pygame.draw.polygon(surf, shade(HULL, 1.25), P([(0, -28), (3, -6), (0, 6), (-3, -6)]))
        pygame.draw.ellipse(surf, COCKPIT, pygame.Rect(x - 4 * u, y - 14 * u, 8 * u, 12 * u))
        pygame.draw.line(surf, (255, 255, 255), (x - 1 * u, y - 12 * u), (x - 1 * u, y - 6 * u), max(1, int(u)))

    def _draw_enemy(self, surf, e, ox, oy):
        u = self.u
        x, y, r = e.x + ox, e.y + oy, e.r
        col = (255, 255, 255) if e.flash > 0 else ENEMY[e.kind]
        dark = shade(col, 0.55)

        def P(pts, s=1.0):
            return [(x + a * r * s, y + b * r * s) for a, b in pts]
        if e.kind == "drone":
            spin = e.t * 3
            for k in range(4):
                a = spin + k * math.pi / 2
                pygame.draw.line(surf, dark, (x, y), (x + math.cos(a) * r * 1.15, y + math.sin(a) * r * 1.15), max(2, int(3 * u)))
            pygame.draw.circle(surf, col, (int(x), int(y)), int(r * 0.78))
            pygame.draw.circle(surf, dark, (int(x), int(y)), int(r * 0.78), max(1, int(2 * u)))
            pygame.draw.circle(surf, (255, 240, 220), (int(x), int(y + r * 0.1)), max(2, int(r * 0.28)))
            pygame.draw.circle(surf, (40, 10, 10), (int(x), int(y + r * 0.15)), max(1, int(r * 0.13)))
        elif e.kind == "weaver":
            flap = math.sin(e.t * 10) * 0.25
            pygame.draw.polygon(surf, dark, P([(0, -0.3), (1.25, -0.6 - flap), (0.9, 0.5), (0.3, 0.3), (0, 0.6), (-0.3, 0.3), (-0.9, 0.5), (-1.25, -0.6 - flap)]))
            pygame.draw.polygon(surf, col, P([(0, -0.55), (0.45, 0.0), (0, 0.75), (-0.45, 0.0)]))
            pygame.draw.circle(surf, (230, 255, 240), (int(x), int(y)), max(2, int(r * 0.18)))
        elif e.kind == "diver":
            ang = math.atan2(e.vy, e.vx) - math.pi / 2 if e.state == 2 else 0.0
            ca, sa = math.cos(ang), math.sin(ang)
            pts = [(0, 1.1), (0.9, -0.7), (0.3, -0.35), (0, -0.9), (-0.3, -0.35), (-0.9, -0.7)]
            pygame.draw.polygon(surf, col, [(x + (a * ca - b * sa) * r, y + (a * sa + b * ca) * r) for a, b in pts])
            pygame.draw.polygon(surf, dark, [(x + (a * ca - b * sa) * r, y + (a * sa + b * ca) * r) for a, b in pts], max(1, int(2 * u)))
            if e.state == 1:
                pygame.draw.circle(surf, (255, 255, 200), (int(x), int(y)), int(r * (1.3 + 0.2 * math.sin(e.t * 30))), max(1, int(u)))
        elif e.kind == "tank":
            hexa = [(math.cos(k * math.pi / 3 + math.pi / 6), math.sin(k * math.pi / 3 + math.pi / 6) * 0.82) for k in range(6)]
            pygame.draw.polygon(surf, dark, P(hexa, 1.08))
            pygame.draw.polygon(surf, col, P(hexa, 0.9))
            pygame.draw.circle(surf, shade(col, 0.4), (int(x), int(y)), int(r * 0.42))
            pygame.draw.line(surf, shade(col, 0.4), (x, y), (x, y + r * 0.95), max(3, int(6 * u)))
            pygame.draw.circle(surf, (255, 220, 240), (int(x), int(y)), int(r * 0.2))
            # health pips
            pw = r * 1.6
            pygame.draw.rect(surf, (40, 20, 30), (x - pw / 2, y - r * 1.2, pw, max(2, 4 * u)))
            pygame.draw.rect(surf, (255, 120, 170), (x - pw / 2, y - r * 1.2, pw * e.hp / e.maxhp, max(2, 4 * u)))
        else:  # boss
            pulse = 0.5 + 0.5 * math.sin(e.t * 4)
            pygame.draw.polygon(surf, shade(col, 0.45), P([(-1.6, -0.2), (-0.6, -0.6), (0.6, -0.6), (1.6, -0.2), (1.2, 0.5), (0.4, 0.3), (0, 0.8), (-0.4, 0.3), (-1.2, 0.5)]))
            pygame.draw.polygon(surf, col, P([(-1.0, -0.15), (-0.4, -0.5), (0.4, -0.5), (1.0, -0.15), (0.6, 0.35), (0, 0.55), (-0.6, 0.35)]))
            pygame.draw.circle(surf, shade(col, 0.35), (int(x), int(y)), int(r * 0.38))
            pygame.draw.circle(surf, mix((255, 120, 60), (255, 240, 160), pulse), (int(x), int(y)), int(r * 0.24))
            for side in (-1, 1):
                pygame.draw.circle(surf, (255, 230, 120), (int(x + side * r * 0.62), int(y - r * 0.12)), max(2, int(r * 0.09)))
            # boss health bar
            bw = self.w * 0.5
            by = self.top + T.px(70)
            pygame.draw.rect(surf, (40, 14, 22), ((self.w - bw) / 2, by, bw, T.px(8)), border_radius=T.px(4))
            pygame.draw.rect(surf, (255, 70, 100), ((self.w - bw) / 2, by, bw * e.hp / e.maxhp, T.px(8)), border_radius=T.px(4))
            self.hud_text(surf, "MOTHERSHIP", (self.w // 2, by - T.px(4)), 11, "semibold", (255, 140, 160), "midbottom")

    def _draw_powerup(self, surf, x, y, kind, t):
        u = self.u
        col = {"W": WING, "S": T.C["cyan"], "+": T.C["ok"]}[kind]
        r = 13 * u
        a = t * 2.5
        pts = [(x + math.cos(a + k * math.pi / 2) * r, y + math.sin(a + k * math.pi / 2) * r) for k in range(4)]
        pygame.draw.polygon(surf, shade(col, 0.35), pts)
        pygame.draw.polygon(surf, col, pts, max(1, int(2 * u)))
        f = T.font("bold", 13)
        img = f.render(kind, True, (255, 255, 255))
        surf.blit(img, img.get_rect(center=(int(x), int(y))))
