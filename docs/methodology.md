# Methodology

## 1. Fix the comparison point

The cutoff is `2026-09-10T14:00:00Z`.

- shard 0: block `93,623,067`;
- shard 1: block `95,882,100`.

The checkpoint manifest records each block hash and state root. Every run must
verify these values before reading balances.

## 2. Enumerate liquid state

`account-snapshot` opens a specified state trie and iterates every account leaf.
It records:

- secure trie key;
- address, when a preimage is available;
- balance;
- nonce;
- code hash.

Supply arithmetic uses secure keys and integer balances, so a missing address
preimage does not remove value from the total.

## 3. Enumerate staking claims

Shard 0 stores validator wrappers. `staking-claims` discovers the wrappers from
the selected state root and sums by delegator:

- active delegation;
- pending undelegation;
- unclaimed reward.

Validator lifetime reward statistics are not claimant balances and are not
added again.

## 4. Reconcile cross-shard receipts

`cross-shard-supply` reads canonical source receipt groups and destination
lookup records at explicit shard cutoffs.

A failed destination lookup read is not evidence that a receipt is pending.
After a failed read, the scanner verifies that the key is absent; if the key
exists or its existence cannot be checked, it aborts without publishing totals.

A receipt is included as pending only when:

1. the source debit is within the source cutoff;
2. the receipt is supported by the active destination shard;
3. no canonical destination application exists at or before its cutoff.

Receipts to retired shards 2 and 3 remain a separate uncertainty because their
spent status cannot be proved from active-shard data alone.

## 5. Build the factual claim ledger

`actual-supply-ledger.py` combines liquid, staking, and supported pending
receipt components by secure key.

All arithmetic uses integer atto-ONE:

`1 ONE = 1,000,000,000,000,000,000 atto-ONE`.

Decimal strings are display values produced only after integer totals are
final.

## 6. Rebuild the endpoint formula

The public endpoint does not sum account state. Its code calculates:

`released genesis + fixed pre-staking rewards + local blk-rwd accumulator`

and subtracts one hard-coded address.

The audit reconstructs that formula at the cutoff and compares the same
canonical block across nodes. This exposed two independent effects: the queried
endpoint used a later block than the cutoff, and two nodes returned different
block-reward counters for the same block hash and state root.

The counter is node-local metadata, not consensus state.

The exact cutoff counter is reconstructed as:

`base blk-rwd + (cutoff validator lifetime rewards - base validator lifetime rewards)`

`reconstruct-cutoff-formula.py` performs this calculation from one
`block-reward-accumulator` output and two complete `actual-supply` outputs.

## 7. Localize historical differences

`historical-state-diff` compares state roots. Historical staking exports add
the staking components that a liquid-state diff cannot see.

Canonical outgoing-receipt and replay scans divide history into manifest
ranges. `cx-source-audit.py` then checks source transactions and traces to
distinguish:

- valid source debit;
- reverted-frame rollback leakage;
- unresolved source behavior.

Only canonical receipts with proved reverted source debit are classified as
rollback-created ONE.

For traced transactions, an invocation of the cross-shard precompile that
itself returned an error did not create a receipt. In particular, a rejected
second invocation must not turn a successful first debit into rollback leakage.
The classifier requires exactly one locally completed precompile invocation;
it counts rollback evidence only when an ancestor of that invocation failed.
No completed invocation or multiple possible producers remain `unclassified`.
These checks do not replace matching the canonical receipt to the source
transaction and its transfer payload in the surrounding forensic workflow.

The trace's root success/failure must agree with the stored transaction receipt;
a mismatch leaves the row `unclassified`. Matching statuses alone do not prove
equivalence of the internal execution.

Historical re-execution must also reproduce the implementation used at the
source height. An archive replay that rejects the precompile despite an existing
canonical source receipt is conflicting evidence, not proof of the original
debit. Resolve such rows using compatible historical execution or independent
source-debit evidence; do not interpret `unclassified` as a zero-value adjustment.

The preferred shard-1 historical measurement is a direct account-trie scan at
the matching historical root. When that root is unavailable, the audit derives
the historical balance from the measured cutoff balance:

`S1(t) = S1(cutoff) - later S0→S1 credits + later valid S1→S0 debits`

`map-cx-receipt-destinations.py` maps outgoing receipts to exact shard-1
destination blocks. `historical-shard1-balance.py` then applies the equation.
The result depends on the source audit's `valid_source_debit` labels.

The residual at each checkpoint is:

`S0 claims + S1 claims - genesis - pre-staking rewards - blk-rwd`

minus named direct-state adjustments such as HIP-30 recovery, the reconstructed
December incident, and cumulative rollback leakage.

`historical-closure.py` performs this calculation at every checkpoint and
checks the change between checkpoints. The residual chain is an independent
cross-check of shard-0-sourced leakage. It is not an independent check of
shard-1-sourced leakage because the shard-1 derivation uses the same source
classification; transaction traces are the primary evidence for that
direction.

## 8. Count HIP-30 recovery issuance

`hip30-recovery-issuance` replays the 64-block reward-group rule over canonical
shard-0 headers from HIP-30 activation to the cutoff.

It counts synthetic beacon links and included crosslinks using integer rules.
The resulting counts and issuance are withheld during independent review.

This amount is legitimate protocol issuance that the endpoint's
`blk-rwd-` formula omits.

## 9. Reconstruct staking bugs

### December 2023 repeated payouts

`undelegation-mint-reconcile.py` reads historical validator state at block
`51,085,312` and calculates repeated matured-undelegation payouts exactly.

The reconstructed amount is withheld during independent review.

### 2024 max-rate wrapper-write failure

The audit separates:

- peak duplicated claim exposure;
- stale pending claims deleted at cleanup;
- validator rewards counted by the formula but not saved;
- net effect in the state-versus-formula comparison.

At age seven, principal was released to liquid once, but failed validator
wrapper persistence could leave the same principal as a pending claim. After
age seven, the MaxRate rule suppressed another liquid payout. The stale claim
could still be redelegated. Cleanup removed remaining stale pending records; it
did not debit liquid ONE from a delegator account.

## 10. Audit burns and address lists

Burn evidence is transaction evidence. Sending ONE to an inaccessible address
does not remove it from state.

Address-list audits:

- normalize Bech32 and hexadecimal forms;
- deduplicate entries;
- join to the exact cutoff ledger;
- keep report-derived labels separate from chain-derived balances.

Allocation or treasury routing is not part of the supply calculation.

## 11. Verify independently

The repository provides three levels of checking:

1. database preflight and full scanner reruns;
2. compact result and CSV hash verification;
3. no-database integer reconciliation checks.

Curated report evidence and policy scenarios are labeled separately and are
not described as chain-regenerated results.
