#!/bin/bash
# Run as root in the streamer-qemu container (it has systemd-analyze) with streamer-br
# mounted at /work.
# Checks the built image from the outside and with its own ARM64 binaries: unit files,
# filesystems, boot partition, and that nothing secret is in it.
set -euo pipefail
O=/work/out
I=$O/images
T=/work/review-rootfs
rm -rf "$T"
mkdir -p "$T"
"$O/host/sbin/debugfs" -R "rdump / $T" "$I/rootfs.ext4" >/work/review-rdump.log 2>&1
mknod -m666 "$T/dev/null" c 1 3

# this project's own unit files (not the links that enable or mask stock units)
units=$(cd "$T/etc/systemd/system" && for u in *.service; do [ -f "$u" ] && [ ! -L "$u" ] && echo "/etc/systemd/system/$u"; done)
systemd-analyze verify --root="$T" $units >/work/review-units.log 2>&1 || { cat /work/review-units.log; echo "systemd unit verification: FAIL"; exit 1; }
# the stock units of the image's newer systemd use keys this container's systemd does not know; only our own files count
if grep -F "/etc/systemd/system/" /work/review-units.log; then echo "systemd unit verification: FAIL"; exit 1; fi
echo "systemd unit verification: PASS ($(echo $units | wc -w) units)"

echo "rootfs: $("$O/host/sbin/e2fsck" -fn "$I/rootfs.ext4" 2>&1 | tail -n1 | sed 's/^[^:]*: //')"
echo "data: $("$O/host/sbin/e2fsck" -fn "$I/data.ext4" 2>&1 | tail -n1 | sed 's/^[^:]*: //')"
"$O/host/sbin/e2fsck" -fn "$I/rootfs.ext4" >/dev/null 2>&1
"$O/host/sbin/e2fsck" -fn "$I/data.ext4" >/dev/null 2>&1

echo "== boot partition"
"$O/host/bin/mdir" -b -i "$I/boot.vfat" :: | tr '\n' ' '; echo
"$O/host/bin/mtype" -i "$I/boot.vfat" ::cmdline.txt
settings=$("$O/host/bin/mtype" -i "$I/boot.vfat" ::streamer.txt | grep -vE '^#|^[[:space:]]*$' | tr -d '\r' | tr '\n' ' ')
echo "$settings"
for want in "ssid=YOUR_WIFI_NAME" "psk=YOUR_WIFI_PASSWORD" "ssh_password= " "debug=0"; do
    case "$settings" in *"$want"*) ;; *) echo "streamer.txt: expected '$want'"; exit 1 ;; esac
done

echo "== nothing secret in the root filesystem"
keys=$(find "$T" -name 'ssh_host_*' | wc -l)
auth=$(find "$T" -name 'authorized_keys*' | wc -l)
pem=$( (grep -rIl -- "PRIVATE KEY-----" "$T" 2>/dev/null || true) | wc -l)
home=$(find "$T/root" -type f | wc -l)
rootpw=$(grep '^root:' "$T/etc/shadow" | cut -d: -f2)
echo "ssh host keys: $keys   authorized_keys files: $auth   files under /root: $home"
echo "text files containing a PEM private key: $pem   (data partition: $(grep -c -a -- 'PRIVATE KEY-----' "$I/data.ext4" || true), boot partition: $(grep -c -a -- 'PRIVATE KEY-----' "$I/boot.vfat" || true))"
echo "root password field: $rootpw"
[ "$keys$auth$pem$home" = 0000 ] && [ "$rootpw" = '*' ]
grep -vE '^#|^$' "$T/etc/ssh/sshd_config" | tr '\n' ';'; echo
grep -E '/boot|/data' "$T/etc/fstab"

echo "== tools the SSH setup needs"
echo "mkpasswd: $(echo test-password | chroot "$T" /usr/bin/mkpasswd -m sha512 -P 0 | cut -c1-3)"
ls "$T/usr/bin/ssh-keygen" "$T/usr/libexec/streamer/ssh-setup" | sed "s#$T##"
tr '\n' ';' < "$T/etc/systemd/system/sshd.service.d/streamer.conf"; echo

echo "== sizes and versions"
echo "root filesystem contents: $(du -sh "$T" | cut -f1)"
chroot "$T" /usr/bin/shairport-sync -V
chroot "$T" /usr/bin/librespot --version | cut -c1-16
echo "bluealsa $(chroot "$T" /usr/bin/bluealsa --version)"
echo "PASS"
