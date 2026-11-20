# CUE Audio Splitter (`cue-tui`)

A fast, standalone Terminal User Interface (TUI) built with Python and [Textual](https://textual.textualize.io/) for batch-splitting monolithic lossless audio files (`.flac`, `.wav`, `.ape`, `.wv`) into individual, tagged tracks using `.cue` sheets.

- **Repository:** [https://github.com/JevgeniPillau/cue-tui](https://github.com/JevgeniPillau/cue-tui)
- **Author:** Jevgeni Pillau ([@JevgeniPillau](https://github.com/JevgeniPillau))
- **Target OS:** Void Linux (`x86_64`)
- **Current Version:** `1.0.1` (`revision 2`)

---

## Program Purpose

Lossless album archives often arrive as a single large audio file paired with a `.cue` sheet (frequently encoded in legacy Windows-1251/Cyrillic or other non-UTF-8 charsets). `cue-tui` replaces command-line scripting with an interactive terminal dashboard that lets you browse your music library, preview parsed track titles and timestamps before touching any files, and split entire directory trees cleanly with FFmpeg.

---

## Key Features

- **Interactive Library Browser:** Opens directly into `~/Music` (falling back to `~`), hiding dotfiles while displaying folders alongside `.cue`, `.flac`, `.wav`, and `.ape` files.
- **Automatic Encoding Detection:** Uses `chardet` to detect legacy `.cue` encodings (such as CP1251) and convert track titles cleanly to UTF-8.
- **Live Track Preview Table:** Clicking any `.cue` sheet immediately populates a preview table with track numbers, parsed track titles, and `INDEX 01` start timestamps.
- **Zero-Dependency CUE Parsing & Frame-Accurate Splitting:** Parses `FILE` directives and `INDEX 01` timestamps directly in Python (converting 75 fps CD frames to exact `HH:MM:SS.mmm` FFmpeg timestamps) and copies audio streams losslessly (`-c copy`) with embedded `title` and `track` metadata tags.
- **Non-Blocking Background Execution:** Runs batch splitting in a background worker thread with a live progress bar and scrolling execution report.
- **Safe Source Cleanup:** Optional post-split confirmation modal lists the exact original archive files before permanently deleting them.
- **Persistent Theme Selection:** Automatically saves your chosen Textual theme (`Ctrl+P`) to `~/.config/cue-tui/config.json` and restores it across restarts—even in compiled standalone binaries.
- **Desktop Menu Integration:** Ships with a freedesktop `.desktop` entry so **CUE Audio Splitter** launches directly from your desktop application menu.

---

## Keyboard Shortcuts

| Key | Action |
| :--- | :--- |
| `Ctrl+R` | Start batch splitting the selected directory |
| `Ctrl+L` | Clear the execution log |
| `Ctrl+P` | Open the Textual Command Palette (switch themes, toggle key panel) |
| `Esc` | Close the docked Key Panel |
| `Ctrl+Q` | Quit the application |

---

## Summary of What We Built & Solved

1. **Refactored CLI Script into a Textual TUI:** Replaced blocking `print()` and `input()` calls with a responsive two-pane Textual layout (`DirectoryTree` on the left; path input, checkbox, `DataTable` preview, `ProgressBar`, and `RichLog` on the right).
2. **Eliminated External `cuetools` Dependency:** Replaced `cuebreakpoints` subprocess calls with native Python parsing of `FILE "..."` directives and `INDEX 01` timestamps, fixing 1:1 track alignment on albums with pre-gaps.
3. **Fixed 60+ Minute Timestamp Overflow:** Converted `MM:SS:FF` timestamps into `HH:MM:SS.mmm` format (`divmod(total_mins, 60)`) so FFmpeg cleanly splits long albums and classical symphonies exceeding 59 minutes.
4. **Hardened Error Handling & File Matching:** Added case-insensitive extension matching, CUE `FILE` directive resolution, empty-title fallbacks, and FFmpeg return-code verification before allowing source deletion.
5. **Solved Frozen Binary Theme Persistence:** Deferred theme loading via `call_after_refresh()` with a `_theme_loaded` guard so PyInstaller builds do not overwrite `~/.config/cue-tui/config.json` during startup.
6. **Packaged for Void Linux (`xbps`):** Compiled a standalone executable with PyInstaller inside a dedicated `venv` (respecting PEP 668) and built a native `.xbps` package with `xbps-src` (`nostrip=yes`) complete with `/usr/share/applications/cue-tui.desktop`.

---

## Automated Build & Package Script (`build.sh`)

Save this script as `~/build.sh` (`chmod +x ~/build.sh`) to automate recompiling the PyInstaller binary and rebuilding/installing the Void Linux `.xbps` package whenever you update the source code:

```bash
#!/usr/bin/env bash
set -euo pipefail

VERSION="1.0.1"
REVISION="2"
SCRIPT_PATH="$HOME/cuesplitter_core_tui-${VERSION}.py"
VENV_DIR="$HOME/.cue-venv"
BUILD_DIR="$HOME/cuesplitter-build"
VOID_PKGS="$HOME/void-packages"
PKG_DIR="$VOID_PKGS/srcpkgs/cue-tui"

echo "==> 1. Compiling standalone binary with PyInstaller..."
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
"$VENV_DIR/bin/pyinstaller" --onefile --clean --name cue-tui "$SCRIPT_PATH"

echo "==> 2. Staging binary and .desktop entry into void-packages..."
mkdir -p "$PKG_DIR/files"
cp "$BUILD_DIR/dist/cue-tui" "$PKG_DIR/files/cue-tui"

cat << 'EOF' > "$PKG_DIR/files/cue-tui.desktop"
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

cat << EOF > "$PKG_DIR/template"
# Template file for 'cue-tui'
pkgname=cue-tui
version=${VERSION}
revision=${REVISION}
archs="x86_64"
depends="ffmpeg"
short_desc="Terminal UI for splitting monolithic audio files using CUE sheets"
maintainer="Jevgeni Pillau <JevgeniPillau@users.noreply.github.com>"
license="MIT"
homepage="https://github.com/JevgeniPillau/cue-tui"
nostrip=yes

do_install() {
    vbin "\${FILESDIR}/cue-tui"
    vinstall "\${FILESDIR}/cue-tui.desktop" 644 usr/share/applications
}
EOF

echo "==> 3. Building and installing XBPS package..."
cd "$VOID_PKGS"
./xbps-src pkg cue-tui
sudo xbps-install --repository=hostdir/binpkgs -f cue-tui

echo "==> Done! cue-tui ${VERSION}_${REVISION} is built and installed."
```

---

## Installation & Usage

### From Prebuilt Local XBPS Repository
```bash
sudo xbps-install --repository=~/void-packages/hostdir/binpkgs cue-tui
```

### Running from Source (Development)
```bash
python3 -m venv ~/.cue-venv
~/.cue-venv/bin/pip install textual chardet
~/.cue-venv/bin/python ~/cuesplitter_core_tui-1.0.1.py
```

### Installed Paths

| Path | Description |
| :--- | :--- |
| `/usr/bin/cue-tui` | Standalone compiled executable |
| `/usr/share/applications/cue-tui.desktop` | Desktop application menu launcher |
| `~/.config/cue-tui/config.json` | Saved UI theme configuration |

---

## License

MIT License

Copyright (c) 2026 Jevgeni Pillau

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
