#!/usr/bin/env bash
source /workspace/scripts/common.sh
wait_for_brokers
while read -r topic retention bytes segment roll; do
  [[ -z "$topic" || "$topic" == \#* ]] && continue
  "$BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --create --if-not-exists \
    --topic "$topic" --partitions 3 --replication-factor 3 \
    --config min.insync.replicas=2 --config cleanup.policy=delete \
    --config retention.ms="$retention" --config retention.bytes="$bytes" \
    --config segment.bytes="$segment" --config segment.ms="$roll"
done < "$TOPICS"
# Existing mismatches are reported, never silently altered or deleted.
exec /bin/bash /workspace/scripts/verify-topics.sh
