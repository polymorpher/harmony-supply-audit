# Limitations and open work

## Retired shards

The active cutoff uses shards 0 and 1. Final shard-2 and shard-3 contract state
has not been recovered and enumerated.

Historical shard-1 receipt groups to retired shards were found. Their count
and value are withheld during independent review. Their destination spent
status cannot be proved from active-shard records, so they remain separate
from the primary result.

## Pre-existing deficit

At the December 18, 2023 checkpoint, the issuance formula exceeded the counted
active-shard balances. The amount is withheld during independent review.

This is not unexplained minting. It may include protocol fee destruction,
contract balances left on retired shards, and smaller accounting effects. The
components have not been fully separated.

## Staking-precompile internal calls

The native staking audit and top-level calls to precompile `0xfc` found no
unknown validator target in the audited interval.

A contract can call the precompile internally. Those calls are not represented
as top-level transactions in block bodies. Full exclusion requires transaction
re-execution or complete call traces.

## Burn paths

The blacklisted extra-mint burn audit checked direct transfers and one
intermediate top-level address. It did not prove every longer or
contract-internal route.

ONE is fungible. Address linkage does not prove which individual units were
burned.

## Historical blacklist

The final 2024 Ansible mint-response blacklist is preserved and verified.

The separate 2021–2022 production blacklist used during extension-wallet theft
incidents has not been located. GitHub default-branch searches do not recover
an operator file that was deployed out of band.

The best remaining source is former DevOps staff or old leader-node backups.
Useful files would include:

- `.hmy/blacklist.txt` from December 2021 through April 2022;
- matching `allowedtxs.txt`;
- deployment tickets or hashes;
- node backup timestamps.

Do not resume that search without new source material.

## RPC-derived December amount

The exact December 2023 repeated-payout amount was reconstructed from
historical staking RPC state at block `51,085,312`.

The script and result are preserved, but a local database-only implementation
of that particular reconstruction is not yet included.

## Node-local reward counter

`blk-rwd-<height>` is stored in each node's local database and is not committed
to the state root. Two nodes can have the same canonical state but different
endpoint supply responses.

The audit proves the observed divergence. It does not prove which code path
caused the affected node's missing counter value.

## Curated evidence

Wallet-theft labels and operations-list history come from reports and GitHub
history. They are curated evidence, not conclusions regenerated from chain
state.

The uploaded investigation reports are not republished here. Their titles and
hashes are recorded where their extracted addresses are used.

## Migration policy

Treasury-routing figures are retained locally under the numerical embargo as a
historical policy scenario. This repository does not create the final migration
allocation or choose the treasury destination.

## Reproducible bytes

Some historical JSON files include old absolute paths, RPC URLs, and elapsed
times. Sanitized committed copies retain the original source hash but do not
claim to be byte-identical.

Large CSVs are not committed. Reproduction can compare their hashes with the
release manifest once release URLs are published.
