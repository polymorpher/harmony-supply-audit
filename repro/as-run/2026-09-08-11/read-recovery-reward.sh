#!/usr/bin/env bash

# SANITIZED HISTORICAL TEMPLATE: set the required environment variables before use.
# This is not byte-identical to the original run wrapper; see SOURCE-HASHES.json.
set -Eeuo pipefail
umask 077

readonly DB=${HARMONY_DB_SHARD0:?set HARMONY_DB_SHARD0}
readonly WORK=${AUDIT_WORK:?set AUDIT_WORK}
readonly BIN="$WORK/harmony-block-reward-amd64"
readonly OUTPUT="$WORK/recovery-92730034-block-reward.json"
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

runuser -u "${AUDIT_USER:-$(id -un)}" -- "$BIN" -db "$DB" -block 92730034 >"$OUTPUT"

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
