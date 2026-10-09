from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MODULE_PATH = (
    ROOT
    / "scripts"
    / "compare_stalltips_consensus.py"
)

spec = importlib.util.spec_from_file_location(
    "stalltips_temporal_comparison",
    MODULE_PATH,
)

if spec is None or spec.loader is None:
    raise RuntimeError(
        "Could not load comparator"
    )

module = importlib.util.module_from_spec(
    spec
)

sys.modules[spec.name] = module

spec.loader.exec_module(
    module
)


def make_observation(
    selection_frequency: float,
    banker_frequency: float,
) -> dict:
    return {
        "observation": {
            "firstCapturedAt":
                "2026-10-08T10:00:00+02:00",
            "lastCapturedAt":
                "2026-10-08T10:01:00+02:00",
            "durationSeconds":
                60.0,
            "timingSource":
                "CAPTURE_SESSION_WINDOW",
            "sampleCount":
                20,
        },
        "selectedGroup": {
            "sampleCount":
                20,
            "raceDayKey":
                "BT_NR_2026-10-10",
            "raceDate":
                "2026-10-10",
            "trackCode":
                "BT",
            "product":
                "V75",
            "requestedStakeOre":
                38900,
            "rowPriceOre":
                50,
        },
        "legs": [
            {
                "legNumber":
                    leg,
                "alwaysSelected":
                    (
                        [1]
                        if (
                            leg == 1
                            and selection_frequency
                            == 1.0
                        )
                        else []
                    ),
                "bankerCandidates":
                    (
                        [
                            {
                                "startNumber":
                                    1,
                                "bankerFrequency":
                                    banker_frequency,
                            }
                        ]
                        if (
                            leg == 1
                            and banker_frequency
                            > 0
                        )
                        else []
                    ),
                "horses":
                    (
                        [
                            {
                                "startNumber":
                                    1,
                                "selectionFrequency":
                                    selection_frequency,
                                "alwaysSelected":
                                    selection_frequency
                                    == 1.0,
                            }
                        ]
                        if leg == 1
                        else []
                    ),
            }
            for leg in range(
                1,
                8,
            )
        ],
    }


earlier = make_observation(
    1.0,
    0.70,
)

later = make_observation(
    0.65,
    0.35,
)

result = module.compare(
    earlier,
    later,
)

leg1 = result[
    "legs"
][0]

horse = leg1[
    "horses"
][0]

assert (
    horse[
        "selection"
    ][
        "deltaPercentagePoints"
    ]
    == -35.0
)

assert (
    horse[
        "selection"
    ][
        "changeBand"
    ]
    == "LARGE_DOWN"
)

assert (
    horse[
        "banker"
    ][
        "deltaPercentagePoints"
    ]
    == -35.0
)

assert (
    leg1[
        "lostAlwaysSelected"
    ]
    == [1]
)

assert (
    result[
        "guardrails"
    ][
        "statisticalSignificanceClaimed"
    ]
    is False
)

print(
    "PASS: Stalltips temporal comparator contract."
)
