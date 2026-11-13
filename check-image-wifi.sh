#!/bin/bash
# Native ARM64 integration test in the builder container, using throwaway credentials.
# Run as root inside streamer-br-builder with streamer-br mounted at /work.
set -euo pipefail
O=/work/out
T=/work/wifi-image-test
rm -rf "$T"
mkdir -p "$T"
"$O/host/sbin/debugfs" -R "rdump / $T" "$O/images/rootfs.ext4" >/work/wifi-rdump.log 2>&1
mkdir -p "$T/run" "$T/boot"
mknod -m 666 "$T/dev/null" c 1 3
# Exercise the actual installed helper, not a hand-written substitute config.
printf 'ssid=test-network\npsk=test-password\ncountry=IN\nbluetooth=auto\n' > "$T/boot/streamer.txt"
chroot "$T" /usr/libexec/streamer/wifi-config
set +e
output=$(timeout 4 chroot "$T" /usr/sbin/wpa_supplicant -Dnone -ilo -c/run/streamer/wpa_supplicant.conf 2>&1)
set -e
# Driver "none" is deliberately absent: reaching its error proves config parsing succeeded.
if printf '%s' "$output" | grep -qiE 'Failed to read or parse|unknown global field|unknown configuration'; then
    printf '%s\n' "$output"
    exit 1
fi
printf '%s' "$output" | grep -q "Unsupported driver 'none'"
grep -q '^CONFIG_CTRL_IFACE=y' "$O"/build/wpa_supplicant-*/wpa_supplicant/.config
[ -x "$T/usr/bin/wpa_cli" ] || [ -x "$T/usr/sbin/wpa_cli" ]
echo 'Native ARM64 generated Wi-Fi config parsing: PASS'
echo 'Compiled Unix control interface and diagnostic wpa_cli: PASS'
