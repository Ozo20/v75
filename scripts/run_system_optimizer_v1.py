from __future__ import annotations

import argparse
import json
from pathlib import Path

from v75.system_optimizer_v1 import (
    BETA,
    optimize_system,
)


BUDGETS = [
    64,
    128,
    256,
    512,
    1024,
    2048,
    4096,
]


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--predictions",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    prediction = load(
        args.predictions
    )

    assert (
        prediction["model"]
        == "candidate-v2a-speed"
    )

    systems = []

    for budget in BUDGETS:
        system = optimize_system(
            prediction["legs"],
            max_rows=budget,
        )

        systems.append(
            system
        )

    output = {
        "schemaVersion": "1.0",
        "systemModel":
            "v75-system-optimizer-v1",
        "horseModel":
            "candidate-v2a-speed",
        "beta":
            BETA,
        "raceDate":
            prediction["raceDate"],
        "raceDayKey":
            prediction["raceDayKey"],
        "raceDayName":
            prediction["raceDayName"],
        "budgets":
            BUDGETS,
        "systems":
            systems,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"{prediction['raceDate']} "
        f"{prediction['raceDayName']:<14}",
        end="",
    )

    for system in systems:
        ks = [
            leg["k"]
            for leg
            in system["legs"]
        ]

        print(
            f" | "
            f"{system['maxRows']}="
            f"{system['actualRows']}"
            f"{ks}",
            end="",
        )

    print()


if __name__ == "__main__":
    main()
