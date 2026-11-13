# Streamer

A small network audio receiver built on a Raspberry Pi Zero 2 W. It appears on the
network as **Streamer** and plays through a USB DAC:

- **AirPlay 2** (shairport-sync 5.6.3 + nqptp)
- **Spotify Connect** (librespot 0.8.0, up to 320 kbps)
- **Bluetooth** receiver (SBC, AAC, aptX, aptX HD)
- a view-only **status page** at `http://streamer.local/`

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

## Using an image

1. Flash the `.img.xz` with Raspberry Pi Imager ("Use custom") or balenaEtcher.
2. Open the `STREAMER` drive and edit `streamer.txt`: `ssid`, `psk`, `country`,
   `bluetooth` (`auto`, `usb`, `builtin` or `off`).
3. Boot. After about a minute: `http://streamer.local/`, and Streamer shows up as an
   AirPlay speaker, a Spotify Connect device and a Bluetooth speaker.

If it does not join Wi-Fi, set `debug=1` in `streamer.txt`. The Pi then saves
`streamer-log.txt` on the `STREAMER` drive 1 and 4 minutes after power-on (the Wi-Fi
password is not written to it).

`output/README.txt` describes the current image revision (r5) in detail.

## Layout

| Path | Contents |
| --- | --- |
| `br2-streamer/` | Buildroot external tree: defconfig, `librespot` package, board files, root filesystem overlay (units, scripts, status page) |
| `br2-streamer/board/streamer/streamer.txt` | The settings file that ends up on the boot partition |
| `buildroot-backports/` | `shairport-sync`, `nqptp` and `libplist` package files taken from Buildroot master (commit `dc102467`), because 2026.08.1 only has shairport-sync 4.3.7 |
| `status-page/` | Source of the status page; the overlay holds an identical copy (a test checks this) |
| `Dockerfile`, `run.sh`, `build-updated.sh` | Build container and build commands |
| `test-streamer.py` | 13 host-side tests of the scripts and settings |
| `check-image-modules.sh`, `check-image-wifi.sh` | Checks run against the built image with its own ARM64 binaries |
| `qemu-test/` | Boots the built SD image in QEMU and inspects it |
| `output/` | Notes, checksums, resolved Buildroot config and check results for r5. The image files themselves are not in the repository. |
| `pi-os-setup/` | Scripts from the earlier hand-built Raspberry Pi OS setup, for reference |

## Building

The image was built on an Apple Silicon Mac inside a Linux container, with the
Buildroot tree and output kept in a Docker volume named `streamer-br`. These are the
steps that were used. A rebuild from a fresh clone of this repository has not been
tried.

```sh
# 1. Build container and volume
docker build -t streamer-br-builder .
docker volume create streamer-br
docker run --rm -u 0 -v streamer-br:/work streamer-br-builder chown 1000:1000 /work

# 2. Buildroot 2026.08.1 (commit 7fdeadb3b9f12f78e5fccca914d7fef47090ab9a)
docker run --rm -v streamer-br:/work streamer-br-builder \
  git clone --depth 1 --branch 2026.08.1 https://gitlab.com/buildroot.org/buildroot.git /work/buildroot

# 3. Secrets (not in the repository): SSH host keys and the key allowed to log in as root
S=br2-streamer/board/streamer/secrets; mkdir -p $S
ssh-keygen -q -t ed25519 -N "" -C streamer -f $S/ssh_host_ed25519_key
ssh-keygen -q -t ecdsa   -N "" -C streamer -f $S/ssh_host_ecdsa_key
ssh-keygen -q -t rsa -b 3072 -N "" -C streamer -f $S/ssh_host_rsa_key
cp ~/.ssh/id_ed25519.pub $S/authorized_keys

# 4. Build (copies the backports in, then runs Buildroot)
./build-updated.sh

# 5. Copy the image out of the volume
docker run --rm -v streamer-br:/work -v "$PWD/output:/out" streamer-br-builder \
  cp /work/out/images/sdcard.img /out/streamer-zero2w.img
```

`run.sh` runs a command in the build container and expects this checkout at
`~/streamer-buildroot`.

Every image built this way carries the same SSH host keys and accepts the same login
key, so an image is personal: do not hand it to someone else without new secrets.

## Tests

```sh
python3 test-streamer.py          # scripts and settings; no Pi, no network

docker run --rm -u0 -v streamer-br:/work -v "$PWD/check-image-modules.sh:/c.sh:ro" streamer-br-builder bash /c.sh
docker run --rm -u0 -v streamer-br:/work -v "$PWD/check-image-wifi.sh:/c.sh:ro"    streamer-br-builder bash /c.sh

docker build -t streamer-qemu qemu-test
docker run --rm -u0 -v streamer-br:/work -v "$PWD/qemu-test/boot-test.py:/boot-test.py:ro" streamer-qemu \
  python3 /boot-test.py bcm2710-rpi-zero-2-w.dtb "net.ifnames=0 snd_usb_audio.id=JM7MAX"
```

The QEMU boot has no Wi-Fi chip, no Bluetooth radio and no JM7MAX, so those are only
proven on the Pi itself.

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

r5 was flashed and booted on the Pi on 2026-11-13: Wi-Fi, `streamer.local`, SSH, the
status page, AirPlay, Spotify Connect and Bluetooth on the UB500 all came up, with
no failed services. The Bluetooth dongle recovery has only been exercised by
simulating a dead dongle on the Pi, because the real failure is intermittent.
