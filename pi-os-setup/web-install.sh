#!/bin/bash
set -euo pipefail
W=/usr/local/share/streamer-www
mkdir -p $W/cgi-bin
tar -xzf /tmp/streamer-www.tgz -C $W
chown -R root:root $W; chmod 755 $W/cgi-bin/status; chmod 644 $W/index.html
id streamer-web >/dev/null 2>&1 || useradd -r -M -s /usr/sbin/nologin streamer-web
for g in audio bluetooth video; do getent group $g >/dev/null && usermod -aG $g streamer-web; done
cat > /etc/systemd/system/streamer-status.service <<'U'
[Unit]
Description=Streamer status page (http://streamer.local)
After=network.target

[Service]
User=streamer-web
Group=streamer-web
SupplementaryGroups=audio video
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=yes
Nice=10
IOSchedulingClass=idle
RuntimeDirectory=streamer-web
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ExecStart=/usr/bin/busybox httpd -f -p 80 -h /usr/local/share/streamer-www
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
U
systemctl daemon-reload
systemctl enable --now streamer-status >/dev/null 2>&1
sleep 2; systemctl is-active streamer-status
