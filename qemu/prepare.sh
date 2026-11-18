#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
model=$(dirname "$(realpath "$0")")
repo=$(dirname "$model")
work=$(realpath -m "${FIREFLY_QEMU_WORK:-$model/work}")
qemu_image=${FIREFLY_QEMU_IMAGE:-firefly-rk3288-qemu:10.2.0}
cross_image=${FIREFLY_BUILD_IMAGE:-firefly-ubuntu22-cross:local}
config="$repo/kernel/config-6.6.161-firefly"
[ -f "$config" ] || { echo "Missing release kernel config: $config" >&2; exit 1; }
mkdir -p "$work"
cd "$work"
fetch() {
    if [ ! -f "$2" ]; then
        curl --fail --location --retry 3 "$1" -o "$2.partial"
        mv -- "$2.partial" "$2"
    fi
    printf '%s  %s\n' "$3" "$2" | sha256sum -c -
}
fetch https://download.qemu.org/qemu-10.2.0.tar.xz qemu-10.2.0.tar.xz \
    9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a
fetch https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.6.161.tar.xz linux-6.6.161.tar.xz \
    7d34405be5cd4989b2a5e9cbefa798e3a175218901271e034af3fe4e840b71c6
for src in qemu-10.2.0 linux-6.6.161; do
    if [ ! -d "$src" ]; then
        tar -xJf "$src.tar.xz"
    fi
done

docker build -t "$qemu_image" "$model"
docker build -t "$cross_image" "$repo/kernel"
docker run --rm --network none --user "$(id -u):$(id -g)" -e JOBS="${JOBS:-$(nproc)}" \
    -v "$model:/model:ro" -v "$work:/build" -w /build "$qemu_image" sh -ec '
        /model/build-qemu.sh qemu-10.2.0 qemu-build
        dtc -I dts -O dtb -o firefly-rk3288.dtb /model/firefly-rk3288.dts
    '
docker run --rm --network none --user "$(id -u):$(id -g)" -e JOBS="${JOBS:-$(nproc)}" \
    -v "$model:/model:ro" --mount "type=bind,src=$config,dst=/config,readonly" \
    -v "$work:/build" -w /build "$cross_image" \
    /model/build-kernel.sh linux-6.6.161 /config linux-build
