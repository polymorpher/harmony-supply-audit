# Harmony supply audit

This repository independently measures Harmony account and staking claims,
rebuilds the public supply formula, and documents historical events that made
the two numbers differ.

It is designed for public review. A developer can run the tools with their own
Harmony archive databases. No access to the original machines is required.

## Numerical results

The total, component breakdowns, incident amounts, and address-level result
tables are temporarily withheld. Harmony reviewers can use this repository to
produce their own numbers before seeing the original audit result.

See [`docs/numerical-embargo.md`](docs/numerical-embargo.md) for the release
condition and [`docs/reproduce.md`](docs/reproduce.md) for the independent
reproduction procedure.

## Repository scope

Included:

- account and staking supply;
- cross-shard receipt accounting;
- HIP-30 recovery issuance;
- historical state and exploit-flow analysis;
- staking-target audits;
- burn, blacklist, and wallet-theft address evidence;
- retained historical-incident balances and migration non-issuance checks;
- compact result metadata and checksums.

Not included:

- wallet preimage recovery;
- migration eligibility thresholds;
- final routing and deployment implementation;
- final migration allocation generation.

Those belong in the separate `harmony-migration` project. This audit records
the current policy input: reviewed extra-mint, inaccessible, wallet-theft, and
retained historical-hack amounts are not recreated on the replacement chain.
Instead, they remain in the
[Year 2025 Supply Reserve](docs/year-2025-supply-reserve.md) and are not
allocated to a claimant or another purpose by the current migration. Exact
policy-scenario figures remain under the numerical embargo.

## Quick start

Requirements:

- Go `1.24.2`;
- Python `3.10` or later;
- a stopped Harmony archive database or a consistent cold snapshot.

The optional Harmony integration test also needs Git, a C/C++ compiler, GMP,
and OpenSSL.

Install Go modules, build, and run tests:

```sh
make setup
make build
make test
make check-public
```

Preflight a shard-0 database:

```sh
bin/db-preflight \
  -db /absolute/path/to/harmony_db_0 \
  -shard 0 \
  -checkpoints manifests/checkpoints/checkpoints.json \
  -output artifacts/preflight-shard0.json
```

Then follow
[`docs/reproduce.md`](docs/reproduce.md).

## Database safety

Read-only LevelDB opens still use the database `LOCK`. Stop Harmony first, or
scan a consistent cold snapshot. Never copy a live LevelDB file by file.

Keep outputs outside the database directory.

## Harmony Go source

The default toolkit does not require a Harmony source checkout. It reads the
raw database formats directly and pins go-ethereum `v1.11.2`, matching the
referenced Harmony revision.

The optional fake-validator-wrapper integration test does require Harmony,
MCL, and BLS source. Set `HARMONY_SRC`, `MCL_SRC`, and `BLS_SRC` to clean
checkouts, or let the explicit `make integration-test` target clone temporary
copies. The pinned revisions are in
[`manifests/dependencies.lock.json`](manifests/dependencies.lock.json).

The integration script clones from a supplied checkout into a temporary
directory. It does not checkout, fetch, or modify the supplied checkout.

## Repository map

- `toolkit/cmd/`: maintained Go scanners.
- `toolkit/scripts/`: maintained Python analysis and verification.
- `docs/`: scope, methodology, reproduction, verification, and findings.
- `inputs/curated/`: public address inputs with provenance.
- `manifests/`: public dependency, checkpoint, and source identities.
- `results/`: the public embargo notice; numerical files remain local.
- `artifacts/`: git-ignored local outputs.
- `repro/`: sanitized historical run templates and original source hashes.

## Important limits

The audit still does not fully resolve:

- contract balances left on retired shards 2 and 3;
- some retired-shard receipt status;
- the cause and components of a pre-existing deficit;
- contract-internal calls to staking precompile `0xfc`;
- the complete 2022-era production blacklist.

See [`docs/limitations.md`](docs/limitations.md).
