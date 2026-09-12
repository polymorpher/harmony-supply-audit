# Database requirements

## Required databases

Most issuance and historical staking work needs a shard-0 archive database.

The complete active-shard cutoff and cross-shard calculation needs:

- shard 0 at block `93,623,067`;
- shard 1 at block `95,882,100`.

The word “archive” is not enough by itself. The database must still contain
every state trie, canonical header, body, receipt record, and lookup required
by `manifests/checkpoints/checkpoints.json`.

Run `db-preflight` before a long scan.

## Cold database rule

Harmony and the read-only scanners both use the LevelDB `LOCK`. Use one of
these methods:

1. stop Harmony cleanly and scan the original database read-only; or
2. stop Harmony, make a storage-level snapshot, restart Harmony, and scan the
   mounted snapshot.

Do not copy `.ldb` or `.sst` files while Harmony is writing. A file-by-file
copy of a live LevelDB can combine incompatible manifests and table files.

## Paths

Choose paths on your own machine:

```sh
export HARMONY_DB_SHARD0=/absolute/path/to/harmony_db_0
export HARMONY_DB_SHARD1=/absolute/path/to/harmony_db_1
export OUT="$PWD/artifacts/reproduction-2026-09-10"
```

Do not put `OUT` inside either database.

## Preflight

Build the toolkit, then run:

```sh
bin/db-preflight \
  -db "$HARMONY_DB_SHARD0" \
  -shard 0 \
  -checkpoints manifests/checkpoints/checkpoints.json \
  -output "$OUT/preflight-shard0.json"

bin/db-preflight \
  -db "$HARMONY_DB_SHARD1" \
  -shard 1 \
  -checkpoints manifests/checkpoints/checkpoints.json \
  -output "$OUT/preflight-shard1.json"
```

Preflight verifies:

- it can acquire the read-only LevelDB lock;
- expected canonical hashes exist;
- stored headers hash to those canonical hashes;
- required bodies exist;
- each required state root can be opened;
- shard-0 validator and reward-accumulator records exist.

It does not hash the entire multi-terabyte database.

## Historical RPC requirements

Some forensics use RPC because they need transaction traces or staking API
pagination. Run your own archival RPC where possible:

```sh
export HARMONY_RPC_SHARD0=http://127.0.0.1:9500
export HARMONY_RPC_SHARD1=http://127.0.0.1:9501
```

Required methods include:

- historical `hmyv2_getBlockByNumber`;
- `hmyv2_getAllValidatorInformationByBlockNumber`;
- transaction and receipt lookup;
- `debug_traceTransaction` with `callTracer`;
- `trace_block` for created-account origin checks.

Public RPCs were used for some historical checks. They are not guaranteed to
retain the required history or tracing methods, so they are not the default
reproduction input.

Do not run a node and a direct LevelDB scanner against the same database at the
same time. Use separate cold copies if RPC and direct scans must run
concurrently.

## Capacity and duration

Observed times are hardware-dependent:

- full state snapshot: about 25–30 minutes;
- HIP-30 canonical-header scan: about 15 minutes;
- bounded body/target scans: usually a few minutes;
- full historical tracing: potentially hours.

Shard-0 archive storage can be many terabytes. Keep temporary output,
compression, and backup space separate from the chain database.
