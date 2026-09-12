#!/usr/bin/env python3

import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "results" / "2026-09-11"
OUTPUT = ROOT / "manifests" / "results.sha256"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    with (RESULT_ROOT / "index.json").open(encoding="utf-8") as source:
        index = json.load(source)
    paths = [RESULT_ROOT / entry["path"] for entry in index["entries"]]
    paths.extend((RESULT_ROOT / "index.json", RESULT_ROOT.parent / "README.md"))
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
