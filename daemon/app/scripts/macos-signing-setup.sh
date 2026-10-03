#!/usr/bin/env bash
# Sets up Developer ID signing and notarization for one macOS app build in CI.
#   macos-signing-setup.sh <work dir>
# Reads the APPLE_* repository secrets from the environment:
# - none set: prints a note and exits 0; the build keeps its ad-hoc signature.
# - some set: fails, so a half-configured repository never ships a build that
#   looks signed but is not notarized.
# - all set: imports the certificate into a new keychain, writes the
#   notarization key to <work dir>, and appends the variables Tauri reads to
#   $GITHUB_ENV.
# Keep it to bash 3.2: that is the bash on macOS runners.
set -eu
work="$1"
names="APPLE_CERTIFICATE APPLE_CERTIFICATE_PASSWORD APPLE_SIGNING_IDENTITY APPLE_API_KEY APPLE_API_ISSUER APPLE_API_KEY_P8"
missing=""
set_count=0
for name in $names; do
  if [ -n "$(printenv "$name" || true)" ]; then set_count=$((set_count + 1)); else missing="$missing $name"; fi
done
if [ "$set_count" -eq 0 ]; then
  echo "No Apple signing secrets: building with an ad-hoc signature."
  exit 0
fi
if [ -n "$missing" ]; then
  echo "Apple signing secrets missing:$missing" >&2
  exit 1
fi

keychain="$work/app-signing.keychain-db"
certificate="$work/certificate.p12"
# On a failure, delete the keychain here: the workflow cleanup step only knows
# the keychain after APP_SIGNING_KEYCHAIN is exported.
trap 'status=$?; rm -f "$certificate"; [ "$status" -eq 0 ] || security delete-keychain "$keychain" 2> /dev/null || true' EXIT
password="$(openssl rand -hex 24)"
printf '%s' "$APPLE_CERTIFICATE" | openssl base64 -d -A > "$certificate"
security create-keychain -p "$password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$password" "$keychain"
security import "$certificate" -k "$keychain" -P "$APPLE_CERTIFICATE_PASSWORD" -T /usr/bin/codesign
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$password" "$keychain" > /dev/null
# Search the new keychain first and keep the existing ones.
existing="$(security list-keychains -d user | tr -d '"')"
# shellcheck disable=SC2086  # one keychain path per word; runner paths have no spaces
security list-keychains -d user -s "$keychain" $existing
if ! security find-identity -v -p codesigning "$keychain" | grep -qF "\"$APPLE_SIGNING_IDENTITY\""; then
  echo "the certificate does not hold the identity $APPLE_SIGNING_IDENTITY" >&2
  exit 1
fi
printf '%s' "$APPLE_API_KEY_P8" > "$work/notarization-key.p8"
{
  echo "APPLE_SIGNING_IDENTITY=$APPLE_SIGNING_IDENTITY"
  echo "APPLE_API_KEY=$APPLE_API_KEY"
  echo "APPLE_API_ISSUER=$APPLE_API_ISSUER"
  echo "APPLE_API_KEY_PATH=$work/notarization-key.p8"
  echo "APP_SIGNING_KEYCHAIN=$keychain"
} >> "$GITHUB_ENV"
