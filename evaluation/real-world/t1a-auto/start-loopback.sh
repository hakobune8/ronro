#!/usr/bin/env bash
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/ronro-runtime}"
export PULSE_SERVER="${PULSE_SERVER:-unix:${XDG_RUNTIME_DIR}/pulse/native}"
mkdir -p "$XDG_RUNTIME_DIR"

# Run a headed Chromium inside a private virtual display. Playwright's
# headless shell adds --mute-audio, which would make the PulseAudio loopback
# silent; Xvfb keeps the browser unattended without suppressing playback.
if [[ -z "${DISPLAY:-}" ]]; then
  export DISPLAY=:99
  Xvfb "$DISPLAY" -screen 0 1440x900x24 -ac -nolisten tcp >/tmp/ronro-t1a-xvfb.log 2>&1 &
  xvfb_pid=$!
  trap 'kill "$xvfb_pid" >/dev/null 2>&1 || true' EXIT
fi

if ! pactl info >/dev/null 2>&1; then
  pulseaudio --daemonize=yes --exit-idle-time=-1 --log-target=stderr
fi

for _ in $(seq 1 30); do
  if pactl info >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! pactl info >/dev/null 2>&1; then
  echo "PulseAudio did not become ready" >&2
  exit 1
fi

sink="${RONRO_AUDIO_SINK}"
description="${RONRO_AUDIO_SINK_DESCRIPTION}"
source="${RONRO_AUDIO_SOURCE:-${sink}_input}"
source_description="${RONRO_AUDIO_SOURCE_DESCRIPTION:-${description}_Input}"

if ! pactl list short sinks | awk '{print $2}' | grep -Fxq "$sink"; then
  pactl load-module module-null-sink \
    "sink_name=${sink}" \
    "sink_properties=device.description=${description}" >/dev/null
fi

if ! pactl list short sources | awk '{print $2}' | grep -Fxq "$source"; then
  pactl load-module module-remap-source \
    "source_name=${source}" \
    "master=${sink}.monitor" \
    "source_properties=device.description=${source_description}" >/dev/null
fi

pactl set-default-sink "$sink"
pactl set-default-source "$source"

mkdir -p "$(dirname "${T1A_AUTO_OUTPUT}")"
exec node /runner/runner.mjs "$@"
