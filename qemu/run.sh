#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
if [ "$#" -lt 1 ] || [ "$#" -gt 3 ]; then
    echo "Usage: $0 RELEASE_RAW_IMG [VM_STATE_DIR [VNC_DISPLAY_NUMBER]]" >&2
    exit 2
fi
model=$(dirname "$(realpath "$0")")
work=$(realpath "${FIREFLY_QEMU_WORK:-$model/work}")
raw=$(realpath "$1")
state=$(realpath -m "${2:-$work/vm}")
display=${3:-8}
ssh_port=${FIREFLY_QEMU_SSH_PORT:-}
network=${FIREFLY_QEMU_NETWORK:-isolated}
case "$network" in
    isolated|nat) ;;
    *) echo 'Set FIREFLY_QEMU_NETWORK to isolated or nat.' >&2; exit 2 ;;
esac
size=${FIREFLY_QEMU_SCREEN:-1024x768}
case "$ssh_port" in
    '') ;;
    *[!0-9]*|0*|??????*) echo 'Use a numeric SSH port (1024–65535).' >&2; exit 2 ;;
    *) [ "$ssh_port" -ge 1024 ] && [ "$ssh_port" -le 65535 ] || {
        echo 'Use a numeric SSH port (1024–65535).' >&2; exit 2;
    } ;;
esac
case "$size" in
    800x600|1024x768|1280x800) ;;
    *) echo 'Use an 800x600, 1024x768, or 1280x800 desktop.' >&2; exit 2 ;;
esac
case "$display" in ''|*[!0-9]*|0[0-9]*) echo 'Use a numeric VNC display (0–99).' >&2; exit 2 ;; esac
[ "$display" -le 99 ]
[ -f "$raw" ]
for path in qemu-build/qemu-system-arm qemu-build/qemu-img qemu-build/keymaps/en-us linux-build/arch/arm/boot/zImage firefly-rk3288.dtb; do
    [ -f "$work/$path" ] || { echo "Missing build file: $work/$path" >&2; exit 1; }
done
expected=918b1e8a98f7ae35d599941be0013b24d5019ae08aaf78946bdcfca91dee390d
if command -v openssl >/dev/null 2>&1; then
    digest=$(openssl dgst -sha256 -r < "$raw")
    digest=${digest%% *}
    [ "$digest" = "$expected" ] || { echo "SHA-256 mismatch: $raw" >&2; exit 1; }
    printf 'SHA-256 OK: %s\n' "$raw"
else
    printf '%s  %s\n' "$expected" "$raw" | sha256sum -c -
fi
(umask 077 && mkdir -p "$state")
name=firefly-rk3288-vnc-$display
port=$((5900 + display))
docker run --rm --detach --name "$name" --network host --user "$(id -u):$(id -g)" \
    --mount "type=bind,src=$raw,dst=/release/source.img,readonly" \
    --mount "type=bind,src=$work,dst=/qemu,readonly" \
    --mount "type=bind,src=$state,dst=/vm" \
    ${FIREFLY_QEMU_CPU_LIMIT:+--cpus="$FIREFLY_QEMU_CPU_LIMIT"} \
    ${FIREFLY_QEMU_RAM_LIMIT:+--memory="$FIREFLY_QEMU_RAM_LIMIT"} \
    "${FIREFLY_QEMU_IMAGE:-firefly-rk3288-qemu:10.2.0}" sh -ec '
        umask 077
        cd /vm
        if [ ! -e ubuntu.qcow2 ]; then
            /qemu/qemu-build/qemu-img create -f qcow2 -F raw -b /release/source.img ubuntu.qcow2
        fi
        display=$1; ssh_port=$2; size=$3; network=$4
        cmdline="console=tty0 console=ttyS0,115200n8 earlycon=uart8250,mmio32,0xff690000 root=PARTUUID=eab61153-02 rootwait rw systemd.mask=firefly-resize.service"
        set --
        if [ "$network" = nat ] || [ -n "$ssh_port" ]; then
            restrict=on
            [ "$network" != nat ] || restrict=off
            netdev="user,id=net,restrict=$restrict,ipv6=off"
            if [ -n "$ssh_port" ]; then
                cmdline="$cmdline systemd.wants=ssh.service"
                netdev="$netdev,hostfwd=tcp:127.0.0.1:$ssh_port-:22"
            fi
            set -- -netdev "$netdev" -device virtio-net-device,netdev=net
        fi
        exec /qemu/qemu-build/qemu-system-arm \
            -name "Firefly-RK3288 Ubuntu 22.04 GNOME" \
            -machine firefly-rk3288 -accel tcg,thread=multi,tb-size=512 -m 2G -smp 4 \
            -nodefaults -nic none -monitor none -display none \
            -L /qemu/qemu-build -vnc "127.0.0.1:$display" \
            -chardev socket,id=console,path=/vm/console.sock,server=on,wait=off,logfile=/vm/serial.log \
            -serial chardev:console -qmp unix:/vm/qmp.sock,server=on,wait=off \
            -kernel /qemu/linux-build/arch/arm/boot/zImage -dtb /qemu/firefly-rk3288.dtb \
            -append "$cmdline" \
            -drive if=none,id=ubuntu,file=/vm/ubuntu.qcow2,format=qcow2 \
            -device virtio-blk-device,drive=ubuntu -device "virtio-gpu-device,xres=${size%x*},yres=${size#*x}" \
            -device virtio-keyboard-device -device virtio-tablet-device \
            -object rng-random,id=rng,filename=/dev/urandom -device virtio-rng-device,rng=rng "$@" 2>/vm/qemu.log
    ' firefly "$display" "$ssh_port" "$size" "$network"
if [ "$(docker inspect --format '{{.State.Running}}' "$name" 2>/dev/null || true)" != true ]; then
    echo "QEMU failed to start; check $state/qemu.log" >&2
    exit 1
fi
printf 'VNC: 127.0.0.1:%s\nContainer: %s\nState: %s\n' "$port" "$name" "$state"
if [ -n "$ssh_port" ]; then
    printf 'SSH: 127.0.0.1:%s (after boot)\n' "$ssh_port"
fi
