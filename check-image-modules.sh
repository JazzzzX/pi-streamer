#!/bin/bash
# Run as root in streamer-br-builder with streamer-br mounted at /work.
# Decode real compressed ARM64 modules using the target image's own libkmod.
set -euo pipefail
O=/work/out
T=/work/module-image-test
rm -rf "$T"
mkdir -p "$T"
"$O/host/sbin/debugfs" -R "rdump / $T" "$O/images/rootfs.ext4" >/work/module-rdump.log 2>&1
mknod -m666 "$T/dev/null" c 1 3
chroot "$T" /usr/bin/kmod --version | grep -F -- '+XZ'
for name in brcmfmac snd-usb-audio btusb hci_uart; do
    path=$(find "$T/lib/modules" -name "$name.ko.xz" | head -1)
    test -n "$path"
    decoded=$(chroot "$T" /sbin/modinfo -F name "${path#$T}")
    test "$decoded" = "${name//-/_}"
    echo "Native ARM64 compressed module decode: $name PASS"
done
