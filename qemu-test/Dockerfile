FROM debian:trixie
RUN apt-get update && apt-get install -y --no-install-recommends \
    qemu-system-arm python3 device-tree-compiler mtools sshpass openssh-client && rm -rf /var/lib/apt/lists/*
