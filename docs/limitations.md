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

The later residual chain accounts for changes after this checkpoint. It does
not prove that all earlier positive and negative components were separately
identified or that no earlier offsetting creation occurred.

## Historical shard-1 derivation

The preferred historical shard-1 value is a direct full account-trie scan.
Where the old trie was unavailable, the audit derived it from the cutoff
balance and later cross-shard flows.

That derivation uses the same `valid_source_debit` classifications as the
rollback audit. Therefore the residual chain is not an independent
confirmation of shard-1-sourced rollback leakage; compatible source
transaction traces or separately recorded canonical source-debit evidence are
the primary evidence for that direction.

A separate RPC check summed only addresses that were still positive at the
cutoff. It was lower than the derived historical value because it was not a
complete historical address census. It must not be described as an
independent full-state sum.

## Historical transaction replay

`debug_traceTransaction` executes historical transactions with the node's
current binary. Epoch selection does not revert non-fork-gated implementation
changes.

Harmony commit `31752f21aa` changed delegated precompile contract context after
some audited transactions had already executed. Current archive binaries can
therefore return a failed replay for a transaction whose stored receipt
succeeded. Such a trace is labeled `replay_incompatible` and is not used by
itself to classify the source debit.

Compatible historical execution is preferred. When it is unavailable,
independent canonical source-state evidence may resolve the row, but its
artifact reference and SHA-256 must be recorded. A result derived from that
evidence must not be described as reproduced by the incompatible trace.
Debit absence alone is labeled `source_debit_absent`; it is not promoted to the
mechanism-specific `rollback_leak` classification without compatible failed-frame
evidence.

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

The calculation reconstructs payments from historical pending entries and
protocol epoch rules. It does not observe every epoch-boundary liquid credit
individually. Agreement with Harmony's published incident amount and direct
checks of selected affected accounts are corroborating evidence, not a second
fully independent method.

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

The public curated input identifies addresses only as
`report-identified`. This is source attribution, not an independent legal or
identity finding by this audit.

Current policy also distinguishes a direct transaction-linked theft recipient
from an address explicitly labeled as a perpetrator. Reported victims are
recorded separately and are not automatically omitted from issuance.

## Long-pending cross-shard receipts

Supported source-debited receipts that were never applied at the destination
are reported separately from state-resident balances. Including them in the
claim ledger is an explicit migration treatment, not proof that they are
ordinary circulating balances.

## Migration policy

Reviewed incident amounts are now `not_issued` on the replacement chain. They
have no destination address, do not become treasury assets, and are unavailable
for another use. Historical treasury-routing figures remain only as superseded
calculation evidence.

The retained May/April amount is capped by initial incident-contract
distribution and cutoff balance. This proves balance-supported incident
provenance, not that every address is controlled by one person or every
retained unit was newly created. Exchange reserves and mixed downstream
balances are not added.

This decision does not convert every custody or reserve route into
non-issuance. Dedicated backing reserves such as WONE custody remain separate
migration policies.

This repository verifies the policy overlay but does not create the final
migration allocation. Thresholds, contract handling, custody, and deployment
remain in `harmony-migration`.

## Reproducible bytes

Some historical JSON files include old absolute paths, RPC URLs, and elapsed
times. Sanitized committed copies retain the original source hash but do not
claim to be byte-identical.

Large CSVs are not committed. Reproduction can compare their hashes with the
release manifest once release URLs are published.
