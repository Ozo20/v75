from __future__ import annotations

import argparse
import json
import math
import statistics
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


Json = Any


DESCRIPTIVE_BANDS = (
    (1.00, "ALWAYS"),
    (0.50, "FREQUENT"),
    (0.20, "ROTATING"),
    (0.00, "RARE"),
)


def descriptive_band(
    frequency: float,
) -> str:
    for threshold, label in DESCRIPTIVE_BANDS:
        if frequency >= threshold:
            return label

    raise RuntimeError(
        "Could not classify frequency"
    )


def parse_bet_data(
    url: str,
) -> dict[str, str]:
    query = parse_qs(
        urlparse(url).query
    )

    values = query.get("betData")

    if not values:
        raise ValueError(
            "Draft URL has no betData"
        )

    result: dict[str, str] = {}

    for token in values[0].split("|"):
        if ":" not in token:
            continue

        key, value = token.split(
            ":",
            1,
        )

        result[key] = value

    return result


@dataclass(frozen=True)
class CaptureSource:
    path: Path
    manifest_name: str
    manifest_parent: str
    is_zip: bool

    def read_json(
        self,
        relative_name: str,
    ) -> Json:
        if self.is_zip:
            full_name = (
                f"{self.manifest_parent}/"
                f"{relative_name}"
                if self.manifest_parent
                else relative_name
            )

            with zipfile.ZipFile(
                self.path
            ) as archive:
                return json.loads(
                    archive.read(
                        full_name
                    ).decode(
                        "utf-8"
                    )
                )

        manifest_path = (
            self.path
            / self.manifest_name
        )

        full_path = (
            manifest_path.parent
            / relative_name
        )

        return json.loads(
            full_path.read_text(
                encoding="utf-8"
            )
        )

    def read_manifest(
        self,
    ) -> Json:
        if self.is_zip:
            with zipfile.ZipFile(
                self.path
            ) as archive:
                return json.loads(
                    archive.read(
                        self.manifest_name
                    ).decode(
                        "utf-8"
                    )
                )

        return json.loads(
            (
                self.path
                / self.manifest_name
            ).read_text(
                encoding="utf-8"
            )
        )


def open_capture(
    path: Path,
) -> CaptureSource:
    if path.is_file():
        if path.suffix.lower() != ".zip":
            raise ValueError(
                "Capture file must be a ZIP"
            )

        with zipfile.ZipFile(
            path
        ) as archive:
            manifests = sorted(
                name
                for name in archive.namelist()
                if (
                    name == "manifest.json"
                    or name.endswith(
                        "/manifest.json"
                    )
                )
            )

        if len(manifests) != 1:
            raise ValueError(
                "Expected exactly one "
                "manifest.json in ZIP"
            )

        manifest_name = manifests[0]

        parent = (
            manifest_name.rsplit(
                "/",
                1,
            )[0]
            if "/" in manifest_name
            else ""
        )

        return CaptureSource(
            path=path,
            manifest_name=manifest_name,
            manifest_parent=parent,
            is_zip=True,
        )

    if path.is_dir():
        manifests = sorted(
            path.rglob(
                "manifest.json"
            )
        )

        if len(manifests) != 1:
            raise ValueError(
                "Expected exactly one "
                "manifest.json in capture directory"
            )

        manifest = manifests[0]

        return CaptureSource(
            path=path,
            manifest_name=str(
                manifest.relative_to(
                    path
                )
            ),
            manifest_parent="",
            is_zip=False,
        )

    raise FileNotFoundError(
        str(path)
    )


def ticket_signature(
    result: dict[str, Any],
) -> tuple[
    tuple[int, tuple[int, ...]],
    ...
]:
    selections = result.get(
        "selections"
    )

    if not isinstance(
        selections,
        list,
    ):
        raise ValueError(
            "Draft result has no selections"
        )

    return tuple(
        (
            int(
                selection[
                    "legNumber"
                ]
            ),
            tuple(
                int(mark)
                for mark
                in selection[
                    "marks"
                ]
            ),
        )
        for selection
        in sorted(
            selections,
            key=lambda row:
                int(
                    row[
                        "legNumber"
                    ]
                ),
        )
    )


def validate_result(
    result: dict[str, Any],
) -> None:
    if result.get(
        "product"
    ) != "V75":
        raise ValueError(
            "Expected V75 draft"
        )

    selections = result.get(
        "selections"
    )

    if not isinstance(
        selections,
        list,
    ):
        raise ValueError(
            "Missing selections"
        )

    if len(selections) != 7:
        raise ValueError(
            "Expected exactly seven legs"
        )

    leg_numbers = sorted(
        int(
            row["legNumber"]
        )
        for row
        in selections
    )

    if leg_numbers != list(
        range(1, 8)
    ):
        raise ValueError(
            "Expected leg numbers 1..7"
        )

    for selection in selections:
        marks = selection.get(
            "marks"
        )

        if (
            not isinstance(
                marks,
                list,
            )
            or not marks
        ):
            raise ValueError(
                "Every leg must have "
                "at least one mark"
            )

        normalized = [
            int(mark)
            for mark in marks
        ]

        if len(
            normalized
        ) != len(
            set(normalized)
        ):
            raise ValueError(
                "Duplicate horse in leg"
            )


def analyze_capture(
    capture_path: Path,
) -> dict[str, Any]:
    source = open_capture(
        capture_path
    )

    manifest = (
        source.read_manifest()
    )

    records = manifest.get(
        "records"
    )

    if not isinstance(
        records,
        list,
    ):
        raise ValueError(
            "Capture manifest has no records"
        )

    groups: dict[
        str,
        list[
            tuple[
                dict[str, Any],
                dict[str, str],
                dict[str, Any],
            ]
        ],
    ] = {}

    rejected = 0

    for record in records:
        if not isinstance(
            record,
            dict,
        ):
            rejected += 1
            continue

        url = record.get(
            "url"
        )

        file_name = record.get(
            "file"
        )

        if (
            not isinstance(
                url,
                str,
            )
            or not isinstance(
                file_name,
                str,
            )
        ):
            rejected += 1
            continue

        bet_data = parse_bet_data(
            url
        )

        payload = source.read_json(
            file_name
        )

        if payload.get(
            "success"
        ) is not True:
            rejected += 1
            continue

        result = payload.get(
            "result"
        )

        if not isinstance(
            result,
            dict,
        ):
            rejected += 1
            continue

        validate_result(
            result
        )

        exact_bet_data = (
            parse_qs(
                urlparse(
                    url
                ).query
            )["betData"][0]
        )

        groups.setdefault(
            exact_bet_data,
            [],
        ).append(
            (
                record,
                bet_data,
                result,
            )
        )

    if not groups:
        raise ValueError(
            "No valid Stalltips drafts found"
        )

    selected_bet_data, selected = max(
        groups.items(),
        key=lambda row: (
            len(
                row[1]
            ),
            row[0],
        ),
    )

    sample_count = len(
        selected
    )

    bet_data = selected[
        0
    ][1]

    results = [
        row[2]
        for row
        in selected
    ]

    race_day_keys = {
        str(
            result[
                "raceDayKey"
            ]
        )
        for result
        in results
    }

    if len(
        race_day_keys
    ) != 1:
        raise ValueError(
            "Selected group spans "
            "multiple raceDayKey values"
        )

    row_prices = {
        int(
            result[
                "rowPrice"
            ]
        )
        for result
        in results
    }

    if len(
        row_prices
    ) != 1:
        raise ValueError(
            "Selected group spans "
            "multiple row prices"
        )

    row_price_ore = next(
        iter(
            row_prices
        )
    )

    signatures = [
        ticket_signature(
            result
        )
        for result
        in results
    ]

    row_counts = []

    banker_counts_per_ticket = []

    per_leg: dict[
        int,
        dict[str, Any],
    ] = {}

    for leg_number in range(
        1,
        8,
    ):
        selection_counts: Counter[
            int
        ] = Counter()

        banker_counts: Counter[
            int
        ] = Counter()

        depth_counts: Counter[
            int
        ] = Counter()

        for result in results:
            selection = next(
                row
                for row
                in result[
                    "selections"
                ]
                if int(
                    row[
                        "legNumber"
                    ]
                )
                == leg_number
            )

            marks = [
                int(mark)
                for mark
                in selection[
                    "marks"
                ]
            ]

            depth_counts[
                len(
                    marks
                )
            ] += 1

            for horse in marks:
                selection_counts[
                    horse
                ] += 1

            if len(
                marks
            ) == 1:
                banker_counts[
                    marks[0]
                ] += 1

        horses = []

        for horse in sorted(
            selection_counts,
            key=lambda number: (
                -selection_counts[
                    number
                ],
                -banker_counts[
                    number
                ],
                number,
            ),
        ):
            selected_count = (
                selection_counts[
                    horse
                ]
            )

            banker_count = (
                banker_counts[
                    horse
                ]
            )

            selection_frequency = (
                selected_count
                / sample_count
            )

            banker_frequency = (
                banker_count
                / sample_count
            )

            horses.append(
                {
                    "startNumber":
                        horse,
                    "selectedCount":
                        selected_count,
                    "selectionFrequency":
                        round(
                            selection_frequency,
                            6,
                        ),
                    "bankerCount":
                        banker_count,
                    "bankerFrequency":
                        round(
                            banker_frequency,
                            6,
                        ),
                    "descriptiveBand":
                        descriptive_band(
                            selection_frequency
                        ),
                    "alwaysSelected":
                        selected_count
                        == sample_count,
                }
            )

        banker_ticket_count = sum(
            banker_counts.values()
        )

        per_leg[
            leg_number
        ] = {
            "legNumber":
                leg_number,
            "bankerTicketCount":
                banker_ticket_count,
            "bankerRate":
                round(
                    banker_ticket_count
                    / sample_count,
                    6,
                ),
            "selectionDepthDistribution": {
                str(depth):
                    count
                for depth, count
                in sorted(
                    depth_counts.items()
                )
            },
            "alwaysSelected": [
                row[
                    "startNumber"
                ]
                for row
                in horses
                if row[
                    "alwaysSelected"
                ]
            ],
            "bankerCandidates": [
                {
                    "startNumber":
                        horse,
                    "bankerCount":
                        count,
                    "bankerFrequency":
                        round(
                            count
                            / sample_count,
                            6,
                        ),
                }
                for horse, count
                in sorted(
                    banker_counts.items(),
                    key=lambda row: (
                        -row[1],
                        row[0],
                    ),
                )
            ],
            "horses":
                horses,
        }

    for result in results:
        depths = [
            len(
                selection[
                    "marks"
                ]
            )
            for selection
            in result[
                "selections"
            ]
        ]

        row_counts.append(
            math.prod(
                depths
            )
        )

        banker_counts_per_ticket.append(
            sum(
                depth == 1
                for depth
                in depths
            )
        )

    actual_costs_nok = [
        (
            rows
            * row_price_ore
            / 100.0
        )
        for rows
        in row_counts
    ]

    requested_stake_ore = (
        int(
            bet_data["p"]
        )
        if bet_data.get(
            "p"
        )
        is not None
        else None
    )

    result = {
        "schemaVersion":
            "1.0",
        "analysisType":
            "stalltips-consensus",
        "source":
            {
                "capture":
                    capture_path.name,
                "manifestCaptureCount":
                    len(records),
                "validDraftCount":
                    sum(
                        len(rows)
                        for rows
                        in groups.values()
                    ),
                "rejectedDraftCount":
                    rejected,
                "groupCount":
                    len(groups),
            },
        "selectedGroup":
            {
                "exactBetData":
                    selected_bet_data,
                "sampleCount":
                    sample_count,
                "ignoredValidDraftCount":
                    (
                        sum(
                            len(rows)
                            for rows
                            in groups.values()
                        )
                        - sample_count
                    ),
                "parameters":
                    bet_data,
                "raceDayKey":
                    next(
                        iter(
                            race_day_keys
                        )
                    ),
                "raceDate":
                    bet_data.get(
                        "d"
                    ),
                "trackCode":
                    bet_data.get(
                        "t"
                    ),
                "product":
                    bet_data.get(
                        "g"
                    ),
                "requestedStakeOre":
                    requested_stake_ore,
                "requestedStakeNok":
                    (
                        requested_stake_ore
                        / 100.0
                        if requested_stake_ore
                        is not None
                        else None
                    ),
                "rowPriceOre":
                    row_price_ore,
                "rowPriceNok":
                    row_price_ore
                    / 100.0,
            },
        "ticketVariation":
            {
                "uniqueTicketCount":
                    len(
                        set(
                            signatures
                        )
                    ),
                "uniqueTicketRate":
                    round(
                        len(
                            set(
                                signatures
                            )
                        )
                        / sample_count,
                        6,
                    ),
                "rowCountDistribution": {
                    str(rows):
                        count
                    for rows, count
                    in sorted(
                        Counter(
                            row_counts
                        ).items()
                    )
                },
                "bankersPerTicketDistribution": {
                    str(count):
                        occurrences
                    for count, occurrences
                    in sorted(
                        Counter(
                            banker_counts_per_ticket
                        ).items()
                    )
                },
                "actualCostNok": {
                    "min":
                        min(
                            actual_costs_nok
                        ),
                    "max":
                        max(
                            actual_costs_nok
                        ),
                    "mean":
                        round(
                            statistics.mean(
                                actual_costs_nok
                            ),
                            2,
                        ),
                },
            },
        "legs": [
            per_leg[
                leg_number
            ]
            for leg_number
            in range(
                1,
                8,
            )
        ],
        "descriptiveBands":
            {
                "ALWAYS":
                    "selectionFrequency == 1.00",
                "FREQUENT":
                    "0.50 <= selectionFrequency < 1.00",
                "ROTATING":
                    "0.20 <= selectionFrequency < 0.50",
                "RARE":
                    "selectionFrequency < 0.20",
            },
        "guardrails":
            {
                "descriptiveOnly":
                    True,
                "outcomesUsed":
                    False,
                "marketUsed":
                    False,
                "coreModelUsed":
                    False,
                "hybridWeightingApplied":
                    False,
                "generatorFrequencyIsNotWinProbability":
                    True,
            },
    }

    return result


def print_summary(
    analysis: dict[str, Any],
) -> None:
    group = analysis[
        "selectedGroup"
    ]

    variation = analysis[
        "ticketVariation"
    ]

    print()
    print(
        "=== STALLTIPS CONSENSUS ==="
    )
    print(
        "Race day:",
        group[
            "raceDayKey"
        ],
    )
    print(
        "Samples:",
        group[
            "sampleCount"
        ],
    )
    print(
        "Generator stake:",
        f"{group['requestedStakeNok']:.2f} NOK",
    )
    print(
        "Unique tickets:",
        variation[
            "uniqueTicketCount"
        ],
    )
    print(
        "Row counts:",
        variation[
            "rowCountDistribution"
        ],
    )
    print(
        "Actual cost:",
        variation[
            "actualCostNok"
        ],
    )

    for leg in analysis[
        "legs"
    ]:
        always = ", ".join(
            f"#{number}"
            for number
            in leg[
                "alwaysSelected"
            ]
        ) or "-"

        bankers = ", ".join(
            (
                f"#{row['startNumber']} "
                f"{row['bankerCount']}/"
                f"{group['sampleCount']}"
            )
            for row
            in leg[
                "bankerCandidates"
            ]
        ) or "-"

        print()
        print(
            f"V75-{leg['legNumber']}"
        )
        print(
            f"  Always selected: {always}"
        )
        print(
            f"  Banker candidates: {bankers}"
        )

        for horse in leg[
            "horses"
        ]:
            print(
                "  "
                f"#{horse['startNumber']:<2} "
                f"{horse['selectedCount']:>2}/"
                f"{group['sampleCount']} "
                f"({horse['selectionFrequency'] * 100:5.1f}%) "
                f"{horse['descriptiveBand']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze repeated Rikstoto "
            "Stalltips draft generations "
            "as descriptive consensus data."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help=(
            "Capture directory or ZIP "
            "containing manifest.json "
            "and draft JSON files."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    analysis = analyze_capture(
        args.input
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            analysis,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print_summary(
        analysis
    )

    print()
    print(
        "Saved:",
        args.output,
    )


if __name__ == "__main__":
    main()
