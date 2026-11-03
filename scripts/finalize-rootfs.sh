#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
ROOTFS=/build/rootfs
KERNEL_RELEASE=6.6.161-firefly
install -m 0755 /usr/bin/qemu-arm-static "$ROOTFS/usr/bin/qemu-arm-static"
if [[ ! -f /proc/sys/fs/binfmt_misc/register ]]; then
  mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
fi
REGISTERED=0
if [[ ! -f /proc/sys/fs/binfmt_misc/qemu-arm ]]; then
  update-binfmts --enable qemu-arm
  REGISTERED=1
fi
cleanup() {
  umount "$ROOTFS/proc" 2>/dev/null || true
  umount "$ROOTFS/sys" 2>/dev/null || true
  umount -R "$ROOTFS/dev" 2>/dev/null || true
  if [[ "$REGISTERED" == 1 ]]; then update-binfmts --disable qemu-arm || true; fi
}
trap cleanup EXIT
mount --rbind /dev "$ROOTFS/dev"
mount --make-rslave "$ROOTFS/dev"
mount -t proc proc "$ROOTFS/proc"
mount -t sysfs sysfs "$ROOTFS/sys"
rsync -a /build/kernel/staging/lib/modules/ "$ROOTFS/lib/modules/"
find "$ROOTFS/lib/modules" -maxdepth 2 -type l \( -name build -o -name source \) -delete
install -m 0644 /build/kernel/build/.config "$ROOTFS/boot/config-$KERNEL_RELEASE"
install -m 0644 /build/kernel/build/System.map "$ROOTFS/boot/System.map-$KERNEL_RELEASE"
install -m 0644 /build/kernel/build/arch/arm/boot/zImage "$ROOTFS/boot/vmlinuz-$KERNEL_RELEASE"
mkdir -p "$ROOTFS/etc/initramfs-tools/conf.d"
printf 'COMPRESS=gzip\nMODULES=most\n' > "$ROOTFS/etc/initramfs-tools/conf.d/firefly"
chroot "$ROOTFS" depmod -a "$KERNEL_RELEASE"
chroot "$ROOTFS" update-initramfs -c -k "$KERNEL_RELEASE"
chroot "$ROOTFS" apt-get check
DPKG_AUDIT=$(chroot "$ROOTFS" dpkg --audit)
if [[ -n "$DPKG_AUDIT" ]]; then printf '%s\n' "$DPKG_AUDIT" >&2; exit 1; fi
chroot "$ROOTFS" dpkg-query -W -f='${binary:Package}\t${Version}\t${Architecture}\n' > /build/packages.tsv
chroot "$ROOTFS" dpkg-query -W -f='${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n' > /build/source-packages.tsv
chroot "$ROOTFS" gnome-shell --version
chroot "$ROOTFS" /usr/libexec/gnome-initial-setup --help > /build/initial-setup-help.txt
chroot "$ROOTFS" /usr/bin/dpkg --print-architecture
# Ensure root is locked and no baked-in regular user exists.
chroot "$ROOTFS" passwd -l root
if awk -F: '$3 >= 1000 && $3 < 65534 { found=1 } END { exit !found }' "$ROOTFS/etc/passwd"; then
  echo 'Unexpected pre-created regular user' >&2; exit 1
fi
bash /build/scripts/configure-rootfs.sh
mkdir -p /build/boot-files/boot /build/boot-files/extlinux
cp "$ROOTFS/boot/vmlinuz-$KERNEL_RELEASE" /build/boot-files/boot/zImage
cp "$ROOTFS/boot/initrd.img-$KERNEL_RELEASE" /build/boot-files/boot/initrd.img
cp /build/kernel/build/arch/arm/boot/dts/rockchip/rk3288-firefly-ubuntu22.dtb /build/boot-files/boot/rk3288-firefly.dtb
cat > /build/boot-files/extlinux/extlinux.conf <<'EXTLINUX'
DEFAULT ubuntu
TIMEOUT 30

LABEL ubuntu
  MENU LABEL Ubuntu 22.04 GNOME - Firefly RK3288 - microSD
  LINUX /boot/zImage
  INITRD /boot/initrd.img
  FDT /boot/rk3288-firefly.dtb
  APPEND root=LABEL=FIREFLY_ROOT rootfstype=ext4 rw rootwait console=ttyS2,115200n8 console=tty1 loglevel=4
EXTLINUX
printf 'Ubuntu root filesystem finalized.\n'
