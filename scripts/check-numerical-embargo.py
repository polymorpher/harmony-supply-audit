#!/usr/bin/env python3

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_PATHS = (
    "docs/findings/",
    "results/2026-09-11/",
    "embargoed/",
)
SENSITIVE_FILES = {
    "manifests/results.sha256",
    "manifests/releases/2026-09-11.json",
}
TEXT_SUFFIXES = {
    ".csv",
    ".go",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".txt",
    ".yaml",
    ".yml",
}
MONETARY_RESULT = re.compile(
    r"(?:"
    r"\b\d[\d,]*\.\d+\s+ONE\b|"
    r"\b(?:\d{4,}|\d{1,3}(?:,\d{3})+)\s+ONE\b|"
    r"\b\d{20,}\s+atto(?:-ONE)?\b"
    r")",
    re.IGNORECASE,
)
RESULT_JSON_VALUE = re.compile(
    r'"[^"]*(?:atto|amount|balance|claim|payout|reclaim|issuance|supply|gap)[^"]*"'
    r'\s*:\s*"?-?\d{7,}"?',
    re.IGNORECASE,
)


def public_files():
    process = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        item.decode("utf-8")
        for item in process.stdout.split(b"\0")
        if item
    ]


def main():
    files = public_files()
    exposed = [
        relative
        for relative in files
        if relative in SENSITIVE_FILES
        or any(relative.startswith(prefix) for prefix in SENSITIVE_PATHS)
    ]
    if exposed:
        raise ValueError(
            "embargoed files are publishable under current ignore rules: "
            + ", ".join(exposed)
        )

    findings = []
    for relative in files:
        path = ROOT / relative
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if MONETARY_RESULT.search(line):
                findings.append(f"{relative}:{line_number}: monetary result")
            if path.suffix.lower() == ".json" and RESULT_JSON_VALUE.search(line):
                findings.append(f"{relative}:{line_number}: numerical result field")
    if findings:
        raise ValueError(
            "possible numerical result outside embargo:\n" + "\n".join(findings)
        )

    print(f"PASS numerical embargo: {len(files)} publishable files checked")


if __name__ == "__main__":
    main()
