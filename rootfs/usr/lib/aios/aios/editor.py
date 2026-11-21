"""A small code editor for the graphical chat: edit app files yourself.

TextEdit holds the text and does the editing (typing, selection, clipboard, undo); draw() paints
it with line numbers and light syntax colours. The chat wraps it in a window (EditorDialog).
Keys: arrows, Ctrl+arrows (by word), Home/End, PageUp/PageDown, Ctrl+Home/End, Shift+any of
them to select, Ctrl+A/C/X/V, Ctrl+Z undo, Ctrl+Y or Ctrl+Shift+Z redo, Tab indents, Enter keeps
the indentation. handle_key() returns 'save' for Ctrl+S and 'run' for F5; the window acts on those.
"""
import re, time

import pygame

from aios import theme as T

CLIPBOARD = [""]                 # shared by every editor window (and kept between them)
TAB = "    "

KEYWORDS = {
    "c": set("auto break case char const continue default do double else enum extern float for goto if inline int "
             "long register return short signed sizeof static struct switch typedef union unsigned void volatile while "
             "bool true false NULL include define ifdef ifndef endif".split()),
    "py": set("and as assert async await break class continue def del elif else except False finally for from global "
              "if import in is lambda None nonlocal not or pass raise return True try while with yield print self".split()),
    "sh": set("if then else elif fi for while until do done case esac in function return local export echo read "
              "exit set shift test break continue".split()),
}
TOKEN = re.compile(r"""(?P<com>//.*|\#.*)|(?P<str>"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?)|(?P<num>\b\d[\d.xXa-fA-F]*\b)|(?P<word>[A-Za-z_]\w*)|(?P<other>.)""")
COLOURS = {"com": (110, 118, 140), "str": (152, 214, 152), "num": (247, 178, 103), "kw": (232, 121, 249),
           "text": (220, 223, 234)}


def lang_of(name):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return {"c": "c", "h": "c", "py": "py", "sh": "sh"}.get(ext, "")


class TextEdit:
    def __init__(self, text="", lang=""):
        self.lines = text.replace("\r\n", "\n").replace("\t", TAB).split("\n")
        self.lang = lang
        self.cy = self.cx = 0
        self.anchor = None           # where the selection started, (line, col), or None
        self.top = 0                 # first line shown
        self.left = 0                # first column shown (long lines scroll sideways)
        self.version = 0
        self.undo, self.redo = [], []
        self._last_kind, self._last_time = None, 0.0
        self._cache = {}
        self._saved = self.text()     # what the file holds: "modified" means the text differs from it

    # ------------------------------------------------------------------ text and state
    def text(self):
        return "\n".join(self.lines)

    @property
    def modified(self):
        """Does the text differ from the saved file? (Undoing every edit makes it False again.)"""
        return self.text() != self._saved

    def mark_saved(self):
        self._saved = self.text()

    def _snapshot(self, kind):
        """Remember the state before an edit; typing in a row becomes one undo step."""
        now = time.monotonic()
        if kind == "type" and self._last_kind == "type" and now - self._last_time < 1.5:
            self._last_time = now
            return
        self.undo.append((list(self.lines), self.cy, self.cx))
        self.undo = self.undo[-300:]
        self.redo.clear()
        self._last_kind, self._last_time = kind, now

    def _changed(self):
        self.version += 1

    # ------------------------------------------------------------------ selection
    def has_sel(self):
        return self.anchor is not None and self.anchor != (self.cy, self.cx)

    def sel_range(self):
        a, b = self.anchor, (self.cy, self.cx)
        return (a, b) if a <= b else (b, a)

    def selected(self):
        if not self.has_sel():
            return ""
        (y1, x1), (y2, x2) = self.sel_range()
        if y1 == y2:
            return self.lines[y1][x1:x2]
        return "\n".join([self.lines[y1][x1:]] + self.lines[y1 + 1:y2] + [self.lines[y2][:x2]])

    def _delete_sel(self):
        (y1, x1), (y2, x2) = self.sel_range()
        self.lines[y1:y2 + 1] = [self.lines[y1][:x1] + self.lines[y2][x2:]]
        self.cy, self.cx = y1, x1
        self.anchor = None

    def select_all(self):
        self.anchor = (0, 0)
        self.cy, self.cx = len(self.lines) - 1, len(self.lines[-1])

    # ------------------------------------------------------------------ editing
    def insert(self, s, kind="type"):
        if not s:
            return
        self._snapshot(kind if not self.has_sel() else "edit")
        if self.has_sel():
            self._delete_sel()
        s = s.replace("\r\n", "\n").replace("\t", TAB)
        line = self.lines[self.cy]
        before, after = line[:self.cx], line[self.cx:]
        parts = s.split("\n")
        if len(parts) == 1:
            self.lines[self.cy] = before + s + after
            self.cx += len(s)
        else:
            new = [before + parts[0]] + parts[1:-1] + [parts[-1] + after]
            self.lines[self.cy:self.cy + 1] = new
            self.cy += len(parts) - 1
            self.cx = len(parts[-1])
        self.anchor = None
        self._changed()

    def newline(self):
        indent = re.match(r"[ ]*", self.lines[self.cy]).group(0)
        if self.lines[self.cy][:self.cx].rstrip().endswith(("{", ":")):   # opening a block: one level deeper
            indent += TAB
        self.insert("\n" + indent, kind="edit")

    def backspace(self):
        if self.has_sel():
            self._snapshot("edit"); self._delete_sel(); self._changed(); return
        if self.cx == 0 and self.cy == 0:
            return
        self._snapshot("delete")
        if self.cx == 0:
            prev = self.lines[self.cy - 1]
            self.lines[self.cy - 1:self.cy + 1] = [prev + self.lines[self.cy]]
            self.cy -= 1
            self.cx = len(prev)
        else:
            line = self.lines[self.cy]
            n = 1
            if line[:self.cx].endswith(TAB) and not line[:self.cx].strip():   # remove a whole indent level
                n = len(TAB)
            self.lines[self.cy] = line[:self.cx - n] + line[self.cx:]
            self.cx -= n
        self._changed()

    def delete(self):
        if self.has_sel():
            self._snapshot("edit"); self._delete_sel(); self._changed(); return
        line = self.lines[self.cy]
        if self.cx < len(line):
            self._snapshot("delete")
            self.lines[self.cy] = line[:self.cx] + line[self.cx + 1:]
        elif self.cy < len(self.lines) - 1:
            self._snapshot("delete")
            self.lines[self.cy:self.cy + 2] = [line + self.lines[self.cy + 1]]
        else:
            return
        self._changed()

    def indent(self, back=False):
        if self.has_sel():                       # (un)indent every selected line
            self._snapshot("edit")
            (y1, _), (y2, x2) = self.sel_range()
            if x2 == 0 and y2 > y1:
                y2 -= 1
            for y in range(y1, y2 + 1):
                if back:
                    self.lines[y] = self.lines[y][len(re.match(r"[ ]{0,4}", self.lines[y]).group(0)):]
                else:
                    self.lines[y] = TAB + self.lines[y]
            self.anchor = (y1, 0)
            self.cy, self.cx = y2, len(self.lines[y2])
            self._changed()
        elif back:
            line = self.lines[self.cy]
            n = len(re.match(r"[ ]{0,4}", line).group(0))
            if n:
                self._snapshot("edit")
                self.lines[self.cy] = line[n:]
                self.cx = max(0, self.cx - n)
                self._changed()
        else:
            self.insert(" " * (len(TAB) - self.cx % len(TAB)), kind="edit")

    def do_undo(self, redo=False):
        src, dst = (self.redo, self.undo) if redo else (self.undo, self.redo)
        if not src:
            return
        dst.append((list(self.lines), self.cy, self.cx))
        self.lines, self.cy, self.cx = src.pop()
        self.anchor = None
        self._last_kind = None
        self._changed()

    # ------------------------------------------------------------------ moving
    def _move(self, y, x, select):
        if select:
            if self.anchor is None:
                self.anchor = (self.cy, self.cx)
        else:
            self.anchor = None
        self.cy = max(0, min(len(self.lines) - 1, y))
        self.cx = max(0, min(len(self.lines[self.cy]), x))

    def _word(self, step):
        y, x = self.cy, self.cx
        line = self.lines[y]
        if step < 0:
            if x == 0:
                return (y - 1, len(self.lines[y - 1])) if y > 0 else (y, x)
            x -= 1
            while x > 0 and not line[x - 1].isalnum() and line[x - 1] != "_":
                x -= 1
            while x > 0 and (line[x - 1].isalnum() or line[x - 1] == "_"):
                x -= 1
        else:
            if x >= len(line):
                return (y + 1, 0) if y < len(self.lines) - 1 else (y, x)
            while x < len(line) and not line[x].isalnum() and line[x] != "_":
                x += 1
            while x < len(line) and (line[x].isalnum() or line[x] == "_"):
                x += 1
        return y, x

    def handle_key(self, ev, page=20):
        """Apply a key press. Returns 'save', 'run' or None."""
        k, mods = ev.key, ev.mods
        ctrl, shift = "ctrl" in mods, "shift" in mods
        if ctrl:
            if k == "s":
                return "save"
            if k == "a":
                self.select_all()
            elif k in ("c", "x"):
                if self.has_sel():
                    CLIPBOARD[0] = self.selected()
                    if k == "x":
                        self._snapshot("edit"); self._delete_sel(); self._changed()
                else:                                     # no selection: the whole line
                    CLIPBOARD[0] = self.lines[self.cy] + "\n"
                    if k == "x":
                        self._snapshot("edit")
                        if len(self.lines) > 1:
                            del self.lines[self.cy]
                            self.cy = min(self.cy, len(self.lines) - 1)
                        else:
                            self.lines[0] = ""
                        self.cx = 0
                        self._changed()
            elif k == "v":
                self.insert(CLIPBOARD[0], kind="edit")
            elif k == "z":
                self.do_undo(redo=shift)
            elif k == "y":
                self.do_undo(redo=True)
            elif k in ("left", "right"):
                self._move(*self._word(-1 if k == "left" else 1), shift)
            elif k == "home":
                self._move(0, 0, shift)
            elif k == "end":
                self._move(len(self.lines) - 1, len(self.lines[-1]), shift)
            elif k == "d":                                # duplicate the line
                self._snapshot("edit")
                self.lines.insert(self.cy + 1, self.lines[self.cy])
                self.cy += 1
                self._changed()
            return None
        if k == "f5":
            return "run"
        if k == "left":
            if self.has_sel() and not shift:
                (y, x), _ = self.sel_range(); self._move(y, x, False)
            elif self.cx == 0 and self.cy > 0:
                self._move(self.cy - 1, len(self.lines[self.cy - 1]), shift)
            else:
                self._move(self.cy, self.cx - 1, shift)
        elif k == "right":
            if self.has_sel() and not shift:
                _, (y, x) = self.sel_range(); self._move(y, x, False)
            elif self.cx >= len(self.lines[self.cy]) and self.cy < len(self.lines) - 1:
                self._move(self.cy + 1, 0, shift)
            else:
                self._move(self.cy, self.cx + 1, shift)
        elif k in ("up", "down", "pageup", "pagedown"):
            d = {"up": -1, "down": 1, "pageup": -page, "pagedown": page}[k]
            self._move(self.cy + d, self.cx, shift)
            if k in ("pageup", "pagedown"):
                self.top = max(0, self.top + d)
        elif k == "home":
            first = len(self.lines[self.cy]) - len(self.lines[self.cy].lstrip(" "))
            self._move(self.cy, 0 if self.cx == first else first, shift)   # smart Home
        elif k == "end":
            self._move(self.cy, len(self.lines[self.cy]), shift)
        elif k == "backspace":
            self.backspace()
        elif k == "delete":
            self.delete()
        elif k == "return":
            self.newline()
        elif k == "tab":
            self.indent(back=shift)
        elif ev.char and ev.char not in "\t\n":
            self.insert(ev.char)
        return None

    # ------------------------------------------------------------------ drawing and the mouse
    def _metrics(self):
        f = T.font("mono", 14)
        return f, f.size("M")[0], f.get_linesize()

    def _layout(self, rect):
        f, cw, lh = self._metrics()
        gutter = f.size("99999")[0] + T.px(16)
        rows = max(1, (rect.h - T.px(12)) // lh)
        cols = max(10, (rect.w - gutter - T.px(14)) // cw)
        return f, cw, lh, gutter, rows, cols

    def page(self, rect):
        return self._layout(rect)[4]

    def cell_at(self, rect, pos):
        """The (line, column) under a screen position inside the text area."""
        f, cw, lh, gutter, rows, cols = self._layout(rect)
        y = self.top + max(0, (pos[1] - rect.y - T.px(6)) // lh)
        y = max(0, min(len(self.lines) - 1, y))
        x = self.left + max(0, round((pos[0] - rect.x - gutter) / cw))
        return y, min(len(self.lines[y]), x)

    def click(self, rect, pos, extend=False):
        y, x = self.cell_at(rect, pos)
        self._move(y, x, extend)

    def drag(self, rect, pos):
        y, x = self.cell_at(rect, pos)
        if self.anchor is None:
            self.anchor = (self.cy, self.cx)
        self.cy, self.cx = y, x

    def scroll(self, rect, lines):
        rows = self._layout(rect)[4]
        self.top = max(0, min(max(0, len(self.lines) - rows // 2), self.top + lines))

    def _render(self, line, f):
        key = (line, self.lang)
        img = self._cache.get(key)
        if img is not None:
            return img
        if len(self._cache) > 600:
            self._cache.clear()
        shown = line[:2000]
        if not self.lang or not shown.strip():
            img = f.render(shown or " ", True, COLOURS["text"])
        else:
            kws = KEYWORDS.get(self.lang, ())
            parts = []
            for m in TOKEN.finditer(shown):
                kind = m.lastgroup
                tok = m.group(0)
                if kind == "com" and ((self.lang == "c" and tok.startswith("#")) or (self.lang != "c" and tok.startswith("//"))):
                    kind = "kw" if self.lang == "c" else "text"        # C preprocessor lines / '//' outside C
                if kind == "word":
                    kind = "kw" if tok in kws else "text"
                elif kind == "other":
                    kind = "text"
                if parts and parts[-1][0] == kind:
                    parts[-1][1] += tok
                else:
                    parts.append([kind, tok])
            w = f.size(shown)[0]
            img = pygame.Surface((max(1, w), f.get_linesize()), pygame.SRCALPHA)
            x = 0
            for kind, tok in parts:
                seg = f.render(tok, True, COLOURS.get(kind, COLOURS["text"]))
                img.blit(seg, (x, 0))
                x += f.size(tok)[0]
        self._cache[key] = img
        return img

    def draw(self, surface, rect, focused=True):
        f, cw, lh, gutter, rows, cols = self._layout(rect)
        # keep the cursor in view
        if self.cy < self.top:
            self.top = self.cy
        elif self.cy >= self.top + rows:
            self.top = self.cy - rows + 1
        if self.cx < self.left:
            self.left = max(0, self.cx - 4)
        elif self.cx >= self.left + cols:
            self.left = self.cx - cols + 4
        T.panel(surface, rect, T.C["term_bg"], 10, T.C["accent"] if focused else T.C["line"])
        clip = surface.get_clip()
        surface.set_clip(rect.inflate(-T.px(4), -T.px(4)))
        pygame.draw.rect(surface, (17, 19, 27), (rect.x + T.px(2), rect.y + T.px(2), gutter - T.px(6), rect.h - T.px(4)),
                         border_top_left_radius=T.px(9), border_bottom_left_radius=T.px(9))
        sel = self.sel_range() if self.has_sel() else None
        tx = rect.x + gutter
        for i in range(rows):
            y = self.top + i
            if y >= len(self.lines):
                break
            py = rect.y + T.px(6) + i * lh
            line = self.lines[y]
            if y == self.cy and not sel:
                pygame.draw.rect(surface, (24, 27, 38), (tx - T.px(6), py, rect.w - gutter, lh))
            if sel and sel[0][0] <= y <= sel[1][0]:              # selection highlight
                x1 = sel[0][1] if y == sel[0][0] else 0
                x2 = sel[1][1] if y == sel[1][0] else len(line) + 1
                a, b = max(x1, self.left), max(x2, self.left)
                if b > a:
                    pygame.draw.rect(surface, (74, 46, 110), (tx + (a - self.left) * cw, py, (b - a) * cw, lh))
            num = f.render(str(y + 1).rjust(5), True, T.C["text2"] if y == self.cy else T.C["muted"])
            surface.blit(num, (rect.x + T.px(4), py))
            if line:
                img = self._render(line, f)
                surface.blit(img, (tx, py), area=pygame.Rect(self.left * cw, 0, cols * cw + cw, lh))
        if focused and int(time.monotonic() * 2) % 2 == 0:     # blinking cursor
            cyp = self.cy - self.top
            if 0 <= cyp < rows:
                cxp = tx + (self.cx - self.left) * cw
                pygame.draw.rect(surface, T.C["accent"], (cxp, rect.y + T.px(6) + cyp * lh, max(2, T.px(2)), lh))
        surface.set_clip(clip)
        if len(self.lines) > rows:                              # scroll bar
            frac = self.top / max(1, len(self.lines) - rows)
            th = max(T.px(30), rect.h * rows // len(self.lines))
            pygame.draw.rect(surface, T.C["line"], (rect.right - T.px(8), rect.y + int((rect.h - th) * frac), T.px(4), th),
                             border_radius=T.px(2))
