#!/usr/bin/env bash
set -euo pipefail
case "${BROKER_ID:-}:${EXTERNAL_PORT:-}" in 1:19092|2:29092|3:39092) ;;
  *) echo 'Invalid broker ID / external port pair' >&2; exit 1;;
esac
# Bypass the image's default config generation; start the ZooKeeper broker directly.
cat /workspace/config/broker.properties > /tmp/bd-server.properties
printf '\nbroker.id=%s\nadvertised.listeners=INTERNAL://kafka-%s:9092,EXTERNAL://localhost:%s\n' \
  "$BROKER_ID" "$BROKER_ID" "$EXTERNAL_PORT" >> /tmp/bd-server.properties
exec /opt/kafka/bin/kafka-server-start.sh /tmp/bd-server.properties
