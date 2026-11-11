#!/usr/bin/env bash
source /workspace/scripts/common.sh
wait_for_brokers
# Dedicated local test topic: business topics are never written by this script.
topic=bd.local.smoke.v1
"$BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --create --if-not-exists \
  --topic "$topic" --partitions 3 --replication-factor 3 \
  --config min.insync.replicas=2 --config cleanup.policy=delete \
  --config retention.ms=3600000 --config retention.bytes=8388608 \
  --config segment.bytes=1048576 --config segment.ms=60000
verify_topic "$topic" 3600000 8388608 1048576 60000
offsets=$("$BIN/kafka-get-offsets.sh" --bootstrap-server "$BOOTSTRAP" --topic "$topic" --time -1)
id=$(cat /proc/sys/kernel/random/uuid)
message="{\"testId\":\"$id\",\"source\":\"infra-local-smoke\"}"
printf '%s\n' "$message" | "$BIN/kafka-console-producer.sh" --bootstrap-server "$BOOTSTRAP" \
  --topic "$topic" --producer-property acks=all --producer-property enable.idempotence=true \
  --producer-property delivery.timeout.ms=30000 --producer-property request.timeout.ms=10000
while IFS=: read -r name partition offset; do
  # A timeout on a partition without the test record is expected.
  output=$("$BIN/kafka-console-consumer.sh" --bootstrap-server "$BOOTSTRAP" --topic "$topic" \
    --partition "$partition" --offset "$offset" --max-messages 1 --timeout-ms 5000 2>/dev/null) || true
  if [[ "$output" == "$message" ]]; then
    printf 'PASS: produced and consumed identical record; topic=%s partition=%s offset=%s\n%s\n' \
      "$topic" "$partition" "$offset" "$message"
    exit 0
  fi
done <<< "$offsets"
echo "FAIL: test record $id was not consumed." >&2
exit 1
