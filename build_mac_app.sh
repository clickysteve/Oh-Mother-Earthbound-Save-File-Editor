#!/usr/bin/env bash
#
# Build a signed, notarised macOS .app bundle from eb_save_gui.py.
#
# Prerequisites:  see BUILDING.md
#
# Configurable via env vars:
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
#                     LOOPSAB_NOTARY (reused from the user's other
#                     project — already configured for smblythe@gmail.com
#                     / team 2N9AC8M66C).  Override if you've set up a
#                     project-specific profile.
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
echo
echo "================================================================="
echo "  Done.  ${APP_PATH} is signed, notarised, and ready to ship."
echo
echo "  Smoke-test it:"
echo "    open \"${APP_PATH}\""
echo
echo "  Repackage for distribution:"
echo "    ditto -c -k --keepParent \"${APP_PATH}\" \"${APP_NAME}-vX.Y.Z.zip\""
echo "================================================================="
