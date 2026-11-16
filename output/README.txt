Streamer — Pi Zero 2 W 64-bit image, revision r9 (2026-11-16), not yet run on a real Pi

IMAGE FILE:  streamer-zero2w-r9.img.xz   (checksums: SHA256SUMS)
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
Connect device, a Bluetooth speaker and a UPnP/DLNA network player.

WHAT CHANGED IN r9
- Network player (UPnP/DLNA). A UPnP app on the same Wi-Fi, such as BubbleUPnP on Android, sees
  "Streamer" as a player and sends it music: local files, or a streaming service the app supports
  (its makers list TIDAL and Qobuz). Unlike Bluetooth, the file itself is sent, and Streamer
  passes it to the DAC in the file's own sample rate and bit depth. It converts only if the DAC
  does not accept that format. The app's volume slider sets the DAC's volume one-to-one.
  Inside: upmpdcli 1.9.7 (what the network sees) and MPD 0.24.15 (plays). Neither runs as root,
  and MPD cannot be reached from the network.
- The status page shows "UPnP" as a source, with the format of the file being played.
- A fault in MPD, found while testing: a volume change could leave one channel silent (3 of 150
  changes in the emulator). Fixed in this image (0 of 450).

WHAT CHANGED IN r8
- One fix. r7's reset of a UB500 that did not start switched the dongle's hub port off and
  then could not switch it back on (it addressed the port through the dongle's own entry,
  which is gone once the port is off). The dongle then stayed off until the next power-on.
  r8 addresses the port through the hub.

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
- validation.txt        21 host-side tests of the scripts and settings.
- image-checks.txt      unit verification, filesystem checks, boot partition contents, and a
                        search of the image for keys.
- module-validation.txt the image's own module loader decodes the Wi-Fi, USB-audio and
                        Bluetooth drivers.
- wifi-validation.txt   the Wi-Fi config generated on the image is accepted by its wpa_supplicant.
- ldac-validation.txt   the image's Bluetooth receiver lists LDAC; the image's LDAC library
                        decodes what it encoded at 44.1, 48, 88.2 and 96 kHz and at all three
                        bit rates, with no decode errors.
- review/qemu-r9.txt    the image booted three times in QEMU (raspi3b machine, Zero 2 W device
                        tree, emulated USB sound and network cards), 51 of 51 checks passed:
                          1. as published: SSH off, port 22 closed, no key anywhere on the
                             card, all services up, the Bluetooth receiver running with LDAC
                             enabled, status page, Avahi, AirPlay, Spotify, DHCP lease.
                             Network player, used from outside like a phone app: found by a
                             UPnP search as "Streamer"; volume 40/75/100 sets the sound card
                             to 40/75/100% on both channels; a 16-bit/48 kHz FLAC file plays
                             to its end with the sound card opened in that format; 496,225
                             of the file's 576,000 sample frames were recorded at the
                             emulated sound card, every one identical to the file (the
                             emulator lost the rest);
                          2. ssh_password set: host keys created, a real SSH login with the
                             password works, a wrong password and a password-less login are
                             refused, the debug report hides both passwords;
                          3. same card again: same host keys, login still works.

ON A REAL PI ZERO 2 W (2026-11-14)
r7, flashed: boot, Wi-Fi, streamer.local, status page, read-only system, no failed service,
SSH password login, AirPlay and Spotify advertised, Bluetooth on the UB500, and LDAC from an
Android phone through the JM7MAX at 96 kHz / 32-bit: about 1,025 kbps received (990 kbps of
audio plus overhead), no lost packets, one decode error early in the session and none after.
Volume: phone at 81% -> DAC at 81% (-14 dB).
r8's fix, run on that Pi: told that the working dongle had not started, the script switched
its hub port off and on; the dongle re-appeared 3.4 s later, loaded its firmware, was selected
again and offered LDAC.

NOT YET CONFIRMED
- r9 has not been flashed. Its network player has only run in the emulator: not on the Pi, not
  with the JM7MAX, not with BubbleUPnP or any other real app, not with a streaming service or an
  HTTPS stream, and not above 48 kHz.
- r8 has not been flashed either; it differs from r7 only in the dongle reset script, and r9
  contains it.
- The reset after a real failed start: the fault cannot be forced. The same port reset, done
  by hand on r6 after a real failed start, brought the dongle up at the first try.
- AirPlay and Spotify Connect playback (last heard on r5).
- Bluetooth from a Mac (AAC) and SSH staying off with a short password (both seen on r6).
Known cosmetic issue: non-ASCII characters in a Bluetooth device name show as escape codes on
the status page.

SOURCE AND LICENSES
The image is built by Buildroot 2026.08.1 from this repository; ./build.sh downloads the exact
source of every package in it. It contains software under the GPL, LGPL, Apache and other
licenses (Linux, BusyBox, systemd, BlueZ, FFmpeg, LDAC, ...) and vendor firmware for the Pi, its
Wi-Fi and Bluetooth chip and the Realtek dongle. "make legal-info" in the Buildroot tree lists
every package with its license and source.
