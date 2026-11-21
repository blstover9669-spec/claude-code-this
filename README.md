# AI OS

A tiny live operating system whose only screen is a chat with an AI. There is no desktop
and no shell: you talk to the AI, it writes programs for you, and you run them with one click.

The chat is a full-screen graphical app (mouse and keyboard): a sidebar with your apps,
Games, Wi-Fi, Settings and Power; chat bubbles; every file the AI writes shows up as a card
with **Run**, **Edit** and **View** buttons; programs run in a terminal window on top of the chat, and
if one fails, **Ask AI to fix** sends the error and the source back to the AI. You can edit any
file yourself in the built-in code editor (line numbers, syntax colours, selection, copy/paste,
undo; Ctrl+S saves, F5 runs), make a new one with **+ New** in the Apps list, and delete files
from their menu (it asks first). Slash commands
work in the message box too. The text-mode boot entry (and the serial console) give the same
chat as plain text:

```
you> make me a snake game in C
(the AI writes snake.c)
[saved apps/snake.c]  type /run snake.c
you> /run snake
compiling snake.c -> snake.exe
```

## Games while it loads

GRUB only loads a small starter system; the starter shows a loading screen while it reads
the rest of AI OS from the disc or USB stick, and you can play while you wait:

| Game | Controls |
| --- | --- |
| **Space Shooter** (2D): waves of alien ships, power-ups, a boss every 5th wave | arrows/WASD move, Space fires |
| **Dino Run** (2D): jump the cacti, duck the pterosaurs | Space/Up jump, Down duck |
| **Dino Run 3D**: three lanes in real (software-rendered) 3D | Left/Right lanes, Space/Up jump |

A slim bar across the top of the game keeps showing the loading progress, Esc goes back to
the menu, and the game closes by itself the moment AI OS is ready. The same games are under
**Games** in the chat's sidebar.

## What it can do

| You type | What happens |
| --- | --- |
| anything | sent to the AI (Groq API, model `openai/gpt-oss-120b` by default) |
| `/run NAME.sh` | runs a shell script (busybox sh) |
| `/run NAME.py` | runs a Python 3 script (standard library only) |
| `/run NAME.c` | compiles it with tcc into `NAME.exe`, then runs it |
| `/run NAME.exe` | runs a program built here (rebuilt first if the `.c` changed) |
| `/run NAME.iso` | boots the ISO in a built-in virtual machine (QEMU, text display) |
| `/iso OUT.iso [apps]` | builds a bootable copy of AI OS with those apps inside |
| `/build NAME.c` | compiles without running |
| `/edit NAME` | edit a file yourself (a new name makes a new file); vi in the text chat |
| `/files` `/show` `/rm` | list, print, delete apps |
| `/send NAME [msg]` | shows a file to the AI |
| `/wifi` | scan for and join a Wi-Fi network |
| `/net` `/model` `/key` `/new` `/clear` `/reboot` `/poweroff` | the rest; `/help` lists them |

The extension is optional: `/run snake` picks `snake.c` (or `.py`, `.sh`, `.exe`, `.iso`).
When a program fails, AI OS offers to send the error and the source to the AI to fix it.

`.exe` here means a native Linux program built on AI OS from C. Windows `.exe` files can't run:
ask the AI to write the program in C instead.

## Booting it

- **Virtual machine** (VirtualBox, VMware, QEMU, Hyper-V): make a 64-bit Linux VM with at
  least 2 GB of RAM, attach `ai-os.iso` as the CD, keep the network adapter on NAT. No disk is needed.
  QEMU: `qemu-system-x86_64 -m 2048 -cdrom ai-os.iso -enable-kvm`
- **RAM**: 1 GB is the minimum and 2 GB is comfortable. Booting an ISO made with `/iso` inside
  AI OS (AI OS in AI OS) needs about 1 GB more, so give it 3–4 GB for that.
- **Real PC**: write the ISO to a USB stick with balenaEtcher, Rufus (DD mode) or
  `dd if=ai-os.iso of=/dev/sdX bs=4M`, then boot from it. Turn off Secure Boot in the
  firmware settings (the boot loader isn't signed). It boots on BIOS and UEFI.
- Networking: wired Ethernet and USB tethering from a phone work right away; for Wi-Fi use `/wifi`.
  In a VM there is nothing to set up: the VM's NAT adapter uses the host's connection, Wi-Fi included.

**VirtualBox in short**: Type *Linux*, Version *Other Linux (64-bit)*, Base Memory 2048 MB,
no hard disk, `ai-os.iso` in the optical drive, network adapter on NAT. Tick
*Skip Unattended Installation* if the new-VM wizard offers it.

Boot menu entries:

- **AI OS**: the normal start, with the graphical loading screen, games and chat.
- **AI OS (serial console)**: text chat on the first serial port as well (for headless VMs).
- **AI OS (text mode, no graphics)**: loads everything up front and uses the text chat; pick
  it if the graphics don't work on a PC.
- **AI OS (show boot messages)**: the normal start with all kernel messages shown.

On a normal PC or VM the chat is up in 10–20 seconds. If it ever stops:

- pick **AI OS (show boot messages)** in the boot menu to see where it stops;
- "couldn't find its disc or USB stick": pick **AI OS (text mode, no graphics)**, which
  doesn't need to find it again;
- "needs a 64-bit processor": set the VM's version to a 64-bit one, or turn on VT-x/AMD-V
  in the PC's BIOS if VirtualBox only offers 32-bit versions;
- "needs more RAM": raise the VM's memory to 2 GB;
- a turtle icon in VirtualBox's status bar means it runs without hardware virtualization
  (often because Hyper-V is on in Windows). Everything still works, only much slower.

Everything runs from RAM. Nothing is written to your disks, and your apps are gone after a
reboot unless you pack them into a new ISO with `/iso`.

## The API key

AI OS uses a [Groq](https://console.groq.com/keys) API key. If the ISO was built with one,
it is used automatically; otherwise AI OS asks for it on first boot (`/key` changes it).
An ISO built with a key contains that key, so only share such an ISO with people you trust,
and never commit a key to this repository.

**Models and the free limit.** Click the model name at the top right of the chat (or type
`/model`) to pick one: GPT-OSS 120B (smartest), GPT-OSS 20B (fast), Qwen 3.8 27B, ALLaM 2 7B.
Groq's free plan allows each model about 8,000 tokens a minute. AI OS keeps requests small
(earlier code isn't re-sent; a file's current text is attached only when you mention it), waits
out a limit of a few seconds, and otherwise lets another model answer, saying so in the chat.

## Building the ISO

Needs a Linux machine with root, `curl`, `cpio`, `zstd`, `xorriso`, `mtools` and GRUB
(`grub-pc-bin` and `grub-efi-amd64-bin` on Debian/Ubuntu).

```
echo 'gsk_your_key' > groq.key     # optional; ignored by git
sudo ./build.sh                     # -> out/ai-os.iso
```

The system is Alpine Linux (packages downloaded during the build) with the `linux-lts` kernel
and a trimmed driver set. The graphical programs are Python with pygame, drawing straight onto
the Linux framebuffer (no X or Wayland) and reading keyboard and mouse from `/dev/input`.
The ISO holds two archives: `boot/starter.img`, which GRUB loads, and `boot/system.img`, which
the starter streams in while the loading screen runs. Interface text uses Liberation Sans, the
open font with Arial's metrics (Arial itself can't be redistributed); code uses JetBrains Mono.

| File | Role |
| --- | --- |
| `build.sh` | downloads Alpine packages and the kernel, assembles the root filesystem, builds the ISO |
| `tools/starter_files.py` | decides what goes into the starter (with every library it needs) |
| `rootfs/init` | the starter: finds the disc or USB stick, streams `system.img` in, starts busybox init |
| `rootfs/sbin/ai-sysinit` | loads drivers, starts networking, sets the clock |
| `rootfs/sbin/ai-progress` | the loading bar (text) and the progress the loading screen shows |
| `rootfs/sbin/ai-netwatch` | keeps DHCP running on every wired adapter |
| `rootfs/sbin/ai-wifi` | Wi-Fi scan and connect (used by `/wifi`) |
| `rootfs/usr/lib/aios/aios/loader_ui.py` | the loading screen with the games |
| `rootfs/usr/lib/aios/aios/games/` | Space Shooter, Dino Run, Dino Run 3D |
| `rootfs/usr/lib/aios/aios/gui.py` | the graphical chat (with `widgets.py`, `term.py` for app windows, `editor.py`) |
| `rootfs/usr/lib/aios/aios/core.py` | chat logic shared by the graphical and the text chat |
| `rootfs/usr/lib/aios/aios/display.py`, `theme.py`, `boot.py` | screen and input, look, loading hand-off |
| `rootfs/usr/bin/aios-gui` | starts the graphical chat, or the text chat when there's no screen |
| `rootfs/usr/bin/aichat` | the text chat |
| `grub/grub.cfg` | boot menu; `grub-classic.cfg` is the menu of ISOs made with `/iso` |
| `fonts/` | Liberation Sans and JetBrains Mono (SIL OFL, see `fonts/OFL.txt`) |
