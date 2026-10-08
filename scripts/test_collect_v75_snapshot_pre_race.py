from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COLLECTOR_PATH = (
    ROOT
    / "scripts"
    / "collect_v75_snapshot.py"
)


def load_collector():
    spec = (
        importlib.util
        .spec_from_file_location(
            "collect_v75_snapshot_contract",
            COLLECTOR_PATH,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Could not load collector."
        )

    module = (
        importlib.util
        .module_from_spec(spec)
    )

    spec.loader.exec_module(
        module
    )

    return module


class DummyRequestContext:
    def dispose(self):
        pass


class DummyRequestFactory:
    def new_context(
        self,
        **_kwargs,
    ):
        return DummyRequestContext()


class DummyPlaywright:
    def __init__(self):
        self.request = (
            DummyRequestFactory()
        )


class DummyPlaywrightManager:
    def __enter__(self):
        return DummyPlaywright()

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False


def build_discovery(
    path: Path,
) -> str:
    race_day_key = (
        "TEST_2026-10-10"
    )

    payload = {
        "schemaVersion":
            "1.0",
        "meetings": [
            {
                "date":
                    "2026-10-10",
                "raceDayKey":
                    race_day_key,
                "raceDayName":
                    "Synthetic",
                "countryIsoCode":
                    "NO",
                "isDomestic":
                    True,
                "poolKey":
                    "TEST-V75",
                "isMultiTrack":
                    False,
                "singleTrack":
                    True,
                "raceKeys": [
                    (
                        f"{race_day_key}"
                        f"#{number}"
                    )
                    for number
                    in range(
                        1,
                        8,
                    )
                ],
                "raceNumbers":
                    list(
                        range(
                            1,
                            8,
                        )
                    ),
                "legCount":
                    7,
            }
        ],
    }

    path.write_text(
        json.dumps(
            payload,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return race_day_key


def synthetic_payload(
    path: str,
):
    if path.endswith(
        "/raceInfo"
    ):
        return [
            {
                "raceNumber":
                    number,
                "distance":
                    2100,
                "startMethod":
                    "AUTO",
            }
            for number
            in range(
                1,
                8,
            )
        ]

    if path.endswith(
        "/starts"
    ):
        return {
            str(number): [
                {
                    "startNumber":
                        1,
                    "isScratched":
                        False,
                }
            ]
            for number
            in range(
                1,
                8,
            )
        }

    if path.endswith(
        "/formrowstrot"
    ):
        return [
            {
                "raceNumber":
                    number,
                "formRowsForStarts": [
                    {
                        "startNumber":
                            1,
                        "formRows": [
                            {
                                "raceDate":
                                    (
                                        "2026-10-01"
                                        "T12:00:00"
                                    ),
                            }
                        ],
                    }
                ],
            }
            for number
            in range(
                1,
                8,
            )
        ]

    if (
        "/api/game/program/"
        in path
        and "/V/trot/"
        in path
    ):
        race_number = int(
            path.rsplit(
                "/",
                1,
            )[-1]
        )

        race_day_key = (
            "TEST_2026-10-10"
        )

        return [
            {
                "raceNumber":
                    race_number,
                "raceKey":
                    (
                        f"{race_day_key}"
                        f"#{race_number}"
                    ),
                "starts": [
                    {
                        "startNumber":
                            1,
                    }
                ],
            }
        ]

    if path.endswith(
        "/raceresults"
    ):
        return {
            "raceWinners": {
                str(number): [
                    {
                        "place":
                            1,
                        "startNumber":
                            1,
                    }
                ]
                for number
                in range(
                    1,
                    8,
                )
            }
        }

    raise AssertionError(
        f"Unexpected API path: {path}"
    )


def run_case(
    *,
    pre_race_only: bool,
):
    collector = load_collector()

    calls = []

    def fake_get_json(
        _request,
        path,
    ):
        calls.append(path)

        return synthetic_payload(
            path
        )

    collector.get_json = (
        fake_get_json
    )

    collector.sync_playwright = (
        lambda:
            DummyPlaywrightManager()
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        discovery = (
            root
            / "discovery.json"
        )

        race_day_key = (
            build_discovery(
                discovery
            )
        )

        output_root = (
            root
            / "raw"
        )

        argv = [
            str(
                COLLECTOR_PATH
            ),
            "--discovery",
            str(discovery),
            "--race-day-key",
            race_day_key,
            "--output-root",
            str(output_root),
        ]

        if pre_race_only:
            argv.append(
                "--pre-race-only"
            )

        previous_argv = sys.argv

        try:
            sys.argv = argv
            collector.main()
        finally:
            sys.argv = (
                previous_argv
            )

        output = (
            output_root
            / "2026-10-10"
        )

        manifest = json.loads(
            (
                output
                / "manifest.json"
            ).read_text(
                encoding="utf-8"
            )
        )

        return {
            "calls":
                calls,
            "resultsProbeExists":
                (
                    output
                    / "results-probe.json"
                ).exists(),
            "manifest":
                manifest,
            "requiredRawFilesExist":
                all(
                    path.exists()
                    for path in [
                        output
                        / "v75-pool.json",
                        output
                        / "race-info.json",
                        output
                        / "starts.json",
                        output
                        / "form-rows-trot.json",
                        *[
                            (
                                output
                                / "program"
                                / (
                                    f"v75-"
                                    f"{leg}.json"
                                )
                            )
                            for leg
                            in range(
                                1,
                                8,
                            )
                        ],
                    ]
                ),
        }


live = run_case(
    pre_race_only=True,
)

assert (
    live[
        "requiredRawFilesExist"
    ]
)

assert not any(
    "/api/results/"
    in path
    for path
    in live["calls"]
)

assert (
    live[
        "resultsProbeExists"
    ]
    is False
)

assert (
    live["manifest"][
        "mode"
    ]
    == "pre-race"
)

assert (
    "winnerStartNumbers"
    not in live["manifest"]
)

assert (
    live["manifest"][
        "guardrails"
    ][
        "resultsFetched"
    ]
    is False
)

print(
    "PASS: pre-race-only collector "
    "never calls results endpoint."
)

print(
    "PASS: pre-race-only collector "
    "writes no results-probe.json."
)

print(
    "PASS: pre-race raw snapshot "
    "contains required model inputs."
)


historical = run_case(
    pre_race_only=False,
)

assert any(
    "/api/results/"
    in path
    for path
    in historical["calls"]
)

assert (
    historical[
        "resultsProbeExists"
    ]
    is True
)

assert (
    historical["manifest"][
        "winnerStartNumbers"
    ]
    == [1] * 7
)

assert (
    historical["manifest"][
        "guardrails"
    ][
        "resultsStoredSeparately"
    ]
    is True
)

assert (
    "mode"
    not in historical[
        "manifest"
    ]
)

assert (
    "resultsFetched"
    not in historical[
        "manifest"
    ][
        "guardrails"
    ]
)

print(
    "PASS: historical collector "
    "still fetches results."
)

print(
    "PASS: historical collector "
    "retains original manifest semantics."
)

print(
    "PASS: collector pre-race contract."
)
