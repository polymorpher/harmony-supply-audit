# Verification

## Fast verification without a database

Run:

```sh
make verify
```

This verifies every public source file against `manifests/source.sha256`. It
does not require or reveal the embargoed numerical results.

No network or database is required.

Local maintainers with the ignored result and finding files can also run:

```sh
make verify-private
```

That command verifies result hashes, recomputes reconciliation identities, and
checks the unredacted finding provenance.

## Source verification

`manifests/source.sha256` covers the public source package.

Regenerate it:

```sh
make manifest
git diff -- manifests/source.sha256
```

The manifest generator uses Git's tracked and nonignored file set. The
repository ignore rules exclude `.cursor`, local artifacts, dependencies,
binaries, caches, databases, generated run data, and embargoed numerical
findings.

## Full independent verification

A full verifier should:

1. run `db-preflight` against each cold database;
2. export both liquid states;
3. export shard-0 staking claims;
4. reconcile receipts at both cutoffs;
5. assemble the component ledger;
6. run `actual-supply` as an independent sum;
7. reproduce HIP-30 issuance;
8. run the native and precompile staking-target audits;
9. save the deterministic fields and CSV hashes before receiving the original
   audit results.

The original result manifest will be published after the independent-review
period.

## Deterministic and run-specific fields

Deterministic result fields include:

- block numbers, hashes, and state roots;
- counts derived from canonical records;
- integer atto-ONE totals;
- canonical sequence digests;
- generated CSV hashes.

Run-specific fields include:

- database and output paths;
- RPC URLs;
- hostnames;
- elapsed time and throughput;
- architecture and process metadata.

Do not compare a complete run JSON byte for byte when it contains run-specific
fields. Compare the deterministic fields listed in the relevant result
manifest.

## Result classes

When published, each result is classified as:

- `database-derived`: reproduced from canonical LevelDB records;
- `RPC-derived`: reproduced from specified historical RPC methods;
- `curated external evidence`: extracted from reports or operations history;
- `policy scenario`: arithmetic that applies an allocation assumption.

Only the first two are chain-derived. Curated and policy files must retain
source hashes and extraction notes.

## Public checkpoint identifiers

### Cutoff

- shard-0 block:
  `0x23572e11f6ef9afe4c27ab3102f15b99fd7277ae5f685ccaef0ae571fe7ee0b6`;
- shard-0 state root:
  `0x5e1927beb00c17c341d02483fbe81a884cc45af1ecfb673366e685aca4632ec3`;
- shard-1 block:
  `0xf801577a5480175c05a63c8e4e5cf3d2623e1a01bdf176e16b46967405ae02ee`;
- shard-1 state root:
  `0x312a34c0254608c59013bc967c486fe036b784e0d2012b266d5fa4ecc2531760`.

The total claim, HIP-30 output, staking-target output, and endpoint comparison
are intentionally withheld. Independent reviewers should record those values
from their own run.

## CI limits

CI builds and tests the code with small fixtures. It does not include a real
archive database. Database-scale findings require an independent archive run
or verification of the published release artifacts.
