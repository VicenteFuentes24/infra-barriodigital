#!/usr/bin/env bash
set -euo pipefail
case "${ZK_ID:-}" in 1|2|3) ;; *) echo 'Invalid ZK_ID' >&2; exit 1;; esac
mkdir -p /var/lib/kafka/data/zookeeper /var/lib/kafka/data/zookeeper-log
id_file=/var/lib/kafka/data/zookeeper/myid
if [[ -f "$id_file" ]] && [[ "$(cat "$id_file")" != "$ZK_ID" ]]; then
  echo 'Persistent ZooKeeper ID differs; refusing to overwrite it.' >&2
  exit 1
fi
[[ -f "$id_file" ]] || printf '%s\n' "$ZK_ID" > "$id_file"
exec /opt/kafka/bin/zookeeper-server-start.sh /workspace/config/zookeeper.properties
