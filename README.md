# AI OS

A tiny live operating system whose only screen is a chat with an AI. There is no desktop
and no shell: you talk to the AI, it writes programs for you, and you run them with `/run`.

```
you> make me a snake game in C
(the AI writes snake.c)
[saved apps/snake.c]  type /run snake.c
you> /run snake
compiling snake.c -> snake.exe
```

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

Everything runs from RAM. Nothing is written to your disks, and your apps are gone after a
reboot unless you pack them into a new ISO with `/iso`.

## The API key

AI OS uses a [Groq](https://console.groq.com/keys) API key. If the ISO was built with one,
it is used automatically; otherwise AI OS asks for it on first boot (`/key` changes it).
An ISO built with a key contains that key, so only share such an ISO with people you trust,
and never commit a key to this repository.

## Building the ISO

Needs a Linux machine with root, `curl`, `cpio`, `xz`, `xorriso`, `mtools` and GRUB
(`grub-pc-bin` and `grub-efi-amd64-bin` on Debian/Ubuntu).

```
echo 'gsk_your_key' > groq.key     # optional; ignored by git
sudo ./build.sh                     # -> out/ai-os.iso
```

The system is Alpine Linux (packages downloaded during the build), the `linux-lts` kernel with
a trimmed driver set, and one program: [`rootfs/usr/bin/aichat`](rootfs/usr/bin/aichat).

| File | Role |
| --- | --- |
| `build.sh` | downloads Alpine packages and the kernel, assembles the root filesystem, builds the ISO |
| `rootfs/init` | first process: mounts the basics, starts busybox init |
| `rootfs/sbin/ai-sysinit` | loads drivers, starts networking, sets the clock |
| `rootfs/sbin/ai-netwatch` | keeps DHCP running on every wired adapter |
| `rootfs/sbin/ai-wifi` | Wi-Fi scan and connect (used by `/wifi`) |
| `rootfs/usr/bin/aichat` | the chat, app runner and ISO builder; the only thing on screen |
| `grub/grub.cfg` | boot menu (normal and serial-console entries) |
