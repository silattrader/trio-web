#!/usr/bin/env bash
# Reproducible build of docs/demo.mp4 from a running app at localhost:3000.
#
# Pre-reqs (one-time):
#   npm install --save-dev playwright ffmpeg-static
#   npx playwright install chromium
#
# Run with the API + web both up:
#   make run                                  # in one terminal
#   cd apps/web && npm run dev                # in another
#   bash scripts/build_demo_mp4.sh            # in a third
#
# Output:
#   docs/demo.mp4    — final 1280x720 captioned MP4 (~2 MB, ~53 s)
#
# Override the URL with TRIO_DEMO_URL env when pointing at a deployed
# instance instead of localhost.

set -euo pipefail

cd "$(dirname "$0")/.."

# 1. Record a raw webm via Playwright.
echo "==> Recording webm via Playwright..."
node scripts/record_demo.js

# 2. Find the recorded file (Playwright names it with a hash).
WEBM=$(ls -t docs/demo_raw/*.webm | head -1)
if [[ -z "${WEBM}" ]]; then
  echo "ERROR: no webm produced by Playwright" >&2
  exit 1
fi
echo "    raw: $WEBM"

# 3. Locate ffmpeg-static (npm puts it in node_modules/.bin/path/ffmpeg.exe).
FFMPEG=$(node -e "console.log(require('ffmpeg-static'))")
if [[ ! -x "$FFMPEG" ]]; then
  echo "ERROR: ffmpeg-static not found. Run: npm install --save-dev ffmpeg-static" >&2
  exit 1
fi
echo "    ffmpeg: $FFMPEG"

# 4. Copy the SRT next to the webm so the subtitles= filter sees a relative path.
cp scripts/demo_captions.srt docs/demo_raw/demo.srt

# 5. Encode to MP4 with burned-in captions.
echo "==> Encoding mp4 with captions..."
pushd docs/demo_raw > /dev/null
"$FFMPEG" -y -hide_banner -loglevel error \
  -i "$(basename "$WEBM")" \
  -vf "subtitles=demo.srt:force_style='FontName=Calibri,FontSize=20,PrimaryColour=&H00FFFFFF&,OutlineColour=&H80000000&,BorderStyle=4,Outline=2,Shadow=0,MarginV=40,Alignment=2'" \
  -c:v libx264 -pix_fmt yuv420p -preset slow -crf 23 \
  -movflags +faststart \
  -an \
  ../demo.mp4
popd > /dev/null

# 6. Clean up intermediate files.
rm -rf docs/demo_raw

echo "==> Done. docs/demo.mp4"
ls -la docs/demo.mp4
