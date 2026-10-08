from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PATH = (
    ROOT
    / "scripts"
    / "run_live_v75.py"
)


def load_module():
    spec = (
        importlib.util
        .spec_from_file_location(
            "run_live_v75_contract",
            PATH,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Could not load live runner."
        )

    module = (
        importlib.util
        .module_from_spec(spec)
    )

    spec.loader.exec_module(
        module
    )

    return module


module = load_module()

module.assert_policy_contract()

assert (
    module.FROZEN_BANKER_THRESHOLD
    == 0.35
)

print(
    "PASS: frozen 35% challenger "
    "policy loaded."
)


discovery = {
    "meetings": [
        {
            "date":
                "2026-10-10",
            "raceDayKey":
                "TEST_2026-10-10",
            "raceDayName":
                "Synthetic",
            "countryIsoCode":
                "NO",
            "singleTrack":
                True,
            "legCount":
                7,
        }
    ]
}

meeting = module.select_meeting(
    discovery,
    race_date="2026-10-10",
    race_day_key=None,
)

assert (
    meeting["raceDayKey"]
    == "TEST_2026-10-10"
)

print(
    "PASS: unique live V75 meeting "
    "is selected."
)


ambiguous = {
    "meetings": [
        discovery["meetings"][0],
        {
            **discovery["meetings"][0],
            "raceDayKey":
                "SECOND_2026-10-10",
            "raceDayName":
                "Second",
        },
    ]
}

try:
    module.select_meeting(
        ambiguous,
        race_date="2026-10-10",
        race_day_key=None,
    )
except RuntimeError:
    pass
else:
    raise AssertionError(
        "Ambiguous discovery did not fail."
    )

explicit = module.select_meeting(
    ambiguous,
    race_date="2026-10-10",
    race_day_key=
        "SECOND_2026-10-10",
)

assert (
    explicit["raceDayKey"]
    == "SECOND_2026-10-10"
)

print(
    "PASS: ambiguous discovery refuses "
    "unless raceDayKey is explicit."
)


with tempfile.TemporaryDirectory() as tmp:
    run_dir = Path(tmp)

    commands = (
        module
        .build_post_discovery_commands(
            run_dir=run_dir,
            race_date=
                "2026-10-10",
            race_day_key=
                "TEST_2026-10-10",
            selected_budget_nok=
                400.0,
            row_price_nok=
                0.5,
            budget_options_nok=[
                100.0,
                200.0,
                400.0,
                600.0,
            ],
        )
    )

collector = commands[
    "collector"
]

normalizer = commands[
    "normalizer"
]

ticket = commands[
    "ticket"
]

assert (
    "--pre-race-only"
    in collector
)

assert (
    "--results-probe"
    not in normalizer
)

assert (
    "--min-banker-probability"
    in ticket
)

threshold_index = (
    ticket.index(
        "--min-banker-probability"
    )
    + 1
)

assert abs(
    float(
        ticket[
            threshold_index
        ]
    )
    - 0.35
) < 1e-12

all_tokens = [
    str(token)
    for command
    in commands.values()
    for token
    in command
]

assert not any(
    token.endswith(
        "outcomes.json"
    )
    for token
    in all_tokens
)

print(
    "PASS: live orchestration uses "
    "--pre-race-only collector."
)

print(
    "PASS: live normalizer receives "
    "no results probe."
)

print(
    "PASS: frozen 35% challenger "
    "threshold is wired."
)

print(
    "PASS: no outcome file is wired "
    "into live pipeline."
)

print(
    "PASS: live V75 orchestration contract."
)
