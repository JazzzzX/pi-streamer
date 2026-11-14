Streamer — Pi Zero 2 W 64-bit image, revision r6 (2026-11-14)

IMAGE FILE:  streamer-zero2w-r6.img.xz   (checksums: SHA256SUMS)
Flash with Raspberry Pi Imager -> Use custom, or balenaEtcher. No need to unzip. Skip OS
customisation.

After flashing, open the STREAMER drive and edit streamer.txt:
  ssid, psk, country   your 2.4 GHz Wi-Fi
  bluetooth            auto | usb | builtin | off
  ssh_password         empty = SSH off; 8 or more characters = SSH on with that password
  debug                1 = save streamer-log.txt on this drive for troubleshooting
Save, eject. Pi's USB data port -> USB 2.0 hub -> JCally JM7MAX DAC (+ optional TP-Link
UB500 Bluetooth dongle). Power on PWR IN.

After about a minute: http://streamer.local/ and "Streamer" as an AirPlay speaker, a Spotify
Connect device and a Bluetooth speaker.

NOTHING PERSONAL IS IN THE IMAGE
- No SSH host keys and no login keys. A card creates its own host keys the first time SSH is
  switched on and keeps them on its data partition.
- The root password is locked. SSH (login: root) works only with ssh_password set.
- streamer.txt ships with placeholders; it is readable by root only on the running system.

WHAT CHANGED IN r6
- SSH: password login set in streamer.txt, off by default, per-card host keys. r5 and earlier
  had fixed host keys and one fixed login key built in, so they were never published.
- The Pi now identifies itself to the router by its hardware address, so it keeps the same IP
  address across reboots (before, the address could change at every boot).
- The status page shows whether SSH is running.
- Built with ./build.sh from an empty build volume, i.e. from a fresh checkout.
Unchanged from r5: AirPlay 2 (shairport-sync 5.6.3 + nqptp 1.2.9), Spotify Connect (librespot
0.8.0, up to 320 kbps, needs Premium), Bluetooth receiver (SBC, AAC, aptX, aptX HD; not aptX
Lossless or LDAC), the UB500 recovery, the Wi-Fi handshake fix, read-only system and boot
partitions with a small writable data partition.

HOW THIS IMAGE FILE WAS CHECKED (details in this folder)
- validation.txt        17 host-side tests of the scripts and settings.
- module-validation.txt the image's own module loader decodes the Wi-Fi, USB-audio and
                        Bluetooth drivers.
- wifi-validation.txt   the Wi-Fi config generated on the image is accepted by its wpa_supplicant.
- image-checks.txt      unit verification, filesystem checks, boot partition contents, and a
                        search of the image for keys.
- review/qemu-r6.txt    the image booted three times in QEMU (raspi3b machine, Zero 2 W device
                        tree, emulated USB sound and network cards):
                          1. as published: SSH off, port 22 closed, no key anywhere on the
                             card, all services up, status page, Avahi, AirPlay, Spotify,
                             Bluetooth service chain, DHCP lease;
                          2. ssh_password set: host keys created, a real SSH login with the
                             password works, a wrong password and a password-less login are
                             refused, the debug report hides both passwords;
                          3. same card again: same host keys, login still works.

NOT CHECKED
- r6 has not been booted on a real Pi yet. The emulator has no Wi-Fi chip, no Bluetooth radio
  and no JM7MAX DAC. r5, which differs from r6 only in the points listed above, was flashed and
  ran on the Pi on 2026-11-13 with Wi-Fi, AirPlay, Spotify and Bluetooth working.
- The UB500 recovery has not yet met a real failed power-on; it was exercised on the Pi by
  making the script treat the working dongle as dead.

SOURCE AND LICENSES
The image is built by Buildroot 2026.08.1 from this repository; ./build.sh downloads the exact
source of every package in it. It contains software under the GPL, LGPL and other licenses
(Linux, BusyBox, systemd, BlueZ, FFmpeg, ...) and vendor firmware for the Pi, its Wi-Fi and
Bluetooth chip and the Realtek dongle. "make legal-info" in the Buildroot tree lists every
package with its license and source.
