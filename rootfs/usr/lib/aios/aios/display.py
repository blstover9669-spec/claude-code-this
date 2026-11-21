"""Screen and input for AI OS's graphical programs (the loading screen, games and the chat).

Programs draw with ordinary pygame calls on `Display.surface` (also what
pygame.display.get_surface() returns) and call `Display.flip()`; finished frames are copied
to the Linux framebuffer /dev/fb0. Keyboard and mouse come straight from /dev/input/event*
through `Input`. No X or Wayland is involved.

Development on a normal PC: set AIOS_HEADLESS=1280x800. Nothing is shown; `flip()` saves
each frame as a PNG when AIOS_SHOTS=<dir> is set, and tests feed events with Input.inject().
"""
import array, errno, fcntl, glob, mmap, os, select, struct, time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")      # pygame draws off-screen; we copy frames
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

# ---------------------------------------------------------------------------- Linux constants
FBIOGET_VSCREENINFO, FBIOGET_FSCREENINFO = 0x4600, 0x4602
KDSETMODE, KD_TEXT, KD_GRAPHICS = 0x4B3A, 0, 1
KDGKBMODE, KDSKBMODE, K_OFF = 0x4B44, 0x4B45, 4
VT_LOCKSWITCH, VT_UNLOCKSWITCH = 0x560B, 0x560C
EV_SYN, EV_KEY, EV_REL, EV_ABS = 0, 1, 2, 3
REL_X, REL_Y, REL_HWHEEL, REL_WHEEL = 0, 1, 6, 8
ABS_X, ABS_Y = 0, 1
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_TOUCH = 0x110, 0x111, 0x112, 0x14A
EVENT = struct.Struct("llHHi")          # struct input_event on 64-bit Linux
EVIOCGABS = lambda axis: 0x80184540 + axis  # noqa: E731  _IOR('E', 0x40+axis, struct input_absinfo)
EVIOCGBIT = lambda ev, n: 0x80004520 + ev + (n << 16)  # noqa: E731  _IOC(READ, 'E', 0x20+ev, n)

# evdev key code -> (name, char, shifted char). US layout.
KEYS = {
    1: ("escape", "", ""), 14: ("backspace", "", ""), 15: ("tab", "\t", "\t"), 28: ("return", "\n", "\n"),
    57: ("space", " ", " "), 111: ("delete", "", ""), 110: ("insert", "", ""),
    102: ("home", "", ""), 107: ("end", "", ""), 104: ("pageup", "", ""), 109: ("pagedown", "", ""),
    103: ("up", "", ""), 108: ("down", "", ""), 105: ("left", "", ""), 106: ("right", "", ""),
    29: ("lctrl", "", ""), 97: ("rctrl", "", ""), 42: ("lshift", "", ""), 54: ("rshift", "", ""),
    56: ("lalt", "", ""), 100: ("ralt", "", ""), 125: ("lmeta", "", ""), 126: ("rmeta", "", ""),
    58: ("capslock", "", ""), 96: ("return", "\n", "\n"),
    12: ("minus", "-", "_"), 13: ("equals", "=", "+"), 26: ("leftbracket", "[", "{"),
    27: ("rightbracket", "]", "}"), 39: ("semicolon", ";", ":"), 40: ("quote", "'", '"'),
    41: ("backquote", "`", "~"), 43: ("backslash", "\\", "|"), 51: ("comma", ",", "<"),
    52: ("period", ".", ">"), 53: ("slash", "/", "?"),
    55: ("kp_multiply", "*", "*"), 74: ("kp_minus", "-", "-"), 78: ("kp_plus", "+", "+"),
    98: ("kp_divide", "/", "/"), 83: ("kp_period", ".", "."),
}
for i, (lo, hi) in enumerate(zip("1234567890", "!@#$%^&*()")):
    KEYS[2 + i] = (lo, lo, hi)
for row, start in (("qwertyuiop", 16), ("asdfghjkl", 30), ("zxcvbnm", 44)):
    for i, ch in enumerate(row):
        KEYS[start + i] = (ch, ch, ch.upper())
for i in range(10):                                  # F1-F10, F11, F12
    KEYS[59 + i] = ("f%d" % (i + 1), "", "")
KEYS[87], KEYS[88] = ("f11", "", ""), ("f12", "", "")
for code, ch in zip((82, 79, 80, 81, 75, 76, 77, 71, 72, 73), "0123456789"):
    KEYS[code] = ("kp" + ch, ch, ch)


class Event:
    """One input event. type: 'key' | 'mouse_move' | 'mouse_button' | 'wheel'.

    key events: key (name such as 'a', 'return', 'left', 'f1'), down, repeat (held-key repeat),
                char (the text typed, '' for none; already shifted), mods (set of 'shift', 'ctrl', 'alt')
    mouse:      pos (x, y); button 1 left / 2 middle / 3 right, down; wheel: dy (+1 up, -1 down)
    """
    __slots__ = ("type", "key", "down", "repeat", "char", "mods", "pos", "button", "dy")

    def __init__(self, type, key="", down=False, repeat=False, char="", mods=(), pos=(0, 0), button=0, dy=0):
        self.type, self.key, self.down, self.repeat, self.char = type, key, down, repeat, char
        self.mods, self.pos, self.button, self.dy = set(mods), pos, button, dy

    def __repr__(self):
        if self.type == "key":
            return "<key %s %s%s %r>" % (self.key, "down" if self.down else "up", " repeat" if self.repeat else "", self.char)
        return "<%s %s b%d dy%d>" % (self.type, self.pos, self.button, self.dy)


# ---------------------------------------------------------------------------- display
class Display:
    """The screen. `surface` is a normal pygame Surface; draw on it, then call flip()."""

    def __init__(self, take_console=True):
        pygame.display.init()
        pygame.font.init()
        self.headless = os.environ.get("AIOS_HEADLESS", "")
        self.shots = os.environ.get("AIOS_SHOTS", "")
        self._frame = 0
        self._tty = None
        self._kbmode = None
        if self.headless:
            w, h = (int(v) for v in self.headless.lower().split("x"))
            self.size = (w, h)
            self._fb = None
        else:
            self._open_fb()
            if take_console:
                self._take_console()
        self.width, self.height = self.size
        # the off-screen surface everything is drawn on; convert()/convert_alpha() work against it
        self.surface = pygame.display.set_mode(self.size, 0, 32)

    # -- framebuffer
    def _open_fb(self):
        path = os.environ.get("AIOS_FB", "/dev/fb0")
        self._fd = os.open(path, os.O_RDWR)
        var = bytearray(160)
        fcntl.ioctl(self._fd, FBIOGET_VSCREENINFO, var)
        xres, yres, _, _, _, _, bpp = struct.unpack_from("7I", var, 0)
        red_off = struct.unpack_from("I", var, 32)[0]
        fix = bytearray(80)
        fcntl.ioctl(self._fd, FBIOGET_FSCREENINFO, fix)
        line = struct.unpack_from("I", fix, 48)[0]
        self.size, self.bpp, self.stride = (xres, yres), bpp, line
        self._mem = mmap.mmap(self._fd, line * yres, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        if bpp == 32:
            # rows are `line` bytes apart, so the shared surface is line/4 pixels wide (padding included)
            fmt = "BGRA" if red_off == 16 else "RGBA"
            self._fb = pygame.image.frombuffer(self._mem, (line // 4, yres), fmt)
            self._conv = None
        elif bpp == 16:
            self._fb = None
            self._conv = pygame.Surface((line // 2, yres), 0, 16, (0xF800, 0x07E0, 0x001F, 0))
        else:
            raise OSError("unsupported framebuffer depth: %d bits" % bpp)

    def _take_console(self):
        """Stop the text console from drawing over us or reading the keyboard while we run."""
        try:
            self._tty = os.open("/dev/tty0", os.O_RDWR | os.O_NOCTTY)
            fcntl.ioctl(self._tty, KDSETMODE, KD_GRAPHICS)
            buf = array.array("i", [0])
            fcntl.ioctl(self._tty, KDGKBMODE, buf)
            self._kbmode = buf[0]
            fcntl.ioctl(self._tty, KDSKBMODE, K_OFF)   # keys reach us via evdev only
            fcntl.ioctl(self._tty, VT_LOCKSWITCH, 0)  # Alt+F2 etc. can't switch away mid-frame
        except OSError:
            pass

    def release_console(self):
        """Give the screen and keyboard back to the text console (also done by close())."""
        if self._tty is None:
            return
        for req, arg in ((VT_UNLOCKSWITCH, 0), (KDSKBMODE, self._kbmode if self._kbmode is not None else 3),
                         (KDSETMODE, KD_TEXT)):
            try:
                fcntl.ioctl(self._tty, req, arg)
            except OSError:
                pass
        os.close(self._tty)
        self._tty = None

    def flip(self, rects=None):
        """Show what has been drawn on `surface`. With `rects`, only those areas are copied to the
        screen (much cheaper when little changed, e.g. the mouse pointer moving)."""
        if self.headless:
            if self.shots:
                os.makedirs(self.shots, exist_ok=True)
                pygame.image.save(self.surface, os.path.join(self.shots, "frame-%05d.png" % self._frame))
            self._frame += 1
            return
        if self._fb is not None:
            if rects:
                bounds = self.surface.get_rect()
                for r in rects:
                    r = pygame.Rect(r).clip(bounds)
                    if r.w and r.h:
                        self._fb.blit(self.surface, r, r)
            else:
                self._fb.blit(self.surface, (0, 0))
        else:
            self._conv.blit(self.surface, (0, 0))
            self._mem[:] = self._conv.get_buffer().raw

    def save(self, path):
        """Write the current frame to a PNG (works on the real screen and headless)."""
        pygame.image.save(self.surface, path)

    def close(self):
        self.release_console()
        try:
            if not self.headless:
                self._fb = None
                self._mem.close()
                os.close(self._fd)
        except Exception:
            pass
        pygame.display.quit()


def available():
    """True when a graphical screen can be used (a framebuffer exists, or headless mode)."""
    if os.environ.get("AIOS_HEADLESS"):
        return True
    path = os.environ.get("AIOS_FB", "/dev/fb0")
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        return False
    try:
        var = bytearray(160)
        fcntl.ioctl(fd, FBIOGET_VSCREENINFO, var)
        xres, yres, _, _, _, _, bpp = struct.unpack_from("7I", var, 0)
        return xres >= 640 and yres >= 480 and bpp in (16, 32)
    except OSError:
        return False
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------- input
class Input:
    """Keyboard and mouse from /dev/input/event*.

    poll(timeout) returns a list of Event. pressed(name) tells whether a key is held (games).
    mouse_pos is the pointer position in screen pixels; draw it with theme.draw_pointer().
    """

    def __init__(self, size):
        self.size = size
        self.mouse_pos = [size[0] // 2, size[1] // 2]
        self.mouse_seen = False          # True once a mouse moved: show the pointer only then
        self._devs = {}                  # path -> fd
        self._abs = {}                   # fd -> {axis: (min, max)}
        self._held = set()
        self._caps = False
        self._queue = []
        self._last_scan = 0.0
        self._pending_abs = {}
        self._scan()

    def _scan(self):
        self._last_scan = time.monotonic()
        if os.environ.get("AIOS_HEADLESS"):
            return
        for path in glob.glob("/dev/input/event*"):
            if path in self._devs:
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self._devs[path] = fd
            axes = {}
            for axis in (ABS_X, ABS_Y):
                info = bytearray(24)
                try:
                    fcntl.ioctl(fd, EVIOCGABS(axis), info)
                    _, lo, hi = struct.unpack_from("3i", info, 0)
                    if hi > lo:
                        axes[axis] = (lo, hi)
                except OSError:
                    pass
            self._abs[fd] = axes
        for path, fd in list(self._devs.items()):
            if not os.path.exists(path):
                self._drop(path)

    def _drop(self, path):
        fd = self._devs.pop(path, None)
        if fd is not None:
            self._abs.pop(fd, None)
            try:
                os.close(fd)
            except OSError:
                pass

    def mods(self):
        m = set()
        if self._held & {"lshift", "rshift"}:
            m.add("shift")
        if self._held & {"lctrl", "rctrl"}:
            m.add("ctrl")
        if self._held & {"lalt", "ralt"}:
            m.add("alt")
        return m

    def pressed(self, name):
        """Is this key held down right now? (e.g. 'left', 'space', 'a')"""
        return name in self._held

    def inject(self, ev):
        """Queue an Event as if it came from a device (tests and headless runs)."""
        if ev.type == "key":
            (self._held.add if ev.down else self._held.discard)(ev.key)
        elif ev.type in ("mouse_move", "mouse_button"):
            self.mouse_pos = list(ev.pos)
            self.mouse_seen = True
        self._queue.append(ev)

    def poll(self, timeout=0.0):
        """Events that arrived, waiting up to `timeout` seconds for the first one."""
        if time.monotonic() - self._last_scan > 2.0:
            self._scan()                    # keyboards/mice plugged in later
        out, self._queue = self._queue, []
        if out or not self._devs:
            if not out and timeout:
                time.sleep(timeout)
            return out
        try:
            ready, _, _ = select.select(list(self._devs.values()), [], [], timeout)
        except (OSError, ValueError):
            self._scan()
            return out
        for fd in ready:
            try:
                data = os.read(fd, EVENT.size * 64)
            except OSError as e:
                if e.errno == errno.ENODEV:
                    for p, f in list(self._devs.items()):
                        if f == fd:
                            self._drop(p)
                continue
            for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _, _, typ, code, value = EVENT.unpack_from(data, i)
                self._handle(fd, typ, code, value, out)
        return out

    def _handle(self, fd, typ, code, value, out):
        w, h = self.size
        if typ == EV_KEY:
            if code in (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_TOUCH):
                if value == 2:
                    return
                btn = {BTN_LEFT: 1, BTN_TOUCH: 1, BTN_MIDDLE: 2, BTN_RIGHT: 3}[code]
                out.append(Event("mouse_button", pos=tuple(self.mouse_pos), button=btn, down=bool(value)))
                return
            info = KEYS.get(code)
            if not info:
                return
            name, lo, hi = info
            down, repeat = value != 0, value == 2
            if down:
                self._held.add(name)
            else:
                self._held.discard(name)
            if name == "capslock" and value == 1:
                self._caps = not self._caps
            mods = self.mods()
            char = ""
            if down and "ctrl" not in mods and "alt" not in mods:
                shifted = "shift" in mods
                if lo.isalpha() and self._caps:
                    shifted = not shifted
                char = hi if shifted else lo
            out.append(Event("key", key=name, down=down, repeat=repeat, char=char, mods=mods))
        elif typ == EV_REL:
            if code in (REL_X, REL_Y):
                i = 0 if code == REL_X else 1
                self.mouse_pos[i] = max(0, min((w, h)[i] - 1, self.mouse_pos[i] + int(value * 1.4)))
                self.mouse_seen = True
                out.append(Event("mouse_move", pos=tuple(self.mouse_pos)))
            elif code == REL_WHEEL:
                out.append(Event("wheel", pos=tuple(self.mouse_pos), dy=value))
        elif typ == EV_ABS and code in (ABS_X, ABS_Y):
            rng = self._abs.get(fd, {}).get(code)
            if rng:
                lo, hi = rng
                i = 0 if code == ABS_X else 1
                self.mouse_pos[i] = int((value - lo) * ((w, h)[i] - 1) / (hi - lo))
                self.mouse_seen = True
                out.append(Event("mouse_move", pos=tuple(self.mouse_pos)))

    def close(self):
        for p in list(self._devs):
            self._drop(p)
