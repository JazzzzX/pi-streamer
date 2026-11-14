#!/bin/bash
# Run as root in streamer-br-builder with streamer-br mounted at /work and this directory's
# check-image-ldac.c at /check-image-ldac.c.
# Checks LDAC with the image's own ARM64 binaries: bluealsa offers LDAC for receiving, and
# the image's LDAC library decodes what it encoded.
set -euo pipefail
O=/work/out
T=/work/ldac-image-test
rm -rf "$T"
mkdir -p "$T"
"$O/host/sbin/debugfs" -R "rdump / $T" "$O/images/rootfs.ext4" >/work/ldac-rdump.log 2>&1
mknod -m666 "$T/dev/null" c 1 3

sink=$(chroot "$T" /usr/bin/bluealsa --help | grep 'a2dp-sink:')
echo "bluealsa in the image receives:$(echo "$sink" | cut -d: -f2)"
for codec in SBC AAC aptX aptX-HD LDAC; do echo "$sink" | grep -qw -- "$codec"; done
grep -q -- '-c LDAC' "$T/etc/systemd/system/streamer-bluealsa.service"
READELF=$(ls "$O"/host/bin/*-linux-gnu-readelf | head -n1)
echo "bluealsa links: $("$READELF" -d "$T/usr/bin/bluealsa" | grep -o 'libldacBT[^]]*')"
test -s "$T/usr/share/licenses/libldac/LICENSE"
grep -q 'Certification' "$T/usr/share/licenses/libldac/NOTICE"
echo "LDAC license and notice are in the image: PASS"

CC=$(ls "$O"/host/bin/*-linux-gnu-gcc | head -n1)
"$CC" -O2 -I"$O/staging/usr/include/ldac" /check-image-ldac.c -o "$T/tmp/check-image-ldac" -lldacBT -lm
for cfg in "44100 0 80" "48000 0 80" "88200 0 80" "96000 0 80" "96000 1 60" "96000 2 20"; do
    chroot "$T" /tmp/check-image-ldac $cfg
done
echo "LDAC round trip with the image's library: PASS"
