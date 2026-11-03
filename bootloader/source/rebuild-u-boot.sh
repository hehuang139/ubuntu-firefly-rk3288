#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
# Run from any directory. No /dev device is read or written.
TASK_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
IMAGE=${FIREFLY_BUILD_IMAGE:-firefly-ubuntu22-cross:local}
ARCHIVE="$TASK_DIR/u-boot-v2024.01.tar.gz"
if [[ ! -f "$ARCHIVE" ]]; then
  curl -fL --retry 3 'https://codeload.github.com/u-boot/u-boot/tar.gz/refs/tags/v2024.01' -o "$ARCHIVE"
fi
(cd "$TASK_DIR" && printf '%s  %s\n' 'a03c3c2ba9d2bea5176c6406f1f3429a79e1147be242f5a07dbd9e89b3cc83c4' 'u-boot-v2024.01.tar.gz' | sha256sum -c -)
if [[ ! -d "$TASK_DIR/u-boot-2024.01" ]]; then
  tar -xzf "$ARCHIVE" -C "$TASK_DIR"
fi
docker run --rm --user "$(id -u):$(id -g)" \
  -e SOURCE_DATE_EPOCH=1704672000 \
  -v "$TASK_DIR:/build" -w /build/u-boot-2024.01 "$IMAGE" \
  bash -c '
    set -euo pipefail
    make CROSS_COMPILE=arm-linux-gnueabihf- O=../build firefly-rk3288_defconfig
    scripts/config --file ../build/.config \
      --disable ENV_IS_IN_MMC --enable ENV_IS_NOWHERE \
      --disable SILENT_CONSOLE --enable BOOTSTD_FULL \
      --set-val BOOTDELAY 5 \
      --set-str BOOTCOMMAND "setenv boot_targets mmc1; bootflow scan -lb" \
      --set-str LOCALVERSION "-firefly-sd1"
    make CROSS_COMPILE=arm-linux-gnueabihf- O=../build olddefconfig
    make -j8 CROSS_COMPILE=arm-linux-gnueabihf- O=../build
  '
sha256sum "$TASK_DIR/build/idbloader.img" "$TASK_DIR/build/u-boot-dtb.img" "$TASK_DIR/build/u-boot-rockchip.bin"
