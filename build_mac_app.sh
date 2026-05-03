#!/usr/bin/env bash
#
# Build a signed, notarised macOS .app bundle from eb_save_gui.py.
#
# Prerequisites:  see BUILDING.md
#
# Configurable via env vars:
#   SKIP_DMG        — if set, don't build a .dmg even if create-dmg is
#                     available.  Useful for fast iteration where you
#                     just want a working .app to smoke-test.
#   SKIP_DMG_NOTARY — if set, build + sign the .dmg but skip the second
#                     notarisation round-trip.  The .app inside is
#                     already stapled, so Gatekeeper still passes; you
#                     just lose the offline-friendly DMG ticket.
#   PYTHON          — path to the Python interpreter to bundle.  Default:
#                     `python3` from $PATH.  Anaconda's python3 has
#                     historically had flaky tkinter on macOS for
#                     PyInstaller bundling — if the build fails or the
#                     resulting .app crashes on launch, try
#                     PYTHON=/usr/bin/python3 (Apple's bundled Python,
#                     which ships tkinter) or a python.org universal2
#                     install.
#   IDENTITY        — codesigning identity.  Defaults to Stephen McLeod
#                     Blythe's Developer ID, since that's what's tied to
#                     this project.  If unset and not present in the
#                     keychain, the script falls back to the first
#                     "Developer ID Application:" identity it finds.
#   NOTARY_PROFILE  — name of the notarytool keychain profile.  Default:
#                     LOOPSAB_NOTARY (a profile name reused from another
#                     project on the maintainer's machine — already
#                     configured for the same Apple ID + team).
#                     Override with NOTARY_PROFILE=YourProfileName if
#                     you've set up your own.
#   APP_NAME        — the name shown in Finder.  Default: "Oh Mother".
#   BUNDLE_ID       — reverse-DNS bundle identifier.  Default:
#                     com.clickysteve.ohmother.

set -euo pipefail

APP_NAME="${APP_NAME:-Oh Mother}"
BUNDLE_ID="${BUNDLE_ID:-com.clickysteve.ohmother}"
DEFAULT_IDENTITY="Developer ID Application: Stephen McLeod Blythe (2N9AC8M66C)"
NOTARY_PROFILE="${NOTARY_PROFILE:-LOOPSAB_NOTARY}"
PYTHON="${PYTHON:-python3}"

cd "$(dirname "$0")"

# ---------------------------------------------------------------------
echo "==> Sanity-checking Python interpreter"
if ! command -v "${PYTHON}" >/dev/null 2>&1 && [[ ! -x "${PYTHON}" ]]; then
    echo "ERROR: PYTHON='${PYTHON}' not found or not executable."
    echo "       Set PYTHON=/path/to/python3 and try again."
    exit 1
fi
PY_VERSION=$("${PYTHON}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
PY_PREFIX=$("${PYTHON}" -c 'import sys; print(sys.prefix)')
echo "    using ${PYTHON} (Python ${PY_VERSION}, prefix ${PY_PREFIX})"

# Tkinter is required by the GUI; PyInstaller bundles whatever the
# build-time interpreter has, so confirm it's present before we waste
# time building.
if ! "${PYTHON}" -c 'import tkinter' >/dev/null 2>&1; then
    echo "ERROR: ${PYTHON} can't import tkinter — the resulting .app would"
    echo "       crash on launch.  Use a python.org installer or"
    echo "       'brew install python-tk@3.12' to get a Python with"
    echo "       working tkinter."
    exit 1
fi

# Apple's /usr/bin/python3 links against the deprecated system Tk 8.5,
# which produces a blank-window .app on modern macOS even though
# everything appears to import correctly.  Refuse to build with it.
TK_INFO=$("${PYTHON}" -c '
import tkinter
r = tkinter.Tk()
print(r.tk.call("info", "patchlevel"))
print(r.tk.call("tk", "windowingsystem"))
r.destroy()
' 2>/dev/null || echo "ERROR")
TK_VER=$(echo "${TK_INFO}" | sed -n '1p')
TK_WS=$(echo "${TK_INFO}"  | sed -n '2p')
echo "    tk: ${TK_VER:-unknown} (${TK_WS:-unknown})"
case "${TK_VER}" in
    8.5*)
        echo "ERROR: Tk ${TK_VER} is too old — this is Apple's deprecated"
        echo "       system Tk and the resulting .app will launch but"
        echo "       render an empty window.  Use a python.org installer"
        echo "       or 'brew install python-tk@3.12' instead.  Set PYTHON"
        echo "       to point at that interpreter and re-run."
        exit 1
        ;;
esac

# PyInstaller must live inside the same interpreter we're going to
# build with — otherwise it'll bundle from a different Python and
# import paths get tangled.
if ! "${PYTHON}" -c 'import PyInstaller' >/dev/null 2>&1; then
    echo "ERROR: PyInstaller is not installed in ${PYTHON}."
    echo
    echo "       Recommended (clean, brew-friendly): use a venv."
    echo "         ${PYTHON} -m venv _local/build-venv"
    echo "         _local/build-venv/bin/pip install pyinstaller"
    echo "         PYTHON=\$(pwd)/_local/build-venv/bin/python3 ./build_mac_app.sh"
    echo
    echo "       Quick alternative — bypass PEP 668 (works on brew Python):"
    echo "         ${PYTHON} -m pip install --user --break-system-packages pyinstaller"
    exit 1
fi

# ---------------------------------------------------------------------
echo "==> Cleaning previous build/ and dist/ folders"
rm -rf build dist *.spec
mkdir -p build dist

# ---------------------------------------------------------------------
echo "==> Picking signing identity"
if [[ -z "${IDENTITY:-}" ]]; then
    # First preference: the project's default identity, if it's installed.
    if security find-identity -v -p codesigning \
        | grep -F -q "${DEFAULT_IDENTITY}"; then
        IDENTITY="${DEFAULT_IDENTITY}"
    else
        # Fallback: first Developer ID Application identity in the keychain.
        IDENTITY=$(security find-identity -v -p codesigning \
            | awk -F'"' '/Developer ID Application:/ {print $2; exit}')
    fi
fi
if [[ -z "${IDENTITY}" ]]; then
    echo "ERROR: no Developer ID Application identity found in keychain."
    echo "       Set IDENTITY=... or import a Developer ID Application cert."
    echo "       See BUILDING.md."
    exit 1
fi
echo "    identity: ${IDENTITY}"

# ---------------------------------------------------------------------
echo "==> Building bundle with PyInstaller"

ICON_OPT=""
if [[ -f "AppIcon.icns" ]]; then
    ICON_OPT="--icon=AppIcon.icns"
    echo "    using AppIcon.icns"
else
    echo "    no AppIcon.icns found — using PyInstaller's default launcher icon"
fi

# --windowed       no console window
# --osx-bundle-id  proper bundle identifier
# --noconfirm      overwrite output without asking
# --clean          discard cached artefacts
"${PYTHON}" -m PyInstaller \
    --noconfirm --clean --windowed \
    --name "${APP_NAME}" \
    --osx-bundle-identifier "${BUNDLE_ID}" \
    ${ICON_OPT} \
    eb_save_gui.py

APP_PATH="dist/${APP_NAME}.app"
[[ -d "${APP_PATH}" ]] || { echo "ERROR: ${APP_PATH} did not appear"; exit 1; }
echo "    built ${APP_PATH}"

# ---------------------------------------------------------------------
# PyInstaller writes an Info.plist with CFBundleShortVersionString and
# CFBundleVersion both set to "0.0.0" (its default). That's what shows
# up in Finder Get Info / the About dialog.  Overwrite both with the
# version pulled from the source so the bundle, the DMG filename, and
# the in-app title bar are all in sync.
PLIST="${APP_PATH}/Contents/Info.plist"
if [[ -f "${PLIST}" ]]; then
    VERSION=$(awk -F'"' '/^__version__/ {print $2; exit}' eb_save_gui.py)
    if [[ -z "${VERSION}" ]]; then
        VERSION="dev"
    fi
    echo "==> Stamping Info.plist version: ${VERSION}"
    # PlistBuddy's `Set` errors out if the key doesn't exist, and
    # `Add` errors out if it does. PyInstaller writes
    # CFBundleShortVersionString but not CFBundleVersion, so we try
    # Add first (silently swallowing the "exists" error) and then Set
    # to the desired value.  `|| true` keeps `set -e` happy.
    /usr/libexec/PlistBuddy \
        -c "Add :CFBundleShortVersionString string ${VERSION}" \
        "${PLIST}" 2>/dev/null || true
    /usr/libexec/PlistBuddy \
        -c "Set :CFBundleShortVersionString ${VERSION}" \
        "${PLIST}"
    /usr/libexec/PlistBuddy \
        -c "Add :CFBundleVersion string ${VERSION}" \
        "${PLIST}" 2>/dev/null || true
    /usr/libexec/PlistBuddy \
        -c "Set :CFBundleVersion ${VERSION}" \
        "${PLIST}"
else
    echo "WARN: ${PLIST} not found — skipping version stamp"
fi

# ---------------------------------------------------------------------
echo "==> Code-signing every binary in the bundle"
codesign --force --deep --options runtime \
    --sign "${IDENTITY}" \
    --timestamp \
    "${APP_PATH}"

echo "    verifying signature..."
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

# ---------------------------------------------------------------------
echo "==> Zipping the bundle for notarisation"
ZIP_PATH="dist/${APP_NAME}.zip"
rm -f "${ZIP_PATH}"
ditto -c -k --keepParent "${APP_PATH}" "${ZIP_PATH}"
echo "    wrote ${ZIP_PATH}"

# ---------------------------------------------------------------------
echo "==> Submitting to Apple notary service (this can take a few minutes)"
xcrun notarytool submit "${ZIP_PATH}" \
    --keychain-profile "${NOTARY_PROFILE}" \
    --wait

# ---------------------------------------------------------------------
echo "==> Stapling the notarisation ticket to the bundle"
xcrun stapler staple "${APP_PATH}"
xcrun stapler validate "${APP_PATH}"

# ---------------------------------------------------------------------
# Build a distributable .dmg.
#
# Why DMG and not zip:  zipping a notarised .app then uploading and
# re-downloading via a browser sometimes mangles the staple or strips
# resource forks, producing the dreaded "Oh Mother.app is damaged and
# can't be opened" Gatekeeper error on the user's end.  DMGs preserve
# everything cleanly and are the conventional Mac distribution format.
DMG_PATH=""
if [[ -n "${SKIP_DMG:-}" ]]; then
    echo "==> SKIP_DMG set — not building .dmg"
elif ! command -v create-dmg >/dev/null 2>&1; then
    echo "==> create-dmg not installed — skipping .dmg step"
    echo "    install with:  brew install create-dmg"
else
    # Pull the version string straight out of the source so the .dmg
    # filename always matches what the app reports.
    VERSION=$(awk -F'"' '/^__version__/ {print $2; exit}' eb_save_gui.py)
    if [[ -z "${VERSION}" ]]; then
        VERSION="dev"
    fi
    DMG_NAME="${APP_NAME// /-}-v${VERSION}.dmg"
    DMG_PATH="dist/${DMG_NAME}"
    rm -f "${DMG_PATH}"

    echo "==> Building ${DMG_PATH} (drag-to-Applications layout)"
    # --no-internet-enable :  silence a deprecated-flag warning
    # The icon coords are tuned for the 600x400 window.
    create-dmg \
        --volname "${APP_NAME}" \
        --window-size 600 400 \
        --icon "${APP_NAME}.app" 175 200 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 425 200 \
        --no-internet-enable \
        "${DMG_PATH}" \
        "${APP_PATH}"

    echo "==> Code-signing ${DMG_PATH}"
    codesign --force --sign "${IDENTITY}" --timestamp "${DMG_PATH}"
    codesign --verify --verbose=2 "${DMG_PATH}"

    if [[ -n "${SKIP_DMG_NOTARY:-}" ]]; then
        echo "==> SKIP_DMG_NOTARY set — DMG is signed but unnotarised"
        echo "    (the .app inside is already notarised + stapled, so"
        echo "    Gatekeeper still passes when the user mounts it)"
    else
        echo "==> Notarising ${DMG_PATH} (a few more minutes)"
        xcrun notarytool submit "${DMG_PATH}" \
            --keychain-profile "${NOTARY_PROFILE}" \
            --wait
        echo "==> Stapling ticket to ${DMG_PATH}"
        xcrun stapler staple "${DMG_PATH}"
        xcrun stapler validate "${DMG_PATH}"
    fi
fi

# ---------------------------------------------------------------------
echo
echo "================================================================="
echo "  Done.  ${APP_PATH} is signed, notarised, and ready to ship."
if [[ -n "${DMG_PATH}" && -f "${DMG_PATH}" ]]; then
    echo "  Distributable:  ${DMG_PATH}"
fi
echo
echo "  Smoke-test it:"
echo "    open \"${APP_PATH}\""
if [[ -n "${DMG_PATH}" && -f "${DMG_PATH}" ]]; then
    echo "    open \"${DMG_PATH}\""
fi
echo
echo "  Upload the .dmg to a GitHub Release (or skip if SKIP_DMG was set"
echo "  and you'd rather hand-craft a zip — see BUILDING.md)."
echo "================================================================="
