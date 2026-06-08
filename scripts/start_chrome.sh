#!/usr/bin/env bash
#
# start_chrome.sh — Ensure a debug-enabled Chrome is running for the LinkedIn tools.
#
# Default (recommended): launches a SEPARATE Chrome instance using a dedicated profile
#   (~/.chrome-linkedin-profile) with remote debugging on. This does NOT touch your everyday
#   Chrome — your normal tabs/windows stay open and untouched. The first time, you log into
#   LinkedIn once in the window it opens; after that the profile stays logged in.
#
# --main-profile: instead, QUITS your everyday Chrome and relaunches it with your real
#   profile + debugging (so you're already logged into LinkedIn). Closes your current tabs.
#
# Usage:
#   bash scripts/start_chrome.sh                 # dedicated profile (no tab loss)
#   bash scripts/start_chrome.sh --main-profile  # quit + relaunch your real Chrome
#   PORT=9333 bash scripts/start_chrome.sh        # custom debug port
#
set -euo pipefail

PORT="${PORT:-9222}"
PROFILE="${PROFILE:-$HOME/.chrome-linkedin-profile}"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FEED_URL="https://www.linkedin.com/feed/"
USE_MAIN=0

for arg in "$@"; do
  case "$arg" in
    --main-profile) USE_MAIN=1 ;;
    --port=*) PORT="${arg#*=}" ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# Already reachable? Nothing to do.
if curl -s "http://localhost:${PORT}/json/version" >/dev/null 2>&1; then
  echo "Debug Chrome already running on port ${PORT}."
  exit 0
fi

if [ ! -x "$CHROME" ]; then
  echo "ERROR: Chrome not found at: $CHROME" >&2
  echo "Edit CHROME path in scripts/start_chrome.sh if installed elsewhere." >&2
  exit 1
fi

ARGS=( --remote-debugging-port="$PORT" --no-first-run --no-default-browser-check )

if [ "$USE_MAIN" -eq 1 ]; then
  echo "Quitting your everyday Chrome (main-profile mode)…"
  osascript -e 'quit app "Google Chrome"' >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do
    pgrep -x "Google Chrome" >/dev/null 2>&1 || break
    sleep 0.5
  done
  if pgrep -x "Google Chrome" >/dev/null 2>&1; then
    echo "ERROR: Chrome did not quit. Close it manually and retry." >&2
    exit 1
  fi
else
  ARGS+=( --user-data-dir="$PROFILE" )
fi

echo "Launching debug Chrome on port ${PORT}…"
"$CHROME" "${ARGS[@]}" "$FEED_URL" >/dev/null 2>&1 &
disown || true

# Wait for the debug endpoint to come up.
for _ in $(seq 1 30); do
  if curl -s "http://localhost:${PORT}/json/version" >/dev/null 2>&1; then
    echo "Ready: debug Chrome on http://localhost:${PORT} (LinkedIn feed opening)."
    echo "If this is the first run with the dedicated profile, log into LinkedIn in that window."
    exit 0
  fi
  sleep 0.5
done

echo "ERROR: debug endpoint did not come up on port ${PORT} within ~15s." >&2
exit 1
