from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from v75.candidate_v2g_temporal_recency import (
    HALF_LIFE_DAYS,
    MODEL_NAME,
    score_field,
)


def load(
    path: Path,
) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save(
    path: Path,
    payload: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--work-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    rows = []

    for meeting_dir in sorted(
        path
        for path
        in args.work_root.iterdir()
        if path.is_dir()
    ):
        pre_path = (
            meeting_dir
            / "normalized"
            / "pre-race.json"
        )

        outcome_path = (
            meeting_dir
            / "normalized"
            / "outcomes.json"
        )

        v2a_path = (
            meeting_dir
            / (
                "candidate-v2a-speed-"
                "predictions.json"
            )
        )

        if not (
            pre_path.exists()
            and outcome_path.exists()
            and v2a_path.exists()
        ):
            continue

        pre = load(
            pre_path
        )

        outcomes = load(
            outcome_path
        )

        v2a = load(
            v2a_path
        )

        winner_by_leg = {
            int(row["leg"]):
                int(
                    row[
                        "winnerStartNumber"
                    ]
                )
            for row
            in outcomes["legs"]
        }

        v2a_by_leg = {
            int(row["leg"]):
                row
            for row
            in v2a["legs"]
        }

        for leg in pre["legs"]:
            leg_no = int(
                leg["leg"]
            )

            entries = [
                entry
                for entry
                in leg[
                    "entries"
                ]
                if entry[
                    "start"
                ][
                    "eligibleForPrediction"
                ]
            ]

            v2g = score_field(
                entries
            )

            winner = (
                winner_by_leg[
                    leg_no
                ]
            )

            v2a_ranking = [
                int(
                    row[
                        "startNumber"
                    ]
                )
                for row
                in v2a_by_leg[
                    leg_no
                ][
                    "rankings"
                ]
            ]

            v2g_ranking = [
                int(
                    row[
                        "startNumber"
                    ]
                )
                for row
                in v2g
            ]

            if (
                winner
                not in v2a_ranking
                or winner
                not in v2g_ranking
            ):
                raise RuntimeError(
                    "Winner missing from ranking."
                )

            rank_a = (
                v2a_ranking.index(
                    winner
                )
                + 1
            )

            rank_g = (
                v2g_ranking.index(
                    winner
                )
                + 1
            )

            rows.append(
                {
                    "date":
                        pre[
                            "raceDate"
                        ],
                    "leg":
                        leg_no,
                    "winnerStartNumber":
                        winner,
                    "v2aRank":
                        rank_a,
                    "v2gRank":
                        rank_g,
                }
            )

    if len(rows) != 252:
        raise RuntimeError(
            "Expected exactly 252 "
            f"paired races, got "
            f"{len(rows)}."
        )

    def summary(
        key: str,
    ) -> dict[str, Any]:
        ranks = [
            int(row[key])
            for row
            in rows
        ]

        return {
            "races":
                len(ranks),
            "top1":
                sum(
                    rank <= 1
                    for rank
                    in ranks
                ),
            "top2":
                sum(
                    rank <= 2
                    for rank
                    in ranks
                ),
            "top3":
                sum(
                    rank <= 3
                    for rank
                    in ranks
                ),
            "top5":
                sum(
                    rank <= 5
                    for rank
                    in ranks
                ),
            "averageWinnerRank":
                mean(
                    ranks
                ),
        }

    v2a_summary = summary(
        "v2aRank"
    )

    v2g_summary = summary(
        "v2gRank"
    )

    better = sum(
        row["v2gRank"]
        < row["v2aRank"]
        for row
        in rows
    )

    worse = sum(
        row["v2gRank"]
        > row["v2aRank"]
        for row
        in rows
    )

    equal = sum(
        row["v2gRank"]
        == row["v2aRank"]
        for row
        in rows
    )

    payload = {
        "schemaVersion":
            "1.0",
        "experiment":
            (
                "v2g-temporal-recency-"
                "retrospective-v1"
            ),
        "status":
            "RETROSPECTIVE_DIAGNOSTIC_ONLY",
        "model":
            MODEL_NAME,
        "halfLifeDays":
            HALF_LIFE_DAYS,
        "halfLifeSelection": (
            "2 x 16-day median "
            "historical inter-start gap; "
            "fixed before outcome scoring"
        ),
        "weights": {
            "baseline":
                0.70,
            "speed":
                0.30,
        },
        "v2a":
            v2a_summary,
        "v2g":
            v2g_summary,
        "pairedWinnerRank": {
            "v2gBetter":
                better,
            "equal":
                equal,
            "v2gWorse":
                worse,
        },
        "races":
            rows,
        "guardrails": {
            "v2aUnchanged":
                True,
            "halfLifeOutcomeTuned":
                False,
            "marketUsed":
                False,
            "outcomesUsedAsModelInput":
                False,
            "datasetAlreadyConsumed":
                True,
            "eligibleForAutomaticPromotion":
                False,
        },
    }

    save(
        args.output,
        payload,
    )

    print(
        "=== V2A vs V2G "
        "TEMPORAL RECENCY ==="
    )

    print()
    print(
        "V2A"
    )

    print(
        f"Top1: "
        f"{v2a_summary['top1']}/252"
    )

    print(
        f"Top2: "
        f"{v2a_summary['top2']}/252"
    )

    print(
        f"Top3: "
        f"{v2a_summary['top3']}/252"
    )

    print(
        f"Top5: "
        f"{v2a_summary['top5']}/252"
    )

    print(
        "Average winner rank:",
        f"{v2a_summary['averageWinnerRank']:.3f}",
    )

    print()
    print(
        "V2G"
    )

    print(
        f"Top1: "
        f"{v2g_summary['top1']}/252"
    )

    print(
        f"Top2: "
        f"{v2g_summary['top2']}/252"
    )

    print(
        f"Top3: "
        f"{v2g_summary['top3']}/252"
    )

    print(
        f"Top5: "
        f"{v2g_summary['top5']}/252"
    )

    print(
        "Average winner rank:",
        f"{v2g_summary['averageWinnerRank']:.3f}",
    )

    print()
    print(
        "Paired winner rank:"
    )

    print(
        f"V2G better: {better}"
    )

    print(
        f"Equal:      {equal}"
    )

    print(
        f"V2G worse:  {worse}"
    )

    print()
    print(
        "PASS: half-life was fixed "
        "without outcome tuning."
    )

    print(
        "PASS: retrospective diagnostic "
        "cannot promote challenger."
    )

    print(
        "Report:",
        args.output,
    )


if __name__ == "__main__":
    main()
