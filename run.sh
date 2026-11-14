#!/bin/bash
# Run a command in the build container, in the Buildroot tree. Usage: ./run.sh '<shell command>'
cd "$(dirname "$0")"
exec docker run --rm -v streamer-br:/work -v "$PWD/br2-streamer:/br2-streamer:ro" \
  -w /work/buildroot streamer-br-builder bash -c "$1"
