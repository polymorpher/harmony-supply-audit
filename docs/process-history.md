# Process history

This file records what was done and why the method changed.

## September 6: initial account census

- Enumerated positive account balances from Harmony state tries.
- Preserved secure trie keys when address preimages were unavailable.
- Merged shard balances without using explorer data.
- Began separate preimage recovery for migration use. That work now belongs in
  `harmony-migration`, not this supply repository.

## September 8: actual supply

- Added validator-wrapper decoding.
- Counted active delegation, pending undelegation, and unclaimed rewards.
- Added cross-shard receipt accounting.
- Compared the account/staking total with the public supply endpoint.
- Found that the endpoint formula could not explain the state total.

## September 8–9: historical localization

- Compared historical state roots.
- Exported staking claims at historical checkpoints.
- Scanned canonical outgoing and incoming cross-shard receipts.
- Traced source transactions and reverted execution frames.
- Proved material rollback-leak incidents in May 2025 and April 2026, plus
  additional June–July 2026 cohorts.

## September 9: exploit flow tracing

- Built transaction and internal-value-edge ledgers.
- Separated source creation from later fund movement.
- Kept exchange and bridge labels separate from proved exploit creation.

## September 10: fixed cutoff

- Selected shard-0 block `93,623,067` at exactly
  `2026-09-10T14:00:00Z`.
- Selected shard-1 block `95,882,100`, one second earlier.
- Re-exported balances and staking claims at those exact roots.
- Audited every canonical block between the earlier snapshot and cutoff.
- Verified pending receipts and rebuilt the complete active-shard claim total.

## September 10: endpoint code trace

- Traced `/circulating-supply` to the issuance formula.
- Confirmed one hard-coded inaccessible address.
- Found that the reward counter is node-local metadata.
- Compared two nodes at the same block hash and state root.
- Proved that the counters differed.

An early report used the phrase “endpoint node-metadata and cutoff-height
adjustment.” It was replaced with two plain statements: the endpoint queried a
later block, and its node-local reward counter was wrong.

## September 10–11: closing the remaining gap

- Replayed HIP-30 reward groups over canonical headers.
- Measured recovery issuance exactly.
- Scanned staking targets and top-level precompile calls.
- Took state checkpoints around the TopMaxRate cleanup.
- Separated peak duplicated claim exposure, stale-liability cleanup, and missing
  validator rewards.

The 2024 accounting was clarified: age-seven principal was released once, but
failed wrapper persistence left a stale pending copy. The cleanup removed that
pending copy, not liquid balances from delegators.

## September 11: burn audit

- Verified the incident author's transactions individually.
- Corrected an important interpretation: the first six linked transactions
  consolidated funds; a later transaction performed the burn.
- Confirmed the article author's linked burn against the extra payout.
- Identified other affected addresses that sent value to the dead address.
- Checked additional inaccessible and precompile addresses.

Burn balances remained in every supply and claim total.

## September 11: blacklist and wallet-theft evidence

- Verified the supplied list against Harmony's final 2024 Ansible
  mint-response template and removed duplicate entries.
- Joined the list to the cutoff ledger.
- Kept direct extra-mint recipients separate from unrelated or auxiliary
  addresses.
- Extracted explicit perpetrator-controlled Harmony addresses from the
  supplied wallet-theft reports and compared them with the mint-response list.

An early routing attempt assigned the entire supplied list to a general
destination account. That was wrong and was discarded. The corrected scenario
caps a direct
extra-mint-recipient reclaim by exact unreturned extra mint.

This was the policy at that time. It was superseded by the later non-issuance
decision.

The complete 2021–2022 operational blacklist was not found. Further work is
deferred until former DevOps staff or node backups provide the original files.

## September 12: independent-review corrections

- Corrected the max-rate description from repeated liquid payouts to peak
  duplicated claim exposure.
- Documented that age-over-seven entries were not paid again; their stale
  pending claims could instead be redelegated.
- Added cutoff-formula reconstruction, shard-1 historical-balance derivation,
  destination-receipt mapping, and historical residual-chain tools.
- Extended private verification to derive the cutoff gaps from scanner outputs
  and rerun the historical closure.
- Added explicit limits for the pre-existing baseline, shard-1 classification,
  RPC-derived December reconstruction, and report-assigned address labels.

## September 15–16: non-issuance policy

- Replaced the prior destination routing for reviewed incident amounts with
  `not_issued` treatment.
- Kept the factual old-chain cutoff ledger unchanged.
- Required no replacement token or staking-vault share to be created for
  not-issued amounts.
- Preserved only the exact reviewed extra-mint portion on mixed rows; legitimate
  remainders stay eligible under the separate migration policy.
- Expanded wallet-theft evidence into explicitly report-identified
  perpetrators, transaction-linked recipients, and separate reported victims.
- Kept victims outside non-issuance unless independent evidence supports a
  different role.

## September 16: retained historical-hack balances

- Rechecked all initial recipients of the May 2025 and April 2026 incident
  distribution contracts at one fixed block.
- Confirmed that the refreshed balances matched the cutoff snapshot.
- Capped each retained amount by both initial incident-contract distribution
  and cutoff balance.
- Verified that the positive retained addresses did not overlap the existing
  non-issuance inventory.
- Added the capped retained amount to migration non-issuance and retained it in
  the Year 2025 Supply Reserve.
- Kept exchange reserves, mixed downstream balances, and reported victims
  outside this amount.

## Public package extraction

This repository was created after the analysis:

- maintained scanners were copied into a standalone geth-pinned module;
- machine-specific wrappers were converted to public templates;
- source hashes were retained for provenance;
- numerical findings and result tables were placed under a pre-publication
  Git ignore rule;
- large evidence stayed outside Git;
- private hosts, paths, node configuration, and logs were excluded;
- fast no-database verification was added for public reviewers.
