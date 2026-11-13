Streamer — Pi Zero 2 W 64-bit image, revision r5 (2026-11-13)

FLASH THIS FILE:  streamer-zero2w-20261113-r5.img.xz
(Raspberry Pi Imager -> Use custom, or balenaEtcher. No need to unzip. Skip OS customisation.)

After flashing, open the STREAMER drive and edit streamer.txt: ssid, psk, country, bluetooth.
Save, eject. Pi's USB data port -> USB 2.0 hub -> JCally JM7MAX + TP-Link UB500. Power on PWR IN.

Web status: http://streamer.local/      SSH: ssh -i ~/.ssh/id_ed25519 root@streamer.local
Login is key-only (this Mac's id_ed25519 key). The SSH host keys in this private image are
the same on every copy: do not distribute this image to other people without replacing them.

IF IT DOES NOT APPEAR ON THE NETWORK
Set debug=1 in streamer.txt. About 1 and 4 minutes after power-on the Pi saves a report as
streamer-log.txt on the STREAMER drive (Wi-Fi state, networks seen, services, kernel
messages; the Wi-Fi password is never written). Wait 5 minutes, then read it on the Mac.
No streamer-log.txt at all means the Pi did not finish booting: connect HDMI.

WHAT CHANGED IN r5 (both found on the real Pi)
- Wi-Fi: r4 associated with the router and then timed out ("Authentication with ... timed
  out"). wpa_supplicant 2.12 waits for a handshake-offload event that the Pi kernel's
  brcmfmac driver never sends. cmdline.txt now has brcmfmac.feature_disable=0x82000, so
  wpa_supplicant does the WPA2 handshake itself.
- Bluetooth: on some boots the UB500's firmware download fails ("RTL: download fw command
  failed"), and r4 then switched the built-in radio off as well. The radio script now
  re-probes such a dongle (up to 3 times per boot) and otherwise falls back to the
  built-in radio (with bluetooth=auto).
- debug is 0 by default; the status page no longer lists masked units.
Earlier revisions (r1 to r4) had the defects fixed above and are not kept.

INCLUDED
- AirPlay 2: shairport-sync 5.6.3 + nqptp 1.2.9.
- Spotify Connect: librespot 0.8.0, up to 320 kbps, discovery through Avahi. Requires Premium.
- Bluetooth receiver: SBC, AAC, aptX, aptX HD (not aptX Lossless or LDAC).
  bluetooth=auto prefers a USB adapter (UB500), otherwise the built-in radio.
  Each radio has its own address: pair again after switching radios.
- Bluetooth video-lag fix: 200 ms PCM buffer, 50 ms period.
- Automatic PCM/Headset volume-control detection (software volume if the DAC has neither),
  DAC hot-plug restart.
- Read-only status page (refreshes every 5 s while open).
- Root and boot partitions read-only; pairings and Spotify credentials on a small writable
  data partition. With debug=1 the boot partition is briefly made writable twice per boot.

HOW THIS IMAGE FILE WAS CHECKED (details in this folder)
- validation.txt        13 host-side tests of the scripts and settings.
- module-validation.txt the image's own module loader decodes the Wi-Fi, USB-audio and
                        Bluetooth drivers.
- wifi-validation.txt   the Wi-Fi config generated on the image is accepted by its wpa_supplicant.
- image-checks.txt      unit verification, filesystem checks, boot partition contents.
- review/qemu-r5.txt    this image booted in QEMU (raspi3b, Zero 2 W device tree) with an
                        emulated USB sound card renamed JM7MAX and an emulated network card:
                        mounts, SSH, status page, Avahi (streamer.local), nqptp, AirPlay
                        (port 7000), Spotify (zeroconf published), the Bluetooth service chain.

SEEN WORKING ON THE REAL PI (2026-11-13)
- This r5 file, flashed and booted: Wi-Fi joined (WPA2, -46 dBm), streamer.local, SSH,
  status page, AirPlay and Spotify advertised, sound playing through the JCally (PCM volume
  control), UB500 firmware loaded and the radio discoverable, a pairing stored on /data,
  system and boot partitions read-only, no failed services.
- Before that, on the r4 card with the two r5 fixes applied by hand: the same, plus the
  debug report and the UB500 coming back after a re-probe.

NOT YET SEEN
- The Bluetooth recovery during a real failed power-on: that failure is intermittent. It was
  exercised on the Pi by making the script treat the working dongle as dead.
Keep the Raspberry Pi OS card as the fallback.

Sources: ../br2-streamer/ ../status-page/ ../qemu-test/   Rebuild: ../build-updated.sh
