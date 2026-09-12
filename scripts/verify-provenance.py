#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked_path(relative):
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def verify_findings():
    manifest_path = ROOT / "docs" / "findings" / "SOURCE-HASHES.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = checked_path(item["target"])
        if sha256(path) != item["published_sha256"]:
            raise ValueError(f"published finding hash mismatch: {item['target']}")
    print(f"PASS findings provenance: {len(manifest['files'])} files")


def verify_run_templates():
    directory = ROOT / "repro" / "as-run" / "2026-09-08-11"
    manifest = json.loads(
        (directory / "SOURCE-HASHES.json").read_text(encoding="utf-8")
    )
    for item in manifest["files"]:
        relative = (directory.relative_to(ROOT) / item["file"]).as_posix()
        path = checked_path(relative)
        if sha256(path) != item["sanitized_sha256"]:
            raise ValueError(f"sanitized run-template hash mismatch: {relative}")
    print(f"PASS run-template provenance: {len(manifest['files'])} files")


def main():
    verify_findings()
    verify_run_templates()


if __name__ == "__main__":
    main()
