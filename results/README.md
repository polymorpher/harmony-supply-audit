# Results

The dated result sets are temporarily excluded from Git under the numerical
embargo. They contain totals, component breakdowns, and address-level data.

- `2026-09-11/` contains factual cutoff and historical incident results plus
  explicitly superseded destination calculations.
- `2026-09-16/` contains the current migration non-issuance policy overlay and
  refreshed retained historical-hack evidence.

In documentation, `not_issued` means retained in the **Year 2025 Supply
Reserve**, not allocated to a claimant in the current migration.

Public reviewers should follow `docs/reproduce.md` and record their own results
before comparing them with the original audit.

See `docs/numerical-embargo.md` for the release condition.

## Verification

`make verify` checks the public source package and does not require the withheld
result set.

Local maintainers with the ignored result files can run:

```sh
make verify-private
```

This derives the cutoff gaps from scanner outputs and a reconstructed endpoint
formula, reruns the historical residual chain, and verifies the current
non-issuance result and retained-address CSV.

## Large release assets

Large evidence and its release manifest remain local during the embargo.
Harmony databases are never release assets.
