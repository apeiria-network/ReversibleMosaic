#!/usr/bin/env bash
# Prefetch every source tarball that python-for-android needs for our current
# probe config, using ghfast.top as a mirror for GitHub URLs. Placed at
# ~/.buildozer/android/packages/<recipe>/<basename> plus a .mark-<basename>
# sentinel so p4a's download_if_necessary() skips the network entirely.
set -euo pipefail

PACKAGES_ROOT="${PACKAGES_ROOT:-$HOME/.p4a-source-cache}"
MIRROR="${MIRROR:-https://ghfast.top}"
CURL=(curl -fSL --retry 3 --retry-delay 3 --connect-timeout 20 --max-time 900)

# recipe|versioned_url (matches p4a Recipe.get_recipe order for our config)
RECIPES=(
  "hostpython3|https://github.com/python/cpython/archive/refs/tags/v3.14.2.tar.gz"
  "jpeg|https://github.com/libjpeg-turbo/libjpeg-turbo/archive/2.0.1.tar.gz"
  "libffi|https://github.com/libffi/libffi/archive/v3.4.2.tar.gz"
  "libwebp|https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.1.0.tar.gz"
  # openssl.org 301-redirects to github.com; go straight to the mirrored github URL
  # so the local file name still matches basename(recipe.versioned_url).
  "openssl|https://github.com/openssl/openssl/releases/download/openssl-3.3.1/openssl-3.3.1.tar.gz"
  "png|https://github.com/glennrp/libpng/archive/v1.6.37.zip"
  "sdl2_image|https://github.com/libsdl-org/SDL_image/releases/download/release-2.8.2/SDL2_image-2.8.2.tar.gz"
  "sdl2_mixer|https://github.com/libsdl-org/SDL_mixer/releases/download/release-2.6.3/SDL2_mixer-2.6.3.tar.gz"
  "sdl2_ttf|https://github.com/libsdl-org/SDL_ttf/releases/download/release-2.22.0/SDL2_ttf-2.22.0.tar.gz"
  "sqlite3|https://github.com/sqlite/sqlite/archive/refs/tags/version-3.50.4.tar.gz"
  "python3|https://github.com/python/cpython/archive/refs/tags/v3.14.2.tar.gz"
  "sdl2|https://github.com/libsdl-org/SDL/releases/download/release-2.30.11/SDL2-2.30.11.tar.gz"
  "libthorvg|https://github.com/thorvg/thorvg/archive/refs/tags/v1.0.5.tar.gz"
  "pyjnius|https://github.com/kivy/pyjnius/archive/1.7.0.zip"
  "kivy|https://github.com/kivy/kivy/archive/2.3.1.zip"
  # Stage 0 batch 1 additions (pyjnius/numpy/pillow). numpy is git+https and is
  # rewritten by GIT_CONFIG in wsl_build_android.sh; Pillow is a plain GitHub
  # tarball so must be prefetched through the mirror.
  "Pillow|https://github.com/python-pillow/Pillow/archive/11.3.0.tar.gz"
)

mirror_url() {
  local raw="$1"
  case "$raw" in
    https://github.com/*|https://raw.githubusercontent.com/*|https://codeload.github.com/*)
      echo "$MIRROR/$raw"
      ;;
    *)
      echo "$raw"
      ;;
  esac
}

for entry in "${RECIPES[@]}"; do
  name="${entry%%|*}"
  url="${entry#*|}"
  filename="$(basename "$url")"
  dest_dir="$PACKAGES_ROOT/$name"
  dest_file="$dest_dir/$filename"
  marker="$dest_dir/.mark-$filename"
  mkdir -p "$dest_dir"
  if [ -f "$dest_file" ] && [ -f "$marker" ]; then
    printf "[skip] %-14s %s (cached)\n" "$name" "$filename"
    continue
  fi
  fetch_url="$(mirror_url "$url")"
  printf "[get ] %-14s %s\n" "$name" "$fetch_url"
  rm -f "$dest_file" "$marker"
  "${CURL[@]}" -o "$dest_file.part" "$fetch_url"
  mv "$dest_file.part" "$dest_file"
  : > "$marker"
  size=$(stat -c '%s' "$dest_file")
  printf "[ok  ] %-14s %s (%d bytes)\n" "$name" "$filename" "$size"
done

echo
echo "Prefetch complete. Cache root: $PACKAGES_ROOT"
