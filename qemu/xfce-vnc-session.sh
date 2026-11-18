#!/bin/sh
# SPDX-License-Identifier: MIT
# Launch in an SSH session with a local forward to the reported socket.
set -eu
: "${XDG_RUNTIME_DIR:?Use an SSH login with a systemd user session}"
for cmd in Xtigervnc xauth mcookie xset flock dbus-run-session xfconf-query xfce4-session; do
    command -v "$cmd" >/dev/null || { echo "Missing $cmd; install the desktop packages." >&2; exit 1; }
done
umask 077
state="$XDG_RUNTIME_DIR/firefly-vnc"
mkdir -p "$state"
exec 9>"$state/lock"
flock -n 9 || { echo 'The Xfce VNC session is already running.' >&2; exit 1; }
export DISPLAY=:9 XAUTHORITY="$state/Xauthority"
rm -f "$state/desktop.sock" "$XAUTHORITY"
touch "$XAUTHORITY"
xauth -q add "$DISPLAY" . "$(mcookie)"
Xtigervnc "$DISPLAY" -geometry 800x600 -depth 24 -nolisten tcp -auth "$XAUTHORITY" \
    -rfbport -1 -rfbunixpath "$state/desktop.sock" -rfbunixmode 0600 \
    -SecurityTypes None -AlwaysShared -FrameRate 20 -desktop 'Firefly RK3288 Xfce' &
xvnc=$!
trap 'kill "$xvnc" 2>/dev/null || true; wait "$xvnc" 2>/dev/null || true' 0
trap 'exit 1' HUP INT TERM
for attempt in $(seq 1 30); do
    kill -0 "$xvnc" 2>/dev/null || exit 1
    if xset q >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done
xset q >/dev/null
echo "VNC socket ready: $state/desktop.sock"
unset SESSION_MANAGER DBUS_SESSION_BUS_ADDRESS WAYLAND_DISPLAY
export XDG_SESSION_TYPE=x11 XDG_CURRENT_DESKTOP=XFCE XDG_SESSION_DESKTOP=xfce
# Avoid redrawing all windows for transparency/shadows on the emulated CPU.
# Store this preference only in this separate desktop session's config.
export XDG_CONFIG_HOME="$state/config"
dbus-run-session -- sh -ec '
    xfconf-query -c xfwm4 -p /general/use_compositing --create -t bool -s false
    exec xfce4-session
'
