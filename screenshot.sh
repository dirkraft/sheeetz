#!/bin/bash
# Usage: ./screenshot.sh [url] [output.png]
# Takes a screenshot of the sheeetz app at phone viewport size.
URL="${1:-http://serrverr.tail2ec075.ts.net:5173}"
OUTPUT="${2:-/tmp/sheeetz-screenshot.png}"

LD_LIBRARY_PATH=~/lib-chrome/extracted/usr/lib/x86_64-linux-gnu \
  ~/.cache/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell \
  --headless --no-sandbox --disable-gpu \
  --screenshot="$OUTPUT" \
  --window-size=390,844 \
  "$URL" 2>/dev/null

echo "$OUTPUT"
