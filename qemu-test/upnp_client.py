"""Just enough of a UPnP control point, and of a FLAC encoder, to test the network player.

Used by boot-test.py: find the renderer the way a phone does (SSDP search), read its device
description, tell it to play a URL (AVTransport) and set its volume (RenderingControl).
The FLAC writer stores samples uncompressed ("verbatim" subframes), which every FLAC decoder
must accept; that makes a known, bit-exact test file without needing an encoder program.
"""
import re, socket, struct, urllib.request
from xml.sax.saxutils import escape


def _crc_table(poly, bits):
    top, mask, table = 1 << (bits - 1), (1 << bits) - 1, []
    for n in range(256):
        c = n << (bits - 8)
        for _ in range(8):
            c = ((c << 1) ^ poly) if c & top else (c << 1)
        table.append(c & mask)
    return table


_CRC8, _CRC16 = _crc_table(0x07, 8), _crc_table(0x8005, 16)


def _crc8(data):
    c = 0
    for b in data:
        c = _CRC8[c ^ b]
    return c


def _crc16(data):
    c = 0
    for b in data:
        c = ((c << 8) & 0xFFFF) ^ _CRC16[(c >> 8) ^ b]
    return c


def _utf8_number(n):
    if n < 0x80:
        return bytes([n])
    out, lead, limit = [], 0xC0, 0x20
    while True:
        out.insert(0, 0x80 | (n & 0x3F))
        n >>= 6
        if n < limit:
            return bytes([lead | n] + out)
        lead, limit = (lead >> 1) | 0x80, limit >> 1


def write_flac(path, samples, rate, block=4096):
    """samples: list of (left, right) signed 16-bit integers."""
    total = len(samples)
    info = struct.pack('>HH', block, block) + b'\0' * 6
    info += ((rate << 44) | (1 << 41) | (15 << 36) | total).to_bytes(8, 'big') + b'\0' * 16
    out = [b'fLaC', bytes([0x80, 0, 0, 34]), info]
    for number, start in enumerate(range(0, total, block)):
        chunk = samples[start:start + block]
        header = bytes([0xFF, 0xF8, 0x70, 0x18]) + _utf8_number(number) + struct.pack('>H', len(chunk) - 1)
        frame = header + bytes([_crc8(header)])
        for ch in (0, 1):
            frame += b'\x02' + struct.pack(f'>{len(chunk)}h', *(s[ch] for s in chunk))
        out.append(frame + struct.pack('>H', _crc16(frame)))
    with open(path, 'wb') as f:
        f.write(b''.join(out))


def ssdp_search(host, port, timeout=4, tries=5):
    """Ask the device at host:port (unicast M-SEARCH) for its MediaRenderer; returns the LOCATION URL."""
    msg = ('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 1\r\n'
           'ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n').encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        for _ in range(tries):
            s.sendto(msg, (host, port))
            try:
                while True:
                    data = s.recv(4096).decode(errors='replace')
                    m = re.search(r'^LOCATION:\s*(\S+)', data, re.I | re.M)
                    if m and 'MediaRenderer' in data:
                        return m.group(1), data
            except socket.timeout:
                pass
    finally:
        s.close()
    return None, ''


class Renderer:
    def __init__(self, location, reach):
        """reach: function mapping the device's own URL to one that works from here (port forward)."""
        self.reach = reach
        self.location = location
        # The device only answers requests addressed to itself, so the Host header keeps its own
        # address even when the connection goes through a port forward.
        self.host = re.match(r'https?://([^/]+)', location).group(1)
        req = urllib.request.Request(reach(location), headers={'Host': self.host})
        xml = urllib.request.urlopen(req, timeout=15).read().decode(errors='replace')
        self.description = xml
        self.name = (re.search(r'<friendlyName>([^<]*)', xml) or [None, ''])[1]
        base = re.match(r'(https?://[^/]+)', location).group(1)
        self.control = {}
        for svc in re.findall(r'<service>(.*?)</service>', xml, re.S):
            kind = re.search(r'<serviceType>([^<]*)', svc).group(1)
            url = re.search(r'<controlURL>([^<]*)', svc).group(1)
            self.control[kind] = base + (url if url.startswith('/') else '/' + url)

    def services(self):
        return sorted(k.split(':')[-2] for k in self.control)

    def call(self, service, action, **args):
        kind = next(k for k in self.control if f':{service}:' in k)
        body = ''.join(f'<{k}>{escape(str(v))}</{k}>' for k, v in args.items())
        envelope = ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
                    f'<u:{action} xmlns:u="{kind}">{body}</u:{action}></s:Body></s:Envelope>').encode()
        req = urllib.request.Request(self.reach(self.control[kind]), data=envelope, method='POST', headers={
            'Content-Type': 'text/xml; charset="utf-8"', 'SOAPACTION': f'"{kind}#{action}"', 'Host': self.host})
        try:
            return urllib.request.urlopen(req, timeout=20).read().decode(errors='replace')
        except urllib.error.HTTPError as e:
            return f'HTTP {e.code}: ' + e.read().decode(errors='replace')

    def play(self, url, mime, title='Streamer test'):
        didl = ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"><item id="1" parentID="0" restricted="1">'
                f'<dc:title>{escape(title)}</dc:title><upnp:class>object.item.audioItem.musicTrack</upnp:class>'
                f'<res protocolInfo="http-get:*:{mime}:*">{escape(url)}</res></item></DIDL-Lite>')
        r1 = self.call('AVTransport', 'SetAVTransportURI', InstanceID=0, CurrentURI=url, CurrentURIMetaData=didl)
        r2 = self.call('AVTransport', 'Play', InstanceID=0, Speed=1)
        return r1, r2

    def state(self):
        r = self.call('AVTransport', 'GetTransportInfo', InstanceID=0)
        return (re.search(r'<CurrentTransportState>([^<]*)', r) or [None, r[:120]])[1]

    def set_volume(self, percent):
        return self.call('RenderingControl', 'SetVolume', InstanceID=0, Channel='Master', DesiredVolume=percent)

    def volume(self):
        r = self.call('RenderingControl', 'GetVolume', InstanceID=0, Channel='Master')
        return (re.search(r'<CurrentVolume>([^<]*)', r) or [None, r[:120]])[1]


def compare_capture(wav_path, samples):
    """Compare what the sound card was given (QEMU's recording of the emulated card) with the samples
    of the test file.

    The recording has silence before and after the track and wherever the player had nothing to play
    in time; that is dropped. An emulator that falls behind can also lose whole packets, so the
    recording may be the source with pieces missing. What is checked: every recorded frame is a frame
    of the source, in the source's order. The source is noise, so a frame that was changed in any way
    (volume, resampling, bit depth) cannot be found there.

    Returns frame counts: played (non-silent, recorded), identical (found in order), foreign (not
    found), pieces (number of unbroken pieces), longest (longest unbroken piece), source."""
    with open(wav_path, 'rb') as f:
        pcm = f.read()[44:]
    pcm = pcm[:len(pcm) - len(pcm) % 4]
    ref = b''.join(struct.pack('<hh', *x) for x in samples)
    played = b''.join(pcm[i:i + 4] for i in range(0, len(pcm), 4) if pcm[i:i + 4] != b'\0\0\0\0')
    pv, rv = memoryview(played), memoryview(ref)
    key = 8 * 4                                   # 8 frames of noise identify a position in the source
    i = pos = identical = foreign = pieces = longest = 0
    while i + key <= len(played):
        j = ref.find(played[i:i + key], pos)
        while j >= 0 and j % 4:
            j = ref.find(played[i:i + key], j + 1)
        if j < 0:
            foreign += 1
            i += 4
            continue
        lo, hi = key, min(len(played) - i, len(ref) - j)      # length of the piece: binary search
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if pv[i:i + mid] == rv[j:j + mid]:
                lo = mid
            else:
                hi = mid - 1
        lo -= lo % 4
        identical += lo // 4
        longest = max(longest, lo // 4)
        pieces += 1
        i, pos = i + lo, j + lo
    foreign += (len(played) - i) // 4
    return {'recorded': len(pcm) // 4, 'played': len(played) // 4, 'identical': identical, 'foreign': foreign,
            'pieces': pieces, 'longest': longest, 'source': len(ref) // 4}
