#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import os
from collections import Counter


CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
GENERATOR = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
ATTO_PER_ONE = 10**18
COMPONENTS = (
    "liquid_shard0",
    "liquid_shard1",
    "active_staked_or_delegated",
    "pending_undelegation",
    "unclaimed_staking_reward",
    "pending_cross_shard",
    "total_claim",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Audit a Harmony address list against an exact cutoff claim CSV"
    )
    parser.add_argument("--addresses", required=True)
    parser.add_argument("--claims", required=True)
    parser.add_argument("--claims-sha256", required=True)
    parser.add_argument("--csv-output", required=True)
    parser.add_argument("--summary-output", required=True)
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def polymod(values):
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for index, generator in enumerate(GENERATOR):
            if (top >> index) & 1:
                checksum ^= generator
    return checksum


def decode_bech32(address):
    if address != address.lower() or not address.startswith("one1"):
        raise ValueError(f"invalid Harmony address: {address}")
    separator = address.rfind("1")
    hrp = address[:separator]
    try:
        data = [CHARSET.index(char) for char in address[separator + 1 :]]
    except ValueError as error:
        raise ValueError(f"invalid Harmony address character: {address}") from error
    expanded_hrp = [ord(char) >> 5 for char in hrp]
    expanded_hrp += [0]
    expanded_hrp += [ord(char) & 31 for char in hrp]
    if polymod(expanded_hrp + data) != 1:
        raise ValueError(f"invalid Harmony address checksum: {address}")
    accumulator = 0
    bits = 0
    decoded = bytearray()
    for value in data[:-6]:
        accumulator = (accumulator << 5) | value
        bits += 5
        while bits >= 8:
            bits -= 8
            decoded.append((accumulator >> bits) & 0xFF)
    if bits and accumulator & ((1 << bits) - 1):
        raise ValueError(f"nonzero Harmony address padding: {address}")
    if len(decoded) != 20:
        raise ValueError(f"Harmony address is not 20 bytes: {address}")
    return "0x" + decoded.hex()


def one(atto):
    return f"{atto // ATTO_PER_ONE}.{atto % ATTO_PER_ONE:018d}"


def main():
    args = parse_args()
    for path in (args.csv_output, args.summary_output):
        if os.path.exists(path) or os.path.exists(path + ".partial"):
            raise FileExistsError(path)

    with open(args.addresses, encoding="utf-8") as source:
        input_addresses = [
            line.strip()
            for line in source
            if line.strip() and not line.lstrip().startswith("#")
        ]
    counts = Counter(input_addresses)
    unique_addresses = list(dict.fromkeys(input_addresses))
    address_hex = {address: decode_bech32(address) for address in unique_addresses}
    if len(set(address_hex.values())) != len(address_hex):
        raise ValueError("different input strings decode to the same 20-byte address")
    by_hex = {value: key for key, value in address_hex.items()}

    required = {
        "secure_key",
        "address",
        "claims_shard0_block",
        "claims_shard1_block",
        "nonce_shard0",
        "nonce_shard1",
        "code_hash_shard0",
        "code_hash_shard1",
        *(f"{component}_atto" for component in COMPONENTS),
        *(f"{component}_one" for component in COMPONENTS),
    }
    found = {}
    cutoff_pairs = set()
    with open(args.claims, newline="") as source:
        reader = csv.DictReader(source)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"claim CSV is missing fields: {sorted(missing)}")
        for row in reader:
            address = row["address"].lower()
            if address not in by_hex:
                continue
            if address in found:
                raise ValueError(f"duplicate claim row for {address}")
            found[address] = row
            cutoff_pairs.add(
                (int(row["claims_shard0_block"]), int(row["claims_shard1_block"]))
            )
    if len(cutoff_pairs) != 1:
        raise ValueError(f"unexpected cutoff pairs: {sorted(cutoff_pairs)}")
    shard0_block, shard1_block = next(iter(cutoff_pairs))

    fieldnames = [
        "input_order",
        "address_bech32",
        "address_hex",
        "duplicate_count_in_input",
        "cutoff_row_present",
        "secure_key",
        *(f"{component}_atto" for component in COMPONENTS),
        *(f"{component}_one" for component in COMPONENTS),
        "nonce_shard0",
        "nonce_shard1",
        "code_hash_shard0",
        "code_hash_shard1",
        "migration_action",
    ]
    rows = []
    totals = {component: 0 for component in COMPONENTS}
    for index, address in enumerate(unique_addresses, start=1):
        hex_address = address_hex[address]
        claim = found.get(hex_address)
        output = {
            "input_order": index,
            "address_bech32": address,
            "address_hex": hex_address,
            "duplicate_count_in_input": counts[address],
            "cutoff_row_present": str(claim is not None).lower(),
            "secure_key": claim["secure_key"] if claim else "",
            "nonce_shard0": claim["nonce_shard0"] if claim else "",
            "nonce_shard1": claim["nonce_shard1"] if claim else "",
            "code_hash_shard0": claim["code_hash_shard0"] if claim else "",
            "code_hash_shard1": claim["code_hash_shard1"] if claim else "",
            "migration_action": "not_set_by_balance_audit",
        }
        for component in COMPONENTS:
            value = int(claim[f"{component}_atto"]) if claim else 0
            if claim and claim[f"{component}_one"] != one(value):
                raise ValueError(f"atto/ONE mismatch for {address}: {component}")
            output[f"{component}_atto"] = str(value)
            output[f"{component}_one"] = one(value)
            totals[component] += value
        rows.append(output)

    csv_partial = args.csv_output + ".partial"
    summary_partial = args.summary_output + ".partial"
    try:
        with open(csv_partial, "x", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            output.flush()
            os.fsync(output.fileno())
        os.replace(csv_partial, args.csv_output)

        positive_rows = [
            row for row in rows if int(row["total_claim_atto"]) > 0
        ]
        top_rows = sorted(
            positive_rows,
            key=lambda row: (-int(row["total_claim_atto"]), row["address_bech32"]),
        )[:10]
        summary = {
            "status": "passed",
            "addresses_input": args.addresses,
            "addresses_input_sha256": sha256(args.addresses),
            "claims_input": args.claims,
            "claims_input_sha256_from_cutoff_manifest": args.claims_sha256.lower(),
            "cutoff": {
                "shard0_block": shard0_block,
                "shard1_block": shard1_block,
            },
            "input_entries": len(input_addresses),
            "unique_addresses": len(unique_addresses),
            "duplicate_entries": {
                address: count
                for address, count in sorted(counts.items())
                if count > 1
            },
            "positive_claim_addresses": len(positive_rows),
            "zero_or_absent_addresses": len(rows) - len(positive_rows),
            "cutoff_rows_present": len(found),
            "component_totals_atto": {
                component: str(value) for component, value in totals.items()
            },
            "component_totals_one": {
                component: one(value) for component, value in totals.items()
            },
            "zero_or_absent_address_list": [
                row["address_bech32"]
                for row in rows
                if int(row["total_claim_atto"]) == 0
            ],
            "top_ten_by_total_claim": [
                {
                    "address_bech32": row["address_bech32"],
                    "address_hex": row["address_hex"],
                    "total_claim_atto": row["total_claim_atto"],
                    "total_claim_one": row["total_claim_one"],
                }
                for row in top_rows
            ],
            "migration_policy": {
                "action": "none; join this balance audit to incident-specific evidence before routing",
                "deduct_from_total_claim": False,
            },
            "csv_output": args.csv_output,
            "csv_output_sha256": sha256(args.csv_output),
        }
        with open(summary_partial, "x", encoding="utf-8") as output:
            json.dump(summary, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(summary_partial, args.summary_output)
        print(json.dumps(summary, sort_keys=True))
    except BaseException:
        for path in (csv_partial, summary_partial):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        raise


if __name__ == "__main__":
    main()
