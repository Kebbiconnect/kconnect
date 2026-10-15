#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../Kpn_android"
java -version
bash gradlew --no-daemon :app:testReleaseUnitTest :app:lintRelease
if [[ "${1:-}" == "release" ]]; then
  : "${KPN_KEYSTORE_FILE:?Set existing release keystore privately}"
  : "${KPN_KEYSTORE_PASSWORD:?Set keystore password privately}"
  : "${KPN_KEY_ALIAS:?Set existing key alias privately}"
  : "${KPN_HIGHEST_RELEASE_CODE:?Confirm highest published version code before release}"
  bash gradlew --no-daemon :app:assembleRelease
  bash ../scripts/verify-android-release.sh
else
  bash gradlew --no-daemon :app:assembleDebug
fi
