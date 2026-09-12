#!/usr/bin/env bash

# SANITIZED HISTORICAL TEMPLATE: set the required environment variables before use.
# This is not byte-identical to the original run wrapper; see SOURCE-HASHES.json.
set -Eeuo pipefail
umask 077

readonly DB=${HARMONY_DB_SHARD0:?set HARMONY_DB_SHARD0}
readonly WORK=${AUDIT_WORK:?set AUDIT_WORK}
readonly SUPPLY_BIN="$WORK/harmony-actual-supply-amd64"
readonly REWARD_BIN="$WORK/harmony-block-reward-amd64"
readonly SUPPLY_BIN_SHA256=8b41c0fa93dbe4f41beeb12d4b8cb35d6c055651f289df786242d39e1d1c640f
readonly REWARD_BIN_SHA256=1aaf32e1ce873c9696aea2b8cef73cca468cc3717fac95a2a0add5fb4a5301d0

: "${SCAN_LABEL:?SCAN_LABEL is required}"
: "${SCAN_BLOCK:?SCAN_BLOCK is required}"
: "${SCAN_ROOT:?SCAN_ROOT is required}"

[[ "$SCAN_LABEL" =~ ^[a-z0-9-]+$ ]]
[[ "$SCAN_BLOCK" =~ ^[0-9]+$ ]]
[[ "$SCAN_ROOT" =~ ^0x[0-9a-f]{64}$ ]]

readonly SUPPLY_OUTPUT="$WORK/$SCAN_LABEL-supply.json"
readonly REWARD_OUTPUT="$WORK/$SCAN_LABEL-block-reward.json"

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
[[ -x "$SUPPLY_BIN" ]]
[[ -x "$REWARD_BIN" ]]
[[ ! -e "$SUPPLY_OUTPUT" ]]
[[ ! -e "$SUPPLY_OUTPUT.partial" ]]
[[ ! -e "$REWARD_OUTPUT" ]]
[[ "$(sha256sum "$SUPPLY_BIN" | awk '{print $1}')" == "$SUPPLY_BIN_SHA256" ]]
[[ "$(sha256sum "$REWARD_BIN" | awk '{print $1}')" == "$REWARD_BIN_SHA256" ]]

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
  "$SUPPLY_BIN" \
  -db "$DB" \
  -root "$SCAN_ROOT" \
  -output "$SUPPLY_OUTPUT" \
  -cache-mb 4096 \
  -handles 4096 \
  -staking \
  -discover-validators

runuser -u "${AUDIT_USER:-$(id -un)}" -- \
  "$REWARD_BIN" \
  -db "$DB" \
  -block "$SCAN_BLOCK" >"$REWARD_OUTPUT"

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
