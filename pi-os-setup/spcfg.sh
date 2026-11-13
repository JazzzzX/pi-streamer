#!/bin/bash
set -euo pipefail
C=/etc/raspotify/conf
cp -n $C /etc/raspotify/conf.orig
sed -i 's/^LIBRESPOT_ENABLE_VOLUME_NORMALISATION=/#LIBRESPOT_ENABLE_VOLUME_NORMALISATION=/' $C
sed -i '/^# --- Streamer overrides ---/,$d' $C
cat >> $C <<'CONF'
# --- Streamer overrides ---
LIBRESPOT_NAME="Streamer"
LIBRESPOT_BITRATE=320
LIBRESPOT_BACKEND=alsa
LIBRESPOT_DEVICE=hw:CARD=JM7MAX
LIBRESPOT_MIXER=alsa
LIBRESPOT_ALSA_MIXER_DEVICE=hw:CARD=JM7MAX
LIBRESPOT_ALSA_MIXER_CONTROL=PCM
CONF
systemctl restart raspotify
sleep 5
systemctl is-active raspotify
journalctl -u raspotify -n 6 --no-pager | cut -c1-170
