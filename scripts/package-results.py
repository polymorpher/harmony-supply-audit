#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Package compact public results from a local accounting tree"
    )
    parser.add_argument("--accounting-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="atomically replace existing packaged result files",
    )
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_string(value):
    replacements = {
        "local/harmony-balance-accounting/artifacts/supply-reconciliation-20260911/": "results/2026-09-11/",
        "local/harmony-balance-accounting/": "source://harmony-balance-accounting/",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    absolute_prefixes = tuple("/" + name for name in ("Users/", "home/", "mnt/", "data/"))
    if value.startswith(absolute_prefixes):
        return "redacted://" + Path(value).name
    return value


def normalize(value):
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, str):
        return normalize_string(value)
    return value


def rename_key(value, old, new):
    if old in value:
        value[new] = value.pop(old)


def cross_shard_component_names(reconciliation):
    names = {
        component["name"] for component in reconciliation.get("components", [])
    }
    legacy = "proven_cross_shard_rollback_leakage"
    split = (
        "trace_proven_cross_shard_rollback_leakage",
        "canonical_state_proven_source_debit_absence",
    )
    if legacy in names and any(name in names for name in split):
        raise ValueError("reconciliation mixes legacy and split cross-shard components")
    if legacy in names:
        return [legacy]
    present = [name for name in split if name in names]
    if present and len(present) != len(split):
        raise ValueError(
            "split cross-shard reconciliation requires both evidence components"
        )
    if present:
        return list(split)
    raise ValueError("reconciliation has no cross-shard evidence component")


def correct_max_rate_labels(value, target_name):
    if target_name == "max-rate-opening-payout-audit.json":
        renames = {
            "activation_inclusive_gross_duplicate_payout_atto":
                "activation_inclusive_peak_duplicated_claim_exposure_atto",
            "activation_inclusive_gross_duplicate_payout_one":
                "activation_inclusive_peak_duplicated_claim_exposure_one",
            "opening_duplicate_payout_atto":
                "opening_duplicated_claim_exposure_atto",
            "opening_duplicate_payout_one":
                "opening_duplicated_claim_exposure_one",
            "post_checkpoint_gross_duplicate_payout_atto":
                "post_checkpoint_peak_duplicated_claim_exposure_atto",
            "post_checkpoint_gross_duplicate_payout_one":
                "post_checkpoint_peak_duplicated_claim_exposure_one",
        }
        for old, new in renames.items():
            rename_key(value, old, new)
        value["finding"] = (
            "three age-seven liquid releases not counted by the first-incident "
            "reconstruction left the same principal in pending undelegation "
            "state when validator-wrapper persistence failed"
        )
        value["accounting_interpretation"] = {
            "age_seven_liquid_release_paid_once": True,
            "pending_claim_failed_to_clear": True,
            "another_liquid_payout_after_age_seven_proved": False,
            "effect": (
                "liquid principal and the stale pending claim represented the "
                "same value twice until cleanup or redelegation"
            ),
        }
        value["scope_note"] = (
            "the opening exposure is absent from the first-incident "
            "reconstruction, which stops at paid epoch 1731, and from the "
            "post-checkpoint exposure reconstruction, which starts after block "
            "51,150,847"
        )

    if target_name == "reconciliation.json":
        cross_shard_components = cross_shard_component_names(value)
        rename_key(
            value,
            "known_unauthorized_gross_creation",
            "known_unauthorized_peak_claim_inflation",
        )
        peak = value["known_unauthorized_peak_claim_inflation"]
        peak["definition"] = (
            "combined peak claim inflation: actual unsupported credits from "
            "the December and cross-shard incidents plus the max-rate value "
            "temporarily represented both as released liquid and as a stale "
            "pending claim; this is not a total of second liquid payouts, and "
            "burn-address balances are not deducted"
        )
        peak["includes"] = [
            "december_2023_repeated_undelegation_mint",
            "post_2023_max_rate_activation_inclusive_peak_duplicated_claim_exposure",
        ] + cross_shard_components
        value["known_unauthorized_net_cutoff_component"]["includes"] = [
            "december_2023_repeated_undelegation_mint",
            "post_2023_max_rate_net_effect_at_cleanup",
        ] + cross_shard_components

        max_rate = value["post_2023_max_rate"]
        renames = {
            "activation_inclusive_gross_duplicate_payouts_atto":
                "activation_inclusive_peak_duplicated_claim_exposure_atto",
            "activation_inclusive_gross_duplicate_payouts_one":
                "activation_inclusive_peak_duplicated_claim_exposure_one",
            "activation_opening_duplicate_payouts_atto":
                "activation_opening_duplicated_claim_exposure_atto",
            "activation_opening_duplicate_payouts_one":
                "activation_opening_duplicated_claim_exposure_one",
            "gross_cleanup_reward_equation_closure_atto":
                "claim_exposure_cleanup_equation_closure_atto",
            "gross_cleanup_reward_equation_closure_one":
                "claim_exposure_cleanup_equation_closure_one",
            "gross_duplicate_payout_breakdown":
                "duplicated_claim_exposure_breakdown",
            "net_retained_mint_at_cleanup_atto":
                "net_state_formula_effect_at_cleanup_atto",
            "net_retained_mint_at_cleanup_one":
                "net_state_formula_effect_at_cleanup_one",
            "post_checkpoint_gross_duplicate_payouts_atto":
                "post_checkpoint_peak_duplicated_claim_exposure_atto",
            "post_checkpoint_gross_duplicate_payouts_one":
                "post_checkpoint_peak_duplicated_claim_exposure_one",
        }
        for old, new in renames.items():
            rename_key(max_rate, old, new)
        max_rate["causal_confidence"] = (
            "very high; peak duplicated claim exposure, cleanup, and omitted "
            "rewards match the measured interval effect within the recorded "
            "sub-nano-ONE closure"
        )
        max_rate["accounting_interpretation"] = {
            "age_seven_behavior": (
                "principal was released to liquid once, but failed wrapper "
                "persistence left the same principal as a pending claim"
            ),
            "age_over_seven_behavior": (
                "the MaxRate rule suppressed another liquid payout and tried "
                "to remove the stale entry without payment"
            ),
            "realization_path": (
                "a stale pending claim could be redelegated into active stake "
                "without removing the already released liquid"
            ),
            "cleanup": (
                "TopMaxRate removed stale pending claims; it did not debit "
                "liquid balances"
            ),
            "peak_exposure_is_not_second_liquid_payout_total": True,
        }
        breakdown = max_rate["duplicated_claim_exposure_breakdown"]
        breakdown[0]["name"] = (
            "stale pending claims represented alongside already released "
            "liquid at cleanup, adjusted for partial redelegations"
        )
        breakdown[1]["name"] = (
            "stale pending claims fully consumed by redelegation before cleanup"
        )
        breakdown[2]["name"] = (
            "age-eight flagged stale claims omitted by the published "
            "greater-than-eight filter; not proved second liquid payouts"
        )
        max_rate["pre_cleanup_net_formula_residual_increase_definition"] = (
            "post-checkpoint duplicated claim exposure after the offset from "
            "formula-counted validator rewards that failed to persist, plus "
            "sub-nano-ONE accounting differences"
        )
    return value


def correct_migration_policy_labels(value, target_name):
    current_summary = "results/2026-09-16/migration-non-issuance-summary.json"
    if target_name == "reconciliation.json":
        rename_key(
            value,
            "treasury_reclaim_inventory",
            "historical_treasury_routing_inventory",
        )
        historical = value["historical_treasury_routing_inventory"]
        historical["policy_status"] = "superseded"
        historical["current_treatment"] = (
            "the reviewed amount is not issued on the replacement chain"
        )
        value["migration_non_issuance_policy"] = {
            "current_summary": current_summary,
            "old_chain_gross_claim_changed": False,
            "replacement_chain_issuance_reduced": True,
            "treasury_destination": None,
            "available_for_other_use": False,
        }
    if target_name in {
        "extra-mint-blacklist-reclaim-summary.json",
        "treasury-reclaim-inventory-summary.json",
    }:
        rename_key(value, "policy", "historical_treasury_policy")
        value["policy_status"] = "superseded"
        value["current_treatment"] = (
            "the selected amount is not issued on the replacement chain; "
            "the historical treasury calculation is retained only as evidence"
        )
        value["current_policy_summary"] = current_summary
    if target_name in {
        "blacklisted-address-cutoff-summary.json",
        "reported-wallet-theft-perpetrator-cutoff-summary.json",
        "wallet-theft-report-coverage.json",
    }:
        rename_key(value, "migration_policy", "historical_migration_policy")
        value["current_policy_summary"] = current_summary
    if target_name == "burn-address-audit.json":
        value["migration_treatment"] = {
            "old_chain_balance_accounting": "included",
            "replacement_chain_issuance": "not_issued",
            "treasury_destination": None,
            "available_for_other_use": False,
            "current_policy_summary": current_summary,
        }
    return value


def csv_rows(path):
    with path.open(newline="") as source:
        return sum(1 for _ in csv.reader(source)) - 1


def main():
    args = parse_args()
    accounting = Path(args.accounting_root).resolve()
    output = Path(args.output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)

    supply = accounting / "artifacts" / "supply-reconciliation-20260911"
    cutoff = accounting / "artifacts" / "cutoff-20260910"
    mappings = [
        (supply / "reconciliation.json", "reconciliation.json", "curated external evidence"),
        (
            supply / "december-2023-undelegation-mint-reconstruction.json",
            "december-2023-undelegation-mint-reconstruction.json",
            "RPC-derived",
        ),
        (
            supply / "max-rate-opening-payout-audit.json",
            "max-rate-opening-payout-audit.json",
            "curated external evidence",
        ),
        (supply / "burn-address-audit.json", "burn-address-audit.json", "curated external evidence"),
        (
            supply / "staking-precompile-target-audit-summary.json",
            "staking-precompile-target-audit-summary.json",
            "database-derived",
        ),
        (
            supply / "blacklisted-address-cutoff.csv",
            "blacklisted-address-cutoff.csv",
            "database-derived",
        ),
        (
            supply / "blacklisted-address-cutoff-summary.json",
            "blacklisted-address-cutoff-summary.json",
            "database-derived",
        ),
        (
            supply / "extra-mint-blacklist-burn-path-audit.json",
            "extra-mint-blacklist-burn-path-audit.json",
            "curated external evidence",
        ),
        (
            supply / "extra-mint-blacklist-reclaim.csv",
            "extra-mint-blacklist-reclaim.csv",
            "policy scenario",
        ),
        (
            supply / "extra-mint-blacklist-reclaim-summary.json",
            "extra-mint-blacklist-reclaim-summary.json",
            "policy scenario",
        ),
        (
            supply / "reported-wallet-theft-perpetrator-cutoff.csv",
            "reported-wallet-theft-perpetrator-cutoff.csv",
            "database-derived",
        ),
        (
            supply / "reported-wallet-theft-perpetrator-cutoff-summary.json",
            "reported-wallet-theft-perpetrator-cutoff-summary.json",
            "database-derived",
        ),
        (
            supply / "wallet-theft-report-coverage.json",
            "wallet-theft-report-coverage.json",
            "curated external evidence",
        ),
        (
            supply / "blacklist-operations-history.json",
            "blacklist-operations-history.json",
            "curated external evidence",
        ),
        (
            supply / "treasury-reclaim-inventory.csv",
            "treasury-reclaim-inventory.csv",
            "policy scenario",
        ),
        (
            supply / "treasury-reclaim-inventory-summary.json",
            "treasury-reclaim-inventory-summary.json",
            "policy scenario",
        ),
        (
            cutoff / "cross-shard-supply-cutoff.json",
            "cross-shard-supply-cutoff.json",
            "database-derived",
        ),
        (
            cutoff / "cutoff-reconciliation.verify.json",
            "cutoff-reconciliation.verify.json",
            "database-derived",
        ),
        (
            cutoff / "state" / "actual-supply-cutoff.json",
            "actual-supply-cutoff.json",
            "database-derived",
        ),
        (
            cutoff / "claims" / "actual-supply-ledger-cutoff-summary.json",
            "actual-supply-ledger-cutoff-summary.json",
            "database-derived",
        ),
        (
            cutoff / "interval-audit" / "shard0-summary.json",
            "cutoff-interval-shard0-summary.json",
            "RPC-derived",
        ),
        (
            cutoff / "interval-audit" / "shard1-summary.json",
            "cutoff-interval-shard1-summary.json",
            "RPC-derived",
        ),
        (
            accounting / "historical-exploit-flow-summary.json",
            "historical-exploit-flow-summary.json",
            "RPC-derived",
        ),
    ]
    source_audit_mappings = [
        (
            supply / "source-audit-summary.json",
            "source-audit-summary.json",
            "RPC and canonical-state evidence",
        ),
        (
            supply / "source-audit-verification.json",
            "source-audit-verification.json",
            "verification-derived",
        ),
    ]
    reconciliation = json.loads((supply / "reconciliation.json").read_text())
    split_cross_shard = cross_shard_component_names(reconciliation) != [
        "proven_cross_shard_rollback_leakage"
    ]
    evidence_exists = [source.is_file() for source, _, _ in source_audit_mappings]
    if split_cross_shard or any(evidence_exists):
        if not all(evidence_exists):
            missing = [
                str(source)
                for (source, _, _), exists in zip(
                    source_audit_mappings, evidence_exists
                )
                if not exists
            ]
            raise FileNotFoundError(
                "source-audit evidence package is incomplete: "
                + ", ".join(missing)
            )
        mappings[1:1] = source_audit_mappings

    provenance_notes = {
        "reconciliation.json": "Synthesis of database, RPC, and curated incident evidence; cutoff formula and historical closure are independently recomputed by verify-reconciliation.py.",
        "source-audit-summary.json": "Exact non-overlapping receipt totals with mechanism proof separated from independent source-debit-absence evidence.",
        "source-audit-verification.json": "Identity-set, evidence-digest, classification-transition, and aggregate-preservation checks for the archival rerun.",
        "burn-address-audit.json": "Transaction and cutoff-state evidence with curated burn-address classification.",
        "max-rate-opening-payout-audit.json": "Opening-boundary evidence assembled from recorded historical RPC checks; the broader peak claim-exposure decomposition remains curated.",
        "extra-mint-blacklist-burn-path-audit.json": "Assembled from a recorded top-level transaction-history check; no standalone generator was preserved.",
        "wallet-theft-report-coverage.json": "Addresses extracted from named investigation reports; not a legal attribution.",
        "blacklist-operations-history.json": "Git and operations-history extraction; not chain state.",
        "extra-mint-blacklist-reclaim.csv": "Superseded historical treasury calculation; the selected amount is now not issued.",
        "extra-mint-blacklist-reclaim-summary.json": "Superseded historical treasury calculation; the selected amount is now not issued.",
        "treasury-reclaim-inventory.csv": "Superseded historical treasury-routing inventory retained as calculation evidence.",
        "treasury-reclaim-inventory-summary.json": "Superseded historical treasury-routing inventory retained as calculation evidence.",
    }

    entries = []
    for source, target_name, classification in mappings:
        if not source.is_file():
            raise FileNotFoundError(source)
        target = output / target_name
        if (target.exists() and not args.overwrite) or Path(str(target) + ".partial").exists():
            raise FileExistsError(target)
        source_hash = sha256(source)
        if source.suffix == ".json":
            value = normalize(json.loads(source.read_text()))
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object: {source}")
            value = correct_max_rate_labels(value, target_name)
            value = correct_migration_policy_labels(value, target_name)
            normalization = "absolute machine paths replaced; factual numeric fields unchanged"
            if target_name in {"reconciliation.json", "max-rate-opening-payout-audit.json"}:
                normalization += "; max-rate accounting labels corrected"
            if target_name in {
                "reconciliation.json",
                "burn-address-audit.json",
                "extra-mint-blacklist-reclaim-summary.json",
                "treasury-reclaim-inventory-summary.json",
            }:
                normalization += "; superseded treasury policy marked"
            value["_provenance"] = {
                "classification": classification,
                "source_name": source.name,
                "source_sha256": source_hash,
                "normalization": normalization,
                "note": provenance_notes.get(target_name, ""),
            }
            encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
            partial = Path(str(target) + ".partial")
            partial.write_text(encoded)
            os.replace(partial, target)
            row_count = None
        else:
            partial = Path(str(target) + ".partial")
            shutil.copyfile(source, partial)
            os.replace(partial, target)
            row_count = csv_rows(target)
        entries.append(
            {
                "path": target.name,
                "classification": classification,
                "bytes": target.stat().st_size,
                "rows": row_count,
                "sha256": sha256(target),
                "source_sha256": source_hash,
            }
        )

    index = {
        "schema_version": 1,
        "result_set": "2026-09-11",
        "entries": sorted(entries, key=lambda item: item["path"]),
    }
    index_path = output / "index.json"
    index_partial = Path(str(index_path) + ".partial")
    if index_partial.exists():
        raise FileExistsError(index_partial)
    index_partial.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    os.replace(index_partial, index_path)
    print(f"packaged {len(entries)} results in {output}")


if __name__ == "__main__":
    main()
