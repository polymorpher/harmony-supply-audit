import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "addresses"
    / "blacklisted-address-audit.py"
)


class BlacklistedAddressAuditTest(unittest.TestCase):
    def test_deduplicates_and_joins_cutoff_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            listed = root / "addresses.txt"
            claims = root / "claims.csv"
            output = root / "audit.csv"
            summary = root / "summary.json"
            present = "one132ggm0mgxdt4l8etud9e5gzpv8psgx30p7hxsq"
            absent = "one1td6g8sh02r7skyqtl46qdlgu0ed5lp259uut7x"
            listed.write_text(f"{present}\n{present}\n{absent}\n")

            components = (
                "liquid_shard0",
                "liquid_shard1",
                "active_staked_or_delegated",
                "pending_undelegation",
                "unclaimed_staking_reward",
                "pending_cross_shard",
                "total_claim",
            )
            fields = [
                "secure_key",
                "address",
                "claims_shard0_block",
                "claims_shard1_block",
                "nonce_shard0",
                "nonce_shard1",
                "code_hash_shard0",
                "code_hash_shard1",
                *(f"{component}_atto" for component in components),
                *(f"{component}_one" for component in components),
            ]
            row = {
                "secure_key": "0x01",
                "address": "0x8a908dbf6833575f9f2be34b9a204161c3041a2f",
                "claims_shard0_block": "93623067",
                "claims_shard1_block": "95882100",
                "nonce_shard0": "1",
                "nonce_shard1": "",
                "code_hash_shard0": "0x00",
                "code_hash_shard1": "",
            }
            for component in components:
                value = 100 if component in ("liquid_shard0", "total_claim") else 0
                row[f"{component}_atto"] = str(value)
                row[f"{component}_one"] = f"0.{value:018d}"
            with claims.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerow(row)

            subprocess.run(
                (
                    sys.executable,
                    str(SCRIPT),
                    "--addresses",
                    str(listed),
                    "--claims",
                    str(claims),
                    "--claims-sha256",
                    "0" * 64,
                    "--csv-output",
                    str(output),
                    "--summary-output",
                    str(summary),
                ),
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(summary.read_text())
            self.assertEqual(result["input_entries"], 3)
            self.assertEqual(result["unique_addresses"], 2)
            self.assertEqual(result["positive_claim_addresses"], 1)
            self.assertEqual(result["zero_or_absent_addresses"], 1)
            self.assertEqual(result["component_totals_atto"]["total_claim"], "100")


if __name__ == "__main__":
    unittest.main()
