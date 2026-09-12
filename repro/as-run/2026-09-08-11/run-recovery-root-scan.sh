#!/usr/bin/env bash

# SANITIZED HISTORICAL TEMPLATE: set the required environment variables before use.
# This is not byte-identical to the original run wrapper; see SOURCE-HASHES.json.
set -Eeuo pipefail
umask 077

readonly DB=${HARMONY_DB_SHARD0:?set HARMONY_DB_SHARD0}
readonly WORK=${AUDIT_WORK:?set AUDIT_WORK}
readonly BIN="$WORK/harmony-actual-supply-amd64"
readonly OUTPUT="$WORK/recovery-92730034-supply.json"
readonly ROOT=0x39e72dc20835abe61f69966bec2cc4766bb9e893c4168e117154dd539f2fc728
readonly EXPECTED_BIN_SHA256=${EXPECTED_BIN_SHA256:?set EXPECTED_BIN_SHA256}

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
[[ ! -e "$OUTPUT.partial" ]]
[[ "$(sha256sum "$BIN" | awk '{print $1}')" == "$EXPECTED_BIN_SHA256" ]]

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
  -root "$ROOT" \
  -output "$OUTPUT" \
  -cache-mb 4096 \
  -handles 4096 \
  -staking \
  -discover-validators

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
