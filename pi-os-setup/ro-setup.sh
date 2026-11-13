#!/bin/bash
set -euo pipefail
exec >>/home/pi/ro-setup.log 2>&1
echo "== start $(date)"
cp -n /boot/firmware/cmdline.txt /home/pi/cmdline.txt.before-overlay
cp -n /etc/fstab /home/pi/fstab.before-overlay
grep -E "auto_initramfs|^initramfs" /boot/firmware/config.txt || echo "no initramfs line in config.txt"
export DEBIAN_FRONTEND=noninteractive
raspi-config nonint enable_overlayfs
echo "== overlayfs step rc=$? $(date)"
raspi-config nonint enable_bootro
echo "== bootro step rc=$?"
sync
echo "-- cmdline now:"; cat /boot/firmware/cmdline.txt
echo "-- fstab now:"; grep -v '^#' /etc/fstab
echo "-- initramfs files:"; ls -la /boot/firmware/initramfs* 2>&1
dpkg -l overlayroot | tail -1
echo "== DONE $(date)"
