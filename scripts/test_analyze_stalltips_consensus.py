from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MODULE_PATH = (
    ROOT
    / "scripts"
    / "analyze_stalltips_consensus.py"
)

spec = importlib.util.spec_from_file_location(
    "stalltips_consensus",
    MODULE_PATH,
)

if spec is None or spec.loader is None:
    raise RuntimeError(
        "Could not load analyzer"
    )

module = importlib.util.module_from_spec(
    spec
)

# Python 3.14 dataclasses resolves the defining module
# through sys.modules while the class decorator executes.
sys.modules[spec.name] = module

spec.loader.exec_module(
    module
)


def make_payload(
    first_leg: list[int],
) -> dict:
    selections = []

    for leg in range(
        1,
        8,
    ):
        marks = (
            first_leg
            if leg == 1
            else [leg]
        )

        selections.append(
            {
                "legNumber": leg,
                "raceNumber": 3,
                "selectionIndex": leg,
                "marks": marks,
            }
        )

    return {
        "result": {
            "rowPrice": 50,
            "selections": selections,
            "product": "V75",
            "raceNumber": 3,
            "betMethod": "LynToto",
            "raceDayKey":
                "BT_NR_2026-10-10",
        },
        "success": True,
        "errorCode": None,
        "message": None,
    }


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)

    records = []

    drafts = [
        [1],
        [1],
        [1, 2],
    ]

    for index, first_leg in enumerate(
        drafts,
        start=1,
    ):
        name = (
            f"draft-{index:02d}.json"
        )

        (root / name).write_text(
            json.dumps(
                make_payload(
                    first_leg
                )
            ),
            encoding="utf-8",
        )

        records.append(
            {
                "index": index,
                "capturedAt": (
                    "2026-10-08T16:00:"
                    f"{index:02d}+02:00"
                ),
                "url": (
                    "https://www.rikstoto.no/"
                    "api/lyntoto/draft?"
                    "betData="
                    "d:2026-10-10|"
                    "t:BT|"
                    "g:V75|"
                    "org:NR|"
                    "p:38900|"
                    "pr:50|"
                    "o:2|"
                    "l:3"
                ),
                "status": 200,
                "file": name,
            }
        )

    (root / "manifest.json").write_text(
        json.dumps(
            {
                "captureCount": 3,
                "records": records,
            }
        ),
        encoding="utf-8",
    )

    analysis = (
        module.analyze_capture(
            root
        )
    )

    assert (
        analysis[
            "selectedGroup"
        ][
            "sampleCount"
        ]
        == 3
    )

    observation = analysis[
        "observation"
    ]

    assert (
        observation[
            "firstCapturedAt"
        ]
        == "2026-10-08T16:00:01+02:00"
    )

    assert (
        observation[
            "lastCapturedAt"
        ]
        == "2026-10-08T16:00:03+02:00"
    )

    assert (
        observation[
            "durationSeconds"
        ]
        == 2.0
    )

    assert (
        observation[
            "sampleCount"
        ]
        == 3
    )

    assert (
        analysis[
            "ticketVariation"
        ][
            "uniqueTicketCount"
        ]
        == 2
    )

    leg1 = analysis[
        "legs"
    ][0]

    horse1 = next(
        row
        for row
        in leg1[
            "horses"
        ]
        if row[
            "startNumber"
        ]
        == 1
    )

    horse2 = next(
        row
        for row
        in leg1[
            "horses"
        ]
        if row[
            "startNumber"
        ]
        == 2
    )

    assert (
        horse1[
            "selectionFrequency"
        ]
        == 1.0
    )

    assert (
        horse1[
            "bankerCount"
        ]
        == 2
    )

    assert (
        horse1[
            "descriptiveBand"
        ]
        == "ALWAYS"
    )

    assert (
        horse2[
            "selectionFrequency"
        ]
        == round(
            1 / 3,
            6,
        )
    )

    assert (
        horse2[
            "descriptiveBand"
        ]
        == "ROTATING"
    )

    assert (
        analysis[
            "guardrails"
        ][
            "generatorFrequencyIsNotWinProbability"
        ]
        is True
    )

print(
    "PASS: Stalltips consensus analyzer "
    "contract."
)
