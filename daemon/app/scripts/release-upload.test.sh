#!/usr/bin/env bash
# Runs release-upload.sh against test build trees with a stand-in for `gh`.
# CI runs this on macOS, Windows (Git Bash), and Linux: the shells the App release workflow uses.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failed=0

# A stand-in for gh that records its arguments, one call per line.
mkdir "$work/bin"
printf '#!/bin/sh\necho "$*" >> "$GH_LOG"\n' > "$work/bin/gh"
chmod +x "$work/bin/gh"

run() { # run <case dir> <target> <updates>; sets $status and $output
  ( cd "$1" && GH_LOG="$1/gh.log" PATH="$work/bin:$PATH" bash "$here/release-upload.sh" "$2" "$3" app-v9.9.9 ) > "$1/out.txt" 2>&1
  status=$?
  output="$(cat "$1/out.txt")"
}
tree() { # tree <name> <target> <files...>: makes a build tree and prints its directory
  local dir="$work/$1" target="$2"; shift 2
  local bundle="$dir/src-tauri/target/$target/release/bundle"
  mkdir -p "$bundle"
  for file in "$@"; do mkdir -p "$bundle/$(dirname "$file")"; echo data > "$bundle/$file"; done
  echo "$dir"
}
check() { # check <what> <condition is true: 0>
  if [ "$2" -eq 0 ]; then echo "ok   $1"; else echo "FAIL $1"; failed=1; fi
}
has() { grep -qF -- "$2" "$1" 2>/dev/null; }

# macOS: one installer, one signed update file. The app name has a space.
dir="$(tree mac aarch64-apple-darwin "dmg/OpenGSD Path_9.9.9_aarch64.dmg" "macos/OpenGSD Path.app.tar.gz" "macos/OpenGSD Path.app.tar.gz.sig")"
run "$dir" aarch64-apple-darwin "darwin-aarch64=app.tar.gz"
check "macOS: the script passes" "$status"
has "$dir/gh.log" "OpenGSD Path_9.9.9_aarch64.dmg --clobber"; check "macOS: the .dmg is uploaded to the tag" $?
has "$dir/gh.log" "release upload app-v9.9.9 updater-darwin-aarch64.app.tar.gz updater-darwin-aarch64.app.tar.gz.sig --clobber"; check "macOS: the update file and its signature are uploaded under the fixed name" $?
[ "$(wc -l < "$dir/gh.log" | tr -d ' ')" = "2" ]; check "macOS: exactly two uploads" $?

# Linux: two installers and two update files.
dir="$(tree linux x86_64-unknown-linux-gnu "deb/OpenGSD Path_9.9.9_amd64.deb" "deb/OpenGSD Path_9.9.9_amd64.deb.sig" "appimage/OpenGSD Path_9.9.9_amd64.AppImage" "appimage/OpenGSD Path_9.9.9_amd64.AppImage.sig")"
run "$dir" x86_64-unknown-linux-gnu "linux-x86_64=AppImage linux-x86_64-deb=deb"
check "Linux: the script passes" "$status"
has "$dir/gh.log" "updater-linux-x86_64.AppImage updater-linux-x86_64.AppImage.sig"; check "Linux: the AppImage update is uploaded" $?
has "$dir/gh.log" "updater-linux-x86_64-deb.deb updater-linux-x86_64-deb.deb.sig"; check "Linux: the .deb update is uploaded" $?
has "$dir/gh.log" "_amd64.deb" && has "$dir/gh.log" "_amd64.AppImage"; check "Linux: both installers are uploaded" $?

# Windows: one .msi is both the installer and the update file.
dir="$(tree win x86_64-pc-windows-msvc "msi/OpenGSD Path_9.9.9_x64_en-US.msi" "msi/OpenGSD Path_9.9.9_x64_en-US.msi.sig")"
run "$dir" x86_64-pc-windows-msvc "windows-x86_64=msi"
check "Windows: the script passes" "$status"
has "$dir/gh.log" "updater-windows-x86_64.msi updater-windows-x86_64.msi.sig"; check "Windows: the .msi update is uploaded" $?

# Refusals: nothing may be uploaded as an update when the build is not complete.
dir="$(tree empty x86_64-pc-windows-msvc)"
run "$dir" x86_64-pc-windows-msvc "windows-x86_64=msi"
[ "$status" -ne 0 ] && echo "$output" | grep -q "the build made no installer"; check "no installer: the script fails and says so" $?
[ ! -e "$dir/gh.log" ]; check "no installer: nothing is uploaded" $?

dir="$(tree nosig aarch64-apple-darwin "dmg/a.dmg" "macos/OpenGSD Path.app.tar.gz")"
run "$dir" aarch64-apple-darwin "darwin-aarch64=app.tar.gz"
[ "$status" -ne 0 ] && echo "$output" | grep -q "expected one signed .app.tar.gz update file"; check "missing signature: the script fails and says so" $?
[ ! -e "$dir/gh.log" ]; check "missing signature: nothing is uploaded" $?

dir="$(tree two x86_64-pc-windows-msvc "msi/a.msi" "msi/a.msi.sig" "msi/b.msi" "msi/b.msi.sig")"
run "$dir" x86_64-pc-windows-msvc "windows-x86_64=msi"
[ "$status" -ne 0 ] && echo "$output" | grep -q "expected one signed .msi update file"; check "two update files: the script fails and says so" $?
[ ! -e "$dir/gh.log" ]; check "two update files: nothing is uploaded" $?

exit "$failed"
