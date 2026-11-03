#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Run from a fresh extracted source bundle. Creates ordinary image files only.
set -euo pipefail
REBUILD_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOTFS_IMAGE=${FIREFLY_ROOTFS_IMAGE:-firefly-ubuntu22-builder:local}
CROSS_IMAGE=${FIREFLY_BUILD_IMAGE:-firefly-ubuntu22-cross:local}
OUTPUT_NAME=${FIREFLY_OUTPUT_NAME:-firefly-rk3288-ubuntu22.04-gnome-armhf}
STEP=${1:-help}

usage() {
  cat <<'HELP'
Usage: ./rebuild.sh {all|fetch|check|tools|kernel|bootloader|rootfs|finalize|image}
  all        Build tools, kernel, U-Boot, a fresh rootfs, then finalize and image.
  fetch      Download and verify the pinned Ubuntu Base, Linux and U-Boot inputs.
  check      Check source files, SHA-256 values and Docker access.
  tools      Build the two Docker tool images.
  kernel     Build kernel, modules and Firefly device tree.
  bootloader Rebuild U-Boot and copy the two loader files into bootloader/.
  rootfs     Install Ubuntu/GNOME packages into a fresh rootfs/ directory.
  finalize   Install kernel modules and initramfs; apply overlay and clean rootfs.
  image      Assemble artifacts/<name>.img, gzip it, and write SHA256SUMS.

Run all in a fresh checkout or extracted directory. Individual stages allow continuation
from their documented inputs. Existing final images are never overwritten.
Environment: FIREFLY_ROOTFS_IMAGE, FIREFLY_BUILD_IMAGE, FIREFLY_OUTPUT_NAME.
See docs/REBUILD.md for prerequisites, layout and update instructions.
HELP
}

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
need() { [[ -f "$REBUILD_ROOT/$1" ]] || fail "Missing $1"; }
check_name() {
  [[ "$OUTPUT_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || fail 'FIREFLY_OUTPUT_NAME must be a simple file name without a path'
}
check_docker() {
  command -v docker >/dev/null || fail 'Docker is required'
  docker info >/dev/null
}
fetch_inputs() {
  command -v python3 >/dev/null || fail 'Python 3 is required for source downloads'
  python3 "$REBUILD_ROOT/scripts/fetch-sources.py"
}
verify_sha() {
  printf '%s  %s\n' "$2" "$1" | (cd "$REBUILD_ROOT" && sha256sum -c -)
}
check_inputs() {
  for p in builder/Dockerfile kernel/Dockerfile kernel/build-kernel.sh \
    kernel/firefly-ubuntu22.config kernel/rk3288-firefly-ubuntu22.dts \
    kernel/source.sha256 kernel/linux-6.6.161.tar.xz \
    bootloader/source/rebuild-u-boot.sh bootloader/source/u-boot-v2024.01.tar.gz \
    downloads/ubuntu-base-22.04.5-base-armhf.tar.gz \
    scripts/install-rootfs.sh scripts/finalize-rootfs.sh \
    scripts/configure-rootfs.sh scripts/assemble-image.py scripts/verify-image.py; do need "$p"; done
  [[ -d "$REBUILD_ROOT/overlay" ]] || fail 'Missing overlay/'
  verify_sha downloads/ubuntu-base-22.04.5-base-armhf.tar.gz fd77cb0659326b75c08ce06b6b8649d2e13ef9a704a8e9212fec32cb97d42add
  verify_sha bootloader/source/u-boot-v2024.01.tar.gz a03c3c2ba9d2bea5176c6406f1f3429a79e1147be242f5a07dbd9e89b3cc83c4
  (cd "$REBUILD_ROOT/kernel" && sha256sum -c source.sha256)
}
require_fresh_rootfs() {
  if [[ -d "$REBUILD_ROOT/rootfs" ]] && [[ -n "$(ls -A "$REBUILD_ROOT/rootfs")" ]]; then
    fail 'rootfs/ is not empty. Use a new extracted source directory for a fresh build; existing data was left intact.'
  fi
}
build_tools() {
  docker build -t "$ROOTFS_IMAGE" "$REBUILD_ROOT/builder"
  docker build -t "$CROSS_IMAGE" "$REBUILD_ROOT/kernel"
}
build_kernel() {
  FIREFLY_BUILD_IMAGE="$CROSS_IMAGE" bash "$REBUILD_ROOT/kernel/build-kernel.sh"
}
build_bootloader() {
  FIREFLY_BUILD_IMAGE="$CROSS_IMAGE" bash "$REBUILD_ROOT/bootloader/source/rebuild-u-boot.sh"
  install -m 0644 "$REBUILD_ROOT/bootloader/source/build/idbloader.img" "$REBUILD_ROOT/bootloader/idbloader.img"
  install -m 0644 "$REBUILD_ROOT/bootloader/source/build/u-boot-dtb.img" "$REBUILD_ROOT/bootloader/u-boot-dtb.img"
}
run_rootfs_script() {
  # Mounts and ARM binfmt registration are confined to these build stages.
  # The scripts restore registrations they create and unmount in an EXIT trap.
  docker run --rm --privileged -v "$REBUILD_ROOT:/build" -w /build \
    "$ROOTFS_IMAGE" bash "/build/scripts/$1"
}
build_rootfs() {
  require_fresh_rootfs
  mkdir -p "$REBUILD_ROOT/rootfs"
  run_rootfs_script install-rootfs.sh
}
finalize_rootfs() {
  need rootfs/etc/os-release
  need kernel/build/arch/arm/boot/zImage
  need kernel/build/arch/arm/boot/dts/rockchip/rk3288-firefly-ubuntu22.dtb
  [[ -d "$REBUILD_ROOT/kernel/staging/lib/modules/6.6.161-firefly" ]] || fail 'Kernel modules are missing'
  run_rootfs_script finalize-rootfs.sh
}
build_image() {
  need rootfs/etc/os-release
  need boot-files/boot/zImage
  need boot-files/boot/initrd.img
  need boot-files/boot/rk3288-firefly.dtb
  need boot-files/extlinux/extlinux.conf
  need bootloader/idbloader.img
  need bootloader/u-boot-dtb.img
  check_name
  mkdir -p "$REBUILD_ROOT/artifacts"
  local image="$REBUILD_ROOT/artifacts/$OUTPUT_NAME.img"
  [[ ! -e "$image" && ! -L "$image" ]] || fail "Output exists: $image"
  [[ ! -e "$image.gz" && ! -L "$image.gz" ]] || fail "Output exists: $image.gz"
  [[ ! -e "$image.gz.partial" && ! -L "$image.gz.partial" ]] || fail "Output exists: $image.gz.partial"
  # Assembly uses file-based mkfs/mtools; it needs no host-device access.
  docker run --rm -v "$REBUILD_ROOT:/build" -w /build "$ROOTFS_IMAGE" \
    python3 /build/scripts/assemble-image.py "/build/artifacts/$OUTPUT_NAME.img"
  docker run --rm -v "$REBUILD_ROOT:/build" -w /build "$ROOTFS_IMAGE" \
    python3 /build/scripts/verify-image.py "/build/artifacts/$OUTPUT_NAME.img"
  gzip -n -6 -c "$image" > "$image.gz.partial"
  mv -- "$image.gz.partial" "$image.gz"
  (cd "$REBUILD_ROOT/artifacts" && sha256sum "$OUTPUT_NAME.img" "$OUTPUT_NAME.img.gz" > "$OUTPUT_NAME.SHA256SUMS")
  printf 'Image: %s\nCompressed image: %s\nChecksums: %s\n' "$image" "$image.gz" "$REBUILD_ROOT/artifacts/$OUTPUT_NAME.SHA256SUMS"
}

case "$STEP" in
  help|-h|--help) usage; exit 0 ;;
  all|fetch|check|tools|kernel|bootloader|rootfs|finalize|image) ;;
  *) usage >&2; exit 2 ;;
esac
if [[ "$STEP" == fetch ]]; then fetch_inputs; exit 0; fi
check_docker
case "$STEP" in
  all) require_fresh_rootfs; fetch_inputs; check_inputs; build_tools; build_kernel; build_bootloader; build_rootfs; finalize_rootfs; build_image ;;
  check) check_inputs ;;
  tools) build_tools ;;
  kernel) build_kernel ;;
  bootloader) build_bootloader ;;
  rootfs) build_rootfs ;;
  finalize) finalize_rootfs ;;
  image) build_image ;;
esac
