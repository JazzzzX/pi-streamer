FROM debian:trixie
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ make git wget curl ca-certificates cpio unzip rsync bc file \
    python3 perl libncurses-dev patch gzip bzip2 xz-utils tar findutils which sed \
    openssh-client locales libssl-dev pkg-config && \
    sed -i 's/# en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && locale-gen && \
    useradd -m -u 1000 br && rm -rf /var/lib/apt/lists/*
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
USER br
WORKDIR /home/br
