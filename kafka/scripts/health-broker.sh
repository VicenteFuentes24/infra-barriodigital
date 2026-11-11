#!/usr/bin/env bash
source /workspace/scripts/common.sh
exec "$BIN/kafka-topics.sh" --bootstrap-server localhost:9092 --list
