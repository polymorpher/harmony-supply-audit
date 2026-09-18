# 2050 premint reserve

In this audit, `not_issued` means:

- the amount is omitted from the applicable migration token and
  staking-vault allocations;
- no replacement token or staking-vault share is created for that amount;
- the amount remains unallocated within the fixed **2050 premint reserve**.

The reserve is part of the fixed 26.271 billion ONE premint, based on
`12.6 billion + 441 million × 31 years`. Migration allocations and retained
amounts are portions of that premint; neither changes the ERC-20 total supply.

The reserve is an accounting bucket, not a recipient address or a transfer
made by routing code. This treatment does not delete old-chain balances or
revise the factual cutoff ledger. It does not authorize a burn, treasury
transfer, or new spending program.

The earlier repository label “Year 2025 Supply Reserve” referred to this same
premint-reserve concept and is superseded. Code and result files may continue
to use stable machine fields such as `not_issuing` or `not_issued`.
