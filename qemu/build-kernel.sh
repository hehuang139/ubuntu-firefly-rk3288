#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 LINUX_SOURCE RELEASE_CONFIG BUILD_DIRECTORY" >&2
    exit 2
fi
src=$(realpath "$1")
base_config=$(realpath "$2")
out=$(realpath -m "$3")
mkdir -p "$out"
cp "$base_config" "$out/.config"
"$src/scripts/config" --file "$out/.config" \
    -e DRM_VIRTIO_GPU -e VIRTIO_INPUT -e HW_RANDOM_VIRTIO
export ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf-
export KBUILD_BUILD_USER=firefly KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1
export KBUILD_BUILD_TIMESTAMP='2026-10-30 00:00:00 UTC'
make -C "$src" O="$out" olddefconfig
for v in DRM_VIRTIO_GPU DRM_VIRTIO_GPU_KMS VIRTIO_INPUT VIRTIO_MMIO VIRTIO_BLK VIRTIO_NET HW_RANDOM_VIRTIO; do
    grep -qx "CONFIG_$v=y" "$out/.config"
done
[ "$(make --no-print-directory -sC "$src" O="$out" kernelrelease)" = 6.6.161-firefly ]
make -j "${JOBS:-$(nproc)}" -C "$src" O="$out" zImage
