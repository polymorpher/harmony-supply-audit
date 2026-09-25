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

mkdir -p "$OUT/state" "$OUT/supply" "$OUT/forensics" "$OUT/policy"
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
The scan requires complete destination `cx` lookup indexes. A missing lookup
paired with a block-level spent marker is evidence of an incomplete index, not
an unspent receipt, and aborts the scan without publishing partial totals.

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
revert leakage only when its source debit occurred inside a failed or
reverted execution frame.

A failed precompile invocation alone is not such evidence. For traced source
transactions, exactly one precompile call must complete locally and its ABI
amount, recipient, destination shard, and effective sender context must match
the canonical receipt. The stored receipt and replay root must both succeed. A
failed non-root ancestor then distinguishes revert leakage from a valid
debit. Traces with zero or multiple completed calls or a receipt-identity
mismatch remain unclassified. A replay root inconsistent with the stored
receipt is labeled `replay_incompatible`.

Direct cross-shard transactions and direct calls to the precompile remain
untraced, but their stored source transaction receipt must report success. A
failed stored status is `receipt_inconsistent`, not a valid source debit.

Current archive software is not necessarily a historical execution engine.
Harmony commit `31752f21aa` changed the contract context used for precompiles
reached through `DELEGATECALL`. A transaction executed before that code change
can therefore fail when replayed by a current binary even when epoch rules are
selected correctly.

Resolve an incompatible or inconclusive replay only with independently
verified canonical source-debit evidence:

```sh
python3 toolkit/scripts/forensics/cx-source-audit.py \
  --rpc "$HARMONY_RPC_SHARD0" \
  --independent-evidence "$OUT/forensics/source-debit-evidence.csv" \
  --output "$OUT/forensics/source-audit.csv" \
  <receipt-ledger.csv>
```

The evidence CSV header is:

```text
source_shard,destination_shard,source_block,source_block_hash,receipt_index,receipt_tx_hash,from,to,amount_atto,source_debit_status,evidence_type,evidence_reference,evidence_sha256
```

`source_debit_status` must be `absent` or `persisted`. The evidence row must
repeat the full canonical receipt identity. `evidence_reference` is an absolute
path or a path relative to the evidence CSV; the classifier reads that local
artifact and verifies its lowercase `evidence_sha256`. Duplicate, unused, or
malformed evidence, a failed stored source receipt, or a conflict with a
conclusive compatible replay aborts the audit.

An independently proved absent debit is classified as `source_debit_absent`,
not `rollback_leak`. Absence establishes an unbacked destination credit but does
not by itself prove which mechanism prevented the debit. A compatible replay
showing the matching completed call inside a failed non-root frame supplies the
additional mechanism evidence required for `rollback_leak`.

Receipt ledgers must identify both shards. If an older destination-side ledger
omits either field, pass `--source-shard` or `--destination-shard` explicitly;
the classifier does not silently assume shard zero.

Summarize all non-overlapping source-audit outputs before using them in
reconciliation:

```sh
python3 toolkit/scripts/forensics/summarize-cx-source-audit.py \
  --output "$OUT/forensics/source-audit-summary.json" \
  "$OUT/forensics/source-audit-shard0.csv" \
  "$OUT/forensics/source-audit-shard1.csv"
```

The summary reports trace-proven rollback and independently proved debit
absence separately. Use `unbacked_cross_shard_credit_atto`, their exact sum, as
the historical-closure adjustment. Do not add a targeted subset a second time.

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

## 13. Rebuild the migration non-issuance audit

This step is separate from the factual claim ledger. Obtain:

- the reviewed current non-issuance inventory from `harmony-migration`;
- the retained initial-recipient balance CSV, its summary, and the raw
  balance-response evidence it cites. This repository keeps its own pinned
  copies under `artifacts/historical-retention-snapshot-20260916/current-state/`
  (balances SHA-256 `0e07628a…3369e7`, summary `b5d6b023…2b632e`), taken on
  2026-09-22 from the September 16 historical-hacks evidence package. That
  package is an external agent's workspace: do not read from or write into it
  during a rebuild; refresh the snapshot only from a package the external
  agent hands over;
- the factual cutoff claim summary.

Then run (the output CSV must reproduce SHA-256 `7a5a7364…43376e`):

```sh
python3 toolkit/scripts/addresses/build-revert-leak-retention.py \
  --receipt-audit artifacts/historical/cx-source-audit-through-prebloom.csv \
  --receipt-audit artifacts/historical/cx-source-audit-shard0-exploit.csv \
  --receipt-audit artifacts/historical/cx-source-audit-shard0-posthip30.csv \
  --receipt-audit artifacts/historical/cx-source-audit-shard0-prehip30-precompile.csv \
  --receipt-audit artifacts/historical/cx-source-audit-shard1-prehip30-late.csv \
  --exploit-transactions artifacts/historical/historical-exploit-traced-transactions.csv \
  --claims ../harmony-migration/artifacts/cutoff-20260910/claims/all-address-migration-claims-cutoff-metadata.csv \
  --prior-retention artifacts/historical-retention-snapshot-20260916/not-issued-retained-initial-addresses.csv \
  --prior-non-issuance ../harmony-migration/artifacts/supply-reconciliation-20260911/non-issuance-inventory.csv \
  --prior-non-issuance ../harmony-migration/artifacts/supply-reconciliation-20260911/inaccessible-address-inventory-20260923.csv \
  --output-csv artifacts/revert-leak-retention-20260923/not-issued-revert-leak-recipients.csv \
  --summary-output artifacts/revert-leak-retention-20260923/summary.json

python3 toolkit/scripts/addresses/build-non-issuance-audit.py \
  --existing-non-issuance ../harmony-migration/artifacts/supply-reconciliation-20260911/non-issuance-inventory.csv \
  --existing-non-issuance ../harmony-migration/artifacts/supply-reconciliation-20260911/inaccessible-address-inventory-20260923.csv \
  --retained-balances artifacts/historical-retention-snapshot-20260916/current-state/initial-address-current-balances.csv \
  --retained-summary artifacts/historical-retention-snapshot-20260916/current-state/summary.json \
  --cutoff-claim-summary artifacts/cutoff-20260910/claims/actual-supply-ledger-cutoff-summary.json \
  --revert-leak-retention artifacts/revert-leak-retention-20260923/not-issued-revert-leak-recipients.csv \
  --revert-leak-summary artifacts/revert-leak-retention-20260923/summary.json \
  --output-csv artifacts/historical-retention-snapshot-20260916/not-issued-retained-initial-addresses.csv \
  --summary-output results/2026-09-16/migration-non-issuance-summary.json \
  --replace
```

The first command withholds exploit credit from the wallets it was credited
to: for every destination of a proven revert-leak receipt (classification
`rollback_leak` or `source_debit_absent`) it records
`min(credited amount, native cutoff claim - earlier non-issuance)`. A wallet
holding only exploit credit loses its whole claim; legitimate remainders stay
eligible. The second command adds that list to the non-issuance summary as a
separate section and includes it in the totals; its own CSV output is unchanged.

The script checks every retained cap, source evidence path, category subtotal,
and address overlap. It verifies:

`gross cutoff claim = remaining full claim + not issued`.

The result must state that the old-chain claim is unchanged, replacement-chain
claimant issuance is reduced, and the amount remains in the **2050 premint
reserve** rather than being allocated to another purpose by this migration.
See [`2050-premint-reserve.md`](2050-premint-reserve.md).

### Verify the integrated migration-stage policy

After `harmony-migration` generates its address-level stage policy, independently
re-sum it against this audit's non-issuance result:

```sh
python3 toolkit/scripts/verify/migration-policy-reconciliation.py \
  --stage-policy ../harmony-migration/artifacts/migration-policy-20260917/migration-stage-policy.csv \
  --stage-summary ../harmony-migration/artifacts/migration-policy-20260917/migration-stage-summary.json \
  --migration-summary ../harmony-migration/artifacts/cutoff-20260910/claims/all-address-migration-claims-cutoff-summary.json \
  --existing-non-issuance ../harmony-migration/artifacts/supply-reconciliation-20260911/non-issuance-inventory.csv \
  --existing-non-issuance ../harmony-migration/artifacts/supply-reconciliation-20260911/inaccessible-address-inventory-20260923.csv \
  --historical-retention artifacts/historical-retention-snapshot-20260916/not-issued-retained-initial-addresses.csv \
  --historical-retention artifacts/revert-leak-retention-20260923/not-issued-revert-leak-recipients.csv \
  --supply-non-issuance-summary results/2026-09-16/migration-non-issuance-summary.json \
  --output results/2026-09-17/migration-policy-reconciliation.json \
  --report docs/findings/migration-policy-reconciliation.md
```

This verifies the wallet-only initial stage, reviewed 196/525 contract
partition, WONE source offset, validator-wrapper exception, and all exact
conservation equations without using an article calculation as authority.

## 14. Public source verification

Without a database:

```sh
make verify
```

This checks the public source manifest. Numerical results are intentionally not
present in a public clone during the independent-review period.

Local maintainers with the ignored result set can run `make verify-private`.

## 15. Optional protocol integration test

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
