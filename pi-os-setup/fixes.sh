#!/bin/bash
set -euo pipefail
# 1. memory-only swap (the default zram+file needs a file on the card, which read-only mode blocks)
mkdir -p /etc/rpi/swap.conf.d
cat > /etc/rpi/swap.conf.d/90-zram-only.conf <<'CONF'
# Streamer: RAM-only compressed swap, so it still works with the read-only overlay
[Main]
Mechanism=zram
CONF
# 2. restart AirPlay + Spotify whenever the JM7MAX DAC becomes ready
cat > /usr/local/sbin/dac-ready.sh <<'SH'
#!/bin/sh
# Run by udev (99-streamer-dac.rules) when the JCally JM7MAX DAC is ready.
/usr/bin/systemctl reset-failed raspotify.service shairport-sync.service 2>/dev/null
/usr/bin/systemctl --no-block restart shairport-sync.service raspotify.service
SH
chmod 755 /usr/local/sbin/dac-ready.sh
cat > /etc/udev/rules.d/99-streamer-dac.rules <<'RULE'
# Streamer: when the JCally JM7MAX USB DAC is plugged in and initialised, (re)start the players on it
ACTION=="change", SUBSYSTEM=="sound", KERNEL=="card*", ENV{SOUND_INITIALIZED}=="1", ENV{ID_VENDOR_ID}=="06cb", ENV{ID_MODEL_ID}=="1595", RUN+="/usr/local/sbin/dac-ready.sh"
RULE
udevadm control --reload
systemctl daemon-reload
echo "== swap unit after reload"; systemctl show dev-zram0.swap -p Description -p After | cut -c1-200
ls /run/systemd/generator/ | grep -iE 'swap|zram|loop' | tr '\n' ' '; echo
echo FIXES-WRITTEN
