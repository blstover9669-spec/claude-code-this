"""Building blocks for the graphical chat: a text box, the message renderer (light markdown and
file cards) and small drawing helpers. All sizes are design pixels passed through theme.px()."""
import os, re, time

import pygame

from aios import core, theme as T

KIND_COLOUR = {"c": (34, 211, 238), "py": (251, 191, 36), "sh": (52, 211, 153), "exe": (217, 70, 239),
               "iso": (168, 85, 247), "text": (160, 167, 186)}
KIND_ICON = {"c": "code", "py": "python", "sh": "shell", "exe": "play", "iso": "disc", "text": "file"}
KIND_LABEL = {"c": "C source", "py": "Python script", "sh": "Shell script", "exe": "Program",
              "iso": "Bootable disc image", "text": "Text file"}


def human_size(n):
    if n < 1024:
        return "%d bytes" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%.1f MB" % (n / 1048576.0)


def ellipsize(s, fnt, width):
    """Cut text to fit `width` pixels, ending with an ellipsis when it had to be cut."""
    if fnt.size(s)[0] <= width:
        return s
    while s and fnt.size(s + "…")[0] > width:
        s = s[:-1]
    return s + "…"


def kind_tile(surface, rect, kind, size=18):
    """A rounded, tinted square with the app type's icon in it."""
    rect = pygame.Rect(rect)
    col = KIND_COLOUR.get(kind, KIND_COLOUR["text"])
    tile = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(tile, col + (38,), tile.get_rect(), border_radius=T.px(8))
    surface.blit(tile, rect)
    isz = T.px(size)
    T.icon(surface, KIND_ICON.get(kind, "file"), (rect.centerx - isz // 2, rect.centery - isz // 2, isz, isz), col)


def avatar(surface, center, radius):
    """The AI's round avatar: AI OS's magenta-violet gradient with a sparkle."""
    r = pygame.Rect(0, 0, radius * 2, radius * 2)
    r.center = center
    T.gradient_rect(surface, r, T.C["accent"], T.C["accent2"], radius=radius / max(T.px(1), 1))
    s = int(radius * 1.1)
    T.icon(surface, "sparkle", (center[0] - s // 2, center[1] - s // 2, s, s), (255, 255, 255))


def logo(surface, rect):
    """AI OS's mark: a rounded gradient square with a sparkle."""
    rect = pygame.Rect(rect)
    T.gradient_rect(surface, rect, T.C["accent"], T.C["accent2"], radius=10)
    s = int(rect.w * 0.62)
    T.icon(surface, "sparkle", (rect.centerx - s // 2, rect.centery - s // 2, s, s), (255, 255, 255))


def pill(surface, pos, label, colour, icon_name=None, size=12, anchor="midtop", bg_alpha=36):
    """A small rounded label (status chips). Returns its Rect."""
    f = T.font("medium", size)
    tw, th = f.size(label)
    isz = T.px(size + 2) if icon_name else 0
    w = tw + T.px(20) + (isz + T.px(6) if icon_name else 0)
    h = th + T.px(10)
    r = pygame.Rect(0, 0, w, h)
    setattr(r, anchor, pos)
    chip = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(chip, colour + (bg_alpha,), chip.get_rect(), border_radius=h // 2)
    pygame.draw.rect(chip, colour + (90,), chip.get_rect(), width=1, border_radius=h // 2)
    surface.blit(chip, r)
    x = r.x + T.px(10)
    if icon_name:
        T.icon(surface, icon_name, (x, r.centery - isz // 2, isz, isz), colour)
        x += isz + T.px(6)
    surface.blit(f.render(label, True, colour if colour != T.C["text2"] else T.C["text2"]), (x, r.centery - th // 2))
    return r


def small_button(surface, rect, label, kind="normal", hover=False, icon_name=None):
    """A compact button for cards (height ~30 design px)."""
    rect = pygame.Rect(rect)
    if kind == "primary":
        T.gradient_rect(surface, rect, T.C["accent"], T.C["accent2"], radius=8)
        if hover:
            pygame.draw.rect(surface, (255, 255, 255), rect, width=1, border_radius=T.px(8))
        fg = (255, 255, 255)
    else:
        bg = T.C["panel2"] if not hover else tuple(min(255, c + 16) for c in T.C["panel2"])
        T.panel(surface, rect, bg, radius=8, border=T.C["line"])
        fg = T.C["err"] if kind == "danger" else T.C["text"]
    f = T.font("semibold", 13)
    img = f.render(label, True, fg)
    isz = T.px(14) if icon_name else 0
    total = img.get_width() + (isz + T.px(6) if icon_name else 0)
    x = rect.centerx - total // 2
    if icon_name:
        T.icon(surface, icon_name, (x, rect.centery - isz // 2, isz, isz), fg)
        x += isz + T.px(6)
    surface.blit(img, (x, rect.centery - img.get_height() // 2))
    return rect


# ---------------------------------------------------------------------------- text box
def wrap_ranges(text, fnt, width):
    """Visual lines of `text` as (start, end) index ranges, word-wrapped to `width` pixels."""
    out = []
    pos = 0
    for para in text.split("\n"):
        start = pos
        end_para = pos + len(para)
        if not para:
            out.append((start, start))
        while start < end_para:
            end = end_para
            if fnt.size(text[start:end])[0] > width:
                lo, hi = start + 1, end_para          # longest prefix that fits
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if fnt.size(text[start:mid])[0] <= width:
                        lo = mid
                    else:
                        hi = mid - 1
                end = max(lo, start + 1)
                sp = text.rfind(" ", start, end)
                if sp > start and end < end_para:
                    end = sp + 1
            out.append((start, end))
            start = end
        pos = end_para + 1
    return out or [(0, 0)]


class TextBox:
    """An editable text field: one line (or masked, for passwords) or several lines."""

    def __init__(self, placeholder="", multiline=False, mask=False, size=15):
        self.text = ""
        self.cursor = 0
        self.placeholder = placeholder
        self.multiline = multiline
        self.mask = mask
        self.size = size
        self.history = []
        self.hist_i = None
        self._blink = time.monotonic()

    def set(self, s):
        self.text = s
        self.cursor = len(s)
        self._blink = time.monotonic()

    def shown(self):
        return "•" * len(self.text) if self.mask else self.text

    def handle(self, ev):
        """Edit on a key event. Returns 'submit' for Enter (without Shift in multi-line), True when
        the text or cursor changed, else False."""
        if ev.type != "key" or not ev.down:
            return False
        k, mods, t, c = ev.key, ev.mods, self.text, self.cursor
        self._blink = time.monotonic()
        if k == "return":
            if self.multiline and "shift" in mods:
                self.text = t[:c] + "\n" + t[c:]
                self.cursor = c + 1
                return True
            return "submit"
        if k == "backspace":
            if c > 0:
                if "ctrl" in mods:       # delete the previous word
                    j = c
                    while j > 0 and t[j - 1] == " ":
                        j -= 1
                    while j > 0 and t[j - 1] not in " \n":
                        j -= 1
                    self.text, self.cursor = t[:j] + t[c:], j
                else:
                    self.text, self.cursor = t[:c - 1] + t[c:], c - 1
            return True
        if k == "delete":
            self.text = t[:c] + t[c + 1:]
            return True
        if k == "left":
            self.cursor = max(0, c - 1)
            return True
        if k == "right":
            self.cursor = min(len(t), c + 1)
            return True
        if k == "home":
            self.cursor = t.rfind("\n", 0, c) + 1 if self.multiline else 0
            return True
        if k == "end":
            j = t.find("\n", c)
            self.cursor = (j if j >= 0 else len(t)) if self.multiline else len(t)
            return True
        if k in ("up", "down") and self.multiline:
            line_start = t.rfind("\n", 0, c) + 1
            col = c - line_start
            if k == "up" and line_start > 0:
                prev_start = t.rfind("\n", 0, line_start - 1) + 1
                self.cursor = min(prev_start + col, line_start - 1)
                return True
            if k == "down":
                j = t.find("\n", c)
                if j >= 0:
                    nxt_end = t.find("\n", j + 1)
                    nxt_end = len(t) if nxt_end < 0 else nxt_end
                    self.cursor = min(j + 1 + col, nxt_end)
                    return True
            return self._history(k)
        if "ctrl" in mods and k == "a":
            self.cursor = 0
            return True
        if "ctrl" in mods and k == "e":
            self.cursor = len(t)
            return True
        if "ctrl" in mods and k == "u":
            self.text, self.cursor = t[c:], 0
            return True
        if ev.char and ev.char not in "\n\r" and (ev.char != "\t" or self.multiline):
            ch = "    " if ev.char == "\t" else ev.char
            self.text = t[:c] + ch + t[c:]
            self.cursor = c + len(ch)
            self.hist_i = None
            return True
        return False

    def _history(self, k):
        """Up/Down on the first/last line walks through what was sent before."""
        if not self.history:
            return False
        if self.hist_i is None:
            if k == "down":
                return False
            self.hist_i = len(self.history)
        self.hist_i += -1 if k == "up" else 1
        if self.hist_i < 0:
            self.hist_i = 0
        if self.hist_i >= len(self.history):
            self.hist_i = None
            self.set("")
        else:
            self.set(self.history[self.hist_i])
        return True

    def remember(self, s):
        if s and (not self.history or self.history[-1] != s):
            self.history.append(s)
        self.hist_i = None

    def layout(self, width):
        f = T.font("mono" if False else "regular", self.size)
        return f, wrap_ranges(self.shown(), f, width)

    def height(self, width, max_lines=6):
        f, lines = self.layout(width)
        return min(len(lines), max_lines) * f.get_linesize()

    def draw(self, surface, rect, focused=True, colour=None, max_lines=6):
        """Draw the text inside `rect`, scrolled so the cursor stays visible."""
        rect = pygame.Rect(rect)
        f, lines = self.layout(rect.w)
        lh = f.get_linesize()
        shown = self.shown()
        # which visual line holds the cursor
        cl = 0
        for i, (a, b) in enumerate(lines):
            if a <= self.cursor <= b:
                cl = i
                if self.cursor < b or i == len(lines) - 1:
                    break
        first = max(0, cl - max_lines + 1)
        clip = surface.get_clip()
        surface.set_clip(rect.clip(clip) if clip else rect)
        if not self.text and self.placeholder:
            surface.blit(f.render(self.placeholder, True, T.C["muted"]), (rect.x, rect.y))
        for i, (a, b) in enumerate(lines[first:first + max_lines]):
            seg = shown[a:b].rstrip("\n")
            if seg:
                surface.blit(f.render(seg, True, colour or T.C["text"]), (rect.x, rect.y + i * lh))
        if focused and int((time.monotonic() - self._blink) * 1.8) % 2 == 0:
            a, b = lines[cl]
            x = rect.x + f.size(shown[a:self.cursor])[0]
            y = rect.y + (cl - first) * lh
            pygame.draw.rect(surface, T.C["accent"], (x, y + T.px(2), max(1, T.px(2)), lh - T.px(4)))
        surface.set_clip(clip)

    def click(self, rect, pos):
        """Move the cursor to where the text was clicked."""
        rect = pygame.Rect(rect)
        f, lines = self.layout(rect.w)
        lh = f.get_linesize()
        i = max(0, min(len(lines) - 1, (pos[1] - rect.y) // lh))
        a, b = lines[i]
        shown = self.shown()
        best = a
        for j in range(a, b + 1):
            if f.size(shown[a:j])[0] <= pos[0] - rect.x:
                best = j
        self.cursor = best
        self._blink = time.monotonic()


# ---------------------------------------------------------------------------- AI message rendering
FENCE = re.compile(r"```([^\n`]*)\n(.*?)(?:```|\Z)", re.S)
OPEN_FILE = re.compile(r"<<<FILE[ \t]+([^\n]+?)[ \t]*\n(.*)\Z", re.S)
INLINE = re.compile(r"(\*\*[^*\n]+\*\*|`[^`\n]+`)")


def split_blocks(text):
    """An AI reply as blocks: ('text', s), ('code', lang, s), ('file', name, body, complete)."""
    blocks = []
    pos = 0
    for m in core.FILE_RE.finditer(text):
        blocks += _text_and_code(text[pos:m.start()])
        blocks.append(("file", core.safe_name(m.group(1)), core.clean_body(m.group(2)), True))
        pos = m.end()
    rest = text[pos:]
    m = OPEN_FILE.search(rest)            # a file block still being written
    if m:
        blocks += _text_and_code(rest[:m.start()])
        blocks.append(("file", core.safe_name(m.group(1)), m.group(2), False))
    else:
        blocks += _text_and_code(rest)
    return blocks


def _text_and_code(s):
    out = []
    pos = 0
    for m in FENCE.finditer(s):
        if s[pos:m.start()].strip():
            out.append(("text", s[pos:m.start()].strip("\n")))
        out.append(("code", m.group(1).strip(), m.group(2).rstrip("\n")))
        pos = m.end()
    if s[pos:].strip():
        out.append(("text", s[pos:].strip("\n")))
    return out


def _runs(line):
    """Inline styling: [(text, 'plain'|'bold'|'code')]."""
    out = []
    for part in INLINE.split(line):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append((part[2:-2], "bold"))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            out.append((part[1:-1], "code"))
        else:
            out.append((part, "plain"))
    return out


def rich_text(surface, text, x, y, width, colour, size=15, draw=True):
    """Draw light-markdown text (paragraphs, # headings, - lists, **bold**, `code`) wrapped to
    `width`. Returns the height used. With draw=False it only measures."""
    fonts = {"plain": T.font("regular", size), "bold": T.font("semibold", size), "code": T.font("mono", size - 1)}
    lh = fonts["plain"].get_linesize()
    cy = y
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            cy += lh // 2
            continue
        indent = 0
        bullet = None
        size_here, base = size, "plain"
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            line = m.group(2)
            size_here = size + (6 - 2 * min(len(m.group(1)), 3)) + 2
            base = "bold"
        m2 = re.match(r"^(\s*)([-*•]|\d+[.)])\s+(.*)", line)
        if m2 and not m:
            indent = T.px(18) + len(m2.group(1).replace("\t", "  ")) * T.px(6)
            bullet = "•" if not m2.group(2)[0].isdigit() else m2.group(2)
            line = m2.group(3)
        hf = {"plain": T.font("regular", size_here), "bold": T.font("semibold", size_here), "code": fonts["code"]}
        hlh = hf["plain"].get_linesize()
        if bullet and draw:
            surface.blit(fonts["plain"].render(bullet, True, T.C["accent"] if bullet == "•" else colour),
                         (x + indent - T.px(16), cy))
        # word-wrap the styled runs
        words = []
        for txt, style in _runs(line):
            style = "bold" if (base == "bold" and style == "plain") else style
            for i, w in enumerate(re.split(r"( )", txt)):
                if w:
                    words.append((w, style))
        cx = x + indent
        maxw = x + width
        for w, style in words:
            f = hf[style]
            ww = f.size(w)[0]
            if w == " ":
                if cx > x + indent:
                    cx += ww
                continue
            if cx + ww > maxw and cx > x + indent:
                cy += hlh
                cx = x + indent
            if ww > width - indent:            # a very long word: break it
                while w:
                    cut = len(w)
                    while cut > 1 and f.size(w[:cut])[0] > maxw - cx:
                        cut -= 1
                    if draw:
                        surface.blit(f.render(w[:cut], True, colour), (cx, cy))
                    w = w[cut:]
                    if w:
                        cy += hlh
                        cx = x + indent
                    else:
                        cx += f.size(w[:cut])[0]
                continue
            if draw:
                if style == "code":
                    pygame.draw.rect(surface, T.C["panel2"], (cx - T.px(3), cy + T.px(1), ww + T.px(6), hlh - T.px(2)),
                                     border_radius=T.px(4))
                    surface.blit(f.render(w, True, T.C["cyan"]), (cx, cy + (hlh - f.get_linesize()) // 2))
                else:
                    surface.blit(f.render(w, True, colour), (cx, cy))
            cx += ww + (T.px(4) if style == "code" else 0)
        cy += hlh
    return cy - y


def code_block(surface, x, y, width, lang, code, draw=True, max_lines=60):
    """A dark panel with monospaced code. Returns the height used."""
    f = T.font("mono", 13)
    lh = f.get_linesize()
    lines = code.split("\n")
    shown = lines[:max_lines]
    wrapped = []
    for l in shown:
        l = l.replace("\t", "    ")
        while f.size(l)[0] > width - T.px(28) and len(l) > 1:
            cut = len(l)
            while cut > 1 and f.size(l[:cut])[0] > width - T.px(28):
                cut -= 1
            wrapped.append(l[:cut])
            l = l[cut:]
        wrapped.append(l)
    head = T.px(26) if lang else T.px(8)
    h = head + len(wrapped) * lh + T.px(12) + (lh if len(lines) > max_lines else 0)
    if draw:
        T.panel(surface, (x, y, width, h), T.C["term_bg"], radius=10, border=T.C["line"])
        if lang:
            surface.blit(T.font("medium", 11).render(lang, True, T.C["muted"]), (x + T.px(14), y + T.px(7)))
        for i, l in enumerate(wrapped):
            surface.blit(f.render(l, True, (214, 218, 230)), (x + T.px(14), y + head + i * lh))
        if len(lines) > max_lines:
            surface.blit(T.font("regular", 12).render("… %d more lines" % (len(lines) - max_lines), True, T.C["muted"]),
                         (x + T.px(14), y + head + len(wrapped) * lh))
    return h
