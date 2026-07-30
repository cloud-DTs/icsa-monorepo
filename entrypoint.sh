#!/usr/bin/env bash
set -e
export DISPLAY="${DISPLAY:-:1}"
export WINEPREFIX="${WINEPREFIX:-/home/ea/.wine}"
export SCREEN_RESOLUTION="${SCREEN_RESOLUTION:-1600x900x24}"

# create virtual monitor
Xvfb "$DISPLAY" -screen 0 "$SCREEN_RESOLUTION" &
sleep 1

# manage screens inside virtual monitor
fluxbox &
sleep 1

# transfer the image from the virtual monitor
x11vnc \
  -display "$DISPLAY" \
  -listen 127.0.0.1 \
  -forever \
  -shared \
  -rfbport 5900 \
  -nopw &

# translates it to http (browser can not interract by vnc)
websockify \
  --web=/usr/share/novnc/ \
  6080 \
  localhost:5900 &

sleep 2

EA_EXE="$(find "$WINEPREFIX/drive_c" -iname "EA.exe" | head -n 1)"

if [ -z "$EA_EXE" ]; then
  echo "Enterprise Architect executable was not found."
  echo "Opening xterm for debugging..."
  exec xterm
fi

echo "Starting Enterprise Architect: $EA_EXE"
exec wine "$EA_EXE" "$@"
