#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
TASK_ROOT=/build
ROOTFS="$TASK_ROOT/rootfs"
BASE="$TASK_ROOT/downloads/ubuntu-base-22.04.5-base-armhf.tar.gz"
if [[ ! -f "$ROOTFS/etc/os-release" ]]; then
  tar --numeric-owner --xattrs -xpf "$BASE" -C "$ROOTFS"
fi
install -m 0755 /usr/bin/qemu-arm-static "$ROOTFS/usr/bin/qemu-arm-static"
cp /etc/resolv.conf "$ROOTFS/etc/resolv.conf"
mkdir -p /proc/sys/fs/binfmt_misc
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
cat > "$ROOTFS/usr/sbin/policy-rc.d" <<'POLICY'
#!/bin/sh
exit 101
POLICY
chmod +x "$ROOTFS/usr/sbin/policy-rc.d"
cat > "$ROOTFS/etc/apt/sources.list" <<'SOURCES'
deb https://mirrors.ustc.edu.cn/ubuntu-ports/ jammy main restricted universe multiverse
deb https://mirrors.ustc.edu.cn/ubuntu-ports/ jammy-updates main restricted universe multiverse
deb https://mirrors.ustc.edu.cn/ubuntu-ports/ jammy-security main restricted universe multiverse
deb https://mirrors.ustc.edu.cn/ubuntu-ports/ jammy-backports main restricted universe multiverse
SOURCES
# Ubuntu's signed archive metadata authenticates packages from this mirror.
mkdir -p "$ROOTFS/etc/ssl/certs"
cp /etc/ssl/certs/ca-certificates.crt "$ROOTFS/etc/ssl/certs/ca-certificates.crt"
cat > "$ROOTFS/etc/apt/apt.conf.d/80firefly-build" <<'APTCONF'
Acquire::Retries "5";
Acquire::Languages "none";
Dpkg::Options { "--force-confdef"; "--force-confold"; };
APTCONF
chroot "$ROOTFS" /usr/bin/env DEBIAN_FRONTEND=noninteractive LC_ALL=C /bin/bash -eux <<'CHROOT'
dpkg --print-architecture
apt-get update
apt-get upgrade -y
apt-get install -y --no-install-recommends \
  ubuntu-minimal systemd-sysv systemd-timesyncd initramfs-tools \
  linux-firmware network-manager netplan.io wpasupplicant wireless-regdb \
  openssh-server sudo locales tzdata console-setup keyboard-configuration \
  ca-certificates curl wget less nano vim-tiny rsyslog logrotate \
  dbus dbus-user-session policykit-1 udev kmod \
  gdm3 gnome-initial-setup accountsservice gnome-session gnome-shell gnome-control-center gnome-terminal \
  nautilus gnome-system-monitor gnome-disk-utility gnome-keyring libpam-gnome-keyring dconf-cli seahorse \
  gedit evince file-roller network-manager-gnome \
  libgl1-mesa-dri mesa-utils xserver-xorg-core xserver-xorg-input-libinput \
  xserver-xorg-video-fbdev xwayland pulseaudio alsa-utils pavucontrol bluez \
  fonts-dejavu-core fonts-noto-core fonts-noto-cjk ibus-libpinyin \
  language-pack-zh-hans language-pack-gnome-zh-hans ubuntu-wallpapers-jammy \
  adwaita-icon-theme-full epiphany-browser gvfs-backends gvfs-fuse \
  dosfstools exfatprogs usbutils pciutils ethtool lsb-release man-db \
  bash-completion rfkill zram-tools cloud-guest-utils
locale-gen en_US.UTF-8 zh_CN.UTF-8
update-locale LANG=zh_CN.UTF-8
ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
echo Asia/Shanghai > /etc/timezone
dpkg-query -W -f='${binary:Package}\t${Version}\t${Architecture}\n' > /var/lib/firefly-packages.tsv
apt-get clean
CHROOT
rm -f "$ROOTFS/usr/sbin/policy-rc.d"
printf 'Root filesystem package installation completed.\n'
