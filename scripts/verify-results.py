#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
from pathlib import Path


def parse_args():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Verify committed compact results")
    parser.add_argument("--results", default=str(root / "results" / "2026-09-11"))
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_rows(path):
    with path.open(newline="") as source:
        return sum(1 for _ in csv.reader(source)) - 1


def main():
    args = parse_args()
    root = Path(args.results)
    with (root / "index.json").open(encoding="utf-8") as source:
        index = json.load(source)
    if index["schema_version"] != 1:
        raise ValueError("unsupported result index schema")

    indexed = set()
    for entry in index["entries"]:
        path = root / entry["path"]
        if not path.is_file():
            raise FileNotFoundError(path)
        indexed.add(path.name)
        if path.stat().st_size != entry["bytes"]:
            raise ValueError(f"size mismatch: {path}")
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"hash mismatch: {path}")
        if entry["rows"] is not None and csv_rows(path) != entry["rows"]:
            raise ValueError(f"row-count mismatch: {path}")

    actual = {path.name for path in root.iterdir() if path.is_file()}
    unexpected = actual - indexed - {"index.json", "README.md"}
    if unexpected:
        raise ValueError(f"unindexed result files: {sorted(unexpected)}")

    repository = Path(__file__).resolve().parents[1]
    manifest_path = repository / "manifests" / "results.sha256"
    manifested = 0
    with manifest_path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            digest, size, relative = line.rstrip("\n").split("  ", 2)
            path = repository / relative
            if not path.is_file():
                raise FileNotFoundError(path)
            if path.stat().st_size != int(size):
                raise ValueError(f"manifest size mismatch at line {line_number}")
            if sha256(path) != digest:
                raise ValueError(f"manifest hash mismatch at line {line_number}")
            manifested += 1
    print(f"PASS compact results: {len(indexed)} indexed, {manifested} manifested")


if __name__ == "__main__":
    main()
