#!/usr/bin/env bash

# SANITIZED HISTORICAL TEMPLATE: set the required environment variables before use.
# This is not byte-identical to the original run wrapper; see SOURCE-HASHES.json.
set -Eeuo pipefail
umask 077

readonly DB=${HARMONY_DB_SHARD0:?set HARMONY_DB_SHARD0}
readonly WORK=${AUDIT_WORK:?set AUDIT_WORK}
readonly BIN="$WORK/harmony-hip30-recovery-issuance-amd64"
readonly EXPECTED_BIN_SHA256=${EXPECTED_BIN_SHA256:?set EXPECTED_BIN_SHA256}

readonly WINDOWS='
post2023-to-oct2024|51150848|64847871
oct2024-to-sep2025|64847872|78168062
sep2025-to-prebloom|78168000|91488254
prebloom-to-cutoff|91488192|93623067
'

restart_harmony() {
  service "${HARMONY_SERVICE:-harmony}" start || true
}

on_exit() {
  local status=$?
  trap - EXIT
  restart_harmony
  exit "$status"
}
trap on_exit EXIT

[[ "$(id -u)" -eq 0 ]]
[[ -d "$DB" ]]
[[ -x "$BIN" ]]
[[ "$(sha256sum "$BIN" | awk '{print $1}')" == "$EXPECTED_BIN_SHA256" ]]
service "${HARMONY_SERVICE:-harmony}" status >/dev/null

while IFS='|' read -r label start end; do
  [[ -z "$label" ]] && continue
  [[ "$label" =~ ^[a-z0-9-]+$ ]]
  [[ "$start" =~ ^[0-9]+$ ]]
  [[ "$end" =~ ^[0-9]+$ ]]
  [[ ! -e "$WORK/hip30-recovery-$label.json" ]]
  [[ ! -e "$WORK/hip30-recovery-$label.json.partial" ]]
done <<<"$WINDOWS"

service "${HARMONY_SERVICE:-harmony}" stop
for _ in $(seq 1 180); do
  if ! pgrep -x harmony >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if pgrep -x harmony >/dev/null 2>&1; then
  echo "Harmony did not stop cleanly" >&2
  exit 1
fi
if fuser "$DB/LOCK" >/dev/null 2>&1; then
  echo "Archive LevelDB lock remains held" >&2
  exit 1
fi

while IFS='|' read -r label start end; do
  [[ -z "$label" ]] && continue
  output="$WORK/hip30-recovery-$label.json"
  partial="$output.partial"
  runuser -u "${AUDIT_USER:-$(id -un)}" -- \
    ionice -c2 -n7 nice -n 5 \
    "$BIN" \
    -db "$DB" \
    -start "$start" \
    -end "$end" \
    -cache-mb 4096 \
    -handles 4096 >"$partial"
  python3 - "$partial" "$start" "$end" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    result = json.load(source)
assert result["requested_start_block"] == int(sys.argv[2])
assert result["requested_end_block"] == int(sys.argv[3])
assert result["covered_beacon_headers"] == result["reward_groups"] * 64
assert int(result["recovery_issuance_atto"]) > 0
PY
  mv "$partial" "$output"
done <<<"$WINDOWS"

restart_harmony
trap - EXIT
for _ in $(seq 1 240); do
  if service "${HARMONY_SERVICE:-harmony}" status >/dev/null 2>&1; then
    echo "Harmony restarted successfully"
    exit 0
  fi
  sleep 1
done

echo "Harmony did not become healthy after restart" >&2
exit 1
