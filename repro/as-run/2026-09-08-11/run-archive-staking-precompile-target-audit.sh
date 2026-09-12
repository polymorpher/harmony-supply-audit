#!/usr/bin/env bash

# SANITIZED HISTORICAL TEMPLATE: set the required environment variables before use.
# This is not byte-identical to the original run wrapper; see SOURCE-HASHES.json.
set -Eeuo pipefail
umask 077

readonly DB=${HARMONY_DB_SHARD0:?set HARMONY_DB_SHARD0}
readonly WORK=${AUDIT_WORK:?set AUDIT_WORK}
readonly BIN="$WORK/harmony-staking-precompile-target-audit-amd64"
readonly CSV="$WORK/staking-precompile-targets-post2023-to-oct2024.csv"
readonly SUMMARY="$WORK/staking-precompile-targets-post2023-to-oct2024-summary.json"
readonly PARTIAL="$SUMMARY.partial"
readonly EXPECTED_BIN_SHA256=${EXPECTED_BIN_SHA256:?set EXPECTED_BIN_SHA256}
readonly START_BLOCK=51150847
readonly END_BLOCK=64847871

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
[[ ! -e "$CSV" ]]
[[ ! -e "$CSV.partial" ]]
[[ ! -e "$SUMMARY" ]]
[[ ! -e "$PARTIAL" ]]
[[ "$(sha256sum "$BIN" | awk '{print $1}')" == "$EXPECTED_BIN_SHA256" ]]
service "${HARMONY_SERVICE:-harmony}" status >/dev/null

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

runuser -u "${AUDIT_USER:-$(id -un)}" -- \
  ionice -c2 -n7 nice -n 5 \
  "$BIN" \
  -db "$DB" \
  -start "$START_BLOCK" \
  -end "$END_BLOCK" \
  -output "$CSV" \
  -cache-mb 4096 \
  -handles 4096 >"$PARTIAL"

python3 - "$PARTIAL" "$CSV" <<'PY'
import hashlib
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    result = json.load(source)
assert result["start_block_exclusive"] == 51_150_847
assert result["end_block_inclusive"] == 64_847_871
assert result["blocks_scanned"] == 13_697_024
with open(sys.argv[2], "rb") as csv_file:
    digest = hashlib.sha256(csv_file.read()).hexdigest()
assert result["output_sha256"] == digest
PY

mv "$PARTIAL" "$SUMMARY"

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
