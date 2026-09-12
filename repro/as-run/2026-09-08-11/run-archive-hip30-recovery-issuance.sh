#!/usr/bin/env bash

# SANITIZED HISTORICAL TEMPLATE: set the required environment variables before use.
# This is not byte-identical to the original run wrapper; see SOURCE-HASHES.json.
set -Eeuo pipefail
umask 077

readonly DB=${HARMONY_DB_SHARD0:?set HARMONY_DB_SHARD0}
readonly WORK=${AUDIT_WORK:?set AUDIT_WORK}
readonly BIN="$WORK/harmony-hip30-recovery-issuance-amd64"
readonly OUTPUT="$WORK/hip30-recovery-issuance-through-93623067.json"
readonly PARTIAL="$OUTPUT.partial"
readonly EXPECTED_BIN_SHA256=${EXPECTED_BIN_SHA256:?set EXPECTED_BIN_SHA256}
readonly START_BLOCK=49152000
readonly END_BLOCK=93623067

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
[[ ! -e "$OUTPUT" ]]
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
  -cache-mb 4096 \
  -handles 4096 >"$PARTIAL"

python3 - "$PARTIAL" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    result = json.load(source)
assert result["requested_start_block"] == 49_152_000
assert result["requested_end_block"] == 93_623_067
assert result["first_reward_block"] == 49_152_063
assert result["last_reward_block"] == 93_623_039
assert result["first_covered_header"] == 49_152_000
assert result["last_covered_header"] == 93_623_039
assert result["reward_groups"] == 694_860
assert result["covered_beacon_headers"] == 44_471_040
assert int(result["recovery_issuance_atto"]) > 0
PY

mv "$PARTIAL" "$OUTPUT"

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
