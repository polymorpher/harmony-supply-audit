# Numerical-results embargo

The source code, cutoff identifiers, database requirements, and reproduction
method are public for independent review.

The audit's numerical outputs are temporarily withheld. This includes:

- the total account and staking claim;
- the difference from the public supply endpoint;
- component and incident amounts;
- per-address balances, payouts, burns, and current non-issuance scenarios;
- superseded historical treasury calculations;
- result tables and machine-readable result files.

Harmony reviewers should run the code against their own archive databases and
record their results before receiving the withheld numbers. This avoids
anchoring their work to the original audit result.

The numerical files will be added after independent review and publication of
the accompanying public article. Their absence is intentional and does not mean
that the scans were not completed.

Local maintainers can run `make verify-private` when the ignored result files
are present. Public clones use `make verify` to verify the published source
package without revealing or requiring the embargoed outputs.
