#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
from pathlib import Path


DEFAULT_GENESIS_ATTO = 12_600_000_000 * 10**18
DEFAULT_PRE_STAKING_ATTO = 319_237_464 * 10**18


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Reconstruct the cutoff supply formula from a node-local reward "
            "counter and state-derived validator lifetime-reward sums"
        )
    )
    parser.add_argument("--base-accumulator", required=True)
    parser.add_argument("--base-supply", required=True)
    parser.add_argument("--cutoff-supply", required=True)
    parser.add_argument("--output")
    parser.add_argument(
        "--genesis-atto", type=int, default=DEFAULT_GENESIS_ATTO
    )
    parser.add_argument(
        "--pre-staking-rewards-atto",
        type=int,
        default=DEFAULT_PRE_STAKING_ATTO,
    )
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_integer(path, field):
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if field not in value:
        raise KeyError(f"{path}: missing {field}")
    return int(value[field])


def reconstruct(
    genesis_atto,
    pre_staking_rewards_atto,
    base_accumulator_atto,
    base_wrapper_rewards_atto,
    cutoff_wrapper_rewards_atto,
):
    wrapper_delta = cutoff_wrapper_rewards_atto - base_wrapper_rewards_atto
    if wrapper_delta < 0:
        raise ValueError("cutoff wrapper rewards are below the base checkpoint")
    reconstructed_accumulator = base_accumulator_atto + wrapper_delta
    formula_before_exclusions = (
        genesis_atto
        + pre_staking_rewards_atto
        + reconstructed_accumulator
    )
    return {
        "genesis_atto": str(genesis_atto),
        "pre_staking_rewards_atto": str(pre_staking_rewards_atto),
        "base_accumulator_atto": str(base_accumulator_atto),
        "base_wrapper_rewards_atto": str(base_wrapper_rewards_atto),
        "cutoff_wrapper_rewards_atto": str(cutoff_wrapper_rewards_atto),
        "wrapper_reward_delta_atto": str(wrapper_delta),
        "reconstructed_accumulator_atto": str(reconstructed_accumulator),
        "formula_before_exclusions_atto": str(formula_before_exclusions),
    }


def write_json(path, value):
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(encoded, end="")
        return
    partial = Path(str(path) + ".partial")
    if partial.exists():
        raise FileExistsError(partial)
    with partial.open("x", encoding="utf-8") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial, path)


def main():
    args = parse_args()
    base_accumulator = Path(args.base_accumulator)
    base_supply = Path(args.base_supply)
    cutoff_supply = Path(args.cutoff_supply)
    result = reconstruct(
        args.genesis_atto,
        args.pre_staking_rewards_atto,
        load_integer(base_accumulator, "reward_atto"),
        load_integer(base_supply, "validator_lifetime_block_reward_atto"),
        load_integer(cutoff_supply, "validator_lifetime_block_reward_atto"),
    )
    result.update(
        {
            "schema_version": 1,
            "method": (
                "base node-local accumulator plus the state-derived increase "
                "in validator lifetime BlockReward"
            ),
            "sources": {
                "base_accumulator": {
                    "path": str(base_accumulator),
                    "sha256": sha256(base_accumulator),
                },
                "base_supply": {
                    "path": str(base_supply),
                    "sha256": sha256(base_supply),
                },
                "cutoff_supply": {
                    "path": str(cutoff_supply),
                    "sha256": sha256(cutoff_supply),
                },
            },
        }
    )
    write_json(Path(args.output) if args.output else None, result)


if __name__ == "__main__":
    main()
