from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(
    __file__
).resolve().parents[1]

FROZEN_BANKER_THRESHOLD = 0.35

DEFAULT_BUDGET_OPTIONS = [
    100.0,
    200.0,
    300.0,
    400.0,
    500.0,
    600.0,
    800.0,
    1000.0,
]


def load_json(
    path: Path,
) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save_json(
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


def parse_date(
    value: str,
) -> date:
    return date.fromisoformat(
        value
    )


def run_stage(
    label: str,
    command: list[str],
) -> None:
    print()
    print(
        f"=== {label} ==="
    )

    subprocess.run(
        command,
        cwd=ROOT,
        check=True,
    )


def assert_policy_contract() -> None:
    path = (
        ROOT
        / "data"
        / "experiments"
        / "risk-profile-v3-decision.json"
    )

    if not path.exists():
        raise RuntimeError(
            "Missing frozen risk-profile "
            f"decision: {path}"
        )

    decision = load_json(
        path
    )

    if (
        decision[
            "defaultPolicy"
        ][
            "name"
        ]
        != "MAX_P7"
    ):
        raise RuntimeError(
            "Unexpected default policy."
        )

    challenger = decision[
        "challengerPolicy"
    ]

    if (
        challenger["name"]
        != "NO_WEAK_BANKER"
    ):
        raise RuntimeError(
            "Unexpected challenger policy."
        )

    threshold = float(
        challenger[
            "minBankerProbability"
        ]
    )

    if abs(
        threshold
        - FROZEN_BANKER_THRESHOLD
    ) > 1e-12:
        raise RuntimeError(
            "Frozen banker threshold "
            "does not equal 35%."
        )

    if (
        challenger[
            "retuneThresholdOnConsumedData"
        ]
        is not False
    ):
        raise RuntimeError(
            "Risk-policy retune guardrail "
            "is not frozen."
        )


def select_meeting(
    discovery: dict[str, Any],
    *,
    race_date: str,
    race_day_key: str | None,
) -> dict[str, Any]:
    candidates = [
        meeting
        for meeting
        in discovery.get(
            "meetings",
            [],
        )
        if (
            meeting.get(
                "date"
            )
            == race_date
            and meeting.get(
                "countryIsoCode"
            )
            == "NO"
            and meeting.get(
                "singleTrack"
            )
            is True
            and int(
                meeting.get(
                    "legCount",
                    0,
                )
            )
            == 7
        )
    ]

    if race_day_key:
        candidates = [
            meeting
            for meeting
            in candidates
            if meeting.get(
                "raceDayKey"
            )
            == race_day_key
        ]

    if len(candidates) != 1:
        available = [
            {
                "raceDayKey":
                    row.get(
                        "raceDayKey"
                    ),
                "raceDayName":
                    row.get(
                        "raceDayName"
                    ),
            }
            for row
            in candidates
        ]

        raise RuntimeError(
            "Expected exactly one "
            "single-track Norwegian V75 "
            f"meeting for {race_date}; "
            f"found {len(candidates)}. "
            f"Candidates: {available}"
        )

    return candidates[0]


def build_post_discovery_commands(
    *,
    run_dir: Path,
    race_date: str,
    race_day_key: str,
    selected_budget_nok: float,
    row_price_nok: float,
    budget_options_nok: list[float],
) -> dict[str, list[str]]:
    discovery_path = (
        run_dir
        / "discovery.json"
    )

    raw_root = (
        run_dir
        / "raw"
    )

    snapshot_dir = (
        raw_root
        / race_date
    )

    normalized_dir = (
        run_dir
        / "normalized"
    )

    prediction_path = (
        run_dir
        / (
            "candidate-v2a-speed-"
            "predictions.json"
        )
    )

    ticket_path = (
        run_dir
        / "live-ticket.json"
    )

    return {
        "collector": [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "collect_v75_snapshot.py"
            ),
            "--discovery",
            str(discovery_path),
            "--race-day-key",
            race_day_key,
            "--output-root",
            str(raw_root),
            "--pre-race-only",
        ],

        "normalizer": [
            sys.executable,
            str(
                ROOT
                / "src"
                / "rikstoto_normalizer.py"
            ),
            "--snapshot-dir",
            str(snapshot_dir),
            "--output-dir",
            str(normalized_dir),
        ],

        "predictor": [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "run_candidate_v2a_speed.py"
            ),
            "--input",
            str(
                normalized_dir
                / "pre-race.json"
            ),
            "--output",
            str(prediction_path),
        ],

        "ticket": [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "build_live_v75_ticket_v1.py"
            ),
            "--predictions",
            str(prediction_path),
            "--row-price-nok",
            str(row_price_nok),
            "--budget-options-nok",
            *[
                str(value)
                for value
                in budget_options_nok
            ],
            "--selected-budget-nok",
            str(
                selected_budget_nok
            ),
            "--min-banker-probability",
            str(
                FROZEN_BANKER_THRESHOLD
            ),
            "--output",
            str(ticket_path),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete pre-race V75 "
            "pipeline and build live ticket "
            "alternatives."
        )
    )

    parser.add_argument(
        "--date",
        required=True,
        type=parse_date,
        help="Race date YYYY-MM-DD.",
    )

    parser.add_argument(
        "--budget-nok",
        required=True,
        type=float,
        help=(
            "Selected total ticket budget."
        ),
    )

    parser.add_argument(
        "--row-price-nok",
        required=True,
        type=float,
        help=(
            "Actual NOK price per V75 row."
        ),
    )

    parser.add_argument(
        "--budget-options-nok",
        nargs="+",
        type=float,
        default=DEFAULT_BUDGET_OPTIONS,
        help=(
            "Budget points shown in the "
            "frontier."
        ),
    )

    parser.add_argument(
        "--race-day-key",
        default=None,
        help=(
            "Optional explicit Rikstoto "
            "raceDayKey if discovery is "
            "ambiguous."
        ),
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        default=(
            ROOT
            / "data"
            / "live"
        ),
    )

    args = parser.parse_args()

    if args.budget_nok <= 0:
        raise ValueError(
            "--budget-nok must be > 0"
        )

    if args.row_price_nok <= 0:
        raise ValueError(
            "--row-price-nok must be > 0"
        )

    if any(
        value <= 0
        for value
        in args.budget_options_nok
    ):
        raise ValueError(
            "All budget options must "
            "be > 0."
        )

    assert_policy_contract()

    race_date = (
        args.date.isoformat()
    )

    run_id = (
        datetime.now()
        .astimezone()
        .strftime(
            "%Y%m%dT%H%M%S%f%z"
        )
    )

    run_dir = (
        args.output_root
        / race_date
        / run_id
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    discovery_path = (
        run_dir
        / "discovery.json"
    )

    print(
        "=== LIVE V75 PIPELINE V1 ==="
    )

    print(
        f"Race date:       "
        f"{race_date}"
    )

    print(
        f"Selected budget: "
        f"{args.budget_nok:.2f} NOK"
    )

    print(
        f"Row price:       "
        f"{args.row_price_nok:.2f} NOK"
    )

    print(
        f"Run directory:   "
        f"{run_dir}"
    )

    run_stage(
        "1. DISCOVER V75",
        [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "discover_v75_days.py"
            ),
            "--from-date",
            race_date,
            "--to-date",
            race_date,
            "--output",
            str(discovery_path),
        ],
    )

    discovery = load_json(
        discovery_path
    )

    meeting = select_meeting(
        discovery,
        race_date=race_date,
        race_day_key=
            args.race_day_key,
    )

    race_day_key = str(
        meeting[
            "raceDayKey"
        ]
    )

    race_day_name = str(
        meeting.get(
            "raceDayName"
        )
    )

    print()
    print(
        "Selected meeting:"
    )

    print(
        f"  {race_day_name}"
    )

    print(
        f"  {race_day_key}"
    )

    commands = (
        build_post_discovery_commands(
            run_dir=run_dir,
            race_date=race_date,
            race_day_key=
                race_day_key,
            selected_budget_nok=
                args.budget_nok,
            row_price_nok=
                args.row_price_nok,
            budget_options_nok=
                sorted(
                    set(
                        [
                            *args.budget_options_nok,
                            args.budget_nok,
                        ]
                    )
                ),
        )
    )

    run_stage(
        "2. COLLECT PRE-RACE SNAPSHOT",
        commands["collector"],
    )

    raw_snapshot = (
        run_dir
        / "raw"
        / race_date
    )

    if (
        raw_snapshot
        / "results-probe.json"
    ).exists():
        raise RuntimeError(
            "SAFETY FAILURE: "
            "pre-race collector wrote "
            "results-probe.json."
        )

    raw_manifest = load_json(
        raw_snapshot
        / "manifest.json"
    )

    if (
        raw_manifest.get(
            "guardrails",
            {},
        ).get(
            "resultsFetched"
        )
        is not False
    ):
        raise RuntimeError(
            "SAFETY FAILURE: raw manifest "
            "does not prove resultsFetched=false."
        )

    run_stage(
        "3. NORMALIZE PRE-RACE DATA",
        commands["normalizer"],
    )

    normalized_dir = (
        run_dir
        / "normalized"
    )

    if (
        normalized_dir
        / "outcomes.json"
    ).exists():
        raise RuntimeError(
            "SAFETY FAILURE: live "
            "normalization wrote outcomes.json."
        )

    normalized_manifest = load_json(
        normalized_dir
        / "manifest.json"
    )

    if (
        normalized_manifest.get(
            "guardrails",
            {},
        ).get(
            "resultsAvailable"
        )
        is not False
    ):
        raise RuntimeError(
            "SAFETY FAILURE: normalized "
            "manifest does not prove "
            "resultsAvailable=false."
        )

    run_stage(
        "4. RUN FROZEN V2A",
        commands["predictor"],
    )

    run_stage(
        "5. BUILD LIVE TICKETS",
        commands["ticket"],
    )

    ticket_path = (
        run_dir
        / "live-ticket.json"
    )

    ticket = load_json(
        ticket_path
    )

    if (
        ticket[
            "guardrails"
        ][
            "outcomesUsed"
        ]
        is not False
    ):
        raise RuntimeError(
            "SAFETY FAILURE: ticket "
            "outcome guardrail failed."
        )

    run_manifest = {
        "schemaVersion":
            "1.0",
        "pipeline":
            "live-v75-v1",
        "createdAt":
            datetime.now()
            .astimezone()
            .isoformat(),
        "raceDate":
            race_date,
        "raceDayKey":
            race_day_key,
        "raceDayName":
            race_day_name,
        "selectedBudgetNok":
            args.budget_nok,
        "rowPriceNok":
            args.row_price_nok,
        "bankerThreshold":
            FROZEN_BANKER_THRESHOLD,
        "defaultPolicy":
            "MAX_P7",
        "challengerPolicy":
            "NO_WEAK_BANKER",
        "files": {
            "discovery":
                "discovery.json",
            "rawSnapshot":
                (
                    f"raw/"
                    f"{race_date}"
                ),
            "normalizedPreRace":
                (
                    "normalized/"
                    "pre-race.json"
                ),
            "prediction":
                (
                    "candidate-v2a-speed-"
                    "predictions.json"
                ),
            "ticket":
                "live-ticket.json",
        },
        "guardrails": {
            "preRaceOnly":
                True,
            "resultsFetched":
                False,
            "outcomesGenerated":
                False,
            "marketUsed":
                False,
            "modelRetuned":
                False,
            "bankerThresholdRetuned":
                False,
        },
    }

    save_json(
        run_dir
        / "run-manifest.json",
        run_manifest,
    )

    print()
    print(
        "=== LIVE PIPELINE COMPLETE ==="
    )

    print(
        f"Meeting: "
        f"{race_day_name}"
    )

    print(
        f"Budget:  "
        f"{args.budget_nok:.2f} NOK"
    )

    print(
        f"Ticket:  "
        f"{ticket_path}"
    )

    print(
        f"Run:     "
        f"{run_dir}"
    )

    print()
    print(
        "PASS: results endpoint "
        "was not used."
    )

    print(
        "PASS: no outcomes were "
        "generated."
    )

    print(
        "PASS: frozen V2A + frozen "
        "risk policies used."
    )


if __name__ == "__main__":
    main()
