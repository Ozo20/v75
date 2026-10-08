from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

FROZEN = {
    "src/v75/candidate_v2a_speed.py":
        "464306a193db1499edce2255806219b12ab0687ff547935ba2cd29741e31c674",
    "scripts/build_live_v75_ticket_v1.py":
        "7030ee6068297da58d24571428aadd1f4cca76b45bfc39f5873d44aab11b82d7",
    "src/v75/system_optimizer_v1.py":
        "3b01e0ff1699381aab2537ca11a56339403fa08cbe186cd17474b19b3d3c9439",
    "scripts/run_live_v75.py":
        "e6e154f276689055a1ab4f2aab9ecbc205574fccd42caf66ad9e0f30760e1890",
    "scripts/build_hybrid_input_v1.py":
        "06c8b05b8f92e075fd775c73d1599b400d417c11446a6a484abffd37a304efcc",
    "scripts/apply_stalltips_to_hybrid_v1.py":
        "be6c86efd681f693d0541eacc053abf5e3006583a3d40b976b39b60c0470f338",
    "scripts/build_hybrid_ticket_v1.py":
        "b3e1f8b01056c05ef62c2b0a3bf1bd58406cf40b3c1fe89f0a2bb7c8ca19b364",
    "data/experiments/hybrid-selector-v1-decision.json":
        "36a8a8c8ec6f21dd458c36fec6d3acf50058bfedd8e96e19c1e8341444307bbd",
}


def load(path: Path) -> Any:
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


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def verify_frozen() -> None:
    for relative, expected in (
        FROZEN.items()
    ):
        path = ROOT / relative

        if not path.is_file():
            raise RuntimeError(
                f"Frozen file missing: "
                f"{relative}"
            )

        actual = sha256_file(
            path
        )

        if actual != expected:
            raise RuntimeError(
                f"Frozen file changed: "
                f"{relative}\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}"
            )


def parse_iso_datetime(
    value: str,
) -> datetime:
    text = value.strip()

    if text.endswith("Z"):
        text = (
            text[:-1]
            + "+00:00"
        )

    result = datetime.fromisoformat(
        text
    )

    if result.tzinfo is None:
        raise ValueError(
            "Timestamp has no timezone: "
            f"{value!r}"
        )

    return result


def run_command(
    command: list[str],
) -> None:
    print()
    print(
        "$",
        " ".join(command),
    )
    print()

    subprocess.run(
        command,
        cwd=ROOT,
        check=True,
    )


def normalize_selections(
    raw: Any,
) -> dict[str, list[int]]:
    if (
        isinstance(raw, dict)
        and isinstance(
            raw.get("selections"),
            dict,
        )
    ):
        raw = raw["selections"]

    if not isinstance(
        raw,
        dict,
    ):
        raise ValueError(
            "Selections file must be "
            "an object keyed 1..7."
        )

    expected = {
        str(value)
        for value
        in range(1, 8)
    }

    actual = {
        str(key)
        for key
        in raw.keys()
    }

    if actual != expected:
        raise ValueError(
            "Selections must contain "
            "exactly legs 1..7."
        )

    result = {}

    for leg in range(1, 8):
        values = raw[
            str(leg)
        ]

        if (
            not isinstance(
                values,
                list,
            )
            or not values
        ):
            raise ValueError(
                f"V75-{leg} must contain "
                "at least one selection."
            )

        numbers = [
            int(value)
            for value
            in values
        ]

        if (
            len(numbers)
            != len(set(numbers))
        ):
            raise ValueError(
                f"V75-{leg} contains "
                "duplicates."
            )

        result[
            str(leg)
        ] = numbers

    return result


def validate_against_field(
    selections: dict[
        str,
        list[int],
    ],
    hybrid: dict[str, Any],
) -> None:
    legs = {
        int(leg["leg"]):
            leg
        for leg
        in hybrid["legs"]
    }

    if set(legs) != set(
        range(1, 8)
    ):
        raise ValueError(
            "Hybrid input does not "
            "contain exactly seven legs."
        )

    for leg_no in range(1, 8):
        eligible = {
            int(
                horse[
                    "startNumber"
                ]
            )
            for horse
            in legs[
                leg_no
            ][
                "horses"
            ]
        }

        supplied = set(
            selections[
                str(leg_no)
            ]
        )

        unknown = (
            supplied
            - eligible
        )

        if unknown:
            raise ValueError(
                f"V75-{leg_no} contains "
                f"ineligible/unknown starts: "
                f"{sorted(unknown)}"
            )


def verify_prepare_artifacts(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
) -> None:
    if (
        manifest.get("pipeline")
        != "live-v75-hybrid-v1"
    ):
        raise RuntimeError(
            "Not a live-v75-hybrid-v1 "
            "prepare run."
        )

    if (
        manifest.get("phase")
        != "AWAITING_STALLTIPS"
    ):
        raise RuntimeError(
            "Prepare run is not "
            "AWAITING_STALLTIPS."
        )

    files = manifest.get(
        "files",
        {},
    )

    expected_empty = (
        "stalltipsInput",
        "classifiedInput",
        "hybridTicket",
    )

    for key in expected_empty:
        if files.get(key) is not None:
            raise RuntimeError(
                f"Prepare manifest already "
                f"contains {key}."
            )

    artifact_hashes = manifest.get(
        "artifactHashes",
        {},
    )

    mapping = {
        "baseRunManifest":
            "run-manifest.json",
        "prediction":
            (
                "candidate-v2a-speed-"
                "predictions.json"
            ),
        "modelTicket":
            "live-ticket.json",
        "hybridInput":
            "hybrid-input.json",
    }

    for key, relative in (
        mapping.items()
    ):
        path = (
            run_dir
            / relative
        )

        if not path.is_file():
            raise RuntimeError(
                f"Prepare artifact missing: "
                f"{relative}"
            )

        expected = (
            artifact_hashes.get(key)
        )

        actual = sha256_file(
            path
        )

        if actual != expected:
            raise RuntimeError(
                f"Prepare artifact changed: "
                f"{relative}"
            )


def first_start_time(
    *,
    run_dir: Path,
    synthetic: bool,
) -> tuple[
    datetime | None,
    str | None,
]:
    path = (
        run_dir
        / "normalized"
        / "pre-race.json"
    )

    if not path.is_file():
        if synthetic:
            return (
                None,
                None,
            )

        raise RuntimeError(
            "Real prospective finalization "
            "requires normalized/pre-race.json "
            "to prove first start time."
        )

    doc = load(path)

    raw = (
        doc.get(
            "pool",
            {},
        ).get(
            "startTime"
        )
    )

    if not isinstance(
        raw,
        str,
    ) or not raw.strip():
        if synthetic:
            return (
                None,
                None,
            )

        raise RuntimeError(
            "Pre-race data has no "
            "pool.startTime."
        )

    return (
        parse_iso_datetime(
            raw
        ),
        raw,
    )


def ensure_no_results(
    run_dir: Path,
) -> None:
    forbidden = [
        run_dir
        / "normalized"
        / "outcomes.json",
    ]

    forbidden.extend(
        run_dir.rglob(
            "results-probe.json"
        )
    )

    for path in forbidden:
        if path.exists():
            raise RuntimeError(
                "Result/outcome artifact "
                f"exists: {path}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Record actual pre-race "
            "Stalltips and finalize frozen "
            "Hybrid Selector v1."
        )
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--selections-file",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--source",
        required=True,
    )

    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help=(
            "Contract-test only. "
            "Never use for prospective "
            "performance evidence."
        ),
    )

    args = parser.parse_args()

    verify_frozen()

    run_dir = (
        args.run_dir
        .expanduser()
        .resolve()
    )

    selections_path = (
        args.selections_file
        .expanduser()
        .resolve()
    )

    prepare_manifest_path = (
        run_dir
        / "hybrid-run-manifest.json"
    )

    hybrid_input_path = (
        run_dir
        / "hybrid-input.json"
    )

    final_paths = {
        "stalltips":
            run_dir
            / "stalltips-input.json",
        "classified":
            run_dir
            / "hybrid-classified.json",
        "ticket":
            run_dir
            / "hybrid-ticket.json",
        "manifest":
            run_dir
            / "hybrid-final-manifest.json",
    }

    for path in (
        prepare_manifest_path,
        hybrid_input_path,
        selections_path,
    ):
        if not path.is_file():
            raise RuntimeError(
                f"Required file missing: "
                f"{path}"
            )

    for path in final_paths.values():
        if path.exists():
            raise RuntimeError(
                "Final artifact already "
                f"exists: {path}"
            )

    prepare_manifest = load(
        prepare_manifest_path
    )

    verify_prepare_artifacts(
        run_dir=run_dir,
        manifest=
            prepare_manifest,
    )

    ensure_no_results(
        run_dir
    )

    synthetic = bool(
        args.allow_synthetic
    )

    if (
        prepare_manifest.get(
            "guardrails",
            {},
        ).get(
            "syntheticSmokeTest",
            False,
        )
        != synthetic
    ):
        raise RuntimeError(
            "Synthetic mode does not "
            "match prepare provenance."
        )

    hybrid = load(
        hybrid_input_path
    )

    if (
        hybrid.get("stalltips", {}).get(
            "status"
        )
        != "NOT_RECORDED"
    ):
        raise RuntimeError(
            "Hybrid input already contains "
            "Stalltips."
        )

    selections = normalize_selections(
        load(
            selections_path
        )
    )

    validate_against_field(
        selections,
        hybrid,
    )

    row_price = float(
        hybrid[
            "modelTicket"
        ][
            "rowPriceNok"
        ]
    )

    model_budget = float(
        hybrid[
            "modelTicket"
        ][
            "selectedBudgetNok"
        ]
    )

    stalltips_rows = math.prod(
        len(
            selections[
                str(leg)
            ]
        )
        for leg
        in range(1, 8)
    )

    stalltips_cost = (
        stalltips_rows
        * row_price
    )

    if (
        not synthetic
        and stalltips_cost
        > model_budget + 1e-9
    ):
        raise RuntimeError(
            "Stalltips ticket exceeds "
            f"selected budget: "
            f"{stalltips_cost:.2f} > "
            f"{model_budget:.2f} NOK."
        )

    start_time, start_time_raw = (
        first_start_time(
            run_dir=run_dir,
            synthetic=synthetic,
        )
    )

    recorded_at = (
        datetime.now()
        .astimezone()
    )

    if (
        not synthetic
        and (
            start_time is None
            or recorded_at
            >= start_time
        )
    ):
        raise RuntimeError(
            "Stalltips was not recorded "
            "before V75 first start."
        )

    canonical_stalltips = {
        "schemaVersion":
            "1.0",
        "package":
            "v75-stalltips-input",
        "raceDate":
            hybrid["raceDate"],
        "raceDayKey":
            hybrid["raceDayKey"],
        "source":
            args.source,
        "recordedAt":
            recorded_at.isoformat(),
        "recordedPreRace":
            bool(
                not synthetic
            ),
        "synthetic":
            synthetic,
        "selections":
            selections,
        "ticketStructure": {
            "rows":
                stalltips_rows,
            "rowPriceNok":
                row_price,
            "costNok":
                stalltips_cost,
            "referenceBudgetNok":
                model_budget,
            "unusedReferenceBudgetNok":
                (
                    model_budget
                    - stalltips_cost
                ),
        },
    }

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix=
                ".hybrid-finalize-",
            dir=run_dir,
        )
    )

    try:
        temp_stalltips = (
            temp_dir
            / "stalltips-input.json"
        )

        temp_classified = (
            temp_dir
            / "hybrid-classified.json"
        )

        temp_ticket = (
            temp_dir
            / "hybrid-ticket.json"
        )

        save(
            temp_stalltips,
            canonical_stalltips,
        )

        run_command(
            [
                sys.executable,
                str(
                    ROOT
                    / "scripts"
                    / "apply_stalltips_to_hybrid_v1.py"
                ),
                "--hybrid-input",
                str(
                    hybrid_input_path
                ),
                "--stalltips",
                str(
                    temp_stalltips
                ),
                "--output",
                str(
                    temp_classified
                ),
            ]
        )

        selector_command = [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "build_hybrid_ticket_v1.py"
            ),
            "--classified-input",
            str(
                temp_classified
            ),
            "--output",
            str(
                temp_ticket
            ),
        ]

        if synthetic:
            selector_command.append(
                "--allow-synthetic"
            )

        run_command(
            selector_command
        )

        classified = load(
            temp_classified
        )

        ticket = load(
            temp_ticket
        )

        if (
            classified.get(
                "hybrid",
                {},
            ).get(
                "status"
            )
            != "CLASSIFIED_AWAITING_SELECTOR"
        ):
            raise RuntimeError(
                "Classifier output state "
                "is invalid."
            )

        if (
            ticket.get("package")
            != "v75-hybrid-ticket"
        ):
            raise RuntimeError(
                "Selector output package "
                "is invalid."
            )

        if (
            ticket.get("selector")
            != "CONSERVATIVE_ONE_SWAP_V1"
        ):
            raise RuntimeError(
                "Unexpected selector."
            )

        if (
            ticket.get(
                "guardrails",
                {},
            ).get(
                "outcomesUsed"
            )
            is not False
        ):
            raise RuntimeError(
                "Hybrid ticket outcome "
                "guardrail failed."
            )

        if (
            ticket.get(
                "guardrails",
                {},
            ).get(
                "rowStructurePreserved"
            )
            is not True
        ):
            raise RuntimeError(
                "Hybrid row structure "
                "was not preserved."
            )

        expected_rows = int(
            hybrid[
                "modelTicket"
            ][
                "actualRows"
            ]
        )

        actual_rows = int(
            ticket[
                "hybridTicket"
            ][
                "actualRows"
            ]
        )

        if actual_rows != expected_rows:
            raise RuntimeError(
                "Hybrid row count differs "
                "from model ticket."
            )

        finalized_at = (
            datetime.now()
            .astimezone()
        )

        prospective_valid = bool(
            not synthetic
            and start_time is not None
            and recorded_at < start_time
            and finalized_at < start_time
        )

        if (
            not synthetic
            and not prospective_valid
        ):
            raise RuntimeError(
                "Hybrid finalization did "
                "not complete before first "
                "V75 start."
            )

        # Only after every guardrail has
        # passed do canonical artifacts
        # become visible in the run dir.
        temp_stalltips.replace(
            final_paths[
                "stalltips"
            ]
        )

        temp_classified.replace(
            final_paths[
                "classified"
            ]
        )

        temp_ticket.replace(
            final_paths[
                "ticket"
            ]
        )

        final_manifest = {
            "schemaVersion":
                "1.0",
            "pipeline":
                "live-v75-hybrid-v1",
            "phase":
                "FINALIZED",
            "selector":
                "CONSERVATIVE_ONE_SWAP_V1",

            "raceDate":
                hybrid["raceDate"],
            "raceDayKey":
                hybrid["raceDayKey"],
            "raceDayName":
                hybrid["raceDayName"],

            "recordedAt":
                recorded_at.isoformat(),
            "finalizedAt":
                finalized_at.isoformat(),
            "firstStartTime":
                start_time_raw,

            "prospectiveValid":
                prospective_valid,

            "stalltipsTicket": {
                "source":
                    args.source,
                "rows":
                    stalltips_rows,
                "costNok":
                    stalltips_cost,
                "referenceBudgetNok":
                    model_budget,
            },

            "modelTicket": {
                "rows":
                    int(
                        hybrid[
                            "modelTicket"
                        ][
                            "actualRows"
                        ]
                    ),
                "costNok":
                    float(
                        hybrid[
                            "modelTicket"
                        ][
                            "actualCostNok"
                        ]
                    ),
            },

            "hybridTicket": {
                "rows":
                    int(
                        ticket[
                            "hybridTicket"
                        ][
                            "actualRows"
                        ]
                    ),
                "costNok":
                    float(
                        ticket[
                            "hybridTicket"
                        ][
                            "actualCostNok"
                        ]
                    ),
                "swapCount":
                    int(
                        ticket[
                            "changes"
                        ][
                            "swapCount"
                        ]
                    ),
                "bankerDisagreementCount":
                    int(
                        ticket[
                            "changes"
                        ][
                            "bankerDisagreementCount"
                        ]
                    ),
            },

            "files": {
                "prepareManifest":
                    "hybrid-run-manifest.json",
                "hybridInput":
                    "hybrid-input.json",
                "stalltipsInput":
                    "stalltips-input.json",
                "classifiedInput":
                    "hybrid-classified.json",
                "hybridTicket":
                    "hybrid-ticket.json",
            },

            "frozenHashes":
                dict(FROZEN),

            "artifactHashes": {
                "prepareManifest":
                    sha256_file(
                        prepare_manifest_path
                    ),
                "hybridInput":
                    sha256_file(
                        hybrid_input_path
                    ),
                "stalltipsInput":
                    sha256_file(
                        final_paths[
                            "stalltips"
                        ]
                    ),
                "classifiedInput":
                    sha256_file(
                        final_paths[
                            "classified"
                        ]
                    ),
                "hybridTicket":
                    sha256_file(
                        final_paths[
                            "ticket"
                        ]
                    ),
            },

            "guardrails": {
                "resultsPresent":
                    False,
                "outcomesUsed":
                    False,
                "stalltipsRecorded":
                    True,
                "classifierApplied":
                    True,
                "selectorApplied":
                    True,
                "v2aRetuned":
                    False,
                "selectorRetuned":
                    False,
                "automaticBankerSwap":
                    False,
                "hybridProbabilityFabricated":
                    False,
                "syntheticSmokeTest":
                    synthetic,
                "completedBeforeFirstStart":
                    bool(
                        prospective_valid
                    ),
            },
        }

        save(
            final_paths[
                "manifest"
            ],
            final_manifest,
        )

    finally:
        if temp_dir.exists():
            shutil.rmtree(
                temp_dir
            )

    print()
    print(
        "=== HYBRID FINALIZE COMPLETE ==="
    )

    print(
        "Run:",
        run_dir,
    )

    print(
        f"Stalltips: "
        f"{stalltips_rows} rows / "
        f"{stalltips_cost:.2f} NOK"
    )

    print(
        f"Hybrid: "
        f"{ticket['hybridTicket']['actualRows']} "
        f"rows / "
        f"{ticket['hybridTicket']['actualCostNok']:.2f} NOK"
    )

    print(
        f"Swaps: "
        f"{ticket['changes']['swapCount']}"
    )

    print(
        f"Banker disagreements: "
        f"{ticket['changes']['bankerDisagreementCount']}"
    )

    print(
        "Prospective valid:",
        prospective_valid,
    )

    print()
    print(
        "PASS: frozen classifier used."
    )

    print(
        "PASS: frozen selector used."
    )

    print(
        "PASS: no outcomes used."
    )

    if synthetic:
        print(
            "PASS: synthetic smoke run "
            "is NOT marked prospective."
        )
    else:
        print(
            "PASS: Stalltips recorded and "
            "hybrid finalized before first "
            "V75 start."
        )


if __name__ == "__main__":
    main()
