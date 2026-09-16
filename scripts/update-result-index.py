#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build an index for one ignored numerical result set"
    )
    parser.add_argument("--results", required=True)
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def csv_rows(path):
    with path.open(newline="") as source:
        return sum(1 for _ in csv.reader(source)) - 1


def main():
    args = parse_args()
    result_root = Path(args.results)
    if not result_root.is_dir():
        raise FileNotFoundError(result_root)
    entries = []
    for path in sorted(result_root.iterdir()):
        if not path.is_file() or path.name in {"README.md", "index.json"}:
            continue
        if path.suffix == ".json":
            value = json.loads(path.read_text())
            provenance = value.get("_provenance", {})
            classification = provenance.get("classification")
            if not classification:
                raise ValueError(f"{path}: missing provenance classification")
            sources = value.get("sources", provenance)
            rows = None
        elif path.suffix == ".csv":
            raise ValueError(
                f"{path}: CSV classification must be supplied by a packager"
            )
        else:
            raise ValueError(f"{path}: unsupported result file")
        entries.append(
            {
                "path": path.name,
                "classification": classification,
                "bytes": path.stat().st_size,
                "rows": rows,
                "sha256": sha256(path),
                "source_sha256": source_digest(sources),
            }
        )
    index = {
        "schema_version": 1,
        "result_set": result_root.name,
        "entries": entries,
    }
    output = result_root / "index.json"
    partial = Path(str(output) + ".partial")
    if partial.exists():
        raise FileExistsError(partial)
    with partial.open("x", encoding="utf-8") as target:
        json.dump(index, target, indent=2, sort_keys=True)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    os.replace(partial, output)
    print(f"indexed {len(entries)} results in {result_root}")


if __name__ == "__main__":
    main()
