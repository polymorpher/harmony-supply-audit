# Year 2025 Supply Reserve

In this audit, `not_issued` means:

- the amount is not issued to a claimant in the current migration;
- no replacement token or staking-vault share is created for that claimant;
- the amount remains in the **Year 2025 Supply Reserve**.

The reserve is the portion of the approved supply that remains unallocated by
the current migration. It is not a recipient address and it is not a transfer
made by the routing code.

This treatment does not delete old-chain balances or revise the factual cutoff
ledger. The accounting remains:

`gross old-chain cutoff claim = current migration issuance + amount retained in reserve`

That equation is a full-claim policy view. Eligibility thresholds, contract
handling, and other migration rules can further affect the actual deployment
amount.

The current migration does not assign reserve amounts to an operator, team
member, claimant, or spending program. Any future change to the reserve is a
separate decision outside this audit and must not be implied by the
`not_issued` label.

Code and result files may continue to use `not_issuing` or `not_issued`.
Public-facing documentation should describe the outcome as **retained in the
Year 2025 Supply Reserve**.
