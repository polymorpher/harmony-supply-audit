#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
from pathlib import Path


def parse_args():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Verify committed compact results")
    parser.add_argument("--results-root", default=str(root / "results"))
    parser.add_argument(
        "--results",
        action="append",
        help="verify only this dated result directory; may be repeated",
    )
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
    repository = Path(__file__).resolve().parents[1]
    results_root = Path(args.results_root).resolve()
    result_directories = (
        [Path(path).resolve() for path in args.results]
        if args.results
        else sorted(
            path
            for path in results_root.glob("20*")
            if (path / "index.json").is_file()
        )
    )
    if not result_directories:
        raise ValueError("no dated result sets found")

    total_indexed = 0
    expected_manifest = {results_root / "README.md"}
    for root in result_directories:
        with (root / "index.json").open(encoding="utf-8") as source:
            index = json.load(source)
        if index["schema_version"] != 1:
            raise ValueError(f"{root}: unsupported result index schema")
        if index["result_set"] != root.name:
            raise ValueError(f"{root}: result-set name mismatch")

        indexed = set()
        for entry in index["entries"]:
            path = root / entry["path"]
            if not path.is_file():
                raise FileNotFoundError(path)
            indexed.add(path.name)
            expected_manifest.add(path)
            if path.stat().st_size != entry["bytes"]:
                raise ValueError(f"size mismatch: {path}")
            if sha256(path) != entry["sha256"]:
                raise ValueError(f"hash mismatch: {path}")
            if entry["rows"] is not None and csv_rows(path) != entry["rows"]:
                raise ValueError(f"row-count mismatch: {path}")

        actual = {path.name for path in root.iterdir() if path.is_file()}
        unexpected = actual - indexed - {"index.json", "README.md"}
        if unexpected:
            raise ValueError(f"{root}: unindexed result files: {sorted(unexpected)}")
        expected_manifest.add(root / "index.json")
        if (root / "README.md").is_file():
            expected_manifest.add(root / "README.md")
        total_indexed += len(indexed)

    manifest_path = repository / "manifests" / "results.sha256"
    manifested = 0
    manifested_paths = set()
    with manifest_path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            digest, size, relative = line.rstrip("\n").split("  ", 2)
            path = repository / relative
            manifested_paths.add(path)
            if not path.is_file():
                raise FileNotFoundError(path)
            if path.stat().st_size != int(size):
                raise ValueError(f"manifest size mismatch at line {line_number}")
            if sha256(path) != digest:
                raise ValueError(f"manifest hash mismatch at line {line_number}")
            manifested += 1
    if manifested_paths != expected_manifest:
        missing = sorted(str(path) for path in expected_manifest - manifested_paths)
        extra = sorted(str(path) for path in manifested_paths - expected_manifest)
        raise ValueError(f"result manifest mismatch: missing={missing} extra={extra}")
    print(
        f"PASS compact results: {len(result_directories)} sets, "
        f"{total_indexed} indexed, {manifested} manifested"
    )


if __name__ == "__main__":
    main()
