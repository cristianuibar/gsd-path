#!/usr/bin/env bash
# Runs macos-signing-setup.sh with a stand-in for `security`, so no keychain changes.
# CI runs this on macOS, Windows (Git Bash), and Linux, like release-upload.test.sh.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failed=0
identity="Developer ID Application: Test Org (ABCDE12345)"

# A stand-in for security that records its arguments, one call per line.
mkdir "$work/bin"
cat > "$work/bin/security" <<'EOF'
#!/bin/sh
echo "$*" >> "$SECURITY_LOG"
case "$1" in
  find-identity) echo "  1) 0123456789ABCDEF \"$STUB_IDENTITY\"" ;;
  list-keychains) [ "$3" = "-s" ] || echo '    "/Users/test/Library/Keychains/login.keychain-db"' ;;
  import) cp "$2" "$SECURITY_LOG.imported" ;;
esac
EOF
chmod +x "$work/bin/security"

run() { # run <case dir> [NAME=value ...]; sets $status and $output
  local dir="$work/$1"; shift
  mkdir -p "$dir"; : > "$dir/github_env"
  ( env -u APPLE_CERTIFICATE -u APPLE_CERTIFICATE_PASSWORD -u APPLE_SIGNING_IDENTITY \
        -u APPLE_API_KEY -u APPLE_API_ISSUER -u APPLE_API_KEY_P8 \
        PATH="$work/bin:$PATH" SECURITY_LOG="$dir/security.log" GITHUB_ENV="$dir/github_env" \
        STUB_IDENTITY="${STUB_IDENTITY:-$identity}" "$@" bash "$here/macos-signing-setup.sh" "$dir" ) > "$dir/out.txt" 2>&1
  status=$?
  output="$(cat "$dir/out.txt")"
}
check() { # check <what> <condition is true: 0>
  if [ "$2" -eq 0 ]; then echo "ok   $1"; else echo "FAIL $1"; failed=1; fi
}
has() { grep -qF -- "$2" "$1" 2>/dev/null; }

certificate="$(printf 'not a real p12' | openssl base64 -A)"
all=(APPLE_CERTIFICATE="$certificate" APPLE_CERTIFICATE_PASSWORD=pw APPLE_SIGNING_IDENTITY="$identity"
     APPLE_API_KEY=KEYID12345 APPLE_API_ISSUER=issuer-uuid APPLE_API_KEY_P8="-----BEGIN PRIVATE KEY-----")

# No secrets (forks, local builds): the ad-hoc build goes on.
run none
check "no secrets: the script passes" "$status"
[ ! -s "$work/none/github_env" ] && [ ! -e "$work/none/security.log" ]; check "no secrets: no keychain and no signing variables" $?

# Some secrets: refuse, and name what is missing.
run partial APPLE_CERTIFICATE="$certificate" APPLE_SIGNING_IDENTITY="$identity"
[ "$status" -ne 0 ] && echo "$output" | grep -q "APPLE_API_KEY_P8"; check "some secrets: the script fails and names the missing ones" $?
[ ! -s "$work/partial/github_env" ] && [ ! -e "$work/partial/security.log" ]; check "some secrets: nothing is set up" $?

# All secrets: import the certificate, write the key, and export what Tauri reads.
run full "${all[@]}"
check "all secrets: the script passes" "$status"
[ "$(cat "$work/full/security.log.imported" 2>/dev/null)" = "not a real p12" ]; check "all secrets: the decoded certificate is imported" $?
has "$work/full/security.log" "-T /usr/bin/codesign"; check "all secrets: codesign may use the key" $?
has "$work/full/security.log" "list-keychains -d user -s $work/full/app-signing.keychain-db /Users/test/Library/Keychains/login.keychain-db"
check "all secrets: the new keychain is searched first, login stays" $?
[ ! -e "$work/full/certificate.p12" ]; check "all secrets: the certificate file is removed" $?
has "$work/full/github_env" "APPLE_SIGNING_IDENTITY=$identity"; check "all secrets: the identity is exported" $?
has "$work/full/github_env" "APPLE_API_KEY=KEYID12345" && has "$work/full/github_env" "APPLE_API_ISSUER=issuer-uuid"
check "all secrets: the notarization IDs are exported" $?
has "$work/full/github_env" "APPLE_API_KEY_PATH=$work/full/notarization-key.p8" \
  && [ "$(cat "$work/full/notarization-key.p8")" = "-----BEGIN PRIVATE KEY-----" ]
check "all secrets: the notarization key file holds the key" $?

# A certificate for another identity: refuse before the build.
STUB_IDENTITY="Developer ID Application: Someone Else (ZZZZZ99999)" run mismatch "${all[@]}"
[ "$status" -ne 0 ] && echo "$output" | grep -q "does not hold"; check "wrong certificate: the script fails and says so" $?
[ ! -s "$work/mismatch/github_env" ]; check "wrong certificate: no signing variables" $?

exit "$failed"
