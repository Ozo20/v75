from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(
    __file__
).resolve().parents[1]

EXPECTED_V2A_HASH = (
    "464306a193db1499edce2255806219b12"
    "ab0687ff547935ba2cd29741e31c674"
)

EXPECTED_NORMALIZER_HASH = (
    "1eba472fe5207d121d62cf8111486a2e"
    "b69e0a0942c73f723fa4a28cfc6f7f38"
)

EVALUATION_SET = (
    ROOT
    / "data"
    / "experiments"
    / "multitrack-v2a-evaluation-set-v1.json"
)


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


def sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:
        while True:
            chunk = handle.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()


def verify_frozen_stack(
    *,
    adapter_hash: str,
    runner_hash: str,
) -> None:
    checks = [
        (
            ROOT
            / "src"
            / "v75"
            / "candidate_v2a_speed.py",
            EXPECTED_V2A_HASH,
            "V2A",
        ),
        (
            ROOT
            / "src"
            / "rikstoto_normalizer.py",
            EXPECTED_NORMALIZER_HASH,
            "normalizer",
        ),
        (
            ROOT
            / "scripts"
            / "materialize_multitrack_fixture_v1.py",
            adapter_hash,
            "multi-track adapter",
        ),
        (
            ROOT
            / "scripts"
            / "run_candidate_v2a_speed.py",
            runner_hash,
            "V2A runner",
        ),
    ]

    for path, expected, label in checks:
        actual = sha256(
            path
        )

        if actual != expected:
            raise RuntimeError(
                f"{label} changed during "
                f"frozen evaluation. "
                f"Expected {expected}, "
                f"got {actual}."
            )


def run(
    label: str,
    command: list[str],
) -> None:
    print()
    print(
        f"--- {label} ---"
    )

    subprocess.run(
        command,
        cwd=ROOT,
        check=True,
    )


def score_meeting(
    *,
    meeting_dir: Path,
    frozen_meeting: dict[str, Any],
) -> dict[str, Any]:
    prediction_path = (
        meeting_dir
        / (
            "candidate-v2a-speed-"
            "predictions.json"
        )
    )

    outcomes_path = (
        meeting_dir
        / "normalized"
        / "outcomes.json"
    )

    source_map_path = (
        meeting_dir
        / "raw"
        / "source-map.json"
    )

    predictions = load_json(
        prediction_path
    )

    outcomes = load_json(
        outcomes_path
    )

    source_map = load_json(
        source_map_path
    )

    if (
        predictions.get(
            "model"
        )
        != "candidate-v2a-speed"
    ):
        raise RuntimeError(
            "Unexpected model."
        )

    if (
        predictions.get(
            "guardrails",
            {},
        ).get(
            "outcomesAvailableToModel"
        )
        is not False
    ):
        raise RuntimeError(
            "Outcome leakage guardrail failed."
        )

    if (
        predictions.get(
            "guardrails",
            {},
        ).get(
            "marketAvailableToModel"
        )
        is not False
    ):
        raise RuntimeError(
            "Market leakage guardrail failed."
        )

    if (
        source_map.get(
            "poolKey"
        )
        != frozen_meeting.get(
            "poolKey"
        )
    ):
        raise RuntimeError(
            "Frozen pool identity mismatch."
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

    source_by_leg = {
        int(row["leg"]):
            row
        for row
        in source_map["legs"]
    }

    rows = []

    for leg in predictions[
        "legs"
    ]:
        leg_no = int(
            leg["leg"]
        )

        winner = (
            winner_by_leg[
                leg_no
            ]
        )

        ranking = [
            int(
                row[
                    "startNumber"
                ]
            )
            for row
            in leg["rankings"]
        ]

        if winner not in ranking:
            raise RuntimeError(
                f"Winner #{winner} missing "
                f"from V75-{leg_no} ranking."
            )

        rank = (
            ranking.index(
                winner
            )
            + 1
        )

        source = (
            source_by_leg[
                leg_no
            ]
        )

        rows.append(
            {
                "leg":
                    leg_no,
                "sourceRaceKey":
                    source[
                        "sourceRaceKey"
                    ],
                "winnerStartNumber":
                    winner,
                "winnerRank":
                    rank,
                "fieldSizeEligible":
                    len(
                        ranking
                    ),
                "top3StartNumbers":
                    ranking[:3],
            }
        )

    ranks = [
        row["winnerRank"]
        for row
        in rows
    ]

    if len(ranks) != 7:
        raise RuntimeError(
            "Expected exactly seven "
            "scored V75 legs."
        )

    return {
        "schemaVersion":
            "1.0",
        "evaluation":
            "multitrack-v2a-v1",
        "date":
            frozen_meeting[
                "date"
            ],
        "raceDayName":
            frozen_meeting.get(
                "raceDayName"
            ),
        "poolKey":
            frozen_meeting.get(
                "poolKey"
            ),
        "model":
            "candidate-v2a-speed",
        "modelSha256":
            EXPECTED_V2A_HASH,
        "races":
            7,
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
            (
                sum(ranks)
                / len(ranks)
            ),
        "winnerRanks":
            ranks,
        "legs":
            rows,
        "guardrails": {
            "evaluationSetFrozenBeforeScoring":
                True,
            "modelChanged":
                False,
            "resultsUsedAsModelInput":
                False,
            "marketUsedAsModelInput":
                False,
            "partialResultsMayNotRetuneModel":
                True,
        },
    }


def import_pilot(
    *,
    pilot_root: Path,
    meeting_dir: Path,
    frozen_meeting: dict[str, Any],
) -> dict[str, Any] | None:
    pilot_eval = (
        pilot_root
        / "v2a-pilot-evaluation.json"
    )

    if not pilot_eval.exists():
        return None

    pilot = load_json(
        pilot_eval
    )

    if (
        pilot.get("date")
        != frozen_meeting[
            "date"
        ]
    ):
        raise RuntimeError(
            "Pilot date mismatch."
        )

    if (
        pilot.get("model")
        != "candidate-v2a-speed"
    ):
        raise RuntimeError(
            "Pilot model mismatch."
        )

    ranks = [
        int(value)
        for value
        in pilot[
            "winnerRanks"
        ]
    ]

    if len(ranks) != 7:
        raise RuntimeError(
            "Pilot does not contain "
            "seven winner ranks."
        )

    result = {
        "schemaVersion":
            "1.0",
        "evaluation":
            "multitrack-v2a-v1",
        "date":
            frozen_meeting[
                "date"
            ],
        "raceDayName":
            frozen_meeting.get(
                "raceDayName"
            ),
        "poolKey":
            frozen_meeting.get(
                "poolKey"
            ),
        "model":
            "candidate-v2a-speed",
        "modelSha256":
            EXPECTED_V2A_HASH,
        "races":
            7,
        "top1":
            int(
                pilot["top1"]
            ),
        "top2":
            int(
                pilot["top2"]
            ),
        "top3":
            int(
                pilot["top3"]
            ),
        "top5":
            int(
                pilot["top5"]
            ),
        "averageWinnerRank":
            float(
                pilot[
                    "averageWinnerRank"
                ]
            ),
        "winnerRanks":
            ranks,
        "legs":
            None,
        "importedFromPilot":
            str(
                pilot_root
            ),
        "guardrails": {
            "evaluationSetFrozenBeforeScoring":
                True,
            "modelChanged":
                False,
            "resultsUsedAsModelInput":
                False,
            "marketUsedAsModelInput":
                False,
            "partialResultsMayNotRetuneModel":
                True,
        },
    }

    meeting_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    save_json(
        meeting_dir
        / "evaluation.json",
        result,
    )

    return result


def aggregate(
    *,
    meetings: list[
        dict[str, Any]
    ],
    work_root: Path,
    adapter_hash: str,
    runner_hash: str,
) -> dict[str, Any]:
    evaluated = []

    for meeting in meetings:
        path = (
            work_root
            / meeting["date"]
            / "evaluation.json"
        )

        if not path.exists():
            continue

        evaluated.append(
            load_json(
                path
            )
        )

    races = sum(
        int(row["races"])
        for row
        in evaluated
    )

    all_ranks = [
        int(rank)
        for row
        in evaluated
        for rank
        in row[
            "winnerRanks"
        ]
    ]

    result = {
        "schemaVersion":
            "1.0",
        "evaluation":
            "MULTITRACK_V2A_RETROSPECTIVE_V1",
        "status":
            (
                "COMPLETE"
                if len(evaluated)
                == len(meetings)
                else "IN_PROGRESS"
            ),
        "frozenMeetingCount":
            len(meetings),
        "evaluatedMeetingCount":
            len(evaluated),
        "races":
            races,
        "model":
            "candidate-v2a-speed",
        "modelSha256":
            EXPECTED_V2A_HASH,
        "adapterSha256":
            adapter_hash,
        "runnerSha256":
            runner_hash,
        "top1":
            sum(
                int(row["top1"])
                for row
                in evaluated
            ),
        "top2":
            sum(
                int(row["top2"])
                for row
                in evaluated
            ),
        "top3":
            sum(
                int(row["top3"])
                for row
                in evaluated
            ),
        "top5":
            sum(
                int(row["top5"])
                for row
                in evaluated
            ),
        "averageWinnerRank":
            (
                sum(all_ranks)
                / len(all_ranks)
                if all_ranks
                else None
            ),
        "meetings":
            evaluated,
        "guardrails": {
            "completeSetFrozenBeforeScoring":
                True,
            "partialResultsNotUsedForRetuning":
                True,
            "modelFrozenThroughoutEvaluation":
                True,
        },
    }

    save_json(
        work_root
        / "aggregate.json",
        result,
    )

    return result


def print_aggregate(
    result: dict[str, Any],
) -> None:
    races = int(
        result["races"]
    )

    print()
    print(
        "=== CURRENT AGGREGATE ==="
    )

    print(
        "Meetings:",
        (
            f"{result['evaluatedMeetingCount']}"
            f"/{result['frozenMeetingCount']}"
        ),
    )

    print(
        "Races:",
        races,
    )

    for key, label in (
        ("top1", "Top1"),
        ("top2", "Top2"),
        ("top3", "Top3"),
        ("top5", "Top5"),
    ):
        count = int(
            result[key]
        )

        pct = (
            count
            / races
            * 100.0
            if races
            else 0.0
        )

        print(
            f"{label}: "
            f"{count}/{races} "
            f"({pct:.1f}%)"
        )

    avg = result[
        "averageWinnerRank"
    ]

    if avg is not None:
        print(
            "Average winner rank:",
            f"{avg:.3f}",
        )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--work-root",
        type=Path,
        default=(
            Path.home()
            / "Downloads"
            / (
                "v75-multitrack-"
                "evaluation-v1"
            )
        ),
    )

    parser.add_argument(
        "--pilot-root",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--resume",
        action="store_true",
    )

    args = parser.parse_args()

    frozen = load_json(
        EVALUATION_SET
    )

    if (
        frozen.get(
            "status"
        )
        != (
            "FROZEN_UNTOUCHED_"
            "RETROSPECTIVE_EVALUATION"
        )
    ):
        raise RuntimeError(
            "Evaluation set is not frozen."
        )

    meetings = frozen[
        "meetings"
    ]

    if len(meetings) != 36:
        raise RuntimeError(
            "Expected exactly 36 "
            "frozen meetings."
        )

    if (
        frozen.get(
            "horseModelSha256"
        )
        != EXPECTED_V2A_HASH
    ):
        raise RuntimeError(
            "Frozen evaluation-set model "
            "hash mismatch."
        )

    adapter = (
        ROOT
        / "scripts"
        / "materialize_multitrack_fixture_v1.py"
    )

    runner = (
        ROOT
        / "scripts"
        / "run_candidate_v2a_speed.py"
    )

    adapter_hash = sha256(
        adapter
    )

    runner_hash = sha256(
        runner
    )

    verify_frozen_stack(
        adapter_hash=
            adapter_hash,
        runner_hash=
            runner_hash,
    )

    args.work_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "=== FROZEN MULTI-TRACK "
        "V2A EVALUATION ==="
    )

    print(
        f"Meetings: {len(meetings)}"
    )

    print(
        "Maximum races:",
        len(meetings) * 7,
    )

    print(
        "Work root:",
        args.work_root,
    )

    for index, meeting in enumerate(
        meetings,
        1,
    ):
        verify_frozen_stack(
            adapter_hash=
                adapter_hash,
            runner_hash=
                runner_hash,
        )

        date = meeting[
            "date"
        ]

        meeting_dir = (
            args.work_root
            / date
        )

        evaluation_path = (
            meeting_dir
            / "evaluation.json"
        )

        print()
        print(
            "=" * 72
        )

        print(
            f"[{index:02d}/"
            f"{len(meetings):02d}] "
            f"{date} "
            f"{meeting.get('raceDayName')}"
        )

        if (
            args.resume
            and evaluation_path.exists()
        ):
            existing = load_json(
                evaluation_path
            )

            if (
                existing.get(
                    "modelSha256"
                )
                != EXPECTED_V2A_HASH
            ):
                raise RuntimeError(
                    "Existing evaluation "
                    "has wrong V2A hash."
                )

            print(
                "PASS: already evaluated; "
                "skipping."
            )

            result = aggregate(
                meetings=meetings,
                work_root=
                    args.work_root,
                adapter_hash=
                    adapter_hash,
                runner_hash=
                    runner_hash,
            )

            print_aggregate(
                result
            )

            continue

        if (
            date == "2026-09-29"
            and args.pilot_root
            is not None
        ):
            imported = (
                import_pilot(
                    pilot_root=
                        args.pilot_root,
                    meeting_dir=
                        meeting_dir,
                    frozen_meeting=
                        meeting,
                )
            )

            if imported is not None:
                print(
                    "PASS: imported already "
                    "completed frozen pilot."
                )

                result = aggregate(
                    meetings=meetings,
                    work_root=
                        args.work_root,
                    adapter_hash=
                        adapter_hash,
                    runner_hash=
                        runner_hash,
                )

                print_aggregate(
                    result
                )

                continue

        if meeting_dir.exists():
            shutil.rmtree(
                meeting_dir
            )

        raw_dir = (
            meeting_dir
            / "raw"
        )

        normalized_dir = (
            meeting_dir
            / "normalized"
        )

        prediction_path = (
            meeting_dir
            / (
                "candidate-v2a-speed-"
                "predictions.json"
            )
        )

        run(
            "MATERIALIZE MULTI-TRACK FIXTURE",
            [
                sys.executable,
                str(adapter),
                "--discovery",
                str(
                    ROOT
                    / "data"
                    / "discovery"
                    / "v75-days-2026.json"
                ),
                "--date",
                date,
                "--output-dir",
                str(raw_dir),
            ],
        )

        run(
            "NORMALIZE",
            [
                sys.executable,
                str(
                    ROOT
                    / "src"
                    / "rikstoto_normalizer.py"
                ),
                "--snapshot-dir",
                str(raw_dir),
                "--results-probe",
                str(
                    raw_dir
                    / "results-probe.json"
                ),
                "--output-dir",
                str(normalized_dir),
            ],
        )

        run(
            "RUN FROZEN V2A",
            [
                sys.executable,
                str(runner),
                "--input",
                str(
                    normalized_dir
                    / "pre-race.json"
                ),
                "--output",
                str(
                    prediction_path
                ),
            ],
        )

        evaluation = score_meeting(
            meeting_dir=
                meeting_dir,
            frozen_meeting=
                meeting,
        )

        save_json(
            evaluation_path,
            evaluation,
        )

        print()
        print(
            "PASS:",
            date,
            (
                f"T1={evaluation['top1']}/7 "
                f"T2={evaluation['top2']}/7 "
                f"T3={evaluation['top3']}/7 "
                f"T5={evaluation['top5']}/7 "
                f"avg="
                f"{evaluation['averageWinnerRank']:.3f}"
            ),
        )

        result = aggregate(
            meetings=meetings,
            work_root=
                args.work_root,
            adapter_hash=
                adapter_hash,
            runner_hash=
                runner_hash,
        )

        print_aggregate(
            result
        )

    verify_frozen_stack(
        adapter_hash=
            adapter_hash,
        runner_hash=
            runner_hash,
    )

    final = aggregate(
        meetings=meetings,
        work_root=
            args.work_root,
        adapter_hash=
            adapter_hash,
        runner_hash=
            runner_hash,
    )

    if (
        final[
            "evaluatedMeetingCount"
        ]
        != 36
    ):
        raise RuntimeError(
            "Evaluation incomplete."
        )

    if final["races"] != 252:
        raise RuntimeError(
            "Expected exactly 252 races."
        )

    print()
    print(
        "=" * 72
    )

    print(
        "=== FINAL FROZEN "
        "MULTI-TRACK RESULT ==="
    )

    print_aggregate(
        final
    )

    print()
    print(
        "PASS: all 36 frozen meetings "
        "evaluated."
    )

    print(
        "PASS: all 252 races scored."
    )

    print(
        "PASS: frozen V2A remained "
        "unchanged throughout."
    )

    print(
        "Report:",
        (
            args.work_root
            / "aggregate.json"
        ),
    )


if __name__ == "__main__":
    main()
