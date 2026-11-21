"""AI OS's graphical chat: the screen you talk to the AI on.

A sidebar with your apps, Games, Wi-Fi, Settings and Power; the conversation in the middle with
chat bubbles, code and file cards (Run / View); a message box at the bottom. Apps run in a
terminal window on top. The engine (AI service, files, building, running) is aios.core, the
same one the text chat uses. Run with `python3 -m aios.gui` (PYTHONPATH=/usr/lib/aios).
"""
import fcntl, os, queue, signal, struct, subprocess, sys, threading, time, urllib.error, warnings

# Alpine's pygame notes at import that it wasn't built for AVX2: true, harmless, and noise in gui.log
warnings.filterwarnings("ignore", message="Your system is avx2 capable")
from aios import boot, core, display, editor as ED, theme as T, widgets as W  # noqa: E402
from aios.term import Terminal
import pygame

HEADLESS = bool(os.environ.get("AIOS_HEADLESS"))
SUGGESTIONS = [
    ("Make a snake game in C", "A classic, playable in the terminal window"),
    ("Write a Python calculator", "Type sums, get answers"),
    ("Make a guess-the-number game", "Higher or lower, in Python"),
    ("What can AI OS do?", "A quick tour of this computer"),
]
COMMANDS = [
    ("/run NAME [args]", "run an app: .sh .py .c .exe .iso"), ("/build NAME.c", "compile C into NAME.exe"),
    ("/iso OUT.iso [apps]", "make a bootable copy of AI OS with these apps"), ("/files", "list your apps"),
    ("/show NAME", "view a file"), ("/edit NAME", "edit a file yourself (a new name makes a new file)"),
    ("/rm NAME", "delete a file"), ("/send NAME [msg]", "show a file to the AI"),
    ("/wifi", "join a Wi-Fi network"), ("/net", "network status"), ("/model [name]", "pick the AI model"),
    ("/key", "change the API key"), ("/new", "start a new conversation"), ("/games", "play a game"),
    ("/reboot  /poweroff", "restart or shut down"),
]


def screen_size():
    """The screen's size in pixels, without taking over the screen yet."""
    if HEADLESS:
        return tuple(int(v) for v in os.environ["AIOS_HEADLESS"].lower().split("x"))
    fd = os.open(os.environ.get("AIOS_FB", "/dev/fb0"), os.O_RDONLY)
    try:
        var = bytearray(160)
        fcntl.ioctl(fd, display.FBIOGET_VSCREENINFO, var)
        return struct.unpack_from("2I", var, 0)
    finally:
        os.close(fd)


class Msg:
    """One entry in the conversation. role: user, ai, chip (status line), card (a titled box)."""

    def __init__(self, role, text="", kind="info", icon=None, title="", lines=None, actions=None, mono=False):
        self.role, self.text, self.kind, self.icon, self.title = role, text, kind, icon, title
        self.lines, self.actions, self.mono = lines or [], actions or [], mono
        self.streaming = False
        self.time = time.strftime("%H:%M")
        self.version = 0
        self.cache = None          # (width, version, surface, buttons)

    def touch(self):
        self.version += 1


class Dialog:
    """A centred window over a dimmed screen. Subclasses fill in body() and on_key()/on_click()."""
    width, title, icon = 560, "", None

    def __init__(self, app):
        self.app = app
        self.buttons = []           # [(rect, callback)] rebuilt every frame
        self.hover = None

    def rect(self):
        w, h = T.px(self.width), self.height()
        return pygame.Rect((self.app.W - w) // 2, (self.app.H - h) // 2, w, h)

    def height(self):
        return T.px(360)

    def close(self):
        if self.app.dialog is self:
            self.app.dialog = None
        self.app.dirty = True

    def draw(self, s):
        dim = pygame.Surface((self.app.W, self.app.H), pygame.SRCALPHA)
        dim.fill((5, 6, 10, 170))
        s.blit(dim, (0, 0))
        r = self.rect()
        T.panel(s, r, T.C["panel"], 16, T.C["line"], shadow=True)
        self.buttons = []
        x = r.x + T.px(24)
        if self.icon:
            T.icon(s, self.icon, (x, r.y + T.px(22), T.px(22), T.px(22)), T.C["accent"])
            x += T.px(32)
        T.text(s, self.title, (x, r.y + T.px(20)), "semibold", 18)
        cb = pygame.Rect(r.right - T.px(48), r.y + T.px(14), T.px(34), T.px(34))
        if self.hover == "close":
            pygame.draw.rect(s, T.C["panel2"], cb, border_radius=T.px(8))
        T.icon(s, "close", cb.inflate(-T.px(12), -T.px(12)), T.C["text2"])
        self.buttons.append((cb, self.close, "close"))
        self.body(s, pygame.Rect(r.x + T.px(24), r.y + T.px(64), r.w - T.px(48), r.h - T.px(88)))

    def body(self, s, r):
        pass

    def add_button(self, s, rect, label, cb, kind="normal", icon=None):
        key = ("btn", label, rect[0], rect[1])
        T.button(s, rect, label, kind, hover=self.hover == key, icon_name=icon)
        self.buttons.append((pygame.Rect(rect), cb, key))

    def handle(self, ev):
        if ev.type == "mouse_move":
            hv = None
            for rect, cb, key in self.buttons:
                if rect.collidepoint(ev.pos):
                    hv = key
            if hv != self.hover:
                self.hover = hv
                self.app.dirty = True
            return
        if ev.type == "mouse_button" and ev.down and ev.button == 1:
            for rect, cb, key in reversed(self.buttons):
                if rect.collidepoint(ev.pos):
                    cb()
                    self.app.dirty = True
                    return
            if not self.rect().collidepoint(ev.pos):
                self.close()
            else:
                self.on_click(ev)
            return
        if ev.type == "wheel":
            self.on_wheel(ev)
            return
        if ev.type == "key" and ev.down:
            if ev.key == "escape":
                self.close()
                return
            self.on_key(ev)
            self.app.dirty = True

    def on_key(self, ev):
        pass

    def on_click(self, ev):
        pass

    def on_wheel(self, ev):
        pass


class ConfirmDialog(Dialog):
    width, icon = 460, "warn"

    def __init__(self, app, title, message, label, action, danger=True):
        super().__init__(app)
        self.title, self.message, self.label, self.action, self.danger = title, message, label, action, danger

    def height(self):
        return T.px(220)

    def body(self, s, r):
        for i, line in enumerate(T.wrap(self.message, T.font("regular", 15), r.w)[:4]):
            T.text(s, line, (r.x, r.y + i * T.px(22)), "regular", 15, T.C["text2"])
        bw = T.px(140)
        self.add_button(s, (r.right - bw, r.bottom - T.px(40), bw, T.px(40)), self.label,
                        lambda: (self.close(), self.action()), "danger" if self.danger else "primary")
        self.add_button(s, (r.right - 2 * bw - T.px(12), r.bottom - T.px(40), bw, T.px(40)), "Cancel", self.close)

    def on_key(self, ev):
        if ev.key == "return":
            self.close()
            self.action()


class KeyDialog(Dialog):
    """Asks for the AI service key (first start, or /key)."""
    width, title, icon = 560, "Connect AI OS to the AI", "sparkle"

    def __init__(self, app, first=False):
        super().__init__(app)
        self.box = W.TextBox("gsk_...", mask=True)
        self.first = first
        self.note = ""

    def height(self):
        return T.px(300)

    def body(self, s, r):
        msg = ("AI OS talks to the AI through Groq. Paste or type your API key (it starts with gsk_). "
               "Get a free one at console.groq.com/keys.")
        if not self.first:
            cur = self.app.key
            msg = "Current key: %s. Type a new one to replace it." % (cur[:4] + "•" * 6 + cur[-4:] if len(cur) > 8 else "none")
        y = r.y
        for line in T.wrap(msg, T.font("regular", 14), r.w):
            T.text(s, line, (r.x, y), "regular", 14, T.C["text2"])
            y += T.px(21)
        box = pygame.Rect(r.x, y + T.px(14), r.w, T.px(46))
        T.panel(s, box, T.C["panel2"], 10, T.C["accent"])
        self.box.draw(s, box.inflate(-T.px(28), -T.px(24)))
        if self.note:
            T.text(s, self.note, (r.x, box.bottom + T.px(10)), "regular", 13, T.C["err"])
        self.add_button(s, (r.right - T.px(150), r.bottom - T.px(40), T.px(150), T.px(40)), "Save key", self.save, "primary")

    def on_key(self, ev):
        if self.box.handle(ev) == "submit":
            self.save()

    def save(self):
        k = self.box.text.strip()
        if not k:
            self.note = "Type or paste the key first."
            return
        self.app.key = k
        try:
            core.save_key(k)
            self.app.toast("API key saved", "ok", "check")
        except OSError as e:          # still used until the next restart
            self.app.toast("Key in use, but not saved: %s" % e, "warn", "warn")
        self.close()


class ViewDialog(Dialog):
    """Shows a file, with Run / Ask AI / Delete."""
    width = 860

    def __init__(self, app, path):
        super().__init__(app)
        self.path = path
        self.name = os.path.basename(path)
        self.title = self.name
        self.kind = core.kind_of(self.name)
        t = core.file_text(path, limit=200000)
        self.lines = (t.split("\n") if t is not None else
                      ["(%s, %s: not a text file)" % (W.KIND_LABEL.get(self.kind, "file"), W.human_size(os.path.getsize(path)))])
        self.top = 0
        self.icon = W.KIND_ICON.get(self.kind, "file")

    def height(self):
        return min(self.app.H - T.px(80), T.px(640))

    def visible(self, r):
        return max(1, (r.h - T.px(60)) // T.font("mono", 13).get_linesize())

    def body(self, s, r):
        f = T.font("mono", 13)
        lh = f.get_linesize()
        area = pygame.Rect(r.x, r.y, r.w, r.h - T.px(56))
        T.panel(s, area, T.C["term_bg"], 10, T.C["line"])
        n = self.visible(r)
        self.top = max(0, min(self.top, max(0, len(self.lines) - n)))
        gutter = f.size("9999")[0] + T.px(14)
        clip = s.get_clip()
        s.set_clip(area.inflate(-T.px(4), -T.px(4)))
        for i, line in enumerate(self.lines[self.top:self.top + n]):
            y = area.y + T.px(10) + i * lh
            s.blit(f.render(str(self.top + i + 1).rjust(4), True, T.C["muted"]), (area.x + T.px(8), y))
            s.blit(f.render(line.replace("\t", "    ")[:400], True, (214, 218, 230)), (area.x + T.px(8) + gutter, y))
        s.set_clip(clip)
        if len(self.lines) > n:
            frac = self.top / max(1, len(self.lines) - n)
            th = max(T.px(30), area.h * n // len(self.lines))
            pygame.draw.rect(s, T.C["line"], (area.right - T.px(8), area.y + int((area.h - th) * frac), T.px(4), th),
                             border_radius=T.px(2))
        y = r.bottom - T.px(40)
        x = r.x
        if self.kind in ("c", "py", "sh", "exe", "iso"):
            self.add_button(s, (x, y, T.px(110), T.px(40)), "Run", lambda: (self.close(), self.app.run_app(self.name)),
                            "primary", "play")
            x += T.px(122)
        if self.kind not in ("exe", "iso") and core.file_text(self.path, limit=2000000) is not None:
            self.add_button(s, (x, y, T.px(110), T.px(40)), "Edit", lambda: self.app.edit_app(self.name), icon="code")
            x += T.px(122)
        if self.kind not in ("exe", "iso"):
            self.add_button(s, (x, y, T.px(150), T.px(40)), "Ask the AI", lambda: (self.close(), self.app.ask_about(self.name)),
                            icon="chat")
        self.add_button(s, (r.right - T.px(120), y, T.px(120), T.px(40)), "Delete",
                        lambda: self.app.confirm_delete(self.name), "danger", "trash")

    def on_wheel(self, ev):
        self.top = max(0, self.top - ev.dy * 3)
        self.app.dirty = True

    def on_key(self, ev):
        r = self.rect()
        n = self.visible(r)
        step = {"up": -1, "down": 1, "pageup": -n, "pagedown": n, "home": -10 ** 9, "end": 10 ** 9}.get(ev.key)
        if step:
            self.top = max(0, self.top + step)


class EditorDialog(Dialog):
    """Edit an app file yourself: Save (Ctrl+S), Run (F5), Delete. Asks before throwing away changes."""

    def __init__(self, app, name, new=False):
        super().__init__(app)
        self.name, self.new = name, new
        text = core.file_text(os.path.join(core.APPS, name), limit=2000000) or ""
        self.ed = ED.TextEdit(text, ED.lang_of(name))
        self.kind = core.kind_of(name)
        self.icon = W.KIND_ICON.get(self.kind, "file")
        self.asking = None          # None, "close" (unsaved changes) or "delete"
        self.dragging = False
        self.area = None

    def rect(self):
        m = T.px(32)
        return pygame.Rect(m, T.px(20), self.app.W - 2 * m, self.app.H - T.px(40))

    def draw(self, s):
        self.title = ("Edit %s" % self.name) + ("  •" if self.ed.modified or self.new else "")
        super().draw(s)

    def body(self, s, r):
        self.area = pygame.Rect(r.x, r.y, r.w, r.h - T.px(56))
        self.ed.draw(s, self.area, focused=self.asking is None)
        y, bh = r.bottom - T.px(40), T.px(40)
        if self.asking:
            q = ("Save your changes to %s?" % self.name if self.asking == "close"
                 else "Delete %s for good?" % self.name)
            T.text(s, q, (r.x, y + bh // 2), "semibold", 15, T.C["warn"] if self.asking == "close" else T.C["err"],
                   anchor="midleft")
            x = r.right
            spec = ([("Save", self.save_and_close, "primary"), ("Don't save", self.close, "danger"),
                     ("Cancel", self.cancel_ask, "normal")] if self.asking == "close"
                    else [("Delete", self.delete, "danger"), ("Cancel", self.cancel_ask, "normal")])
            for label, cb, kind in reversed(spec):
                bw = T.px(130)
                x -= bw
                self.add_button(s, (x, y, bw, bh), label, cb, kind)
                x -= T.px(10)
            return
        status = "Line %d, column %d  ·  %d lines  ·  %s" % (self.ed.cy + 1, self.ed.cx + 1, len(self.ed.lines),
                                                              W.KIND_LABEL.get(self.kind, "Text"))
        T.text(s, status, (r.x, y + T.px(4)), "medium", 13, T.C["text2"])
        T.text(s, "Ctrl+S save  ·  F5 run  ·  Ctrl+Z undo  ·  Esc close", (r.x, y + T.px(24)), "regular", 12, T.C["muted"])
        x = r.right
        buttons = [("Save", self.save, "primary", "check")]
        if self.kind in ("c", "py", "sh"):
            buttons.append(("Run", self.run, "normal", "play"))
        buttons.append(("Delete", lambda: self.ask("delete"), "danger", "trash"))
        for label, cb, kind, icon in buttons:
            bw = T.px(118)
            x -= bw
            self.add_button(s, (x, y, bw, bh), label, cb, kind, icon)
            x -= T.px(10)

    # -- actions
    def ask(self, what):
        self.asking = what
        self.app.dirty = True

    def cancel_ask(self):
        self.asking = None

    def save(self):
        try:
            p = core.write_app(self.name, self.ed.text())
        except OSError as e:
            self.app.toast("Couldn't save %s: %s" % (self.name, e), "err", "warn")
            return False
        if not p:
            self.app.toast("That file name can't be used", "err", "warn")
            return False
        self.ed.mark_saved()
        self.new = False
        self.app.refresh_apps()
        self.app.toast("Saved " + self.name, "ok", "check")
        return True

    def save_and_close(self):
        if self.save():
            self.close()

    def run(self):
        if (self.ed.modified or self.new) and not self.save():
            return
        self.app.run_app(self.name)          # its window opens on top; closing it comes back here

    def delete(self):
        self.app.delete_file(self.name)
        self.close()

    def request_close(self):
        if self.ed.modified:
            self.ask("close")
        else:
            self.close()

    # -- input
    def handle(self, ev):
        a = self.area
        if ev.type == "mouse_move":
            if self.dragging and a is not None:
                self.ed.drag(a, ev.pos)
                self.app.dirty = True
                return
            super().handle(ev)                   # button hover
            return
        if ev.type == "mouse_button":
            if ev.button != 1:
                return
            if not ev.down:
                self.dragging = False
                return
            for rect, cb, key in reversed(self.buttons):
                if rect.collidepoint(ev.pos):
                    if key == "close":
                        self.request_close()     # the window's X asks first too
                    else:
                        cb()
                    self.app.dirty = True
                    return
            if a is not None and a.collidepoint(ev.pos) and not self.asking:
                shift = self.app.input is not None and "shift" in self.app.input.mods()
                self.ed.click(a, ev.pos, extend=shift)
                self.dragging = True
                self.app.dirty = True
            return                               # a click outside the editor never closes it (work could be lost)
        if ev.type == "wheel":
            if a is not None:
                self.ed.scroll(a, -ev.dy * 3)
            self.app.dirty = True
            return
        if ev.type != "key" or not ev.down:
            return
        self.app.dirty = True
        if self.asking:
            if ev.key == "escape":
                self.asking = None
            elif ev.key == "return":
                self.save_and_close() if self.asking == "close" else self.delete()
            return
        if ev.key == "escape":
            self.request_close()
            return
        act = self.ed.handle_key(ev, page=self.ed.page(a) if a is not None else 20)
        if act == "save":
            self.save()
        elif act == "run":
            self.run()


class NewFileDialog(Dialog):
    """Name a new file, then edit it."""
    width, title, icon = 540, "New file", "plus"

    def __init__(self, app):
        super().__init__(app)
        self.box = W.TextBox("notes.txt, game.py, tool.c, start.sh ...")
        self.note = ""

    def height(self):
        return T.px(270)

    def body(self, s, r):
        msg = ("Give it a name. The ending decides what it is: .c is a C program, .py Python, "
               ".sh a shell script, and .txt or .md are notes.")
        y = r.y
        for line in T.wrap(msg, T.font("regular", 14), r.w):
            T.text(s, line, (r.x, y), "regular", 14, T.C["text2"])
            y += T.px(21)
        box = pygame.Rect(r.x, y + T.px(12), r.w, T.px(46))
        T.panel(s, box, T.C["panel2"], 10, T.C["accent"])
        self.box.draw(s, box.inflate(-T.px(28), -T.px(24)))
        if self.note:
            T.text(s, self.note, (r.x, box.bottom + T.px(8)), "regular", 13, T.C["err"])
        self.add_button(s, (r.right - T.px(150), r.bottom - T.px(40), T.px(150), T.px(40)), "Create", self.create,
                        "primary", "plus")

    def on_key(self, ev):
        if self.box.handle(ev) == "submit":
            self.create()

    def create(self):
        name = self.box.text.strip()
        n = core.safe_name(name) if name else ""
        if not n:
            self.note = "Type a name first, like notes.txt or game.py."
            return
        self.app.edit_app(n, create=True)


class HelpDialog(Dialog):
    width, title, icon = 640, "Commands and shortcuts", "terminal"

    def height(self):
        return T.px(600)

    def body(self, s, r):
        y = r.y
        for cmd, what in COMMANDS:
            T.text(s, cmd, (r.x, y), "mono", 13, T.C["cyan"])
            T.text(s, what, (r.x + T.px(200), y), "regular", 14, T.C["text2"])
            y += T.px(24)
        y += T.px(10)
        for keys, what in (("Enter", "send"), ("Shift+Enter", "new line"), ("Esc / Ctrl+C", "stop the AI's reply"),
                           ("Up / Down", "earlier messages"), ("PageUp / PageDown", "scroll the conversation"),
                           ("F12", "close a running app's window")):
            T.text(s, keys, (r.x, y), "semibold", 13, T.C["text"])
            T.text(s, what, (r.x + T.px(200), y), "regular", 14, T.C["text2"])
            y += T.px(22)


class SettingsDialog(Dialog):
    width, title, icon = 640, "Settings", "gear"

    def __init__(self, app):
        super().__init__(app)
        self.models = None
        self.problem = ""
        self.top = 0
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            models = [m for m in core.list_models(self.app.key) if "whisper" not in m and "orpheus" not in m
                      and "guard" not in m]
            self.app.post(self._loaded, models, "")
        except Exception as e:
            self.app.post(self._loaded, [], core.net_error(e) if isinstance(e, (urllib.error.URLError, OSError)) else str(e))

    def _loaded(self, models, problem):
        self.models, self.problem = models, problem

    def height(self):
        rows = 1 if not self.models else min(7, len(self.models))
        return T.px(64 + 24 + rows * 38 + (40 if not self.models else 0) + 16 + 22 + 50 + 30)

    def body(self, s, r):
        T.text(s, "AI MODEL", (r.x, r.y), "semibold", 11, T.C["muted"])
        y = r.y + T.px(24)
        if self.models is None:
            T.text(s, "Loading the list of models…", (r.x, y), "regular", 14, T.C["text2"])
            y += T.px(40)
        elif not self.models:
            for line in T.wrap(self.problem or "No models found.", T.font("regular", 14), r.w)[:3]:
                T.text(s, line, (r.x, y), "regular", 14, T.C["err"])
                y += T.px(20)
            y += T.px(10)
        else:
            rows = 7
            self.top = max(0, min(self.top, max(0, len(self.models) - rows)))
            for i, m in enumerate(self.models[self.top:self.top + rows]):
                row = pygame.Rect(r.x, y, r.w, T.px(36))
                cur = m == self.app.model
                key = ("model", m)
                if cur or self.hover == key:
                    T.panel(s, row, T.C["panel2"], 8, T.C["accent"] if cur else None)
                pygame.draw.circle(s, T.C["accent"] if cur else T.C["line"], (row.x + T.px(18), row.centery), T.px(6),
                                   0 if cur else max(1, T.px(2)))
                T.text(s, m, (row.x + T.px(36), row.centery), "medium" if cur else "regular", 14,
                       T.C["text"] if cur else T.C["text2"], anchor="midleft")
                self.buttons.append((row, lambda m=m: self.pick(m), key))
                y += T.px(38)
        y += T.px(16)
        T.text(s, "API KEY", (r.x, y), "semibold", 11, T.C["muted"])
        k = self.app.key
        T.text(s, (k[:4] + "•" * 10 + k[-4:]) if len(k) > 8 else "No key yet", (r.x, y + T.px(22)), "mono", 14)
        self.add_button(s, (r.right - T.px(170), y + T.px(12), T.px(170), T.px(38)), "Change key",
                        lambda: self.app.open(KeyDialog(self.app)), icon="gear")

    def pick(self, m):
        self.app.model = m
        self.app.toast("Model: " + m, "ok", "check")

    def on_wheel(self, ev):
        self.top = max(0, self.top - ev.dy)
        self.app.dirty = True


class PowerDialog(Dialog):
    width, title, icon = 460, "Power", "power"

    def height(self):
        return T.px(230)

    def body(self, s, r):
        T.text(s, "Apps live in memory: they are gone after a restart unless you /iso them.", (r.x, r.y),
               "regular", 13, T.C["text2"])
        bw = (r.w - T.px(24)) // 3
        y = r.bottom - T.px(44)
        self.add_button(s, (r.x, y, bw, T.px(44)), "Restart", lambda: self.app.power("reboot"), icon="refresh")
        self.add_button(s, (r.x + bw + T.px(12), y, bw, T.px(44)), "Shut down", lambda: self.app.power("poweroff"),
                        "danger", "power")
        self.add_button(s, (r.x + 2 * (bw + T.px(12)), y, bw, T.px(44)), "Cancel", self.close)


class WifiDialog(Dialog):
    width, title, icon = 600, "Wi-Fi", "wifi"

    def __init__(self, app):
        super().__init__(app)
        self.status = "Checking…"
        self.connected = False
        self.nets = None
        self.busy = ""
        self.sel = None
        self.box = W.TextBox("Password", mask=True)
        self.result = ("", "text2")
        self.top = 0
        self._bg(self._status)
        self._bg(self._scan)

    def _bg(self, fn, *a):
        threading.Thread(target=fn, args=a, daemon=True).start()

    def _status(self):
        if not core.wifi_tools():
            self.app.post(self._set, status="Wi-Fi tools are not installed.")
            return
        connected, kv = core.wifi_status()
        if kv.get("state") == "no-adapter":
            st = "No Wi-Fi adapter found." + ("  Wired network: connected." if core.default_route() else "")
        elif connected:
            st = "Connected to %s  ·  %s" % (core.printable(kv.get("ssid", "?")), kv.get("ip", ""))
        else:
            st = "Not connected (%s)" % kv.get("state", "off").lower()
        self.app.post(self._set, status=st, connected=connected)

    def _scan(self):
        if not core.wifi_tools():
            self.app.post(self._set, nets=[])
            return
        self.app.post(self._set, busy="Scanning for networks…")
        nets, problem = core.wifi_scan()
        self.app.post(self._set, nets=nets, busy="", result=(problem, "err") if problem else ("", "text2"))

    def _connect(self, ssid, pw):
        rc, out = core.wifi_connect(ssid, pw)
        if rc == 0:
            res = ("Connected to %s." % core.printable(ssid), "ok")
        elif rc == 3:
            res = ("Wrong password for %s. Try again." % core.printable(ssid), "err")
        else:
            res = ((out.splitlines() or ["Couldn't connect."])[-1], "err")
        self.app.post(self._set, busy="", result=res)
        self._status()

    def _set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.app.dirty = True

    def height(self):
        rows = min(6, len(self.nets)) if self.nets else 1
        return T.px(64 + 36 + 30 + rows * 40 + (110 if self.sel is not None else 50) + 24)

    def body(self, s, r):
        T.text(s, self.status, (r.x, r.y), "medium", 14, T.C["ok"] if self.connected else T.C["text2"])
        if self.connected:
            self.add_button(s, (r.right - T.px(130), r.y - T.px(8), T.px(130), T.px(34)), "Disconnect",
                            lambda: (core.wifi_disconnect(), self._bg(self._status)))
        y = r.y + T.px(36)
        T.text(s, "NETWORKS", (r.x, y), "semibold", 11, T.C["muted"])
        self.add_button(s, (r.right - T.px(110), y - T.px(8), T.px(110), T.px(32)), "Scan",
                        lambda: self._bg(self._scan), icon="refresh")
        y += T.px(30)
        rows = 6
        if self.nets is None or self.busy.startswith("Scanning"):
            T.text(s, self.busy or "Scanning…", (r.x, y + T.px(8)), "regular", 14, T.C["text2"])
        elif not self.nets:
            T.text(s, "No Wi-Fi networks found.", (r.x, y + T.px(8)), "regular", 14, T.C["text2"])
        else:
            self.top = max(0, min(self.top, max(0, len(self.nets) - rows)))
            for i, (sig, sec, ssid) in enumerate(self.nets[self.top:self.top + rows]):
                row = pygame.Rect(r.x, y + i * T.px(40), r.w, T.px(36))
                key = ("net", ssid)
                if self.sel == ssid or self.hover == key:
                    T.panel(s, row, T.C["panel2"], 8, T.C["accent"] if self.sel == ssid else None)
                lvl = core.signal_level(sig)
                for b in range(4):
                    bh = T.px(4 + b * 3)
                    pygame.draw.rect(s, T.C["text"] if b < lvl else T.C["line"],
                                     (row.x + T.px(12) + b * T.px(5), row.centery + T.px(7) - bh, T.px(3), bh))
                T.text(s, W.ellipsize(core.printable(ssid), T.font("medium", 14), row.w - T.px(170)),
                       (row.x + T.px(42), row.centery), "medium", 14, anchor="midleft")
                T.text(s, sec, (row.right - T.px(12), row.centery), "regular", 12, T.C["muted"], anchor="midright")
                self.buttons.append((row, lambda ssid=ssid, sec=sec: self._pick(ssid, sec), key))
        y = r.bottom - T.px(96)
        if self.sel is not None:
            sec = next((n[1] for n in (self.nets or []) if n[2] == self.sel), "")
            if sec not in ("open", "OWE"):
                box = pygame.Rect(r.x, y, r.w - T.px(150), T.px(44))
                T.panel(s, box, T.C["panel2"], 10, T.C["accent"])
                self.box.draw(s, box.inflate(-T.px(24), -T.px(22)))
            self.add_button(s, (r.right - T.px(136), y + T.px(2), T.px(136), T.px(40)),
                            "Connect" if not self.busy else "Connecting…", self._go, "primary", "wifi")
        msg, col = self.result
        if self.busy and not self.busy.startswith("Scanning"):
            msg, col = self.busy, "text2"
        if msg:
            T.text(s, W.ellipsize(msg, T.font("regular", 13), r.w), (r.x, r.bottom - T.px(28)), "regular", 13, T.C[col])

    def _pick(self, ssid, sec):
        self.sel = ssid
        self.box.set("")
        self.result = ("", "text2")
        if sec == "Enterprise":
            self.result = ("%s uses Enterprise (802.1X) login, which AI OS does not support." % ssid, "err")

    def _go(self):
        if self.sel is None or self.busy:
            return
        self.busy = "Connecting to %s…" % core.printable(self.sel)
        self._bg(self._connect, self.sel, self.box.text)

    def on_key(self, ev):
        if self.sel is not None and self.box.handle(ev) == "submit":
            self._go()

    def on_wheel(self, ev):
        self.top = max(0, self.top - ev.dy)
        self.app.dirty = True


class GamesDialog(Dialog):
    width, title, icon = 720, "Games", "gamepad"

    def height(self):
        return T.px(380)

    def body(self, s, r):
        try:
            from aios import games
            entries = list(games.GAMES)
        except Exception:
            entries = []
        if not entries:
            T.text(s, "Games aren't available on this system.", (r.x, r.y + T.px(10)), "regular", 15, T.C["text2"])
            return
        n = len(entries)
        gap = T.px(16)
        cw = (r.w - gap * (n - 1)) // max(1, n)
        for i, entry in enumerate(entries):
            # entries are (id, title, blurb, controls, class); the class is always last
            gid, title, blurb = entry[0], entry[1], entry[2]
            controls = entry[3] if len(entry) > 4 and isinstance(entry[3], str) else ""
            card = pygame.Rect(r.x + i * (cw + gap), r.y + T.px(6), cw, r.h - T.px(12))
            key = ("game", gid)
            T.panel(s, card, T.C["panel2"] if self.hover == key else T.C["bg2"], 14, T.C["accent"] if self.hover == key else T.C["line"])
            art = pygame.Rect(card.x + T.px(14), card.y + T.px(14), card.w - T.px(28), T.px(110))
            self.preview(s, entry, art)
            T.text(s, title, (card.x + T.px(16), art.bottom + T.px(14)), "semibold", 16)
            y = art.bottom + T.px(42)
            for line in T.wrap(blurb, T.font("regular", 13), card.w - T.px(32))[:3]:
                T.text(s, line, (card.x + T.px(16), y), "regular", 13, T.C["text2"])
                y += T.px(19)
            if controls:
                for line in T.wrap(controls, T.font("regular", 11), card.w - T.px(32))[:2]:
                    T.text(s, line, (card.x + T.px(16), y + T.px(6)), "regular", 11, T.C["muted"])
                    y += T.px(16)
            self.buttons.append((card, lambda e=entry: (self.close(), self.app.play(e)), key))

    def preview(self, s, entry, art):
        """A still frame of the game itself as the card's picture (an icon if it can't draw one)."""
        cache = getattr(self, "_previews", None)
        if cache is None:
            cache = self._previews = {}
        img = cache.get((entry[0], art.size))
        if img is None:
            try:
                g = entry[-1]((art.w * 2, art.h * 2), preview=True)
                g.update(0.5, self.app.input) if self.app.input is not None else None
                frame = pygame.Surface((art.w * 2, art.h * 2))
                g.draw(frame)
                img = pygame.transform.smoothscale(frame, art.size)
            except Exception:
                img = False
            cache[(entry[0], art.size)] = img
        if img:
            mask = pygame.Surface(art.size, pygame.SRCALPHA)
            pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=T.px(10))
            layer = pygame.Surface(art.size, pygame.SRCALPHA)
            layer.blit(img, (0, 0))
            layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            s.blit(layer, art)
        else:
            T.gradient_rect(s, art, (40, 22, 70), (18, 40, 70), radius=10)
            T.icon(s, "gamepad", (art.centerx - T.px(24), art.centery - T.px(24), T.px(48), T.px(48)), T.C["accent"])


class TermWindow:
    """An app running in a terminal window over the chat."""

    def __init__(self, app, title, cmd, env, src, on_exit=None):
        self.app, self.title, self.src = app, title, src
        cw, ch = Terminal().cell_size()
        cols = max(80, min(100, (app.W - T.px(80)) // cw))
        rows = max(24, min(30, (app.H - T.px(150)) // ch))
        self.term = Terminal(cols, rows)
        self.hover = None
        self.buttons = []
        self.reported = False
        self.term.start(cmd, cwd=core.APPS, env=env)
        self.started = time.monotonic()

    def rect(self):
        cw, ch = self.term.cell_size()
        w = self.term.cols * cw + T.px(32)
        h = self.term.rows * ch + T.px(52) + (T.px(60) if not self.term.running else T.px(16))
        return pygame.Rect((self.app.W - w) // 2, max(T.px(10), (self.app.H - h) // 2), w, h)

    def draw(self, s):
        dim = pygame.Surface((self.app.W, self.app.H), pygame.SRCALPHA)
        dim.fill((5, 6, 10, 150))
        s.blit(dim, (0, 0))
        r = self.rect()
        T.panel(s, r, T.C["term_bg"], 14, T.C["line"], shadow=True)
        bar = pygame.Rect(r.x, r.y, r.w, T.px(40))
        pygame.draw.rect(s, T.C["bg2"], bar, border_top_left_radius=T.px(14), border_top_right_radius=T.px(14))
        pygame.draw.line(s, T.C["line"], (r.x, bar.bottom), (r.right - 1, bar.bottom))
        T.icon(s, "terminal", (r.x + T.px(14), bar.centery - T.px(9), T.px(18), T.px(18)), T.C["accent"])
        T.text(s, self.title, (r.x + T.px(42), bar.centery), "semibold", 14, anchor="midleft")
        rc = self.term.rc
        if self.term.running:
            st, col = "running", T.C["ok"]
        elif rc in (130, -signal.SIGINT):
            st, col = "stopped", T.C["warn"]
        else:
            st, col = "exited with code %d" % rc, T.C["ok"] if rc == 0 else T.C["err"]
        W.pill(s, (r.x + T.px(52) + T.font("semibold", 14).size(self.title)[0], bar.centery), st, col, anchor="midleft")
        self.buttons = []
        cb = pygame.Rect(bar.right - T.px(36), bar.y + T.px(6), T.px(28), T.px(28))
        if self.hover == "close":
            pygame.draw.rect(s, T.C["panel2"], cb, border_radius=T.px(6))
        T.icon(s, "close", cb.inflate(-T.px(10), -T.px(10)), T.C["text2"])
        self.buttons.append((cb, self.close, "close"))
        self.term.draw(s, (r.x + T.px(16), bar.bottom + T.px(8)), focused=True)
        if not self.term.running:
            y = r.bottom - T.px(50)
            x = r.right - T.px(16)
            for label, cb2, kind, icon in reversed(self.actions()):
                w = T.px(150) if label != "Close" else T.px(100)
                x -= w
                key = ("btn", label)
                W.small_button(s, (x, y, w, T.px(36)), label, kind, self.hover == key, icon)
                self.buttons.append((pygame.Rect(x, y, w, T.px(36)), cb2, key))
                x -= T.px(10)
            T.text(s, "Enter or Esc closes this window", (r.x + T.px(18), y + T.px(18)), "regular", 12, T.C["muted"],
                   anchor="midleft")
        else:
            T.text(s, "F12 closes the window", (r.right - T.px(16), bar.centery), "regular", 11, T.C["muted"],
                   anchor="midright")

    def actions(self):
        acts = []
        if self.failed() and self.src:
            acts.append(("Ask AI to fix", self.ask_fix, "primary", "sparkle"))
        acts.append(("Run again", self.again, "normal", "refresh"))
        acts.append(("Close", self.close, "normal", None))
        return acts

    def failed(self):
        rc = self.term.rc
        return rc is not None and rc not in (0, 130, -signal.SIGINT)

    def error_text(self):
        return "Running %s exited with code %d. Error output:\n%s" % (
            self.title, self.term.rc, self.term.text(40)[-3000:] or "(none)")

    def ask_fix(self):
        msg = core.fix_request(self.error_text(), self.src)
        self.close()
        self.app.send(msg, shown="Fix %s (it exited with code %d)" % (self.src, self.term.rc))

    def again(self):
        self.close()
        self.app.run_app(self.src if self.src and not self.src.endswith(".exe") else self.title)

    def report(self):
        """Note the outcome in the conversation once."""
        if self.reported or self.term.running:
            return
        self.reported = True
        rc = self.term.rc
        if rc in (130, -signal.SIGINT):
            self.app.chip("%s stopped (Ctrl+C)" % self.title, "warn", "stop")
        elif rc == 0:
            self.app.chip("%s exited with code 0" % self.title, "ok", "check")
        else:
            out = self.term.text(12)
            acts = [("Ask AI to fix", lambda e=self.error_text(), s=self.src: self.app.send(
                core.fix_request(e, s), shown="Fix %s (it exited with code %d)" % (s, rc)), "primary", "sparkle")] if self.src else []
            self.app.add(Msg("card", title="%s exited with code %d" % (self.title, rc), kind="err", icon="warn",
                             lines=out.split("\n")[-12:] if out else ["(no output)"], mono=True, actions=acts))

    def close(self):
        self.term.kill()
        self.term.pump()
        self.term._finish()
        self.report()
        if self.app.term is self:
            self.app.term = None
        self.app.dirty = True

    def handle(self, ev):
        if ev.type == "mouse_move":
            hv = None
            for rect, cb, key in self.buttons:
                if rect.collidepoint(ev.pos):
                    hv = key
            if hv != self.hover:
                self.hover = hv
                self.app.dirty = True
            return
        if ev.type == "mouse_button" and ev.down and ev.button == 1:
            for rect, cb, key in self.buttons:
                if rect.collidepoint(ev.pos):
                    cb()
                    return
            return
        if ev.type != "key" or not ev.down:
            return
        if ev.key == "f12":
            self.close()
            return
        if self.term.running:
            self.term.key(ev)
        elif ev.key in ("return", "escape"):
            self.close()


class GameView:
    """A game from aios.games, full screen. Esc goes back to the chat."""

    def __init__(self, app, entry):
        self.app, self.entry = app, entry
        self.title = entry[1]
        self.game = entry[-1](app.surface.get_size())   # entries end with the game's class
        self.t0 = time.monotonic()
        self.last = time.monotonic()

    def handle(self, ev):
        if ev.type == "key" and ev.down and ev.key in ("escape", "f12") and not ev.repeat:
            self.app.game = None
            self.app.dirty = True
            return
        self.game.handle(ev)

    def frame(self, s):
        now = time.monotonic()
        dt = min(0.05, now - self.last)
        self.last = now
        self.game.update(dt, self.app.input)
        self.game.draw(s)
        if now - self.t0 < 4:          # bottom centre: games keep their score and titles at the top
            W.pill(s, (self.app.W // 2, self.app.H - T.px(44)), "%s  ·  Esc returns to the chat" % self.title,
                   T.C["text2"], bg_alpha=160)


class App:
    def __init__(self, size):
        self.W, self.H = size
        T.set_scale(size)
        self.key = core.load_key()
        self.model = core.MODEL
        self.msgs = [Msg("welcome")]
        self.history = []
        self.box = W.TextBox("Message AI OS…  (/help for commands)", multiline=True)
        self.q = queue.Queue()
        self.dirty = True
        self.dialog = None
        self.menu = None
        self.term = None
        self.game = None
        self.toasts = []
        self.hover = None
        self.hits = []               # [(rect, callback, key)] for the main screen, rebuilt every frame
        self.scroll = 0.0            # transcript scroll offset (pixels from the top)
        self.scroll_target = 0.0
        self.stick_bottom = True
        self.content_h = 0
        self.apps = core.list_apps()
        self.apps_top = 0
        self.stream = None           # (Msg, threading.Event) while the AI is answering
        self.online = core.default_route()
        self.wifi_label = ""
        self._next_poll = 0.0
        self.display = None
        self.input = None
        self.surface = None
        self.quit = False
        self.busy = {}               # Msg -> label for work in progress (compiles, ISO builds)
        if not self.key:
            self.dialog = KeyDialog(self, first=True)

    # ---------------------------------------------------------------- plumbing
    def post(self, fn, *args, **kw):
        """Run fn on the main thread (from a background thread)."""
        self.q.put((fn, args, kw))

    def open(self, dlg):
        self.dialog = dlg
        self.menu = None
        self.dirty = True

    def toast(self, text, kind="info", icon=None):
        self.toasts.append([text, kind, icon, time.monotonic()])
        self.toasts = self.toasts[-4:]
        self.dirty = True

    def add(self, msg):
        if len(self.msgs) == 1 and self.msgs[0].role == "welcome":
            self.msgs = []
        self.msgs.append(msg)
        self.stick_bottom = True
        self.dirty = True
        return msg

    def chip(self, text, kind="info", icon=None):
        return self.add(Msg("chip", text, kind=kind, icon=icon))

    def refresh_apps(self):
        self.apps = core.list_apps()
        self.dirty = True

    # ---------------------------------------------------------------- talking to the AI
    def send(self, text, shown=None):
        """Send a message to the AI (shown in the conversation as `shown`, if given)."""
        if not text.strip():
            return
        if self.stream:
            self.toast("Wait for the reply to finish (Esc stops it)", "warn", "warn")
            return
        if not self.key:
            self.open(KeyDialog(self, first=True))
            return
        self.add(Msg("user", shown or text))
        self.history.append({"role": "user", "content": text})
        self.history = self.history[-core.MAX_MSGS:]
        ai = self.add(Msg("ai"))
        ai.streaming = True
        stop = threading.Event()
        self.stream = (ai, stop)
        snapshot = list(self.history)
        threading.Thread(target=self._stream, args=(ai, snapshot, self.model, self.key, stop), daemon=True).start()

    def _stream(self, msg, history, model, key, stop):
        try:
            resp = core.open_chat(key, model, core.chat_messages(history, gui=True))
        except Exception as e:
            self.post(self._stream_end, msg, e)
            return
        try:
            for t in core.iter_chat(resp, stop):
                self.post(self._delta, msg, t)
        except Exception as e:
            self.post(self._stream_end, msg, e)
            return
        finally:
            try:
                resp.close()
            except Exception:
                pass
        self.post(self._stream_end, msg, None)

    def _delta(self, msg, t):
        msg.text += t
        msg.touch()
        self.dirty = True

    def _stream_end(self, msg, e):
        msg.streaming = False
        msg.touch()
        stopped = self.stream is not None and self.stream[1].is_set()
        self.stream = None
        if msg.text:
            self.history.append({"role": "assistant", "content": msg.text})
            saved = core.save_files(msg.text)
            if saved:
                self.refresh_apps()
                self.toast("Saved " + ", ".join(saved), "ok", "check")
            if stopped:
                self.chip("stopped", "warn", "stop")
        else:
            if msg in self.msgs:
                self.msgs.remove(msg)
            if self.history and self.history[-1]["role"] == "user":
                self.history.pop()
            if stopped:
                self.chip("stopped", "warn", "stop")
        if e is not None:
            if isinstance(e, (urllib.error.URLError, OSError)):
                text = core.net_error(e)
            else:
                text = "AI error: %s" % e
            self.add(Msg("card", title="The AI couldn't answer", kind="err", icon="warn", lines=text.split("\n")))
        self.dirty = True

    def stop_reply(self):
        if self.stream:
            self.stream[1].set()

    def ask_about(self, name):
        req = core.send_request(name, "Explain what %s does and how I could improve it." % name)
        if req:
            self.send(req, shown="Tell me about %s" % name)

    # ---------------------------------------------------------------- commands
    def submit(self):
        line = self.box.text.strip()
        if not line:
            return
        self.box.remember(line)
        self.box.set("")
        if line.startswith("/"):
            self.command(line)
        else:
            self.send(line)

    def command(self, line):
        cmd, _, rest = line[1:].partition(" ")
        cmd, rest = cmd.lower(), rest.strip()
        if cmd in ("help", "h", "?"):
            self.open(HelpDialog(self))
        elif cmd == "run":
            self.run_app(rest)
        elif cmd == "build":
            p = core.find_app(rest)
            if not p or not p.endswith(".c"):
                self.chip("usage: /build NAME.c", "err", "warn")
            else:
                self.compile(p, None)
        elif cmd == "send":
            name, _, note = rest.partition(" ")
            req = core.send_request(name, note)
            if req is None:
                self.chip("usage: /send NAME [message]  (a text file in your apps)", "err", "warn")
            else:
                self.send(req, shown="/send " + rest)
        elif cmd in ("files", "ls", "dir"):
            apps = core.list_apps()
            self.add(Msg("card", title="Your apps", icon="folder", mono=True,
                         lines=["%-36s %12s" % (n, W.human_size(s)) for n, s in apps] or ["No apps yet. Ask the AI to make one!"]))
        elif cmd in ("show", "cat", "view"):
            p = core.find_app(rest)
            self.open(ViewDialog(self, p)) if p else self.chip("No such file.", "err", "warn")
        elif cmd in ("rm", "del"):
            n = core.delete_app(rest) if rest else None
            if n:
                self.refresh_apps()
                self.chip("deleted " + n, "info", "trash")
            else:
                self.chip("No such file.", "err", "warn")
        elif cmd == "edit":
            self.edit_app(rest, create=True)
        elif cmd == "iso":
            self.build_iso(rest)
        elif cmd in ("new", "reset"):
            self.new_chat()
        elif cmd in ("clear", "cls"):
            self.msgs = [Msg("welcome")]
            self.dirty = True
        elif cmd == "model":
            if rest:
                self.model = rest
                self.chip("model: " + rest, "ok", "sparkle")
            else:
                self.open(SettingsDialog(self))
        elif cmd == "net":
            self.net_card()
        elif cmd in ("wifi", "wlan"):
            if rest == "off":
                threading.Thread(target=core.wifi_disconnect, daemon=True).start()
                self.chip("Wi-Fi disconnected", "info", "wifi")
            else:
                self.open(WifiDialog(self))
        elif cmd == "key":
            self.open(KeyDialog(self))
        elif cmd in ("games", "game", "play"):
            self.open(GamesDialog(self))
        elif cmd in ("reboot", "restart"):
            self.power("reboot")
        elif cmd in ("poweroff", "shutdown", "off"):
            self.power("poweroff")
        else:
            self.chip("Unknown command. /help lists commands.", "err", "warn")

    def new_chat(self):
        self.stop_reply()
        self.msgs = [Msg("welcome")]
        self.history = []
        self.scroll = self.scroll_target = 0
        self.dirty = True

    def power(self, what):
        if HEADLESS:
            self.toast("(test mode) would %s" % what, "info", "power")
            self.dialog = None
            return
        subprocess.call([what])

    def delete_file(self, name):
        """Delete an app file now (callers have already asked)."""
        try:
            gone = core.delete_app(name)
        except OSError as e:
            self.toast("Couldn't delete %s: %s" % (name, e), "err", "warn")
            return
        if isinstance(self.dialog, (ViewDialog, EditorDialog)):
            self.dialog = None
        self.refresh_apps()
        if gone:
            self.toast("Deleted " + gone, "info", "trash")

    def confirm_delete(self, name):
        self.open(ConfirmDialog(self, "Delete %s?" % name, "This removes %s from your apps for good." % name, "Delete",
                                lambda: self.delete_file(name)))

    def edit_app(self, name, create=False):
        """Open the editor on an app file; a new name makes a new, empty file (with create=True)."""
        name = (name or "").strip()
        if not name:
            self.open(NewFileDialog(self))
            return
        p = core.find_app(name)
        if p:
            n = os.path.basename(p)
            if core.kind_of(n) in ("exe", "iso") or core.file_text(p, limit=2000000) is None:
                self.toast("%s isn't a text file, so it can't be edited" % n, "warn", "warn")
                return
            self.open(EditorDialog(self, n))
        elif create:
            n = core.safe_name(name)
            if not n:
                self.toast("That name can't be used for a file", "err", "warn")
                return
            try:
                core.write_app(n, "")
            except OSError as e:
                self.toast("Couldn't create %s: %s" % (n, e), "err", "warn")
                return
            self.refresh_apps()
            self.open(EditorDialog(self, n, new=True))
        else:
            self.chip("No such file.", "err", "warn")

    def net_card(self):
        card = self.add(Msg("card", title="Network", icon="wifi", mono=True, lines=["Checking…"]))

        def work():
            lines = []
            for dev, up, addrs in core.net_lines():
                lines.append("%-10s %s" % (dev, "up" if up else "no link"))
                lines += ["%-10s ip %s" % ("", a) for a in addrs]
            lines.append("internet: " + ("yes (default route)" if core.default_route() else "no default route yet"))
            ok, reason = core.ai_reachable()
            lines.append("AI service reachable." if ok else "AI service NOT reachable: %s" % reason)

            def show():
                card.lines = lines
                card.kind = "ok" if ok else "err"
                card.touch()
                self.dirty = True
            self.post(show)
        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- running apps
    def run_app(self, arg):
        parts = arg.split()
        if not parts:
            self.chip("usage: /run NAME [args]", "err", "warn")
            return
        p = core.find_app(parts[0])
        if not p:
            self.chip("No app called %s. /files lists apps." % parts[0], "err", "warn")
            return
        args = parts[1:]
        name = os.path.basename(p)
        ext = os.path.splitext(name)[1].lower()
        if ext in (".sh", ".py"):
            self.open_term(name, core.program_command(p, args), name)
        elif ext == ".c":
            self.compile(p, lambda exe: self.open_term(os.path.basename(exe), [exe] + args, name))
        elif ext == ".exe":
            head = core.exe_head(p)
            if head[:2] == b"MZ":
                self.add(Msg("card", title="%s is a Windows program" % name, kind="err", icon="warn",
                             lines=["Windows .exe files can't run on AI OS.",
                                    "Ask the AI to rewrite it in C, then run the .c file to get a native .exe."]))
                return
            c_src = os.path.splitext(name)[0] + ".c"
            src = c_src if os.path.isfile(os.path.join(core.APPS, c_src)) else name
            stale = core.stale_exe_source(p)
            if stale:
                self.compile(stale, lambda exe: self.open_term(name, [exe] + args, src))
                return
            if head != b"\x7fELF":
                self.chip("%s is not a runnable program." % name, "err", "warn")
                return
            self.open_term(name, core.program_command(p, args), src)
        elif ext == ".iso":
            self.boot_iso(p, name)
        else:
            self.open(ViewDialog(self, p))

    def open_term(self, title, cmd, src, env=None):
        if self.term:
            self.term.close()
        try:
            self.term = TermWindow(self, title, cmd, env or dict(os.environ), src)
        except OSError as e:
            self.chip("Couldn't start %s: %s" % (title, e), "err", "warn")
        if not isinstance(self.dialog, EditorDialog):   # the editor stays open underneath the app's window
            self.dialog = None
        self.menu = None
        self.dirty = True

    def compile(self, src, then):
        """Build a .c app in the background; then(exe) runs when it worked."""
        name = os.path.basename(src)
        exe_name = os.path.splitext(name)[0] + ".exe"
        card = self.add(Msg("chip", "compiling %s → %s" % (name, exe_name), kind="busy", icon="code"))

        def work():
            try:
                exe, out = core.compile_c(src)
            except OSError:
                exe, out = None, "C compiler (%s) not found" % core.CC
            self.post(done, exe, out)

        def done(exe, out):
            if exe:
                card.text, card.kind, card.icon = "built apps/%s" % exe_name, "ok", "check"
                card.touch()
                self.refresh_apps()
                if then:
                    then(exe)
            else:
                self.msgs.remove(card) if card in self.msgs else None
                err = "Compiling %s failed:\n%s" % (name, out or "compile failed")
                self.add(Msg("card", title="Compiling %s failed" % name, kind="err", icon="warn", mono=True,
                             lines=(out or "compile failed").split("\n")[-14:],
                             actions=[("Ask AI to fix", lambda: self.send(core.fix_request(err, name),
                                                                          shown="Fix %s (it doesn't compile)" % name),
                                       "primary", "sparkle")]))
            self.dirty = True
        threading.Thread(target=work, daemon=True).start()

    def boot_iso(self, p, name):
        import shutil
        if not shutil.which("qemu-system-x86_64"):
            self.chip("VM (qemu) not installed.", "err", "warn")
            return
        env = dict(os.environ)
        cmd, mem, avail = core.vm_command(p, env)
        if cmd is None:
            self.add(Msg("card", title="Not enough free memory for a VM", kind="err", icon="warn",
                         lines=["%d MB free. Delete big files such as old .iso files (apps live in RAM)," % avail,
                                "or give this PC/VM more RAM."]))
            return
        if mem < 1024:
            self.chip("the VM gets %d MB of RAM; AI OS inside AI OS needs about 1 GB" % mem, "warn", "warn")
        self.chip("Booting %s in a VM. Alt+2 then quit leaves it (or close the window)" % name, "info", "disc")
        self.open_term(name, cmd, None, env)

    def build_iso(self, arg):
        card = self.add(Msg("card", title="Building an ISO", icon="disc", kind="busy", lines=[]))

        def log(line, kind=None):
            def f():
                card.lines.append(line)
                if kind:
                    card.kind = kind
                card.touch()
                self.dirty = True
            self.post(f)

        def built(out, mb):
            def f():
                card.title, card.kind = "Built %s (%d MB)" % (out, mb), "ok"
                card.actions = [("Run", lambda: self.run_app(out), "primary", "play")]
                card.touch()
                self.refresh_apps()
            self.post(f)

        def work():
            r = core.make_iso(arg, log, lambda m: log(m, "err"), built)
            if r is None:
                def f():
                    if card.kind == "busy":
                        card.kind = "err"
                    card.title = card.title if card.kind == "ok" else "The ISO wasn't built"
                    card.touch()
                self.post(f)
        threading.Thread(target=work, daemon=True).start()

    def play(self, entry):
        try:
            self.game = GameView(self, entry)
        except Exception as e:
            self.toast("Couldn't start the game: %s" % e, "err", "warn")
        self.dirty = True

    # ---------------------------------------------------------------- events
    def handle(self, ev):
        if ev.type == "mouse_move" and self.input is not None and self.input.mouse_seen:
            self.dirty = True if self.game is None else self.dirty
        if self.game is not None:
            try:
                self.game.handle(ev)
            except Exception as e:
                self.game = None
                self.toast("The game stopped: %s" % e, "err", "warn")
            return
        if self.term is not None:
            self.term.handle(ev)
            return
        if self.dialog is not None:
            self.dialog.handle(ev)
            return
        if self.menu is not None and ev.type == "mouse_button" and ev.down:
            for rect, cb, key in self.menu["items"]:
                if rect.collidepoint(ev.pos):
                    self.menu = None
                    cb()
                    self.dirty = True
                    return
            self.menu = None
            self.dirty = True
            return
        if ev.type == "mouse_move":
            hv = None
            for rect, cb, key in self.hits:
                if rect.collidepoint(ev.pos):
                    hv = key
            if self.menu:
                for rect, cb, key in self.menu["items"]:
                    if rect.collidepoint(ev.pos):
                        hv = key
            if hv != self.hover:
                self.hover = hv
                self.dirty = True
        elif ev.type == "mouse_button" and ev.down and ev.button == 1:
            for rect, cb, key in reversed(self.hits):
                if rect.collidepoint(ev.pos):
                    cb(ev.pos) if key == "inputbox" else cb()
                    self.dirty = True
                    return
        elif ev.type == "wheel":
            if ev.pos[0] < self.sidebar_w():
                self.apps_top = max(0, self.apps_top - ev.dy)
            else:
                self.scroll_by(-ev.dy * T.px(60))
            self.dirty = True
        elif ev.type == "key" and ev.down:
            self.on_key(ev)

    def on_key(self, ev):
        k, mods = ev.key, ev.mods
        if k == "escape":
            if self.menu:
                self.menu = None
            else:
                self.stop_reply()
        elif "ctrl" in mods and k == "c" and self.stream:
            self.stop_reply()
        elif "ctrl" in mods and k == "n":
            self.new_chat()
        elif k == "pageup":
            self.scroll_by(-(self.H // 2))
        elif k == "pagedown":
            self.scroll_by(self.H // 2)
        elif k == "f1":
            self.open(HelpDialog(self))
        else:
            r = self.box.handle(ev)
            if r == "submit":
                self.submit()
        self.dirty = True

    def scroll_by(self, d):
        view = self.view_rect()
        mx = max(0, self.content_h - view.h)
        self.scroll_target = max(0, min(mx, self.scroll_target + d))
        self.stick_bottom = self.scroll_target >= mx - 2
        self.dirty = True

    # ---------------------------------------------------------------- layout
    def sidebar_w(self):
        return T.px(276)

    def input_h(self):
        inner = self.main_rect().w
        col = min(T.px(800), inner - T.px(64))
        th = self.box.height(col - T.px(90))
        return max(T.px(54), th + T.px(30))

    def main_rect(self):
        return pygame.Rect(self.sidebar_w(), 0, self.W - self.sidebar_w(), self.H)

    def view_rect(self):
        m = self.main_rect()
        top = T.px(60)
        bottom = self.H - self.input_h() - T.px(54)
        return pygame.Rect(m.x, top, m.w, bottom - top)

    def column(self):
        m = self.main_rect()
        w = min(T.px(800), m.w - T.px(64))
        return m.x + (m.w - w) // 2, w

    # ---------------------------------------------------------------- drawing
    def draw(self, s):
        if self.game is not None:
            try:
                self.game.frame(s)
            except Exception as e:
                self.game = None
                self.toast("The game stopped: %s" % e, "err", "warn")
            if self.input is not None and self.input.mouse_seen and self.game is None:
                T.draw_pointer(s, self.input.mouse_pos)
            return
        s.fill(T.C["bg"])
        self.hits = []
        self.draw_sidebar(s)
        self.draw_header(s)
        self.draw_transcript(s)
        self.draw_input(s)
        if self.menu:
            self.draw_menu(s)
        # an app started from the editor runs in a window on top of it (closing it returns to the editor)
        layers = [self.dialog, self.term] if isinstance(self.dialog, EditorDialog) else [self.term, self.dialog]
        for layer in layers:
            if layer is not None:
                layer.draw(s)
        self.draw_toasts(s)
        if self.input is not None and self.input.mouse_seen:
            T.draw_pointer(s, self.input.mouse_pos)

    def draw_sidebar(self, s):
        sw = self.sidebar_w()
        pygame.draw.rect(s, T.C["bg2"], (0, 0, sw, self.H))
        pygame.draw.line(s, T.C["line"], (sw - 1, 0), (sw - 1, self.H))
        pad = T.px(18)
        W.logo(s, (pad, T.px(18), T.px(38), T.px(38)))
        T.text(s, "AI OS", (pad + T.px(50), T.px(18)), "bold", 20)
        T.text(s, "your AI computer", (pad + T.px(50), T.px(43)), "regular", 12, T.C["muted"])
        nb = pygame.Rect(pad, T.px(76), sw - 2 * pad, T.px(42))
        T.button(s, nb, "New chat", "primary", self.hover == "new", "plus")
        self.hits.append((nb, self.new_chat, "new"))
        y = T.px(138)
        T.text(s, "APPS", (pad, y), "semibold", 11, T.C["muted"])
        if self.apps:
            W.pill(s, (pad + T.px(44), y - T.px(4)), str(len(self.apps)), T.C["text2"], anchor="topleft", size=11)
        nf = pygame.Rect(sw - pad - T.px(64), y - T.px(7), T.px(64), T.px(26))     # + New file
        if self.hover == "newfile":
            T.panel(s, nf, T.C["panel2"], 8)
        T.icon(s, "plus", (nf.x + T.px(4), nf.centery - T.px(7), T.px(14), T.px(14)), T.C["accent"])
        T.text(s, "New", (nf.x + T.px(22), nf.centery), "semibold", 12, T.C["accent"], anchor="midleft")
        self.hits.append((nf, lambda: self.open(NewFileDialog(self)), "newfile"))
        y += T.px(26)
        nav_top = self.H - T.px(4 * 44 + 64)
        rowh = T.px(42)
        vis = max(1, (nav_top - T.px(12) - y) // rowh)
        self.apps_top = max(0, min(self.apps_top, max(0, len(self.apps) - vis)))
        if not self.apps:
            for i, line in enumerate(T.wrap("Apps the AI makes for you show up here.", T.font("regular", 13), sw - 2 * pad)):
                T.text(s, line, (pad, y + T.px(6) + i * T.px(19)), "regular", 13, T.C["muted"])
        for i, (name, size) in enumerate(self.apps[self.apps_top:self.apps_top + vis]):
            row = pygame.Rect(T.px(10), y + i * rowh, sw - T.px(20), rowh - T.px(4))
            key = ("app", name)
            if self.hover == key or (self.menu and self.menu.get("app") == name):
                T.panel(s, row, T.C["panel2"], 10)
            kind = core.kind_of(name)
            W.kind_tile(s, (row.x + T.px(8), row.centery - T.px(14), T.px(28), T.px(28)), kind, 15)
            nf = T.font("medium", 14)
            T.text(s, W.ellipsize(name, nf, row.w - T.px(110)), (row.x + T.px(46), row.centery), "medium", 14, anchor="midleft")
            T.text(s, W.human_size(size), (row.right - T.px(8), row.centery), "regular", 11, T.C["muted"], anchor="midright")
            self.hits.append((row, lambda n=name, r=row: self.app_menu(n, r), key))
        if len(self.apps) > vis:
            T.text(s, "scroll for %d more" % (len(self.apps) - vis - self.apps_top) if len(self.apps) - vis - self.apps_top > 0 else "",
                   (pad, nav_top - T.px(18)), "regular", 11, T.C["muted"])
        pygame.draw.line(s, T.C["line"], (pad, nav_top - T.px(4)), (sw - pad, nav_top - T.px(4)))
        items = [("Games", "gamepad", lambda: self.open(GamesDialog(self)), ""),
                 ("Wi-Fi", "wifi", lambda: self.open(WifiDialog(self)), self.wifi_label),
                 ("Settings", "gear", lambda: self.open(SettingsDialog(self)), ""),
                 ("Power", "power", lambda: self.open(PowerDialog(self)), "")]
        for i, (label, icon, cb, extra) in enumerate(items):
            row = pygame.Rect(T.px(10), nav_top + T.px(4) + i * T.px(44), sw - T.px(20), T.px(40))
            key = ("nav", label)
            if self.hover == key:
                T.panel(s, row, T.C["panel2"], 10)
            T.icon(s, icon, (row.x + T.px(12), row.centery - T.px(10), T.px(20), T.px(20)), T.C["text2"])
            T.text(s, label, (row.x + T.px(44), row.centery), "medium", 14, anchor="midleft")
            if extra:
                T.text(s, W.ellipsize(extra, T.font("regular", 11), T.px(110)), (row.right - T.px(10), row.centery),
                       "regular", 11, T.C["muted"], anchor="midright")
            self.hits.append((row, cb, key))
        fy = self.H - T.px(26)
        col = T.C["ok"] if self.online else T.C["muted"]
        pygame.draw.circle(s, col, (pad + T.px(4), fy), T.px(4))
        T.text(s, "Online" if self.online else "Offline", (pad + T.px(16), fy), "medium", 12, col, anchor="midleft")
        T.text(s, W.ellipsize(self.model.split("/")[-1], T.font("regular", 11), T.px(150)), (sw - pad, fy), "regular", 11,
               T.C["muted"], anchor="midright")

    def app_menu(self, name, row):
        kind = core.kind_of(name)
        items = []
        if kind in ("c", "py", "sh", "exe", "iso"):
            items.append(("Run", "play", lambda: self.run_app(name), "normal"))
        items.append(("View", "file", lambda: self.open(ViewDialog(self, os.path.join(core.APPS, name))), "normal"))
        if kind not in ("exe", "iso"):
            items.append(("Edit", "code", lambda: self.edit_app(name), "normal"))
            items.append(("Ask the AI about it", "chat", lambda: self.ask_about(name), "normal"))
        items.append(("Delete", "trash", lambda: self.confirm_delete(name), "danger"))
        w = T.px(220)
        h = T.px(10) + len(items) * T.px(38)
        r = pygame.Rect(row.right + T.px(8), row.y, w, h)
        if r.bottom > self.H - T.px(10):
            r.bottom = self.H - T.px(10)
        self.menu = {"app": name, "rect": r, "items": [], "spec": items}
        self.dirty = True

    def draw_menu(self, s):
        r = self.menu["rect"]
        T.panel(s, r, T.C["panel"], 12, T.C["line"], shadow=True)
        self.menu["items"] = []
        for i, (label, icon, cb, kind) in enumerate(self.menu["spec"]):
            row = pygame.Rect(r.x + T.px(5), r.y + T.px(5) + i * T.px(38), r.w - T.px(10), T.px(36))
            key = ("menu", label)
            if self.hover == key:
                T.panel(s, row, T.C["panel2"], 8)
            col = T.C["err"] if kind == "danger" else T.C["text"]
            T.icon(s, icon, (row.x + T.px(10), row.centery - T.px(8), T.px(16), T.px(16)), col)
            T.text(s, label, (row.x + T.px(36), row.centery), "medium", 14, col, anchor="midleft")
            self.menu["items"].append((row, cb, key))

    def draw_header(self, s):
        m = self.main_rect()
        title = "New conversation"
        for msg in self.msgs:
            if msg.role == "user":
                title = msg.text.split("\n")[0]
                break
        T.text(s, W.ellipsize(title, T.font("semibold", 16), m.w - T.px(360)), (m.x + T.px(28), T.px(30)), "semibold", 16,
               anchor="midleft")
        x = m.right - T.px(24)
        r = W.pill(s, (x, T.px(30)), self.model.split("/")[-1], T.C["accent"], "sparkle", anchor="midright")
        if self.stream:
            dots = "." * (1 + int(time.monotonic() * 3) % 3)
            label = ("Writing" if self.stream[0].text else "Thinking") + dots
            T.text(s, label, (r.x - T.px(14), T.px(30)), "medium", 13, T.C["text2"], anchor="midright")
        pygame.draw.line(s, T.C["line"], (m.x, T.px(59)), (m.right, T.px(59)))

    def msg_surface(self, msg, width):
        if msg.cache and msg.cache[0] == width and msg.cache[1] == msg.version:
            return msg.cache[2], msg.cache[3]
        h, btns = self.render_msg(None, msg, width)
        surf = pygame.Surface((width, max(1, h)), pygame.SRCALPHA)
        h, btns = self.render_msg(surf, msg, width)
        msg.cache = (width, msg.version, surf, btns)
        return surf, btns

    def render_msg(self, s, msg, width):
        """Draw (s is a Surface) or measure (s is None) one message. Returns (height, buttons)
        where buttons are [(rect, label, kind, icon, callback)] relative to the message."""
        draw = s is not None
        btns = []
        if msg.role == "welcome":
            return self.render_welcome(s, width, btns), btns
        if msg.role == "chip":
            col = {"ok": T.C["ok"], "err": T.C["err"], "warn": T.C["warn"], "busy": T.C["cyan"]}.get(msg.kind, T.C["text2"])
            if draw:
                W.pill(s, (width // 2, 0), msg.text + ("…" if msg.kind == "busy" else ""), col, msg.icon, size=12)
            return T.font("medium", 12).get_linesize() + T.px(10), btns
        if msg.role == "user":
            f = T.font("regular", 15)
            maxw = int(width * 0.72)
            lines = T.wrap(msg.text, f, maxw - T.px(32))
            tw = max([f.size(l)[0] for l in lines] + [T.px(20)])
            lh = f.get_linesize()
            bw, bh = tw + T.px(32), len(lines) * lh + T.px(22)
            if draw:
                r = pygame.Rect(width - bw, 0, bw, bh)
                pygame.draw.rect(s, T.C["user"], r, border_radius=T.px(16), border_bottom_right_radius=T.px(4))
                for i, l in enumerate(lines):
                    s.blit(f.render(l, True, (255, 255, 255)), (r.x + T.px(16), r.y + T.px(11) + i * lh))
            return bh, btns
        if msg.role == "card":
            return self.render_card(s, msg, width, btns), btns
        # AI message
        av = T.px(15)
        x0 = av * 2 + T.px(12)
        if draw:
            W.avatar(s, (av, av), av)
            T.text(s, "AI OS", (x0, T.px(2)), "semibold", 13)
            T.text(s, msg.time, (x0 + T.font("semibold", 13).size("AI OS")[0] + T.px(8), T.px(3)), "regular", 12, T.C["muted"])
        y = T.px(24)
        bw = width - x0
        inner_x, inner_w = x0 + T.px(16), bw - T.px(32)
        blocks = W.split_blocks(msg.text) if msg.text else []
        yy = y + T.px(12)
        body = []
        for b in blocks:
            if b[0] == "text":
                h = W.rich_text(None, b[1], inner_x, 0, inner_w, T.C["text"], draw=False)
                body.append((b, h))
            elif b[0] == "code":
                body.append((b, W.code_block(None, inner_x, 0, inner_w, b[1], b[2], draw=False)))
            else:
                body.append((b, T.px(66)))
        total = sum(h for _, h in body) + T.px(10) * max(0, len(body) - 1)
        if not blocks:
            total = T.font("regular", 15).get_linesize()
        bh = total + T.px(24)
        if draw:
            r = pygame.Rect(x0, y, bw, bh)
            pygame.draw.rect(s, T.C["panel"], r, border_radius=T.px(16), border_top_left_radius=T.px(4))
            pygame.draw.rect(s, T.C["line"], r, width=1, border_radius=T.px(16), border_top_left_radius=T.px(4))
            if not blocks:
                dots = int(time.monotonic() * 3) % 3
                for i in range(3):
                    pygame.draw.circle(s, T.C["accent"] if i == dots else T.C["muted"],
                                       (inner_x + T.px(6) + i * T.px(14), yy + T.px(9)), T.px(4))
        for b, h in body:
            if b[0] == "text":
                if draw:
                    W.rich_text(s, b[1], inner_x, yy, inner_w, T.C["text"])
            elif b[0] == "code":
                if draw:
                    W.code_block(s, inner_x, yy, inner_w, b[1], b[2])
            else:
                self.render_file_card(s, b, inner_x, yy, inner_w, btns, draw)
            yy += h + T.px(10)
        if msg.streaming and blocks and draw:
            pygame.draw.rect(s, T.C["accent"], (inner_x, yy - T.px(6), T.px(8), T.px(3)), border_radius=T.px(2))
        return y + bh, btns

    def render_file_card(self, s, block, x, y, w, btns, draw):
        _, name, body, complete = block
        kind = core.kind_of(name)
        h = T.px(56)
        if draw:
            r = pygame.Rect(x, y, w, h)
            T.panel(s, r, T.C["panel2"], 12, T.C["line"])
            W.kind_tile(s, (r.x + T.px(10), r.y + T.px(10), T.px(36), T.px(36)), kind, 18)
            T.text(s, name, (r.x + T.px(58), r.y + T.px(10)), "semibold", 14)
            nlines = body.count("\n") + (0 if body.endswith("\n") else 1)
            meta = ("%s  ·  %d lines  ·  saved" % (W.KIND_LABEL.get(kind, "File"), nlines) if complete
                    else "writing…  %d lines so far" % nlines)
            T.text(s, meta, (r.x + T.px(58), r.y + T.px(31)), "regular", 12, T.C["ok"] if complete else T.C["muted"])
        if complete:
            bx = x + w - T.px(10)
            for label, kind2, icon, cb in (("View", "normal", "file", lambda n=name: self.view_app(n)),
                                           ("Edit", "normal", "code", lambda n=name: self.edit_app(n)),
                                           ("Run", "primary", "play", lambda n=name: self.run_app(n))):
                if label == "Run" and kind not in ("c", "py", "sh", "exe", "iso"):
                    continue
                if label == "Edit" and kind in ("exe", "iso"):
                    continue
                bw = T.px(84)
                bx -= bw
                btns.append((pygame.Rect(bx, y + T.px(13), bw, T.px(30)), label, kind2, icon, cb))
                bx -= T.px(8)
        return h

    def view_app(self, name):
        p = core.find_app(name)
        if p:
            self.open(ViewDialog(self, p))
        else:
            self.chip("No such file.", "err", "warn")

    def render_card(self, s, msg, width, btns):
        draw = s is not None
        f = T.font("mono" if msg.mono else "regular", 13 if msg.mono else 14)
        lh = f.get_linesize()
        lines = []
        for l in msg.lines:
            lines += T.wrap(l, f, width - T.px(40)) if l else [""]
        lines = lines[-40:]
        h = T.px(46) + len(lines) * lh + (T.px(48) if msg.actions else T.px(10))
        if draw:
            col = {"ok": T.C["ok"], "err": T.C["err"], "warn": T.C["warn"], "busy": T.C["cyan"]}.get(msg.kind, T.C["accent"])
            r = pygame.Rect(0, 0, width, h)
            T.panel(s, r, T.C["panel"], 14, T.C["line"])
            pygame.draw.rect(s, col, (r.x, r.y + T.px(14), T.px(3), T.px(18)), border_radius=T.px(2))
            T.icon(s, msg.icon or "file", (r.x + T.px(16), r.y + T.px(14), T.px(18), T.px(18)), col)
            T.text(s, msg.title + ("…" if msg.kind == "busy" else ""), (r.x + T.px(44), r.y + T.px(14)), "semibold", 14)
            for i, l in enumerate(lines):
                s.blit(f.render(l, True, T.C["text2"]), (r.x + T.px(20), r.y + T.px(42) + i * lh))
        if msg.actions:
            bx = T.px(20)
            for label, cb, kind, icon in msg.actions:
                bw = T.px(150)
                btns.append((pygame.Rect(bx, h - T.px(44), bw, T.px(32)), label, kind, icon, cb))
                bx += bw + T.px(10)
        return h

    def render_welcome(self, s, width, btns):
        draw = s is not None
        y = T.px(40)
        if draw:
            W.logo(s, (width // 2 - T.px(32), y, T.px(64), T.px(64)))
            T.text(s, "What should we make today?", (width // 2, y + T.px(86)), "bold", 28, anchor="midtop")
            T.text(s, "Ask for anything. The AI can write apps, and you run them with one click.",
                   (width // 2, y + T.px(130)), "regular", 15, T.C["text2"], anchor="midtop")
        y += T.px(180)
        cw = (width - T.px(16)) // 2
        for i, (title, sub) in enumerate(SUGGESTIONS):
            r = pygame.Rect((i % 2) * (cw + T.px(16)), y + (i // 2) * T.px(86), cw, T.px(74))
            btns.append((r, "suggest:" + title, "card", None, lambda t=title: self.send(t)))
            if draw:
                T.panel(s, r, T.C["panel"], 14, T.C["line"])
                T.text(s, title, (r.x + T.px(18), r.y + T.px(16)), "semibold", 15)
                T.text(s, sub, (r.x + T.px(18), r.y + T.px(42)), "regular", 13, T.C["muted"])
        return y + 2 * T.px(86)

    def draw_transcript(self, s):
        view = self.view_rect()
        cx, cw = self.column()
        gap = T.px(18)
        items = []
        y = T.px(20)
        for msg in self.msgs:
            surf, btns = self.msg_surface(msg, cw)
            items.append((msg, y, surf, btns))
            y += surf.get_height() + gap
        self.content_h = y + T.px(10)
        mx = max(0, self.content_h - view.h)
        if self.stick_bottom:
            self.scroll_target = mx
        self.scroll_target = min(self.scroll_target, mx)
        if abs(self.scroll - self.scroll_target) < 1:
            self.scroll = self.scroll_target
        else:
            self.scroll += (self.scroll_target - self.scroll) * 0.35
        clip = s.get_clip()
        s.set_clip(view)
        for msg, my, surf, btns in items:
            sy = view.y + my - int(self.scroll)
            if sy > view.bottom or sy + surf.get_height() < view.y:
                continue
            s.blit(surf, (cx, sy))
            for rect, label, kind, icon, cb in btns:
                r = rect.move(cx, sy)
                key = ("mbtn", id(msg), label)
                if kind == "card":       # welcome suggestions: the whole card is the button
                    if self.hover == key:
                        pygame.draw.rect(s, T.C["accent"], r, width=1, border_radius=T.px(14))
                else:
                    W.small_button(s, r, label, kind, self.hover == key, icon)
                vis = r.clip(view)
                if vis.w > 0 and vis.h > 0:
                    self.hits.append((vis, cb, key))
        s.set_clip(clip)
        if mx > 0:
            frac = self.scroll / mx
            th = max(T.px(40), view.h * view.h // self.content_h)
            pygame.draw.rect(s, T.C["line"], (view.right - T.px(10), view.y + int((view.h - th) * frac), T.px(4), th),
                             border_radius=T.px(2))

    def draw_input(self, s):
        m = self.main_rect()
        cx, cw = self.column()
        h = self.input_h()
        box = pygame.Rect(cx, self.H - h - T.px(40), cw, h)
        focused = self.dialog is None and self.term is None
        T.panel(s, box, T.C["panel"], 16, T.C["accent"] if focused else T.C["line"], shadow=True)
        tr = pygame.Rect(box.x + T.px(18), box.y + T.px(15), box.w - T.px(90), box.h - T.px(24))
        self.box.draw(s, tr, focused=focused)
        self.hits.append((box, lambda pos=None: self.box.click(tr, pos) if pos else None, "inputbox"))
        b = pygame.Rect(box.right - T.px(52), box.bottom - T.px(46), T.px(38), T.px(38))
        if self.stream:
            pygame.draw.rect(s, T.C["panel2"], b, border_radius=T.px(12))
            T.icon(s, "stop", b.inflate(-T.px(14), -T.px(14)), T.C["text"])
            self.hits.append((b, self.stop_reply, "stop"))
        else:
            if self.box.text.strip():
                T.gradient_rect(s, b, T.C["accent"], T.C["accent2"], radius=12)
            else:
                pygame.draw.rect(s, T.C["panel2"], b, border_radius=T.px(12))
            T.icon(s, "send", b.inflate(-T.px(16), -T.px(16)), (255, 255, 255) if self.box.text.strip() else T.C["muted"])
            self.hits.append((b, self.submit, "send"))
        T.text(s, "Enter to send  ·  Shift+Enter for a new line  ·  /help for commands",
               (cx + cw // 2, self.H - T.px(30)), "regular", 11, T.C["muted"], anchor="midtop")

    def draw_toasts(self, s):
        now = time.monotonic()
        self.toasts = [t for t in self.toasts if now - t[3] < 4.0]
        y = T.px(72)
        for text, kind, icon, t0 in self.toasts:
            col = {"ok": T.C["ok"], "err": T.C["err"], "warn": T.C["warn"]}.get(kind, T.C["text2"])
            f = T.font("medium", 13)
            w = f.size(text)[0] + T.px(56)
            r = pygame.Rect(self.W - w - T.px(20), y, w, T.px(42))
            age = now - t0
            alpha = 255 if age < 3.4 else int(255 * (4.0 - age) / 0.6)
            layer = pygame.Surface(r.size, pygame.SRCALPHA)
            T.panel(layer, layer.get_rect(), T.C["panel2"], 12, T.C["line"])
            T.icon(layer, icon or "check", (T.px(14), r.h // 2 - T.px(9), T.px(18), T.px(18)), col)
            layer.blit(f.render(text, True, T.C["text"]), (T.px(42), r.h // 2 - f.get_linesize() // 2))
            layer.set_alpha(max(0, alpha))
            s.blit(layer, r)
            y += T.px(50)

    # ---------------------------------------------------------------- main loop
    def animating(self):
        return bool(self.stream or (self.term is not None and self.term.term.running) or self.game or self.toasts
                    or abs(self.scroll - self.scroll_target) >= 1
                    or any(m.kind == "busy" for m in self.msgs[-3:]))

    def step(self, timeout=None):
        """One pass of the main loop: input, background results, periodic checks, drawing."""
        if timeout is None:
            timeout = 0.016 if self.game is not None else (0.03 if self.animating() else 0.4)
        for ev in self.input.poll(timeout):
            self.handle(ev)
        while True:
            try:
                fn, args, kw = self.q.get_nowait()
            except queue.Empty:
                break
            fn(*args, **kw)
            self.dirty = True
        if self.term is not None:
            if self.term.term.pump():
                self.dirty = True
            if not self.term.term.running and not self.term.reported:
                self.term.report()
                self.dirty = True
        now = time.monotonic()
        if now >= self._next_poll:
            self._next_poll = now + 3.0
            online = core.default_route()
            if online != self.online:
                self.online = online
                self.dirty = True
            if core.wifi_tools() and not HEADLESS:
                threading.Thread(target=self._wifi_poll, daemon=True).start()
            if len(self.apps) != len(core.list_apps()):
                self.refresh_apps()
        if self.animating() or self.box.text or self.dialog is not None:
            self.dirty = True          # blinking cursors, thinking dots, smooth scrolling
        if self.dirty:
            self.draw(self.surface)
            self.display.flip()
            self.dirty = False

    def _wifi_poll(self):
        connected, kv = core.wifi_status()
        label = core.printable(kv.get("ssid", "")) if connected else ""
        if label != self.wifi_label:
            self.post(setattr, self, "wifi_label", label)

    def attach(self, disp):
        self.display = disp
        self.surface = disp.surface
        self.input = display.Input(disp.size)

    def run(self):
        while not self.quit:
            self.step()


def main():
    if not display.available():
        os.execv("/usr/bin/aichat", ["aichat"])
    pygame.font.init()
    size = screen_size()
    app = App(size)
    first = pygame.Surface(size)
    app.draw(first)                        # drawn before taking the screen (no input yet: no pointer)
    boot.finish_loading()                  # the loading screen closes; then the screen is ours
    disp = display.Display()

    def bye(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, bye)
    try:
        app.attach(disp)
        disp.surface.blit(first, (0, 0))
        disp.flip()
        app.dirty = True
        app.run()
    finally:
        if app.term is not None:
            app.term.term.kill()
        disp.close()


if __name__ == "__main__":
    main()
