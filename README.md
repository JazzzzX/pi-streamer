# Streamer

A small network audio receiver built on a Raspberry Pi Zero 2 W. It appears on the
network as **Streamer** and plays through a USB DAC:

- **AirPlay 2** (shairport-sync 5.6.3 + nqptp)
- **Spotify Connect** (librespot 0.8.0, up to 320 kbps)
- **Bluetooth** receiver (SBC, AAC, aptX, aptX HD)
- a view-only **status page** at `http://streamer.local/`

## Quick start: download the image and flash it

You don't need to build anything. A ready-made SD-card image is attached to the
[r6 release](https://github.com/JazzzzX/pi-streamer/releases/tag/r6).

1. Download
   [`streamer-zero2w-r6.img.xz`](https://github.com/JazzzzX/pi-streamer/releases/download/r6/streamer-zero2w-r6.img.xz)
   (60 MB).
2. Flash it to a microSD card (1 GB or larger) with
   [Raspberry Pi Imager](https://www.raspberrypi.com/software/) ("Use custom") or
   balenaEtcher. No need to unzip it; skip Imager's OS customisation.
3. Open the `STREAMER` drive that appears on your computer and edit `streamer.txt`:
   your Wi-Fi name (`ssid`), password (`psk`) and `country`.
4. Put the card in the Pi, connect the DAC to its USB data port (through a USB 2.0 hub
   if you also use a Bluetooth dongle), and power it on.
5. After about a minute, **Streamer** shows up as an AirPlay speaker, a Spotify Connect
   device and a Bluetooth speaker, and `http://streamer.local/` shows its status.

The image is a pre-release: it passed every emulator test but has not yet been booted
on a real Pi. The details are below.

The system is a custom [Buildroot](https://buildroot.org) image, about 160 MB of
contents, with read-only system and boot partitions. Pairings and the Spotify login
live on a small writable data partition.

## Hardware it was built for

| Part | Notes |
| --- | --- |
| Raspberry Pi Zero 2 W | 64-bit, 2.4 GHz Wi-Fi only |
| JCally JM7MAX USB-C DAC | USB ID `06cb:1595`; shows its volume control as `PCM` or `Headset` |
| TP-Link UB500 Bluetooth dongle | Optional. Realtek RTL8761BU. The built-in radio shares its chip with Wi-Fi and dropped audio badly in testing. |
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

## Layout

| Path | Contents |
| --- | --- |
| `br2-streamer/` | Buildroot external tree: defconfig, `librespot` package, board files, root filesystem overlay (units, scripts, status page) |
| `br2-streamer/board/streamer/streamer.txt` | The settings file that ends up on the boot partition |
| `buildroot-backports/` | `shairport-sync`, `nqptp` and `libplist` package files taken from Buildroot master (commit `dc102467`), because 2026.08.1 only has shairport-sync 4.3.7 |
| `status-page/` | Source of the status page; the overlay holds an identical copy (a test checks this) |
| `Dockerfile`, `build.sh`, `run.sh` | Build container, the build itself, and a helper to run commands in the Buildroot tree |
| `test-streamer.py` | 17 host-side tests of the scripts and settings |
| `check-image-modules.sh`, `check-image-wifi.sh` | Checks run against the built image with its own ARM64 binaries |
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
`output/streamer-zero2w.img`. A first build takes one to two hours or more, most of it
downloading and compiling. It was last run from an empty volume on an Apple Silicon
Mac (Colima, 8 CPUs, 12 GB).

Later runs reuse the volume and pick up changes to the root filesystem overlay. Other
changes need one package rebuilt first; the comments at the top of `build.sh` list
which. `./run.sh '<command>'` runs a command inside the Buildroot tree.

## Tests

```sh
python3 test-streamer.py          # scripts and settings; no Pi, no network

# against the built image, using its own ARM64 binaries
docker run --rm -u0 -v streamer-br:/work -v "$PWD/check-image-modules.sh:/c.sh:ro" streamer-br-builder bash /c.sh
docker run --rm -u0 -v streamer-br:/work -v "$PWD/check-image-wifi.sh:/c.sh:ro"    streamer-br-builder bash /c.sh

# boot the image in QEMU; exit status 0 means every check passed
docker build -t streamer-qemu qemu-test
docker run --rm -u0 -v streamer-br:/work -v "$PWD/qemu-test/boot-test.py:/boot-test.py:ro" streamer-qemu python3 /boot-test.py
```

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
- The UB500 sometimes fails its firmware download at power-on. `bt-select` re-probes
  it up to three times, then falls back to the built-in radio.
- Only one mDNS responder may run. librespot uses Avahi (`with-avahi`), and
  systemd-resolved's mDNS is off; otherwise the Pi can come up as `streamer-2.local`.
- BusyBox 1.38 httpd with CGI enabled returns 404 for `/` unless basic-auth support
  is compiled in.
- Bluetooth video lag: `bluealsa-aplay` with a 200 ms buffer and 50 ms period.

## Status

r6 is the first image with nothing personal built in, and the one published under
Releases. It passed the tests above, including the three QEMU boots with a real SSH
password login, but it has not yet been booted on a real Pi.

Its predecessor r5 was flashed and ran on the Pi on 2026-11-13: Wi-Fi,
`streamer.local`, the status page, AirPlay, Spotify Connect and Bluetooth on the UB500
all came up, with no failed services. r6 differs from r5 in the SSH setup, in how the
Pi identifies itself to the router, and in one line of the status page.

The Bluetooth dongle recovery has only been exercised by simulating a dead dongle on
the Pi, because the real failure is intermittent.
