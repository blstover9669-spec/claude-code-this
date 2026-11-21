"""AI OS loading screen: how far loading has got, and three games to play meanwhile.

The starter's /init runs `python3 -m aios.loader_ui` in the background while it reads the rest
of AI OS from the disc. Progress comes from boot.read_progress() (written by /sbin/ai-progress
and, at the end, by the chat). When progress says `done`, the screen shows "AI OS is ready" for
about a second and exits, even in the middle of a game, so the chat can take over the screen.

Nothing here may hold up the boot: any failure ends this program quickly and the boot carries
on with its text progress bar. Only modules in the starter's trimmed standard library are used.
"""
import math, os, random, signal, sys, time, traceback, warnings

warnings.filterwarnings("ignore", message=".*avx2.*")   # Alpine's pygame build notice; harmless
import pygame  # noqa: E402

from . import boot, display, theme as T
from .display import Event  # noqa: F401  (re-exported for tests)

TIPS = [
    "Ask the AI to make a game, then press Run on the file it writes.",
    "Apps you make are .c, .py or .sh files. /run name starts one.",
    "Type /iso to pack your apps into a bootable copy of AI OS.",
    "Wi-Fi: open Wi-Fi in the sidebar (or type /wifi) once the chat is up.",
    "Everything runs from memory: the USB stick can come out once AI OS is ready.",
]
STRIP = 38          # design-pixel height of the progress strip shown over a game


class Texts:
    """Rendered text, kept so unchanged labels aren't re-rendered every frame."""

    def __init__(self):
        self.cache = {}

    def get(self, s, role="regular", size=15, color=None):
        color = tuple(color or T.C["text"])
        key = (s, role, size, color, T.px(100))
        img = self.cache.get(key)
        if img is None:
            if len(self.cache) > 400:
                self.cache.clear()
            img = T.font(role, size).render(s, True, color)
            self.cache[key] = img
        return img


def _rounded(img, radius):
    """A copy of `img` with rounded corners (transparent outside)."""
    out = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    out.blit(img, (0, 0))
    mask = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return out


def _glow(radius, color, strength):
    """A soft light for additive blits (same idea as games.common.glow, kept local and cheap)."""
    d = radius * 2
    s = pygame.Surface((d, d))
    k = strength / 255.0
    steps = max(8, radius // 3)
    for i in range(steps):
        r = radius * (1 - i / steps)
        f = (1 - r / radius) ** 2
        pygame.draw.circle(s, (int(color[0] * f * k), int(color[1] * f * k), int(color[2] * f * k)), (radius, radius), max(1, int(r)))
    return s


class LoaderUI:
    def __init__(self, disp, inp):
        self.d, self.inp = disp, inp
        self.w, self.h = disp.size
        self.tx = Texts()
        self.state = "menu"               # menu | game | ready
        self.sel = 0
        self.game = None
        self.game_id = None
        self.progress = None              # latest dict from boot.read_progress()
        self.shown = 0.0                  # displayed fraction (eases towards the real one)
        self.last_poll = 0.0
        self.ready_t = 0.0
        self.t = 0.0
        self.tip = random.randrange(len(TIPS))
        self.tip_t = 0.0
        self.notice = ""                  # e.g. a game that failed to start
        self.notice_t = 0.0
        self.hover = None
        try:
            from . import games
            self.games = games.GAMES
        except Exception:                 # no games: still a perfectly good loading screen
            traceback.print_exc()
            self.games = []
        self._layout()
        self._prerender()

    # ------------------------------------------------------------------ layout & static art
    def _layout(self):
        px = T.px
        w, h = self.w, self.h
        self.logo_y = px(70)
        self.bar = pygame.Rect(0, 0, min(px(760), w - px(80)), px(14))
        self.bar.midtop = (w // 2, px(250))
        n = max(1, len(self.games))
        gap = px(28)
        cw = min(px(330), (w - px(80) - gap * (n - 1)) // n)
        ch = int(cw * 0.86)
        total = n * cw + (n - 1) * gap
        top = max(self.bar.bottom + px(150), int(h * 0.5))      # room for a two-line error under the bar
        if top + ch + px(90) > h:
            top = max(self.bar.bottom + px(70), h - ch - px(90))
        self.cards = [pygame.Rect((w - total) // 2 + i * (cw + gap), top, cw, ch) for i in range(len(self.games))]
        self.cards_title_y = top - px(46)
        self.preview_h = int(ch * 0.56)

    def _prerender(self):
        px = T.px
        w, h = self.w, self.h
        # background: deep gradient, a faint dot grid and a few stars
        bg = pygame.Surface((w, h))
        top, bottom = (10, 9, 22), (20, 12, 34)
        for y in range(h):
            k = y / max(1, h - 1)
            bg.fill((int(top[0] + (bottom[0] - top[0]) * k), int(top[1] + (bottom[1] - top[1]) * k),
                     int(top[2] + (bottom[2] - top[2]) * k)), (0, y, w, 1))
        step = px(34)
        dot = (32, 30, 52)
        for yy in range(step // 2, h, step):
            for xx in range(step // 2, w, step):
                bg.fill(dot, (xx, yy, max(1, px(2)), max(1, px(2))))
        rnd = random.Random(3)
        for _ in range(int(w * h / 14000)):
            c = rnd.randint(60, 150)
            bg.fill((c, c, min(255, c + 30)), (rnd.randrange(w), rnd.randrange(h), 1, 1))
        self.bg = bg
        self.glow_a = _glow(int(h * 0.55), (140, 40, 220), 60)
        self.glow_b = _glow(int(h * 0.45), (220, 40, 160), 52)
        self.glow_c = _glow(px(110), T.C["accent"], 140)
        # the logo badge: a rounded square with the AI OS gradient and a four-point spark
        s = px(84)
        badge = pygame.Surface((s, s), pygame.SRCALPHA)
        T.gradient_rect(badge, (0, 0, s, s), T.C["accent"], T.C["accent2"], radius=22, horizontal=False)
        cx = cy = s / 2
        for k in range(4):
            a = k * math.pi / 2
            pts = [(cx, cy), (cx + math.cos(a - 0.42) * s * 0.13, cy + math.sin(a - 0.42) * s * 0.13),
                   (cx + math.cos(a) * s * 0.36, cy + math.sin(a) * s * 0.36),
                   (cx + math.cos(a + 0.42) * s * 0.13, cy + math.sin(a + 0.42) * s * 0.13)]
            pygame.draw.polygon(badge, (255, 255, 255), pts)
        pygame.draw.circle(badge, (255, 255, 255), (int(s * 0.74), int(s * 0.27)), max(2, int(s * 0.055)))
        self.badge = badge
        # the bar's fill gradient (full width; partial fills blit part of it)
        b = self.bar
        self.bar_fill = pygame.Surface(b.size, pygame.SRCALPHA)
        T.gradient_rect(self.bar_fill, (0, 0, b.w, b.h), T.C["accent"], T.C["accent2"], radius=b.h / 2 / max(0.01, T.px(100) / 100))
        shim = pygame.Surface((px(160), b.h), pygame.SRCALPHA)
        for x in range(shim.get_width()):
            a = int(90 * math.sin(math.pi * x / max(1, shim.get_width() - 1)) ** 2)
            pygame.draw.line(shim, (255, 255, 255, a), (x, 0), (x, b.h))
        self.shimmer = shim
        # game card previews: drawn lazily, one per frame (see update), so the first frame is quick
        self.previews = [None] * len(self.games)

    def _make_preview(self, i):
        """Render game i's preview scene twice the card size, crop around its action, scale down."""
        px = T.px
        gid, title, blurb, controls, cls = self.games[i]
        size = (self.cards[i].w - px(16), self.preview_h)
        try:
            rw, rh = size[0] * 2, size[1] * 2
            big = pygame.Surface((rw, rh))
            cls((rw, rh), preview=True).draw(big)
            fx, fy, zoom = getattr(cls, "preview_view", (0.5, 0.5, 1.0))
            cw, ch = int(rw / zoom), int(rh / zoom)
            crop = pygame.Rect(0, 0, cw, ch)
            crop.center = (int(rw * fx), int(rh * fy))
            crop.clamp_ip(big.get_rect())
            img = pygame.transform.smoothscale(big.subsurface(crop), size)
        except Exception:
            traceback.print_exc()
            img = pygame.Surface(size)
            img.fill(T.C["panel2"])
            T.icon(img, "gamepad", (size[0] // 2 - px(30), size[1] // 2 - px(30), px(60), px(60)), T.C["text2"])
        self.previews[i] = _rounded(img, px(12))

    # ------------------------------------------------------------------ progress
    def poll_progress(self):
        now = time.monotonic()
        if now - self.last_poll < 0.2:
            return
        self.last_poll = now
        p = boot.read_progress()
        if p is not None:
            self.progress = p
            if p.get("done") and self.state != "ready":
                self.state = "ready"
                self.ready_t = 0.0

    def fraction(self):
        return float((self.progress or {}).get("fraction", 0.0) or 0.0)

    def stage(self):
        p = self.progress or {}
        return p.get("stage") or "Starting AI OS"

    # ------------------------------------------------------------------ input
    def start_game(self, i):
        gid, title, blurb, controls, cls = self.games[i]
        try:
            self.game = cls(self.d.size, top=T.px(STRIP))
            self.game_id = gid
            self.state = "game"
        except Exception:
            traceback.print_exc()
            self.notice, self.notice_t = "%s couldn't start." % title, 3.0
            self.game = None

    def handle(self, ev):
        if self.state == "ready":
            return
        if self.state == "game":
            if ev.type == "key" and ev.down and ev.key == "escape":
                self.state, self.game = "menu", None
                return
            try:
                self.game.handle(ev)
            except Exception:
                traceback.print_exc()
                self.state, self.game = "menu", None
                self.notice, self.notice_t = "The game stopped because of an error.", 3.0
            return
        n = len(self.games)
        if ev.type == "key" and ev.down and n:
            if ev.key in ("left", "a"):
                self.sel = (self.sel - 1) % n
            elif ev.key in ("right", "d", "tab"):
                self.sel = (self.sel + 1) % n
            elif ev.key in ("return", "space"):
                self.start_game(self.sel)
            elif ev.key in ("1", "2", "3") and int(ev.key) <= n:
                self.sel = int(ev.key) - 1
                self.start_game(self.sel)
        elif ev.type == "mouse_move":
            self.hover = None
            for i, r in enumerate(self.cards):
                if r.collidepoint(ev.pos):
                    self.hover = self.sel = i
        elif ev.type == "mouse_button" and ev.down and ev.button == 1:
            for i, r in enumerate(self.cards):
                if r.collidepoint(ev.pos):
                    self.sel = i
                    self.start_game(i)

    # ------------------------------------------------------------------ update & draw
    def update(self, dt):
        self.t += dt
        if self.state == "menu" and self.t > 0.05:
            for i, pv in enumerate(self.previews):
                if pv is None:
                    self._make_preview(i)
                    break
        self.tip_t += dt
        if self.tip_t > 7.0:
            self.tip_t = 0.0
            self.tip = (self.tip + 1) % len(TIPS)
        self.notice_t = max(0.0, self.notice_t - dt)
        target = 1.0 if self.state == "ready" else self.fraction()
        self.shown += (target - self.shown) * min(1.0, dt * 4.0)
        if abs(target - self.shown) < 0.002:
            self.shown = target
        if self.state == "game" and self.game is not None:
            try:
                self.game.update(dt, self.inp)
            except Exception:
                traceback.print_exc()
                self.state, self.game = "menu", None
                self.notice, self.notice_t = "The game stopped because of an error.", 3.0
        if self.state == "ready":
            self.ready_t += dt

    def draw(self):
        s = self.d.surface
        if self.state == "game" or (self.state == "ready" and self.game is not None):
            try:
                self.game.draw(s)
            except Exception:
                traceback.print_exc()
                self.game = None
                self._draw_menu(s)
            else:
                self._draw_strip(s)
        else:
            self._draw_menu(s)
        if self.state == "ready":
            self._draw_ready(s)
        if self.inp.mouse_seen and self.state != "ready":
            T.draw_pointer(s, self.inp.mouse_pos)

    def _draw_background(self, s):
        s.blit(self.bg, (0, 0))
        w, h = self.w, self.h
        t = self.t
        for g, fx, fy, ax, ay, sp in ((self.glow_a, 0.22, 0.25, 0.08, 0.06, 0.13), (self.glow_b, 0.8, 0.7, 0.07, 0.08, 0.11)):
            x = w * (fx + ax * math.sin(t * sp * math.tau))
            y = h * (fy + ay * math.cos(t * sp * 0.8 * math.tau))
            s.blit(g, (int(x - g.get_width() / 2), int(y - g.get_height() / 2)), special_flags=pygame.BLEND_ADD)

    def _draw_menu(self, s):
        px = T.px
        w = self.w
        self._draw_background(s)
        # logo: badge with a soft pulse of light behind it, then the wordmark
        word = self.tx.get("AI OS", "bold", 54)
        total = self.badge.get_width() + px(22) + word.get_width()
        x0 = (w - total) // 2
        by = self.logo_y
        pulse = 0.75 + 0.25 * math.sin(self.t * 2.2)
        g = self.glow_c
        g.set_alpha(int(255 * pulse))
        s.blit(g, (x0 + self.badge.get_width() // 2 - g.get_width() // 2, by + self.badge.get_height() // 2 - g.get_height() // 2), special_flags=pygame.BLEND_ADD)
        s.blit(self.badge, (x0, by))
        s.blit(word, (x0 + self.badge.get_width() + px(22), by + (self.badge.get_height() - word.get_height()) // 2))
        sub = self.tx.get("Getting everything ready. Play a game while you wait.", "regular", 17, T.C["text2"])
        s.blit(sub, sub.get_rect(midtop=(w // 2, by + self.badge.get_height() + px(22))))
        self._draw_progress(s)
        # games
        if self.games:
            head = self.tx.get("PLAY WHILE YOU WAIT", "bold", 13, T.C["muted"])
            s.blit(head, head.get_rect(midtop=(w // 2, self.cards_title_y)))
            for i, r in enumerate(self.cards):
                self._draw_card(s, i, r)
            hint = "Left / Right choose   ·   Enter play   ·   Esc back to this menu"
            img = self.tx.get(hint, "regular", 13, T.C["muted"])
            s.blit(img, img.get_rect(midtop=(w // 2, self.cards[0].bottom + px(26))))
        # rotating tip at the bottom
        k = min(1.0, self.tip_t / 0.6, (7.0 - self.tip_t) / 0.6)
        tip = self.tx.get("Tip: " + TIPS[self.tip], "regular", 14, T.C["text2"])
        tip = tip.copy()
        tip.set_alpha(int(255 * max(0.0, k)))
        s.blit(tip, tip.get_rect(midbottom=(w // 2, self.h - px(22))))
        if self.notice_t > 0:
            img = self.tx.get(self.notice, "semibold", 14, T.C["warn"])
            s.blit(img, img.get_rect(midbottom=(w // 2, self.h - px(52))))

    def _draw_progress(self, s):
        px = T.px
        b = self.bar
        p = self.progress or {}
        err = p.get("error")
        stage = self.tx.get(self.stage(), "semibold", 17, T.C["text"])
        s.blit(stage, (b.x, b.y - px(14) - stage.get_height()))
        pct = self.tx.get("%d%%" % int(round(self.shown * 100)), "bold", 17, T.C["accent"])
        s.blit(pct, (b.right - pct.get_width(), b.y - px(14) - pct.get_height()))
        self._bar(s, b, self.shown, shimmer=not err)
        if err:
            box = pygame.Rect(b.x, b.bottom + px(16), b.w, px(10))
            lines = T.wrap(str(err), T.font("medium", 15), b.w - px(56))
            box.h = px(22) + len(lines) * px(22)
            T.panel(s, box, (60, 26, 30), 12, (150, 60, 66))
            T.icon(s, "warn", (box.x + px(14), box.y + px(12), px(20), px(20)), T.C["err"])
            for i, ln in enumerate(lines):
                img = self.tx.get(ln, "medium", 15, (255, 214, 214))
                s.blit(img, (box.x + px(44), box.y + px(11) + i * px(22)))
        else:
            detail = p.get("detail") or ("Reading AI OS from the disc" if self.shown < 0.8 and self.progress else "")
            if detail:
                img = self.tx.get(detail, "regular", 14, T.C["text2"])
                s.blit(img, (b.x, b.bottom + px(12)))

    def _bar(self, s, rect, frac, shimmer=True, thin=False):
        """The gradient progress bar; `thin` draws the slim one used over games."""
        pygame.draw.rect(s, T.C["panel2"], rect, border_radius=rect.h // 2)
        fw = int(rect.w * max(0.0, min(1.0, frac)))
        if fw <= 0:
            return
        if thin or rect.size != self.bar.size:
            fill = pygame.Rect(rect.x, rect.y, max(rect.h, fw), rect.h)
            T.gradient_rect(s, fill, T.C["accent"], T.C["accent2"], radius=max(1, rect.h // 2) / max(0.01, T.px(100) / 100))
            return
        fw = max(rect.h, fw)
        s.blit(self.bar_fill, rect.topleft, (0, 0, fw, rect.h))
        # round off the moving end
        endc = tuple(int(T.C["accent"][k] + (T.C["accent2"][k] - T.C["accent"][k]) * fw / rect.w) for k in range(3))
        pygame.draw.circle(s, endc, (rect.x + fw - rect.h // 2, rect.centery), rect.h // 2)
        if shimmer and frac < 1.0:
            sw = self.shimmer.get_width()
            x = rect.x - sw + int(((self.t * 0.6) % 1.0) * (fw + sw))
            clip = s.get_clip()
            s.set_clip(pygame.Rect(rect.x, rect.y, fw, rect.h))
            s.blit(self.shimmer, (x, rect.y))
            s.set_clip(clip)

    def _draw_card(self, s, i, r):
        px = T.px
        gid, title, blurb, controls, cls = self.games[i]
        selected = i == self.sel
        rr = r.move(0, -px(6)) if selected else r
        T.panel(s, rr, T.C["panel"], 16, T.C["accent"] if selected else T.C["line"], shadow=selected)
        if selected:
            pygame.draw.rect(s, T.C["accent"], rr, width=max(2, px(2)), border_radius=px(16))
        prev = self.previews[i]
        if prev is not None:
            s.blit(prev, (rr.x + px(8), rr.y + px(8)))
        else:
            pygame.draw.rect(s, T.C["panel2"], (rr.x + px(8), rr.y + px(8), rr.w - px(16), self.preview_h), border_radius=px(12))
        y = rr.y + px(8) + self.preview_h + px(12)
        s.blit(self.tx.get(title, "bold", 18, T.C["text"]), (rr.x + px(16), y))
        y += px(26)
        for ln in T.wrap(blurb, T.font("regular", 13), rr.w - px(32))[:2]:
            s.blit(self.tx.get(ln, "regular", 13, T.C["text2"]), (rr.x + px(16), y))
            y += px(18)
        ctl = self.tx.get(controls, "medium", 12, T.C["muted"])
        s.blit(ctl, (rr.x + px(16), rr.bottom - px(14) - ctl.get_height()))
        if selected:
            play = pygame.Rect(0, 0, px(76), px(28))
            play.bottomright = (rr.right - px(12), rr.bottom - px(10))
            T.gradient_rect(s, play, T.C["accent"], T.C["accent2"], radius=14)
            T.icon(s, "play", (play.x + px(10), play.centery - px(7), px(14), px(14)), (255, 255, 255))
            lbl = self.tx.get("Play", "bold", 13, (255, 255, 255))
            s.blit(lbl, (play.x + px(30), play.centery - lbl.get_height() // 2))

    def _draw_strip(self, s):
        """The slim progress strip over a running game."""
        px = T.px
        h = px(STRIP)
        strip = pygame.Surface((self.w, h), pygame.SRCALPHA)
        strip.fill((8, 8, 16, 205))
        s.blit(strip, (0, 0))
        pygame.draw.line(s, (60, 54, 86), (0, h - 1), (self.w, h - 1))
        s.blit(self.badge_small(), (px(12), (h - px(22)) // 2))
        p = self.progress or {}
        label = "AI OS is ready" if self.state == "ready" else self.stage()
        if p.get("error"):
            label = "Loading stopped (see the menu)"
        img = self.tx.get(label, "semibold", 13, T.C["err"] if p.get("error") else T.C["text"])
        s.blit(img, (px(44), (h - img.get_height()) // 2))
        bar = pygame.Rect(px(44) + img.get_width() + px(16), (h - px(6)) // 2, px(260), px(6))
        self._bar(s, bar, self.shown, shimmer=False, thin=True)
        pct = self.tx.get("%d%%" % int(round(self.shown * 100)), "bold", 13, T.C["accent"])
        s.blit(pct, (bar.right + px(10), (h - pct.get_height()) // 2))
        esc = self.tx.get("Esc  menu", "medium", 12, T.C["muted"])
        s.blit(esc, (self.w - px(14) - esc.get_width(), (h - esc.get_height()) // 2))

    def badge_small(self):
        if not hasattr(self, "_badge_small"):
            sz = T.px(22)
            self._badge_small = pygame.transform.smoothscale(self.badge, (sz, sz))
        return self._badge_small

    def _draw_ready(self, s):
        px = T.px
        k = min(1.0, self.ready_t / 0.35)
        veil = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        veil.fill((8, 8, 16, int(170 * k)))
        s.blit(veil, (0, 0))
        card = pygame.Rect(0, 0, px(360), px(150))
        card.center = (self.w // 2, self.h // 2 + int((1 - k) * px(20)))
        T.panel(s, card, T.C["panel"], 18, T.C["accent"], shadow=True)
        c = (card.centerx, card.y + px(46))
        pygame.draw.circle(s, T.C["ok"], c, px(22))
        T.icon(s, "check", (c[0] - px(13), c[1] - px(13), px(26), px(26)), (10, 30, 20))
        img = self.tx.get("AI OS is ready", "bold", 22, T.C["text"])
        s.blit(img, img.get_rect(midtop=(card.centerx, card.y + px(80))))
        sub = self.tx.get("Opening the chat…", "regular", 14, T.C["text2"])
        s.blit(sub, sub.get_rect(midtop=(card.centerx, card.y + px(112))))

    # ------------------------------------------------------------------ main loop
    def run(self, should_stop=lambda: False):
        clock = pygame.time.Clock()
        errors = 0
        while not should_stop():
            fps = 60 if self.state == "game" else 30
            dt = min(0.05, clock.tick(fps) / 1000.0)
            try:
                self.poll_progress()
                for ev in self.inp.poll(0):
                    self.handle(ev)
                self.update(dt)
                self.draw()
                self.d.flip()
                errors = 0
            except Exception:
                traceback.print_exc()
                errors += 1
                if errors > 5:
                    return 1
                self.state, self.game = ("ready" if self.state == "ready" else "menu"), None
            if self.state == "ready" and self.ready_t > 1.1:
                return 0
        return 0


def main():
    stop = {"flag": False}

    def on_signal(sig, frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        os.makedirs(boot.RUN, exist_ok=True)
        with open(boot.LOADER_PID, "w") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass
    d = inp = None
    code = 1
    try:
        d = display.Display()
        T.set_scale(d.size)
        inp = display.Input(d.size)
        code = LoaderUI(d, inp).run(lambda: stop["flag"])
    except Exception:
        traceback.print_exc()
        code = 1
    finally:
        if inp is not None:
            inp.close()
        if d is not None:
            d.close()
        try:
            if open(boot.LOADER_PID).read().strip() == str(os.getpid()):
                os.remove(boot.LOADER_PID)
        except OSError:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
