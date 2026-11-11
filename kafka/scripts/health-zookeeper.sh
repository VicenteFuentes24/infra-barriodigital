#!/usr/bin/env bash
set -euo pipefail
exec 3<>/dev/tcp/127.0.0.1/2181
printf 'srvr' >&3
response=$(cat <&3)
printf '%s\n' "$response" | grep -E '^Mode: (leader|follower)$'
