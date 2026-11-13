#!/usr/bin/env python3
"""Host-side regression checks for the Streamer image sources.
No Pi, no disk writes outside temp dirs, no network. The boot itself is checked by qemu-test/boot-test.py."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

BASE = Path(__file__).resolve().parent
BOARD = BASE / 'br2-streamer/board/streamer'
OVERLAY = BOARD / 'rootfs-overlay'
LIBEXEC = OVERLAY / 'usr/libexec/streamer'
UNITS = OVERLAY / 'etc/systemd/system'


def sh(script, *args, env=None):
    return subprocess.run(['/bin/sh', '-c', script, 'test', *args], capture_output=True, env=env,
                          text=True, encoding='utf-8', errors='replace')


class StreamerTests(unittest.TestCase):
    def test_script_syntax(self):
        files = list(LIBEXEC.iterdir())
        files += [OVERLAY / 'usr/share/streamer-www/cgi-bin/status', BOARD / 'post-build.sh']
        for path in files:
            with self.subTest(script=path.name):
                p = subprocess.run(['/bin/sh', '-n', str(path)], capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertTrue(os.access(path, os.X_OK), f'{path.name} is not executable')
        p = subprocess.run(['bash', '-n', str(BOARD / 'post-image.sh')], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_json_escaping(self):
        status = (OVERLAY / 'usr/share/streamer-www/cgi-bin/status').read_text()
        helpers = status[status.index('q() {'):status.index('\nn() {')]
        for value in ['ordinary', 'Phone "X2"', 'back\\slash', 'line\nbreak', 'tab\tCR\r', 'Sam’s Laptop']:
            with self.subTest(value=value):
                p = sh(helpers + '\nq "$VALUE"', env=dict(os.environ, VALUE=value, LC_ALL='C'))
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(json.loads(p.stdout), value)

    def test_mixer_detection(self):
        with tempfile.TemporaryDirectory() as d:
            mock = Path(d) / 'amixer'
            # $4 is the control name in: amixer -c JM7MAX sget NAME
            mock.write_text('#!/bin/sh\n[ "$4" = "$MIXER" ] || exit 1\n'
                            'echo "Simple mixer control \'$4\',0"; echo "  Capabilities: $CAPS"\n')
            mock.chmod(0o755)
            cases = [('PCM', 'pvolume pswitch', 'PCM'), ('Headset', 'pvolume pswitch cvolume', 'Headset'),
                     ('Speaker', 'pvolume', 'Speaker'), ('Master', 'pvolume', 'Master'),
                     ('PCM', 'pswitch', None),          # a switch without a volume is not usable
                     ('Other', 'pvolume', None)]
            for name, caps, expected in cases:
                with self.subTest(mixer=name, caps=caps):
                    env = dict(os.environ, PATH=d + ':' + os.environ['PATH'], MIXER=name, CAPS=caps)
                    p = subprocess.run(['/bin/sh', str(LIBEXEC / 'dac-mixer')], env=env, capture_output=True, text=True)
                    if expected is None:
                        self.assertNotEqual(p.returncode, 0)
                        self.assertEqual(p.stdout, '')
                    else:
                        self.assertEqual((p.returncode, p.stdout.strip()), (0, expected))

    def _start_player(self, d, kind, mixer, dac_present=True):
        d = Path(d)
        player = d / 'player'
        player.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        player.chmod(0o755)
        stub = d / 'dac-mixer'
        stub.write_text('#!/bin/sh\n[ -n "$MIXER" ] || exit 1\necho "$MIXER"\n')
        stub.chmod(0o755)
        (d / 'template').write_text((OVERLAY / 'etc/shairport-sync.conf').read_text())
        dac = d / 'JM7MAX'
        if dac_present:
            dac.mkdir(exist_ok=True)
        script = (LIBEXEC / 'start-player').read_text()
        for old, new in [('/usr/libexec/streamer/dac-mixer', str(stub)), ('/proc/asound/JM7MAX', str(dac)),
                         ('/usr/bin/shairport-sync', str(player)), ('/usr/bin/librespot', str(player)),
                         ('/usr/bin/bluealsa-aplay', str(player)), ('sleep 2;', ''),
                         ('/run/streamer-airplay/shairport-sync.conf', str(d / 'rendered')),
                         ('/etc/shairport-sync.conf', str(d / 'template')),
                         ('/data/librespot', str(d / 'no-data')), ('/run/streamer-librespot', str(d / 'ram-cache'))]:
            script = script.replace(old, new)
        return sh(script, kind, env=dict(os.environ, MIXER=mixer)), d

    def test_players_with_hardware_mixer(self):
        for mixer in ['PCM', 'Headset']:
            for kind in ['airplay', 'spotify', 'bluetooth']:
                with self.subTest(kind=kind, mixer=mixer), tempfile.TemporaryDirectory() as tmp:
                    p, d = self._start_player(tmp, kind, mixer)
                    self.assertEqual(p.returncode, 0, p.stderr)
                    if kind == 'airplay':
                        conf = (d / 'rendered').read_text()
                        self.assertIn(f'mixer_control_name = "{mixer}";', conf)
                        self.assertIn('output_device = "hw:CARD=JM7MAX";', conf)
                    elif kind == 'spotify':
                        self.assertIn(f'--alsa-mixer-control\n{mixer}\n', p.stdout)
                        self.assertIn('--bitrate\n320\n', p.stdout)
                        self.assertIn(str(d / 'ram-cache'), p.stdout)      # /data unavailable -> RAM fallback
                    else:
                        self.assertIn(f'--mixer-name={mixer}\n', p.stdout)
                        self.assertIn('--volume=mixer\n', p.stdout)
                        # the tested Bluetooth video-lag fix
                        self.assertIn('--pcm-buffer-time=200000\n', p.stdout)
                        self.assertIn('--pcm-period-time=50000\n', p.stdout)

    def test_players_fall_back_to_software_volume(self):
        for kind, marker in [('airplay', None), ('spotify', '--mixer\nsoftvol\n'), ('bluetooth', '--volume=software\n')]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                p, d = self._start_player(tmp, kind, '')
                self.assertEqual(p.returncode, 0, p.stderr)
                if kind == 'airplay':
                    conf = (d / 'rendered').read_text()
                    self.assertNotIn('mixer_control_name', conf)
                    self.assertNotIn('@MIXER@', conf)
                    self.assertIn('output_device = "hw:CARD=JM7MAX";', conf)
                else:
                    self.assertIn(marker, p.stdout)
                    self.assertNotIn('alsa-mixer-control', p.stdout)
                    self.assertNotIn('--mixer-name', p.stdout)

    def test_players_wait_for_dac(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, _ = self._start_player(tmp, 'airplay', 'PCM', dac_present=False)
            self.assertEqual(p.returncode, 1)
            self.assertEqual(p.stdout, '')

    def _bt_env(self, d, radios, usable):
        """Fake /sys/class/bluetooth plus busctl/systemd-run. radios: {name: 'usb'|'serial'}."""
        d = Path(d)
        sysfs = d / 'sys'; mockbin = d / 'bin'
        mockbin.mkdir(exist_ok=True)
        (mockbin / 'busctl').write_text(
            '#!/bin/sh\n# usable radios are listed in $USABLE; a set-property on them succeeds\n'
            'n=${3##*/}\ncase " $USABLE " in *" $n "*) ;; *) exit 1 ;; esac\n'
            '[ "$1" = get-property ] && { [ "$5" = Discoverable ] && echo "b true" || echo \'s "AA:BB:CC:DD:EE:FF"\'; }\nexit 0\n')
        # the real script detaches the re-probe with systemd-run; here run it inline, without the pause
        (mockbin / 'systemd-run').write_text('#!/bin/sh\nfor a; do last=$a; done\neval "$(echo "$last" | sed "s/sleep 2;//")"\necho ran >> "$REPROBE_LOG"\n')
        for f in ('busctl', 'systemd-run'):
            (mockbin / f).chmod(0o755)
        for n, typ in radios.items():
            h = sysfs / n
            (h / 'rfkill0').mkdir(parents=True, exist_ok=True)
            (h / 'rfkill0/soft').write_text('0\n')
            iface = d / f'{typ}dev-{n}' / f'{typ}-if'              # .../<device>/<interface>, as in sysfs
            iface.mkdir(parents=True, exist_ok=True)
            (iface.parent / 'authorized').write_text('1\n')
            if not (h / 'device').exists():
                (h / 'device').symlink_to(iface)
        settings = d / 'streamer.txt'
        env = dict(os.environ, STREAMER_TXT=str(settings), BT_SYSFS=str(sysfs), BT_STATE=str(d / 'reprobe-count'),
                   BT_WAIT='0', USABLE=' '.join(usable), REPROBE_LOG=str(d / 'reprobe.log'),
                   PATH=str(mockbin) + ':' + os.environ['PATH'])
        return d, sysfs, settings, env

    def _soft(self, sysfs, name):
        return (sysfs / name / 'rfkill0/soft').read_text().strip()

    def test_radio_policy(self):
        script = str(LIBEXEC / 'bt-select')
        with tempfile.TemporaryDirectory() as tmp:
            d, sysfs, settings, env = self._bt_env(tmp, {'hci0': 'serial', 'hci1': 'usb'}, ['hci0', 'hci1'])
            for mode, expected in [('auto', 'hci1'), ('usb', 'hci1'), ('builtin', 'hci0'), ('off', 'none')]:
                settings.write_text('bluetooth=' + mode + '\r\n')      # CRLF as written by some editors
                with self.subTest(mode=mode):
                    p = subprocess.run(['/bin/sh', script], capture_output=True, text=True, env=env)
                    self.assertEqual(p.returncode, 0, p.stderr)
                    self.assertIn('using=' + expected, p.stdout)
                    for name in ['hci0', 'hci1']:
                        self.assertEqual(self._soft(sysfs, name), '0' if name == expected else '1')
                    if expected != 'none':
                        self.assertIn(f'{expected} AA:BB:CC:DD:EE:FF powered and discoverable', p.stdout)
            self.assertFalse((d / 'reprobe.log').exists(), 'a healthy dongle must never be re-probed')
            shutil.rmtree(sysfs / 'hci1')                              # dongle unplugged
            settings.write_text('bluetooth=auto\n')
            p = subprocess.run(['/bin/sh', script], capture_output=True, text=True, env=env)
            self.assertIn('using=hci0', p.stdout)

    def test_dead_usb_radio_is_reprobed_then_falls_back(self):
        """The UB500 failure seen on the Pi: hci1 exists but its firmware never loaded, so BlueZ does not list it."""
        script = str(LIBEXEC / 'bt-select')
        with tempfile.TemporaryDirectory() as tmp:
            d, sysfs, settings, env = self._bt_env(tmp, {'hci0': 'serial', 'hci1': 'usb'}, ['hci0'])
            settings.write_text('bluetooth=auto\n')
            auth = d / 'usbdev-hci1' / 'authorized'
            for attempt in (1, 2, 3):
                p = subprocess.run(['/bin/sh', script], capture_output=True, text=True, env=env)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn(f're-probing it, attempt {attempt} of 3', p.stdout)
                self.assertNotIn('using=', p.stdout)                   # nothing selected yet: wait for the radio
                self.assertEqual(auth.read_text().strip(), '1', 'the dongle must end up switched back on')
                self.assertEqual((d / 'reprobe-count').read_text().strip(), str(attempt))
            self.assertEqual((d / 'reprobe.log').read_text().count('ran'), 3)
            self.assertEqual((d / 'serialdev-hci0' / 'authorized').read_text().strip(), '1')   # built-in untouched
            # fourth run: give up on the dongle, use the built-in radio, and block the dead one
            p = subprocess.run(['/bin/sh', script], capture_output=True, text=True, env=env)
            self.assertIn('not usable after 3 re-probe(s)', p.stdout)
            self.assertIn('using=hci0', p.stdout)
            self.assertEqual((self._soft(sysfs, 'hci0'), self._soft(sysfs, 'hci1')), ('0', '1'))
            self.assertEqual((d / 'reprobe.log').read_text().count('ran'), 3, 'no fourth re-probe')
            # bluetooth=usb must not silently use the built-in radio
            settings.write_text('bluetooth=usb\n')
            p = subprocess.run(['/bin/sh', script], capture_output=True, text=True, env=env)
            self.assertIn('using=none', p.stdout)
            # once the dongle works (re-probe succeeded), it is selected
            env['USABLE'] = 'hci0 hci1'
            settings.write_text('bluetooth=auto\n')
            p = subprocess.run(['/bin/sh', script], capture_output=True, text=True, env=env)
            self.assertIn('using=hci1', p.stdout)
            # bluetooth=builtin never touches the dongle's state
            env['USABLE'] = 'hci0'
            (d / 'reprobe-count').unlink()
            settings.write_text('bluetooth=builtin\n')
            p = subprocess.run(['/bin/sh', script], capture_output=True, text=True, env=env)
            self.assertIn('using=hci0', p.stdout)
            self.assertFalse((d / 'reprobe-count').exists())

    def test_wifi_config_generation(self):
        text = (LIBEXEC / 'wifi-config').read_text()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'wpa_passphrase').write_text('#!/bin/sh\nprintf \'network={\\n\\tssid="%s"\\n\\t#psk="%s"\\n\\tpsk=abcdef\\n}\\n\' "$1" "$2"\n')
            (d / 'iw').write_text('#!/bin/sh\nexit 0\n')
            for f in ('wpa_passphrase', 'iw'):
                (d / f).chmod(0o755)
            settings = d / 'streamer.txt'
            settings.write_text('# comment\r\nssid=My Net 2G\r\npsk=p@ss word!\r\ncountry=IN\r\n')
            script = text.replace('/boot/streamer.txt', str(settings)).replace('/run/streamer', str(d / 'run'))
            p = sh(script, env=dict(os.environ, PATH=str(d) + ':' + os.environ['PATH']))
            self.assertEqual(p.returncode, 0, p.stderr)
            conf = (d / 'run/wpa_supplicant.conf').read_text()
            self.assertIn('ctrl_interface=/run/wpa_supplicant', conf)
            self.assertIn('country=IN\n', conf)
            self.assertIn('ssid="My Net 2G"', conf)                    # spaces kept, CR stripped
            self.assertNotIn('p@ss word!', conf)                       # plain-text passphrase comment removed
            self.assertEqual(oct((d / 'run/wpa_supplicant.conf').stat().st_mode & 0o777), '0o600')

    def test_debug_log_is_opt_in_and_hides_password(self):
        text = (LIBEXEC / 'debug-log').read_text()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            settings = d / 'streamer.txt'
            script = (text.replace('/boot/streamer.txt', str(settings))
                          .replace('/run/streamer-log.txt', str(d / 'report.txt'))
                          .replace('/boot/streamer-log.txt', str(d / 'saved.txt'))
                          .replace('mount -o remount,rw /boot', 'true')
                          .replace('mount -o remount,ro /boot', 'true'))
            self.assertNotIn('mount -o', script, 'the test must never remount anything on this computer')
            settings.write_text('ssid=HomeNet\npsk=TopSecret123\ndebug=0\n')
            p = sh(script, '0', '0')
            self.assertEqual(p.returncode, 0)
            self.assertFalse((d / 'saved.txt').exists(), 'debug=0 must write nothing')
            settings.write_text('ssid=HomeNet\npsk=TopSecret123\ndebug=1\n')
            p = sh(script, '0', '0')
            self.assertEqual(p.returncode, 0, p.stderr)
            saved = (d / 'saved.txt').read_text(errors='replace')
            self.assertIn('ssid=HomeNet', saved)
            self.assertIn('psk=<hidden>', saved)
            self.assertNotIn('TopSecret123', saved)

    def test_boot_configuration(self):
        cmdline = (BOARD / 'cmdline.txt').read_text().split()
        for word in ['root=/dev/mmcblk0p2', 'ro', 'rootwait', 'net.ifnames=0', 'console=tty1']:
            self.assertIn(word, cmdline)
        # wpa_supplicant >= 2.11 waits for a 'port authorized' event that this kernel's brcmfmac never sends
        # for WPA2-PSK handshake offload; without this the Pi associates and then times out (seen on hardware).
        self.assertIn('brcmfmac.feature_disable=0x82000', cmdline)
        self.assertNotIn('quiet', cmdline)                             # keep boot messages visible on HDMI
        self.assertFalse(any(w.startswith('console=ttyAMA') for w in cmdline), 'PL011 is the Bluetooth UART')
        config = (BASE / 'br2-streamer/configs/streamer_zero2w_defconfig').read_text()
        for setting in ['BR2_PACKAGE_XZ=y', 'BR2_PACKAGE_KMOD_TOOLS=y',               # .ko.xz driver loading
                        'BR2_PACKAGE_WPA_SUPPLICANT_CTRL_IFACE=y', 'BR2_PACKAGE_WPA_SUPPLICANT_CLI=y',
                        'BR2_PACKAGE_BLUEZ5_UTILS_TOOLS=y', 'BR2_PACKAGE_BLUEZ5_UTILS_DEPRECATED=y',
                        'BR2_PACKAGE_LINUX_FIRMWARE_RTL_87XX_BT=y', 'BR2_PACKAGE_BRCMFMAC_SDIO_FIRMWARE_RPI_WIFI=y']:
            self.assertIn(setting, config)
        librespot = (BASE / 'br2-streamer/package/librespot/librespot.mk').read_text()
        self.assertIn('with-avahi', librespot)                        # one mDNS responder only (Avahi)
        self.assertNotIn('with-libmdns', librespot)
        settings = (BOARD / 'streamer.txt').read_text()
        for key in ['ssid=', 'psk=', 'country=IN', 'bluetooth=auto', 'debug=']:
            self.assertIn('\n' + key, settings)

    def test_units(self):
        wifi = (UNITS / 'streamer-wifi.service').read_text()
        self.assertIn('BindsTo=sys-subsystem-net-devices-wlan0.device', wifi)
        self.assertIn('-i wlan0 -D nl80211', wifi)
        preset = (OVERLAY / 'etc/systemd/system-preset/10-streamer.preset').read_text()
        self.assertIn('disable wpa_supplicant.service', preset)       # packaged unit needs D-Bus support we don't build
        for unit in ['bt-agent', 'bt-select', 'streamer-bluealsa', 'streamer-bluealsa-aplay']:
            text = (UNITS / f'{unit}.service').read_text()
            with self.subTest(unit=unit):
                self.assertIn('ConditionPathIsDirectory=/sys/class/bluetooth', text)
                self.assertIn('WantedBy=multi-user.target bluetooth.target', text)
        bt = (UNITS / 'bluetooth.service.d/streamer.conf').read_text()
        self.assertIn('BindPaths=-/data/bluetooth:/var/lib/bluetooth', bt)
        self.assertIn('After=streamer-data.service', bt)
        data = (UNITS / 'streamer-data.service').read_text()
        self.assertIn('RequiresMountsFor=/data', data)
        self.assertIn('/data/bluetooth /data/librespot', data)
        web = (UNITS / 'streamer-status.service').read_text()
        for key in ['User=streamer-web', 'ProtectSystem=strict', 'NoNewPrivileges=yes', 'RuntimeDirectory=streamer-web']:
            self.assertIn(key, web)
        resolved = (OVERLAY / 'etc/systemd/resolved.conf.d/streamer.conf').read_text()
        self.assertIn('MulticastDNS=no', resolved)                     # Avahi is the only mDNS responder
        rules = (OVERLAY / 'etc/udev/rules.d/99-streamer-dac.rules').read_text()
        self.assertIn('ENV{ID_VENDOR_ID}=="06cb", ENV{ID_MODEL_ID}=="1595"', rules)
        ready = (LIBEXEC / 'dac-ready').read_text()
        for unit in ['shairport-sync.service', 'librespot.service', 'streamer-bluealsa-aplay.service']:
            self.assertIn(unit, ready)

    def test_status_page_makes_no_lossless_claims(self):
        status = (OVERLAY / 'usr/share/streamer-www/cgi-bin/status').read_text()
        self.assertNotIn('Lossless (ALAC, est.)', status)
        self.assertIn('Codec not verified', status)
        html = (OVERLAY / 'usr/share/streamer-www/index.html').read_text()
        self.assertIn('do not prove lossless audio', html)
        self.assertIn('setInterval(tick, 5000)', html)
        self.assertIn('fetching', html)
        self.assertEqual(html, (BASE / 'status-page/index.html').read_text(), 'overlay copy is stale')
        self.assertEqual(status, (BASE / 'status-page/cgi-bin/status').read_text(), 'overlay copy is stale')


if __name__ == '__main__':
    unittest.main(verbosity=2)
