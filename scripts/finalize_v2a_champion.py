from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("data/experiments")


def load(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


development = load(
    ROOT
    / "feature-v2a-development.json"
)

validation = load(
    ROOT
    / "v2a-speed-validation.json"
)

holdout = load(
    ROOT
    / "v2a-speed-true-holdout.json"
)

robustness = load(
    ROOT
    / "speed-models-independent-robustness.json"
)


cohorts = [
    {
        "name": "development",
        "safe":
            development[
                "results"
            ][
                "safe-v1"
            ],
        "v2a":
            development[
                "results"
            ][
                "v2a-speed"
            ],
    },
    {
        "name": "validation",
        "safe":
            validation[
                "baseline"
            ],
        "v2a":
            validation[
                "candidate"
            ],
    },
    {
        "name": "true-holdout",
        "safe":
            holdout[
                "baseline"
            ],
        "v2a":
            holdout[
                "candidate"
            ],
    },
    {
        "name":
            "independent-robustness",
        "safe":
            robustness[
                "results"
            ][
                "safe-v1"
            ],
        "v2a":
            robustness[
                "results"
            ][
                "v2a-speed"
            ],
    },
]


def aggregate(model_key):
    races = sum(
        cohort[
            model_key
        ][
            "races"
        ]
        for cohort
        in cohorts
    )

    top1 = sum(
        cohort[
            model_key
        ][
            "top1"
        ]
        for cohort
        in cohorts
    )

    top2 = sum(
        cohort[
            model_key
        ][
            "top2"
        ]
        for cohort
        in cohorts
    )

    top3 = sum(
        cohort[
            model_key
        ][
            "top3"
        ]
        for cohort
        in cohorts
    )

    top5 = sum(
        cohort[
            model_key
        ][
            "top5"
        ]
        for cohort
        in cohorts
    )

    weighted_rank = sum(
        cohort[
            model_key
        ][
            "averageWinnerRank"
        ]
        * cohort[
            model_key
        ][
            "races"
        ]
        for cohort
        in cohorts
    ) / races

    return {
        "races":
            races,
        "top1":
            top1,
        "top1Rate":
            top1 / races,
        "top2":
            top2,
        "top2Rate":
            top2 / races,
        "top3":
            top3,
        "top3Rate":
            top3 / races,
        "top5":
            top5,
        "top5Rate":
            top5 / races,
        "averageWinnerRank":
            weighted_rank,
    }


safe = aggregate("safe")
v2a = aggregate("v2a")


assert safe["races"] == 196
assert v2a["races"] == 196

assert safe["top3"] == 108
assert v2a["top3"] == 118

assert safe["top5"] == 147
assert v2a["top5"] == 156


decision = {
    "schemaVersion": "1.0",
    "decision":
        "PROMOTE_V2A_SPEED",
    "currentChampion":
        "candidate-v2a-speed",
    "previousChampion":
        "baseline-safe-v1",
    "candidateFingerprint":
        "464306a193db1499edce2255806219b12ab0687ff547935ba2cd29741e31c674",
    "weights": {
        "safeBaseline":
            0.70,
        "speed":
            0.30,
    },
    "evidence": {
        "development": {
            "status":
                "V2A improved ranking metrics"
        },
        "validation": {
            "status":
                "V2A improved all reported metrics"
        },
        "trueHoldout": {
            "status":
                "MIXED",
            "note":
                "Original predeclared holdout verdict remains unchanged"
        },
        "independentRobustness": {
            "status":
                "STRONG_V2A_SUPPORT",
            "races":
                70,
            "safeTop3":
                41,
            "v2aTop3":
                47,
            "safeTop5":
                54,
            "v2aTop5":
                58
        }
    },
    "descriptiveAggregate": {
        "warning":
            "Combined 196-race metrics are descriptive, not one independent holdout test.",
        "safeV1":
            safe,
        "v2aSpeed":
            v2a
    },
    "policy": {
        "doNotRetuneV2AWeightsFromSpentDatasets":
            True,
        "v2bContextStatus":
            "NOT_PROMOTED",
        "nextCapability":
            "win-probability calibration"
    }
}


output = (
    ROOT
    / "champion-v2a-speed.json"
)

output.write_text(
    json.dumps(
        decision,
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)


def show(name, result):
    n = result["races"]

    print(
        f"{name:<16} "
        f"T1={result['top1']:>3}/{n} "
        f"({100*result['top1Rate']:5.1f}%) "
        f"T2={result['top2']:>3}/{n} "
        f"({100*result['top2Rate']:5.1f}%) "
        f"T3={result['top3']:>3}/{n} "
        f"({100*result['top3Rate']:5.1f}%) "
        f"T5={result['top5']:>3}/{n} "
        f"({100*result['top5Rate']:5.1f}%) "
        f"avgRank="
        f"{result['averageWinnerRank']:.2f}"
    )


print(
    "=== CONSOLIDATED MODEL EVIDENCE ==="
)

show(
    "safe-v1",
    safe,
)

show(
    "v2a-speed",
    v2a,
)

print()
print(
    "PASS: V2A-speed promoted "
    "to current champion."
)

print(
    "NOTE: original holdout "
    "verdict remains MIXED."
)

print(
    f"Decision: {output}"
)
