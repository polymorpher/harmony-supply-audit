#!/usr/bin/env python3

import argparse
import json
import os
import time
import urllib.request


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
                message = json.load(response)
            if message.get("error"):
                raise RuntimeError(message["error"])
            return message["result"]
        except (OSError, RuntimeError):
            if attempt == 4:
                raise
            time.sleep(2**attempt)


def one(atto):
    return f"{atto // 10**18}.{atto % 10**18:018d}"


def main():
    parser = argparse.ArgumentParser(
        description="Exactly reconstruct the December 2023 repeated-undelegation mint"
    )
    parser.add_argument("--rpc", default="https://a.api.s0.t.hmny.io")
    parser.add_argument("--block", type=int, default=51_085_312)
    parser.add_argument("--output")
    args = parser.parse_args()

    block = rpc(
        args.rpc,
        "hmyv2_getBlockByNumber",
        [args.block, {"fullTx": False}],
    )
    epoch = int(block["epoch"])
    last_paid_epoch = epoch - 1
    lock_period = 7

    validator_totals = {}
    delegator_totals = {}
    affected_entries = []
    delegators = set()
    entries = 0
    validators_scanned = 0
    page = 0
    while True:
        batch = rpc(
            args.rpc,
            "hmyv2_getAllValidatorInformationByBlockNumber",
            [page, args.block],
        )
        if not batch:
            break
        validators_scanned += len(batch)
        for information in batch:
            validator = information["validator"]
            validator_total = 0
            for delegation in validator["delegations"]:
                for undelegation in delegation["undelegations"]:
                    undelegation_epoch = int(undelegation["epoch"])
                    repeated_payouts = (
                        last_paid_epoch - (undelegation_epoch + lock_period)
                    )
                    if repeated_payouts <= 0:
                        continue
                    amount = int(undelegation["amount"])
                    repeated_mint = amount * repeated_payouts
                    delegator = delegation["delegator-address"]
                    validator_total += repeated_mint
                    delegator_totals[delegator] = (
                        delegator_totals.get(delegator, 0) + repeated_mint
                    )
                    affected_entries.append(
                        {
                            "validator": validator["address"],
                            "delegator": delegator,
                            "undelegation_epoch": undelegation_epoch,
                            "amount_atto": str(amount),
                            "repeated_payouts": repeated_payouts,
                            "mint_atto": str(repeated_mint),
                            "mint_one": one(repeated_mint),
                        }
                    )
                    delegators.add(delegator)
                    entries += 1
            if validator_total:
                validator_totals[validator["address"]] = validator_total
        page += 1

    total = sum(validator_totals.values())
    result = {
        "rpc": args.rpc,
        "block": args.block,
        "block_hash": block["hash"],
        "epoch": epoch,
        "last_paid_epoch": last_paid_epoch,
        "lock_period": lock_period,
        "validators_scanned": validators_scanned,
        "affected_validators": len(validator_totals),
        "affected_delegators": len(delegators),
        "bad_undelegation_entries": entries,
        "total_atto": str(total),
        "total_one": one(total),
        "by_validator": [
            {
                "validator": validator,
                "atto": str(amount),
                "one": one(amount),
            }
            for validator, amount in sorted(
                validator_totals.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "by_delegator": [
            {
                "delegator": delegator,
                "atto": str(amount),
                "one": one(amount),
            }
            for delegator, amount in sorted(
                delegator_totals.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "entries": sorted(
            affected_entries,
            key=lambda item: (
                item["validator"],
                item["delegator"],
                item["undelegation_epoch"],
            ),
        ),
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        partial = args.output + ".partial"
        if os.path.exists(args.output) or os.path.exists(partial):
            raise FileExistsError(args.output)
        try:
            with open(partial, "x", encoding="utf-8") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            os.replace(partial, args.output)
        except BaseException:
            try:
                os.remove(partial)
            except FileNotFoundError:
                pass
            raise
    print(encoded, end="")


if __name__ == "__main__":
    main()
