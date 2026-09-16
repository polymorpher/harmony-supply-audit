#!/usr/bin/env python3

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = ROOT / "results"
OUTPUT = ROOT / "manifests" / "results.sha256"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    paths = [RESULTS_ROOT / "README.md"]
    result_sets = 0
    for result_root in sorted(RESULTS_ROOT.glob("20*")):
        index_path = result_root / "index.json"
        if not index_path.is_file():
            continue
        with index_path.open(encoding="utf-8") as source:
            index = json.load(source)
        if index["result_set"] != result_root.name:
            raise ValueError(f"{index_path}: result-set name mismatch")
        paths.extend(result_root / entry["path"] for entry in index["entries"])
        paths.append(index_path)
        readme = result_root / "README.md"
        if readme.is_file():
            paths.append(readme)
        result_sets += 1
    if not result_sets:
        raise ValueError("no dated result sets found")
    rows = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        rows.append(
            (
                path.relative_to(ROOT).as_posix(),
                sha256(path),
                path.stat().st_size,
            )
        )
    rows.sort()
    partial = Path(str(OUTPUT) + ".partial")
    with partial.open("x", encoding="utf-8") as output:
        for path, digest, size in rows:
            output.write(f"{digest}  {size}  {path}\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial, OUTPUT)
    print(f"wrote {len(rows)} entries to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
