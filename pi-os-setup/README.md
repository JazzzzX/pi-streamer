# Raspberry Pi OS setup scripts (earlier approach, kept for reference)

Before the Buildroot image existed, the same streamer was set up by hand on
Raspberry Pi OS Lite 64-bit (Debian 13 "trixie") on the Pi Zero 2 W. These are the
scripts that were copied to the Pi and run with `sudo`, in this order. They are
one-off scripts with fixed paths, not an installer.

| Script | What it did |
| --- | --- |
| `ap2build.sh`, `ap2resume.sh` | Compile nqptp and shairport-sync with AirPlay 2 (the Pi OS package is AirPlay 1 only). The first run stopped on a missing `libplist-utils`; the second installs it and finishes. |
| `ap2setup.sh` | shairport-sync service and config for the JM7MAX DAC; Wi-Fi power saving off. |
| `spcfg.sh` | raspotify (Spotify Connect) settings: 320 kbps, hardware volume. |
| `ro-setup.sh` | Read-only overlay root and read-only boot partition (`raspi-config`). |
| `fixes.sh` | RAM-only (zram) swap so swap works with the overlay; udev rule restarting the players when the DAC is plugged in. |
| `mixfix.sh` | Look up the DAC's volume control name (`PCM` or `Headset`) each time a player starts. |
| `btsetup.sh` | Bluetooth receiver (bluez-alsa, SBC/aptX/aptX HD), no-PIN pairing agent, USB-dongle-or-built-in radio choice. The radio script was later rewritten; the current one is in `../br2-streamer`. |
| `web-install.sh` | Install the status page (`../status-page`) under busybox httpd. |
