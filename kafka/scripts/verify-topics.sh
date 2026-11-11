#!/usr/bin/env bash
source /workspace/scripts/common.sh
wait_for_brokers
for attempt in $(seq 1 12); do
  valid=true
  while read -r topic retention bytes segment roll; do
    [[ -z "$topic" || "$topic" == \#* ]] && continue
    verify_topic "$topic" "$retention" "$bytes" "$segment" "$roll" || valid=false
  done < "$TOPICS"
  if $valid; then echo 'PASS: both topics, 3 partitions, RF=3, leaders, ISR={1,2,3}, configurations.'; exit 0; fi
  echo "Metadata/ISR not ready or configuration mismatch ($attempt/12)." >&2
  sleep 5
done
exit 1
