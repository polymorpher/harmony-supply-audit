#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Package compact public results from a local accounting tree"
    )
    parser.add_argument("--accounting-root", required=True)
    parser.add_argument("--output-root", required=True)
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_string(value):
    replacements = {
        "local/harmony-balance-accounting/artifacts/supply-reconciliation-20260911/": "results/2026-09-11/",
        "local/harmony-balance-accounting/": "source://harmony-balance-accounting/",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    absolute_prefixes = tuple("/" + name for name in ("Users/", "home/", "mnt/", "data/"))
    if value.startswith(absolute_prefixes):
        return "redacted://" + Path(value).name
    return value


def normalize(value):
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, str):
        return normalize_string(value)
    return value


def csv_rows(path):
    with path.open(newline="") as source:
        return sum(1 for _ in csv.reader(source)) - 1


def main():
    args = parse_args()
    accounting = Path(args.accounting_root).resolve()
    output = Path(args.output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)

    supply = accounting / "artifacts" / "supply-reconciliation-20260911"
    cutoff = accounting / "artifacts" / "cutoff-20260910"
    mappings = [
        (supply / "reconciliation.json", "reconciliation.json", "curated external evidence"),
        (
            supply / "december-2023-undelegation-mint-reconstruction.json",
            "december-2023-undelegation-mint-reconstruction.json",
            "RPC-derived",
        ),
        (
            supply / "max-rate-opening-payout-audit.json",
            "max-rate-opening-payout-audit.json",
            "curated external evidence",
        ),
        (supply / "burn-address-audit.json", "burn-address-audit.json", "curated external evidence"),
        (
            supply / "staking-precompile-target-audit-summary.json",
            "staking-precompile-target-audit-summary.json",
            "database-derived",
        ),
        (
            supply / "blacklisted-address-cutoff.csv",
            "blacklisted-address-cutoff.csv",
            "database-derived",
        ),
        (
            supply / "blacklisted-address-cutoff-summary.json",
            "blacklisted-address-cutoff-summary.json",
            "database-derived",
        ),
        (
            supply / "extra-mint-blacklist-burn-path-audit.json",
            "extra-mint-blacklist-burn-path-audit.json",
            "curated external evidence",
        ),
        (
            supply / "extra-mint-blacklist-reclaim.csv",
            "extra-mint-blacklist-reclaim.csv",
            "policy scenario",
        ),
        (
            supply / "extra-mint-blacklist-reclaim-summary.json",
            "extra-mint-blacklist-reclaim-summary.json",
            "policy scenario",
        ),
        (
            supply / "reported-wallet-theft-perpetrator-cutoff.csv",
            "reported-wallet-theft-perpetrator-cutoff.csv",
            "database-derived",
        ),
        (
            supply / "reported-wallet-theft-perpetrator-cutoff-summary.json",
            "reported-wallet-theft-perpetrator-cutoff-summary.json",
            "database-derived",
        ),
        (
            supply / "wallet-theft-report-coverage.json",
            "wallet-theft-report-coverage.json",
            "curated external evidence",
        ),
        (
            supply / "blacklist-operations-history.json",
            "blacklist-operations-history.json",
            "curated external evidence",
        ),
        (
            supply / "treasury-reclaim-inventory.csv",
            "treasury-reclaim-inventory.csv",
            "policy scenario",
        ),
        (
            supply / "treasury-reclaim-inventory-summary.json",
            "treasury-reclaim-inventory-summary.json",
            "policy scenario",
        ),
        (
            cutoff / "cross-shard-supply-cutoff.json",
            "cross-shard-supply-cutoff.json",
            "database-derived",
        ),
        (
            cutoff / "cutoff-reconciliation.verify.json",
            "cutoff-reconciliation.verify.json",
            "database-derived",
        ),
        (
            cutoff / "state" / "actual-supply-cutoff.json",
            "actual-supply-cutoff.json",
            "database-derived",
        ),
        (
            cutoff / "claims" / "actual-supply-ledger-cutoff-summary.json",
            "actual-supply-ledger-cutoff-summary.json",
            "database-derived",
        ),
        (
            cutoff / "interval-audit" / "shard0-summary.json",
            "cutoff-interval-shard0-summary.json",
            "RPC-derived",
        ),
        (
            cutoff / "interval-audit" / "shard1-summary.json",
            "cutoff-interval-shard1-summary.json",
            "RPC-derived",
        ),
        (
            accounting / "historical-exploit-flow-summary.json",
            "historical-exploit-flow-summary.json",
            "RPC-derived",
        ),
    ]

    provenance_notes = {
        "reconciliation.json": "Synthesis of database, RPC, and curated incident evidence; arithmetic is independently checked.",
        "burn-address-audit.json": "Transaction and cutoff-state evidence with curated burn-address classification.",
        "max-rate-opening-payout-audit.json": "Assembled from recorded historical RPC checks; no standalone generator was preserved.",
        "extra-mint-blacklist-burn-path-audit.json": "Assembled from a recorded top-level transaction-history check; no standalone generator was preserved.",
        "wallet-theft-report-coverage.json": "Addresses extracted from named investigation reports; not a legal attribution.",
        "blacklist-operations-history.json": "Git and operations-history extraction; not chain state.",
        "extra-mint-blacklist-reclaim.csv": "Historical allocation-policy scenario; not part of supply arithmetic.",
        "extra-mint-blacklist-reclaim-summary.json": "Historical allocation-policy scenario; not part of supply arithmetic.",
        "treasury-reclaim-inventory.csv": "Historical allocation-policy scenario; not part of supply arithmetic.",
        "treasury-reclaim-inventory-summary.json": "Historical allocation-policy scenario; not part of supply arithmetic.",
    }

    entries = []
    for source, target_name, classification in mappings:
        if not source.is_file():
            raise FileNotFoundError(source)
        target = output / target_name
        if target.exists() or Path(str(target) + ".partial").exists():
            raise FileExistsError(target)
        source_hash = sha256(source)
        if source.suffix == ".json":
            value = normalize(json.loads(source.read_text()))
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object: {source}")
            value["_provenance"] = {
                "classification": classification,
                "source_name": source.name,
                "source_sha256": source_hash,
                "normalization": "absolute machine paths replaced; factual numeric fields unchanged",
                "note": provenance_notes.get(target_name, ""),
            }
            encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
            partial = Path(str(target) + ".partial")
            partial.write_text(encoded)
            os.replace(partial, target)
            row_count = None
        else:
            partial = Path(str(target) + ".partial")
            shutil.copyfile(source, partial)
            os.replace(partial, target)
            row_count = csv_rows(target)
        entries.append(
            {
                "path": target.name,
                "classification": classification,
                "bytes": target.stat().st_size,
                "rows": row_count,
                "sha256": sha256(target),
                "source_sha256": source_hash,
            }
        )

    index = {
        "schema_version": 1,
        "result_set": "2026-09-11",
        "entries": sorted(entries, key=lambda item: item["path"]),
    }
    index_path = output / "index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    print(f"packaged {len(entries)} results in {output}")


if __name__ == "__main__":
    main()
