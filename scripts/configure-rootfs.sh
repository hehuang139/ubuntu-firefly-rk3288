#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
ROOTFS=/build/rootfs
rsync -a --chown=0:0 --chmod=D0755,F0644 /build/overlay/ "$ROOTFS/"
chmod 0755 "$ROOTFS/usr/local/sbin/firefly-resize"
chroot "$ROOTFS" /usr/bin/dconf update
echo firefly-ubuntu > "$ROOTFS/etc/hostname"
cat > "$ROOTFS/etc/hosts" <<'HOSTS'
127.0.0.1 localhost
127.0.1.1 firefly-ubuntu
::1 localhost ip6-localhost ip6-loopback
HOSTS
cat > "$ROOTFS/etc/fstab" <<'FSTAB'
LABEL=FIREFLY_ROOT / ext4 defaults,noatime 0 1
LABEL=FIREFLYBOOT /boot/firmware vfat defaults,noatime,umask=0077 0 2
FSTAB
install -d "$ROOTFS/boot/firmware" "$ROOTFS/etc/netplan"
cat > "$ROOTFS/etc/netplan/01-network-manager.yaml" <<'NETPLAN'
network:
  version: 2
  renderer: NetworkManager
NETPLAN
chmod 0600 "$ROOTFS/etc/netplan/01-network-manager.yaml"
# GDM starts GNOME Initial Setup while no regular user exists.
chroot "$ROOTFS" systemctl --root=/ enable firefly-resize.service NetworkManager.service systemd-timesyncd.service systemd-resolved.service
printf '%s\n' /usr/sbin/gdm3 > "$ROOTFS/etc/X11/default-display-manager"
ln -sfn /lib/systemd/system/gdm3.service "$ROOTFS/etc/systemd/system/display-manager.service"
chroot "$ROOTFS" systemctl --root=/ set-default graphical.target
chroot "$ROOTFS" systemctl --root=/ disable ssh.service ssh.socket 2>/dev/null || true
rm -f "$ROOTFS/etc/ssh/ssh_host_"*
# OpenSSH keys are generated on the first SSH start, not shared across images.
install -d "$ROOTFS/etc/systemd/system/ssh.service.d"
cat > "$ROOTFS/etc/systemd/system/ssh.service.d/10-host-keys.conf" <<'SSH'
[Service]
ExecStartPre=
ExecStartPre=/usr/bin/ssh-keygen -A
ExecStartPre=/usr/sbin/sshd -t
SSH
chroot "$ROOTFS" systemctl --root=/ enable serial-getty@ttyS2.service
# Build-only DNS config is replaced with the systemd-resolved managed link.
rm -f "$ROOTFS/etc/resolv.conf"
ln -s /run/systemd/resolve/stub-resolv.conf "$ROOTFS/etc/resolv.conf"
rm -f "$ROOTFS/etc/machine-id" "$ROOTFS/var/lib/dbus/machine-id"
touch "$ROOTFS/etc/machine-id"
ln -s /etc/machine-id "$ROOTFS/var/lib/dbus/machine-id"
# Do not ship build caches or a copied emulator.
rm -f "$ROOTFS/usr/bin/qemu-arm-static" "$ROOTFS/etc/apt/apt.conf.d/80firefly-build"
rm -rf "$ROOTFS/var/lib/apt/lists/"* "$ROOTFS/var/cache/apt/archives/"*.deb "$ROOTFS/var/cache/apt/archives/"*.prefetch
rm -f "$ROOTFS/root/.bash_history" "$ROOTFS/var/lib/systemd/random-seed"
find "$ROOTFS/var/log" -type f -exec truncate -s 0 {} +
