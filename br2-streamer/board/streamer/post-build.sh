#!/bin/sh
# Streamer post-build: secrets, read-only fstab, locked root password, enabled services.
set -eu
T="${TARGET_DIR}"
S="${BR2_EXTERNAL_STREAMER_PATH}/board/streamer/secrets"

# Executable scripts and view-only web files
chmod 0755 "$T"/usr/libexec/streamer/* "$T"/usr/share/streamer-www/cgi-bin/status
chmod 0644 "$T"/usr/share/streamer-www/index.html

# SSH host keys + authorized key (root login by key only)
install -d -m 0700 "$T/root/.ssh"
install -m 0600 "$S/authorized_keys" "$T/root/.ssh/authorized_keys"
for k in ed25519 ecdsa rsa; do
	install -m 0600 "$S/ssh_host_${k}_key" "$T/etc/ssh/ssh_host_${k}_key"
	install -m 0644 "$S/ssh_host_${k}_key.pub" "$T/etc/ssh/ssh_host_${k}_key.pub"
done

# Lock root's password (console login disabled; SSH key still works)
sed -i 's|^root:[^:]*:|root:*:|' "$T/etc/shadow"

# Mounts: rootfs stays read-only (kernel "ro"); /boot read-only FAT; /data small writable ext4
mkdir -p "$T/boot" "$T/data"
sed -i '/[[:space:]]\/boot[[:space:]]/d; /[[:space:]]\/data[[:space:]]/d' "$T/etc/fstab"
cat >> "$T/etc/fstab" <<'FSTAB'
/dev/mmcblk0p1	/boot	vfat	ro,nofail,umask=0022	0	0
/dev/mmcblk0p3	/data	ext4	defaults,noatime,nofail,x-systemd.device-timeout=15s	0	2
FSTAB

# No SysV init scripts under systemd
rm -f "$T"/etc/init.d/S*nqptp "$T"/etc/init.d/S*shairport-sync

# Use our units instead of the packaged BlueALSA ones
for u in bluealsa.service bluealsa-aplay.service; do
	[ -e "$T/usr/lib/systemd/system/$u" ] && ln -sf /dev/null "$T/etc/systemd/system/$u"
done

# Enable services
W="$T/etc/systemd/system/multi-user.target.wants"
mkdir -p "$W"
# (renamed units from earlier builds)
rm -f "$T/etc/systemd/system/bt-discoverable.service" "$W/bt-discoverable.service"
# (Buildroot runs "systemctl preset-all" afterwards, which enables every unit from its
#  [Install] section; these links only document the intent. Disabled units: see
#  /etc/systemd/system-preset/10-streamer.preset.)
for u in streamer-wifi nqptp shairport-sync librespot bt-agent bt-select \
	streamer-bluealsa streamer-bluealsa-aplay streamer-status streamer-data streamer-debug-log; do
	ln -sf "../$u.service" "$W/$u.service"
done
for u in systemd-networkd systemd-resolved systemd-timesyncd systemd-time-wait-sync \
	avahi-daemon bluetooth sshd; do
	f=""
	for d in usr/lib/systemd/system lib/systemd/system; do
		[ -e "$T/$d/$u.service" ] && f="/$d/$u.service" && break
	done
	if [ -n "$f" ]; then ln -sf "$f" "$W/$u.service"; else echo "post-build: WARNING unit $u.service not found" >&2; fi
done
# networkd needs network-online for shairport/librespot ordering
if [ -e "$T/usr/lib/systemd/system/systemd-networkd-wait-online.service" ]; then
	mkdir -p "$T/etc/systemd/system/network-online.target.wants"
	ln -sf /usr/lib/systemd/system/systemd-networkd-wait-online.service \
		"$T/etc/systemd/system/network-online.target.wants/systemd-networkd-wait-online.service"
fi
