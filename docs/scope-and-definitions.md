# Scope and definitions

## What this audit measures

The audit uses five separate quantities. They must not be treated as
interchangeable.

### Account and staking claims

This is the sum recognized by chain state:

- liquid account balances;
- active delegation;
- pending undelegation;
- unclaimed staking rewards;
- supported source-debited cross-shard receipts that had not arrived.

The cutoff total is withheld during the independent-review period.

### Replacement-chain issued amount

This is a migration policy result:

`gross cutoff claim - reviewed not-issued amounts`

`not_issued` is terminal. No replacement token or staking-vault share is
created, no treasury receives the amount, and it is not available for another
use.

For an extra-mint recipient, only the reviewed extra-mint portion is omitted.
Any legitimate remainder stays eligible under the separate migration policy.

### State-resident formula gap

This compares balances and staking records already in active-shard state with
the protocol issuance formula before address exclusions.

It does not include receipts still outside destination state.

### Public supply endpoint

The endpoint calculates:

`released genesis + fixed pre-staking rewards + node-local block reward counter`

and then subtracts one hard-coded address.

It does not enumerate accounts, contracts, delegations, undelegations, or
cross-shard receipts.

### Circulating supply

“Circulating” is a policy term. A balance can exist in state but be difficult
or impossible to spend. This repository reports those balances separately
instead of silently changing the state sum.

## Peak and net bug amounts

Gross creation records actual unsupported liquid credits. Peak duplicated
claim exposure records principal represented twice in state, even when it was
not paid twice in liquid form.

Net effect records what remains in a later state-versus-formula comparison
after protocol cleanup and missing credits are included.

For the 2024 max-rate bug, principal was released to liquid once while failed
wrapper persistence left the same principal as a stale pending claim. The
audit separately records peak duplicated claim exposure, stale pending claims
deleted by cleanup, validator rewards counted by the formula but not saved,
and the measured post-checkpoint net effect. Those amounts are withheld during
the independent-review period.

The cleanup did not debit liquid ONE from delegators. It removed stale pending
undelegation records that duplicated already-paid liquid value.

## Burned and inaccessible balances

Sending ONE to an address such as `0x000…dEaD` does not delete the balance from
state. It makes the balance practically inaccessible.

Therefore:

- burn balances remain in the gross state sum;
- burn balances are not deducted from bug-created amounts;
- reviewed burn and inaccessible balances are not issued on the replacement
  chain.

This does not claim that the old-chain balances disappeared. It separates
factual old-chain accounting from replacement-chain issuance.

## Address formats

Harmony Bech32 (`one1…`) is the primary display format for people and address
lists. The equivalent 20-byte hexadecimal (`0x…`) form is recorded alongside
it for EVM and raw-state verification.

The two encodings identify the same account.

## Authority and trust

Authoritative:

- canonical block hashes and state roots;
- trie values read from a database containing those roots;
- canonical transaction and receipt bodies;
- exact integer atto-ONE arithmetic.

Supporting, but not independently authoritative:

- node-local `blk-rwd-` metadata;
- public RPC responses;
- explorer output;
- report-derived address labels;
- migration-policy scenarios.

Every published result identifies its class in the result metadata or release
manifest.
