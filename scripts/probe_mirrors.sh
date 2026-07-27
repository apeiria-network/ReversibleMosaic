#!/usr/bin/env bash
set -u
HOSTS=(
  mirror.ghproxy.com
  ghfast.top
  ghproxy.link
  gh-proxy.com
  github.moeyy.xyz
)
for host in "${HOSTS[@]}"; do
  printf "%-25s " "$host"
  code=$(curl -sSo /dev/null -w "%{http_code}" --max-time 10 "https://${host}/" 2>&1)
  echo "http=$code"
done
