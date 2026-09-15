#!/usr/bin/env python3
"""Optional real-EVM reproduction using an existing Harmony source checkout."""

import argparse
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harmony-source", required=True, type=Path)
    args = parser.parse_args()
    harmony = args.harmony_source.resolve(strict=True)
    target = harmony / "core/vm/zz_supply_audit_review_test.go"
    if target.exists():
        raise FileExistsError(target)
    fixture = (
        Path(__file__).resolve().parents[1]
        / "toolkit/tests/fixtures/cx_constructor_evm_test.go.txt"
    )
    with tempfile.TemporaryDirectory(prefix="cx-constructor-evm-") as directory:
        overlay = Path(directory) / "overlay.json"
        overlay.write_text(json.dumps({"Replace": {str(target): str(fixture)}}))
        try:
            result = subprocess.run(
                ["go", "test", f"-overlay={overlay}", "-run",
                 "^TestSupplyAuditRepeatedCXCall$", "-v", "./core/vm"],
                cwd=harmony, check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as error:
            print(error.stdout, end="")
            print(error.stderr, end="")
            raise
        print(result.stdout, end="")
        trace = next(
            json.loads(line.split("TRACE=", 1)[1])
            for line in result.stdout.splitlines() if "TRACE=" in line
        )
        script = fixture.parents[2] / "scripts/forensics/cx-source-audit.py"
        spec = importlib.util.spec_from_file_location("cx_source_audit", script)
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        observed = audit.inspect_trace(trace, {
            "from": trace["to"].lower(),
            "to": "0x0000000000000000000000000000000000002222",
            "amount_atto": 100,
            "destination_shard": 1,
        })
        expected = {
            "precompile_call_count": 2,
            "completed_precompile_call_count": 1,
            "precompile_payload_match_count": 2,
            "completed_precompile_payload_match_count": 1,
            "failed_precompile_path_count": 0,
            "failed_matching_precompile_path_count": 0,
        }
        if observed != expected:
            raise AssertionError(f"unexpected audit evidence for real EVM trace: {observed}")
        print("PASS real EVM trace: two calls, one completed debit, no reverted debit path")


if __name__ == "__main__":
    main()
