#!/usr/bin/env bash
#
# Convert a source PNG into AppIcon.icns for the Mac .app bundle.
#
# Usage:
#   ./make_icon.sh path/to/source.png
#
# If no path is given, defaults to _local/icon-source.png so you can
# keep the high-resolution source out of the public repo.
#
# Notes:
#   - Source should be square. 512×512 or larger is best; 1024×1024 is
#     ideal. Smaller sources still work but Retina sizes will be
#     upscaled and look soft.
#   - Pixel art (like the EarthBound Sky Runner sprite) will look
#     better if you upscale it to 1024 with a nearest-neighbour filter
#     BEFORE running this script — otherwise the iconutil pipeline
#     will smooth it out and lose the chunky-pixel aesthetic.
#     Quick way to do that on macOS:
#       sips -z 1024 1024 --resampleHeightWidthMax 1024 \
#            -s formatOptions normal source.png \
#            --out source-1024.png
#     Or with ImageMagick (preserves pixels):
#       magick source.png -filter point -resize 1024x1024 source-1024.png

set -euo pipefail

cd "$(dirname "$0")"

SRC="${1:-_local/icon-source.png}"

if [[ ! -f "${SRC}" ]]; then
    echo "ERROR: source file not found: ${SRC}"
    echo
    echo "Drop your icon source PNG into the project (e.g. _local/icon-source.png)"
    echo "and run this script again."
    exit 1
fi

if ! command -v sips >/dev/null 2>&1; then
    echo "ERROR: sips not found. This script needs macOS."
    exit 1
fi

if ! command -v iconutil >/dev/null 2>&1; then
    echo "ERROR: iconutil not found. Install Xcode Command Line Tools:"
    echo "       xcode-select --install"
    exit 1
fi

ICONSET="AppIcon.iconset"
echo "==> Building ${ICONSET} from ${SRC}"
rm -rf "${ICONSET}"
mkdir "${ICONSET}"

# Apple's required sizes for a complete iconset.
sips -z 16   16   "${SRC}" --out "${ICONSET}/icon_16x16.png"     >/dev/null
sips -z 32   32   "${SRC}" --out "${ICONSET}/icon_16x16@2x.png"  >/dev/null
sips -z 32   32   "${SRC}" --out "${ICONSET}/icon_32x32.png"     >/dev/null
sips -z 64   64   "${SRC}" --out "${ICONSET}/icon_32x32@2x.png"  >/dev/null
sips -z 128  128  "${SRC}" --out "${ICONSET}/icon_128x128.png"   >/dev/null
sips -z 256  256  "${SRC}" --out "${ICONSET}/icon_128x128@2x.png">/dev/null
sips -z 256  256  "${SRC}" --out "${ICONSET}/icon_256x256.png"   >/dev/null
sips -z 512  512  "${SRC}" --out "${ICONSET}/icon_256x256@2x.png">/dev/null
sips -z 512  512  "${SRC}" --out "${ICONSET}/icon_512x512.png"   >/dev/null
sips -z 1024 1024 "${SRC}" --out "${ICONSET}/icon_512x512@2x.png">/dev/null

echo "==> Compiling AppIcon.icns"
iconutil -c icns "${ICONSET}"

# Tidy up the intermediate iconset folder; the .icns is all we need.
rm -rf "${ICONSET}"

echo
echo "Done. AppIcon.icns is in place — re-run ./build_mac_app.sh and"
echo "PyInstaller will pick it up automatically."
