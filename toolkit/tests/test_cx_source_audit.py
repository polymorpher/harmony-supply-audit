import contextlib
import copy
import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "toolkit/scripts/forensics/cx-source-audit.py"
SPEC = importlib.util.spec_from_file_location("cx_source_audit", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
TX_HASH = "0x" + "11" * 32
ORIGIN = "0x0000000000000000000000000000000000001111"
CONSTRUCTOR = "0xff9fa8f363f78f9f5658971a4f357ad95130d1f5"
RECIPIENT = "0x0000000000000000000000000000000000002222"
INPUT = (
    "0x28480800"
    + f"{100:064x}"
    + RECIPIENT[2:].zfill(64)
    + f"{1:064x}"
)


def constructor_trace():
    # Reduced from Harmony's real callTracer output for a successful CREATE:
    # CALL f9(value=100), POP, CALL f9(value=0), POP, STOP. Constructors have
    # no installed runtime code, so the first call passes the contract guard.
    # The legacy JS tracer reports the rejected duplicate as internal failure.
    first = {
        "type": "CALL", "from": CONSTRUCTOR, "to": audit.CX_PRECOMPILE,
        "value": "0x64", "input": INPUT, "output": "0x",
    }
    second = {**first, "value": "0x0", "error": "internal failure"}
    second.pop("output")
    return {
        "type": "CREATE", "from": ORIGIN, "to": CONSTRUCTOR,
        "value": "0x64", "output": "0x", "calls": [first, second],
    }


class CXSourceAuditTest(unittest.TestCase):
    def run_audit(self, trace, transaction_updates=None, receipt_status=None):
        transaction = {
            "hash": TX_HASH, "ethHash": TX_HASH, "from": ORIGIN, "to": None,
            "shardID": 0, "toShardID": 0, "value": 100, "input": "0x",
        }
        transaction.update(transaction_updates or {})

        def rpc(url, method, params):
            if method == "hmyv2_getTransactionByHash":
                return transaction
            if trace is None:
                self.fail(f"direct source path unexpectedly requested {method}")
            return {
                "hmyv2_getTransactionReceipt": {
                    "status": int(not trace.get("error")) if receipt_status is None else receipt_status
                },
                "debug_traceTransaction": trace,
            }[method]

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "receipts.csv"
            output = Path(directory) / "audit.csv"
            receipt = {
                "source_shard": 0, "destination_shard": 1, "source_block": 10,
                "tx_hash": TX_HASH, "from": CONSTRUCTOR, "to": RECIPIENT,
                "amount_atto": 100,
            }
            with source.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(receipt))
                writer.writeheader()
                writer.writerow(receipt)
            stdout = io.StringIO()
            with patch.object(audit, "rpc", rpc), patch.object(
                sys, "argv", [str(SCRIPT), "--rpc", "offline://fixture",
                              "--output", str(output), str(source)]
            ), contextlib.redirect_stdout(stdout):
                audit.main()
            with output.open(newline="") as handle:
                row = next(csv.DictReader(handle))
            return row, json.loads(stdout.getvalue().splitlines()[-1])

    def test_successful_constructor_with_rejected_duplicate(self):
        row, totals = self.run_audit(constructor_trace())
        self.assertEqual(row["classification"], "valid_source_debit")
        self.assertEqual(row["precompile_call_count"], "2")
        self.assertEqual(row["failed_precompile_path_count"], "0")
        self.assertEqual(totals["valid_source_debit_atto"], "100")
        self.assertEqual(totals["rollback_leak_atto"], "0")

    def test_reverted_constructor_with_completed_call(self):
        trace = constructor_trace()
        trace["error"] = "execution reverted"
        row, totals = self.run_audit(trace)
        self.assertEqual(row["classification"], "rollback_leak")
        self.assertEqual(row["failed_precompile_path_count"], "1")
        self.assertEqual(totals["rollback_leak_atto"], "100")

    def test_rejected_call_alone_does_not_prove_a_debit(self):
        for root_error in (None, "execution reverted"):
            with self.subTest(root_error=root_error):
                trace = constructor_trace()
                trace["calls"] = trace["calls"][1:]
                if root_error:
                    trace["error"] = root_error
                row, totals = self.run_audit(trace)
                self.assertEqual(row["classification"], "unclassified")
                self.assertEqual(totals["unclassified_atto"], "100")

    def test_reverted_nested_frame(self):
        trace = constructor_trace()
        trace["calls"] = [{"type": "CALL", "error": "execution reverted",
                           "calls": trace["calls"]}]
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "rollback_leak")

    def test_multiple_completed_calls_are_ambiguous(self):
        trace = constructor_trace()
        trace["calls"][1] = copy.deepcopy(trace["calls"][0])
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "unclassified")

    def test_single_completed_call_and_unrelated_error(self):
        trace = constructor_trace()
        trace["calls"][1]["to"] = RECIPIENT
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "valid_source_debit")

    def test_no_precompile_call(self):
        row, _ = self.run_audit({"type": "CREATE"})
        self.assertEqual(row["classification"], "unclassified")

    def test_selfdestruct_to_precompile_is_not_an_invocation(self):
        trace = constructor_trace()
        trace["calls"][1] = {
            "type": "SELFDESTRUCT", "from": CONSTRUCTOR,
            "to": audit.CX_PRECOMPILE, "value": "0x64",
        }
        trace["error"] = "execution reverted"
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "rollback_leak")
        self.assertEqual(row["precompile_call_count"], "1")
        self.assertEqual(row["completed_precompile_call_count"], "1")

    def test_selfdestruct_alone_does_not_prove_a_cross_shard_debit(self):
        trace = {"type": "CALL", "error": "execution reverted", "calls": [
            {"type": "SELFDESTRUCT", "to": audit.CX_PRECOMPILE, "value": "0x64"}
        ]}
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "unclassified")

    def test_replay_status_must_match_stored_receipt(self):
        for root_error, status in (("out of gas", 1), (None, 0)):
            with self.subTest(root_error=root_error, receipt_status=status):
                trace = constructor_trace()
                if root_error:
                    trace["error"] = root_error
                row, totals = self.run_audit(trace, receipt_status=status)
                self.assertEqual(row["classification"], "unclassified")
                self.assertEqual(totals["unclassified_atto"], "100")

    def test_direct_source_paths_remain_untraced(self):
        for update in ({"to": audit.CX_PRECOMPILE}, {"toShardID": 1}):
            with self.subTest(update=update):
                row, _ = self.run_audit(None, update)
                self.assertEqual(row["classification"], "valid_source_debit")
                self.assertEqual(row["completed_precompile_call_count"], "")
