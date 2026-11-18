#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 QEMU_SOURCE BUILD_DIRECTORY" >&2
    exit 2
fi
src=$(realpath "$1")
build=$(realpath -m "$2")
model=$(dirname "$(realpath "$0")")
[ "$(cat "$src/VERSION")" = 10.2.0 ]
if ! cmp -s "$model/firefly-rk3288.c" "$src/hw/arm/firefly-rk3288.c"; then
    cp "$model/firefly-rk3288.c" "$src/hw/arm/firefly-rk3288.c"
fi
if ! grep -q 'CONFIG_FIREFLY_RK3288' "$src/hw/arm/meson.build"; then
    printf "\narm_ss.add(when: 'CONFIG_FIREFLY_RK3288', if_true: files('firefly-rk3288.c'))\n" >> "$src/hw/arm/meson.build"
fi
if ! grep -q '^config FIREFLY_RK3288$' "$src/hw/arm/Kconfig"; then
    cat >> "$src/hw/arm/Kconfig" <<'KCONFIG'

config FIREFLY_RK3288
    bool
    depends on TCG
    select ARM_GIC
    select SERIAL_MM
    select PL031
    select VIRTIO_MMIO
    select VIRTIO_BLK
    select VIRTIO_GPU
    select VIRTIO_INPUT
    select VIRTIO_RNG
KCONFIG
fi
config="$src/configs/devices/arm-softmmu/firefly-rk3288.mak"
if [ ! -f "$config" ] || ! grep -qxF CONFIG_VIRTIO_NET=y "$config" ||
   ! grep -qxF CONFIG_FIREFLY_RK3288=y "$config"; then
    printf 'CONFIG_FIREFLY_RK3288=y\nCONFIG_VIRTIO_NET=y\n' > "$config"
fi
mkdir -p "$build"
cd "$build"
if [ ! -f build.ninja ]; then
    "$src/configure" --target-list=arm-softmmu \
        --with-devices-arm=firefly-rk3288 --without-default-devices \
        --without-default-features --enable-tcg --enable-fdt=system \
        --enable-tools --enable-pixman --enable-vnc --enable-slirp --disable-download --disable-docs
else
    meson=$(realpath pyvenv/bin/meson)
    "$meson" configure -Dslirp=enabled
fi
ninja -j "${JOBS:-$(nproc)}" qemu-system-arm qemu-img
mkdir -p keymaps
cp "$src/pc-bios/keymaps/en-us" keymaps/en-us
