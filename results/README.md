# Results

The dated result set is temporarily excluded from Git under the numerical
embargo. It contains totals, component breakdowns, and address-level data.

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
formula, then reruns the historical residual chain.

## Large release assets

Large evidence and its release manifest remain local during the embargo.
Harmony databases are never release assets.
