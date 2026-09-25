#!/usr/bin/env python3

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def parse_args():
    default = REPOSITORY_ROOT / "results" / "2026-09-11"
    parser = argparse.ArgumentParser(
        description="Verify committed Harmony supply reconciliation arithmetic"
    )
    parser.add_argument("--results", default=str(default))
    parser.add_argument(
        "--formula-input",
        default=str(REPOSITORY_ROOT / "embargoed" / "cutoff-formula.json"),
    )
    parser.add_argument(
        "--closure-input",
        default=str(
            REPOSITORY_ROOT / "embargoed" / "historical-closure-input.json"
        ),
    )
    parser.add_argument(
        "--non-issuance-results",
        default=str(REPOSITORY_ROOT / "results" / "2026-09-16"),
    )
    parser.add_argument(
        "--non-issuance-release",
        default=str(
            REPOSITORY_ROOT
            / "manifests"
            / "releases"
            / "2026-09-16.json"
        ),
    )
    return parser.parse_args()


def load(root, name):
    with (root / name).open(encoding="utf-8") as source:
        return json.load(source)


def load_path(path):
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cross_shard_components(by_name):
    legacy_name = "proven_cross_shard_rollback_leakage"
    trace_name = "trace_proven_cross_shard_rollback_leakage"
    absent_name = "canonical_state_proven_source_debit_absence"
    legacy = by_name.get(legacy_name)
    split_present = trace_name in by_name or absent_name in by_name
    if legacy is not None and split_present:
        raise ValueError("cross-shard reconciliation mixes legacy and split components")
    if legacy is not None:
        return {
            "trace_proven": legacy,
            "source_debit_absent": 0,
            "total_unbacked_credit": legacy,
        }
    if not split_present:
        raise ValueError("cross-shard reconciliation component is missing")
    if trace_name not in by_name or absent_name not in by_name:
        raise ValueError(
            "split cross-shard reconciliation requires both evidence components"
        )
    trace = by_name[trace_name]
    absent = by_name[absent_name]
    return {
        "trace_proven": trace,
        "source_debit_absent": absent,
        "total_unbacked_credit": trace + absent,
    }


def load_historical_closure_module():
    path = Path(__file__).with_name("historical-closure.py")
    spec = importlib.util.spec_from_file_location("historical_closure", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    args = parse_args()
    root = Path(args.results)
    reconciliation = load(root, "reconciliation.json")
    formula_input = load_path(Path(args.formula_input))

    components = reconciliation["components"]
    component_total = sum(int(component["atto"]) for component in components)
    state_gap = int(reconciliation["state_resident_formula_gap_atto"])
    if component_total != state_gap:
        raise ValueError(f"component sum {component_total} != state gap {state_gap}")

    pending = int(reconciliation["supported_pending_receipts_outside_state_atto"])
    claim_gap = int(reconciliation["claim_adjusted_formula_gap_atto"])
    if state_gap + pending != claim_gap:
        raise ValueError("claim-adjusted gap does not equal state gap plus pending receipts")

    by_name = {component["name"]: int(component["atto"]) for component in components}
    cross_shard = cross_shard_components(by_name)["total_unbacked_credit"]
    december = by_name["december_2023_repeated_undelegation_mint"]
    max_rate_net = by_name["post_2023_max_rate_net_effect_at_cleanup"]
    rounding = by_name["post_top_max_rate_rounding_drift"]
    max_rate = reconciliation["post_2023_max_rate"]
    if int(max_rate["net_state_formula_effect_at_cleanup_atto"]) != max_rate_net:
        raise ValueError("max-rate component does not match cleanup result")

    known_net = int(reconciliation["known_unauthorized_net_cutoff_component"]["atto"])
    if cross_shard + december + max_rate_net != known_net:
        raise ValueError("known unauthorized net subtotal mismatch")

    max_rate_peak = int(
        max_rate["activation_inclusive_peak_duplicated_claim_exposure_atto"]
    )
    known_peak = int(
        reconciliation["known_unauthorized_peak_claim_inflation"]["atto"]
    )
    if cross_shard + december + max_rate_peak != known_peak:
        raise ValueError("known peak claim-inflation subtotal mismatch")

    post_peak = int(
        max_rate["post_checkpoint_peak_duplicated_claim_exposure_atto"]
    )
    opening = int(
        max_rate["activation_opening_duplicated_claim_exposure_atto"]
    )
    if post_peak + opening != max_rate_peak:
        raise ValueError("max-rate activation-inclusive exposure mismatch")
    interpretation = max_rate["accounting_interpretation"]
    if not interpretation["peak_exposure_is_not_second_liquid_payout_total"]:
        raise ValueError("max-rate peak exposure is mislabeled as liquid payout")

    stale_cleanup = int(
        max_rate["stale_undelegation_liabilities_removed_at_cleanup_atto"]
    )
    missing_rewards = int(
        max_rate["formula_counted_validator_rewards_not_committed_atto"]
    )
    closure = int(max_rate["claim_exposure_cleanup_equation_closure_atto"])
    measured = int(max_rate["measured_net_effect_through_october_atto"])
    if post_peak - stale_cleanup - missing_rewards + closure != measured:
        raise ValueError("max-rate exposure/cleanup/reward equation mismatch")

    genesis = int(formula_input["genesis_atto"])
    pre_staking = int(formula_input["pre_staking_rewards_atto"])
    base_accumulator = int(formula_input["base_accumulator_atto"])
    base_wrappers = int(formula_input["base_wrapper_rewards_atto"])
    cutoff_wrappers = int(formula_input["cutoff_wrapper_rewards_atto"])
    wrapper_delta = cutoff_wrappers - base_wrappers
    if wrapper_delta != int(formula_input["wrapper_reward_delta_atto"]):
        raise ValueError("cutoff wrapper-reward delta mismatch")
    reconstructed_accumulator = base_accumulator + wrapper_delta
    if reconstructed_accumulator != int(
        formula_input["reconstructed_accumulator_atto"]
    ):
        raise ValueError("reconstructed cutoff accumulator mismatch")
    formula_before_exclusions = (
        genesis + pre_staking + reconstructed_accumulator
    )
    if formula_before_exclusions != int(
        formula_input["formula_before_exclusions_atto"]
    ):
        raise ValueError("cutoff formula component sum mismatch")

    cutoff_supply = load(root, "actual-supply-cutoff.json")
    ledger = load(root, "actual-supply-ledger-cutoff-summary.json")
    receipts = load(root, "cross-shard-supply-cutoff.json")
    shard0_claims = int(cutoff_supply["account_and_staking_claims_atto"])
    shard1_claims = int(ledger["liquid_shard1_atto"])
    ledger_total = int(ledger["total_claim_atto"])
    ledger_pending = int(ledger["pending_cross_shard_atto"])
    if ledger_pending != pending or ledger_pending != int(
        receipts["pending_active_atto"]
    ):
        raise ValueError("pending-receipt totals disagree")
    if shard0_claims + shard1_claims + pending != ledger_total:
        raise ValueError("cutoff ledger components do not sum to total claim")
    if shard0_claims + shard1_claims - formula_before_exclusions != state_gap:
        raise ValueError("state gap is not derived from cutoff result files")
    if ledger_total - formula_before_exclusions != claim_gap:
        raise ValueError("claim gap is not derived from cutoff result files")

    closure_input_path = Path(args.closure_input)
    closure_configuration = load_path(closure_input_path)
    historical_closure = load_historical_closure_module().calculate(
        closure_configuration, closure_input_path.parent
    )
    points = {
        point["name"]: point for point in historical_closure["checkpoints"]
    }
    first_residual = int(points["post-2023-fix"]["residual_atto"])
    if first_residual != int(reconciliation["pre_existing_net_deficit"]["net_atto"]):
        raise ValueError("pre-existing checkpoint residual mismatch")
    cleanup_change = int(
        points["top-max-rate-cleanup"]["change_from_previous_atto"]
    )
    if cleanup_change != max_rate_net:
        raise ValueError("historical closure does not reproduce max-rate net effect")
    cutoff_point = points["cutoff"]
    if int(cutoff_point["formula_gap_atto"]) != state_gap:
        raise ValueError("historical cutoff formula gap mismatch")
    if int(cutoff_point["shard0_claims_atto"]) != shard0_claims:
        raise ValueError("historical closure shard-0 cutoff mismatch")
    if int(cutoff_point["shard1_claims_atto"]) != shard1_claims:
        raise ValueError("historical closure shard-1 cutoff mismatch")
    expected_cutoff_residual = first_residual + max_rate_net + rounding
    if int(cutoff_point["residual_atto"]) != expected_cutoff_residual:
        raise ValueError("historical residual chain does not close at cutoff")

    december_result = load(root, "december-2023-undelegation-mint-reconstruction.json")
    if int(december_result["total_atto"]) != december:
        raise ValueError("December reconstruction does not match reconciliation")
    if sum(int(row["atto"]) for row in december_result["by_delegator"]) != december:
        raise ValueError("December per-delegator sum mismatch")

    burn = load(root, "burn-address-audit.json")
    inaccessible = sum(
        int(row["cutoff_atto"])
        for row in burn["positive_inaccessible_or_precompile_addresses"]
    )
    if inaccessible != int(burn["positive_inaccessible_total_atto"]):
        raise ValueError("inaccessible-address total mismatch")

    precompile = load(root, "staking-precompile-target-audit-summary.json")
    if precompile["blocks_scanned"] != 13_697_024:
        raise ValueError("staking-precompile block count mismatch")
    if precompile["top_level_staking_precompile_calls"] != 79_602:
        raise ValueError("staking-precompile call count mismatch")
    if precompile["unknown_target_transactions"] != 0:
        raise ValueError("unexpected unknown staking-precompile target")

    treasury = load(root, "treasury-reclaim-inventory-summary.json")
    treasury_meta = reconciliation["historical_treasury_routing_inventory"]
    if treasury["totals_atto"]["treasury_reclaim"] != treasury_meta[
        "treasury_reclaim_atto"
    ]:
        raise ValueError("historical treasury calculation mismatch")
    if treasury["policy_status"] != "superseded":
        raise ValueError("historical treasury policy is not marked superseded")

    non_issuance = load(
        Path(args.non_issuance_results), "migration-non-issuance-summary.json"
    )
    reconciliation_policy = reconciliation["migration_non_issuance_policy"]
    if (
        reconciliation_policy["treasury_destination"] is not None
        or reconciliation_policy["available_for_other_use"]
        or reconciliation_policy["old_chain_gross_claim_changed"]
        or not reconciliation_policy["migration_allocation_reduced"]
        or reconciliation_policy["fixed_erc20_total_supply_changed"]
        or not reconciliation_policy["composite_policy_summary"].endswith(
            "2026-09-17/migration-policy-reconciliation.json"
        )
    ):
        raise ValueError("reconciliation points to an invalid migration policy")
    policy = non_issuance["policy"]
    if policy["migration_treatment"] != "not_issued":
        raise ValueError("current migration treatment is not non-issuance")
    if (
        policy["old_chain_gross_claim_changed"]
        or not policy["migration_allocation_reduced"]
        or policy["fixed_erc20_total_supply_changed"]
        or policy["treasury_destination"] is not None
        or policy["available_for_other_use"]
        or not policy["composite_policy_summary"].endswith(
            "2026-09-17/migration-policy-reconciliation.json"
        )
    ):
        raise ValueError("non-issuance policy semantics are inconsistent")
    historical_treasury = int(treasury["totals_atto"]["treasury_reclaim"])
    existing_non_issuance = int(
        non_issuance["existing_non_issuance"]["not_issued_atto"]
    )
    if historical_treasury > existing_non_issuance:
        raise ValueError("historical policy amount exceeds current non-issuance")

    flow = load(root, "historical-exploit-flow-summary.json")
    retained_from_flow = sum(
        int(values["held_cap_atto"])
        for values in flow["distribution"].values()
    )
    retained = int(
        non_issuance["historical_hack_retained_initial_addresses"][
            "not_issued_atto"
        ]
    )
    if retained != retained_from_flow:
        raise ValueError("historical retained-balance totals disagree")
    if non_issuance["historical_hack_retained_initial_addresses"][
        "overlap_with_existing_non_issuance_addresses"
    ]:
        raise ValueError("historical retained addresses overlap existing policy")
    leak_section = non_issuance.get("revert_leak_credited_recipients")
    revert_leak = int(leak_section["not_issued_atto"]) if leak_section else 0
    combined_not_issued = int(non_issuance["totals"]["not_issued_atto"])
    if combined_not_issued != existing_non_issuance + retained + revert_leak:
        raise ValueError("combined non-issuance total mismatch")
    if int(non_issuance["totals"]["gross_cutoff_claim_atto"]) != ledger_total:
        raise ValueError("non-issuance gross claim does not match cutoff ledger")
    remaining = int(
        non_issuance["totals"][
            "remaining_full_claim_after_non_issuance_atto"
        ]
    )
    if remaining + combined_not_issued != ledger_total:
        raise ValueError("gross claim does not close after non-issuance")

    retained_csv = (
        REPOSITORY_ROOT
        / "artifacts"
        / "historical-retention-snapshot-20260916"
        / non_issuance["outputs"]["retained_not_issued_csv"]
    )
    if sha256(retained_csv) != non_issuance["outputs"][
        "retained_not_issued_csv_sha256"
    ]:
        raise ValueError("retained non-issuance CSV hash mismatch")
    with retained_csv.open(newline="") as source:
        retained_rows = 0
        retained_csv_total = 0
        retained_addresses = set()
        for row in csv.DictReader(source):
            retained_rows += 1
            address = row["address_hex"].lower()
            if address in retained_addresses:
                raise ValueError(f"duplicate retained address: {address}")
            retained_addresses.add(address)
            amount = int(row["retained_cap_atto"])
            if amount != min(
                int(row["initial_distribution_atto"]),
                int(row["cutoff_balance_atto"]),
            ):
                raise ValueError(f"invalid retained cap: {address}")
            if row["migration_treatment"] != "not_issued":
                raise ValueError(f"retained address is not terminal: {address}")
            evidence = retained_csv.parent / row["source_evidence"]
            if not evidence.is_file():
                raise FileNotFoundError(evidence)
            retained_csv_total += amount
    if retained_rows != non_issuance["outputs"]["retained_not_issued_rows"]:
        raise ValueError("retained non-issuance CSV row-count mismatch")
    if retained_csv_total != retained:
        raise ValueError("retained non-issuance CSV total mismatch")

    release = load_path(Path(args.non_issuance_release))
    assets = {asset["name"]: asset for asset in release["assets"]}
    retained_asset = assets.get(retained_csv.name)
    if retained_asset is None:
        raise ValueError("retained non-issuance CSV missing from release manifest")
    if (
        retained_asset["bytes"] != retained_csv.stat().st_size
        or retained_asset["rows"] != retained_rows
        or retained_asset["sha256"] != sha256(retained_csv)
    ):
        raise ValueError("retained non-issuance release metadata mismatch")

    if leak_section:
        leak_csv = (
            REPOSITORY_ROOT
            / "artifacts"
            / "revert-leak-retention-20260923"
            / Path(non_issuance["sources"]["revert_leak_retention"]["name"]).name
        )
        if sha256(leak_csv) != non_issuance["sources"]["revert_leak_retention"]["sha256"]:
            raise ValueError("revert-leak non-issuance CSV hash mismatch")
        leak_rows = 0
        leak_csv_total = 0
        with leak_csv.open(newline="") as source:
            for row in csv.DictReader(source):
                leak_rows += 1
                amount = int(row["retained_cap_atto"])
                expected = min(
                    int(row["unbacked_credit_atto"]),
                    max(int(row["cutoff_native_claim_atto"]) - int(row["prior_non_issuance_atto"]), 0),
                )
                if amount != expected or amount <= 0 or row["migration_treatment"] != "not_issued":
                    raise ValueError(f"invalid revert-leak amount: {row['address_hex']}")
                leak_csv_total += amount
        if leak_rows != leak_section["positive_addresses"] or leak_csv_total != revert_leak:
            raise ValueError("revert-leak non-issuance CSV total mismatch")
        leak_asset = assets.get(leak_csv.name)
        if (
            leak_asset is None
            or leak_asset["bytes"] != leak_csv.stat().st_size
            or leak_asset["rows"] != leak_rows
            or leak_asset["sha256"] != sha256(leak_csv)
        ):
            raise ValueError("revert-leak non-issuance release metadata mismatch")

    print(
        "PASS reconciliation: "
        f"state_gap_atto={state_gap} "
        f"claim_gap_atto={claim_gap} "
        f"known_peak_claim_inflation_atto={known_peak} "
        f"not_issued_atto={combined_not_issued}"
    )


if __name__ == "__main__":
    main()
