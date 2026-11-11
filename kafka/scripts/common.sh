#!/usr/bin/env bash
set -euo pipefail
export KAFKA_HEAP_OPTS='-Xms32m -Xmx128m'
export KAFKA_OPTS='-XX:MaxDirectMemorySize=32m'
BOOTSTRAP='kafka-1:9092,kafka-2:9092,kafka-3:9092'
BIN=/opt/kafka/bin
TOPICS=/workspace/config/topics.tsv

wait_for_brokers() {
  local attempt output
  for attempt in $(seq 1 30); do
    if output=$(timeout 15 "$BIN/kafka-broker-api-versions.sh" --bootstrap-server "$BOOTSTRAP" 2>/dev/null) &&
       [[ $(printf '%s\n' "$output" | grep -cE '^kafka-[123]:9092 \(id: [123] ') == 3 ]]; then
      return 0
    fi
    echo "Waiting for all three brokers ($attempt/30)..." >&2
    sleep 2
  done
  echo 'Three responsive brokers are required.' >&2
  return 1
}

verify_topic() {
  local topic=$1 retention=$2 bytes=$3 segment=$4 roll=$5 description config
  description=$("$BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" --describe --topic "$topic")
  printf '%s\n' "$description"
  printf '%s\n' "$description" | awk '
    /PartitionCount:/ {
      for (i=1;i<=NF;i++) {
        if ($i=="PartitionCount:" && $(i+1)!=3) bad=1
        if ($i=="ReplicationFactor:" && $(i+1)!=3) bad=1
      }
      headers++
    }
    /Partition:/ {
      count++; leader=""; replicas=""; isr=""
      for(i=1;i<=NF;i++) {
        if($i=="Partition:") {p=$(i+1); seen[p]++; if(p !~ /^[012]$/) bad=1}
        if($i=="Leader:") leader=$(i+1)
        if($i=="Replicas:") replicas=$(i+1)
        if($i=="Isr:") isr=$(i+1)
      }
      if(leader !~ /^[123]$/) bad=1
      if(split(replicas,r,",")!=3 || split(isr,s,",")!=3) bad=1
      for(j=1;j<=3;j++) {
        rc=0; sc=0
        for(k=1;k<=3;k++) {if(r[k]==j) rc++; if(s[k]==j) sc++}
        if(rc!=1 || sc!=1) bad=1
      }
    }
    END {exit (bad || headers!=1 || count!=3 || seen[0]!=1 || seen[1]!=1 || seen[2]!=1)}' || return 1
  config=$("$BIN/kafka-configs.sh" --bootstrap-server "$BOOTSTRAP" --entity-type topics --entity-name "$topic" --describe)
  printf '%s\n' "$config"
  local expected
  for expected in 'min.insync.replicas=2' 'cleanup.policy=delete' "retention.ms=$retention" \
                  "retention.bytes=$bytes" "segment.bytes=$segment" "segment.ms=$roll"; do
    printf '%s\n' "$config" | grep -Eq "(^|[[:space:]])${expected//./\\.}([[:space:]]|$)" || {
      echo "Configuration mismatch: $topic needs $expected" >&2; return 1;
    }
  done
}
