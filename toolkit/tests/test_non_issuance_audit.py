import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "toolkit"
    / "scripts"
    / "addresses"
    / "build-non-issuance-audit.py"
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load_module("non_issuance_audit", SCRIPT)
blacklist = load_module(
    "blacklist_audit",
    ROOT
    / "toolkit"
    / "scripts"
    / "addresses"
    / "blacklisted-address-audit.py",
)


def write_csv(path, fields, rows):
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class NonIssuanceAuditTest(unittest.TestCase):
    def test_bech32_round_trip(self):
        address = "0x0000000000000000000000000000000000000002"
        encoded = audit.to_bech32(address)
        self.assertEqual(blacklist.decode_bech32(encoded), address)

    def test_combines_existing_and_retained_without_treasury(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "existing.csv"
            retained = root / "retained.csv"
            retained_summary = root / "retained-summary.json"
            claim_summary = root / "claim-summary.json"
            output = root / "output.csv"
            summary = root / "summary.json"
            (root / "raw").mkdir()
            (root / "raw" / "example.json").write_text("{}\n")

            write_csv(
                existing,
                (
                    "address_hex",
                    "category",
                    "not_issued_atto",
                    "cutoff_claim_atto",
                ),
                [
                    {
                        "address_hex": "0x0000000000000000000000000000000000000001",
                        "category": "inaccessible",
                        "not_issued_atto": "10",
                        "cutoff_claim_atto": "10",
                    }
                ],
            )
            write_csv(
                retained,
                (
                    "incident",
                    "address",
                    "initial_amount_atto",
                    "cutoff_block",
                    "cutoff_balance_atto",
                    "rpc_block",
                    "rpc_balance_atto",
                    "rpc_retained_cap_atto",
                    "balance_changed_from_sep10",
                    "raw_file",
                ),
                [
                    {
                        "incident": "april-2026",
                        "address": "0x0000000000000000000000000000000000000002",
                        "initial_amount_atto": "100",
                        "cutoff_block": "50",
                        "cutoff_balance_atto": "80",
                        "rpc_block": "51",
                        "rpc_balance_atto": "80",
                        "rpc_retained_cap_atto": "80",
                        "balance_changed_from_sep10": "false",
                        "raw_file": "raw/example.json",
                    }
                ],
            )
            retained_summary.write_text(
                json.dumps(
                    {
                        "block": 51,
                        "block_hash": "0xabc",
                        "block_utc": "example",
                        "queried_at_utc": "example",
                        "changed_from_sep10": 0,
                        "incidents": {
                            "april-2026": {
                                "addresses": 1,
                                "retained_cap_atto": "80",
                                "above_1000_one": 0,
                            }
                        },
                    }
                )
            )
            claim_summary.write_text(json.dumps({"total_claim_atto": "200"}))

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--existing-non-issuance",
                    str(existing),
                    "--retained-balances",
                    str(retained),
                    "--retained-summary",
                    str(retained_summary),
                    "--cutoff-claim-summary",
                    str(claim_summary),
                    "--output-csv",
                    str(output),
                    "--summary-output",
                    str(summary),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(summary.read_text())
            self.assertEqual(result["totals"]["not_issued_atto"], "90")
            self.assertEqual(
                result["totals"]["remaining_full_claim_after_non_issuance_atto"],
                "110",
            )
            self.assertIsNone(result["policy"]["treasury_destination"])
            self.assertFalse(result["policy"]["available_for_other_use"])


if __name__ == "__main__":
    unittest.main()
