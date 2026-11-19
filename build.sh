#!/bin/sh
# Builds out/ai-os.iso: an Alpine Linux based live OS whose only screen is an AI chat.
# Needs root, curl, cpio, xz, grub-mkrescue (grub-pc-bin + grub-efi-amd64-bin), xorriso, mtools.
# API key: put it in ./groq.key or GROQ_API_KEY. Without one, the OS asks for it at boot.
set -eu
cd "$(dirname "$0")"
TOP=$PWD
BR=${ALPINE_BRANCH:-v3.24}
M=${ALPINE_MIRROR:-https://dl-cdn.alpinelinux.org/alpine}/$BR
B=$TOP/build; R=$B/rootfs; K=$B/kernel; ISO=$B/iso
rm -rf "$R" "$K" "$ISO"; mkdir -p "$B" "$R" "$K" "$ISO/boot/grub" out

# 1. apk.static
if [ ! -x "$B/apk.static" ]; then
  v=$(curl -fsSL "$M/main/x86_64/APKINDEX.tar.gz" | tar xzO APKINDEX | awk '/^P:apk-tools-static$/{f=1} f&&/^V:/{print substr($0,3);exit}')
  curl -fsSL "$M/main/x86_64/apk-tools-static-$v.apk" | tar xz -C "$B" sbin/apk.static 2>/dev/null || true
  mv "$B/sbin/apk.static" "$B/apk.static"; rmdir "$B/sbin"
fi
APK="$B/apk.static -X $M/main -X $M/community --allow-untrusted --no-cache"

# 2. root filesystem
$APK --root "$R" --initdb -U add \
  alpine-baselayout busybox busybox-binsh musl ca-certificates kmod \
  python3 tcc tcc-libs tcc-libs-static musl-dev \
  qemu-system-x86_64 qemu-ui-curses ncurses-terminfo-base \
  xorriso mtools grub grub-bios grub-efi cpio zstd \
  wpa_supplicant wireless-regdb
rm -rf "$R/usr/lib/python3"*/test "$R/usr/lib/python3"*/ensurepip "$R/usr/lib/python3"*/idlelib \
       "$R/usr/lib/python3"*/tkinter "$R/var/cache/apk/"*
find "$R/usr/lib" -name __pycache__ -prune -exec rm -rf {} +
# precompile Python's standard library: without it, every boot spends seconds (minutes in a slow VM)
# compiling the modules the chat imports before it can show anything
PYTHONHASHSEED=0 chroot "$R" /usr/bin/python3 -m compileall -q -j 0 -x '/(test|tests|idlelib|turtledemo)/' /usr/lib >/dev/null
# qemu firmware we do not need (keeps BIOS + the default VGA ROMs)
find "$R/usr/share/qemu" -name '*.fd' -o -name 'edk2*' -o -name '*-s390*' -o -name 'u-boot*' -o -name '*.dtb' 2>/dev/null | xargs rm -rf

# 3. kernel + a trimmed module set (wired/virtual network, USB, input, KVM, filesystems)
kv=$(curl -fsSL "$M/main/x86_64/APKINDEX.tar.gz" | tar xzO APKINDEX | awk '/^P:linux-lts$/{f=1} f&&/^V:/{print substr($0,3);exit}')
curl -fsSL "$M/main/x86_64/linux-lts-$kv.apk" | tar xz -C "$K" 2>/dev/null || true
KV=$(ls "$K/lib/modules")
cp "$K/boot/vmlinuz-lts" "$ISO/boot/vmlinuz"
mkdir -p "$R/boot" && cp "$K/boot/vmlinuz-lts" "$R/boot/vmlinuz"
S=$K/lib/modules/$KV; D=$R/lib/modules/$KV; mkdir -p "$D"
cp "$S"/modules.order "$S"/modules.builtin* "$D"/
# Wi-Fi drivers stay, except those whose firmware we do not ship (or that only exist on ARM boards)
W=kernel/drivers/net/wireless
(cd "$S" && find kernel \( -path 'kernel/drivers/gpu' -o -path 'kernel/drivers/media' -o -path 'kernel/drivers/staging' \
   -o -path 'kernel/drivers/infiniband' -o -path 'kernel/drivers/bluetooth' \
   -o -path "$W/marvell" -o -path "$W/ti" -o -path "$W/st" -o -path "$W/intersil" -o -path "$W/rsi" -o -path "$W/zydas" \
   -o -path "$W/ath/ath6kl" -o -path "$W/ath/wcn36xx" -o -path "$W/broadcom/b43" -o -path "$W/broadcom/b43legacy" \
   -o -path 'kernel/drivers/iio' -o -path 'kernel/drivers/isdn' -o -path 'kernel/sound' \
   -o -path 'kernel/net/bluetooth' -o -path 'kernel/drivers/scsi/qla2xxx' \
   -o -path 'kernel/drivers/scsi/lpfc' -o -path 'kernel/drivers/md' -o -path 'kernel/fs/xfs' -o -path 'kernel/fs/btrfs' \
   -o -path 'kernel/fs/bcachefs' -o -path 'kernel/fs/ocfs2' -o -path 'kernel/fs/gfs2' -o -path 'kernel/drivers/net/ethernet/mellanox' \
   -o -path 'kernel/drivers/net/ethernet/chelsio' -o -path 'kernel/drivers/net/ethernet/qlogic' -o -path 'kernel/drivers/net/ethernet/sfc' \) -prune -o -type f -print \
 | cpio -pdm "$D" 2>/dev/null)
chroot "$R" /sbin/depmod "$KV"

# 3b. Wi-Fi firmware (Intel, Realtek, MediaTek, Qualcomm/Atheros, Broadcom, Ralink): only the files
#     the drivers above can load, ~50 MB. The packages (~210 MB) are downloaded once into build/fwcache.
fv=$(curl -fsSL "$M/main/x86_64/APKINDEX.tar.gz" | tar xzO APKINDEX | awk '/^P:linux-firmware-intel$/{f=1} f&&/^V:/{print substr($0,3);exit}')
FC=$B/fwcache; FW=$B/fw/lib/firmware; FD=$R/lib/firmware
rm -rf "$B/fw"; mkdir -p "$FC" "$B/fw" "$FD"
for p in intel mediatek ath10k ath11k ath12k ath9k_htc rtw88 rtw89 rtlwifi brcm other; do
  f=$FC/linux-firmware-$p-$fv.apk
  if [ ! -s "$f" ]; then curl -fsSL -o "$f.part" "$M/main/x86_64/linux-firmware-$p-$fv.apk"; mv "$f.part" "$f"; fi
  tar xzf "$f" -C "$B/fw" 2>/dev/null || true
done
WFW=$(find "$D" -path '*/net/wireless/*' -name '*.ko*' -exec sh -c 'zcat -f "$1" | tr "\0" "\n"' _ {} \; | sed -n 's/^firmware=//p' | sort -u)
IWLC=$(printf '%s\n' "$WFW" | sed -n 's/^iwlwifi-.*-c\([0-9]*\)\.ucode$/\1/p' | sort -n | tail -1)
{
  # Intel: per chip family the newest firmware the driver accepts (6.18 tries core c99, then API 101 and older)
  (cd "$FW" && ls iwlwifi-*.ucode.zst) | sed 's/\.ucode\.zst$//' | awk -v cmax="${IWLC:-0}" '
    { fam=$0; sub(/-c?[0-9]+$/, "", fam); v=substr($0, length(fam)+2)
      if (v ~ /^c/) { n=substr(v,2)+0; if (n<=cmax && n>cb[fam]) cb[fam]=n }
      else if (v+0<=101 && v+0>db[fam]) db[fam]=v+0 }
    END { for (f in db) print f "-" db[f] ".ucode.zst"; for (f in cb) print f "-c" cb[f] ".ucode.zst" }'
  (cd "$FW" && ls iwlwifi-*.pnvm.zst)
  # other drivers: exactly the files they declare (MODULE_FIRMWARE); "dir/*" means the whole directory
  printf '%s\n' "$WFW" | grep -v '^iwlwifi-' | while read -r f; do
    case $f in
      */\*) (cd "$FW" && find "${f%/\*}" \( -type f -o -type l \) 2>/dev/null) || : ;;
      *\**) ;;
      *) if [ -e "$FW/$f.zst" ]; then echo "$f.zst"; elif [ -e "$FW/$f" ]; then echo "$f"; fi ;;
    esac
  done
  # drivers that pick between file versions themselves, or declare nothing (ath12k): whole directories
  (cd "$FW" && find rtw88 rtw89 rtlwifi ath12k/WCN7850 \( -type f -o -type l \) 2>/dev/null) || :
} | grep -viE 'notice|QCN9074|/mt791[56]_|brcmfmac4366|-sdio[.]' | sort -u > "$B/fw.list"
while read -r f; do
  if [ -e "$FW/$f" ]; then mkdir -p "$(dirname "$FD/$f")"; cp -L "$FW/$f" "$FD/$f"; fi
done < "$B/fw.list"
echo "Wi-Fi firmware: $(wc -l < "$B/fw.list") files, $(du -sh "$FD" | cut -f1)"

# 4. our files
cp -a rootfs/. "$R"/
chmod 755 "$R/init" "$R/usr/bin/aichat" "$R"/sbin/ai-*
KEY=${GROQ_API_KEY:-$( [ -f groq.key ] && cat groq.key || true )}
if [ -n "$KEY" ]; then mkdir -p "$R/etc/ai-os"; printf '%s\n' "$KEY" > "$R/etc/ai-os/key"; chmod 600 "$R/etc/ai-os/key"; fi
echo ai-os > "$R/etc/hostname"
mkdir -p "$R/root/apps"
cp grub/grub.cfg "$R/boot/grub.cfg"   # /iso gives the ISOs it makes this same boot menu

# 5. initramfs + ISO
# The files /init needs to print "needs more RAM" go first: when the kernel runs out of memory
# while unpacking, it stops part way through the archive, and these are already in place.
EARLY="./init ./bin ./bin/busybox ./bin/sh ./bin/echo ./bin/sleep ./lib ./lib/ld-musl-x86_64.so.1 ./sbin ./sbin/poweroff"
# zstd unpacks about 10x faster than xz: that unpacking is most of the wait between the boot menu and the chat
# .aios-complete goes last: /init only finds it when the whole system was unpacked
touch "$R/.aios-complete"
(cd "$R" && { printf '%s\n' . $EARLY; find . | grep -vxF -e . -e ./.aios-complete $(printf -- '-e %s ' $EARLY); \
  echo ./.aios-complete; } | cpio -o -H newc --quiet | zstd -q -T0 -19) > "$ISO/boot/initramfs"
cp grub/grub.cfg "$ISO/boot/grub/grub.cfg"
grub-mkrescue -o out/ai-os.iso "$ISO" -- -volid AIOS 2>/dev/null
ls -lh out/ai-os.iso
