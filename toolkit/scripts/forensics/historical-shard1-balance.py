#!/usr/bin/env python3

import argparse
import csv
import json
import os
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Derive a historical shard-1 balance from a measured cutoff "
            "balance and later canonical cross-shard credits and debits"
        )
    )
    parser.add_argument("--cutoff-balance-atto", type=int, required=True)
    parser.add_argument("--checkpoint-block", type=int, required=True)
    parser.add_argument("--cutoff-block", type=int, required=True)
    parser.add_argument(
        "--credits",
        required=True,
        help=(
            "CSV of shard-0-to-shard-1 receipts with destination_block, "
            "destination_shard, and amount_atto"
        ),
    )
    parser.add_argument(
        "--debits",
        required=True,
        help=(
            "audited source CSV with signed_source_block, "
            "signed_source_shard, classification, and amount_atto"
        ),
    )
    parser.add_argument("--expected-balance-atto", type=int)
    parser.add_argument("--output")
    return parser.parse_args()


def integer(row, names, source):
    for name in names:
        if name in row and row[name] != "":
            return int(row[name])
    raise KeyError(f"{source}: expected one of {', '.join(names)}")


def sum_later_credits(path, checkpoint_block, cutoff_block):
    count = 0
    amount = 0
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            if row.get("destination_status") == "not_found":
                continue
            destination_shard = integer(
                row, ("destination_shard", "to_shard"), path
            )
            if destination_shard != 1:
                continue
            destination_block = integer(row, ("destination_block",), path)
            if checkpoint_block < destination_block <= cutoff_block:
                count += 1
                amount += integer(row, ("amount_atto", "value_atto"), path)
    return count, amount


def sum_later_valid_debits(path, checkpoint_block, cutoff_block):
    count = 0
    amount = 0
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            source_shard = integer(
                row, ("signed_source_shard", "source_shard"), path
            )
            if source_shard != 1 or row.get("classification") != "valid_source_debit":
                continue
            source_block = integer(
                row, ("signed_source_block", "source_block"), path
            )
            if checkpoint_block < source_block <= cutoff_block:
                count += 1
                amount += integer(row, ("amount_atto", "value_atto"), path)
    return count, amount


def derive(cutoff_balance, credits, debits):
    result = cutoff_balance - credits + debits
    if result < 0:
        raise ValueError("derived historical balance is negative")
    return result


def write_json(path, value):
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(encoded, end="")
        return
    partial = Path(str(path) + ".partial")
    if partial.exists():
        raise FileExistsError(partial)
    with partial.open("x", encoding="utf-8") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial, path)


def main():
    args = parse_args()
    if args.checkpoint_block >= args.cutoff_block:
        raise ValueError("checkpoint block must be below cutoff block")
    credits_path = Path(args.credits)
    debits_path = Path(args.debits)
    credit_count, credits = sum_later_credits(
        credits_path, args.checkpoint_block, args.cutoff_block
    )
    debit_count, debits = sum_later_valid_debits(
        debits_path, args.checkpoint_block, args.cutoff_block
    )
    historical = derive(args.cutoff_balance_atto, credits, debits)
    if (
        args.expected_balance_atto is not None
        and historical != args.expected_balance_atto
    ):
        raise ValueError(
            f"derived balance {historical} != expected "
            f"{args.expected_balance_atto}"
        )
    result = {
        "schema_version": 1,
        "checkpoint_block": args.checkpoint_block,
        "cutoff_block": args.cutoff_block,
        "cutoff_balance_atto": str(args.cutoff_balance_atto),
        "later_shard0_to_shard1_credit_count": credit_count,
        "later_shard0_to_shard1_credits_atto": str(credits),
        "later_valid_shard1_to_shard0_debit_count": debit_count,
        "later_valid_shard1_to_shard0_debits_atto": str(debits),
        "derived_historical_balance_atto": str(historical),
        "formula": (
            "cutoff balance - later shard0-to-shard1 credits "
            "+ later valid shard1-to-shard0 debits"
        ),
        "classification_limit": (
            "the debit adjustment depends on the source-audit "
            "valid_source_debit classification"
        ),
        "inputs": {
            "credits": str(credits_path),
            "debits": str(debits_path),
        },
    }
    write_json(Path(args.output) if args.output else None, result)


if __name__ == "__main__":
    main()
