#!/bin/bash
set -euo pipefail
exec >>/home/pi/ap2build.log 2>&1
echo "== start $(date)"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends build-essential git autoconf automake libtool pkg-config \
  libpopt-dev libconfig-dev libasound2-dev avahi-daemon libavahi-client-dev libssl-dev libsoxr-dev \
  libplist-dev libsodium-dev libavutil-dev libavcodec-dev libavformat-dev uuid-dev libgcrypt20-dev xxd
mkdir -p /opt/src && cd /opt/src
rm -rf nqptp shairport-sync
git clone --depth 1 https://github.com/mikebrady/nqptp.git
cd nqptp && autoreconf -fi && ./configure --with-systemd-startup && make && make install
systemctl daemon-reload && systemctl enable --now nqptp
echo "== nqptp done $(date)"
cd /opt/src
git clone --depth 1 https://github.com/mikebrady/shairport-sync.git
cd shairport-sync && autoreconf -fi
./configure --sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl --with-systemd --with-airplay-2
make -j2
make install
echo "== shairport-sync built $(date)"
/usr/local/bin/shairport-sync -V
echo "== DONE $(date)"
