#!/usr/bin/env python3
"""Boot the built SD-card image in QEMU and check it from the inside and over SSH.

Three boots of one copy of the image, so the data partition carries over like a real card:
  1. as published      SSH must be off, nothing secret on the card, all services up
  2. ssh_password set  host keys are created, password login works, wrong password is refused
  3. same card again   the host keys are the same as in boot 2

QEMU's raspi3b machine is used with the Zero 2 W device tree. It has no Wi-Fi chip, no Bluetooth
radio and no JM7MAX DAC: an emulated USB sound card (renamed JM7MAX) and USB network card stand in.
The image itself is not modified, except that boots 2 and 3 set ssh_password in streamer.txt.
A test-only copy of the device tree frees the PL011 UART (the Bluetooth UART on a real Pi) for
systemd's debug shell, which is how commands are run inside the guest.

Run in the streamer-qemu container with the build volume at /work:
  python3 /boot-test.py            exit status 0 = every check passed
"""
import os, re, socket, struct, subprocess, sys, time

W = '/work/qemu-test'
IMG = '/work/out/images'
DTB_SRC = '/work/out/build/linux-custom/arch/arm64/boot/dts/broadcom/bcm2710-rpi-zero-2-w.dtb'
PASSWORD = 'qemu-Test pw$42'
SSH_PORT = 2222
results = []


def sh(*cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def prepare():
    os.makedirs(W, exist_ok=True)
    sd = f'{W}/sd.img'
    sh('cp', f'{IMG}/sdcard.img', sd)
    sh('truncate', '-s', '1G', sd)                       # QEMU wants a power-of-two SD card
    dtb = f'{W}/test.dtb'
    sh('cp', DTB_SRC, dtb)
    sh('fdtput', '-t', 's', dtb, '/soc/serial@7e201000/bluetooth', 'status', 'disabled')
    with open(sd, 'rb') as f:
        mbr = f.read(512)
    start = struct.unpack_from('<I', mbr, 446 + 8)[0]    # first partition = FAT boot partition
    return sd, dtb, f'{sd}@@{start * 512}'


def read_settings(fat):
    return subprocess.run(['mtype', '-i', fat, '::/streamer.txt'], capture_output=True, text=True, check=True).stdout


def write_settings(fat, text):
    with open(f'{W}/streamer.txt', 'w') as f:
        f.write(text)
    sh('mcopy', '-o', '-i', fat, f'{W}/streamer.txt', '::/streamer.txt')


class Guest:
    def __init__(self, sd, dtb, cmdline_file):
        try:
            os.remove(f'{W}/shell.sock')
        except FileNotFoundError:
            pass
        cmdline = (cmdline_file.replace('console=tty1', 'console=ttyAMA1,115200 loglevel=1') +
                   ' systemd.debug_shell=ttyAMA1 systemd.mask=serial-getty@ttyAMA1.service systemd.show_status=0'
                   ' snd_usb_audio.id=JM7MAX')
        self.cmdline = cmdline
        self.q = subprocess.Popen(
            ['qemu-system-aarch64', '-M', 'raspi3b', '-kernel', f'{IMG}/Image', '-dtb', dtb,
             '-drive', f'file={sd},if=sd,format=raw', '-append', cmdline,
             '-serial', f'unix:{W}/shell.sock,server=on,wait=off', '-serial', 'null', '-display', 'none', '-no-reboot',
             '-device', 'usb-audio', '-device', 'usb-kbd', '-device', 'usb-net,netdev=n0',
             '-netdev', f'user,id=n0,hostfwd=tcp:127.0.0.1:{SSH_PORT}-10.0.2.15:22'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        self.s = socket.socket(socket.AF_UNIX)
        self.s.connect(f'{W}/shell.sock')
        self.s.settimeout(2)

    def _read_until(self, marker, timeout):
        buf = b''
        end = time.time() + timeout
        while time.time() < end:
            try:
                d = self.s.recv(65536)
                if not d:
                    break
                buf += d
                if marker in buf:
                    return buf, True
            except socket.timeout:
                pass
        return buf, False

    def wait_for_shell(self):
        t0 = time.time()
        while time.time() - t0 < 420 and self.q.poll() is None:
            self.s.sendall(b'\necho RDY$((40+2))\n')
            if self._read_until(b'RDY42', 6)[1]:
                self._read_until(b'\x00never', 2)
                self.run('stty -echo 2>/dev/null; export SYSTEMD_PAGER=cat SYSTEMD_COLORS=0 TERM=dumb', show=False)
                return True
        return False

    def run(self, cmd, timeout=90, show=True):
        self.s.sendall(cmd.encode() + b'; echo "__END_$((6*7))__"\n')
        out, ok = self._read_until(b'__END_42__', timeout)
        if not ok:                                   # let it finish so later commands stay in step
            more, _ = self._read_until(b'__END_42__', 300)
            out += more
        txt = out.decode(errors='replace').replace('\r', '').split('__END_42__')[0]
        txt = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', txt)
        txt = re.sub(r'^/ # ', '', txt.strip())
        if show:
            print(f'\n$ {cmd}\n{txt}' + ('' if ok else '\n[TIMEOUT]'))
        return txt

    def stop(self):
        self.run('sync; mount -o remount,ro /data 2>/dev/null; sync', show=False)
        self.q.kill()
        self.q.wait()


def check(name, text, has=(), lacks=(), equals=None):
    ok = all(h in text for h in has) and not any(l in text for l in lacks)
    if equals is not None:
        ok = ok and text.strip() == equals
    results.append((name, ok))
    print(f'  [{"PASS" if ok else "FAIL"}] {name}')
    return ok


def active(g, *units):
    return g.run('for u in ' + ' '.join(units) + '; do printf "%s=%s " $u $(systemctl is-active $u); done; echo')


def ssh_login(password, command='id -u; cat /etc/hostname'):
    p = subprocess.run(['sshpass', '-p', password, 'ssh', '-p', str(SSH_PORT), '-o', 'StrictHostKeyChecking=no',
                        '-o', 'UserKnownHostsFile=/dev/null', '-o', 'PreferredAuthentications=password',
                        '-o', 'PubkeyAuthentication=no', '-o', 'NumberOfPasswordPrompts=1', '-o', 'ConnectTimeout=25',
                        '-o', 'LogLevel=ERROR', 'root@127.0.0.1', command], capture_output=True, text=True, timeout=90)
    print(f'\nssh login from outside the guest -> rc={p.returncode} out={p.stdout.strip()!r} err={p.stderr.strip()[:90]!r}')
    return p


def port22(g):
    return g.run('i=0; while [ $i -lt 60 ]; do netstat -ltn | grep -q ":22 " && break; sleep 1; i=$((i+1)); done; '
                 'netstat -ltn | grep -q ":22 " && echo open || echo closed', timeout=120)


def network_up(g):
    """Bring up the emulated USB network card with systemd-networkd, using the same DHCP settings as wlan0."""
    out = g.run('IF=$(ls /sys/class/net | grep -vE "^(lo|wlan0)$" | head -n1); echo "card=$IF"; '
                'mkdir -p /run/systemd/network; sed "s/^Name=wlan0/Name=$IF/" /etc/systemd/network/30-wlan0.network '
                '> /run/systemd/network/20-test.network; cat /run/systemd/network/20-test.network | tr "\\n" " "; echo; '
                'networkctl reload; i=0; while [ $i -lt 30 ]; do ip -4 -o addr show dev $IF | grep -q "inet " && break; sleep 1; i=$((i+1)); done; '
                'ip -4 -o addr show dev $IF | awk "{print \\"address=\\" \\$4}"', timeout=80)
    return out


def boot(title, sd, dtb, cmdline_file, settle):
    print(f'\n{"=" * 78}\n{title}\n{"=" * 78}')
    g = Guest(sd, dtb, cmdline_file)
    if not g.wait_for_shell():
        check('guest boots to a shell', '', has=['never'])
        g.q.kill()
        return None
    g.run(f'sleep {settle}; echo settled', timeout=settle + 40, show=False)
    return g


def main():
    sd, dtb, fat = prepare()
    shipped = read_settings(fat)
    cmdline_file = subprocess.run(['mtype', '-i', fat, '::/cmdline.txt'], capture_output=True, text=True, check=True).stdout.strip()
    print('cmdline.txt:', cmdline_file)
    print('boot partition:', subprocess.run(['mdir', '-b', '-i', fat, '::/'], capture_output=True, text=True).stdout.split())
    check('published streamer.txt has placeholders, SSH off, debug off', shipped,
          has=['ssid=YOUR_WIFI_NAME', 'psk=YOUR_WIFI_PASSWORD', '\nssh_password=\n', '\ndebug=0\n'])

    # ---------------------------------------------------------------- boot 1: as published
    g = boot('BOOT 1: image as published', sd, dtb, cmdline_file, 150)
    if g:
        check('kernel and model', g.run('uname -r; cat /proc/device-tree/model; echo'), has=['Raspberry Pi Zero 2 W'])
        mounts = g.run('grep -E " (/|/var|/boot|/data) " /proc/mounts')
        check('root and boot read-only, data writable', mounts,
              has=['/dev/root / ext4 ro', '/dev/mmcblk0p1 /boot vfat ro', '/dev/mmcblk0p3 /data ext4 rw'])
        check('root filesystem refuses writes', g.run('touch /etc/x 2>&1; echo rc=$?'), has=['Read-only file system'])
        check('streamer.txt readable by root only', g.run('ls -ld /boot/streamer.txt | awk "{print \\$1, \\$3}"; su -s /bin/sh streamer-web -c "cat /boot/streamer.txt" 2>&1 | tail -n1'),
              has=['-rwx------ root', 'Permission denied'])
        check('only the network wait fails (no Wi-Fi chip in the emulator)',
              g.run('systemctl --failed --no-legend --plain --no-pager --full | awk "{print \\$1}"'), equals='systemd-networkd-wait-online.service')
        a = active(g, 'dbus', 'avahi-daemon', 'systemd-networkd', 'systemd-resolved', 'systemd-timesyncd', 'nqptp',
                   'streamer-data', 'streamer-status', 'shairport-sync', 'librespot', 'streamer-ssh-setup')
        check('core services active', a, lacks=['=inactive', '=failed', '=activating'])
        # --- SSH must be off and nothing secret may exist
        check('sshd is not running', active(g, 'sshd'), has=['sshd=inactive'])
        check('ssh-setup says why', g.run('journalctl -b -u streamer-ssh-setup --no-pager -o cat | grep ssh-setup:'), has=['SSH stays off'])
        check('nothing listens on port 22', g.run('netstat -ltn | grep -c ":22 "'), equals='0')
        check('no host keys, login keys or SSH state anywhere on the card',
              g.run('echo "etc: $(ls /etc/ssh | tr "\\n" " ")"; echo "files-under-root-home=$(find /root -type f | wc -l)"; echo "data: $(ls /data | tr "\\n" " ")"; '
                    'echo "ssh-state-files=$(ls /run/streamer-ssh | wc -l)"; '
                    'echo "key-files=$(find / /data /boot -xdev \\( -name "ssh_host_*" -o -name authorized_keys -o -name "id_*" \\) 2>/dev/null | wc -l)"'),
              lacks=['ssh_host', 'authorized_keys'], has=['files-under-root-home=0', 'data: bluetooth librespot', 'ssh-state-files=0', 'key-files=0'])
        check('root password locked', g.run('grep "^root:" /etc/shadow | cut -d: -f2'), equals='*')
        net = network_up(g)
        check('DHCP lease obtained with ClientIdentifier=mac', net, has=['ClientIdentifier=mac', 'address=10.0.2.15/'])
        ssh_off = ssh_login(PASSWORD)
        check('login from outside is impossible', f'rc={ssh_off.returncode}', lacks=['rc=0'])
        # --- players, discovery, status page, Bluetooth chain
        check('emulated DAC is the JM7MAX card', g.run('cat /proc/asound/cards | head -n1'), has=['JM7MAX'])
        check('players running on the DAC', g.run('ps -o args= | grep -E "^/usr/bin/(librespot|shairport)" | cut -c1-120'),
              has=['/usr/bin/shairport-sync -c /run/streamer-airplay/shairport-sync.conf', '/usr/bin/librespot --name Streamer'])
        check('AirPlay port open', 'open' if g.run('netstat -ltn | grep -c ":7000 "').strip() not in ('', '0') else 'closed', equals='open')
        page = g.run('wget -qO- http://127.0.0.1/ | head -c 15; echo; wget -qO- http://127.0.0.1/cgi-bin/status')
        check('status page and status JSON served', page, has=['<!doctype html>', '"host":"streamer"', '"read_only":true', '"sshd.service":"inactive"'])
        check('status JSON makes no lossless claim', page, has=['Codec not verified'], lacks=['Lossless'])
        g.run('sleep 12', show=False)
        check('Avahi announces streamer.local on the network card', g.run('journalctl -b -u avahi-daemon --no-pager -o cat | grep -iE "host name|Joining mDNS.*IPv4" | tail -n 3'),
              has=['Host name is streamer.local', '10.0.2.15'], lacks=['streamer-2'])
        check('Spotify published through Avahi', g.run('journalctl -b -u librespot --no-pager -o cat | grep -iE "zeroconf|error" | tail -n 3'),
              has=['Published zeroconf service'], lacks=['ERROR'])
        check('players still active with the network up', active(g, 'shairport-sync', 'librespot', 'avahi-daemon')
              + g.run('for u in shairport-sync librespot; do echo "$u restarts=$(systemctl show -p NRestarts --value $u)"; done'),
              lacks=['=inactive', '=failed', '=activating'])
        bt = g.run('modprobe bluetooth; sleep 2; systemctl start bluetooth.target; sleep 14; '
                   'for u in bluetooth bt-agent bt-select streamer-bluealsa streamer-bluealsa-aplay; do printf "%s=%s " $u $(systemctl is-active $u); done; echo', timeout=60)
        check('Bluetooth service chain starts once a Bluetooth stack exists', bt, lacks=['=inactive', '=failed', '=activating'])
        check('pairings are stored on the data partition', g.run('grep -c " /var/lib/bluetooth " /proc/$(pidof bluetoothd)/mountinfo'), equals='1')
        check('no diagnostic report written (debug=0)', g.run('ls /boot/streamer-log.txt 2>&1 | tail -n1'), has=['No such file'])
        g.stop()

    # ---------------------------------------------------------------- boot 2: ssh_password set
    write_settings(fat, shipped.replace('\nssh_password=\n', f'\nssh_password={PASSWORD}\n').replace('\ndebug=0\n', '\ndebug=1\n'))
    fp2 = ''
    g = boot('BOOT 2: ssh_password and debug=1 set in streamer.txt', sd, dtb, cmdline_file, 130)
    if g:
        check('ssh-setup enabled SSH and created keys', g.run('journalctl -b -u streamer-ssh-setup --no-pager -o cat | grep ssh-setup:'),
              has=['created a new ed25519 host key', 'created a new ecdsa host key', 'SSH is on'])
        check('sshd running', active(g, 'sshd'), has=['sshd=active'])
        check('sshd listening on port 22', port22(g), equals='open')
        check('password is hashed, and not stored in clear anywhere but streamer.txt',
              g.run(f"echo \"hash=$(grep '^root:' /etc/shadow | cut -d: -f2 | cut -c1-3)\"; "
                    f"echo \"files-with-password=$(find /run /data /var /tmp -xdev -type f ! -path '/run/log/*' 2>/dev/null | xargs grep -lF '{PASSWORD}' 2>/dev/null | wc -l)\"; "
                    f"echo \"journal-lines-with-password=$(journalctl -b --no-pager | grep -cF '{PASSWORD}')\"; "
                    f"echo \"streamer.txt=$(grep -cF 'ssh_password={PASSWORD}' /boot/streamer.txt)\"", timeout=240),
              has=['hash=$6$', 'files-with-password=0', 'journal-lines-with-password=0', 'streamer.txt=1'])
        fp2 = g.run('for k in /data/ssh/ssh_host_ed25519_key /data/ssh/ssh_host_ecdsa_key; do ssh-keygen -lf $k | cut -d" " -f2; done; ls -ld /data/ssh /data/ssh/ssh_host_ed25519_key | cut -d" " -f1 | tr "\\n" " "')
        check('host keys kept on the data partition, private', fp2, has=['SHA256:', 'drwx------ -rw-------'])
        net = network_up(g)
        check('network card up for the login test', net, has=['address=10.0.2.15/'])
        good = ssh_login(PASSWORD)
        check('login with the password from streamer.txt works', f'{good.returncode}|{good.stdout}', has=['0|0\nstreamer'])
        bad = ssh_login(PASSWORD + 'x')
        check('wrong password is refused', f'rc={bad.returncode}', lacks=['rc=0'])
        key = subprocess.run(['ssh', '-p', str(SSH_PORT), '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'BatchMode=yes',
                              '-o', 'ConnectTimeout=20', '-o', 'LogLevel=ERROR', 'root@127.0.0.1', 'true'], capture_output=True, text=True, timeout=60)
        check('login without a password is refused', f'rc={key.returncode}', lacks=['rc=0'])
        report = g.run('cat /boot/streamer-log.txt | head -n 14; echo ...; grep -c . /boot/streamer-log.txt')
        check('diagnostic report written, both passwords hidden', report, has=['psk=<hidden>', 'ssh_password=<hidden>'], lacks=[PASSWORD, 'YOUR_WIFI_PASSWORD'])
        check('boot partition read-only again after the report', g.run('grep " /boot " /proc/mounts | cut -d" " -f4 | cut -c1-2'), equals='ro')
        g.stop()

    # ---------------------------------------------------------------- boot 3: same card again
    g = boot('BOOT 3: same card, second boot with SSH on', sd, dtb, cmdline_file, 120)
    if g:
        fp3 = g.run('for k in /data/ssh/ssh_host_ed25519_key /data/ssh/ssh_host_ecdsa_key; do ssh-keygen -lf $k | cut -d" " -f2; done; ls -ld /data/ssh /data/ssh/ssh_host_ed25519_key | cut -d" " -f1 | tr "\\n" " "')
        check('host keys unchanged after a reboot', fp3, equals=fp2.strip())
        check('no new keys were created', g.run('journalctl -b -u streamer-ssh-setup --no-pager -o cat | grep ssh-setup:'), has=['SSH is on'], lacks=['created a new'])
        network_up(g)
        check('sshd listening on port 22 after the reboot', port22(g), equals='open')
        again = ssh_login(PASSWORD)
        check('login still works', f'{again.returncode}|{again.stdout}', has=['0|0\nstreamer'])
        g.stop()

    failed = [n for n, ok in results if not ok]
    print(f'\n{"=" * 78}\n{len(results) - len(failed)} of {len(results)} checks passed' + (f'; FAILED: {failed}' if failed else ''))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
