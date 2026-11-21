#!/usr/bin/python3
"""Lists the files of AI OS's starter system: what GRUB loads before anything else.

Run inside the finished root filesystem (build.sh does `chroot build/rootfs python3 ...`).
The starter holds the shell tools, Python with pygame, the loading screen and games, and the
drivers needed to find the boot disc or USB stick; the rest of AI OS (system.img) is read by
the starter itself while the loading screen runs. Prints one path per line (relative, './x').
"""
import glob, os, re, subprocess, sys

PY = "/usr/lib/python%d.%d" % sys.version_info[:2]

# whole directories (and single files) that belong to the starter
TREES = ["/init", "/bin", "/sbin", "/etc", "/dev", "/root", "/run", "/tmp", "/var", "/mnt", "/proc", "/sys",
         "/usr/lib/aios", "/usr/share/fonts/aios", PY]
# Python standard library parts the starter never uses (they arrive with the rest of AI OS)
PY_SKIP = {"asyncio", "pydoc_data", "unittest", "xml", "xmlrpc", "multiprocessing", "concurrent", "sqlite3",
           "lib2to3", "ensurepip", "venv", "idlelib", "tkinter", "turtledemo", "test", "wsgiref", "email", "http",
           "urllib", "html", "zoneinfo", "curses", "dbm", "ctypes", "tomllib", "site-packages", "config-"}
SITE_KEEP = ("pygame", "wcwidth")       # from site-packages; pyte lives in /usr/lib/aios
SITE_DROP = ("pygame/examples", "pygame/tests", "pygame/docs", "pygame/__pyinstaller")
# kernel modules: find the boot medium (CD/DVD, USB, VM disks), read it, and keyboard/mouse
MODULES = """ata_piix pata_acpi ata_generic ahci libahci libata sr_mod cdrom sd_mod scsi_mod scsi_common
 usb_storage uas xhci_pci xhci_pci_renesas xhci_hcd ehci_pci ehci_hcd ohci_pci ohci_hcd uhci_hcd usbcore
 usb_common virtio_blk virtio_scsi virtio_pci virtio_pci_legacy_dev virtio_pci_modern_dev virtio_ring virtio
 nvme nvme_core hv_storvsc hv_vmbus vmw_pvscsi mptspi mptscsih mptbase mmc_block mmc_core sdhci sdhci_pci
 sdhci_acpi isofs vfat fat nls_cp437 nls_iso8859_1 nls_utf8 evdev psmouse usbhid hid_generic hid
 hid_multitouch hyperv_keyboard hid_hyperv serio_raw""".split()

out = set()


def add(path):
    """Add a path, the directories above it and, for a symlink, what it points to."""
    p = path.rstrip("/") or "/"
    while p not in ("/", ""):
        if p in out:
            break
        out.add(p)
        p = os.path.dirname(p)
    if os.path.islink(path):
        target = os.path.join(os.path.dirname(path), os.readlink(path))
        target = os.path.normpath(target)
        if os.path.lexists(target) and target not in out:
            add(target)


def walk(top, skip=lambda p: False):
    if not os.path.lexists(top):
        return
    if not os.path.isdir(top) or os.path.islink(top):
        add(top)
        return
    add(top)
    for dirpath, dirs, files in os.walk(top):
        dirs[:] = [d for d in dirs if not skip(os.path.join(dirpath, d))]
        for name in dirs + files:
            p = os.path.join(dirpath, name)
            if not skip(p):
                add(p)


def py_skip(p):
    rel = p[len(PY) + 1:] if p.startswith(PY + "/") else ""
    first = rel.split("/", 1)[0]
    if first == "site-packages":
        sub = rel.split("/", 2)
        if len(sub) == 1:
            return False
        if not sub[1].startswith(SITE_KEEP):
            return True
        return any(rel.startswith("site-packages/" + d) for d in SITE_DROP)
    if first == "lib-dynload":
        return bool(re.search(r"_(sqlite3|ctypes|curses|tkinter|dbm|gdbm|test)", rel))
    return any(first == s or first.startswith(s) and s.endswith("-") for s in PY_SKIP)


for t in TREES:
    walk(t, py_skip if t == PY else (lambda p: p.startswith(("/lib/modules", "/lib/firmware"))))
# busybox applet links in /usr/bin and /usr/sbin, plus the few real programs the starter runs
for d in ("/usr/bin", "/usr/sbin"):
    for p in glob.glob(d + "/*"):
        if os.path.islink(p) and os.path.basename(os.readlink(p)) == "busybox":
            add(p)
for p in glob.glob("/usr/bin/python3*") + glob.glob("/usr/bin/zstd*") + glob.glob("/usr/bin/unzstd") + \
        ["/usr/bin/ldd", "/usr/bin/cpio", "/bin/cpio"] + \
        glob.glob("/usr/lib/libSDL3.so*"):   # GNU cpio replaces busybox's cpio link; sdl2-compat dlopen()s SDL3
    if os.path.lexists(p):
        add(p)
add("/lib/ld-musl-x86_64.so.1")

# kernel modules (with what they depend on) and the module index files
kv = os.listdir("/lib/modules")[0]
mdir = "/lib/modules/" + kv
deps = {}
for line in open(mdir + "/modules.dep"):
    path, _, rest = line.partition(":")
    deps[path] = rest.split()
byname = {re.sub(r"\.ko(\.\w+)?$", "", os.path.basename(p)).replace("-", "_"): p for p in deps}
want = [byname[m] for m in MODULES if m in byname]
seen = set()
while want:
    m = want.pop()
    if m in seen:
        continue
    seen.add(m)
    want.extend(deps.get(m, []))
for m in seen:
    add(mdir + "/" + m)
for p in glob.glob(mdir + "/modules.*"):
    add(p)

# shared libraries every program above needs (musl's ldd, run inside the chroot)
def elf(p):
    try:
        with open(p, "rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False

todo = [p for p in out if os.path.isfile(p) and not os.path.islink(p) and elf(p)]
done = set()
while todo:
    p = todo.pop()
    if p in done:
        continue
    done.add(p)
    try:
        res = subprocess.run(["/lib/ld-musl-x86_64.so.1", "--list", p], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        continue
    for m in re.finditer(r"=> (/\S+)", res.stdout):
        lib = m.group(1)
        if lib not in out:
            add(lib)
        real = os.path.realpath(lib)
        if real not in done:
            todo.append(real)

for p in sorted(out):
    print("." + p)
