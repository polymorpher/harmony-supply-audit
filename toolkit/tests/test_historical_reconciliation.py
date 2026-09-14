import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cutoff_formula = load_module(
    "cutoff_formula",
    "toolkit/scripts/verify/reconstruct-cutoff-formula.py",
)
historical_closure = load_module(
    "historical_closure",
    "toolkit/scripts/verify/historical-closure.py",
)
shard1_balance = load_module(
    "shard1_balance",
    "toolkit/scripts/forensics/historical-shard1-balance.py",
)
exploit_flow = load_module(
    "exploit_flow",
    "toolkit/scripts/forensics/historical-exploit-flow-export.py",
)
package_results = load_module(
    "package_results",
    "scripts/package-results.py",
)


class HistoricalReconciliationTest(unittest.TestCase):
    def test_cutoff_formula_reconstruction(self):
        result = cutoff_formula.reconstruct(1000, 200, 300, 400, 475)
        self.assertEqual(result["wrapper_reward_delta_atto"], "75")
        self.assertEqual(result["reconstructed_accumulator_atto"], "375")
        self.assertEqual(result["formula_before_exclusions_atto"], "1575")

    def test_historical_closure(self):
        configuration = {
            "genesis_atto": "1000",
            "pre_staking_rewards_atto": "200",
            "checkpoints": [
                {
                    "name": "first",
                    "shard0_claims_atto": "1500",
                    "shard1_claims_atto": "100",
                    "block_reward_accumulator_atto": "300",
                    "adjustments_atto": {"known": "25"},
                    "expected_residual_atto": "75",
                },
                {
                    "name": "second",
                    "shard0_claims_atto": "1600",
                    "shard1_claims_atto": "110",
                    "block_reward_accumulator_atto": "320",
                    "adjustments_atto": {"known": "35"},
                    "expected_residual_atto": "155",
                    "expected_change_atto": "80",
                },
            ],
        }
        result = historical_closure.calculate(configuration, ROOT)
        self.assertEqual(result["checkpoints"][0]["residual_atto"], "75")
        self.assertEqual(
            result["checkpoints"][1]["change_from_previous_atto"], "80"
        )

    def test_historical_shard1_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            credits = directory / "credits.csv"
            debits = directory / "debits.csv"
            with credits.open("w", newline="") as output:
                writer = csv.DictWriter(
                    output,
                    fieldnames=(
                        "destination_shard",
                        "destination_block",
                        "amount_atto",
                    ),
                )
                writer.writeheader()
                writer.writerows(
                    (
                        {
                            "destination_shard": 1,
                            "destination_block": 11,
                            "amount_atto": 50,
                        },
                        {
                            "destination_shard": 1,
                            "destination_block": 21,
                            "amount_atto": 999,
                        },
                        {
                            "destination_shard": 0,
                            "destination_block": 12,
                            "amount_atto": 999,
                        },
                    )
                )
            with debits.open("w", newline="") as output:
                writer = csv.DictWriter(
                    output,
                    fieldnames=(
                        "audit_source_shard",
                        "audit_source_block",
                        "signed_source_shard",
                        "signed_source_block",
                        "classification",
                        "amount_atto",
                    ),
                )
                writer.writeheader()
                writer.writerows(
                    (
                        {
                            "audit_source_shard": 1,
                            "audit_source_block": 15,
                            "classification": "valid_source_debit",
                            "amount_atto": 20,
                        },
                        {
                            "signed_source_shard": 1,
                            "signed_source_block": 16,
                            "classification": "rollback_leak",
                            "amount_atto": 999,
                        },
                    )
                )
            _, later_credits = shard1_balance.sum_later_credits(
                credits, 10, 20
            )
            _, later_debits = shard1_balance.sum_later_valid_debits(
                debits, 10, 20
            )
            self.assertEqual(later_credits, 50)
            self.assertEqual(later_debits, 20)
            self.assertEqual(
                shard1_balance.derive(1000, later_credits, later_debits),
                970,
            )

    def test_source_audit_evidence_provenance_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source-audit.csv"
            row = {
                "from": "0x0000000000000000000000000000000000001111",
                "classification": "source_debit_absent",
                "classification_source": "independent_source_debit_evidence",
                "replay_classification": "replay_incompatible",
                "independent_evidence_reference": "evidence.json",
                "independent_evidence_sha256": "ab" * 32,
                "source_transaction_hash": "0x" + "11" * 32,
                "audit_source_block": "10",
                "amount_atto": "100",
                "precompile_call_count": "1",
                "failed_precompile_path_count": "0",
                "source_transaction_status": "1",
                "source_transaction_from":
                    "0x0000000000000000000000000000000000001111",
                "source_transaction_to":
                    "0x0000000000000000000000000000000000002222",
                "source_transaction_value_atto": "100",
                "source_input_selector": "0x12345678",
            }
            with source.open("w", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            records = {}
            exploit_flow.load_source_audit(records, source, 1)
            record = next(iter(records.values()))
            self.assertIn("source-debit-absent", record["incidents"])
            self.assertIn(
                "independent-source-debit-evidence",
                record["trace_methods"],
            )
            self.assertEqual(
                record["source_audit_classification_sources"],
                {"independent_source_debit_evidence"},
            )
            self.assertEqual(
                record["source_audit_replay_classifications"],
                {"replay_incompatible"},
            )
            self.assertEqual(
                record["source_audit_evidence_references"],
                {"evidence.json"},
            )
            self.assertEqual(
                record["source_audit_evidence_sha256"],
                {"ab" * 32},
            )

    def test_max_rate_opening_labels_are_corrected(self):
        value = {
            "activation_inclusive_gross_duplicate_payout_atto": "10",
            "activation_inclusive_gross_duplicate_payout_one": "10",
            "opening_duplicate_payout_atto": "2",
            "opening_duplicate_payout_one": "2",
            "post_checkpoint_gross_duplicate_payout_atto": "8",
            "post_checkpoint_gross_duplicate_payout_one": "8",
        }
        corrected = package_results.correct_max_rate_labels(
            value, "max-rate-opening-payout-audit.json"
        )
        self.assertNotIn(
            "activation_inclusive_gross_duplicate_payout_atto", corrected
        )
        self.assertEqual(
            corrected[
                "activation_inclusive_peak_duplicated_claim_exposure_atto"
            ],
            "10",
        )
        self.assertTrue(
            corrected["accounting_interpretation"][
                "age_seven_liquid_release_paid_once"
            ]
        )


if __name__ == "__main__":
    unittest.main()
