#!/bin/bash
set -euo pipefail
exec >>/home/pi/ap2build.log 2>&1
echo "== resume $(date)"
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libplist-utils
cd /opt/src/shairport-sync
./configure --sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl --with-systemd --with-airplay-2
echo "== configured $(date)"
make -j2
make install
echo "== shairport-sync built $(date)"
/usr/local/bin/shairport-sync -V
echo "== DONE $(date)"
