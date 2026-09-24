#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path


ATTO = 10**18
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32_GENERATOR = (
    0x3B6A57B2,
    0x26508E6D,
    0x1EA119FA,
    0x3D4233DD,
    0x2A1462B3,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Combine a reviewed non-issuance inventory with retained balances "
            "at initial recipients of historical unbacked credits"
        )
    )
    parser.add_argument(
        "--existing-non-issuance",
        action="append",
        required=True,
        help="reviewed non-issuance inventory; repeatable, an address may appear in only one",
    )
    parser.add_argument("--retained-balances", required=True)
    parser.add_argument("--retained-summary", required=True)
    parser.add_argument("--cutoff-claim-summary", required=True)
    parser.add_argument(
        "--rollback-leak-retention",
        help="build-rollback-leak-retention.py export: wallets credited by proven rollback-leak receipts",
    )
    parser.add_argument("--rollback-leak-summary", help="summary written with --rollback-leak-retention")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_source_name(path):
    parts = path.resolve().parts
    for repository in ("harmony-migration", "harmony-supply-audit"):
        if repository in parts:
            index = parts.index(repository)
            return Path(*parts[index:]).as_posix()
    if "artifacts" in parts:
        index = parts.index("artifacts")
        return Path(*parts[index:]).as_posix()
    return path.name


def one(atto):
    sign = "-" if atto < 0 else ""
    atto = abs(atto)
    return f"{sign}{atto // ATTO}.{atto % ATTO:018d}"


def bech32_polymod(values):
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = (checksum & 0x1FFFFFF) << 5 ^ value
        for index, generator in enumerate(BECH32_GENERATOR):
            if (top >> index) & 1:
                checksum ^= generator
    return checksum


def convert_bits(data, from_bits, to_bits):
    accumulator = 0
    bits = 0
    result = []
    maximum = (1 << to_bits) - 1
    for value in data:
        accumulator = (accumulator << from_bits) | value
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            result.append((accumulator >> bits) & maximum)
    if bits:
        result.append((accumulator << (to_bits - bits)) & maximum)
    return result


def to_bech32(address):
    raw = bytes.fromhex(address.removeprefix("0x"))
    if len(raw) != 20:
        raise ValueError(f"address is not 20 bytes: {address}")
    data = convert_bits(raw, 8, 5)
    expanded_hrp = [ord(char) >> 5 for char in "one"]
    expanded_hrp += [0]
    expanded_hrp += [ord(char) & 31 for char in "one"]
    polymod = bech32_polymod(expanded_hrp + data + [0] * 6) ^ 1
    checksum = [(polymod >> (5 * (5 - index))) & 31 for index in range(6)]
    return "one1" + "".join(BECH32_CHARSET[value] for value in data + checksum)


def false_value(value):
    return value.strip().lower() in {"", "0", "false", "no"}


def load_existing(path):
    rows = []
    seen = set()
    categories = defaultdict(lambda: {"rows": 0, "positive_rows": 0, "atto": 0})
    with path.open(newline="") as source:
        for line, row in enumerate(csv.DictReader(source), start=2):
            address = row["address_hex"].lower()
            if address in seen:
                raise ValueError(f"{path}:{line}: duplicate address {address}")
            seen.add(address)
            amount = int(row["not_issued_atto"])
            if amount < 0 or amount > int(row["cutoff_claim_atto"]):
                raise ValueError(f"{path}:{line}: invalid not-issued amount")
            category = row["category"]
            categories[category]["rows"] += 1
            categories[category]["positive_rows"] += amount > 0
            categories[category]["atto"] += amount
            rows.append(row)
    return rows, seen, categories


def load_retained(path, output_directory):
    rows = []
    seen = set()
    by_incident = defaultdict(
        lambda: {
            "input_addresses": 0,
            "positive_addresses": 0,
            "retained_cap_atto": 0,
            "above_1000_one": 0,
        }
    )
    blocks = Counter()
    for line, row in enumerate(csv.DictReader(path.open(newline="")), start=2):
        address = row["address"].lower()
        if address in seen:
            raise ValueError(f"{path}:{line}: duplicate address {address}")
        seen.add(address)
        incident = row["incident"]
        initial = int(row["initial_amount_atto"])
        cutoff_balance = int(row["cutoff_balance_atto"])
        rpc_balance = int(row["rpc_balance_atto"])
        retained = int(row["rpc_retained_cap_atto"])
        if retained != min(initial, rpc_balance):
            raise ValueError(f"{path}:{line}: retained cap does not match inputs")
        if cutoff_balance != rpc_balance or not false_value(
            row["balance_changed_from_sep10"]
        ):
            raise ValueError(f"{path}:{line}: balance changed after cutoff")
        evidence_path = path.parent / row["raw_file"]
        if not evidence_path.is_file():
            raise FileNotFoundError(evidence_path)
        blocks[int(row["rpc_block"])] += 1
        summary = by_incident[incident]
        summary["input_addresses"] += 1
        if retained > 0:
            summary["positive_addresses"] += 1
            summary["retained_cap_atto"] += retained
            summary["above_1000_one"] += retained > 1000 * ATTO
            rows.append(
                {
                    "address_bech32": to_bech32(address),
                    "address_hex": address,
                    "incident": incident,
                    "initial_distribution_atto": str(initial),
                    "cutoff_balance_atto": str(cutoff_balance),
                    "retained_cap_atto": str(retained),
                    "retained_cap_one": one(retained),
                    "cutoff_block": row["cutoff_block"],
                    "verification_block": row["rpc_block"],
                    "source_evidence": Path(
                        os.path.relpath(
                            evidence_path, output_directory
                        )
                    ).as_posix(),
                    "migration_treatment": "not_issued",
                }
            )
    if len(blocks) != 1:
        raise ValueError(f"retained balances use multiple RPC blocks: {blocks}")
    return rows, seen, by_incident, next(iter(blocks))


def load_rollback_leak(path, summary_path, retained_caps, existing_amounts):
    """Re-check every withheld amount: min(credit, native claim - earlier non-issuance)."""
    summary = json.loads(summary_path.read_text())
    if summary.get("status") != "passed":
        raise ValueError(f"{summary_path}: did not pass")
    if summary["outputs"]["csv_sha256"] != sha256(path):
        raise ValueError(f"{path}: SHA-256 differs from {summary_path}")
    by_incident = defaultdict(lambda: {"positive_addresses": 0, "unbacked_credit_atto": 0, "not_issued_atto": 0})
    seen = set()
    overlap_retained = []
    for line, row in enumerate(csv.DictReader(path.open(newline="")), start=2):
        address = row["address_hex"].lower()
        if address in seen:
            raise ValueError(f"{path}:{line}: duplicate address {address}")
        seen.add(address)
        prior = retained_caps.get(address, 0) + existing_amounts.get(address, 0)
        if int(row["prior_non_issuance_atto"]) != prior:
            raise ValueError(f"{path}:{line}: earlier non-issuance does not match the inventories")
        withheld = int(row["retained_cap_atto"])
        expected = min(int(row["unbacked_credit_atto"]), max(int(row["cutoff_native_claim_atto"]) - prior, 0))
        if withheld != expected or withheld <= 0 or row["migration_treatment"] != "not_issued":
            raise ValueError(f"{path}:{line}: withheld amount does not follow the rule")
        if address in retained_caps:
            overlap_retained.append(address)
        values = by_incident[row["incident"]]
        values["positive_addresses"] += 1
        values["unbacked_credit_atto"] += int(row["unbacked_credit_atto"])
        values["not_issued_atto"] += withheld
    total = sum(values["not_issued_atto"] for values in by_incident.values())
    if str(total) != summary["not_issued_atto"] or len(seen) != summary["positive_rows"]:
        raise ValueError(f"{path}: totals differ from {summary_path}")
    return seen, by_incident, total, sorted(overlap_retained), summary


def write_csv(path, rows, replace):
    fields = (
        "address_bech32",
        "address_hex",
        "incident",
        "initial_distribution_atto",
        "cutoff_balance_atto",
        "retained_cap_atto",
        "retained_cap_one",
        "cutoff_block",
        "verification_block",
        "source_evidence",
        "migration_treatment",
    )
    partial = Path(str(path) + ".partial")
    if partial.exists() or (path.exists() and not replace):
        raise FileExistsError(path)
    with partial.open("x", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: row["address_hex"]))
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial, path)


def write_json(path, value, replace):
    partial = Path(str(path) + ".partial")
    if partial.exists() or (path.exists() and not replace):
        raise FileExistsError(path)
    with partial.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial, path)


def main():
    args = parse_args()
    existing_paths = [Path(path) for path in args.existing_non_issuance]
    retained_path = Path(args.retained_balances)
    retained_summary_path = Path(args.retained_summary)
    claim_summary_path = Path(args.cutoff_claim_summary)
    output_path = Path(args.output_csv)
    summary_path = Path(args.summary_output)

    existing_rows = []
    existing_addresses = set()
    existing_categories = defaultdict(lambda: {"rows": 0, "positive_rows": 0, "atto": 0})
    for existing_path in existing_paths:
        rows, addresses, categories = load_existing(existing_path)
        overlap = existing_addresses & addresses
        if overlap:
            raise ValueError(f"{existing_path}: addresses already in another inventory: {sorted(overlap)}")
        existing_rows.extend(rows)
        existing_addresses |= addresses
        for category, values in categories.items():
            for key, value in values.items():
                existing_categories[category][key] += value
    retained_rows, _, retained_by_incident, verification_block = load_retained(
        retained_path, output_path.parent
    )
    retained_positive_addresses = {
        row["address_hex"] for row in retained_rows
    }
    overlap = existing_addresses & retained_positive_addresses
    if overlap:
        raise ValueError(
            "retained historical-hack addresses overlap the existing "
            f"non-issuance inventory: {sorted(overlap)}"
        )

    retained_summary = json.loads(retained_summary_path.read_text())
    if retained_summary["block"] != verification_block:
        raise ValueError("retained summary block does not match balance rows")
    if retained_summary["changed_from_sep10"] != 0:
        raise ValueError("retained summary reports post-cutoff balance changes")
    for incident, values in retained_by_incident.items():
        expected = retained_summary["incidents"][incident]
        if values["input_addresses"] != expected["addresses"]:
            raise ValueError(f"{incident}: input address count mismatch")
        if str(values["retained_cap_atto"]) != expected["retained_cap_atto"]:
            raise ValueError(f"{incident}: retained cap mismatch")
        if values["above_1000_one"] != expected["above_1000_one"]:
            raise ValueError(f"{incident}: large-address count mismatch")

    claim_summary = json.loads(claim_summary_path.read_text())
    gross_claim = int(claim_summary["total_claim_atto"])
    existing_total = sum(
        values["atto"] for values in existing_categories.values()
    )
    retained_total = sum(
        values["retained_cap_atto"]
        for values in retained_by_incident.values()
    )
    leak_section = None
    leak_total = 0
    leak_sources = {}
    if args.rollback_leak_retention:
        if not args.rollback_leak_summary:
            raise ValueError("--rollback-leak-retention needs --rollback-leak-summary")
        leak_path = Path(args.rollback_leak_retention)
        leak_summary_path = Path(args.rollback_leak_summary)
        leak_addresses, leak_by_incident, leak_total, leak_overlap, leak_summary = load_rollback_leak(
            leak_path,
            leak_summary_path,
            {row["address_hex"]: int(row["retained_cap_atto"]) for row in retained_rows},
            {row["address_hex"].lower(): int(row["not_issued_atto"]) for row in existing_rows},
        )
        leak_section = {
            "rule": leak_summary["rule"],
            "leak_receipts": leak_summary["leak_receipts"],
            "credited_recipients": leak_summary["credited_recipients"],
            "unbacked_credit_atto": leak_summary["unbacked_credit_atto"],
            "unbacked_credit_one": leak_summary["unbacked_credit_one"],
            "positive_addresses": len(leak_addresses),
            "by_incident": {
                incident: {
                    "positive_addresses": values["positive_addresses"],
                    "unbacked_credit_atto": str(values["unbacked_credit_atto"]),
                    "unbacked_credit_one": one(values["unbacked_credit_atto"]),
                    "not_issued_atto": str(values["not_issued_atto"]),
                    "not_issued_one": one(values["not_issued_atto"]),
                }
                for incident, values in sorted(leak_by_incident.items())
            },
            "not_issued_atto": str(leak_total),
            "not_issued_one": one(leak_total),
            "addresses_also_in_retained_initial_addresses": leak_overlap,
            "overlap_note": (
                "an address in both lists loses its retained cap first and then "
                "the rollback-leak amount from what remains"
            ),
        }
        leak_sources = {
            "rollback_leak_retention": {"name": portable_source_name(leak_path), "sha256": sha256(leak_path)},
            "rollback_leak_summary": {"name": portable_source_name(leak_summary_path),
                                      "sha256": sha256(leak_summary_path)},
        }
    combined = existing_total + retained_total + leak_total
    if combined > gross_claim:
        raise ValueError("combined non-issuance exceeds the gross cutoff claim")

    write_csv(output_path, retained_rows, args.replace)
    summary = {
        "_provenance": {
            "classification": "policy scenario",
            "factual_input": (
                "RPC-derived fixed-block balances capped by incident-contract "
                "distribution amounts"
            ),
            "note": (
                "The retained-balance measurement is factual; treating the "
                "capped amount as not issued is a migration policy."
            ),
        },
        "schema_version": 1,
        "status": "passed",
        "cutoff": {
            "claim_block_shard0": int(retained_rows[0]["cutoff_block"]),
            "balance_verification_block": verification_block,
            "balance_verification_hash": retained_summary["block_hash"],
            "balance_verification_utc": retained_summary["block_utc"],
            "queried_at_utc": retained_summary["queried_at_utc"],
            "all_balances_unchanged_from_cutoff": True,
        },
        "policy": {
            "scope": (
                "incident and retained-fund non-issuance component; not the "
                "complete staged migration policy"
            ),
            "migration_treatment": "not_issued",
            "old_chain_gross_claim_changed": False,
            "migration_allocation_reduced": True,
            "fixed_erc20_total_supply_changed": False,
            "treasury_destination": None,
            "available_for_other_use": False,
            "composite_policy_summary": (
                "results/2026-09-17/migration-policy-reconciliation.json"
            ),
            "retained_historical_hack_rule": (
                "for each initial recipient, omit min(initial incident-contract "
                "distribution, cutoff balance)"
            ),
            "extra_mint_partial_rows": (
                "only the reviewed extra-mint portion is omitted; a legitimate "
                "remainder stays eligible under the separate migration policy"
            ),
        },
        "existing_non_issuance": {
            "inventory_rows": len(existing_rows),
            "positive_addresses": sum(
                values["positive_rows"] for values in existing_categories.values()
            ),
            "categories": {
                category: {
                    "inventory_rows": values["rows"],
                    "positive_addresses": values["positive_rows"],
                    "not_issued_atto": str(values["atto"]),
                    "not_issued_one": one(values["atto"]),
                }
                for category, values in sorted(existing_categories.items())
            },
            "not_issued_atto": str(existing_total),
            "not_issued_one": one(existing_total),
        },
        "historical_hack_retained_initial_addresses": {
            "positive_addresses": len(retained_rows),
            "by_incident": {
                incident: {
                    "input_addresses": values["input_addresses"],
                    "positive_addresses": values["positive_addresses"],
                    "above_1000_one": values["above_1000_one"],
                    "not_issued_atto": str(values["retained_cap_atto"]),
                    "not_issued_one": one(values["retained_cap_atto"]),
                }
                for incident, values in sorted(retained_by_incident.items())
            },
            "not_issued_atto": str(retained_total),
            "not_issued_one": one(retained_total),
            "overlap_with_existing_non_issuance_addresses": 0,
        },
        **({"rollback_leak_credited_recipients": leak_section} if leak_section else {}),
        "totals": {
            "gross_cutoff_claim_atto": str(gross_claim),
            "gross_cutoff_claim_one": one(gross_claim),
            "not_issued_atto": str(combined),
            "not_issued_one": one(combined),
            "remaining_full_claim_after_non_issuance_atto": str(
                gross_claim - combined
            ),
            "remaining_full_claim_after_non_issuance_one": one(
                gross_claim - combined
            ),
        },
        "evidence_limits": [
            (
                "retained cap is balance-supported incident provenance, not "
                "proof that every address is controlled by one person"
            ),
            (
                "the incident-contract distribution included some seed or "
                "pre-existing value, so the cap is a migration-policy amount "
                "rather than a claim that every retained unit was newly created"
            ),
            (
                "exchange reserves and downstream mixed-fund balances are not "
                "added to the retained initial-recipient amount"
            ),
            (
                "reported victims are not omitted merely because they appear "
                "in an investigation report"
            ),
        ],
        "outputs": {
            "retained_not_issued_csv": output_path.name,
            "retained_not_issued_csv_sha256": sha256(output_path),
            "retained_not_issued_rows": len(retained_rows),
        },
        "sources": {
            "existing_non_issuance": [
                {"name": portable_source_name(path), "sha256": sha256(path)}
                for path in existing_paths
            ],
            "retained_balances": {
                "name": portable_source_name(retained_path),
                "sha256": sha256(retained_path),
            },
            "retained_summary": {
                "name": portable_source_name(retained_summary_path),
                "sha256": sha256(retained_summary_path),
            },
            "cutoff_claim_summary": {
                "name": portable_source_name(claim_summary_path),
                "sha256": sha256(claim_summary_path),
            },
            **leak_sources,
        },
    }
    if leak_section:
        summary["policy"]["rollback_leak_credit_rule"] = leak_section["rule"]
    write_json(summary_path, summary, args.replace)
    print(
        json.dumps(
            {
                "status": "passed",
                "retained_rows": len(retained_rows),
                "retained_not_issued_atto": str(retained_total),
                "rollback_leak_not_issued_atto": str(leak_total),
                "combined_not_issued_atto": str(combined),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
