#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path


FINAL_CLASSIFICATIONS = {
    "rollback_leak",
    "source_debit_absent",
    "valid_source_debit",
    "unclassified",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Summarize final and replay-only cross-shard source "
            "classifications without conflating debit absence with mechanism proof"
        )
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("source_audits", nargs="+")
    return parser.parse_args()


def required(row, names, path):
    for name in names:
        if row.get(name) not in (None, ""):
            return row[name]
    raise KeyError(f"{path}: expected one of {', '.join(names)}")


def file_sha256(path):
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def classify(paths):
    seen = set()
    final = defaultdict(lambda: {"count": 0, "amount_atto": 0})
    for classification in FINAL_CLASSIFICATIONS:
        final[classification]
    replay = defaultdict(lambda: {"count": 0, "amount_atto": 0})
    by_source_shard = defaultdict(
        lambda: defaultdict(lambda: {"count": 0, "amount_atto": 0})
    )
    inputs = []
    for path in paths:
        rows = 0
        with path.open(newline="") as source:
            for row in csv.DictReader(source):
                source_shard = int(
                    required(
                        row,
                        ("audit_source_shard", "signed_source_shard", "source_shard"),
                        path,
                    )
                )
                destination_shard = int(
                    required(
                        row,
                        ("audit_destination_shard", "destination_shard", "to_shard"),
                        path,
                    )
                )
                source_block = int(
                    required(
                        row,
                        ("audit_source_block", "signed_source_block", "source_block"),
                        path,
                    )
                )
                source_block_hash = required(
                    row,
                    (
                        "audit_source_block_hash",
                        "signed_source_header_hash",
                        "source_block_hash",
                        "claimed_source_block_hash",
                    ),
                    path,
                ).lower()
                receipt_index = int(required(row, ("receipt_index",), path))
                tx_hash = required(row, ("tx_hash",), path).lower()
                key = (
                    source_shard,
                    destination_shard,
                    source_block,
                    source_block_hash,
                    receipt_index,
                    tx_hash,
                )
                if key in seen:
                    raise ValueError(f"{path}: duplicate canonical receipt {key}")
                seen.add(key)
                amount = int(required(row, ("amount_atto",), path))
                classification = required(row, ("classification",), path)
                if classification not in FINAL_CLASSIFICATIONS:
                    raise ValueError(
                        f"{path}: unsupported final classification {classification!r}"
                    )
                replay_classification = row.get("replay_classification") or "legacy"
                final[classification]["count"] += 1
                final[classification]["amount_atto"] += amount
                replay[replay_classification]["count"] += 1
                replay[replay_classification]["amount_atto"] += amount
                by_source_shard[source_shard][classification]["count"] += 1
                by_source_shard[source_shard][classification]["amount_atto"] += amount
                rows += 1
        inputs.append(
            {
                "path": str(path),
                "sha256": file_sha256(path),
                "rows": rows,
            }
        )

    def encoded(values):
        return {
            name: {
                "count": value["count"],
                "amount_atto": str(value["amount_atto"]),
            }
            for name, value in sorted(values.items())
        }

    rollback = final["rollback_leak"]["amount_atto"]
    absent = final["source_debit_absent"]["amount_atto"]
    return {
        "schema_version": 1,
        "inputs": inputs,
        "receipts": len(seen),
        "by_final_classification": encoded(final),
        "by_replay_classification": encoded(replay),
        "by_source_shard": {
            str(shard): encoded(values)
            for shard, values in sorted(by_source_shard.items())
        },
        "trace_proven_rollback_leakage_atto": str(rollback),
        "canonical_state_proven_source_debit_absence_atto": str(absent),
        "unbacked_cross_shard_credit_atto": str(rollback + absent),
        "unclassified_atto": str(final["unclassified"]["amount_atto"]),
    }


def write_json(path, value):
    partial = Path(str(path) + ".partial")
    if path.exists() or partial.exists():
        raise FileExistsError(path)
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with partial.open("x", encoding="utf-8") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial, path)


def main():
    args = parse_args()
    paths = [Path(path) for path in args.source_audits]
    result = classify(paths)
    write_json(Path(args.output), result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
