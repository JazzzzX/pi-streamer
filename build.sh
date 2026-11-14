#!/bin/bash
# Build the Streamer SD-card image in a Linux container. Works from a fresh clone.
# The Buildroot tree, downloads and build output live in the Docker volume "streamer-br"
# (about 20 GB); the finished image is copied to output/.
#
# After the first build, plain re-runs pick up changes to the root filesystem overlay.
# Other changes need the package rebuilt first, inside the container (see run.sh):
#   board/streamer/cmdline.txt or config.txt  ->  make O=/work/out rpi-firmware-rebuild
#   board/streamer/busybox.fragment           ->  make O=/work/out busybox-reconfigure
#   board/streamer/linux.fragment             ->  make O=/work/out linux-reconfigure
#   package options in the defconfig          ->  make O=/work/out <package>-reconfigure
set -euo pipefail
cd "$(dirname "$0")"
BUILDROOT_TAG=2026.08.1
BUILDROOT_COMMIT=7fdeadb3b9f12f78e5fccca914d7fef47090ab9a

docker build -q -t streamer-br-builder . >/dev/null
docker volume create streamer-br >/dev/null
docker run --rm -u 0 -v streamer-br:/work streamer-br-builder chown 1000:1000 /work
docker run --rm \
  -v streamer-br:/work \
  -v "$PWD/br2-streamer:/br2-streamer:ro" \
  -v "$PWD/buildroot-backports:/backports:ro" \
  -e BUILDROOT_TAG="$BUILDROOT_TAG" -e BUILDROOT_COMMIT="$BUILDROOT_COMMIT" \
  streamer-br-builder bash -ec '
  cd /work
  [ -d buildroot ] || git clone -q --depth 1 --branch "$BUILDROOT_TAG" https://gitlab.com/buildroot.org/buildroot.git
  cd buildroot
  test "$(git rev-parse HEAD)" = "$BUILDROOT_COMMIT"
  # shairport-sync 5.x, nqptp and the libplist host package come from Buildroot master
  for pkg in shairport-sync nqptp libplist; do
    cp -a /backports/$pkg/. package/$pkg/
  done
  make O=/work/out BR2_EXTERNAL=/br2-streamer streamer_zero2w_defconfig
  make O=/work/out
'
mkdir -p output
docker run --rm -v streamer-br:/work -v "$PWD/output:/out" streamer-br-builder \
  cp /work/out/images/sdcard.img /out/streamer-zero2w.img
echo "Image: output/streamer-zero2w.img"
