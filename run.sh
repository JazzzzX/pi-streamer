#!/bin/bash
# Run a command in the Buildroot container. Usage: ./run.sh '<shell command>'
exec docker run --rm -v streamer-br:/work -v "$HOME/streamer-buildroot/br2-streamer:/br2-streamer:ro" \
  -w /work/buildroot streamer-br-builder bash -c "$1"
