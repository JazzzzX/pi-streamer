#!/usr/bin/env python3
"""Host-side regression checks for the Streamer image sources.
No Pi, no disk writes outside temp dirs, no network. The boot itself is checked by qemu-test/boot-test.py."""
import json
import os
import re
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
        (d / 'mpd-template').write_text((OVERLAY / 'etc/streamer-mpd.conf').read_text())
        dac = d / 'JM7MAX'
        if dac_present:
            dac.mkdir(exist_ok=True)
        script = (LIBEXEC / 'start-player').read_text()
        for old, new in [('/usr/libexec/streamer/dac-mixer', str(stub)), ('/proc/asound/JM7MAX', str(dac)),
                         ('/usr/bin/shairport-sync', str(player)), ('/usr/bin/librespot', str(player)),
                         ('/usr/bin/bluealsa-aplay', str(player)), ('/usr/bin/mpd', str(player)), ('sleep 2;', ''),
                         ('/run/streamer-mpd/mpd.conf', str(d / 'rendered-mpd')), ('/run/streamer-mpd/playlists', str(d / 'playlists')),
                         ('/etc/streamer-mpd.conf', str(d / 'mpd-template')),
                         ('/run/streamer-airplay/shairport-sync.conf', str(d / 'rendered')),
                         ('/etc/shairport-sync.conf', str(d / 'template')),
                         ('/data/librespot', str(d / 'no-data')), ('/run/streamer-librespot', str(d / 'ram-cache'))]:
            script = script.replace(old, new)
        return sh(script, kind, env=dict(os.environ, MIXER=mixer)), d

    def test_players_with_hardware_mixer(self):
        for mixer in ['PCM', 'Headset']:
            for kind in ['airplay', 'spotify', 'bluetooth', 'upnp']:
                with self.subTest(kind=kind, mixer=mixer), tempfile.TemporaryDirectory() as tmp:
                    p, d = self._start_player(tmp, kind, mixer)
                    self.assertEqual(p.returncode, 0, p.stderr)
                    if kind == 'upnp':
                        conf = (d / 'rendered-mpd').read_text()
                        self.assertRegex(conf, rf'mixer_control\s+"{mixer}"')
                        self.assertRegex(conf, r'mixer_type\s+"hardware"')
                        self.assertRegex(conf, r'device\s+"hw:CARD=JM7MAX"')        # opened directly: no ALSA conversion
                        self.assertRegex(conf, r'bind_to_address\s+"127.0.0.1"')    # MPD itself is not on the network
                        self.assertEqual(p.stdout, f'--systemd\n{d / "rendered-mpd"}\n')
                        self.assertTrue((d / 'playlists').is_dir())
                    elif kind == 'airplay':
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
        for kind, marker in [('airplay', None), ('spotify', '--mixer\nsoftvol\n'), ('bluetooth', '--volume=software\n'),
                             ('upnp', None)]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                p, d = self._start_player(tmp, kind, '')
                self.assertEqual(p.returncode, 0, p.stderr)
                if kind == 'upnp':
                    conf = (d / 'rendered-mpd').read_text()
                    self.assertRegex(conf, r'mixer_type\s+"software"')
                    for gone in ['@MIXER@', 'mixer_control', 'mixer_device', '"hardware"']:
                        self.assertNotIn(gone, conf)
                    self.assertRegex(conf, r'device\s+"hw:CARD=JM7MAX"')
                elif kind == 'airplay':
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

    def _bt_env(self, d, radios, usable, port=True):
        """Fake /sys/class/bluetooth plus busctl/systemd-run. radios: {name: 'usb'|'serial'}."""
        d = Path(d)
        sysfs = d / 'sys'; mockbin = d / 'bin'
        mockbin.mkdir(exist_ok=True)
        (mockbin / 'busctl').write_text(
            '#!/bin/sh\n# usable radios are listed in $USABLE; a set-property on them succeeds\n'
            'n=${3##*/}\ncase " $USABLE " in *" $n "*) ;; *) exit 1 ;; esac\n'
            '[ "$1" = get-property ] && { [ "$5" = Discoverable ] && echo "b true" || echo \'s "AA:BB:CC:DD:EE:FF"\'; }\nexit 0\n')
        # The real script detaches the re-probe with systemd-run; here run it inline. Instead of the
        # pause, record what the hub port and the "authorized" switch look like half-way, and do what
        # the kernel does while a port is off: the device, and with it the device's "port" link, is
        # gone. (r7 wrote through that link and so never switched the port back on.)
        (mockbin / 'systemd-run').write_text(
            '#!/bin/sh\nfor a; do last=$a; done\nH=$REPROBE_HUBPORT\n'
            'mid() { echo "port=$(cat "$H/disable" 2>/dev/null) authorized=$(cat "$REPROBE_USBDEV/authorized")" >> "$REPROBE_MID"\n'
            '  if [ "$(cat "$H/disable" 2>/dev/null)" = 1 ]; then rm -f "$REPROBE_USBDEV/port"; fi; }\n'
            'eval "$(echo "$last" | sed "s/sleep [0-9]*;/mid;/")"\n'
            'if [ -d "$H" ] && [ "$(cat "$H/disable")" = 0 ]; then ln -sfn "$H" "$REPROBE_USBDEV/port"; fi\n'
            'echo ran >> "$REPROBE_LOG"\n')
        for f in ('busctl', 'systemd-run'):
            (mockbin / f).chmod(0o755)
        for n, typ in radios.items():
            h = sysfs / n
            (h / 'rfkill0').mkdir(parents=True, exist_ok=True)
            (h / 'rfkill0/soft').write_text('0\n')
            iface = d / f'{typ}dev-{n}' / f'{typ}-if'              # .../<device>/<interface>, as in sysfs
            iface.mkdir(parents=True, exist_ok=True)
            (iface.parent / 'authorized').write_text('1\n')
            if typ == 'usb' and port:                                  # the hub port's on/off switch (Linux 6.0+)
                hubport = d / 'hub' / f'port-{n}'                      # lives in the hub's directory;
                hubport.mkdir(parents=True, exist_ok=True)             # the device only has a link to it
                (hubport / 'disable').write_text('0\n')
                (iface.parent / 'port').symlink_to(hubport)
            if not (h / 'device').exists():
                (h / 'device').symlink_to(iface)
        settings = d / 'streamer.txt'
        env = dict(os.environ, STREAMER_TXT=str(settings), BT_SYSFS=str(sysfs), BT_STATE=str(d / 'reprobe-count'),
                   BT_WAIT='0', USABLE=' '.join(usable), REPROBE_LOG=str(d / 'reprobe.log'),
                   REPROBE_MID=str(d / 'reprobe.mid'), REPROBE_USBDEV=str(d / 'usbdev-hci1'),
                   REPROBE_HUBPORT=str(d / 'hub' / 'port-hci1'),
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
            port = d / 'hub' / 'port-hci1' / 'disable'
            for attempt in (1, 2, 3):
                p = subprocess.run(['/bin/sh', script], capture_output=True, text=True, env=env)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn(f're-probing it (hub port reset), attempt {attempt} of 3', p.stdout)
                self.assertNotIn('using=', p.stdout)                   # nothing selected yet: wait for the radio
                self.assertEqual(port.read_text().strip(), '0', 'the hub port must end up switched back on')
                self.assertTrue((d / 'usbdev-hci1' / 'port').is_symlink(), 'the dongle must be back')
                self.assertEqual(auth.read_text().strip(), '1')
                self.assertEqual((d / 'reprobe-count').read_text().strip(), str(attempt))
            self.assertEqual((d / 'reprobe.log').read_text().count('ran'), 3)
            # half-way through each reset the port was off; the software switch was never used
            self.assertEqual((d / 'reprobe.mid').read_text().splitlines(), ['port=1 authorized=1'] * 3)
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

    def test_dead_usb_radio_without_a_port_switch_is_replugged_in_software(self):
        """Kernels older than 6.0 have no hub port switch: fall back to the USB "authorized" switch."""
        script = str(LIBEXEC / 'bt-select')
        with tempfile.TemporaryDirectory() as tmp:
            d, sysfs, settings, env = self._bt_env(tmp, {'hci0': 'serial', 'hci1': 'usb'}, ['hci0'], port=False)
            settings.write_text('bluetooth=auto\n')
            p = subprocess.run(['/bin/sh', script], capture_output=True, text=True, env=env)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('re-probing it (software re-plug), attempt 1 of 3', p.stdout)
            self.assertEqual((d / 'reprobe.mid').read_text().splitlines(), ['port= authorized=0'])
            self.assertEqual((d / 'usbdev-hci1' / 'authorized').read_text().strip(), '1')

    def test_ldac_is_built_in_from_a_pinned_licensed_source(self):
        ext = BASE / 'br2-streamer'
        mk = (ext / 'package/libldac/libldac.mk').read_text()
        version = re.search(r'^LIBLDAC_VERSION = ([0-9a-f]{40})$', mk, re.M).group(1)      # a commit, not a branch
        self.assertIn('$(call github,open-vela,external_libldac,$(LIBLDAC_VERSION))', mk)
        self.assertNotIn('O2C14', mk)                                   # the decoder without a license
        self.assertIn('LIBLDAC_LICENSE = Apache-2.0', mk)
        self.assertIn('LIBLDAC_LICENSE_FILES = LICENSE NOTICE', mk)
        for f in ('LICENSE', 'NOTICE'):                                # shipped with the binary, as the license asks
            self.assertIn(f'$(TARGET_DIR)/usr/share/licenses/libldac/{f}', mk)
        hashes = (ext / 'package/libldac/libldac.hash').read_text()
        self.assertRegex(hashes, rf'sha256  [0-9a-f]{{64}}  libldac-{version}\.tar\.gz')
        self.assertIn('source "$BR2_EXTERNAL_STREAMER_PATH/package/libldac/Config.in"', (ext / 'Config.in').read_text())
        defconfig = (ext / 'configs/streamer_zero2w_defconfig').read_text()
        self.assertIn('BR2_PACKAGE_LIBLDAC=y', defconfig)
        self.assertIn('$(BR2_EXTERNAL_STREAMER_PATH)/patches"', defconfig)
        external = (ext / 'external.mk').read_text()
        self.assertIn('BLUEZ_ALSA_CONF_OPTS += --enable-ldac', external)
        self.assertIn('$(BLUEZ_ALSA_TARGET_CONFIGURE): | libldac', external)   # libldac first
        pc = (ext / 'package/libldac/ldacBT.pc.in').read_text()
        self.assertIn('Name: ldacBT-@MODULE@', pc)
        self.assertRegex(mk, r'foreach m,enc dec abr')                 # the three names bluez-alsa's configure asks for
        unit = (UNITS / 'streamer-bluealsa.service').read_text()
        self.assertIn('-p a2dp-sink -c AAC -c aptX -c aptX-HD -c LDAC', unit)
        readme = (BASE / 'README.md').read_text()
        for text in ['open-vela/external_libldac', 'Apache', 'not certified', 'trademark of Sony']:
            self.assertIn(text, readme)

    def test_bluetooth_volume_follows_the_mixer_scale(self):
        patches = sorted((BASE / 'br2-streamer/patches/bluez-alsa').glob('*.patch'))
        self.assertEqual([p.name[:4] for p in patches], ['0001', '0002'])
        volume = patches[0].read_text()
        self.assertIn('+++ b/utils/aplay/aplay.c', volume)
        self.assertIn('+	if ((err = snd_mixer_selem_set_playback_volume_all(elem, raw)) != 0) {', volume)
        self.assertIn('-	if ((err = snd_mixer_selem_set_playback_dB_all(elem, db, 0)) != 0) {', volume)
        # the two conversions of the patch, phone (0-127) <-> JM7MAX mixer (0-148), agree with each other
        to_mixer = lambda v: round(v / 127 * 148)
        to_phone = lambda raw: round(raw / 148 * 127)
        self.assertEqual([to_mixer(v) for v in (0, 51, 64, 127)], [0, 59, 75, 148])   # 40% -> 40%, 50% -> 50%
        self.assertEqual([to_phone(to_mixer(v)) for v in range(128)], list(range(128)))
        player = (LIBEXEC / 'start-player').read_text()
        self.assertIn('--volume=mixer', player)
        # the network player (MPD) gets the same mapping
        mpd = (BASE / 'br2-streamer/patches/mpd/0001-alsa-mixer-map-volume-linearly-onto-the-mixer-range.patch').read_text()
        self.assertIn('+++ b/src/mixer/plugins/AlsaMixerPlugin.cxx', mpd)
        self.assertIn('-	int err = set_normalized_playback_volume(elem, 0.01*volume, 1);', mpd)
        self.assertIn('+		err = snd_mixer_selem_set_playback_volume_all(elem,', mpd)

    def _ssh_env(self, d, settings_text, shadow="root:*:::::::\ndaemon:*:::::::\n"):
        d = Path(d)
        mockbin = d / 'bin'; mockbin.mkdir(exist_ok=True)
        # stand-in for BusyBox mkpasswd: password must arrive on stdin (-P 0), never as an argument
        (mockbin / 'mkpasswd').write_text('#!/bin/sh\necho "$*" >> "$MKPASSWD_ARGS"\n'
                                          'printf \'$6$testsalt$%s\\n\' "$(cat | shasum -a 256 | cut -c1-40)"\n')
        (mockbin / 'mkpasswd').chmod(0o755)
        (d / 'streamer.txt').write_text(settings_text)
        (d / 'shadow').write_text(shadow)
        env = dict(os.environ, STREAMER_TXT=str(d / 'streamer.txt'), SSH_RUN=str(d / 'run'), SSH_KEEP=str(d / 'data/ssh'),
                   SSH_SHADOW=str(d / 'shadow'), SSH_BIND='0', MKPASSWD_ARGS=str(d / 'mkpasswd.args'),
                   PATH=str(mockbin) + ':' + os.environ['PATH'])
        return d, env

    def _run_ssh_setup(self, env):
        return subprocess.run(['/bin/sh', str(LIBEXEC / 'ssh-setup')], capture_output=True, text=True, env=env)

    def test_ssh_is_off_by_default(self):
        shipped = (BOARD / 'streamer.txt').read_text()
        self.assertIn('\nssh_password=\n', shipped)                    # the published image ships with SSH off
        for text, reason in [(shipped, 'not set'), ('ssh_password=\r\n', 'not set'), ('ssh_password=short7!\n', 'shorter than 8')]:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                d, env = self._ssh_env(tmp, text)
                p = self._run_ssh_setup(env)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn(reason, p.stdout)
                self.assertFalse((d / 'run/enabled').exists())
                self.assertFalse((d / 'data').exists(), 'no host keys are created while SSH is off')
                self.assertFalse((d / 'run/shadow').exists())

    def test_ssh_password_enables_login_with_per_device_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            password = 'corr3ct horse$battery'
            d, env = self._ssh_env(tmp, f'ssid=x\nssh_password={password}\r\ndebug=0\n')
            p = self._run_ssh_setup(env)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertTrue((d / 'run/enabled').exists())
            # password: hashed from stdin, only root's entry changed, original file untouched
            self.assertNotIn(password, (d / 'mkpasswd.args').read_text())
            self.assertNotIn(password, p.stdout + p.stderr)
            lines = (d / 'run/shadow').read_text().splitlines()
            self.assertRegex(lines[0], r'^root:\$6\$testsalt\$[0-9a-f]{40}:::::::$')
            self.assertEqual(lines[1], 'daemon:*:::::::')
            self.assertEqual((d / 'shadow').read_text().splitlines()[0], 'root:*:::::::')
            self.assertEqual(oct((d / 'run/shadow').stat().st_mode & 0o777), '0o600')
            # host keys: created on the data partition, copied for sshd, private
            keys = {}
            for typ in ('ed25519', 'ecdsa'):
                kept = d / f'data/ssh/ssh_host_{typ}_key'
                self.assertEqual(kept.read_text(), (d / f'run/ssh_host_{typ}_key').read_text())
                self.assertEqual(oct(kept.stat().st_mode & 0o777), '0o600')
                keys[typ] = kept.read_text()
            self.assertIn('created a new ed25519 host key', p.stdout)
            # second boot: same keys, nothing regenerated
            p = self._run_ssh_setup(env)
            self.assertNotIn('created a new', p.stdout)
            for typ in keys:
                self.assertEqual((d / f'data/ssh/ssh_host_{typ}_key').read_text(), keys[typ])
            # a damaged key is replaced
            (d / 'data/ssh/ssh_host_ed25519_key').write_text('garbage\n')
            p = self._run_ssh_setup(env)
            self.assertIn('created a new ed25519 host key', p.stdout)
            self.assertNotIn('created a new ecdsa', p.stdout)
            # a different device (fresh data partition) gets different keys
            with tempfile.TemporaryDirectory() as other:
                d2, env2 = self._ssh_env(other, f'ssh_password={password}\n')
                self._run_ssh_setup(env2)
                self.assertNotEqual((d2 / 'data/ssh/ssh_host_ecdsa_key').read_text(), keys['ecdsa'])
            # removing the password switches SSH off again
            (d / 'streamer.txt').write_text('ssh_password=\n')
            p = self._run_ssh_setup(env)
            self.assertFalse((d / 'run/enabled').exists())
            self.assertFalse((d / 'run/shadow').exists())

    def test_ssh_setup_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:                     # no root entry to put the password on
            d, env = self._ssh_env(tmp, 'ssh_password=longenough1\n', shadow='daemon:*:::::::\n')
            p = self._run_ssh_setup(env)
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse((d / 'run/enabled').exists())
        with tempfile.TemporaryDirectory() as tmp:                     # hashing tool broken
            d, env = self._ssh_env(tmp, 'ssh_password=longenough1\n')
            (d / 'bin/mkpasswd').write_text('#!/bin/sh\nexit 1\n')
            p = self._run_ssh_setup(env)
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse((d / 'run/enabled').exists())

    def test_nothing_secret_is_built_into_the_image(self):
        post = (BOARD / 'post-build.sh').read_text()
        self.assertNotIn('secrets', post)
        self.assertNotIn('authorized_keys', post)
        self.assertIn("root:*:", post)                                 # root password locked in the image
        tracked = subprocess.run(['git', 'ls-files'], cwd=BASE, capture_output=True, text=True).stdout.split()
        self.assertTrue(tracked)
        bad = [f for f in tracked if 'ssh_host' in f or 'authorized_keys' in f or '/secrets/' in f or f.endswith(('.img', '.xz', '.pem'))]
        self.assertEqual(bad, [])
        sshd = (OVERLAY / 'etc/ssh/sshd_config').read_text()
        self.assertIn('HostKey /run/streamer-ssh/ssh_host_ed25519_key', sshd)
        self.assertNotIn('/etc/ssh/ssh_host', sshd)
        dropin = (UNITS / 'sshd.service.d/streamer.conf').read_text()
        self.assertIn('ConditionPathExists=/run/streamer-ssh/enabled', dropin)
        self.assertIn('After=streamer-ssh-setup.service', dropin)
        self.assertIn('\nExecStartPre=\n', dropin)                     # no "ssh-keygen -A" on the read-only root
        self.assertIn('umask=0077', post)                              # streamer.txt readable by root only

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
            settings.write_text('ssid=HomeNet\npsk=TopSecret123\nssh_password=AlsoSecret456\ndebug=1\n')
            p = sh(script, '0', '0')
            self.assertEqual(p.returncode, 0, p.stderr)
            saved = (d / 'saved.txt').read_text(errors='replace')
            self.assertIn('ssid=HomeNet', saved)
            self.assertIn('psk=<hidden>', saved)
            self.assertIn('ssh_password=<hidden>', saved)
            self.assertNotIn('TopSecret123', saved)
            self.assertNotIn('AlsoSecret456', saved)

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
        for key in ['ssid=', 'psk=', 'country=IN', 'bluetooth=auto', 'ssh_password=', 'debug=0']:
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
        network = (OVERLAY / 'etc/systemd/network/30-wlan0.network').read_text()
        self.assertIn('DHCP=yes', network)
        self.assertIn('ClientIdentifier=mac', network)             # same address at every boot
        resolved = (OVERLAY / 'etc/systemd/resolved.conf.d/streamer.conf').read_text()
        self.assertIn('MulticastDNS=no', resolved)                     # Avahi is the only mDNS responder
        rules = (OVERLAY / 'etc/udev/rules.d/99-streamer-dac.rules').read_text()
        self.assertIn('ENV{ID_VENDOR_ID}=="06cb", ENV{ID_MODEL_ID}=="1595"', rules)
        ready = (LIBEXEC / 'dac-ready').read_text()
        for unit in ['shairport-sync.service', 'librespot.service', 'streamer-bluealsa-aplay.service', 'streamer-mpd.service']:
            self.assertEqual(ready.count(unit), 2, unit)               # reset-failed and restart

    def test_network_player(self):
        """UPnP/DLNA: MPD plays on the DAC, upmpdcli is the part phones see. Neither runs as root."""
        mpd = (UNITS / 'streamer-mpd.service').read_text()
        for key in ['Type=notify', 'User=streamer-mpd', 'SupplementaryGroups=audio', 'RuntimeDirectory=streamer-mpd',
                    'ExecStart=/usr/libexec/streamer/start-player upnp', 'NoNewPrivileges=yes', 'ProtectSystem=strict',
                    'Restart=always', 'WantedBy=multi-user.target']:
            self.assertIn(key, mpd)
        upnp = (UNITS / 'streamer-upnp.service').read_text()
        for key in ['BindsTo=streamer-mpd.service', 'After=streamer-mpd.service', 'User=upmpdcli',
                    'RuntimeDirectory=streamer-upnp', 'ExecStart=/usr/bin/upmpdcli -c /etc/streamer-upnp.conf',
                    'NoNewPrivileges=yes', 'ProtectSystem=strict', 'WantedBy=streamer-mpd.service']:
            self.assertIn(key, upnp)
        conf = dict(l.split(' = ', 1) for l in (OVERLAY / 'etc/streamer-upnp.conf').read_text().splitlines()
                    if l and not l.startswith('#'))
        self.assertEqual((conf['friendlyname'], conf['avfriendlyname']), ('Streamer', 'Streamer'))
        self.assertEqual((conf['upnpav'], conf['openhome']), ('1', '0'))   # one device on the network, not two
        self.assertEqual((conf['mpdhost'], conf['mpdport']), ('127.0.0.1', '6600'))
        self.assertEqual(conf['cachedir'], '/run/streamer-upnp')        # the root filesystem is read-only
        mpdconf = (OVERLAY / 'etc/streamer-mpd.conf').read_text()
        self.assertNotIn('/var/', mpdconf)
        self.assertNotIn('music_directory', mpdconf)                    # plays what it is sent; no library
        users = (BOARD / 'users.txt').read_text()
        self.assertIn('streamer-mpd 501 streamer-mpd 501 * - /bin/false audio ', users)
        post = (BOARD / 'post-build.sh').read_text()
        self.assertIn('mpd.service mpd.socket upmpdcli.service', post)  # the packaged units are masked
        self.assertIn('rm -f "$T/etc/mpd.conf" "$T/etc/upmpdcli.conf"', post)
        config = (BASE / 'br2-streamer/configs/streamer_zero2w_defconfig').read_text()
        for setting in ['BR2_PACKAGE_MPD=y', 'BR2_PACKAGE_MPD_CURL=y', 'BR2_PACKAGE_MPD_FLAC=y', 'BR2_PACKAGE_MPD_FFMPEG=y',
                        'BR2_PACKAGE_MPD_LIBSOXR=y', 'BR2_PACKAGE_UPMPDCLI=y']:
            self.assertIn(setting, config)
        self.assertIn('CONFIG_NC=y\nCONFIG_NC_EXTRA=y', (BOARD / 'busybox.fragment').read_text())   # nc -w
        status = (OVERLAY / 'usr/share/streamer-www/cgi-bin/status').read_text()
        self.assertIn('mpd) src=UPnP ;;', status)
        self.assertIn('nc -w 2 127.0.0.1 6600', status)
        self.assertIn('streamer-mpd streamer-upnp', status)
        html = (OVERLAY / 'usr/share/streamer-www/index.html').read_text()
        self.assertIn("d.source === 'UPnP'", html)
        self.assertNotIn('ossless', html.replace('do not prove lossless audio', ''))   # the page claims nothing

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
