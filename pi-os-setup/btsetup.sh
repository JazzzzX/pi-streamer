#!/bin/bash
set -euo pipefail
# --- BlueZ: name, always discoverable/pairable, no PIN
cp -n /etc/bluetooth/main.conf /etc/bluetooth/main.conf.orig
python3 - <<'PY'
import re
p="/etc/bluetooth/main.conf"; s=open(p).read()
def setkey(s, sect, key, val):
    m=re.search(r"^\[%s\]\s*$"%sect, s, re.M)
    pat=re.compile(r"^#?\s*%s\s*=.*$"%re.escape(key), re.M)
    start=m.end(); nxt=re.search(r"^\[", s[start:], re.M); end=start+(nxt.start() if nxt else len(s)-start)
    body=s[start:end]
    if pat.search(body): body=pat.sub("%s = %s"%(key,val), body, count=1)
    else: body="\n%s = %s"%(key,val)+body
    return s[:start]+body+s[end:]
for k,v in [("Name","Streamer"),("Class","0x240414"),("DiscoverableTimeout","0"),("PairableTimeout","0"),("AlwaysPairable","true"),("JustWorksRepairing","always"),("FastConnectable","true")]:
    s=setkey(s,"General",k,v)
s=setkey(s,"Policy","AutoEnable","true")
open(p,"w").write(s)
PY
# --- BlueALSA: receiver only (A2DP sink) with aptX + aptX HD; player -> JM7MAX with hardware volume
mkdir -p /etc/systemd/system/bluealsa.service.d /etc/systemd/system/bluealsa-aplay.service.d
cat > /etc/systemd/system/bluealsa.service.d/streamer.conf <<'U'
[Service]
ExecStart=
ExecStart=/usr/bin/bluealsa -S -p a2dp-sink -c aptX -c aptX-HD
U
cat > /etc/systemd/system/bluealsa-aplay.service.d/streamer.conf <<'U'
[Unit]
StartLimitIntervalSec=0
[Service]
ExecStart=
ExecStart=/bin/sh -c 'exec /usr/bin/bluealsa-aplay -S --profile-a2dp --pcm=plughw:CARD=JM7MAX --mixer-device=hw:CARD=JM7MAX --mixer-name="$(/usr/local/sbin/dac-mixer)" --volume=mixer'
Restart=always
RestartSec=5
U
# --- pairing agent (auto-accept, no PIN)
cat > /etc/systemd/system/bt-agent.service <<'U'
[Unit]
Description=Bluetooth pairing agent (no PIN, auto-accept)
Requires=bluetooth.service
After=bluetooth.service
[Service]
ExecStart=/usr/bin/bt-agent -c NoInputNoOutput
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
U
# --- radio choice: UB500 (USB) if present, else built-in; others rfkill-blocked
cat > /usr/local/sbin/bt-select <<'SH'
#!/bin/sh
# Pick the Bluetooth radio (bluetooth=auto|usb|builtin|off in /boot/firmware/streamer.txt; default auto),
# block the others, make the chosen one discoverable as "Streamer".
F=/boot/firmware/streamer.txt
mode=$(sed -n 's/^bluetooth=//p' "$F" 2>/dev/null | head -n1 | tr -d '\r ')
[ -n "$mode" ] || mode=auto
usb=""; builtin=""
for h in /sys/class/bluetooth/hci*; do
	n=${h##*/}; case "$n" in *:*) continue ;; esac
	[ -e "$h/address" ] || continue
	case "$(readlink -f "$h/device")" in *usb*) usb="$usb $n" ;; *) builtin="$builtin $n" ;; esac
done
case "$mode" in
	usb) want="$usb" ;; builtin) want="$builtin" ;; off) want="" ;;
	*) if [ -n "$usb" ]; then want="$usb"; else want="$builtin"; fi ;;
esac
want=$(echo $want | awk '{print $1}')
for n in $usb $builtin; do
	v=1; [ "$n" = "$want" ] && v=0
	for r in /sys/class/bluetooth/"$n"/rfkill*/soft; do [ -e "$r" ] && echo $v > "$r"; done
done
echo "bt-select: mode=$mode usb=[$usb ] builtin=[$builtin ] using=${want:-none}"
[ -n "$want" ] || exit 0
mac=$(cat /sys/class/bluetooth/"$want"/address)
sleep 2
printf 'select %s\npower on\npairable on\ndiscoverable on\n' "$mac" | bluetoothctl >/dev/null 2>&1
exit 0
SH
chmod 755 /usr/local/sbin/bt-select
cat > /etc/systemd/system/bt-select.service <<'U'
[Unit]
Description=Choose Bluetooth radio and make Streamer discoverable
Requires=bluetooth.service
After=bluetooth.service bt-agent.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/bt-select
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
U
cat > /etc/udev/rules.d/98-streamer-bt.rules <<'R'
# Streamer: Bluetooth adapter plugged in/removed (e.g. TP-Link UB500) -> re-pick the radio
ACTION=="add|remove", SUBSYSTEM=="bluetooth", KERNEL=="hci[0-9]*", ENV{DEVTYPE}=="host", RUN+="/usr/bin/systemctl --no-block restart bt-select.service"
R
# --- DAC hot-plug: also restart the Bluetooth player
sed -i 's/restart shairport-sync.service raspotify.service$/restart shairport-sync.service raspotify.service bluealsa-aplay.service/; s/reset-failed raspotify.service shairport-sync.service/reset-failed raspotify.service shairport-sync.service bluealsa-aplay.service/' /usr/local/sbin/dac-ready.sh
udevadm control --reload
systemctl daemon-reload
systemctl enable bt-agent bt-select >/dev/null 2>&1
systemctl restart bluetooth
sleep 2
systemctl restart bluealsa bluealsa-aplay bt-agent bt-select
sleep 5
echo "== services"; systemctl is-active bluetooth bluealsa bluealsa-aplay bt-agent bt-select shairport-sync raspotify | tr '\n' ' '; echo
journalctl -u bt-select --since '-30 sec' --no-pager | grep bt-select: | tail -1
bluetoothctl show | grep -E 'Controller|Name:|Alias|Powered|Discoverable:|Pairable:'
cat /usr/local/sbin/dac-ready.sh | tail -2
