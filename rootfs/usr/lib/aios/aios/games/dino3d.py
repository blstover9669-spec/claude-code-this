"""Dino Run 3D: a three-lane runner rendered in software with real perspective.

Left/Right (or A/D) switch lanes, Space/Up jumps (Down drops faster). Tall cacti must be dodged,
low rocks can be jumped, and gems give bonus points. The scene is drawn at half resolution with
flat-shaded polygons (painter's algorithm, per-face lighting, distance fog) and scaled up, so it
runs smoothly without a GPU.
"""
import math, random

import pygame

from .. import theme as T
from .common import Game, Particles, clamp, glow, mix, shade

LANES = (-1.9, 0.0, 1.9)
ROAD = 2.95                       # half width of the road
CAM_Y = 2.45
DINO_Z = 5.2
NEAR, FAR = 1.05, 64.0

SKY_TOP, SKY_MID, HORIZON = (16, 10, 44), (92, 28, 110), (255, 122, 160)
FOG = (232, 104, 156)
GROUND_NEAR, ROAD_NEAR = (30, 16, 52), (46, 28, 84)
GRID, EDGE = (224, 84, 230), (120, 230, 255)
BODY, BODY_D, SPIKE, EYE = (139, 92, 246), (98, 60, 196), (217, 70, 239), (245, 245, 255)
CACTUS, CACTUS_D = (52, 200, 130), (30, 140, 92)
ROCK, ROCK_D = (150, 128, 170), (110, 92, 132)
GEM = (110, 235, 255)

# per-face light: the top is brightest, the light comes from the right
LIGHT = {"top": 1.0, "right": 0.86, "left": 0.62, "back": 0.74}


class Dino3D(Game):
    id = "dino3d"
    title = "Dino Run 3D"
    blurb = "Three lanes, real 3D, and the road keeps getting faster."
    controls = "Left / Right lanes   Space jump"
    preview_view = (0.5, 0.58, 1.15)

    def __init__(self, size, top=0, preview=False):
        w, h = size
        self.iw, self.ih = max(160, w // 2), max(100, h // 2)
        self.buf = pygame.Surface((self.iw, self.ih))
        self.F = self.ih * 0.98
        self.cx, self.cy = self.iw / 2, self.ih * 0.38
        self.pad = int(self.iw * 0.08)
        self.bg = self._make_bg()
        super().__init__(size, top, preview)

    # ------------------------------------------------------------------ background
    def _make_bg(self):
        iw, ih, cy, pad = self.iw, self.ih, int(self.cy), self.pad
        bw = iw + pad * 2
        bg = pygame.Surface((bw, ih))
        for y in range(ih):
            if y < cy * 0.55:
                c = mix(SKY_TOP, SKY_MID, y / (cy * 0.55))
            elif y <= cy:
                c = mix(SKY_MID, HORIZON, (y - cy * 0.55) / (cy * 0.45))
            else:
                c = mix(FOG, GROUND_NEAR, ((y - cy) / (ih - cy)) ** 0.55)
            bg.fill(c, (0, y, bw, 1))
        rng = random.Random(5)
        for _ in range(60):  # stars
            x, y = rng.randrange(bw), rng.randrange(int(cy * 0.6))
            b = rng.randint(140, 255)
            bg.fill((b, b, min(255, b + 20)), (x, y, 1, 1))
        # striped synthwave sun
        sr = int(ih * 0.17)
        sx, sy = bw // 2, int(cy - sr * 0.55)
        g = glow(int(sr * 1.9), (255, 120, 170), 120)
        bg.blit(g, (sx - g.get_width() // 2, sy - g.get_height() // 2), special_flags=pygame.BLEND_ADD)
        for yy in range(-sr, sr + 1):
            half = int(math.sqrt(max(0, sr * sr - yy * yy)))
            t = (yy + sr) / (2 * sr)
            bg.fill(mix((255, 226, 120), (255, 70, 150), t), (sx - half, sy + yy, half * 2, 1))
        for k in range(6):
            yy = int(sy + sr * (0.15 + k * 0.15))
            th = 1 + k // 2
            bg.fill(mix(SKY_MID, HORIZON, 0.75 + k * 0.04), (sx - sr, yy, sr * 2, th))
        # two layers of mountains on the horizon
        for layer, (col, amp, step) in enumerate((((70, 26, 96), 0.13, 26), ((44, 18, 70), 0.08, 18))):
            pts, x, y = [], 0, cy - ih * amp * 0.5
            while x <= bw + step:
                y = clamp(y + rng.uniform(-ih * amp * 0.45, ih * amp * 0.45), cy - ih * amp, cy - 2)
                pts.append((x, y))
                x += step * rng.uniform(0.6, 1.4)
            pygame.draw.polygon(bg, col, [(0, cy + 1)] + pts + [(bw, cy + 1)])
            pygame.draw.lines(bg, mix(col, HORIZON, 0.45), False, pts, 1)
        pygame.draw.line(bg, mix(HORIZON, (255, 255, 255), 0.4), (0, cy), (bw, cy), 1)
        return bg

    # ------------------------------------------------------------------ state
    def reset(self):
        super().reset()
        self.lane = 1
        self.x = 0.0
        self.y, self.vy = 0.0, 0.0
        self.camx = 0.0
        self.speed = 15.0
        self.dist = 0.0
        self.rows = []                  # obstacles: dicts with z, items [(kind, lane)], gems [(lane, dz, alive)]
        self.props = []                 # roadside scenery
        self.next_row = 26.0
        self.gems = 0
        self.run = 0.0
        self.shake = 0.0
        self.parts = Particles(220)
        self.bonus = []                 # floating "+25" texts on the internal surface
        for _ in range(14):
            self._spawn_prop(random.uniform(8, FAR))
        if self.preview:
            self.y = 0.75
            self.rows = [{"z": 12.0, "items": [("cactus", 0), ("rock", 2)], "gems": []},
                         {"z": 22.0, "items": [("cactus", 1)], "gems": [[0, 0.0, True], [2, 0.0, True]]},
                         {"z": 34.0, "items": [("rock", 0), ("rock", 1), ("rock", 2)], "gems": []}]
            self.run = 0.7

    def _spawn_prop(self, z):
        side = random.choice((-1, 1))
        self.props.append({"x": side * random.uniform(3.9, 8.5), "z": z, "kind": random.choice(("cactus", "cactus", "rock")),
                           "s": random.uniform(0.6, 1.15)})

    def _spawn_row(self, z):
        lanes = [0, 1, 2]
        random.shuffle(lanes)
        r = random.random()
        if self.score > 220 and r < 0.16:
            items = [("rock", 0), ("rock", 1), ("rock", 2)]
            free = []
        elif r < 0.45:
            items = [("cactus", lanes[0])]
            free = lanes[1:]
        elif r < 0.72:
            items = [("cactus", lanes[0]), ("cactus", lanes[1])]
            free = lanes[2:]
        elif r < 0.88:
            items = [("cactus", lanes[0]), ("rock", lanes[1])]
            free = lanes[2:]
        else:
            items = [("rock", lanes[0])]
            free = lanes[1:]
        gems = []
        if free and random.random() < 0.55:
            gl = random.choice(free)
            gems = [[gl, -k * 1.6, True] for k in range(random.choice((1, 3, 4)))]
        self.rows.append({"z": z, "items": items, "gems": gems})

    # ------------------------------------------------------------------ input / update
    def handle(self, ev):
        if super().handle(ev):
            return True
        if self.over or ev.type != "key" or not ev.down or ev.repeat:
            return False
        if ev.key in ("left", "a"):
            self.lane = max(0, self.lane - 1)
            return True
        if ev.key in ("right", "d"):
            self.lane = min(2, self.lane + 1)
            return True
        if ev.key in ("space", "up", "w") and self.y <= 0.001:
            self.vy = 7.9
            return True
        return False

    def update(self, dt, inp):
        super().update(dt, inp)
        self.parts.update(dt)
        self.shake = max(0.0, self.shake - dt * 2.5)
        for b in self.bonus:
            b[2] -= dt
        self.bonus = [b for b in self.bonus if b[2] > 0]
        if self.over:
            return
        self.speed = min(36.0, self.speed + 0.28 * dt)
        mv = self.speed * dt
        self.dist += mv
        self.score = int(self.dist) + self.gems * 25
        # dino
        self.x += (LANES[self.lane] - self.x) * min(1.0, dt * 13)
        if self.y > 0 or self.vy > 0:
            g = 23.0 * (2.6 if (inp.pressed("down") or inp.pressed("s")) else 1.0)
            self.vy -= g * dt
            self.y += self.vy * dt
            if self.y <= 0:
                self.y, self.vy = 0.0, 0.0
        if self.y <= 0 and (inp.pressed("space") or inp.pressed("up") or inp.pressed("w")):
            self.vy = 7.9
        self.run += dt * self.speed * 0.55
        self.camx += (self.x * 0.62 - self.camx) * min(1.0, dt * 6)
        # world
        for r in self.rows:
            r["z"] -= mv
        for p in self.props:
            p["z"] -= mv
        self.rows = [r for r in self.rows if r["z"] > NEAR + 0.4]
        self.props = [p for p in self.props if p["z"] > NEAR + 0.2]
        while len(self.props) < 14:
            self._spawn_prop(FAR + random.uniform(0, 10))
        far_z = max([r["z"] for r in self.rows], default=0.0)
        self.next_row -= mv
        if self.next_row <= 0:
            self._spawn_row(max(FAR, far_z + 4))
            self.next_row = max(8.5, 17.0 - self.speed * 0.22) + random.uniform(0, 6)
        self._collide()

    def _collide(self):
        x, y = self.x, self.y
        for r in self.rows:
            z = r["z"]
            if abs(z - DINO_Z) < 0.75:
                for kind, lane in r["items"]:
                    lx = LANES[lane]
                    half, hgt = (0.36, 1.9) if kind == "cactus" else (0.78, 0.56)
                    if abs(lx - x) < half + 0.3 and y < hgt - 0.06:
                        self.end()
                        self.shake = 0.8
                        sx, sy = self._proj(x, 0.9, DINO_Z)
                        self.parts.burst(sx, sy, SPIKE, n=30, speed=150, life=0.7, size=4, gravity=260)
                        return
            for gem in r["gems"]:
                if gem[2] and abs(z + gem[1] - DINO_Z) < 0.8 and abs(LANES[gem[0]] - x) < 0.75 and y < 1.6:
                    gem[2] = False
                    self.gems += 1
                    sx, sy = self._proj(LANES[gem[0]], 0.8, DINO_Z)
                    self.parts.burst(sx, sy, GEM, n=14, speed=110, life=0.5, size=3)
                    self.bonus.append([sx, sy, 0.8])

    # ------------------------------------------------------------------ rendering
    def _proj(self, x, y, z):
        s = self.F / z
        return self.cx + (x - self.camx) * s, self.cy + (CAM_Y + self.y * 0.15 - y) * s

    def _box(self, out, x0, x1, y0, y1, z0, z1, col):
        """Add the visible faces of an axis-aligned box to `out` as (depth, colour, points)."""
        if z1 <= NEAR:
            return
        if z0 < NEAR:
            z0 = NEAR
        F, cx, cy, camx = self.F, self.cx, self.cy, self.camx
        camy = CAM_Y + self.y * 0.15
        s0, s1 = F / z0, F / z1
        ax0, ax1 = (x0 - camx), (x1 - camx)
        X0n, X1n, X0f, X1f = cx + ax0 * s0, cx + ax1 * s0, cx + ax0 * s1, cx + ax1 * s1
        Y0n, Y1n = cy + (camy - y0) * s0, cy + (camy - y1) * s0
        Y0f, Y1f = cy + (camy - y0) * s1, cy + (camy - y1) * s1
        d = (z0 + z1) * 0.5
        fk = clamp((d - 9.0) / (FAR - 9.0), 0.0, 1.0) ** 0.8 * 0.92
        out.append((d, mix(shade(col, LIGHT["back"]), FOG, fk), ((X0n, Y1n), (X1n, Y1n), (X1n, Y0n), (X0n, Y0n))))
        if camy > y1:
            out.append((d, mix(shade(col, LIGHT["top"]), FOG, fk), ((X0n, Y1n), (X1n, Y1n), (X1f, Y1f), (X0f, Y1f))))
        if camx < x0:
            out.append((d, mix(shade(col, LIGHT["left"]), FOG, fk), ((X0n, Y1n), (X0f, Y1f), (X0f, Y0f), (X0n, Y0n))))
        elif camx > x1:
            out.append((d, mix(shade(col, LIGHT["right"]), FOG, fk), ((X1n, Y1n), (X1f, Y1f), (X1f, Y0f), (X1n, Y0n))))

    def _ground_quad(self, x0, x1, z0, z1, col):
        z0 = max(z0, NEAR)
        if z1 <= z0:
            return
        a, b = self._proj(x0, 0, z0), self._proj(x1, 0, z0)
        c, d = self._proj(x1, 0, z1), self._proj(x0, 0, z1)
        pygame.draw.polygon(self.buf, col, (a, b, c, d))

    def _fog(self, col, z):
        return mix(col, FOG, clamp((z - 9.0) / (FAR - 9.0), 0.0, 1.0) ** 0.8 * 0.92)

    def draw(self, surf):
        buf = self.buf
        sh = self.shake
        jx = random.uniform(-sh, sh) * 6 if sh > 0.05 else 0
        buf.blit(self.bg, (-self.pad - int(self.camx * self.pad * 0.35) + jx, 0))
        # road in depth bands (each fogged), then moving cross stripes, lane dashes and neon edges
        zs = [NEAR, 2, 3, 4.5, 6.5, 9, 13, 19, 28, 42, FAR]
        for i in range(len(zs) - 1):
            self._ground_quad(-ROAD, ROAD, zs[i], zs[i + 1], self._fog(ROAD_NEAR, zs[i]))
        off = self.dist % 3.0
        z = 3.0 - off
        while z < FAR:
            if z > NEAR:
                col = self._fog(mix(ROAD_NEAR, GRID, 0.45), z)
                self._ground_quad(-ROAD, ROAD, z, z + 0.12 + z * 0.004, col)
                for lx in (-0.95, 0.95):
                    self._ground_quad(lx - 0.05, lx + 0.05, z + 0.6, z + 2.0, self._fog((200, 170, 230), z))
            z += 3.0
        for i in range(len(zs) - 1):
            col = self._fog(EDGE, zs[i])
            self._ground_quad(-ROAD - 0.1, -ROAD + 0.03, zs[i], zs[i + 1], col)
            self._ground_quad(ROAD - 0.03, ROAD + 0.1, zs[i], zs[i + 1], col)
        # dino shadow on the road
        k = max(0.35, 1.0 - self.y * 0.4)
        pts = [self._proj(self.x + math.cos(a) * 0.55 * k, 0.0, DINO_Z + 0.05 + math.sin(a) * 0.65 * k) for a in [i * math.tau / 12 for i in range(12)]]
        pygame.draw.polygon(buf, mix(ROAD_NEAR, (0, 0, 0), 0.45), pts)

        faces = []
        box = self._box
        for p in self.props:
            x, z, s = p["x"], p["z"], p["s"]
            if p["kind"] == "cactus":
                box(faces, x - 0.22 * s, x + 0.22 * s, 0, 1.5 * s, z - 0.22 * s, z + 0.22 * s, CACTUS_D)
                box(faces, x - 0.6 * s, x - 0.22 * s, 0.7 * s, 0.9 * s, z - 0.12 * s, z + 0.12 * s, CACTUS_D)
            else:
                box(faces, x - 0.6 * s, x + 0.6 * s, 0, 0.45 * s, z - 0.5 * s, z + 0.5 * s, ROCK_D)
        for r in self.rows:
            z = r["z"]
            for kind, lane in r["items"]:
                lx = LANES[lane]
                if kind == "cactus":
                    box(faces, lx - 0.3, lx + 0.3, 0, 1.9, z - 0.3, z + 0.3, CACTUS)
                    box(faces, lx - 0.78, lx - 0.3, 0.82, 1.06, z - 0.16, z + 0.16, CACTUS)
                    box(faces, lx - 0.78, lx - 0.54, 1.06, 1.5, z - 0.16, z + 0.16, CACTUS)
                    box(faces, lx + 0.3, lx + 0.74, 1.08, 1.3, z - 0.16, z + 0.16, CACTUS)
                    box(faces, lx + 0.5, lx + 0.74, 1.3, 1.68, z - 0.16, z + 0.16, CACTUS)
                else:
                    box(faces, lx - 0.78, lx + 0.78, 0, 0.42, z - 0.48, z + 0.48, ROCK)
                    box(faces, lx - 0.5, lx + 0.46, 0.42, 0.58, z - 0.32, z + 0.3, ROCK)
        self._dino(faces)
        faces.sort(key=lambda f: f[0], reverse=True)
        draw_poly = pygame.draw.polygon
        for _, col, pts in faces:
            draw_poly(buf, col, pts)
        # gems: spinning diamonds (drawn after solids that are behind them is good enough)
        for r in self.rows:
            for lane, dz, alive in r["gems"]:
                gz = r["z"] + dz
                if not alive or gz <= NEAR + 0.2:
                    continue
                x, y = self._proj(LANES[lane], 0.8 + 0.12 * math.sin(self.t * 4 + gz), gz)
                s = self.F / gz * 0.28
                hw = s * (0.35 + 0.65 * abs(math.cos(self.t * 3 + gz)))
                col = self._fog(GEM, gz)
                draw_poly(buf, col, ((x, y - s), (x + hw, y), (x, y + s), (x - hw, y)))
                draw_poly(buf, self._fog((235, 255, 255), gz), ((x, y - s), (x + hw * 0.4, y), (x, y + s * 0.2), (x - hw * 0.4, y)))
        self.parts.draw(buf, ROAD_NEAR)
        f = T.font("bold", 11)
        for x, y, life in self.bonus:
            img = f.render("+25", True, mix(FOG, GEM, min(1.0, life * 2)))
            buf.blit(img, (x - img.get_width() / 2, y - 22 + (0.8 - life) * -30))
        pygame.transform.scale(buf, self.size, surf)
        if self.preview:
            return
        top = self.top + T.px(14)
        self.hud_text(surf, format(self.score, ","), (T.px(22), top), 26, "bold")
        self.hud_text(surf, "BEST %s" % format(self.best, ","), (T.px(22), top + T.px(34)), 13, "medium", T.C["text2"])
        self.hud_text(surf, "GEMS %d" % self.gems, (self.w - T.px(22), top + T.px(4)), 16, "semibold", GEM, "topright")
        self.hud_text(surf, "SPEED %.1fx" % (self.speed / 15.0), (self.w - T.px(22), top + T.px(28)), 13, "medium", T.C["text2"], "topright")
        if self.t < 3.2 and not self.over:
            self.hud_text(surf, "Left / Right to change lanes  ·  Space to jump", (self.w // 2, int(self.h * 0.72)), 18, "semibold", T.C["text"], "center")
        if self.over:
            lines = ["Score  %s" % format(self.score, ","), "Gems  %d" % self.gems, "Best  %s" % format(self.best, ",") + ("  (new best!)" if self.flash_new_best else "")]
            self.overlay(surf, "Crashed!", lines, "Press Space to run again")

    def _dino(self, faces):
        x, y, z = self.x, self.y, DINO_Z
        body = (235, 80, 90) if self.over else BODY
        dark = shade(body, 0.72)
        sw = math.sin(self.run * math.tau * 0.5) * (0.22 if y <= 0 and not self.over else 0.0)
        b = self._box
        b(faces, x - 0.09, x + 0.09, y + 0.55, y + 0.72, z - 1.38, z - 0.95, dark)          # tail tip
        b(faces, x - 0.16, x + 0.16, y + 0.55, y + 0.9, z - 0.98, z - 0.45, body)            # tail
        b(faces, x - 0.06, x + 0.06, y + 0.9, y + 1.02, z - 0.82, z - 0.68, SPIKE)
        b(faces, x - 0.32, x - 0.1, y, y + 0.56, z - 0.14 + sw, z + 0.16 + sw, dark)          # legs
        b(faces, x + 0.1, x + 0.32, y, y + 0.56, z - 0.14 - sw, z + 0.16 - sw, dark)
        b(faces, x - 0.37, x + 0.37, y + 0.48, y + 1.2, z - 0.5, z + 0.42, body)              # body
        b(faces, x - 0.07, x + 0.07, y + 1.2, y + 1.4, z - 0.34, z - 0.16, SPIKE)              # back spikes
        b(faces, x - 0.07, x + 0.07, y + 1.2, y + 1.46, z - 0.06, z + 0.12, SPIKE)
        b(faces, x - 0.34, x - 0.22, y + 0.74, y + 0.92, z + 0.36, z + 0.64, dark)            # arms
        b(faces, x + 0.22, x + 0.34, y + 0.74, y + 0.92, z + 0.36, z + 0.64, dark)
        b(faces, x - 0.2, x + 0.2, y + 1.0, y + 1.42, z + 0.18, z + 0.56, body)              # neck
        b(faces, x - 0.28, x + 0.28, y + 1.3, y + 1.7, z + 0.34, z + 0.98, body)              # head
        b(faces, x - 0.3, x - 0.27, y + 1.5, y + 1.62, z + 0.58, z + 0.72, EYE)              # eyes
        b(faces, x + 0.27, x + 0.3, y + 1.5, y + 1.62, z + 0.58, z + 0.72, EYE)
