#!/bin/bash
# Rebuild with the existing Linux Docker volume and pinned package backports.
set -euo pipefail
cd "$(dirname "$0")"
docker run --rm \
  -v streamer-br:/work \
  -v "$PWD/br2-streamer:/br2-streamer:ro" \
  -v "$PWD/buildroot-backports:/backports:ro" \
  -w /work/buildroot streamer-br-builder bash -ec '
  test "$(git rev-parse HEAD)" = 7fdeadb3b9f12f78e5fccca914d7fef47090ab9a
  for pkg in shairport-sync nqptp libplist; do
    cp -a /backports/$pkg/. package/$pkg/
  done
  make O=/work/out BR2_EXTERNAL=/br2-streamer streamer_zero2w_defconfig
  make O=/work/out busybox-reconfigure bluez5_utils-reconfigure wpa_supplicant-reconfigure kmod-reconfigure rpi-firmware-rebuild librespot-rebuild
  make O=/work/out
'
# The firmware/config and kernel rebuild targets are additionally needed if
# config.txt/cmdline.txt or linux.fragment change (as in the initial build).
