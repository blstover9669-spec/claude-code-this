"""AI OS's chat engine, shared by the text chat (/usr/bin/aichat) and the graphical chat (aios.gui).

It talks to the AI service, saves the files the AI writes, finds, builds and runs apps, builds
bootable ISOs and reports on the network. Nothing here prints or draws: each chat shows the
results its own way. No pygame here, so the text chat works even without a screen.
"""
import json, os, re, shutil, subprocess, tempfile, urllib.error, urllib.request

APPS = os.environ.get("AIOS_APPS", "/root/apps")
KEY_FILES = [os.environ.get("AIOS_KEY", "/etc/ai-os/key"), "/root/.ai-key"]
USER_KEY = os.environ.get("AIOS_USER_KEY", "/root/.ai-key")
CC = os.environ.get("AIOS_CC", "tcc")
API = "https://api.groq.com/openai/v1"
MODEL = os.environ.get("AIOS_MODEL", "openai/gpt-oss-120b")
MAX_MSGS = 40

_FILES_AND_RUNNING = """To create or overwrite a file, write a block exactly like this (the user's OS saves it into its apps folder):
<<<FILE name.ext
...full file content...
FILE>>>
Use plain file names (no folders). Always write the complete file. You may create several files in one reply.
Do not wrap the block in markdown code fences.

What can run here (the user types /run name.ext):
- .sh  : busybox sh script (busybox tools only).
- .py  : python3, standard library only (no pip, no extra packages, no tkinter).
- .c   : C compiled with tcc and musl libc into name.exe (tcc -o name.exe name.c -lm), then run. Keep C simple and portable (C99, POSIX, termios ok).
- .exe : on this OS an .exe is a native Linux x86-64 program built from C here. It is NOT Windows: Windows .exe files cannot run. If the user wants an exe, write a .c file and tell them /run name.c (or /build name.c) makes name.exe.
- .iso : bootable disc images, booted in a built-in virtual machine with /run name.iso. To make an ISO, write the files, then tell the user to type: /iso name.iso file1 file2 ... (this builds a bootable copy of AI OS with those files included).
- .txt/.md/.html and others are shown as text.
"""

# The text chat's prompt (unchanged wording: the model's behaviour there is tested).
SYSTEM = ("""You are the AI inside AI OS, a tiny live operating system whose only interface is this chat on a \
Linux text console (about 80x25, ANSI colours ok, no mouse, no GUI/X, no web browser). You help the user with \
anything, and you can create programs and files for them.

""" + _FILES_AND_RUNNING + """Programs are terminal programs. The internet is reachable but only via the python standard library (urllib).
Other user commands: /files, /show, /rm, /send (shows you a file), /build, /iso, /wifi (join Wi-Fi), /new, /model, \
/net, /help. Keep answers concise; plain text \
is best because the console does not render markdown.""")

# The graphical chat's prompt: same rules, but it renders light markdown and runs apps in a window.
SYSTEM_GUI = ("""You are the AI inside AI OS, a tiny live operating system whose only interface is this chat app \
(a graphical chat window with a mouse; there is no web browser, desktop or other apps besides this chat). You help \
the user with anything, and you can create programs and files for them.

""" + _FILES_AND_RUNNING + """Programs are terminal programs: they run in a terminal window inside the chat (about \
100x30 characters, ANSI colours and cursor movement ok, keyboard input works; there is no GUI toolkit for programs). \
The internet is reachable but only via the python standard library (urllib).
The user can also click an app in the sidebar to run it. Other commands: /files, /show, /rm, /send (shows you a \
file), /build, /iso, /wifi, /new, /model, /net, /help. The chat window shows simple markdown (**bold**, `code`, \
``` code blocks). Keep answers concise.""")


# ---------------------------------------------------------------------------- API key
def load_key():
    for f in KEY_FILES:
        try:
            k = open(f).read().strip()
            if k:
                return k
        except OSError:
            pass
    return ""


def save_key(k):
    """Keep a key the user typed in (raises OSError when it can't be written)."""
    os.makedirs(os.path.dirname(USER_KEY), exist_ok=True)
    with open(USER_KEY, "w") as fh:
        fh.write(k + "\n")
    os.chmod(USER_KEY, 0o600)


# ---------------------------------------------------------------------------- AI service
def api_req(path, key, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(API + path, data=data, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "ai-os/1.0"})
    return urllib.request.urlopen(r, timeout=timeout)


def net_error(e):
    """A plain-language message for a failed request to the AI service."""
    if isinstance(e, urllib.error.HTTPError):
        try:
            msg = json.loads(e.read().decode()).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        if e.code == 401:
            return "API key rejected (401). Use /key to enter a new one."
        if e.code == 429:
            return "Rate limited by the AI service (429). Wait a moment and try again."
        return "AI service error %d: %s" % (e.code, msg or e.reason)
    reason = getattr(e, "reason", e)
    return ("No connection to the AI (%s).\nCheck the network cable / VM network, then try again. /net shows status." % reason)


def open_chat(key, model, messages):
    """Start a streamed reply (raises urllib errors when the service can't be reached)."""
    return api_req("/chat/completions", key, {"model": model, "messages": messages, "stream": True}, timeout=90)


def iter_chat(resp, stop=None):
    """Yield the reply's text pieces from open_chat() as they arrive. `stop` (a threading.Event)
    ends it early. Raises RuntimeError when the service reports an error mid-stream."""
    for raw in resp:
        if stop is not None and stop.is_set():
            return
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        d = line[5:].strip()
        if d == "[DONE]":
            return
        try:
            j = json.loads(d)
        except ValueError:
            continue
        if j.get("error"):
            raise RuntimeError(j["error"].get("message", "stream error"))
        for ch in j.get("choices", []):
            t = (ch.get("delta") or {}).get("content")
            if t:
                yield t


def list_models(key):
    return sorted(m["id"] for m in json.load(api_req("/models", key, timeout=20)).get("data", []))


def chat_messages(history, gui=False):
    """The messages to send: the system prompt (with the current apps) and the recent history."""
    return [{"role": "system", "content": (SYSTEM_GUI if gui else SYSTEM) + file_list_note()}] + history[-MAX_MSGS:]


# ---------------------------------------------------------------------------- files the AI writes
FILE_RE = re.compile(r"<<<FILE[ \t]+([^\n]+?)[ \t]*\n(.*?)\n?FILE>>>", re.S)


def safe_name(n):
    n = os.path.basename(n.strip().strip("`'\"").replace("\\", "/"))
    n = re.sub(r"[^A-Za-z0-9._+-]", "_", n).lstrip(".")
    return n[:80]


def clean_body(body):
    """A file block's content without a markdown fence the model may have put inside it."""
    lines = body.split("\n")
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    body = "\n".join(lines)
    return body if body.endswith("\n") else body + "\n"


def save_files(text, on_saved=None):
    """Save every <<<FILE ... FILE>>> block in an AI reply into the apps folder.
    Calls on_saved(name) for each one and returns the saved names."""
    os.makedirs(APPS, exist_ok=True)
    saved = []
    for name, body in FILE_RE.findall(text):
        n = safe_name(name)
        if not n:
            continue
        p = os.path.join(APPS, n)
        with open(p, "w") as fh:
            fh.write(clean_body(body))
        if n.endswith((".sh", ".py")):
            os.chmod(p, 0o755)
        saved.append(n)
        if on_saved:
            on_saved(n)
    return saved


def write_app(name, text):
    """Save `text` as the app file `name` (your own edits, or a new file). Written atomically, so a
    crash never leaves half a file; .sh and .py files are made executable. Returns the path, or
    None when the name can't be used."""
    n = safe_name(name or "")
    if not n:
        return None
    os.makedirs(APPS, exist_ok=True)
    p = os.path.join(APPS, n)
    tmp = p + ".saving"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.replace(tmp, p)
    if n.endswith((".sh", ".py")):
        os.chmod(p, 0o755)
    return p


def delete_app(name):
    """Delete an app file. Returns its name, or None when there is no such file."""
    p = find_app(name)
    if not p:
        return None
    os.remove(p)
    return os.path.basename(p)


def find_app(name):
    n = safe_name(name or "")
    if not n:
        return None
    p = os.path.join(APPS, n)
    if os.path.isfile(p):
        return p
    try:
        cands = [f for f in os.listdir(APPS) if os.path.splitext(f)[0] == n]
    except OSError:
        return None
    order = [".c", ".py", ".sh", ".exe", ".iso"]  # .c first: it is rebuilt, so never a stale .exe
    cands.sort(key=lambda f: order.index(os.path.splitext(f)[1]) if os.path.splitext(f)[1] in order else 99)
    return os.path.join(APPS, cands[0]) if cands else None


def list_apps():
    """[(name, size in bytes)] for the apps folder, sorted by name."""
    try:
        names = sorted(os.listdir(APPS))
    except OSError:
        return []
    out = []
    for f in names:
        try:
            out.append((f, os.path.getsize(os.path.join(APPS, f))))
        except OSError:
            pass
    return out


def kind_of(name):
    """What sort of app a file is: c, py, sh, exe, iso or text."""
    ext = os.path.splitext(name)[1].lower()
    return {".c": "c", ".py": "py", ".sh": "sh", ".exe": "exe", ".iso": "iso"}.get(ext, "text")


def file_list_note():
    try:
        fs = sorted(os.listdir(APPS))
    except OSError:
        fs = []
    return ("\n\nFiles currently in the apps folder: " + ", ".join(fs)) if fs else ""


def file_text(p, limit=12000):
    """A text file's content (truncated to `limit` characters), or None for a binary/missing file."""
    try:
        data = open(p, "rb").read()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    t = data.decode("utf-8", "replace")
    return t if len(t) <= limit else t[:limit] + "\n...(truncated)"


def fix_request(errtext, fname):
    msg = errtext + "\n\nPlease fix %s and write the whole corrected file." % fname
    t = file_text(os.path.join(APPS, fname))
    if t is not None:
        msg += "\n\nCurrent %s:\n%s" % (fname, t)
    return msg


def send_request(name, note=""):
    """The message for /send NAME [note]: the file's text with the user's note. None if not a text app."""
    p = find_app(name)
    t = file_text(p) if p else None
    if t is None:
        return None
    return "%s\n\nHere is %s:\n%s" % (note.strip() or "Look at this file.", os.path.basename(p), t)


# ---------------------------------------------------------------------------- building and running
# Runs a .py app as __main__ but turns Ctrl+C into a quiet exit (code 130) instead of a traceback.
PY_LAUNCH = ("import runpy, sys\n"
             "sys.argv = sys.argv[1:]\n"
             "try:\n"
             "    runpy.run_path(sys.argv[0], run_name='__main__')\n"
             "except KeyboardInterrupt:\n"
             "    sys.exit(130)\n")


def compile_c(src):
    """Compile a .c app into NAME.exe next to it. Returns (exe path, or None when it failed,
    compiler output, possibly empty). Raises OSError when the C compiler isn't installed."""
    exe = os.path.splitext(src)[0] + ".exe"
    r = subprocess.run([CC, "-o", exe, src, "-lm"], cwd=APPS, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        return None, out
    os.chmod(exe, 0o755)
    return exe, out


def exe_head(p):
    with open(p, "rb") as fh:
        return fh.read(4)


def stale_exe_source(p):
    """For NAME.exe with a NAME.c beside it: the .c path when it must be (re)built first, else None."""
    c_path = os.path.splitext(p)[0] + ".c"
    if not os.path.isfile(c_path):
        return None
    if exe_head(p) != b"\x7fELF" or os.path.getmtime(c_path) > os.path.getmtime(p):
        return c_path
    return None


def emulated_cpu():
    """True when AI OS itself runs on a software-emulated CPU (QEMU without KVM). Such CPUs can claim
    virtualization support, but KVM on top of them crashes, so VMs must use plain emulation there."""
    try:
        if "QEMU Virtual CPU" not in open("/proc/cpuinfo").read():
            return False
        cs = open("/sys/devices/system/clocksource/clocksource0/available_clocksource").read()
        return "kvm-clock" not in cs  # QEMU *with* KVM underneath offers kvm-clock; pure emulation does not
    except OSError:
        return False


def mem_available_mb():
    avail = 1024
    try:
        for l in open("/proc/meminfo"):
            if l.startswith("MemAvailable:"):
                avail = int(l.split()[1]) // 1024
    except (OSError, ValueError):
        pass
    return avail


def vm_command(path, env):
    """How to boot an ISO in the built-in VM. Returns (cmd or None, memory in MB, free MB).
    cmd is None when there isn't enough free memory. Adjusts `env` for QEMU's text display."""
    avail = mem_available_mb()
    mem = min(4096, avail - 400)  # the VM gets the free RAM, minus a reserve for AI OS itself
    if mem < 256:
        return None, mem, avail
    cmd = ["qemu-system-x86_64", "-m", str(mem), "-cdrom", path, "-boot", "d", "-display", "curses",
           "-nic", "user,model=e1000"]
    if os.path.exists("/dev/kvm") and not emulated_cpu():
        cmd += ["-accel", "kvm", "-accel", "tcg", "-cpu", "max"]  # hardware speed; falls back to emulation
    if env.get("TERM") in (None, "", "dumb", "unknown"):
        env["TERM"] = "linux"
    env["LC_ALL"] = "C.UTF-8"  # the VM's text screen uses box-drawing characters
    return cmd, mem, avail


def program_command(p, args):
    """The command that runs a ready-to-run app (.sh, .py or a built .exe)."""
    ext = os.path.splitext(p)[1].lower()
    if ext == ".sh":
        return ["sh", p] + args
    if ext == ".py":
        return ["python3", "-c", PY_LAUNCH, p] + args
    os.chmod(p, 0o755)
    return [p] + args


# ---------------------------------------------------------------------------- ISO builder
# The boot menu for ISOs made with /iso. They hold one archive that GRUB loads in one go (AI OS's own
# ISO splits into starter.img + system.img, which a copy of the running system can't do), so they
# use the classic menu that build.sh installs at /boot/grub-classic.cfg. This copy is the fallback
# and should match grub/grub-classic.cfg.
GRUB_CFG = """set timeout=3
set default=0
if serial --unit=0 --speed=115200; then
  terminal_input console serial
  terminal_output console serial
fi
# Boot menu for ISOs made inside AI OS with /iso: one archive, loaded by GRUB in one go.
if cpuid -l; then set aios_cpu_ok=1; fi
if [ "$aios_cpu_ok" != "1" ]; then
  clear
  echo "AI OS needs a 64-bit processor, and this PC or VM is running as 32-bit."
  echo ""
  echo "VirtualBox: power the VM off, open Settings > General > Basic and set"
  echo "Version to 'Other Linux (64-bit)'. If only 32-bit versions are listed,"
  echo "turn on virtualization (Intel VT-x or AMD-V) in your PC's BIOS settings."
  echo ""
  echo "Press Enter to restart."
  read
  reboot
fi
insmod all_video
insmod echo
insmod linux
insmod progress
menuentry "AI OS" {
  echo "Loading AI OS..."
  set gfxpayload=1280x800x32,1280x720x32,1024x768x32,auto
  linux /boot/vmlinuz quiet loglevel=3 edd=off
  initrd /boot/initramfs
}
menuentry "AI OS (serial console)" {
  set gfxpayload=text
  linux /boot/vmlinuz console=tty0 console=ttyS0,115200 loglevel=3 edd=off aios.text=1
  initrd /boot/initramfs
}
menuentry "AI OS (text mode, no graphics)" {
  echo "Loading AI OS..."
  set gfxpayload=text
  linux /boot/vmlinuz quiet loglevel=3 edd=off aios.text=1
  initrd /boot/initramfs
}
menuentry "AI OS (show boot messages)" {
  set gfxpayload=1280x800x32,1280x720x32,1024x768x32,auto
  linux /boot/vmlinuz loglevel=7 edd=off
  initrd /boot/initramfs
}
"""


def make_iso(arg, info, err, built):
    """Build a bootable copy of the running AI OS with some apps preloaded (/iso OUT.iso [apps]).
    Reports through info(msg) / err(msg) and finally built(name, size_mb). Returns the ISO path or None."""
    parts = arg.split()
    if not parts:
        err("usage: /iso OUT.iso [files...]"); return None
    out = safe_name(parts[0])
    if not out.endswith(".iso"):
        out += ".iso"
    if parts[1:]:
        files = []
        for f in parts[1:]:
            p = find_app(f)
            if not p:
                err("No app %s." % f); return None
            files.append(os.path.basename(p))
    else:
        files = sorted(f for f in os.listdir(APPS) if not f.endswith(".iso")) if os.path.isdir(APPS) else []
    for tool in ("cpio", "gzip", "grub-mkrescue"):
        if not shutil.which(tool):
            err("%s is missing; can't build ISOs here." % tool); return None
    if not os.path.isfile("/boot/vmlinuz"):
        err("/boot/vmlinuz missing; can't build ISOs here."); return None
    st = os.statvfs("/tmp")
    free = st.f_bavail * st.f_frsize // (1 << 20)
    if free < 400:
        err("Warning: only %d MB free in /tmp (RAM). The build may fail; give the PC/VM more RAM." % free)
    info("Building %s with %d app(s): %s" % (out, len(files), " ".join(files) or "(none)"))
    info("Note: the new ISO includes this OS's saved API key - only share it with people you trust.")
    work = tempfile.mkdtemp(prefix="iso.", dir="/tmp")
    try:
        iso = os.path.join(work, "iso")
        os.makedirs(iso + "/boot/grub")
        extra = os.path.join(work, "extra")
        for d in ("proc", "sys", "dev", "tmp", "run", "root/apps"):
            os.makedirs(os.path.join(extra, d))
        for f in files:
            shutil.copy2(os.path.join(APPS, f), os.path.join(extra, "root/apps", f))
        info("[1/3] packing the system (this can take a minute)...")
        initrd = os.path.join(iso, "boot/initramfs")
        # etc/wpa_supplicant holds the Wi-Fi password: never copy it into a new ISO
        prune = " ".join("-path ./%s -prune -o" % d for d in ("proc", "sys", "dev", "tmp", "run", "root/apps",
                                                               "etc/wpa_supplicant", ".aios-complete"))
        # the marker /init checks goes in the archive that is unpacked last
        open(os.path.join(extra, ".aios-complete"), "w").close()
        # zstd packs ~30% smaller than gzip, so the new ISO needs less RAM to unpack when it boots
        comp = "zstd -q -T0 -12" if shutil.which("zstd") else "gzip -1"
        sh = ("set -e; { (cd / && find . -xdev %s -print | cpio -o -H newc 2>/dev/null); "
              "(cd '%s' && find . | cpio -o -H newc 2>/dev/null); } | %s > '%s'" % (prune, extra, comp, initrd))
        if subprocess.call(["sh", "-c", sh]) != 0:
            err("Packing failed."); return None
        shutil.copy2("/boot/vmlinuz", iso + "/boot/vmlinuz")
        try:
            cfg = open("/boot/grub-classic.cfg").read()  # the single-archive boot menu build.sh installs
        except OSError:
            cfg = GRUB_CFG
        with open(iso + "/boot/grub/grub.cfg", "w") as fh:
            fh.write(cfg)
        info("[2/3] system image %d MB" % (os.path.getsize(initrd) >> 20))
        info("[3/3] writing ISO...")
        dest = os.path.join(APPS, out)
        r = subprocess.run(["grub-mkrescue", "-o", dest, iso, "--", "-volid", "AIOS"], capture_output=True, text=True)
        if r.returncode != 0:
            err("grub-mkrescue failed:\n" + r.stderr[-2000:]); return None
        built(out, os.path.getsize(dest) >> 20)
        return dest
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------- network
def default_route():
    """True once DHCP has given us a default route."""
    try:
        for l in open("/proc/net/route").readlines()[1:]:
            f = l.split()
            if len(f) > 2 and f[1] == "00000000":
                return True
    except OSError:
        pass
    return False


def net_lines():
    """[(adapter, has_link, [IPv4 addresses])] for every network adapter except loopback."""
    out = []
    try:
        text = subprocess.run(["ip", "addr"], capture_output=True, text=True).stdout
    except OSError:
        return out
    for l in text.splitlines():
        m = re.match(r"\d+: ([^:@]+)[^<]*<([^>]*)>", l)
        if m:
            out.append((m.group(1), "LOWER_UP" in m.group(2), []))
        elif l.strip().startswith("inet ") and out:
            out[-1][2].append(l.split()[1])
    return [x for x in out if x[0] != "lo"]


def ai_reachable():
    """(True, '') when the AI service answers, else (False, reason)."""
    try:
        urllib.request.urlopen(urllib.request.Request(API + "/models"), timeout=8)
        return True, ""
    except urllib.error.HTTPError:
        return True, ""          # it answered (401 without a key is fine)
    except Exception as e:
        return False, str(getattr(e, "reason", e))


def wired_ifaces():
    try:
        names = os.listdir("/sys/class/net")
    except OSError:
        return []
    return [n for n in names if n != "lo" and not os.path.exists("/sys/class/net/%s/wireless" % n)
            and not os.path.exists("/sys/class/net/%s/phy80211" % n)]


# ---------------------------------------------------------------------------- Wi-Fi (rootfs/sbin/ai-wifi)
def wifi_tools():
    return bool(shutil.which("ai-wifi"))


def wifi_iface():
    try:
        return subprocess.run(["ai-wifi", "iface"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def wifi_status():
    """(connected, {iface, state, ssid, ip}) from `ai-wifi status`; state 'no-adapter' without Wi-Fi."""
    try:
        r = subprocess.run(["ai-wifi", "status"], capture_output=True, text=True)
    except OSError:
        return False, {"state": "no-adapter"}
    kv = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)
    return r.returncode == 0, kv


def wifi_scan():
    """([(signal_dbm, security, ssid)], error message or '') from `ai-wifi scan`, strongest first."""
    try:
        r = subprocess.run(["ai-wifi", "scan"], capture_output=True, text=True)
    except OSError as e:
        return [], str(e)
    if r.returncode != 0:
        return [], (r.stderr or r.stdout).strip() or "Scan failed."
    return [tuple(l.split("\t", 2)) for l in r.stdout.splitlines() if l.count("\t") >= 2], ""


def wifi_connect(ssid, password):
    """Join a network. Returns (exit code, the helper's messages). 0 connected, 3 wrong password."""
    try:
        r = subprocess.run(["ai-wifi", "connect", ssid, password], capture_output=True, text=True)
    except OSError as e:
        return 1, str(e)
    return r.returncode, (r.stdout + r.stderr).strip()


def wifi_disconnect():
    try:
        subprocess.run(["ai-wifi", "disconnect"], capture_output=True, text=True)
    except OSError:
        pass


def printable(s):
    return "".join(c if c.isprintable() else "?" for c in s)


def bars(dbm):
    try:
        d = int(float(dbm))
    except ValueError:
        return ""
    n = 4 if d >= -55 else 3 if d >= -67 else 2 if d >= -75 else 1
    return "[%s%s] %d dBm" % ("#" * n, " " * (4 - n), d)


def signal_level(dbm):
    """Signal strength 1..4 (for drawing Wi-Fi bars)."""
    try:
        d = int(float(dbm))
    except ValueError:
        return 1
    return 4 if d >= -55 else 3 if d >= -67 else 2 if d >= -75 else 1
