#!/usr/bin/env bash
# Try various GitHub mirrors that (may) support git clone through HTTPS.
set -u

MIRRORS=(
  "https://ghfast.top/https://github.com"
  "https://kkgithub.com"
  "https://hub.gitmirror.com/https://github.com"
  "https://bgithub.xyz"
  "https://gitclone.com/github.com"
)

cd /tmp

for mirror in "${MIRRORS[@]}"; do
  rm -rf gh-clone-test 2>/dev/null
  printf "%-60s " "$mirror"
  if timeout 30 git clone --depth 1 -b v9e-SDL "$mirror/libsdl-org/jpeg.git" gh-clone-test >/tmp/clone.log 2>&1; then
    files=$(ls gh-clone-test 2>/dev/null | wc -l)
    echo "OK ($files entries)"
  else
    tail -1 /tmp/clone.log
  fi
done

rm -rf /tmp/gh-clone-test /tmp/clone.log 2>/dev/null
