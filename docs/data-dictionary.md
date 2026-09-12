# Data dictionary

## Common fields

- `address`: 20-byte EVM-style address.
- `address_bech32`: Harmony `one1…` encoding of the same address.
- `secure_key`: Keccak-256 state-trie key for an account address.
- `*_atto`: exact integer atto-ONE.
- `*_one`: decimal display with 18 fractional digits.
- `block`, `block_number`: canonical block height.
- `block_hash`: canonical header hash.
- `state_root`: account-state trie root.
- `output_sha256`: SHA-256 of a generated file.

Atto fields are authoritative for arithmetic. ONE fields are display values.

## Account snapshot CSV

- `secure_key`: account trie key.
- `address`: recovered address, or empty if its preimage is unavailable.
- `balance_atto`: liquid ONE.
- `nonce`: account transaction nonce.
- `code_hash`: EVM code hash.

## Staking claims CSV

- `secure_key`: delegator trie key.
- `address`: delegator address.
- `active_delegation_atto`: active principal.
- `pending_undelegation_atto`: principal waiting for unlock.
- `unclaimed_reward_atto`: reward still held in staking state.

Validator lifetime reward statistics are reported in summaries but are not
claim components.

## Factual supply ledger CSV

- `liquid_shard0_atto`, `liquid_shard1_atto`: liquid balance per shard.
- `liquid_total_atto`: sum of active-shard liquid balances.
- `active_delegation_atto`: active delegated principal.
- `pending_undelegation_atto`: pending principal.
- `unclaimed_reward_atto`: unclaimed staking reward.
- `pending_cross_shard_atto`: supported source-debited receipt not yet applied.
- `total_claim_atto`: sum of all preceding claim components.
- `nonce_shard0`, `nonce_shard1`: per-shard account nonce.
- `code_hash_shard0`, `code_hash_shard1`: per-shard EVM code hash.

## Historical state-diff CSV

- `secure_key`: changed account key.
- `old_*`, `new_*`: values at each root.
- `balance_delta_atto`: signed liquid change.
- `change_type`: created, changed, or deleted.

## Outgoing and replay receipt CSVs

Important fields include:

- source and destination shard;
- source block and transaction hash;
- receipt transaction hash and index;
- recipient and secure key;
- amount atto;
- canonical source/destination status;
- duplicate application or proof identity;
- source-trace classification.

`rollback_leak` means the destination receipt was accepted while the matching
source debit occurred inside execution that reverted.

## Staking-target audit CSVs

Native staking audit:

- directive;
- actor/delegator;
- target validator;
- amount;
- whether the target belongs to the known validator set.

Precompile audit:

- top-level transaction and block;
- ABI method;
- delegator;
- target validator;
- amount;
- calldata validity;
- target-set membership.

Neither CSV contains contract-internal calls.

## Result metadata classes

When published, result entries use one of:

- `database-derived`;
- `RPC-derived`;
- `curated external evidence`;
- `policy scenario`.

Run metadata such as paths, URLs, elapsed time, and throughput is not a
deterministic result.

## Curated address evidence

The inputs under `inputs/curated/` retain:

- Bech32 as the primary address form;
- equivalent hexadecimal form where available;
- incident/report role;
- source citation and source hash.

An address label is not promoted from “suspected” to “perpetrator” without an
explicit source statement.

## Treasury scenario fields

Treasury scenario files are retained locally under the numerical embargo as
historical context, not maintained allocation code:

- `extra_mint_atto`;
- `verified_burn_atto`;
- `unreturned_extra_atto`;
- `treasury_reclaim_atto`;
- `remaining_original_address_allocation_atto`;
- decision and evidence notes.

These fields do not change `total_claim_atto`.
