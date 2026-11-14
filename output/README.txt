Streamer — Pi Zero 2 W 64-bit image, revision r7 (2026-11-14), not yet run on a real Pi

IMAGE FILE:  streamer-zero2w-r7.img.xz   (checksums: SHA256SUMS)
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

WHAT CHANGED IN r7
- LDAC: the Bluetooth receiver now accepts LDAC (up to 96 kHz, 990 kbps) next to SBC, AAC,
  aptX and aptX HD. Use a USB Bluetooth dongle for it: the Pi's built-in radio carried LDAC
  cleanly only at its lowest rate (330 kbps); the UB500 carried 990 kbps without losses.
  On an Android phone choose LDAC in the device's Bluetooth settings, and "Optimised for audio
  quality (990 kbps)" in Developer options for the full rate. Apple devices do not send LDAC.
- Bluetooth volume: the phone's slider now sets the DAC's volume one-to-one (40% on the phone
  is 40% on the DAC). Before, the DAC stayed within 10 dB of full output for the whole upper
  half of the slider, which was very loud.
- UB500 that does not start at power-on: Streamer now resets it by switching its hub port off
  and on. The software re-plug of r6 failed on the real fault; the port reset, done by hand on
  the Pi, brought the dongle up at the first try.
Unchanged from r6: AirPlay 2 (shairport-sync 5.6.3 + nqptp 1.2.9), Spotify Connect (librespot
0.8.0, up to 320 kbps, needs Premium), SSH by password from streamer.txt (off by default),
no keys or passwords built in, read-only system and boot partitions with a small writable
data partition.

LDAC: SOURCE, LICENSE, TRADEMARK
The LDAC code is Sony's library as published by the openvela project
(https://github.com/open-vela/external_libldac, commit 5b4bf660) under the Apache License 2.0.
Its LICENSE and NOTICE are in the image under /usr/share/licenses/libldac. LDAC is a trademark
of Sony Corporation. This project is not affiliated with Sony and the image is not certified by
Sony; the NOTICE says that products using LDAC need Sony's certification.

HOW THIS IMAGE FILE WAS CHECKED (details in this folder)
- validation.txt        20 host-side tests of the scripts and settings.
- image-checks.txt      unit verification, filesystem checks, boot partition contents, and a
                        search of the image for keys.
- module-validation.txt the image's own module loader decodes the Wi-Fi, USB-audio and
                        Bluetooth drivers.
- wifi-validation.txt   the Wi-Fi config generated on the image is accepted by its wpa_supplicant.
- ldac-validation.txt   the image's Bluetooth receiver lists LDAC; the image's LDAC library
                        decodes what it encoded at 44.1, 48, 88.2 and 96 kHz and at all three
                        bit rates, with no decode errors.
- review/qemu-r7.txt    the image booted three times in QEMU (raspi3b machine, Zero 2 W device
                        tree, emulated USB sound and network cards), 41 of 41 checks passed:
                          1. as published: SSH off, port 22 closed, no key anywhere on the
                             card, all services up, the Bluetooth receiver running with LDAC
                             enabled, status page, Avahi, AirPlay, Spotify, DHCP lease;
                          2. ssh_password set: host keys created, a real SSH login with the
                             password works, a wrong password and a password-less login are
                             refused, the debug report hides both passwords;
                          3. same card again: same host keys, login still works.

NOT CHECKED
- r7 has not been booted on a real Pi. The emulator has no Wi-Fi chip, no Bluetooth radio and
  no JM7MAX DAC, so these parts of r7 are untested on hardware: LDAC from a phone through this
  decoder, the new volume mapping, and the automatic hub port reset.
- r6, which r7 is built on, ran on the Pi on 2026-11-14: Wi-Fi, status page, SSH password
  login, AirPlay and Spotify advertised, Bluetooth audio from a Mac (AAC). LDAC was tried on it
  with a hand-installed receiver and a different LDAC decoder.
- AirPlay and Spotify Connect playback were last heard on r5.

SOURCE AND LICENSES
The image is built by Buildroot 2026.08.1 from this repository; ./build.sh downloads the exact
source of every package in it. It contains software under the GPL, LGPL, Apache and other
licenses (Linux, BusyBox, systemd, BlueZ, FFmpeg, LDAC, ...) and vendor firmware for the Pi, its
Wi-Fi and Bluetooth chip and the Realtek dongle. "make legal-info" in the Buildroot tree lists
every package with its license and source.
