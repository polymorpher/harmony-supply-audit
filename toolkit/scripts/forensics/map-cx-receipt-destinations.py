#!/usr/bin/env python3

import argparse
import csv
import json
import os
import time
import urllib.request
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Map canonical outgoing cross-shard receipts to destination "
            "blocks through hmyv2_getCXReceiptByHash"
        )
    )
    parser.add_argument("--rpc", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--destination-shard", type=int, required=True)
    parser.add_argument("--minimum-source-block", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--allow-missing", action="store_true")
    return parser.parse_args()


def required(row, names, path):
    for name in names:
        if name in row and row[name] != "":
            return row[name]
    raise KeyError(f"{path}: expected one of {', '.join(names)}")


def rpc_batch(url, requests, timeout, retries):
    body = json.dumps(requests).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                value = json.load(response)
            if not isinstance(value, list):
                raise ValueError(f"expected batch response, got {value!r}")
            return value
        except Exception:
            if attempt + 1 == retries:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def selected_rows(path, destination_shard, minimum_source_block):
    rows = []
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            shard = int(required(row, ("destination_shard", "to_shard"), path))
            block = int(required(row, ("source_block",), path))
            if shard != destination_shard or block < minimum_source_block:
                continue
            rows.append(
                {
                    "tx_hash": required(
                        row, ("tx_hash", "receipt_tx_hash"), path
                    ).lower(),
                    "source_block": block,
                    "destination_shard": shard,
                    "amount_atto": required(
                        row, ("amount_atto", "value_atto"), path
                    ),
                }
            )
    return rows


def write_rows(path, rows):
    partial = Path(str(path) + ".partial")
    if path.exists() or partial.exists():
        raise FileExistsError(path)
    fields = (
        "tx_hash",
        "source_block",
        "destination_shard",
        "amount_atto",
        "destination_status",
        "destination_block",
        "destination_block_hash",
    )
    with partial.open("x", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial, path)


def main():
    args = parse_args()
    if args.batch_size <= 0 or args.retries <= 0:
        raise ValueError("batch size and retries must be positive")
    input_path = Path(args.input)
    output_path = Path(args.output)
    rows = selected_rows(
        input_path, args.destination_shard, args.minimum_source_block
    )
    mapped = []
    missing = []
    for start in range(0, len(rows), args.batch_size):
        chunk = rows[start : start + args.batch_size]
        requests = [
            {
                "jsonrpc": "2.0",
                "id": start + index,
                "method": "hmyv2_getCXReceiptByHash",
                "params": [row["tx_hash"]],
            }
            for index, row in enumerate(chunk)
        ]
        response = rpc_batch(
            args.rpc, requests, args.timeout, args.retries
        )
        by_id = {item["id"]: item for item in response}
        for index, row in enumerate(chunk):
            item = by_id[start + index]
            if item.get("error"):
                raise RuntimeError(item["error"])
            receipt = item.get("result")
            result = dict(row)
            if receipt is None:
                result.update(
                    {
                        "destination_status": "not_found",
                        "destination_block": "",
                        "destination_block_hash": "",
                    }
                )
                missing.append(row["tx_hash"])
            else:
                if receipt["hash"].lower() != row["tx_hash"]:
                    raise ValueError(f"hash mismatch for {row['tx_hash']}")
                if int(receipt["value"]) != int(row["amount_atto"]):
                    raise ValueError(f"value mismatch for {row['tx_hash']}")
                result.update(
                    {
                        "destination_status": "applied",
                        "destination_block": int(receipt["blockNumber"]),
                        "destination_block_hash": receipt.get("blockHash", ""),
                    }
                )
            mapped.append(result)
    if missing and not args.allow_missing:
        raise ValueError(
            f"{len(missing)} destination receipts not found; rerun with "
            "--allow-missing only when missing receipts are intentionally "
            "kept outside the historical balance derivation"
        )
    write_rows(output_path, mapped)
    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output_path),
                "mapped": len(mapped) - len(missing),
                "missing": len(missing),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
