#!/usr/bin/env bash
set -euo pipefail

# Configuration
APP_NAME="cue-tui"
VERSION="1.0.1"
REVISION="2"
SCRIPT_PATH="${1:-$HOME/cuesplitter_core_tui-1.0.1.py}"
VENV_DIR="$HOME/.cue-venv"
BUILD_DIR="$HOME/cuesplitter-build"
VOID_PKGS="$HOME/void-packages"
PKG_SRC_DIR="$VOID_PKGS/srcpkgs/$APP_NAME"

echo "==> Checking source script at: $SCRIPT_PATH"
if [[ ! -f "$SCRIPT_PATH" ]]; then
    echo "Error: Python source file not found at $SCRIPT_PATH"
    echo "Usage: ./build.sh [/path/to/cuesplitter_core_tui.py]"
    exit 1
fi

echo "==> Checking virtual environment at: $VENV_DIR"
if [[ ! -x "$VENV_DIR/bin/pyinstaller" ]]; then
    echo "PyInstaller not found in $VENV_DIR. Installing dependencies..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip textual chardet pyinstaller
fi

echo "==> Compiling standalone binary with PyInstaller..."
mkdir -p "$BUILD_DIR"
"$VENV_DIR/bin/pyinstaller" --onefile --clean \
    --name "$APP_NAME" \
    --distpath "$BUILD_DIR/dist" \
    --workpath "$BUILD_DIR/build" \
    --specpath "$BUILD_DIR" \
    "$SCRIPT_PATH"

echo "==> Preparing Void Linux xbps-src template..."
mkdir -p "$PKG_SRC_DIR/files"
cp "$BUILD_DIR/dist/$APP_NAME" "$PKG_SRC_DIR/files/$APP_NAME"
chmod 755 "$PKG_SRC_DIR/files/$APP_NAME"

cat << 'EOF' > "$PKG_SRC_DIR/files/$APP_NAME.desktop"
[Desktop Entry]
Name=CUE Audio Splitter
GenericName=CUE Sheet Audio Splitter
Comment=Split monolithic FLAC/WAV/APE files using CUE sheets
Exec=cue-tui
Icon=audio-x-generic
Terminal=true
Type=Application
Categories=AudioVideo;Audio;Utility;
Keywords=cue;flac;ape;wav;splitter;audio;
EOF

cat << EOF > "$PKG_SRC_DIR/template"
# Template file for '$APP_NAME'
pkgname=$APP_NAME
version=$VERSION
revision=$REVISION
archs="x86_64"
depends="ffmpeg"
short_desc="Terminal UI for splitting monolithic audio files using CUE sheets"
maintainer="JevgeniPillau <JevgeniPillau@users.noreply.github.com>"
license="MIT"
homepage="https://github.com/JevgeniPillau/cue-tui"
nostrip=yes

do_install() {
    vbin "\${FILESDIR}/$APP_NAME"
    vinstall "\${FILESDIR}/$APP_NAME.desktop" 644 usr/share/applications
}
EOF

echo "==> Building .xbps package via xbps-src..."
cd "$VOID_PKGS"
./xbps-src pkg "$APP_NAME"

echo "==> Installing $APP_NAME via xbps-install..."
sudo xbps-install --repository=hostdir/binpkgs -f "$APP_NAME"

echo "==> Done! Launch '$APP_NAME' from your terminal or application menu."
