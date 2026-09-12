#!/usr/bin/env bash

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT=${OUTPUT:-"$ROOT/bin"}
COMMANDS=(
  account-snapshot
  actual-supply
  staking-claims
  cross-shard-supply
  cx-lookup
  cx-lookup-snapshot
  block-reward-accumulator
  historical-state-diff
  outgoing-cx-scan
  cx-replay-scan
  hip30-recovery-issuance
  staking-target-audit
  staking-precompile-target-audit
  db-preflight
)

mkdir -p "$OUTPUT"
cd "$ROOT/toolkit"

for command in "${COMMANDS[@]}"; do
  CGO_ENABLED=0 GOWORK=off go build \
    -buildvcs=false \
    -trimpath \
    -o "$OUTPUT/$command" \
    "./cmd/$command"
done

echo "Built ${#COMMANDS[@]} commands in $OUTPUT"
