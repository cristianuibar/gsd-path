#!/usr/bin/env bash
# Uploads one platform's build to its GitHub release. Run from daemon/app by the App release workflow:
#   release-upload.sh <rust target> "<platform>=<ext> ..." <tag>
# It uploads the installers, then each signed update file under the fixed name
# updater-<platform>.<ext> that latest.json points to.
# Keep it to bash 3.2: that is the bash on macOS runners (no globstar, no mapfile).
set -euo pipefail
target="$1"
updates="$2"
tag="$3"
bundle="src-tauri/target/$target/release/bundle"

files=()
while IFS= read -r file; do files+=("$file"); done < <(
  find "$bundle" -type f \( -name '*.dmg' -o -name '*.msi' -o -name '*.deb' -o -name '*.AppImage' \))
if [[ ${#files[@]} -eq 0 ]]; then
  echo "the build made no installer" >&2
  exit 1
fi

# Check every update file before any upload, so a build that is not complete uploads nothing.
names=()
sources=()
for update in $updates; do
  platform="${update%%=*}"
  ext="${update#*=}"
  found=()
  while IFS= read -r file; do found+=("$file"); done < <(find "$bundle" -type f -name "*.$ext")
  if [[ ${#found[@]} -ne 1 || ! -f "${found[0]}.sig" ]]; then
    echo "expected one signed .$ext update file, found: ${found[*]:-none}" >&2
    exit 1
  fi
  names+=("updater-$platform.$ext")
  sources+=("${found[0]}")
done

gh release upload "$tag" "${files[@]}" --clobber
for index in "${!names[@]}"; do
  cp "${sources[$index]}" "${names[$index]}"
  cp "${sources[$index]}.sig" "${names[$index]}.sig"
  gh release upload "$tag" "${names[$index]}" "${names[$index]}.sig" --clobber
done
