#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ANDROID_HOME:?Set Android SDK path}"
: "${KPN_HIGHEST_RELEASE_CODE:?Confirm highest already published version code}"
[[ "$KPN_HIGHEST_RELEASE_CODE" =~ ^[0-9]+$ ]] || { echo 'Published version code must be an integer.' >&2; exit 1; }
apk="Kpn_android/app/build/outputs/apk/release/app-release.apk"
tools="$ANDROID_HOME/build-tools/35.0.0"
expected='eb66894d812f21b47f927ba052f00bfd47b4572daa9dfd63ec80805af61c0482'
actual="$("$tools/apksigner" verify --print-certs "$apk" | sed -n 's/^Signer #1 certificate SHA-256 digest: //p' | tr -d ': ' | tr '[:upper:]' '[:lower:]')"
[[ "$actual" == "$expected" ]] || { echo 'Signing certificate differs from the supplied production certificate. Release blocked.' >&2; exit 1; }
metadata="$("$tools/aapt" dump badging "$apk" | sed -n '1p')"
version="$(printf '%s' "$metadata" | sed -n "s/.*versionCode='\([0-9]*\)'.*/\1/p")"
[[ "$version" =~ ^[0-9]+$ && "$version" -gt "$KPN_HIGHEST_RELEASE_CODE" ]] || { echo 'Version code does not exceed the highest published release. Release blocked.' >&2; exit 1; }
printf '%s\n' "$metadata" | grep -q "name='com.kpn.mobile'" || { echo 'Unexpected application ID.' >&2; exit 1; }
"$tools/zipalign" -c -P 16 4 "$apk"
printf 'APK signature, existing certificate, package ID, version increment and alignment passed.\n'
