# SPDX-License-Identifier: MIT
FROM ubuntu:22.04
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       build-essential pkg-config ninja-build python3 python3-venv python3-tomli \
       libglib2.0-dev libpixman-1-dev libfdt-dev zlib1g-dev libslirp-dev \
       device-tree-compiler e2fsprogs \
    && rm -rf /var/lib/apt/lists/*
