#!/usr/bin/env bash
# Probe direct (non-github) source URLs used by p4a recipes.
set -u
URLS=(
  "https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.1.0.tar.gz"
  "https://www.openssl.org/source/openssl-3.3.1.tar.gz"
)
for u in "${URLS[@]}"; do
  printf "%-90s " "$u"
  curl -sSo /dev/null -w "http=%{http_code}\n" --max-time 15 -I "$u"
done
