#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def parse_args():
    default = Path(__file__).resolve().parents[3] / "results" / "2026-09-11"
    parser = argparse.ArgumentParser(
        description="Verify committed Harmony supply reconciliation arithmetic"
    )
    parser.add_argument("--results", default=str(default))
    return parser.parse_args()


def load(root, name):
    with (root / name).open(encoding="utf-8") as source:
        return json.load(source)


def main():
    args = parse_args()
    root = Path(args.results)
    reconciliation = load(root, "reconciliation.json")

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
    cross_shard = by_name["proven_cross_shard_rollback_leakage"]
    december = by_name["december_2023_repeated_undelegation_mint"]
    max_rate_net = by_name["post_2023_max_rate_net_effect_at_cleanup"]
    max_rate = reconciliation["post_2023_max_rate"]
    if int(max_rate["net_retained_mint_at_cleanup_atto"]) != max_rate_net:
        raise ValueError("max-rate component does not match cleanup result")

    known_net = int(reconciliation["known_unauthorized_net_cutoff_component"]["atto"])
    if cross_shard + december + max_rate_net != known_net:
        raise ValueError("known unauthorized net subtotal mismatch")

    max_rate_gross = int(max_rate["activation_inclusive_gross_duplicate_payouts_atto"])
    known_gross = int(reconciliation["known_unauthorized_gross_creation"]["atto"])
    if cross_shard + december + max_rate_gross != known_gross:
        raise ValueError("known unauthorized gross subtotal mismatch")

    post_gross = int(max_rate["post_checkpoint_gross_duplicate_payouts_atto"])
    opening = int(max_rate["activation_opening_duplicate_payouts_atto"])
    if post_gross + opening != max_rate_gross:
        raise ValueError("max-rate activation-inclusive gross mismatch")

    stale_cleanup = int(
        max_rate["stale_undelegation_liabilities_removed_at_cleanup_atto"]
    )
    missing_rewards = int(
        max_rate["formula_counted_validator_rewards_not_committed_atto"]
    )
    closure = int(max_rate["gross_cleanup_reward_equation_closure_atto"])
    measured = int(max_rate["measured_net_effect_through_october_atto"])
    if post_gross - stale_cleanup - missing_rewards + closure != measured:
        raise ValueError("max-rate gross/cleanup/reward equation mismatch")

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
    treasury_meta = reconciliation["treasury_reclaim_inventory"]
    if treasury["totals_atto"]["treasury_reclaim"] != treasury_meta[
        "treasury_reclaim_atto"
    ]:
        raise ValueError("policy-scenario treasury total mismatch")

    print(
        "PASS reconciliation: "
        f"state_gap_atto={state_gap} "
        f"claim_gap_atto={claim_gap} "
        f"known_gross_atto={known_gross}"
    )


if __name__ == "__main__":
    main()
