# Streamer

A small network audio receiver built on a Raspberry Pi Zero 2 W. It appears on the
network as **Streamer** and plays through a USB DAC:

- **AirPlay 2** (shairport-sync 5.6.3 + nqptp)
- **Spotify Connect** (librespot 0.8.0, up to 320 kbps)
- **Bluetooth** receiver (SBC, AAC, aptX, aptX HD, and LDAC with a USB Bluetooth dongle)
- a view-only **status page** at `http://streamer.local/`

## Quick start: download the image and flash it

You don't need to build anything. A ready-made SD-card image is attached to the
[r7 release](https://github.com/JazzzzX/pi-streamer/releases/tag/r7).

1. Download
   [`streamer-zero2w-r7.img.xz`](https://github.com/JazzzzX/pi-streamer/releases/download/r7/streamer-zero2w-r7.img.xz)
   (62 MB).
2. Flash it to a microSD card (1 GB or larger) with
   [Raspberry Pi Imager](https://www.raspberrypi.com/software/) ("Use custom") or
   balenaEtcher. No need to unzip it; skip Imager's OS customisation.
3. Open the `STREAMER` drive that appears on your computer and edit `streamer.txt`:
   your Wi-Fi name (`ssid`), password (`psk`) and `country`.
4. Put the card in the Pi, connect the DAC to its USB data port (through a USB 2.0 hub
   if you also use a Bluetooth dongle), and power it on.
5. After about a minute, **Streamer** shows up as an AirPlay speaker, a Spotify Connect
   device and a Bluetooth speaker, and `http://streamer.local/` shows its status.

This image has been flashed and run on a real Pi Zero 2 W (see Status below).

The system is a custom [Buildroot](https://buildroot.org) image, about 160 MB of
contents, with read-only system and boot partitions. Pairings and the Spotify login
live on a small writable data partition.

## Hardware it was built for

| Part | Notes |
| --- | --- |
| Raspberry Pi Zero 2 W | 64-bit, 2.4 GHz Wi-Fi only |
| JCally JM7MAX USB-C DAC | USB ID `06cb:1595`; shows its volume control as `PCM` or `Headset` |
| TP-Link UB500 Bluetooth dongle | Optional, but needed for LDAC above its lowest rate. Realtek RTL8761BU. The built-in radio shares its chip with Wi-Fi and dropped audio badly in testing. |
| USB 2.0 hub | The Zero has one USB data port |

The DAC name `JM7MAX` is fixed in the player scripts and the udev rule. Another
DAC needs those changed.

## Settings in streamer.txt

| Setting | Meaning |
| --- | --- |
| `ssid`, `psk`, `country` | Your Wi-Fi. The Pi Zero 2 W only uses 2.4 GHz. |
| `bluetooth` | `auto` (USB dongle if plugged in, otherwise built-in), `usb`, `builtin` or `off` |
| `ssh_password` | Empty = SSH off. 8 or more characters = SSH on with that password. |
| `debug` | `1` = save a troubleshooting report on the card (see below) |

If it does not join Wi-Fi, set `debug=1` in `streamer.txt`. The Pi then saves
`streamer-log.txt` on the `STREAMER` drive 1 and 4 minutes after power-on (the Wi-Fi
password is not written to it).

SSH is off unless `ssh_password` (8 or more characters) is set in `streamer.txt`.
With it set, log in with `ssh root@streamer.local` and that password. Nothing secret
is built into the image: each card creates its own SSH host keys the first time SSH
is switched on and keeps them on its data partition.

`output/README.txt` describes the current image revision in detail.

## LDAC

Streamer receives LDAC from Android phones, at up to 96 kHz and 990 kbps. Apple
devices do not send LDAC; they use AAC.

- **Use a USB Bluetooth dongle for it.** Measured on the Pi: the Zero 2 W's built-in
  radio played LDAC cleanly only at its lowest rate, 330 kbps. At 990 kbps about a
  third of the data never arrived and playback broke up. With the TP-Link UB500,
  990 kbps at 96 kHz played with no lost packets. Other dongles have not been tried.
- **On the phone:** pair with Streamer and choose LDAC in the device's Bluetooth
  settings. For the full rate, set "Bluetooth audio LDAC codec: playback quality" to
  "Optimised for audio quality (990 kbps)" in Developer options.
- **Where the code comes from:** Sony's LDAC library as published by the openvela
  project, [open-vela/external_libldac](https://github.com/open-vela/external_libldac),
  under the Apache License 2.0. The build downloads it at a pinned commit
  (`br2-streamer/package/libldac`); none of it is in this repository. Sony itself has
  published the encoder, in Android; the decoder files are only in the openvela
  repository. The image carries the library's `LICENSE` and `NOTICE` in
  `/usr/share/licenses/libldac`.
- **Trademark and certification:** LDAC is a trademark of Sony Corporation. This
  project is not affiliated with Sony, and the image is not certified by Sony. The
  library's `NOTICE` says that products using LDAC need Sony's certification.
- **Building without it:** remove `BR2_PACKAGE_LIBLDAC=y` from the defconfig and
  `-c LDAC` from `streamer-bluealsa.service`.

## Bluetooth volume

The phone's volume slider sets the DAC's own hardware volume, on the DAC's scale: 40%
on the phone is 40% on the DAC, as `amixer set PCM 40%` would set it. Stock
`bluealsa-aplay` uses a loudness formula instead, which keeps a USB DAC within 10 dB
of full output for the whole upper half of the slider; a patch in
`br2-streamer/patches/bluez-alsa` replaces it.

## Layout

| Path | Contents |
| --- | --- |
| `br2-streamer/` | Buildroot external tree: defconfig, `librespot` and `libldac` packages, two patches for bluez-alsa, board files, root filesystem overlay (units, scripts, status page) |
| `br2-streamer/board/streamer/streamer.txt` | The settings file that ends up on the boot partition |
| `buildroot-backports/` | `shairport-sync`, `nqptp` and `libplist` package files taken from Buildroot master (commit `dc102467`), because 2026.08.1 only has shairport-sync 4.3.7 |
| `status-page/` | Source of the status page; the overlay holds an identical copy (a test checks this) |
| `Dockerfile`, `build.sh`, `run.sh` | Build container, the build itself, and a helper to run commands in the Buildroot tree |
| `test-streamer.py` | 20 host-side tests of the scripts and settings |
| `check-image-contents.sh`, `check-image-modules.sh`, `check-image-wifi.sh`, `check-image-ldac.sh` (+ `.c`) | Checks run against the built image, most of them with its own ARM64 binaries |
| `qemu-test/` | Boots the built SD image in QEMU three times and checks it from inside and over SSH |
| `output/` | Notes, checksums, resolved Buildroot config and check results for the current image. The image files themselves are not in the repository. |
| `pi-os-setup/` | Scripts from the earlier hand-built Raspberry Pi OS setup, for reference |

## Building

```sh
./build.sh
```

This needs Docker. It builds the build container, keeps the Buildroot tree, downloads
and build output in a Docker volume named `streamer-br` (about 20 GB), fetches
Buildroot 2026.08.1, copies in the three backported packages, builds, and writes
`output/streamer-zero2w.img`. It was last run from an empty volume on an Apple Silicon
Mac (Colima, 8 CPUs, 12 GB) and took 35 minutes. With slow downloads the same build
has taken many hours.

Later runs reuse the volume and pick up changes to the root filesystem overlay. Other
changes need one package rebuilt first; the comments at the top of `build.sh` list
which. `./run.sh '<command>'` runs a command inside the Buildroot tree.

## Tests

```sh
python3 test-streamer.py          # scripts and settings; no Pi, no network

# against the built image, using its own ARM64 binaries
docker run --rm -u0 -v streamer-br:/work -v "$PWD/check-image-modules.sh:/c.sh:ro" streamer-br-builder bash /c.sh
docker run --rm -u0 -v streamer-br:/work -v "$PWD/check-image-wifi.sh:/c.sh:ro"    streamer-br-builder bash /c.sh
docker run --rm -u0 -v streamer-br:/work -v "$PWD/check-image-ldac.sh:/c.sh:ro" \
  -v "$PWD/check-image-ldac.c:/check-image-ldac.c:ro" streamer-br-builder bash /c.sh

# unit files, filesystems, boot partition, nothing secret; then boot the image in QEMU.
# Exit status 0 means every check passed.
docker build -t streamer-qemu qemu-test
docker run --rm -u0 -v streamer-br:/work -v "$PWD/check-image-contents.sh:/c.sh:ro" streamer-qemu bash /c.sh
docker run --rm -u0 -v streamer-br:/work -v "$PWD/qemu-test/boot-test.py:/boot-test.py:ro" streamer-qemu python3 /boot-test.py
```

The LDAC check encodes a test signal with the image's LDAC library, decodes it again
the way the Bluetooth receiver does, and compares the result with the original, at
44.1 to 96 kHz and at all three LDAC bit rates.

The QEMU test boots one copy of the image three times: as published (SSH must be
off and no key may exist), with `ssh_password` set (a real password login must work
and a wrong password must fail), and once more (the host keys must be unchanged).
QEMU has no Wi-Fi chip, no Bluetooth radio and no JM7MAX, so those are only proven on
the Pi itself.

## Things learned the hard way

- The Pi kernel installs drivers as `.ko.xz`, so `kmod` must be built with XZ support
  (`BR2_PACKAGE_XZ=y`), or no Wi-Fi, Bluetooth or USB-audio driver loads.
- wpa_supplicant 2.12 with this kernel's `brcmfmac` associates and then times out on
  WPA2. `brcmfmac.feature_disable=0x82000` on the kernel command line fixes it.
- The UB500 sometimes fails its firmware download at power-on and then stays dead.
  Switching its hub port off and on (`/sys/bus/usb/devices/<dev>/port/disable`) brings
  it back; taking the device away and back in software (`authorized`) does not.
  `bt-select` does the port reset up to three times, then falls back to the built-in
  radio.
- Buildroot's bluez-alsa package has no LDAC option, and a package's dependencies
  cannot be extended from an external tree. `external.mk` adds `--enable-ldac` and an
  ordering rule so that `libldac` is installed first.
- The openvela LDAC library's `ldac_ABR_get_handle()` takes an argument that the
  Android one does not; bluez-alsa needs a one-line patch to build against it.
- Only one mDNS responder may run. librespot uses Avahi (`with-avahi`), and
  systemd-resolved's mDNS is off; otherwise the Pi can come up as `streamer-2.local`.
- BusyBox 1.38 httpd with CGI enabled returns 404 for `/` unless basic-auth support
  is compiled in.
- Bluetooth video lag: `bluealsa-aplay` with a 200 ms buffer and 50 ms period.

## Status

**r7 (2026-11-14)** is the released image. Compared with r6 it adds LDAC, the
one-to-one Bluetooth volume and the hub port reset for a UB500 that did not start.

**r7 on a real Pi Zero 2 W (2026-11-14), flashed from the release file:**

- boots, joins a WPA2 2.4 GHz network, `streamer.local` and the status page load, the
  system is read-only and no service has failed
- SSH password login works
- Streamer is advertised as an AirPlay speaker and a Spotify Connect device
- the UB500 is used for Bluetooth. It started normally at this power-on, so the hub
  port reset has not yet run by itself.
- LDAC from an Android phone plays through the JM7MAX at 96 kHz / 32-bit: about
  1,025 kbps received (990 kbps of audio plus Bluetooth overhead), no lost packets,
  the decoder using about 5% of one CPU core. The log shows one decode error early in
  the session and none in the minutes after.
- volume: with the phone at 81% the DAC is at 81% (-14 dB). The stock mapping would
  have put it at -3 dB.

**Seen on r6, not repeated on r7:**

- Bluetooth audio from a Mac (AAC, 44.1 kHz)
- SSH staying off with a password shorter than 8 characters
- the UB500 failing its firmware download at power-on. r6's recovery (software
  re-plug) failed three times and Streamer fell back to the built-in radio. Switching
  the hub port off and on by hand brought the dongle up at the first try; r7 does
  that by itself.
- LDAC on the built-in radio (with a hand-installed receiver and a different LDAC
  decoder than r7's): clean at 330 kbps, about a third of the data lost at 990 kbps

**Not yet confirmed on hardware:** AirPlay and Spotify Connect playback on r6 or r7
(both played on r5).

**Checks that do not need a Pi,** all passed on the r7 image: 20 host-side tests; unit
files, filesystems, boot partition and no keys or passwords; the image's module
loader, wpa_supplicant and LDAC library (round trip at 44.1 to 96 kHz); 41 of 41
checks over three boots in QEMU.

Known cosmetic issue: the status page shows non-ASCII characters in a Bluetooth device
name as escape codes (for example `\342\200\231` for a curly apostrophe).
