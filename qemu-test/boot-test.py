#!/usr/bin/env python3
"""Boot the built SD image in QEMU (raspi3b) and inspect it through systemd's debug shell on the 2nd UART.
This checks kernel + read-only root + systemd userspace. It cannot test Wi-Fi/Bluetooth radios or the JM7MAX DAC."""
import os, socket, subprocess, sys, time

W = '/work/qemu-test'
IMG = '/work/out/images'
DTB = sys.argv[1] if len(sys.argv) > 1 else 'bcm2710-rpi-zero-2-w.dtb'
EXTRA = sys.argv[2] if len(sys.argv) > 2 else ''
os.makedirs(W, exist_ok=True)
sd = f'{W}/sd.img'
subprocess.run(['cp', f'{IMG}/sdcard.img', sd], check=True)
subprocess.run(['truncate', '-s', '1G', sd], check=True)          # QEMU SD cards must be a power of two
# Test-only device-tree copy: QEMU has no Bluetooth chip on the PL011 UART, and its mini-UART gives no output,
# so the BT node is disabled here to free ttyAMA0 for the console and the debug shell. The SD image is untouched.
dtb = f'{W}/test.dtb'
subprocess.run(['cp', f'/work/out/build/linux-custom/arch/arm64/boot/dts/broadcom/{DTB}', dtb], check=True)
subprocess.run(['fdtput', '-t', 's', dtb, '/soc/serial@7e201000/bluetooth', 'status', 'disabled'], check=True)
for f in ('uart0.log', 'uart1.sock'):
    try: os.remove(f'{W}/{f}')
    except FileNotFoundError: pass
cmdline = ('root=/dev/mmcblk0p2 rootfstype=ext4 rootwait ro console=ttyAMA1,115200 loglevel=1 '
           'systemd.debug_shell=ttyAMA1 systemd.mask=serial-getty@ttyAMA1.service systemd.show_status=0 ' + EXTRA)
q = subprocess.Popen(['qemu-system-aarch64', '-M', 'raspi3b', '-kernel', f'{IMG}/Image', '-dtb', dtb,
                      '-drive', f'file={sd},if=sd,format=raw', '-append', cmdline,
                      '-serial', f'unix:{W}/uart1.sock,server=on,wait=off', '-serial', 'null',
                      '-display', 'none', '-no-reboot', '-device', 'usb-audio', '-device', 'usb-kbd',
                      '-device', 'usb-net,netdev=n0', '-netdev', 'user,id=n0'],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(3)
s = socket.socket(socket.AF_UNIX); s.connect(f'{W}/uart1.sock'); s.settimeout(2)

def read_until(marker, timeout):
    buf = b''; end = time.time() + timeout
    while time.time() < end:
        try:
            d = s.recv(65536)
            if not d: break
            buf += d
            if marker in buf: return buf, True
        except socket.timeout: pass
    return buf, False

t0 = time.time(); ready = False
while time.time() - t0 < 420 and q.poll() is None:
    s.sendall(b'\necho RDY$((40+2))\n')
    _, ready = read_until(b'RDY42', 6)
    if ready: break
print(f'debug shell ready: {ready} after {time.time()-t0:.0f}s (qemu rc={q.poll()})')

def run(cmd, timeout=60):
    s.sendall(b'stty -echo 2>/dev/null; ' + cmd.encode() + b'; echo "__END_$((6*7))__"\n')
    out, ok = read_until(b'__END_42__', timeout)
    txt = out.decode(errors='replace').replace('\r', '')
    txt = txt.split('__END_42__')[0]
    print(f'\n### {cmd}\n{txt.strip()}' + ('' if ok else '\n[TIMEOUT]'))

if ready:
    read_until(b'\x00never', 2)
    run('export SYSTEMD_PAGER=cat SYSTEMD_COLORS=0 TERM=dumb; echo env-set')
    wait = int(os.environ.get('SETTLE', '75'))
    run(f'sleep {wait}; echo settled', wait + 30)
    for c in [
        r'cat /proc/cmdline; uname -r; cat /proc/device-tree/model; echo',
        r'grep -E " (/|/var|/boot|/data) " /proc/mounts',
        r'touch /etc/ro-test 2>&1; touch /data/rw-test && echo data-writable && rm /data/rw-test',
        r'ls -la /data | cat; ls -ld /var/empty /run/streamer-web 2>&1 | cat',
        r'ls /etc/systemd/system/multi-user.target.wants /etc/systemd/system/bluetooth.target.wants | tr "\n" " "; echo',
        r'systemctl --failed --no-legend --plain --no-pager',
        r'systemctl list-jobs --no-legend --plain --no-pager | head -20',
        r'for u in dbus sshd streamer-status avahi-daemon systemd-networkd systemd-resolved systemd-timesyncd nqptp streamer-data streamer-debug-log wpa_supplicant streamer-wifi shairport-sync librespot bluetooth bt-agent bt-select streamer-bluealsa streamer-bluealsa-aplay; do printf "%s=%s  " $u $(systemctl is-active $u); done; echo',
        r'lsmod | awk "NR>1{print \$1}" | sort | tr "\n" " "; echo',
        r'cat /proc/asound/cards; amixer -c JM7MAX scontrols; /usr/libexec/streamer/dac-mixer; echo "dac-mixer rc=$?"',
        r'for u in shairport-sync librespot nqptp; do printf "%s=%s restarts=%s  " $u $(systemctl is-active $u) $(systemctl show -p NRestarts --value $u); done; echo; cat /run/streamer-airplay/shairport-sync.conf; ps -o args= | grep -E "^/usr/bin/(librespot|shairport)" | cut -c1-200',
        r'journalctl -b --no-pager -o cat -u avahi-daemon | grep -iE "another|Registering|established|Service \"" | cut -c1-150 | tail -8',
        r'netstat -ltn 2>/dev/null | grep -E ":(22|80|7000) " | cut -c1-80; netstat -lun 2>/dev/null | grep -E ":(319|320|5353) " | cut -c1-80',
        r'wget -qO- http://127.0.0.1/ | head -c 40; echo; wget -qO- http://127.0.0.1/cgi-bin/status; echo',
        r'journalctl -b --no-pager -o short-monotonic -u shairport-sync -u librespot -u nqptp | grep -vE "Scheduled restart|Started |Stopped " | tail -14',
        # --- Bluetooth service chain without a radio: load the core module, then let bluetooth.target pull the units in
        r'modprobe bluetooth; sleep 2; systemctl start bluetooth.target; sleep 14; for u in bluetooth bt-agent bt-select streamer-bluealsa streamer-bluealsa-aplay; do printf "%s=%s  " $u $(systemctl is-active $u); done; echo',
        r'grep -E "/var/lib/bluetooth" /proc/$(pidof bluetoothd)/mountinfo | cut -c1-120; busctl list --no-pager | grep -E "org.bluez|org.bluealsa" | awk "{print \$1, \$3}"',
        r'journalctl -b --no-pager -o short-monotonic -u bt-agent -u bt-select -u streamer-bluealsa -u bluetooth | grep -viE "Started |Starting |Finished " | tail -12',
        r'bluealsa-cli list-pcms; echo "bluealsa-cli rc=$?"; systemctl --failed --no-legend --plain --no-pager',
        # --- give the emulator a multicast-capable interface so mDNS users (Avahi, librespot discovery) can be exercised
        r'IF=$(ls /sys/class/net | grep -v "^lo$" | head -n1); echo "emulated USB network card: $IF"; ip link set $IF up; ip addr add 10.0.2.15/24 dev $IF; ip route add default via 10.0.2.2; sleep 16; for u in avahi-daemon shairport-sync librespot; do printf "%s=%s restarts=%s  " $u $(systemctl is-active $u) $(systemctl show -p NRestarts --value $u); done; echo',
        r'journalctl -b --no-pager -o cat -u avahi-daemon | grep -iE "Joining|another|host name" | cut -c1-140 | tail -5; journalctl -b --no-pager -o cat -u librespot | grep -iE "zeroconf|discovery|error" | tail -3 | cut -c1-170',
        r'netstat -ltn 2>/dev/null | grep -E ":(22|80|7000) " | cut -c1-80; ps -o args= | grep -E "^/usr/bin/(librespot|shairport|bluealsa)" | cut -c1-230',
        r'journalctl -b --no-pager -o short-monotonic -u shairport-sync -u librespot | grep -iE "fatal|warn|error|exited|avahi|zeroconf|discovery|Published|register" | tail -8 | cut -c1-190',
        # --- diagnostics written to the boot drive (debug=1 is the image default)
        r'ls -l /boot/streamer-log.txt | cat; grep -c YOUR_WIFI_PASSWORD /boot/streamer-log.txt; grep " /boot " /proc/mounts | cut -c1-60',
        r'sed -n "1,34p" /boot/streamer-log.txt',
        r'journalctl -b -p warning --no-pager -o cat | grep -vE "^$|staging directory|vchiq|VCHI|bcm2835-(isp|codec|camera|audio|power|aux)|core params|Interrupt|Transfer|Split|FIFO|DMA|OTG|Init:|host mode|KASLR|mmc[01]:" | sort | uniq -c | sort -rn | head -25',
        r'free -m | head -2',
    ]:
        run(c)
else:
    print('--- no debug shell ---')
q.kill()
