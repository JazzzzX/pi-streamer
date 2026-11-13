#!/bin/bash
set -euo pipefail
# 1) helper: print the DAC's playback volume control (name changes: "PCM" or "Headset")
cat > /usr/local/sbin/dac-mixer <<'SH'
#!/bin/sh
# Print the JCally JM7MAX playback volume control name (it shows up as "PCM" or "Headset").
CARD=JM7MAX
for n in PCM Headset Speaker Master; do
	amixer -c "$CARD" sget "$n" 2>/dev/null | grep -q 'Playback' && { echo "$n"; exit 0; }
done
amixer -c "$CARD" scontrols 2>/dev/null | sed -n "s/^Simple mixer control '\([^']*\)'.*/\1/p" | head -n1
SH
chmod 755 /usr/local/sbin/dac-mixer
# 2) shairport-sync: render the config with the live mixer name
cp -n /etc/shairport-sync.conf /etc/shairport-sync.conf.template
sed -i 's/mixer_control_name = "[^"]*"/mixer_control_name = "@MIXER@"/' /etc/shairport-sync.conf.template
mkdir -p /etc/systemd/system/shairport-sync.service.d
cat > /etc/systemd/system/shairport-sync.service.d/streamer-mixer.conf <<'U'
[Unit]
StartLimitIntervalSec=0
[Service]
ExecStartPre=/bin/sh -c 'm=$(/usr/local/sbin/dac-mixer); mkdir -p /run/streamer; sed "s/@MIXER@/$${m:-PCM}/" /etc/shairport-sync.conf.template > /run/streamer/shairport-sync.conf'
ExecStart=
ExecStart=/usr/local/bin/shairport-sync -c /run/streamer/shairport-sync.conf
Restart=always
RestartSec=5
U
# 3) raspotify: same, via an env file written just before start
mkdir -p /etc/systemd/system/raspotify.service.d
cat > /etc/systemd/system/raspotify.service.d/streamer-mixer.conf <<'U'
[Unit]
StartLimitIntervalSec=0
[Service]
ExecStartPre=/bin/sh -c 'm=$(/usr/local/sbin/dac-mixer); mkdir -p /run/streamer; echo "LIBRESPOT_ALSA_MIXER_CONTROL=$${m:-PCM}" > /run/streamer/librespot-mixer.env'
EnvironmentFile=-/run/streamer/librespot-mixer.env
Restart=always
RestartSec=10
U
systemctl daemon-reload
systemctl reset-failed raspotify shairport-sync || true
systemctl restart shairport-sync raspotify
sleep 6
echo "mixer=$(/usr/local/sbin/dac-mixer)"
systemctl is-active shairport-sync raspotify | tr '\n' ' '; echo
grep mixer_control_name /run/streamer/shairport-sync.conf; cat /run/streamer/librespot-mixer.env
journalctl -u shairport-sync -u raspotify --since '-20 sec' --no-pager | grep -iE 'warn|error|mixer' | cut -c1-150 | tail -4
