"""A terminal window for running apps inside the graphical chat.

The app runs on a pseudo-terminal; its output goes through pyte (a VT100/xterm emulator) and
is drawn with JetBrains Mono. Keys typed while the window has focus are sent to the app as
the bytes a real terminal would send (arrows, Ctrl+C, function keys...).
"""
import errno, fcntl, os, re, signal, struct, subprocess, termios, time

import pygame
import pyte

from aios import theme as T

# 16-colour palette tuned for the dark terminal background
PALETTE = {
    "black": (46, 50, 66), "red": (248, 113, 113), "green": (74, 222, 128), "brown": (250, 204, 21),
    "blue": (96, 165, 250), "magenta": (232, 121, 249), "cyan": (34, 211, 238), "white": (214, 218, 230),
    "brightblack": (110, 117, 140), "brightred": (252, 165, 165), "brightgreen": (134, 239, 172),
    "brightbrown": (253, 224, 71), "brightblue": (147, 197, 253), "brightmagenta": (240, 171, 252),
    "brightcyan": (103, 232, 249), "brightwhite": (255, 255, 255),
}
DEFAULT_FG = (222, 225, 235)
DECCKM = 1 << 5          # pyte stores private mode 1 (application cursor keys) shifted by 5 bits

SEQ = {
    "return": b"\r", "backspace": b"\x7f", "tab": b"\t", "escape": b"\x1b", "delete": b"\x1b[3~",
    "insert": b"\x1b[2~", "home": b"\x1b[H", "end": b"\x1b[F", "pageup": b"\x1b[5~", "pagedown": b"\x1b[6~",
    "f1": b"\x1bOP", "f2": b"\x1bOQ", "f3": b"\x1bOR", "f4": b"\x1bOS", "f5": b"\x1b[15~", "f6": b"\x1b[17~",
    "f7": b"\x1b[18~", "f8": b"\x1b[19~", "f9": b"\x1b[20~", "f10": b"\x1b[21~", "f11": b"\x1b[23~",
}
ARROWS = {"up": b"A", "down": b"B", "right": b"C", "left": b"D"}
CTRL_PUNCT = {"space": b"\x00", "leftbracket": b"\x1b", "backslash": b"\x1c", "rightbracket": b"\x1d"}
ANSI = re.compile(r"\x1b(\[[0-9;?]*[ -/]*[@-~]|\][^\x07]*\x07|[()][0-9A-Za-z]|.)")


def _colour(name, default):
    if name in (None, "", "default"):
        return default
    if name in PALETTE:
        return PALETTE[name]
    if len(name) == 6:
        try:
            return tuple(int(name[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return default


def _term_name():
    """The best TERM this system has a terminfo entry for."""
    for name in ("xterm-256color", "xterm", "vt100"):
        for base in ("/usr/share/terminfo", "/etc/terminfo", "/lib/terminfo"):
            if os.path.exists(os.path.join(base, name[0], name)):
                return name
    return "xterm-256color"


class Terminal:
    """One app running on a pseudo-terminal of cols x rows characters."""

    def __init__(self, cols=100, rows=30):
        self.cols, self.rows = cols, rows
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.ByteStream(self.screen)
        self.screen.write_process_input = self._reply   # answers to "where is the cursor?" and similar
        self.proc = None
        self.fd = None
        self.rc = None
        self.tail = bytearray()      # recent raw output, for "Ask AI to fix"
        self._rows = {}              # row -> (signature, Surface)
        self._cell = None

    # -- process
    def start(self, cmd, cwd=None, env=None):
        master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.cols, 0, 0))
        env = dict(env or os.environ)
        env.update(TERM=_term_name(), COLUMNS=str(self.cols), LINES=str(self.rows))
        env.setdefault("LANG", "C.UTF-8")

        def child_setup():
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)     # the pty becomes the app's terminal (Ctrl+C works)
            signal.signal(signal.SIGINT, signal.SIG_DFL)
        try:
            self.proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
                                         start_new_session=True, preexec_fn=child_setup, close_fds=True)
        finally:
            os.close(slave)
        self.fd = master
        fl = fcntl.fcntl(master, fcntl.F_GETFL)
        fcntl.fcntl(master, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    @property
    def running(self):
        return self.proc is not None and self.rc is None

    def _reply(self, data):
        if self.fd is not None:
            try:
                os.write(self.fd, data.encode() if isinstance(data, str) else data)
            except OSError:
                pass

    def pump(self):
        """Read what the app wrote; returns True when the screen changed."""
        if self.fd is None:
            return False
        changed = False
        for _ in range(64):
            try:
                data = os.read(self.fd, 65536)
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    break
                data = b""          # EIO: the app closed its terminal
            if not data:
                self._finish()
                return True
            self.stream.feed(data)
            self.tail += data
            if len(self.tail) > 16000:
                del self.tail[:-12000]
            changed = True
        if self.proc is not None and self.rc is None and self.proc.poll() is not None:
            self._finish()          # exited, even if something it started still holds the terminal
            changed = True
        return changed

    def _finish(self):
        if self.rc is None and self.proc is not None:
            try:
                self.rc = self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.kill()
                self.rc = self.proc.wait()
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def kill(self):
        """End the app (and whatever it started)."""
        if self.proc is None or self.proc.poll() is not None:
            return
        for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(self.proc.pid, sig)
            except OSError:
                pass
            for _ in range(10):
                if self.proc.poll() is not None:
                    return
                time.sleep(0.03)

    def send(self, data):
        if self.fd is not None and data:
            try:
                os.write(self.fd, data)
            except OSError:
                pass

    def key(self, ev):
        """Send a key Event to the app the way a terminal would."""
        if ev.type != "key" or not ev.down:
            return
        k, mods = ev.key, ev.mods
        if k in ARROWS:
            self.send((b"\x1bO" if DECCKM in self.screen.mode else b"\x1b[") + ARROWS[k])
        elif k == "tab" and "shift" in mods:
            self.send(b"\x1b[Z")
        elif "ctrl" in mods and len(k) == 1 and k.isalpha():
            self.send(bytes([ord(k) & 0x1F]))
        elif "ctrl" in mods and k in CTRL_PUNCT:
            self.send(CTRL_PUNCT[k])
        elif k in SEQ:
            self.send(SEQ[k])
        elif ev.char:
            data = ev.char.encode("utf-8")
            self.send(b"\x1b" + data if "alt" in mods else data)
        elif "alt" in mods and len(k) == 1:
            self.send(b"\x1b" + k.encode())       # Alt+2 etc. (QEMU's display uses Alt+digit)

    def text(self, lines=40):
        """The last lines the app showed, as plain text (for error reports)."""
        raw = self.tail.decode("utf-8", "replace")
        raw = ANSI.sub("", raw).replace("\r\n", "\n").replace("\r", "\n")
        out = [l.rstrip() for l in raw.split("\n")]
        while out and not out[-1]:
            out.pop()
        return "\n".join(out[-lines:])

    # -- drawing
    def cell_size(self):
        if self._cell is None:
            f = T.font("mono", 14)
            self._cell = (f.size("M")[0], f.get_linesize())
        return self._cell

    def draw(self, surface, origin, focused=True):
        """Draw the screen with its top-left corner at `origin`."""
        cw, ch = self.cell_size()
        ox, oy = origin
        f, fb = T.font("mono", 14), T.font("mono-bold", 14)
        buf = self.screen.buffer
        for y in range(self.rows):
            row = buf[y]
            sig = tuple((row[x].data, row[x].fg, row[x].bg, row[x].bold, row[x].reverse, row[x].underscore)
                        for x in range(self.cols))
            cached = self._rows.get(y)
            if cached is None or cached[0] != sig:
                img = pygame.Surface((self.cols * cw, ch), pygame.SRCALPHA)
                x = 0
                while x < self.cols:          # draw runs of characters that share a style
                    c = row[x]
                    start, style = x, (c.fg, c.bg, c.bold, c.reverse, c.underscore)
                    chars = []
                    while x < self.cols and (row[x].fg, row[x].bg, row[x].bold, row[x].reverse, row[x].underscore) == style:
                        chars.append(row[x].data or " ")
                        x += 1
                    fg = _colour(style[0], DEFAULT_FG)
                    bg = _colour(style[1], None)
                    if style[2] and style[0] in PALETTE and not style[0].startswith("bright"):
                        fg = PALETTE["bright" + style[0]]
                    if style[3]:
                        fg, bg = (bg or T.C["term_bg"]), fg
                    if bg is not None:
                        pygame.draw.rect(img, bg, (start * cw, 0, (x - start) * cw, ch))
                    s = "".join(chars)
                    if s.strip():
                        img.blit((fb if style[2] else f).render(s, True, fg), (start * cw, 0))
                    if style[4]:
                        pygame.draw.line(img, fg, (start * cw, ch - 2), (x * cw, ch - 2))
                self._rows[y] = cached = (sig, img)
            surface.blit(cached[1], (ox, oy + y * ch))
        self.screen.dirty.clear()
        cur = self.screen.cursor
        if self.running and not cur.hidden and focused and int(time.monotonic() * 2) % 2 == 0:
            r = pygame.Rect(ox + cur.x * cw, oy + cur.y * ch, cw, ch)
            pygame.draw.rect(surface, T.C["accent"], r, border_radius=2)
            data = buf[cur.y][cur.x].data
            if data.strip():
                surface.blit(f.render(data, True, (20, 10, 24)), r)
