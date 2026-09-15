# Independent reproduction

This guide uses your own Harmony databases. Replace every example path with a
path on your machine.

No original audit host is required.

## 1. Build and test

```sh
git clone <repository-url> harmony-supply-audit
cd harmony-supply-audit

make setup
make test
make build
```

Expected binaries are written to `bin/`.

## 2. Prepare cold databases

Set:

```sh
export HARMONY_DB_SHARD0=/absolute/path/to/harmony_db_0
export HARMONY_DB_SHARD1=/absolute/path/to/harmony_db_1
export OUT="$PWD/artifacts/reproduction-2026-09-10"

mkdir -p "$OUT/state" "$OUT/supply" "$OUT/forensics"
```

Stop Harmony before using the original LevelDB, or use a consistent cold
storage snapshot. See
[`database-requirements.md`](database-requirements.md).

## 3. Verify database coverage

```sh
bin/db-preflight \
  -db "$HARMONY_DB_SHARD0" \
  -shard 0 \
  -checkpoints manifests/checkpoints/checkpoints.json \
  -output "$OUT/preflight-shard0.json"

bin/db-preflight \
  -db "$HARMONY_DB_SHARD1" \
  -shard 1 \
  -checkpoints manifests/checkpoints/checkpoints.json \
  -output "$OUT/preflight-shard1.json"
```

If this fails, do not start a long scan. Obtain an archive snapshot containing
the missing records.

## 4. Export liquid balances

```sh
bin/account-snapshot \
  -db "$HARMONY_DB_SHARD0" \
  -root 0x5e1927beb00c17c341d02483fbe81a884cc45af1ecfb673366e685aca4632ec3 \
  -threshold-atto 1 \
  -require-preimages=false \
  -output "$OUT/state/shard0-positive-balances.csv" \
  > "$OUT/state/shard0-positive-balances.run.json"

bin/account-snapshot \
  -db "$HARMONY_DB_SHARD1" \
  -root 0x312a34c0254608c59013bc967c486fe036b784e0d2012b266d5fa4ecc2531760 \
  -threshold-atto 1 \
  -require-preimages=false \
  -output "$OUT/state/shard1-positive-balances.csv" \
  > "$OUT/state/shard1-positive-balances.run.json"
```

Missing address preimages do not affect the balance sum. They affect only the
human-readable address column.

## 5. Export staking claims

```sh
bin/staking-claims \
  -db "$HARMONY_DB_SHARD0" \
  -root 0x5e1927beb00c17c341d02483fbe81a884cc45af1ecfb673366e685aca4632ec3 \
  -discover-validators \
  -output "$OUT/state/staking-claims.csv" \
  > "$OUT/state/staking-claims.run.json"
```

Record the active stake, pending undelegation, and unclaimed reward totals
before comparing with another audit.

## 6. Reconcile cross-shard receipts

```sh
bin/cross-shard-supply \
  -shard0-db "$HARMONY_DB_SHARD0" \
  -shard1-db "$HARMONY_DB_SHARD1" \
  -shard0-cutoff 93623067 \
  -shard1-cutoff 95882100 \
  -output "$OUT/supply/cross-shard-supply.json"
```

Record the supported pending amount before comparing with another audit.

Receipts to retired shards 2 and 3 are not silently included.

## 7. Assemble the factual ledger

```sh
python3 toolkit/scripts/supply/actual-supply-ledger.py \
  --shard0-liquid "$OUT/state/shard0-positive-balances.csv" \
  --shard1-liquid "$OUT/state/shard1-positive-balances.csv" \
  --staking "$OUT/state/staking-claims.csv" \
  --receipts "$OUT/supply/cross-shard-supply.json" \
  --output "$OUT/supply/actual-supply-ledger.csv" \
  --summary-output "$OUT/supply/actual-supply-ledger-summary.json"
```

This is a factual component ledger. It is not an eligibility or allocation
file. Record its total before comparing with another audit.

## 8. Independently sum the state

```sh
bin/actual-supply \
  -db "$HARMONY_DB_SHARD0" \
  -root 0x5e1927beb00c17c341d02483fbe81a884cc45af1ecfb673366e685aca4632ec3 \
  -staking \
  -discover-validators \
  -output "$OUT/supply/actual-supply-shard0.json"
```

Run the same command without `-staking` for shard 1.

The independent totals must agree with the component exports.

### Reconstruct the endpoint formula at the cutoff

Run a second complete shard-0 scan at the base checkpoint:

```sh
bin/actual-supply \
  -db "$HARMONY_DB_SHARD0" \
  -root 0xde6ebf84f3cbb6095603dbfc8c33fba8abc9333ca5072a3f9ee97fc1bcb089d2 \
  -staking \
  -discover-validators \
  -output "$OUT/supply/actual-supply-shard0-base.json"

bin/block-reward-accumulator \
  -db "$HARMONY_DB_SHARD0" \
  -block 93529887 \
  > "$OUT/supply/block-reward-base.json"

python3 toolkit/scripts/verify/reconstruct-cutoff-formula.py \
  --base-accumulator "$OUT/supply/block-reward-base.json" \
  --base-supply "$OUT/supply/actual-supply-shard0-base.json" \
  --cutoff-supply "$OUT/supply/actual-supply-shard0.json" \
  --output "$OUT/supply/cutoff-formula.json"
```

The script adds the state-derived increase in validator lifetime rewards to the
base node-local accumulator. It then adds genesis and fixed pre-staking
issuance. Record the output before comparing it with another audit.

## 9. Reproduce HIP-30 issuance

```sh
bin/hip30-recovery-issuance \
  -db "$HARMONY_DB_SHARD0" \
  -start 49152000 \
  -end 93623067 \
  > "$OUT/supply/hip30-recovery.run.json"
```

Record the reward-group count, recovery-bearing link count, issuance, and
canonical digest before comparing with another audit.

Path and elapsed-time fields differ between machines and must not be compared
byte for byte.

## 10. Audit staking targets

```sh
bin/staking-target-audit \
  -db "$HARMONY_DB_SHARD0" \
  -start 51150847 \
  -end 64847871 \
  -output "$OUT/forensics/staking-targets.csv" \
  > "$OUT/forensics/staking-targets.run.json"

bin/staking-precompile-target-audit \
  -db "$HARMONY_DB_SHARD0" \
  -start 51150847 \
  -end 64847871 \
  -output "$OUT/forensics/staking-precompile-targets.csv" \
  > "$OUT/forensics/staking-precompile-targets.run.json"
```

Record the block count, transaction counts, precompile-call count, and unknown
target counts before comparing with another audit.

This does not test contract-internal precompile calls.

## 11. Reconstruct the December 2023 mint

This step needs an archival shard-0 RPC with historical staking pagination:

```sh
python3 toolkit/scripts/forensics/undelegation-mint-reconcile.py \
  --rpc "$HARMONY_RPC_SHARD0" \
  --block 51085312 \
  --output "$OUT/forensics/december-2023-mint.json"
```

Record the reconstructed amount before comparing with another audit.

## 12. Cross-shard exploit tracing

First generate canonical outgoing and replay ledgers with:

- `outgoing-cx-scan`;
- `cx-replay-scan`;
- the ranges in `manifests/checkpoints/checkpoints.json`.

Then run:

```sh
python3 toolkit/scripts/forensics/cx-source-audit.py \
  --rpc "$HARMONY_RPC_SHARD0" \
  --output "$OUT/forensics/source-audit.csv" \
  <receipt-ledger.csv>
```

`cx-source-audit.py` requires transaction traces. A receipt is classified as
rollback leakage only when its source debit occurred inside a failed or
reverted execution frame.

A failed precompile invocation alone is not such evidence. For traced source
transactions, exactly one precompile call must complete locally; a failed
ancestor then distinguishes rollback leakage from a valid debit. Traces with
zero or multiple completed calls, or an outcome inconsistent with the stored
transaction receipt, remain unclassified.

The offline regression suite includes a successful constructor that creates a
receipt and catches a rejected duplicate invocation. To reproduce its trace
with a real Harmony EVM, use an existing buildable Harmony checkout:

```sh
python3 scripts/test-cx-constructor-evm.py --harmony-source /path/to/harmony
```

This optional test uses a Go build overlay, an in-memory state database, and
mainnet epoch 2000 rules (before receipt rollback and strict-validation changes).
It does not modify the Harmony checkout or contact a node. The test asserts a
successful constructor, a source debit of 100 synthetic units, one matching
receipt, and a rejected second call. The Go dependencies/native build prerequisites
are those of the supplied Harmony checkout. It is not a mainnet transaction replay
or evidence that published audit totals were affected.

### Derive historical shard-1 balances when direct tries are unavailable

A direct `account-snapshot` at each historical shard-1 root is preferred. If an
archive does not contain those tries:

```sh
python3 toolkit/scripts/forensics/map-cx-receipt-destinations.py \
  --rpc "$HARMONY_RPC_SHARD1" \
  --input "$OUT/forensics/shard0-outgoing-receipts.csv" \
  --destination-shard 1 \
  --output "$OUT/forensics/shard0-to-shard1-destinations.csv"

python3 toolkit/scripts/forensics/historical-shard1-balance.py \
  --cutoff-balance-atto "$SHARD1_CUTOFF_BALANCE_ATTO" \
  --checkpoint-block "$SHARD1_CHECKPOINT_BLOCK" \
  --cutoff-block 95882100 \
  --credits "$OUT/forensics/shard0-to-shard1-destinations.csv" \
  --debits "$OUT/forensics/source-audit.csv" \
  --output "$OUT/forensics/shard1-checkpoint-balance.json"
```

The exact equation is:

`historical S1 = cutoff S1 - later S0→S1 credits + later valid S1→S0 debits`.

Resolve `SHARD1_CHECKPOINT_BLOCK` from the same UTC instant as the shard-0
checkpoint. The derived balance depends on the source audit's
`valid_source_debit` classifications.

### Recompute the residual chain

Copy `inputs/templates/historical-closure.example.json`, add one entry for each
checkpoint, and reference your scanner outputs:

```sh
python3 toolkit/scripts/verify/historical-closure.py \
  --input "$OUT/forensics/historical-closure-input.json" \
  --output "$OUT/forensics/historical-closure.json"
```

This computes every state-versus-formula residual and its change from the
previous checkpoint. Save the result before comparing it with the original
audit.

The complete historical command sequence is described in
[`process-history.md`](process-history.md) and the sanitized `repro/`
templates.

## 13. Public source verification

Without a database:

```sh
make verify
```

This checks the public source manifest. Numerical results are intentionally not
present in a public clone during the independent-review period.

Local maintainers with the ignored result set can run `make verify-private`.

## 14. Optional protocol integration test

The maintained scanners do not need Harmony source. To run the separate
fake-wrapper protocol regression test:

```sh
export HARMONY_SRC=/path/to/clean/polymorpher-harmony-checkout
export MCL_SRC=/path/to/clean/mcl-checkout
export BLS_SRC=/path/to/clean/bls-checkout

make integration-test
```

The script clones each supplied checkout into a temporary directory and checks
out the pinned revision there. It never changes the supplied checkout.
