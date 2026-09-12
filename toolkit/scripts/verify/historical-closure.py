#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path


ATTO = 10**18


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Recompute historical state-versus-formula residuals from "
            "checkpoint measurements and named adjustments"
        )
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    return parser.parse_args()


def display_one(value):
    sign = "-" if value < 0 else ""
    value = abs(value)
    return f"{sign}{value // ATTO}.{value % ATTO:018d}"


def nested(value, field):
    for part in field.split("."):
        value = value[part]
    return value


def resolve(specification, base):
    if isinstance(specification, (int, str)):
        return int(specification)
    if not isinstance(specification, dict):
        raise TypeError(f"invalid value specification: {specification!r}")
    path = (base / specification["path"]).resolve()
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    return int(nested(value, specification["field"]))


def calculate(configuration, base):
    genesis = resolve(configuration["genesis_atto"], base)
    pre_staking = resolve(configuration["pre_staking_rewards_atto"], base)
    formula_base = genesis + pre_staking
    results = []
    previous_residual = None
    for point in configuration["checkpoints"]:
        shard0 = resolve(point["shard0_claims_atto"], base)
        shard1 = resolve(point["shard1_claims_atto"], base)
        accumulator = resolve(point["block_reward_accumulator_atto"], base)
        adjustments = {
            name: resolve(value, base)
            for name, value in point.get("adjustments_atto", {}).items()
        }
        state = shard0 + shard1
        formula = formula_base + accumulator
        formula_gap = state - formula
        residual = formula_gap - sum(adjustments.values())
        change = (
            None
            if previous_residual is None
            else residual - previous_residual
        )
        if (
            "expected_residual_atto" in point
            and residual != int(point["expected_residual_atto"])
        ):
            raise ValueError(
                f"{point['name']}: residual {residual} != expected "
                f"{point['expected_residual_atto']}"
            )
        if (
            "expected_change_atto" in point
            and change != int(point["expected_change_atto"])
        ):
            raise ValueError(
                f"{point['name']}: change {change} != expected "
                f"{point['expected_change_atto']}"
            )
        results.append(
            {
                "name": point["name"],
                "block": point.get("block"),
                "shard0_claims_atto": str(shard0),
                "shard1_claims_atto": str(shard1),
                "global_state_atto": str(state),
                "block_reward_accumulator_atto": str(accumulator),
                "formula_atto": str(formula),
                "formula_gap_atto": str(formula_gap),
                "adjustments_atto": {
                    name: str(value) for name, value in adjustments.items()
                },
                "residual_atto": str(residual),
                "residual_one": display_one(residual),
                "change_from_previous_atto": (
                    None if change is None else str(change)
                ),
                "change_from_previous_one": (
                    None if change is None else display_one(change)
                ),
            }
        )
        previous_residual = residual
    return {
        "schema_version": 1,
        "genesis_atto": str(genesis),
        "pre_staking_rewards_atto": str(pre_staking),
        "formula": (
            "shard0 claims + shard1 claims - genesis - pre-staking rewards "
            "- block reward accumulator - named adjustments"
        ),
        "checkpoints": results,
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
    input_path = Path(args.input).resolve()
    with input_path.open(encoding="utf-8") as source:
        configuration = json.load(source)
    result = calculate(configuration, input_path.parent)
    write_json(Path(args.output) if args.output else None, result)


if __name__ == "__main__":
    main()
