#!/usr/bin/env python3

"""Independently verify the migration-stage and non-issuance reconciliation."""

import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone


ATTO_PER_ONE = 10**18


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-policy", required=True)
    parser.add_argument("--stage-summary", required=True)
    parser.add_argument("--migration-summary", required=True)
    parser.add_argument(
        "--existing-non-issuance",
        action="append",
        required=True,
        help="reviewed non-issuance inventory used by the stage policy; repeatable, in the same order",
    )
    parser.add_argument(
        "--historical-retention",
        action="append",
        required=True,
        help="retained-cap export used by the stage policy; repeatable, in the same order",
    )
    parser.add_argument("--supply-non-issuance-summary", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path, label):
    with open(path, encoding="utf-8") as source:
        value = json.load(source)
    if value.get("status") != "passed":
        raise ValueError(f"{label} did not pass")
    return value


def one(value):
    whole, fraction = divmod(int(value), ATTO_PER_ONE)
    return f"{whole}.{fraction:018d}"


def parse_utc(value):
    if not value.endswith("Z"):
        raise ValueError(f"UTC timestamp must end in Z: {value}")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != timezone.utc:
        raise ValueError(f"timestamp is not UTC: {value}")
    return parsed


def write_text(path, text, replace):
    if os.path.exists(path + ".partial"):
        raise FileExistsError(path + ".partial")
    if os.path.exists(path) and not replace:
        raise FileExistsError(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path + ".partial", "x", encoding="utf-8") as output:
        output.write(text)
        output.flush()
        os.fsync(output.fileno())
    os.replace(path + ".partial", path)


def table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend(
        "| " + " | ".join(str(value) for value in row) + " |" for row in rows
    )
    return "\n".join(lines)


def render_report(result):
    allocation = result["allocation"]
    stages = result["stages"]
    contracts = result["contracts"]
    return f"""# Migration policy reconciliation

Prepared: `2026-09-17`

This independently re-sums the migration repository's address-level stage
policy from shared source artifacts rather than an editorial calculation.

## Result

{table(
    ("Allocation bucket", "Addresses", "ONE"),
    (
        ("Initial wallets", f'{stages["initial"]["addresses"]:,}', one(stages["initial"]["allocation_atto"])),
        ("Next-stage reviewed contracts", f'{stages["next_stage"]["addresses"]:,}', one(stages["next_stage"]["allocation_atto"])),
        ("Deferred wallets", "not a destination manifest", one(allocation["deferred_wallets_atto"])),
        ("Total migration allocation", "", one(allocation["total_migration_atto"])),
    ),
)}

The initial cohort contains only positive eligible wallets with indexed
activity in the six calendar months before cutoff. Reviewed contracts are not
present in its activity rows. Exchange/manual routing rows remain allocations;
their routing category does not mean non-issuance. In the migration
repository's compiled routing, confirmed exchange wallets leave this cohort for
the `exchange_manual` stage: they are excluded from the airdrop and delivered
manually from the 2050 supply reserve, so the stage-policy count below is an
upper bound on the airdropped initial cohort.
It contains `{result["initial_wallets"]["automatic_policy_addresses"]:,}`
automatic-policy rows and
`{result["initial_wallets"]["manual_routing_addresses"]:,}` exchange/manual
rows, including
`{result["initial_wallets"]["validator_wrapper_addresses"]:,}` verified
validator wallets.

## Reviewed contract partition

{table(
    (
        "Internal group",
        "Addresses",
        "ONE",
        "Migration stage",
        "Issuance treatment",
    ),
    (
        ("Multisigs", f'{contracts["multisig"]["addresses"]:,}', one(contracts["multisig"]["allocation_atto"]), "next stage", "issue after per-address destination approval"),
        ("LayerZero collateral", f'{contracts["layerzero_bridge_collateral"]["addresses"]:,}', one(contracts["layerzero_bridge_collateral"]["allocation_atto"]), "next stage", "issue after reconciliation"),
        ("1wallet", f'{contracts["onewallet"]["addresses"]:,}', one(contracts["onewallet"]["allocation_atto"]), "next stage", "issue after recovery destination approval"),
        ("SmartVault", f'{contracts["smartvault"]["addresses"]:,}', one(contracts["smartvault"]["not_issued_atto"]), "—", "not issued"),
        ("Other reviewed contracts", f'{contracts["other_reviewed_contract"]["addresses"]:,}', one(contracts["other_reviewed_contract"]["not_issued_atto"]), "—", "not issued"),
    ),
)}

“Abandoned contracts” is the approved public aggregate label:
`{one(allocation["reviewed_contract_non_issuance_atto"])} + `
`{one(allocation["wone_retained_not_issued_atto"])} = `
`{one(allocation["abandoned_contracts_public_aggregate_atto"])} ONE`.
It is not an on-chain abandonment finding.

## Conservation

```text
gross native snapshot                      {one(allocation["gross_native_snapshot_atto"])}
- existing non-issuance                    {one(allocation["existing_non_issuance_atto"])}
- historical retained caps                 {one(allocation["historical_retained_caps_atto"])}
    incident-contract recipients           {one(allocation["historical_incident_contract_recipients_atto"])}
    rollback-leak credited wallets         {one(allocation["rollback_leak_credited_recipients_atto"])}
- retained WONE backing                     {one(allocation["wone_retained_not_issued_atto"])}
- reviewed-contract non-issuance            {one(allocation["reviewed_contract_non_issuance_atto"])}
= total migration allocation               {one(allocation["total_migration_atto"])}
```

The fixed premint is unchanged. Not issued means omitted from migration token
and vault allocations and retained within the 2050 premint reserve; it is not
a burn or treasury transfer.

## Verification

- Address-stage rows are unique and match the recorded SHA-256.
- The threshold-qualified stage set is disjoint by stage.
- Validator wrappers remain wallet accounts.
- Contract group amounts, WONE source offset, and both non-issuance inventories
  re-sum independently.
- Initial + next-stage + deferred equals the total migration allocation.

Machine-readable result: `{result["output"]}`.
"""


def main():
    args = parse_args()
    stage_summary = load_json(args.stage_summary, "stage summary")
    migration = load_json(args.migration_summary, "migration summary")
    supply_non_issuance = load_json(
        args.supply_non_issuance_summary, "supply non-issuance summary"
    )
    sources = {
        "stage_policy": args.stage_policy,
        "stage_summary": args.stage_summary,
        "migration_summary": args.migration_summary,
        "supply_non_issuance_summary": args.supply_non_issuance_summary,
    }
    for name in ("existing_non_issuance", "historical_retention"):
        for index, path in enumerate(getattr(args, name)):
            sources[f"{name}_{index + 1}"] = path
    hashes = {name: file_sha256(path) for name, path in sources.items()}
    if hashes["stage_policy"] != stage_summary["output_sha256"]:
        raise ValueError("stage-policy hash mismatch")
    if hashes["migration_summary"] != stage_summary["sources"]["migration_summary"]["sha256"]:
        raise ValueError("migration_summary hash mismatch")
    for name in ("existing_non_issuance", "historical_retention"):
        recorded = stage_summary["sources"][name]
        recorded = recorded if isinstance(recorded, list) else [recorded]
        local = [hashes[f"{name}_{index + 1}"] for index in range(len(getattr(args, name)))]
        if local != [record["sha256"] for record in recorded]:
            raise ValueError(f"{name} hash mismatch")

    seen = set()
    stages = defaultdict(lambda: {"addresses": 0, "allocation_atto": 0})
    treatments = Counter()
    contracts = defaultdict(
        lambda: {
            "addresses": 0,
            "allocation_atto": 0,
            "wallet_allocation_atto": 0,
            "staked_allocation_atto": 0,
            "not_issued_atto": 0,
            "not_issued_wallet_atto": 0,
            "not_issued_staked_atto": 0,
        }
    )
    totals = Counter()
    initial_routing = Counter()
    initial_validators = 0
    initial_since = parse_utc(
        stage_summary["initial_window"]["since_time_utc"]
    )
    with open(args.stage_policy, newline="") as source:
        reader = csv.DictReader(source)
        required = {
            "address",
            "account_classification",
            "policy_group",
            "routing_category",
            "migration_stage",
            "issuance_treatment",
            "qualification_total_atto",
            "gross_allocation_atto",
            "existing_non_issuance_atto",
            "historical_retained_cap_atto",
            "wone_source_offset_atto",
            "reviewed_contract_non_issuance_atto",
            "reviewed_contract_wallet_non_issuance_atto",
            "reviewed_contract_staked_non_issuance_atto",
            "migration_wallet_allocation_atto",
            "migration_staked_to_vault_atto",
            "migration_allocation_atto",
            "last_activity_time_utc",
        }
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"stage policy is missing fields: {sorted(missing)}"
            )
        for line, row in enumerate(reader, start=2):
            address = row["address"].lower()
            if address in seen:
                raise ValueError(f"duplicate stage address at line {line}")
            seen.add(address)
            values = {
                field: int(row[field])
                for field in (
                    "gross_allocation_atto",
                    "existing_non_issuance_atto",
                    "historical_retained_cap_atto",
                    "wone_source_offset_atto",
                    "reviewed_contract_non_issuance_atto",
                    "reviewed_contract_wallet_non_issuance_atto",
                    "reviewed_contract_staked_non_issuance_atto",
                    "migration_wallet_allocation_atto",
                    "migration_staked_to_vault_atto",
                    "migration_allocation_atto",
                )
            }
            if min(values.values()) < 0:
                raise ValueError(f"negative stage amount at line {line}")
            if int(row["qualification_total_atto"]) < 1000 * ATTO_PER_ONE:
                raise ValueError(f"below-threshold stage row at line {line}")
            if (
                values["gross_allocation_atto"]
                - values["existing_non_issuance_atto"]
                - values["historical_retained_cap_atto"]
                - values["wone_source_offset_atto"]
                - values["reviewed_contract_non_issuance_atto"]
                != values["migration_allocation_atto"]
            ):
                raise ValueError(f"stage row does not close at line {line}")
            stage = row["migration_stage"]
            treatment = row["issuance_treatment"]
            if (
                values["migration_wallet_allocation_atto"]
                + values["migration_staked_to_vault_atto"]
                != values["migration_allocation_atto"]
            ):
                raise ValueError(
                    f"final components do not close at line {line}"
                )
            if (
                values["reviewed_contract_wallet_non_issuance_atto"]
                + values["reviewed_contract_staked_non_issuance_atto"]
                != values["reviewed_contract_non_issuance_atto"]
            ):
                raise ValueError(
                    f"contract non-issuance components do not close at line {line}"
                )
            if treatment == "issue":
                if not stage or values["migration_allocation_atto"] <= 0:
                    raise ValueError(
                        f"issued row has no stage or amount at line {line}"
                    )
            elif treatment == "not_issued":
                if stage or values["migration_allocation_atto"]:
                    raise ValueError(
                        f"not-issued row has stage or amount at line {line}"
                    )
            else:
                raise ValueError(
                    f"invalid issuance treatment at line {line}"
                )
            if stage:
                stages[stage]["addresses"] += 1
                stages[stage]["allocation_atto"] += values[
                    "migration_allocation_atto"
                ]
            treatments[treatment] += 1
            for field, amount in values.items():
                totals[field] += amount
            activity_time = (
                parse_utc(row["last_activity_time_utc"])
                if row["last_activity_time_utc"]
                else None
            )
            if stage == "initial":
                if (
                    row["account_classification"]
                    not in {"wallet", "validator_wallet"}
                    or values["migration_allocation_atto"] <= 0
                    or activity_time is None
                    or activity_time < initial_since
                ):
                    raise ValueError(f"invalid initial-stage row at line {line}")
                initial_routing[row["routing_category"]] += 1
                initial_validators += int(
                    row["account_classification"] == "validator_wallet"
                )
            elif (
                stage == "deferred"
                and row["account_classification"] in {"wallet", "validator_wallet"}
                and values["migration_allocation_atto"] > 0
                and activity_time is not None
                and activity_time >= initial_since
            ):
                raise ValueError(
                    f"active wallet incorrectly deferred at line {line}"
                )
            if row["account_classification"] == "genuine_contract":
                group = contracts[row["policy_group"]]
                group["addresses"] += 1
                group["allocation_atto"] += values[
                    "migration_allocation_atto"
                ]
                group["wallet_allocation_atto"] += values[
                    "migration_wallet_allocation_atto"
                ]
                group["staked_allocation_atto"] += values[
                    "migration_staked_to_vault_atto"
                ]
                group["not_issued_atto"] += values[
                    "reviewed_contract_non_issuance_atto"
                ]
                group["not_issued_wallet_atto"] += values[
                    "reviewed_contract_wallet_non_issuance_atto"
                ]
                group["not_issued_staked_atto"] += values[
                    "reviewed_contract_staked_non_issuance_atto"
                ]
                if stage == "initial":
                    raise ValueError("genuine contract entered initial stage")

    if len(seen) != int(stage_summary["qualified_rows"]):
        raise ValueError("stage row count mismatch")
    if set(stages) != set(stage_summary["stage_rows"]):
        raise ValueError("stage labels do not match summary")
    for stage, values in stages.items():
        if values["addresses"] != stage_summary["stage_rows"][stage]:
            raise ValueError(f"{stage} address count mismatch")
    if dict(sorted(treatments.items())) != stage_summary[
        "issuance_treatment_rows"
    ]:
        raise ValueError("issuance-treatment counts do not match summary")
    for group, values in contracts.items():
        expected = stage_summary["contracts"]["groups"][group]
        if (
            values["addresses"] != expected["addresses"]
            or values["allocation_atto"] != expected["allocation_atto"]
            or values["wallet_allocation_atto"]
            != expected["wallet_allocation_atto"]
            or values["staked_allocation_atto"]
            != expected["staked_allocation_atto"]
            or values["not_issued_atto"] != expected["not_issued_atto"]
            or values["not_issued_wallet_atto"]
            != expected["not_issued_wallet_atto"]
            or values["not_issued_staked_atto"]
            != expected["not_issued_staked_atto"]
        ):
            raise ValueError(f"{group} contract totals mismatch")

    allocation = stage_summary["allocation"]
    existing_total = int(allocation["existing_non_issuance_atto"])
    historical_total = int(allocation["historical_retained_caps_atto"])
    if existing_total != int(
        supply_non_issuance["existing_non_issuance"]["not_issued_atto"]
    ):
        raise ValueError("existing non-issuance total mismatch")
    supply_retained = int(
        supply_non_issuance["historical_hack_retained_initial_addresses"][
            "not_issued_atto"
        ]
    )
    supply_rollback_leak = int(
        supply_non_issuance.get("rollback_leak_credited_recipients", {}).get(
            "not_issued_atto", 0
        )
    )
    if historical_total != supply_retained + supply_rollback_leak:
        raise ValueError("historical retained-cap total mismatch")
    if existing_total + historical_total != int(
        supply_non_issuance["totals"]["not_issued_atto"]
    ):
        raise ValueError("supply non-issuance total does not close")

    gross = int(migration["native_total_claim_atto"])
    retained_wone = int(migration["wone_retained_not_issued_atto"])
    contract_non_issuance = totals[
        "reviewed_contract_non_issuance_atto"
    ]
    total_migration = (
        gross
        - existing_total
        - historical_total
        - retained_wone
        - contract_non_issuance
    )
    if gross != int(allocation["gross_native_snapshot_atto"]):
        raise ValueError("gross native snapshot mismatch")
    if total_migration != int(allocation["total_migration_atto"]):
        raise ValueError("total migration allocation mismatch")
    if totals["wone_source_offset_atto"] != int(
        migration["wone_reserve_atto"]
    ):
        raise ValueError("WONE source offset mismatch")
    if contract_non_issuance != int(
        allocation["reviewed_contract_non_issuance_atto"]
    ):
        raise ValueError("reviewed-contract non-issuance mismatch")
    if stages["initial"]["allocation_atto"] != int(
        allocation["initial_wallets_atto"]
    ):
        raise ValueError("initial wallet allocation mismatch")
    if (
        initial_routing["automatic_policy"]
        != stage_summary["initial_wallets"]["automatic_policy_addresses"]
        or initial_routing["exchange_or_manual"]
        != stage_summary["initial_wallets"]["manual_routing_addresses"]
        or initial_validators
        != stage_summary["validator_wrappers"]["initial_addresses"]
    ):
        raise ValueError("initial wallet composition mismatch")
    if stages["next_stage"]["allocation_atto"] != int(
        allocation["next_stage_contracts_atto"]
    ):
        raise ValueError("next-stage allocation mismatch")
    if (
        stages["initial"]["allocation_atto"]
        + stages["next_stage"]["allocation_atto"]
        + int(allocation["deferred_wallets_atto"])
        != total_migration
    ):
        raise ValueError("stage allocation does not close")

    result = {
        "schema_version": 1,
        "status": "passed",
        "method": (
            "independent row-level re-sum of migration-stage policy and "
            "cross-repository non-issuance sources"
        ),
        "_provenance": {
            "classification": "policy-scenario verification",
            "factual_input": (
                "cutoff-pinned migration ledger, contract identities, "
                "activity, and retained-balance evidence"
            ),
            "note": (
                "stage and non-issuance treatments are user-selected "
                "migration policy; gross native supply remains factual"
            ),
        },
        "sources": {
            name: {"path": path, "sha256": hashes[name]}
            for name, path in sources.items()
        },
        "qualified_rows": len(seen),
        "initial_wallets": {
            "automatic_policy_addresses": initial_routing[
                "automatic_policy"
            ],
            "manual_routing_addresses": initial_routing[
                "exchange_or_manual"
            ],
            "validator_wrapper_addresses": initial_validators,
            "since_time_utc": stage_summary["initial_window"][
                "since_time_utc"
            ],
        },
        "stages": {
            stage: dict(values) for stage, values in sorted(stages.items())
        },
        "issuance_treatments": dict(sorted(treatments.items())),
        "contracts": {
            group: dict(values)
            for group, values in sorted(contracts.items())
        },
        "allocation": {
            "gross_native_snapshot_atto": gross,
            "existing_non_issuance_atto": existing_total,
            "historical_retained_caps_atto": historical_total,
            "historical_incident_contract_recipients_atto": supply_retained,
            "rollback_leak_credited_recipients_atto": supply_rollback_leak,
            "wone_retained_not_issued_atto": retained_wone,
            "reviewed_contract_non_issuance_atto": contract_non_issuance,
            "abandoned_contracts_public_aggregate_atto": (
                retained_wone + contract_non_issuance
            ),
            "initial_wallets_atto": stages["initial"]["allocation_atto"],
            "next_stage_contracts_atto": stages["next_stage"][
                "allocation_atto"
            ],
            "deferred_wallets_atto": int(
                allocation["deferred_wallets_atto"]
            ),
            "total_exclusions_atto": gross - total_migration,
            "total_migration_atto": total_migration,
        },
        "output": args.output,
    }
    write_text(
        args.output,
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        args.replace,
    )
    write_text(args.report, render_report(result), args.replace)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
