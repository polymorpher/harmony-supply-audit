import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "addresses" / "build-revert-leak-retention.py"
A, B, C, D = (f"0x{n:040x}" for n in (0xA, 0xB, 0xC, 0xD))


def write(path, fields, rows):
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class RevertLeakRetentionTest(unittest.TestCase):
    def test_withholds_credit_capped_at_remaining_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipts = root / "receipts.csv"
            receipt_fields = ("tx_hash", "receipt_index", "destination_block", "to", "amount_atto",
                              "source_transaction_hash", "classification")
            write(receipts, receipt_fields, [
                # only exploit credit: the whole claim goes
                {"tx_hash": "0x01", "receipt_index": "0", "destination_block": "1", "to": A,
                 "amount_atto": "500", "source_transaction_hash": "0xs1", "classification": "rollback_leak"},
                # the same receipt listed twice counts once
                {"tx_hash": "0x01", "receipt_index": "0", "destination_block": "1", "to": A,
                 "amount_atto": "500", "source_transaction_hash": "0xs1", "classification": "rollback_leak"},
                # mixed funds: only the credit goes
                {"tx_hash": "0x02", "receipt_index": "0", "destination_block": "2", "to": B,
                 "amount_atto": "30", "source_transaction_hash": "0xs2", "classification": "source_debit_absent"},
                # already partly deducted: only what is left can go
                {"tx_hash": "0x03", "receipt_index": "0", "destination_block": "3", "to": C,
                 "amount_atto": "1000", "source_transaction_hash": "0xs3", "classification": "rollback_leak"},
                # a valid receipt is not exploit credit
                {"tx_hash": "0x04", "receipt_index": "0", "destination_block": "4", "to": D,
                 "amount_atto": "70", "source_transaction_hash": "0xs4", "classification": "valid_source_debit"},
            ])
            transactions = root / "transactions.csv"
            write(transactions, ("transaction_hash", "incident"), [
                {"transaction_hash": "0xs1", "incident": "smaller-2026"},
                {"transaction_hash": "0xs2", "incident": "smaller-2026"},
                {"transaction_hash": "0xs3", "incident": "april-2026"},
            ])
            claims = root / "claims.csv"
            write(claims, ("address", "native_total_claim_atto"), [
                {"address": A, "native_total_claim_atto": "200"},
                {"address": B, "native_total_claim_atto": "100"},
                {"address": C, "native_total_claim_atto": "90"},
                {"address": D, "native_total_claim_atto": "70"},
            ])
            prior = root / "prior.csv"
            write(prior, ("address_hex", "retained_cap_atto"), [{"address_hex": C, "retained_cap_atto": "40"}])
            output = root / "out.csv"
            summary = root / "summary.json"
            subprocess.run(
                [sys.executable, str(SCRIPT), "--receipt-audit", str(receipts), "--exploit-transactions",
                 str(transactions), "--claims", str(claims), "--prior-retention", str(prior),
                 "--output-csv", str(output), "--summary-output", str(summary)],
                check=True, capture_output=True, text=True,
            )
            rows = {row["address_hex"]: row for row in csv.DictReader(output.open())}
            self.assertEqual({a: rows[a]["retained_cap_atto"] for a in rows}, {A: "200", B: "30", C: "50"})
            self.assertEqual(rows[A]["incident"], "june-july-2026")
            self.assertEqual(rows[C]["prior_non_issuance_atto"], "40")
            result = json.loads(summary.read_text())
            self.assertEqual(result["leak_receipts"], 3)
            self.assertEqual(result["unbacked_credit_atto"], "1530")
            self.assertEqual(result["not_issued_atto"], "280")


if __name__ == "__main__":
    unittest.main()
