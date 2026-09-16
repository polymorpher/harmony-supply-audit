# Audit toolkit

The maintained commands read Harmony's LevelDB and RPC formats without
importing the Harmony Go module. They pin go-ethereum `v1.11.2`, matching the
database and trie implementation selected by the referenced Harmony revision.

Build all commands:

```sh
make build
```

The binaries are written to `bin/`.

## Commands

- `account-snapshot`: export every positive account from a state root.
- `actual-supply`: sum liquid accounts and optional staking claims.
- `staking-claims`: export active stake, undelegations, and rewards by
  delegator.
- `cross-shard-supply`: classify cross-shard receipts at explicit cutoffs.
- `cx-lookup` and `cx-lookup-snapshot`: inspect or copy bounded destination
  receipt lookups.
- `block-reward-accumulator`: read node-local `blk-rwd-<height>` metadata.
- `historical-state-diff`: compare two account-state roots.
- `outgoing-cx-scan` and `cx-replay-scan`: enumerate canonical receipt
  creation and application.
- `hip30-recovery-issuance`: count exact HIP-30 recovery issuance.
- `staking-target-audit`: audit native staking targets.
- `staking-precompile-target-audit`: audit top-level calls to precompile
  `0xfc`.
- `db-preflight`: confirm that a cold database contains the required
  checkpoints, bodies, state tries, and local reward counters.

## Scripts

- `supply/`: assemble factual component ledgers.
- `forensics/`: historical staking, receipt-source, exploit-flow, and
  undelegation-mint analysis, including shard-1 historical-balance derivation
  and destination-receipt mapping.
- `addresses/`: join address lists to an exact cutoff ledger and verify the
  migration non-issuance overlay for reviewed incident balances.
- `cutoff/`: verify canonical intervals, changed state, created accounts, and
  pending receipts.
- `verify/`: cutoff-formula reconstruction, historical residual closure, and
  checks over locally generated result metadata.

This repository verifies non-issuance policy inputs but does not build the
final allocation. Eligibility thresholds, destination routing, and deployment
logic remain in the separate `harmony-migration` project.
