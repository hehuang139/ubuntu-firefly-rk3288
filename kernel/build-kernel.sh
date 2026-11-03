#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
KERNEL_TASK_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
KERNEL_BUILD_IMAGE=${FIREFLY_BUILD_IMAGE:-firefly-ubuntu22-cross:local}
KERNEL_VERSION=6.6.161
KERNEL_ARCHIVE="$KERNEL_TASK_DIR/linux-$KERNEL_VERSION.tar.xz"
KERNEL_SRC="$KERNEL_TASK_DIR/linux-$KERNEL_VERSION"
if [[ ! -f "$KERNEL_ARCHIVE" ]]; then
    curl -fL --retry 3 "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-$KERNEL_VERSION.tar.xz" -o "$KERNEL_ARCHIVE"
fi
(cd "$KERNEL_TASK_DIR" && sha256sum -c source.sha256)
if [[ ! -d "$KERNEL_SRC" ]]; then
    tar -xJf "$KERNEL_ARCHIVE" -C "$KERNEL_TASK_DIR"
fi
cp "$KERNEL_TASK_DIR/rk3288-firefly-ubuntu22.dts" "$KERNEL_SRC/arch/arm/boot/dts/rockchip/"
if ! grep -q '^dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3288-firefly-ubuntu22.dtb$' "$KERNEL_SRC/arch/arm/boot/dts/rockchip/Makefile"; then
    printf '%s\n' 'dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3288-firefly-ubuntu22.dtb' >> "$KERNEL_SRC/arch/arm/boot/dts/rockchip/Makefile"
fi
docker run --rm --user "$(id -u):$(id -g)" \
    -e KBUILD_BUILD_TIMESTAMP='2026-10-30 00:00:00 UTC' \
    -e KBUILD_BUILD_USER=firefly -e KBUILD_BUILD_HOST=builder \
    -e KBUILD_BUILD_VERSION=1 \
    -v "$KERNEL_TASK_DIR:/kernel" -w "/kernel/linux-$KERNEL_VERSION" \
    "$KERNEL_BUILD_IMAGE" bash -c '
      set -euo pipefail
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build multi_v7_defconfig
      ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- scripts/kconfig/merge_config.sh -m -O ../build ../build/.config ../firefly-ubuntu22.config
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build olddefconfig
      make -j12 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build zImage modules rockchip/rk3288-firefly-ubuntu22.dtb
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build INSTALL_MOD_PATH=/kernel/staging INSTALL_MOD_STRIP=1 DEPMOD=true modules_install
    '
# Headers are delivered as sources, not an installed kernel-headers package.
# Remove build-system symlinks that point into the temporary Docker directory.
for KERNEL_LINK in "$KERNEL_TASK_DIR/staging/lib/modules/6.6.161-firefly/build" "$KERNEL_TASK_DIR/staging/lib/modules/6.6.161-firefly/source"; do
    if [[ -L "$KERNEL_LINK" ]]; then
        rm -- "$KERNEL_LINK"
    fi
done
