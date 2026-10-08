from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
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

DEFAULT_BUDGETS = [
    100.0,
    200.0,
    300.0,
    400.0,
    500.0,
    600.0,
    800.0,
    1000.0,
]


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


def verify_frozen_stack() -> None:
    for relative, expected in (
        FROZEN.items()
    ):
        path = ROOT / relative

        if not path.is_file():
            raise RuntimeError(
                f"Frozen component missing: "
                f"{relative}"
            )

        actual = sha256_file(
            path
        )

        if actual != expected:
            raise RuntimeError(
                f"Frozen component changed: "
                f"{relative}\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}"
            )


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


def existing_run_dirs(
    *,
    output_root: Path,
    race_date: str,
) -> set[Path]:
    date_root = (
        output_root
        / race_date
    )

    if not date_root.exists():
        return set()

    return {
        path.parent.resolve()
        for path
        in date_root.glob(
            "*/run-manifest.json"
        )
        if path.is_file()
    }


def verify_base_manifest(
    manifest: dict[str, Any],
    *,
    allow_synthetic: bool,
) -> None:
    if (
        manifest.get("pipeline")
        != "live-v75-v1"
    ):
        raise RuntimeError(
            "Base run is not "
            "live-v75-v1."
        )

    if (
        manifest.get(
            "syntheticSmokeTest",
            False,
        )
        and not allow_synthetic
    ):
        raise RuntimeError(
            "Synthetic base run refused."
        )

    guardrails = manifest.get(
        "guardrails",
        {},
    )

    expected = {
        "preRaceOnly": True,
        "resultsFetched": False,
        "outcomesGenerated": False,
        "marketUsed": False,
        "modelRetuned": False,
    }

    for key, value in (
        expected.items()
    ):
        if (
            guardrails.get(key)
            is not value
        ):
            raise RuntimeError(
                "Base run guardrail "
                f"failed: {key}"
            )


def attach_hybrid_input(
    *,
    run_dir: Path,
    allow_synthetic: bool,
) -> Path:
    run_dir = (
        run_dir
        .expanduser()
        .resolve()
    )

    manifest_path = (
        run_dir
        / "run-manifest.json"
    )

    predictions_path = (
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

    hybrid_input_path = (
        run_dir
        / "hybrid-input.json"
    )

    hybrid_manifest_path = (
        run_dir
        / "hybrid-run-manifest.json"
    )

    for path in (
        manifest_path,
        predictions_path,
        ticket_path,
    ):
        if not path.is_file():
            raise RuntimeError(
                f"Required base artifact "
                f"missing: {path}"
            )

    if hybrid_input_path.exists():
        raise RuntimeError(
            "Hybrid input already exists; "
            "refusing overwrite."
        )

    if hybrid_manifest_path.exists():
        raise RuntimeError(
            "Hybrid manifest already exists; "
            "refusing overwrite."
        )

    base_manifest = load(
        manifest_path
    )

    verify_base_manifest(
        base_manifest,
        allow_synthetic=
            allow_synthetic,
    )

    # Defense in depth:
    # no result artifacts may exist in
    # this prospective run directory.
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
                "Outcome/result artifact "
                f"present: {path}"
            )

    run_command(
        [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "build_hybrid_input_v1.py"
            ),
            "--predictions",
            str(
                predictions_path
            ),
            "--ticket",
            str(
                ticket_path
            ),
            "--policy",
            "MAX_P7",
            "--output",
            str(
                hybrid_input_path
            ),
        ]
    )

    hybrid = load(
        hybrid_input_path
    )

    if (
        hybrid.get("package")
        != "v75-hybrid-input"
    ):
        raise RuntimeError(
            "Unexpected hybrid input "
            "package."
        )

    if (
        hybrid.get(
            "stalltips",
            {},
        ).get("status")
        != "NOT_RECORDED"
    ):
        raise RuntimeError(
            "Prepared hybrid input "
            "already contains Stalltips."
        )

    if (
        hybrid.get(
            "hybrid",
            {},
        ).get("status")
        != "AWAITING_STALLTIPS"
    ):
        raise RuntimeError(
            "Unexpected hybrid state."
        )

    if (
        hybrid.get(
            "guardrails",
            {},
        ).get("outcomesUsed")
        is not False
    ):
        raise RuntimeError(
            "Hybrid outcome guardrail "
            "failed."
        )

    if (
        hybrid.get(
            "guardrails",
            {},
        ).get("hybridRulesApplied")
        is not False
    ):
        raise RuntimeError(
            "Hybrid selector was applied "
            "during prepare phase."
        )

    manifest = {
        "schemaVersion": "1.0",
        "pipeline":
            "live-v75-hybrid-v1",
        "phase":
            "AWAITING_STALLTIPS",
        "createdAt":
            datetime.now()
            .astimezone()
            .isoformat(),
        "raceDate":
            hybrid["raceDate"],
        "raceDayKey":
            hybrid["raceDayKey"],
        "raceDayName":
            hybrid["raceDayName"],
        "basePipeline":
            "live-v75-v1",
        "baseRunDirectory":
            str(run_dir),
        "selectedBudgetNok":
            hybrid[
                "modelTicket"
            ][
                "selectedBudgetNok"
            ],
        "rowPriceNok":
            hybrid[
                "modelTicket"
            ][
                "rowPriceNok"
            ],
        "files": {
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
            "stalltipsInput":
                None,
            "classifiedInput":
                None,
            "hybridTicket":
                None,
        },
        "frozenHashes":
            dict(FROZEN),
        "artifactHashes": {
            "baseRunManifest":
                sha256_file(
                    manifest_path
                ),
            "prediction":
                sha256_file(
                    predictions_path
                ),
            "modelTicket":
                sha256_file(
                    ticket_path
                ),
            "hybridInput":
                sha256_file(
                    hybrid_input_path
                ),
        },
        "guardrails": {
            "preRaceOnly":
                True,
            "resultsFetched":
                False,
            "outcomesGenerated":
                False,
            "stalltipsRecorded":
                False,
            "classifierApplied":
                False,
            "selectorApplied":
                False,
            "v2aRetuned":
                False,
            "selectorRetuned":
                False,
            "syntheticSmokeTest":
                bool(
                    base_manifest.get(
                        "syntheticSmokeTest",
                        False,
                    )
                ),
        },
    }

    save(
        hybrid_manifest_path,
        manifest,
    )

    print()
    print(
        "=== HYBRID PREPARE COMPLETE ==="
    )

    print(
        "Run:",
        run_dir,
    )

    print(
        "Hybrid input:",
        hybrid_input_path,
    )

    print(
        "Hybrid manifest:",
        hybrid_manifest_path,
    )

    print()
    print(
        "STATUS: AWAITING_STALLTIPS"
    )

    print(
        "PASS: no Stalltips fabricated."
    )

    print(
        "PASS: classifier not applied."
    )

    print(
        "PASS: selector not applied."
    )

    return run_dir


def run_live_and_prepare(
    args: argparse.Namespace,
) -> Path:
    output_root = (
        args.output_root
        .expanduser()
        .resolve()
    )

    race_date = (
        args.date
    )

    before = existing_run_dirs(
        output_root=output_root,
        race_date=race_date,
    )

    command = [
        sys.executable,
        str(
            ROOT
            / "scripts"
            / "run_live_v75.py"
        ),
        "--date",
        race_date,
        "--budget-nok",
        str(
            args.budget_nok
        ),
        "--row-price-nok",
        str(
            args.row_price_nok
        ),
        "--budget-options-nok",
        *[
            str(value)
            for value
            in args.budget_options_nok
        ],
        "--output-root",
        str(output_root),
    ]

    if args.race_day_key:
        command.extend(
            [
                "--race-day-key",
                args.race_day_key,
            ]
        )

    run_command(
        command
    )

    after = existing_run_dirs(
        output_root=output_root,
        race_date=race_date,
    )

    created = sorted(
        after - before
    )

    if len(created) != 1:
        raise RuntimeError(
            "Expected exactly one new "
            "live run directory, found "
            f"{len(created)}."
        )

    return attach_hybrid_input(
        run_dir=created[0],
        allow_synthetic=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run frozen live V75 pipeline "
            "and prepare Hybrid Selector v1 "
            "input without recording "
            "Stalltips or applying selector."
        )
    )

    parser.add_argument(
        "--attach-run-dir",
        type=Path,
        help=(
            "Attach hybrid input to an "
            "already completed live-v75-v1 "
            "run instead of collecting "
            "new live data."
        ),
    )

    parser.add_argument(
        "--allow-synthetic-attach",
        action="store_true",
        help=(
            "Contract-test only. Allows "
            "attachment to a manifest "
            "explicitly marked synthetic."
        ),
    )

    parser.add_argument(
        "--date",
        help="Race date YYYY-MM-DD.",
    )

    parser.add_argument(
        "--budget-nok",
        type=float,
    )

    parser.add_argument(
        "--row-price-nok",
        type=float,
    )

    parser.add_argument(
        "--budget-options-nok",
        type=float,
        nargs="+",
        default=DEFAULT_BUDGETS,
    )

    parser.add_argument(
        "--race-day-key",
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

    verify_frozen_stack()

    print(
        "PASS: complete frozen stack "
        "verified."
    )

    if args.attach_run_dir:
        if any(
            value is not None
            for value in (
                args.date,
                args.budget_nok,
                args.row_price_nok,
                args.race_day_key,
            )
        ):
            raise SystemExit(
                "--attach-run-dir cannot "
                "be combined with live-run "
                "arguments."
            )

        attach_hybrid_input(
            run_dir=
                args.attach_run_dir,
            allow_synthetic=
                args.allow_synthetic_attach,
        )

        return

    if (
        args.date is None
        or args.budget_nok is None
        or args.row_price_nok is None
    ):
        raise SystemExit(
            "Live mode requires --date, "
            "--budget-nok and "
            "--row-price-nok."
        )

    if args.budget_nok <= 0:
        raise SystemExit(
            "--budget-nok must be > 0."
        )

    if args.row_price_nok <= 0:
        raise SystemExit(
            "--row-price-nok must be > 0."
        )

    run_live_and_prepare(
        args
    )


if __name__ == "__main__":
    main()
