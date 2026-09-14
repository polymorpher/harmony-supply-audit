import contextlib
import copy
import csv
import hashlib
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
BLOCK_HASH = "0x" + "22" * 32
ORIGIN = "0x0000000000000000000000000000000000001111"
CONSTRUCTOR = "0xff9fa8f363f78f9f5658971a4f357ad95130d1f5"
RECIPIENT = "0x0000000000000000000000000000000000002222"


def cx_input(amount=100, recipient=RECIPIENT, destination_shard=1):
    return (
        "0x28480800"
        + f"{amount:064x}"
        + recipient[2:].zfill(64)
        + f"{destination_shard:064x}"
    )


INPUT = cx_input()


def dirty_padding_input():
    raw = bytearray.fromhex(INPUT[2:])
    raw[36:48] = b"\xff" * 12
    raw[68:96] = b"\xff" * 28
    return "0x" + raw.hex()


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
    def run_audit(
        self,
        trace,
        transaction_updates=None,
        receipt_updates=None,
        receipt_status=None,
        evidence_status=None,
        evidence_updates=None,
    ):
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
            evidence = Path(directory) / "evidence.csv"
            evidence_artifact = Path(directory) / "evidence-artifact.json"
            receipt = {
                "source_shard": 0, "destination_shard": 1, "source_block": 10,
                "source_block_hash": BLOCK_HASH, "receipt_index": 0,
                "tx_hash": TX_HASH, "from": CONSTRUCTOR, "to": RECIPIENT,
                "amount_atto": 100,
            }
            receipt.update(receipt_updates or {})
            with source.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(receipt))
                writer.writeheader()
                writer.writerow(receipt)
            argv = [
                str(SCRIPT), "--rpc", "offline://fixture",
                "--output", str(output),
            ]
            if evidence_status is not None:
                evidence_artifact.write_text('{"verified":true}\n')
                evidence_row = {
                    "source_shard": 0,
                    "destination_shard": 1,
                    "source_block": 10,
                    "source_block_hash": BLOCK_HASH,
                    "receipt_index": 0,
                    "receipt_tx_hash": TX_HASH,
                    "from": receipt["from"],
                    "to": receipt["to"],
                    "amount_atto": receipt["amount_atto"],
                    "source_debit_status": evidence_status,
                    "evidence_type": "canonical_state_delta",
                    "evidence_reference": evidence_artifact.name,
                    "evidence_sha256": hashlib.sha256(
                        evidence_artifact.read_bytes()
                    ).hexdigest(),
                }
                evidence_row.update(evidence_updates or {})
                with evidence.open("w", newline="") as handle:
                    writer = csv.DictWriter(
                        handle, fieldnames=list(evidence_row)
                    )
                    writer.writeheader()
                    writer.writerow(evidence_row)
                argv.extend(["--independent-evidence", str(evidence)])
            argv.append(str(source))
            stdout = io.StringIO()
            with patch.object(audit, "rpc", rpc), patch.object(
                sys, "argv", argv
            ), contextlib.redirect_stdout(stdout):
                audit.main()
            with output.open(newline="") as handle:
                row = next(csv.DictReader(handle))
            return row, json.loads(stdout.getvalue().splitlines()[-1])

    def test_receipt_identity_requires_explicit_shards(self):
        row = {
            "source_block": "10",
            "tx_hash": TX_HASH,
            "from": CONSTRUCTOR,
            "to": RECIPIENT,
            "amount_atto": "100",
        }
        with self.assertRaises(KeyError):
            audit.receipt_identity(row)

    def test_successful_constructor_with_rejected_duplicate(self):
        row, totals = self.run_audit(constructor_trace())
        self.assertEqual(row["classification"], "valid_source_debit")
        self.assertEqual(row["replay_classification"], "valid_source_debit")
        self.assertEqual(row["classification_source"], "compatible_replay")
        self.assertEqual(row["precompile_call_count"], "2")
        self.assertEqual(row["completed_precompile_call_count"], "1")
        self.assertEqual(row["completed_precompile_payload_match_count"], "1")
        self.assertEqual(row["failed_precompile_path_count"], "0")
        self.assertEqual(totals["valid_source_debit_atto"], "100")
        self.assertEqual(totals["rollback_leak_atto"], "0")
        self.assertEqual(totals["replay_valid_source_debit_atto"], "100")

    def test_failed_root_cannot_prove_a_canonical_outgoing_receipt(self):
        trace = constructor_trace()
        trace["error"] = "execution reverted"
        row, totals = self.run_audit(trace)
        self.assertEqual(row["classification"], "unclassified")
        self.assertEqual(row["replay_classification"], "replay_incompatible")
        self.assertEqual(row["failed_precompile_path_count"], "0")
        self.assertEqual(totals["unclassified_atto"], "100")
        self.assertEqual(totals["replay_incompatible_atto"], "100")

    def test_rejected_call_alone_does_not_prove_a_debit(self):
        trace = constructor_trace()
        trace["calls"] = trace["calls"][1:]
        row, totals = self.run_audit(trace)
        self.assertEqual(row["classification"], "unclassified")
        self.assertEqual(row["replay_classification"], "unclassified")
        self.assertEqual(row["completed_precompile_call_count"], "0")
        self.assertEqual(totals["unclassified_atto"], "100")

    def test_reverted_nested_frame(self):
        trace = constructor_trace()
        trace["calls"] = [{"type": "CALL", "error": "execution reverted",
                           "calls": trace["calls"]}]
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "rollback_leak")
        self.assertEqual(row["replay_classification"], "rollback_leak")
        self.assertEqual(row["failed_precompile_path_count"], "1")
        self.assertEqual(row["failed_matching_precompile_path_count"], "1")

    def test_multiple_completed_calls_are_ambiguous(self):
        trace = constructor_trace()
        trace["calls"][1] = copy.deepcopy(trace["calls"][0])
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "unclassified")
        self.assertEqual(row["completed_precompile_call_count"], "2")

    def test_single_completed_call_and_unrelated_error(self):
        trace = constructor_trace()
        trace["calls"][1]["to"] = RECIPIENT
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "valid_source_debit")

    def test_no_precompile_call(self):
        row, _ = self.run_audit({"type": "CREATE"})
        self.assertEqual(row["classification"], "unclassified")
        self.assertEqual(row["replay_compatible"], "True")

    def test_selfdestruct_to_precompile_is_not_an_invocation(self):
        trace = constructor_trace()
        trace["calls"][1] = {
            "type": "SELFDESTRUCT", "from": CONSTRUCTOR,
            "to": audit.CX_PRECOMPILE, "value": "0x64",
        }
        trace["calls"] = [{
            "type": "CALL",
            "error": "execution reverted",
            "calls": trace["calls"],
        }]
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "rollback_leak")
        self.assertEqual(row["precompile_call_count"], "1")
        self.assertEqual(row["completed_precompile_call_count"], "1")

    def test_selfdestruct_alone_does_not_prove_a_cross_shard_debit(self):
        trace = {"type": "CALL", "calls": [
            {"type": "SELFDESTRUCT", "to": audit.CX_PRECOMPILE, "value": "0x64"}
        ]}
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "unclassified")
        self.assertEqual(row["precompile_call_count"], "0")

    def test_replay_status_must_match_stored_receipt(self):
        for root_error, status in (("out of gas", 1), (None, 0)):
            with self.subTest(root_error=root_error, receipt_status=status):
                trace = constructor_trace()
                if root_error:
                    trace["error"] = root_error
                row, totals = self.run_audit(trace, receipt_status=status)
                self.assertEqual(row["classification"], "unclassified")
                self.assertEqual(
                    row["replay_classification"], "replay_incompatible"
                )
                self.assertEqual(totals["unclassified_atto"], "100")

    def test_completed_call_payload_must_match_receipt(self):
        mismatches = (
            cx_input(amount=101),
            cx_input(recipient=ORIGIN),
            cx_input(destination_shard=2),
            "0xdeadbeef",
        )
        for call_input in mismatches:
            with self.subTest(call_input=call_input):
                trace = constructor_trace()
                trace["calls"][0]["input"] = call_input
                row, _ = self.run_audit(trace)
                self.assertEqual(row["classification"], "unclassified")
                self.assertEqual(
                    row["completed_precompile_payload_match_count"], "0"
                )
                self.assertIn(
                    "does not authenticate", row["replay_issue"]
                )

    def test_completed_call_sender_context_must_match_receipt(self):
        trace = constructor_trace()
        trace["calls"][0]["from"] = ORIGIN
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "unclassified")
        self.assertEqual(row["completed_precompile_payload_match_count"], "0")

    def test_payload_matches_harmony_dirty_padding_semantics(self):
        trace = constructor_trace()
        trace["calls"][0]["input"] = dirty_padding_input()
        row, _ = self.run_audit(trace)
        self.assertEqual(row["classification"], "valid_source_debit")
        self.assertEqual(row["completed_precompile_payload_match_count"], "1")

    def test_delegatecall_preserves_effective_sender_context(self):
        trace = {
            "type": "CALL",
            "from": ORIGIN,
            "to": CONSTRUCTOR,
            "calls": [{
                "type": "DELEGATECALL",
                "from": CONSTRUCTOR,
                "to": "0x0000000000000000000000000000000000003333",
                "calls": [{
                    "type": "DELEGATECALL",
                    "from": CONSTRUCTOR,
                    "to": audit.CX_PRECOMPILE,
                    "input": INPUT,
                }],
            }],
        }
        row, _ = self.run_audit(
            trace, receipt_updates={"from": ORIGIN}
        )
        self.assertEqual(row["classification"], "valid_source_debit")
        self.assertEqual(row["completed_precompile_payload_match_count"], "1")

    def test_absent_debit_evidence_does_not_overclaim_rollback_mechanism(self):
        trace = constructor_trace()
        trace["error"] = "out of gas"
        row, totals = self.run_audit(
            trace, receipt_status=1, evidence_status="absent"
        )
        self.assertEqual(row["replay_classification"], "replay_incompatible")
        self.assertEqual(row["classification"], "source_debit_absent")
        self.assertEqual(
            row["classification_source"], "independent_source_debit_evidence"
        )
        self.assertEqual(
            row["independent_evidence_classification"], "source_debit_absent"
        )
        self.assertEqual(totals["source_debit_absent_atto"], "100")
        self.assertEqual(totals["replay_incompatible_atto"], "100")
        self.assertEqual(totals["independent_evidence_receipts"], 1)

    def test_absent_debit_evidence_agrees_with_trace_proven_rollback(self):
        trace = constructor_trace()
        trace["calls"] = [{
            "type": "CALL",
            "error": "execution reverted",
            "calls": trace["calls"],
        }]
        row, totals = self.run_audit(trace, evidence_status="absent")
        self.assertEqual(row["replay_classification"], "rollback_leak")
        self.assertEqual(row["classification"], "rollback_leak")
        self.assertEqual(
            row["classification_source"],
            "compatible_replay_and_independent_evidence",
        )
        self.assertEqual(
            row["independent_evidence_classification"],
            "source_debit_absent",
        )
        self.assertEqual(totals["rollback_leak_atto"], "100")

    def test_independent_persisted_debit_evidence(self):
        trace = constructor_trace()
        trace["error"] = "out of gas"
        row, _ = self.run_audit(
            trace, receipt_status=1, evidence_status="persisted"
        )
        self.assertEqual(row["classification"], "valid_source_debit")
        self.assertEqual(
            row["classification_source"], "independent_source_debit_evidence"
        )

    def test_conflicting_independent_evidence_aborts(self):
        with self.assertRaisesRegex(
            ValueError, "independent source-debit evidence conflicts"
        ):
            self.run_audit(constructor_trace(), evidence_status="absent")

    def test_evidence_cannot_override_failed_stored_receipt(self):
        trace = constructor_trace()
        trace["error"] = "execution reverted"
        with self.assertRaisesRegex(
            ValueError, "cannot override a failed stored source transaction"
        ):
            self.run_audit(
                trace, receipt_status=0, evidence_status="absent"
            )

    def test_invalid_independent_evidence_digest_aborts(self):
        with self.assertRaisesRegex(ValueError, "not a SHA-256 digest"):
            self.run_audit(
                constructor_trace(),
                evidence_status="persisted",
                evidence_updates={"evidence_sha256": "invalid"},
            )

    def test_invalid_independent_evidence_hash_aborts(self):
        with self.assertRaisesRegex(ValueError, "not a transaction hash"):
            self.run_audit(
                constructor_trace(),
                evidence_status="persisted",
                evidence_updates={"receipt_tx_hash": "0x1234"},
            )

    def test_independent_evidence_artifact_hash_is_verified(self):
        with self.assertRaisesRegex(ValueError, "evidence SHA-256 mismatch"):
            self.run_audit(
                constructor_trace(),
                evidence_status="persisted",
                evidence_updates={"evidence_sha256": "ab" * 32},
            )

    def test_independent_evidence_binds_complete_receipt_identity(self):
        for update in (
            {"amount_atto": 101},
            {"from": ORIGIN},
            {"to": ORIGIN},
            {"receipt_index": 1},
            {"source_block_hash": "0x" + "33" * 32},
        ):
            with self.subTest(update=update):
                with self.assertRaisesRegex(
                    ValueError, "did not match the selected canonical receipts"
                ):
                    self.run_audit(
                        constructor_trace(),
                        evidence_status="persisted",
                        evidence_updates=update,
                    )

    def test_direct_source_paths_remain_untraced(self):
        for update in ({"to": audit.CX_PRECOMPILE}, {"toShardID": 1}):
            with self.subTest(update=update):
                row, _ = self.run_audit(None, update)
                self.assertEqual(row["classification"], "valid_source_debit")
                self.assertEqual(row["replay_classification"], "not_traced")
                self.assertEqual(row["classification_source"], "direct_transaction")
                self.assertEqual(row["completed_precompile_call_count"], "")
