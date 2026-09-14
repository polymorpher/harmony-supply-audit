#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
CX_PRECOMPILE = "0x00000000000000000000000000000000000000f9"
CX_SELECTOR = bytes.fromhex("28480800")
CALL_TYPES = {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"}
FINAL_CLASSIFICATIONS = {
    "rollback_leak",
    "source_debit_absent",
    "valid_source_debit",
}
EVIDENCE_STATUS_CLASSIFICATION = {
    "absent": "source_debit_absent",
    "persisted": "valid_source_debit",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TX_HASH_RE = re.compile(r"^0x[0-9a-f]{64}$")


def bech32_polymod(values):
    generators = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for index, generator in enumerate(generators):
            if (top >> index) & 1:
                checksum ^= generator
    return checksum


def hrp_expand(hrp):
    return [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]


def convert_bits(values, from_bits, to_bits):
    accumulator = 0
    bits = 0
    output = []
    maximum = (1 << to_bits) - 1
    for value in values:
        accumulator = (accumulator << from_bits) | value
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            output.append((accumulator >> bits) & maximum)
    if bits and ((accumulator << (to_bits - bits)) & maximum):
        raise ValueError("nonzero address padding")
    return bytes(output)


def decode_address(value):
    if value is None:
        return ""
    if value.startswith("0x"):
        return value.lower()
    if value != value.lower() or not value.startswith("one1"):
        raise ValueError(f"invalid Harmony address {value!r}")
    separator = value.rfind("1")
    hrp = value[:separator]
    data = [CHARSET.index(char) for char in value[separator + 1 :]]
    if len(data) < 6 or bech32_polymod(hrp_expand(hrp) + data) != 1:
        raise ValueError(f"invalid Harmony address checksum {value!r}")
    decoded = convert_bits(data[:-6], 5, 8)
    if len(decoded) != 20:
        raise ValueError(f"invalid Harmony address length {value!r}")
    return "0x" + decoded.hex()


def rpc(url, method, params):
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    for attempt in range(5):
        try:
            request = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.load(response)
            if result.get("error"):
                raise RuntimeError(result["error"])
            return result["result"]
        except (OSError, RuntimeError, urllib.error.HTTPError):
            if attempt == 4:
                raise
            time.sleep(2**attempt)


def row_integer(row, names):
    for name in names:
        if name in row and row[name] != "":
            return int(row[name])
    raise KeyError(f"expected one of {', '.join(names)}")


def row_text(row, names):
    for name in names:
        if name in row and row[name] != "":
            return row[name]
    raise KeyError(f"expected one of {', '.join(names)}")


def receipt_identity(row):
    identity = {
        "source_shard": row_integer(
            row, ("audit_source_shard", "signed_source_shard", "source_shard")
        ),
        "destination_shard": row_integer(
            row, ("audit_destination_shard", "destination_shard", "to_shard")
        ),
        "source_block": row_integer(
            row, ("audit_source_block", "signed_source_block", "source_block")
        ),
        "source_block_hash": row_text(
            row,
            (
                "audit_source_block_hash",
                "signed_source_header_hash",
                "source_block_hash",
                "claimed_source_block_hash",
            ),
        ).lower(),
        "receipt_index": row_integer(row, ("receipt_index",)),
        "tx_hash": row["tx_hash"].lower(),
        "from": decode_address(row["from"]),
        "to": decode_address(row["to"]),
        "amount_atto": int(row["amount_atto"]),
    }
    if not TX_HASH_RE.fullmatch(identity["source_block_hash"]):
        raise ValueError("source block hash is not a 32-byte hash")
    if not TX_HASH_RE.fullmatch(identity["tx_hash"]):
        raise ValueError("receipt transaction hash is not a transaction hash")
    return identity


def evidence_key(identity):
    return (
        identity["source_shard"],
        identity["destination_shard"],
        identity["source_block"],
        identity["source_block_hash"],
        identity["receipt_index"],
        identity["tx_hash"],
        identity["from"],
        identity["to"],
        identity["amount_atto"],
    )


def file_sha256(path):
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_independent_evidence(paths):
    evidence = {}
    for path in paths:
        evidence_path = Path(path)
        with evidence_path.open(newline="") as source:
            for row_number, row in enumerate(csv.DictReader(source), 2):
                identity = {
                    "source_shard": row_integer(row, ("source_shard",)),
                    "destination_shard": row_integer(row, ("destination_shard",)),
                    "source_block": row_integer(row, ("source_block",)),
                    "source_block_hash": row["source_block_hash"].lower(),
                    "receipt_index": row_integer(row, ("receipt_index",)),
                    "tx_hash": row["receipt_tx_hash"].lower(),
                    "from": decode_address(row["from"]),
                    "to": decode_address(row["to"]),
                    "amount_atto": int(row["amount_atto"]),
                }
                if not TX_HASH_RE.fullmatch(identity["source_block_hash"]):
                    raise ValueError(
                        f"{path}:{row_number}: source_block_hash is not a 32-byte hash"
                    )
                if not TX_HASH_RE.fullmatch(identity["tx_hash"]):
                    raise ValueError(
                        f"{path}:{row_number}: receipt_tx_hash is not a transaction hash"
                    )
                status = row["source_debit_status"].lower()
                if status not in EVIDENCE_STATUS_CLASSIFICATION:
                    raise ValueError(
                        f"{path}:{row_number}: source_debit_status must be "
                        "'absent' or 'persisted'"
                    )
                evidence_type = row["evidence_type"].strip()
                reference = row["evidence_reference"].strip()
                digest = row["evidence_sha256"].strip().lower()
                if not evidence_type or not reference:
                    raise ValueError(
                        f"{path}:{row_number}: evidence type and reference are required"
                    )
                if not SHA256_RE.fullmatch(digest):
                    raise ValueError(
                        f"{path}:{row_number}: evidence_sha256 is not a SHA-256 digest"
                    )
                artifact_path = Path(reference)
                if not artifact_path.is_absolute():
                    artifact_path = evidence_path.parent / artifact_path
                if not artifact_path.is_file():
                    raise ValueError(
                        f"{path}:{row_number}: evidence artifact does not exist: "
                        f"{reference}"
                    )
                actual_digest = file_sha256(artifact_path)
                if actual_digest != digest:
                    raise ValueError(
                        f"{path}:{row_number}: evidence SHA-256 mismatch for "
                        f"{reference}"
                    )
                key = evidence_key(identity)
                if key in evidence:
                    raise ValueError(f"{path}:{row_number}: duplicate evidence for {key}")
                evidence[key] = {
                    "classification": EVIDENCE_STATUS_CLASSIFICATION[status],
                    "source_debit_status": status,
                    "type": evidence_type,
                    "reference": reference,
                    "sha256": digest,
                }
    return evidence


def parse_precompile_input(value):
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    try:
        raw = bytes.fromhex(value[2:])
    except ValueError:
        return None
    if len(raw) < 100 or raw[:4] != CX_SELECTOR:
        return None
    address_word = raw[36:68]
    shard_word = raw[68:100]
    return {
        "amount_atto": int.from_bytes(raw[4:36], "big"),
        "to": "0x" + address_word[12:].hex(),
        "destination_shard": int.from_bytes(shard_word[28:], "big"),
    }


def inspect_trace(root, identity):
    result = {
        "precompile_call_count": 0,
        "completed_precompile_call_count": 0,
        "precompile_payload_match_count": 0,
        "completed_precompile_payload_match_count": 0,
        "failed_precompile_path_count": 0,
        "failed_matching_precompile_path_count": 0,
    }

    def visit(node, failed_nonroot_ancestor, context_sender, is_root=False):
        call_type = str(node.get("type", "")).upper()
        is_precompile_call = (
            str(node.get("to", "")).lower() == CX_PRECOMPILE
            and call_type in CALL_TYPES
        )
        if is_precompile_call:
            result["precompile_call_count"] += 1
            payload = parse_precompile_input(node.get("input"))
            payload_matches = bool(
                payload
                and payload["amount_atto"] == identity["amount_atto"]
                and context_sender == identity["from"]
                and payload["to"] == identity["to"]
                and payload["destination_shard"] == identity["destination_shard"]
            )
            if payload_matches:
                result["precompile_payload_match_count"] += 1
            # A rejected invocation did not create a receipt. Only a locally
            # completed, payload-matching invocation can authenticate this
            # receipt and show whether an inner ancestor reverted its debit.
            if not node.get("error"):
                result["completed_precompile_call_count"] += 1
                if payload_matches:
                    result["completed_precompile_payload_match_count"] += 1
                if failed_nonroot_ancestor:
                    result["failed_precompile_path_count"] += 1
                    if payload_matches:
                        result["failed_matching_precompile_path_count"] += 1
        failed_for_children = failed_nonroot_ancestor or (
            not is_root and bool(node.get("error"))
        )
        for child in node.get("calls", []):
            child_type = str(child.get("type", "")).upper()
            child_sender = (
                context_sender
                if child_type == "DELEGATECALL"
                else str(child.get("from", "")).lower()
            )
            visit(child, failed_for_children, child_sender)

    visit(root, False, str(root.get("from", "")).lower(), is_root=True)
    return result


def classify_replay(receipt_status, trace, inspection):
    trace_status = 0 if trace.get("error") else 1
    if receipt_status != 1:
        return (
            "replay_incompatible",
            False,
            "canonical outgoing receipt has a failed source transaction status",
            trace_status,
        )
    if trace_status != receipt_status:
        return (
            "replay_incompatible",
            False,
            "replay root outcome disagrees with the stored source receipt",
            trace_status,
        )
    if inspection["completed_precompile_call_count"] != 1:
        return (
            "unclassified",
            True,
            "replay does not contain exactly one locally completed precompile call",
            trace_status,
        )
    if inspection["completed_precompile_payload_match_count"] != 1:
        return (
            "unclassified",
            True,
            "completed precompile call does not authenticate the canonical receipt",
            trace_status,
        )
    if inspection["failed_matching_precompile_path_count"] == 1:
        return "rollback_leak", True, "", trace_status
    return "valid_source_debit", True, "", trace_status


def resolve_classification(direct_classification, replay_classification, evidence):
    replay_final = (
        direct_classification
        if direct_classification is not None
        else replay_classification
    )
    evidence_classification = evidence["classification"] if evidence else ""
    if evidence:
        status = evidence["source_debit_status"]
        conflict = (
            replay_final == "valid_source_debit" and status == "absent"
        ) or (
            replay_final == "rollback_leak" and status == "persisted"
        )
        if conflict:
            raise ValueError(
                "independent source-debit evidence conflicts with "
                f"{replay_final} classification"
            )
        if replay_final in ("rollback_leak", "valid_source_debit"):
            if direct_classification is not None:
                source = "direct_transaction_and_independent_evidence"
            else:
                source = "compatible_replay_and_independent_evidence"
            return replay_final, source, evidence_classification
        return (
            evidence_classification,
            "independent_source_debit_evidence",
            evidence_classification,
        )
    if replay_final in FINAL_CLASSIFICATIONS:
        return (
            replay_final,
            "direct_transaction"
            if direct_classification is not None
            else "compatible_replay",
            "",
        )
    return "unclassified", "unresolved", ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-source-block", type=int, default=0)
    parser.add_argument("--max-source-block", type=int)
    parser.add_argument("--source-shard", type=int)
    parser.add_argument("--destination-shard", type=int)
    parser.add_argument("--address", action="append", default=[])
    parser.add_argument(
        "--independent-evidence",
        action="append",
        default=[],
        help=(
            "CSV binding the complete canonical receipt identity to "
            "source_debit_status, evidence_type, a local evidence_reference, "
            "and evidence_sha256"
        ),
    )
    parser.add_argument("receipts", nargs="+")
    args = parser.parse_args()
    addresses = {address.lower() for address in args.address}
    independent_evidence = load_independent_evidence(args.independent_evidence)

    rows = []
    for path in args.receipts:
        with open(path, newline="") as source:
            for row in csv.DictReader(source):
                source_block = row_integer(
                    row, ("signed_source_block", "source_block")
                )
                source_block_hash = row_text(
                    row,
                    (
                        "signed_source_header_hash",
                        "source_block_hash",
                        "claimed_source_block_hash",
                    ),
                ).lower()
                try:
                    source_shard = row_integer(
                        row, ("signed_source_shard", "source_shard")
                    )
                except KeyError as error:
                    if args.source_shard is None:
                        raise ValueError(
                            f"{path}: source shard is absent; pass --source-shard"
                        ) from error
                    source_shard = args.source_shard
                try:
                    destination_shard = row_integer(
                        row, ("destination_shard", "to_shard")
                    )
                except KeyError as error:
                    if args.destination_shard is None:
                        raise ValueError(
                            f"{path}: destination shard is absent; "
                            "pass --destination-shard"
                        ) from error
                    destination_shard = args.destination_shard
                if source_block < args.min_source_block:
                    continue
                if (
                    args.max_source_block is not None
                    and source_block > args.max_source_block
                ):
                    continue
                if (
                    args.source_shard is not None
                    and source_shard != args.source_shard
                ):
                    continue
                if (
                    args.destination_shard is not None
                    and destination_shard != args.destination_shard
                ):
                    continue
                if addresses and row["from"].lower() not in addresses:
                    continue
                row["receipt_file"] = path
                row["audit_source_block"] = str(source_block)
                row["audit_source_block_hash"] = source_block_hash
                row["audit_source_shard"] = str(source_shard)
                row["audit_destination_shard"] = str(destination_shard)
                rows.append(row)
    rows.sort(key=lambda row: int(row["audit_source_block"]))
    row_keys = [evidence_key(receipt_identity(row)) for row in rows]
    if len(row_keys) != len(set(row_keys)):
        raise ValueError("duplicate canonical receipt rows in selected inputs")

    totals = {
        "rollback_leak": 0,
        "source_debit_absent": 0,
        "valid_source_debit": 0,
        "unclassified": 0,
    }
    replay_totals = {
        "rollback_leak": 0,
        "valid_source_debit": 0,
        "replay_incompatible": 0,
        "unclassified": 0,
        "not_traced": 0,
    }
    independent_evidence_count = 0
    independent_evidence_amount = 0
    used_evidence_keys = set()
    output_rows = []
    for index, row in enumerate(rows, 1):
        identity = receipt_identity(row)
        evidence = independent_evidence.get(evidence_key(identity))
        transaction = rpc(
            args.rpc, "hmyv2_getTransactionByHash", [row["tx_hash"]]
        )
        if transaction is None:
            raise RuntimeError(f"source transaction missing: {row['tx_hash']}")
        transaction_hashes = {
            transaction["hash"].lower(),
            transaction["ethHash"].lower(),
        }
        if row["tx_hash"].lower() not in transaction_hashes:
            raise RuntimeError(f"source transaction hash mismatch: {row['tx_hash']}")
        amount = identity["amount_atto"]
        source_to = decode_address(transaction.get("to"))
        direct_source_debit = (
            source_to == CX_PRECOMPILE
            or transaction["shardID"] != transaction["toShardID"]
        )
        if direct_source_debit:
            receipt_status = ""
            trace = {}
            inspection = {
                "precompile_call_count": int(source_to == CX_PRECOMPILE),
                "completed_precompile_call_count": "",
                "precompile_payload_match_count": "",
                "completed_precompile_payload_match_count": "",
                "failed_precompile_path_count": 0,
                "failed_matching_precompile_path_count": 0,
            }
            replay_classification = "not_traced"
            replay_compatible = ""
            replay_issue = ""
            replay_status = ""
            direct_classification = "valid_source_debit"
        else:
            receipt = rpc(
                args.rpc, "hmyv2_getTransactionReceipt", [transaction["hash"]]
            )
            if receipt is None:
                raise RuntimeError(
                    f"source transaction receipt missing: {transaction['hash']}"
                )
            receipt_status = int(receipt["status"])
            trace = rpc(
                args.rpc,
                "debug_traceTransaction",
                [transaction["hash"], {"tracer": "callTracer", "timeout": "60s"}],
            )
            inspection = inspect_trace(trace, identity)
            (
                replay_classification,
                replay_compatible,
                replay_issue,
                replay_status,
            ) = classify_replay(
                receipt_status, trace, inspection
            )
            direct_classification = None
        if evidence and not direct_source_debit and receipt_status != 1:
            raise ValueError(
                f"{row['tx_hash']}: independent evidence cannot override "
                "a failed stored source transaction receipt"
            )
        try:
            (
                classification,
                classification_source,
                independent_evidence_classification,
            ) = resolve_classification(
                direct_classification, replay_classification, evidence
            )
        except ValueError as error:
            raise ValueError(f"{row['tx_hash']}: {error}") from error
        totals[classification] += amount
        replay_totals[replay_classification] += amount
        if evidence:
            independent_evidence_count += 1
            independent_evidence_amount += amount
            used_evidence_keys.add(evidence_key(identity))
        output_rows.append(
            {
                **row,
                "source_transaction_hash": transaction["hash"],
                "source_transaction_from": decode_address(transaction["from"]),
                "source_transaction_to": source_to,
                "source_transaction_value_atto": transaction["value"],
                "source_transaction_status": receipt_status,
                "source_input_selector": transaction["input"][:10],
                "trace_root_error": trace.get("error", ""),
                "replay_status": replay_status,
                "replay_compatible": replay_compatible,
                "replay_issue": replay_issue,
                **inspection,
                "replay_classification": replay_classification,
                "independent_evidence_classification": (
                    independent_evidence_classification
                ),
                "independent_source_debit_status": (
                    evidence["source_debit_status"] if evidence else ""
                ),
                "independent_evidence_type": evidence["type"] if evidence else "",
                "independent_evidence_reference": (
                    evidence["reference"] if evidence else ""
                ),
                "independent_evidence_sha256": (
                    evidence["sha256"] if evidence else ""
                ),
                "classification_source": classification_source,
                "classification": classification,
            }
        )
        print(
            f"{index}/{len(rows)} source_block={row['audit_source_block']} "
            f"amount={amount} replay={replay_classification} "
            f"classification={classification}",
            flush=True,
        )

    unused_evidence = set(independent_evidence) - used_evidence_keys
    if unused_evidence:
        raise ValueError(
            f"{len(unused_evidence)} independent evidence rows did not match "
            "the selected canonical receipts"
        )

    fields = list(output_rows[0]) if output_rows else []
    with open(args.output, "x", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    print(
        json.dumps(
            {
                "receipts": len(rows),
                "rollback_leak_atto": str(totals["rollback_leak"]),
                "source_debit_absent_atto": str(
                    totals["source_debit_absent"]
                ),
                "valid_source_debit_atto": str(totals["valid_source_debit"]),
                "unclassified_atto": str(totals["unclassified"]),
                "replay_rollback_leak_atto": str(
                    replay_totals["rollback_leak"]
                ),
                "replay_valid_source_debit_atto": str(
                    replay_totals["valid_source_debit"]
                ),
                "replay_incompatible_atto": str(
                    replay_totals["replay_incompatible"]
                ),
                "replay_unclassified_atto": str(
                    replay_totals["unclassified"]
                ),
                "not_traced_atto": str(replay_totals["not_traced"]),
                "independent_evidence_receipts": independent_evidence_count,
                "independent_evidence_atto": str(independent_evidence_amount),
                "independent_evidence_supplied": len(independent_evidence),
                "independent_evidence_unused": (
                    len(independent_evidence) - len(used_evidence_keys)
                ),
                "output": args.output,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
