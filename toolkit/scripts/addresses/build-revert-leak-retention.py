#!/usr/bin/env python3

"""Withhold revert-leak credit from the wallets that received it.

A proven revert-leak receipt credited ONE to a destination wallet without a
matching debit anywhere. For every such destination the migration does not
issue the credited amount, capped at what the wallet still holds at cutoff
after earlier non-issuance: a wallet holding only exploit credit loses its
whole claim; a wallet that also held legitimate funds keeps the difference.
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import os
from collections import defaultdict
from pathlib import Path


ATTO = 10**18
# receipt classification values stored by cx-source-audit.py
LEAK_CLASSIFICATIONS = {"rollback_leak", "source_debit_absent"}
INCIDENT_LABELS = {
    "may-2025": "may-2025",
    "april-2026": "april-2026",
    "smaller-2026": "june-july-2026",
}
FIELDS = (
    "address_bech32",
    "address_hex",
    "incident",
    "unbacked_credit_atto",
    "leak_receipts",
    "cutoff_native_claim_atto",
    "prior_non_issuance_atto",
    "retained_cap_atto",
    "retained_cap_one",
    "cutoff_block",
    "source_evidence",
    "migration_treatment",
)

_audit_spec = importlib.util.spec_from_file_location(
    "non_issuance_audit", Path(__file__).with_name("build-non-issuance-audit.py")
)
_audit = importlib.util.module_from_spec(_audit_spec)
_audit_spec.loader.exec_module(_audit)
to_bech32 = _audit.to_bech32
portable_source_name = _audit.portable_source_name
one = _audit.one


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-audit", action="append", required=True,
                        help="cx-source-audit CSV with per-receipt classification; repeatable")
    parser.add_argument("--exploit-transactions", required=True,
                        help="historical-exploit-traced-transactions.csv, for incident labels")
    parser.add_argument("--claims", required=True,
                        help="all-address migration claims ledger at cutoff")
    parser.add_argument("--prior-retention", action="append", default=[],
                        help="earlier retained-cap export (retained_cap_atto); repeatable")
    parser.add_argument("--prior-non-issuance", action="append", default=[],
                        help="earlier non-issuance inventory (not_issued_atto); repeatable")
    parser.add_argument("--cutoff-block", type=int, default=93623067)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path, writer_function, replace):
    path = Path(path)
    partial = path.with_name(path.name + ".partial")
    if partial.exists():
        raise FileExistsError(partial)
    if path.exists() and not replace:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with partial.open("x", newline="", encoding="utf-8") as output:
        writer_function(output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial, path)


def load_leaks(paths, incident_by_tx):
    credit = defaultdict(int)
    receipts = defaultdict(int)
    incidents = defaultdict(set)
    seen = set()
    for path in paths:
        with open(path, newline="") as source:
            for line, row in enumerate(csv.DictReader(source), start=2):
                if row.get("classification") not in LEAK_CLASSIFICATIONS:
                    continue
                key = (row["tx_hash"].lower(), row.get("receipt_index", ""), row.get("destination_block", ""))
                if key in seen:
                    continue
                seen.add(key)
                address = row["to"].lower()
                amount = int(row["amount_atto"])
                if amount <= 0:
                    raise ValueError(f"{path}:{line}: non-positive leak receipt")
                credit[address] += amount
                receipts[address] += 1
                source_tx = (row.get("source_transaction_hash") or "").lower()
                incidents[address].add(incident_by_tx.get(source_tx, "unattributed"))
    return credit, receipts, incidents, len(seen)


def load_prior(paths, field):
    amounts = defaultdict(int)
    for path in paths:
        with open(path, newline="") as source:
            for row in csv.DictReader(source):
                amounts[row["address_hex"].lower()] += int(row[field])
    return amounts


def load_claims(path, wanted):
    claims = {}
    with open(path, newline="") as source:
        reader = csv.DictReader(source)
        for row in reader:
            address = row["address"].lower()
            if address in wanted:
                if address in claims:
                    raise ValueError(f"{path}: duplicate claim row for {address}")
                claims[address] = int(row["native_total_claim_atto"])
    return claims


def main():
    args = parse_args()
    incident_by_tx = {}
    with open(args.exploit_transactions, newline="") as source:
        for row in csv.DictReader(source):
            incident_by_tx[row["transaction_hash"].lower()] = row["incident"]

    credit, receipts, incidents, receipt_count = load_leaks(args.receipt_audit, incident_by_tx)
    prior = load_prior(args.prior_retention, "retained_cap_atto")
    for address, amount in load_prior(args.prior_non_issuance, "not_issued_atto").items():
        prior[address] += amount
    claims = load_claims(args.claims, set(credit))

    rows = []
    by_incident = defaultdict(lambda: {"recipients": 0, "unbacked_credit_atto": 0, "positive_rows": 0,
                                       "not_issued_atto": 0})
    for address in sorted(credit):
        labels = sorted(INCIDENT_LABELS.get(label, label) for label in incidents[address])
        incident = "+".join(labels)
        claim = claims.get(address, 0)
        remaining = max(claim - prior.get(address, 0), 0)
        withheld = min(credit[address], remaining)
        stats = by_incident[incident]
        stats["recipients"] += 1
        stats["unbacked_credit_atto"] += credit[address]
        if withheld == 0:
            continue
        stats["positive_rows"] += 1
        stats["not_issued_atto"] += withheld
        rows.append({
            "address_bech32": to_bech32(address),
            "address_hex": address,
            "incident": incident,
            "unbacked_credit_atto": str(credit[address]),
            "leak_receipts": str(receipts[address]),
            "cutoff_native_claim_atto": str(claim),
            "prior_non_issuance_atto": str(prior.get(address, 0)),
            "retained_cap_atto": str(withheld),
            "retained_cap_one": one(withheld),
            "cutoff_block": str(args.cutoff_block),
            "source_evidence": "proven revert-leak receipts (cx-source-audit classification)",
            "migration_treatment": "not_issued",
        })

    def write_rows(output):
        writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    write_atomic(args.output_csv, write_rows, args.replace)
    total_credit = sum(credit.values())
    total_withheld = sum(int(row["retained_cap_atto"]) for row in rows)
    summary = {
        "status": "passed",
        "_provenance": {
            "classification": "policy scenario",
            "factual_input": "proven revert-leak receipts and cutoff-pinned native claims",
            "note": "the credited amounts are factual; not issuing them is a migration policy",
        },
        "rule": (
            "for each destination credited by a proven revert-leak receipt, do not issue "
            "min(total credited, native cutoff claim minus earlier non-issuance)"
        ),
        "leak_classifications": sorted(LEAK_CLASSIFICATIONS),
        "leak_receipts": receipt_count,
        "credited_recipients": len(credit),
        "unbacked_credit_atto": str(total_credit),
        "unbacked_credit_one": one(total_credit),
        "positive_rows": len(rows),
        "not_issued_atto": str(total_withheld),
        "not_issued_one": one(total_withheld),
        "addresses_with_earlier_non_issuance": sorted(a for a in credit if prior.get(a)),
        "by_incident": {
            incident: {
                "recipients": values["recipients"],
                "unbacked_credit_atto": str(values["unbacked_credit_atto"]),
                "unbacked_credit_one": one(values["unbacked_credit_atto"]),
                "positive_rows": values["positive_rows"],
                "not_issued_atto": str(values["not_issued_atto"]),
                "not_issued_one": one(values["not_issued_atto"]),
            }
            for incident, values in sorted(by_incident.items())
        },
        "cutoff_block": args.cutoff_block,
        "sources": {
            "receipt_audits": [{"name": portable_source_name(Path(p)), "sha256": sha256(p)} for p in args.receipt_audit],
            "exploit_transactions": {"name": portable_source_name(Path(args.exploit_transactions)),
                                     "sha256": sha256(args.exploit_transactions)},
            "claims": {"name": portable_source_name(Path(args.claims)), "sha256": sha256(args.claims)},
            "prior_retention": [{"name": portable_source_name(Path(p)), "sha256": sha256(p)} for p in args.prior_retention],
            "prior_non_issuance": [{"name": portable_source_name(Path(p)), "sha256": sha256(p)} for p in args.prior_non_issuance],
        },
        "outputs": {
            "csv": Path(args.output_csv).name,
            "csv_sha256": sha256(args.output_csv),
            "rows": len(rows),
        },
    }

    def write_summary(output):
        json.dump(summary, output, indent=2, sort_keys=True)
        output.write("\n")

    write_atomic(args.summary_output, write_summary, args.replace)
    print(json.dumps({k: summary[k] for k in ("leak_receipts", "credited_recipients", "unbacked_credit_one",
                                              "positive_rows", "not_issued_one", "by_incident")}, indent=1))


if __name__ == "__main__":
    main()
