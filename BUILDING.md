# Building a standalone Mac .app

This document walks through bundling `eb_save_gui.py` into a signed,
notarized macOS application that anyone can double-click to run — no
Python install required.

It uses **PyInstaller** because tkinter bundling on macOS is more
reliable there than with `py2app`. The output is a `.app` bundle of
roughly 30 MB.

## Quick start (if you're me)

If you're Stephen and your keychain already has the
`Developer ID Application: Stephen McLeod Blythe (2N9AC8M66C)`
identity plus the `LOOPSAB_NOTARY` notarytool profile (set up for the
Loop-Saboteur project), just:

```bash
# One-time: install a Python that ships with a modern Tk.
brew install python@3.12 python-tk@3.12
PY="$(brew --prefix python@3.12)/bin/python3.12"
"$PY" -m pip install pyinstaller

# Build:
PYTHON="$PY" ./build_mac_app.sh
```

Or, if you'd rather use the python.org universal2 installer, point
`PYTHON` at `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`
instead.

The script auto-detects the right identity and reuses the existing
notary profile. Skip to "Building" below.

### Why not use /usr/bin/python3 or Anaconda?

Two macOS Python pitfalls — both produce a `.app` that "works" until
you try to launch it:

- **`/usr/bin/python3`** (Apple's bundled Python) links against the
  deprecated system Tk 8.5, which causes the bundled `.app` to launch
  with a blank window — widgets get created but never paint. The
  build script refuses to use it.
- **Anaconda's `python3`** ships a broken or non-bundleable tkinter
  for PyInstaller — the build either fails outright or produces a
  `.app` that crashes on launch.

Stick to a python.org installer or Homebrew's `python@3.x` +
`python-tk@3.x`. The build script's preflight will check the Tk
version and refuse to build if it's stuck on 8.5.

For everyone else (or for a fresh machine), follow the prerequisites
and one-time setup below.

## Prerequisites

- macOS 11 or newer
- **Apple Developer account** (membership active, $99/yr) — needed for
  the *Developer ID Application* and *Developer ID Installer*
  certificates and for notarisation
- Xcode Command Line Tools:  `xcode-select --install`
- A working Python 3 with tkinter — Apple's bundled `python3` is fine,
  or any Homebrew / python.org install with tk
- App-specific Apple ID password for notarisation
  (https://account.apple.com/account/manage → App-Specific Passwords)

## One-time setup

### 1. Install a Python with a modern Tk

You need a Python that ships with **Tk 8.6 or newer**. The two
reliable options on macOS:

**python.org installer** (universal2):
download the latest 3.12.x macOS installer from
<https://www.python.org/downloads/macos/> and run it. The interpreter
lives at `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`.

**Homebrew:**

```bash
brew install python@3.12 python-tk@3.12
# Interpreter path:
"$(brew --prefix python@3.12)/bin/python3.12"
```

Verify Tk is at least 8.6:

```bash
"$YOUR_PYTHON" -c 'import tkinter; r = tkinter.Tk(); print(r.tk.call("info", "patchlevel"))'
# expected: 8.6.x or 9.x
```

If it prints 8.5.x you're on Apple's system Tk — bundled apps will
launch blank. Switch interpreter.

### 2. Install PyInstaller

PyInstaller has to be importable by the **same** Python interpreter
you'll build with, because it bundles itself from inside that Python.

Homebrew's Python 3.12 is "externally managed" (PEP 668), so plain
`pip install` will be refused. Pick one of these:

**Recommended — use a venv.** Clean, isolated, doesn't touch the brew
install, and `_local/` is already gitignored:

```bash
"$YOUR_PYTHON" -m venv _local/build-venv
_local/build-venv/bin/pip install pyinstaller
PYTHON="$(pwd)/_local/build-venv/bin/python3" ./build_mac_app.sh
```

**Or** override PEP 668 (quick, slightly grubby — installs into
`~/Library/Python/3.12/site-packages`):

```bash
"$YOUR_PYTHON" -m pip install --user --break-system-packages pyinstaller
PYTHON="$YOUR_PYTHON" ./build_mac_app.sh
```

For the python.org installer, plain `pip install pyinstaller` works
without any of this — it isn't subject to PEP 668.

**Avoid:**
- `/usr/bin/python3` — Apple's bundled Python uses Tk 8.5, which
  makes bundled apps launch with a blank window.
- Anaconda's `python3` — its tkinter often fails to bundle, and the
  resulting `.app` crashes on launch.

### 3. Save your signing identity once

Confirm your Developer ID Application certificate is in your keychain:

```bash
security find-identity -v -p codesigning
```

You should see something like:

```
1) ABCDEF1234567890ABCDEF1234567890ABCDEF12 "Developer ID Application: Steve Blythe (TEAMID12345)"
```

Note the **TEAMID12345** part — you'll need it.

### 4. Store your notarytool credentials in the keychain

So you only have to enter your password once:

```bash
xcrun notarytool store-credentials "OhMotherNotaryProfile" \
    --apple-id "you@example.com" \
    --team-id  "TEAMID12345" \
    --password "abcd-efgh-ijkl-mnop"     # app-specific password
```

By default `build_mac_app.sh` looks for a profile called
`LOOPSAB_NOTARY` (reused from another project on Stephen's machine).
Either:
- name your profile `LOOPSAB_NOTARY` to match, or
- name it whatever you like and run with
  `NOTARY_PROFILE=YourProfileName ./build_mac_app.sh`.

### 5. (Optional) Create an app icon

By default the bundle uses Python's generic launcher icon. To replace
it, save your source artwork (square, 1024×1024 PNG ideally) somewhere
in the project — `_local/icon-source.png` is the conventional spot,
since `_local/` is gitignored — then run:

```bash
./make_icon.sh             # uses _local/icon-source.png
# or:
./make_icon.sh path/to/source.png
```

That script produces `AppIcon.icns` next to `eb_save_gui.py`, and
`build_mac_app.sh` picks it up automatically on the next build.

For pixel art (e.g. the EarthBound Sky Runner sprite), upscale the
source to 1024×1024 with a nearest-neighbour filter first to keep the
chunky-pixel look — otherwise sips will smooth it. With ImageMagick:

```bash
magick source.png -filter point -resize 1024x1024 _local/icon-source.png
```

## Building

Run the included script:

```bash
./build_mac_app.sh
```

It will:

1. Clean any previous `build/` and `dist/` folders
2. Run PyInstaller in `--windowed` mode to produce `dist/Oh Mother.app`
3. Code-sign every binary in the bundle with your Developer ID
4. Zip the bundle and submit it to Apple's notary service
5. Wait for notarisation (usually 2-5 minutes) and report success/failure
6. Staple the notarisation ticket to the bundle so it works offline

When it finishes, `dist/Oh Mother.app` is ready to ship.

## Distribution

### Recommended — drag-to-install DMG (built automatically)

If you have `create-dmg` installed, `build_mac_app.sh` produces a
signed + notarised `.dmg` automatically. The version string comes from
`__version__` in `eb_save_gui.py`, so the filename always matches what
the app reports:

```bash
brew install create-dmg          # one-time
./build_mac_app.sh               # produces dist/Oh-Mother-v1.0.0.dmg
```

That's the file to upload to a GitHub Release. Users download, mount,
drag the app to Applications, eject. No Gatekeeper warnings because
both the `.app` and the `.dmg` are notarised + stapled.

If you want the .app and skip the DMG step (e.g. for fast iteration),
set `SKIP_DMG=1`. To build + sign the DMG but skip the second
notarisation round-trip (the inner `.app` stays notarised + stapled,
which is enough for Gatekeeper), set `SKIP_DMG_NOTARY=1`.

### Alternative — zip (only if you have a reason)

Zipping a notarised `.app` and uploading via a browser is fragile —
some zip tools strip resource forks, and the round-trip through a
browser's quarantine handling can produce the "Oh Mother.app is
damaged and can't be opened" Gatekeeper error on the receiver's
machine. If you must zip, use `ditto` with `--sequesterRsrc` so
metadata survives any extractor:

```bash
ditto -c -k --sequesterRsrc --keepParent \
    "dist/Oh Mother.app" "Oh-Mother-vX.Y.Z-mac.zip"
```

DMG remains the more reliable choice — recommend it.

### Option 3 — automate via GitHub Actions

A GitHub Actions workflow on `macos-latest` can:

1. Check out the repo
2. Set up Python
3. Decrypt your developer cert from a secret
4. Build, sign, and notarise on each tag push
5. Attach the resulting `.app.zip` and `.dmg` to a Release

Not included by default since it requires a one-time
secret-encryption setup that's specific to your CI account.

# Building a Windows .exe

There's a GitHub Actions workflow at `.github/workflows/release.yml`
that builds an unsigned Windows `.exe` on a `windows-latest` runner.
PyInstaller can't cross-compile, so this is the path of least
resistance if you don't have a Windows machine handy.

## Triggering a build

**Push a version tag** (the workflow attaches the resulting `.exe` to
a fresh GitHub Release with auto-generated notes):

```bash
git tag v1.0.0
git push --tags
```

**Or trigger it manually** from the Actions tab (Run workflow). The
`.exe` shows up as a downloadable workflow artifact called
`oh-mother-windows`.

## Icon

The workflow tries to produce `AppIcon.ico` automatically by looking
for an icon source PNG in this order:

1. `AppIcon.ico` already in the repo → use as-is
2. `icon-source.png` at the repo root
3. `assets/icon-source.png` or `assets/icon.png`

If none are found, the build still succeeds — the `.exe` just gets
PyInstaller's default icon. If you want the same UFO icon as on Mac,
copy `_local/icon-source.png` to the repo root (or `assets/`) and
commit it. Pillow handles the multi-resolution `.ico` packing
(16/32/48/64/128/256) and pads non-square sources so the UFO doesn't
end up squashed.

## What users will see on first launch

Because the `.exe` is unsigned, Windows SmartScreen will show
"Windows protected your PC". They have to click **More info → Run
anyway**. Worth mentioning in the release notes.

## Troubleshooting

### "Oh Mother.app is damaged and can't be opened"

The bundle wasn't notarised, or the staple step failed. Re-run
`xcrun stapler staple "dist/Oh Mother.app"` and check
`xcrun stapler validate "dist/Oh Mother.app"` returns "valid for use".

### "App is from an unidentified developer" warning

The `codesign` step failed or used the wrong identity. Run
`codesign -dvv "dist/Oh Mother.app"` and check the `Authority=` line.
It should say `Developer ID Application: ...`. If it says `ad-hoc` or
similar, your `IDENTITY` env var is wrong.

### The app launches and immediately quits

Run from Terminal to see the traceback:

```bash
"dist/Oh Mother.app/Contents/MacOS/Oh Mother"
```

Common causes:

- Missing tkinter — install Python with tk support before running PyInstaller
- Missing data files — the editor only reads/writes the user's `.srm`
  and `~/.eb_save_editor.json`, no extra data, so this shouldn't apply
- Permissions — first launch may show "X wants to access your Documents
  folder" — that's expected for an app that opens save files

### Build is huge (>100 MB)

PyInstaller bundles the whole Python interpreter + tkinter + all
imported modules. ~30 MB is normal. If it's much bigger, check for
accidental dependencies (numpy, PIL etc.) — this project should have
none. Run `pip list` in the build environment to verify.

## Universal binary (Intel + Apple Silicon)

To produce a universal2 bundle that runs natively on both architectures,
run the build on Apple Silicon with a Python that's also universal2:

```bash
# Use Python.org's universal2 installer, or:
arch -arm64 python3 -m pip install pyinstaller
arch -arm64 ./build_mac_app.sh
```

The output `.app` will run on both arches without Rosetta. PyInstaller
respects the host Python's architecture, so a single-arch Python →
single-arch .app.
