#!/bin/bash
set -euo pipefail
id shairport-sync >/dev/null 2>&1 || useradd -r -M -G audio -s /usr/sbin/nologin shairport-sync
getent group shairport-sync >/dev/null || groupadd -r shairport-sync
usermod -a -G audio shairport-sync
install -m 644 /opt/src/shairport-sync/scripts/shairport-sync.service /etc/systemd/system/shairport-sync.service
cat > /etc/shairport-sync.conf <<'CONF'
// Streamer: AirPlay 2 -> JCally JM7MAX USB DAC (full reference: /etc/shairport-sync.conf.sample)
general = {
  name = "Streamer";
  output_backend = "alsa";
};
alsa = {
  output_device = "hw:CARD=JM7MAX";
  mixer_control_name = "PCM";
};
CONF
mkdir -p /etc/NetworkManager/conf.d
printf '[connection]\nwifi.powersave = 2\n' > /etc/NetworkManager/conf.d/99-wifi-powersave-off.conf
systemctl daemon-reload
systemctl enable shairport-sync nqptp
systemctl restart NetworkManager || true
echo SETUP-OK
