from __future__ import annotations

import argparse
import copy
import json
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


BASE = "https://www.rikstoto.no"


def load_json(path: Path) -> Any:
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


def unwrap(payload: Any) -> Any:
    if (
        isinstance(payload, dict)
        and payload.get("success") is True
        and "result" in payload
    ):
        return payload["result"]

    return payload


def get_json(
    request,
    path: str,
) -> Any:
    response = request.get(
        path,
        headers={
            "Accept":
                "application/json",
            "Referer":
                f"{BASE}/",
        },
    )

    print(
        f"{response.status:3}  {path}"
    )

    if not response.ok:
        raise RuntimeError(
            f"GET failed: "
            f"{response.status} {path}"
        )

    payload = unwrap(
        response.json()
    )

    time.sleep(0.20)

    return payload


def unique_race(
    rows: list[dict[str, Any]],
    race_number: int,
    label: str,
) -> dict[str, Any]:
    matches = [
        row
        for row
        in rows
        if int(
            row["raceNumber"]
        )
        == race_number
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one {label} row "
            f"for race {race_number}, "
            f"found {len(matches)}"
        )

    return copy.deepcopy(
        matches[0]
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--discovery",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--date",
        required=True,
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    if args.output_dir.exists():
        raise SystemExit(
            "REFUSING: output already exists: "
            f"{args.output_dir}"
        )

    discovery = load_json(
        args.discovery
    )

    matches = [
        row
        for row
        in discovery.get(
            "meetings",
            [],
        )
        if (
            row.get("date")
            == args.date
            and row.get(
                "isMultiTrack"
            )
            is True
            and row.get(
                "countryIsoCode"
            )
            == "NO"
            and int(
                row.get(
                    "legCount",
                    0,
                )
            )
            == 7
        )
    ]

    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one "
            "Norwegian 7-leg multi-track "
            f"V75 on {args.date}; "
            f"found {len(matches)}."
        )

    meeting = matches[0]

    source_race_keys = (
        meeting["raceKeys"]
    )

    if len(
        source_race_keys
    ) != 7:
        raise RuntimeError(
            "Expected seven source race keys."
        )

    source_legs = []

    for leg_no, race_key in enumerate(
        source_race_keys,
        1,
    ):
        race_day_key, race_number = (
            str(race_key).rsplit(
                "#",
                1,
            )
        )

        source_legs.append(
            {
                "leg":
                    leg_no,
                "raceKey":
                    race_key,
                "raceDayKey":
                    race_day_key,
                "raceNumber":
                    int(
                        race_number
                    ),
            }
        )

    race_day_keys = sorted(
        {
            row["raceDayKey"]
            for row
            in source_legs
        }
    )

    if len(
        race_day_keys
    ) < 2:
        raise RuntimeError(
            "Expected a genuine "
            "multi-race-day pool."
        )

    synthetic_key = (
        "MULTI_NR_"
        + args.date
    )

    synthetic_legs = [
        {
            "leg":
                leg_no,
            "raceKey":
                (
                    f"{synthetic_key}"
                    f"#{leg_no}"
                ),
            "raceNumber":
                leg_no,
        }
        for leg_no
        in range(
            1,
            8,
        )
    ]

    component: dict[
        str,
        dict[str, Any],
    ] = {}

    programs: dict[
        int,
        list[dict[str, Any]],
    ] = {}

    with sync_playwright() as p:
        request = p.request.new_context(
            base_url=BASE,
            extra_http_headers={
                "Accept-Language":
                    "nb-NO,nb;q=0.9",
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/140.0.0.0 Safari/537.36"
                ),
            },
        )

        for race_day_key in (
            race_day_keys
        ):
            print()
            print(
                "=== FETCH COMPONENT ==="
            )
            print(
                race_day_key
            )

            race_info = get_json(
                request,
                (
                    f"/api/racedays/"
                    f"{race_day_key}/"
                    f"raceInfo"
                ),
            )

            starts = get_json(
                request,
                (
                    f"/api/racedays/"
                    f"{race_day_key}/"
                    f"starts"
                ),
            )

            forms = get_json(
                request,
                (
                    f"/api/game/program/"
                    f"{race_day_key}/"
                    f"formrowstrot"
                ),
            )

            results = get_json(
                request,
                (
                    f"/api/results/"
                    f"racedays/"
                    f"{race_day_key}/"
                    f"raceresults"
                ),
            )

            if not isinstance(
                race_info,
                list,
            ):
                raise RuntimeError(
                    "Unexpected raceInfo "
                    f"for {race_day_key}"
                )

            if not isinstance(
                starts,
                dict,
            ):
                raise RuntimeError(
                    "Unexpected starts "
                    f"for {race_day_key}"
                )

            if not isinstance(
                forms,
                list,
            ):
                raise RuntimeError(
                    "Unexpected forms "
                    f"for {race_day_key}"
                )

            if not isinstance(
                results,
                dict,
            ):
                raise RuntimeError(
                    "Unexpected results "
                    f"for {race_day_key}"
                )

            component[
                race_day_key
            ] = {
                "raceInfo":
                    race_info,
                "starts":
                    starts,
                "forms":
                    forms,
                "results":
                    results,
            }

        for source_leg in (
            source_legs
        ):
            race_day_key = (
                source_leg[
                    "raceDayKey"
                ]
            )

            race_number = (
                source_leg[
                    "raceNumber"
                ]
            )

            path = (
                f"/api/game/program/"
                f"{race_day_key}/V/"
                f"trot/{race_number}"
            )

            program = get_json(
                request,
                path,
            )

            if (
                not isinstance(
                    program,
                    list,
                )
                or len(program) != 1
            ):
                raise RuntimeError(
                    "Unexpected program "
                    f"for V75-"
                    f"{source_leg['leg']}"
                )

            row = program[0]

            if (
                row.get("raceKey")
                != source_leg[
                    "raceKey"
                ]
            ):
                raise RuntimeError(
                    "Program identity mismatch "
                    f"for V75-"
                    f"{source_leg['leg']}"
                )

            programs[
                source_leg["leg"]
            ] = copy.deepcopy(
                program
            )

        request.dispose()

    synthetic_race_info = []
    synthetic_starts = {}
    synthetic_forms = []

    synthetic_race_results = {}
    synthetic_race_winners = {}
    synthetic_winner_ranks = {}

    source_map = []

    program_dir = (
        args.output_dir
        / "program"
    )

    program_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    for source_leg in (
        source_legs
    ):
        leg_no = int(
            source_leg["leg"]
        )

        race_day_key = (
            source_leg[
                "raceDayKey"
            ]
        )

        source_number = int(
            source_leg[
                "raceNumber"
            ]
        )

        source = component[
            race_day_key
        ]

        info = unique_race(
            source["raceInfo"],
            source_number,
            "raceInfo",
        )

        info[
            "raceNumber"
        ] = leg_no

        synthetic_race_info.append(
            info
        )

        starts = copy.deepcopy(
            source[
                "starts"
            ].get(
                str(
                    source_number
                )
            )
        )

        if not isinstance(
            starts,
            list,
        ):
            raise RuntimeError(
                "Missing starts for "
                f"{source_leg['raceKey']}"
            )

        synthetic_starts[
            str(leg_no)
        ] = starts

        form = unique_race(
            source["forms"],
            source_number,
            "form",
        )

        form[
            "raceNumber"
        ] = leg_no

        synthetic_forms.append(
            form
        )

        result_doc = (
            source["results"]
        )

        race_results = (
            result_doc.get(
                "raceResults"
            )
            or {}
        )

        race_winners = (
            result_doc.get(
                "raceWinners"
            )
            or {}
        )

        winner_ranks = (
            result_doc.get(
                "vGameWinnerRanks"
            )
            or {}
        )

        result_rows = copy.deepcopy(
            race_results.get(
                str(
                    source_number
                )
            )
            or []
        )

        winner_rows = copy.deepcopy(
            race_winners.get(
                str(
                    source_number
                )
            )
            or []
        )

        if (
            len(winner_rows) != 1
            or winner_rows[0].get(
                "place"
            )
            != 1
        ):
            raise RuntimeError(
                "Expected one historical "
                "winner for "
                f"{source_leg['raceKey']}"
            )

        synthetic_race_results[
            str(leg_no)
        ] = result_rows

        synthetic_race_winners[
            str(leg_no)
        ] = winner_rows

        synthetic_winner_ranks[
            str(leg_no)
        ] = copy.deepcopy(
            winner_ranks.get(
                str(
                    source_number
                )
            )
            or []
        )

        program = copy.deepcopy(
            programs[
                leg_no
            ]
        )

        program_row = (
            program[0]
        )

        program_row[
            "raceNumber"
        ] = leg_no

        program_row[
            "raceKey"
        ] = (
            f"{synthetic_key}"
            f"#{leg_no}"
        )

        save_json(
            program_dir
            / f"v75-{leg_no}.json",
            program,
        )

        source_map.append(
            {
                "leg":
                    leg_no,
                "syntheticRaceKey":
                    (
                        f"{synthetic_key}"
                        f"#{leg_no}"
                    ),
                "sourceRaceKey":
                    source_leg[
                        "raceKey"
                    ],
                "sourceRaceDayKey":
                    race_day_key,
                "sourceRaceNumber":
                    source_number,
            }
        )

    pool_doc = {
        "date":
            args.date,
        "raceDayKey":
            synthetic_key,
        "raceDayName":
            meeting.get(
                "raceDayName"
            ),
        "pool": {
            "product":
                "V75",
            "poolKey":
                meeting.get(
                    "poolKey"
                ),
            "isMultiTrack":
                True,
            "races": [
                row["raceKey"]
                for row
                in synthetic_legs
            ],
        },
        "legs":
            synthetic_legs,
    }

    synthetic_results = {
        "raceDay":
            synthetic_key,
        "raceResults":
            synthetic_race_results,
        "raceWinners":
            synthetic_race_winners,
        "vGameWinnerRanks":
            synthetic_winner_ranks,
    }

    save_json(
        args.output_dir
        / "v75-pool.json",
        pool_doc,
    )

    save_json(
        args.output_dir
        / "race-info.json",
        synthetic_race_info,
    )

    save_json(
        args.output_dir
        / "starts.json",
        synthetic_starts,
    )

    save_json(
        args.output_dir
        / "form-rows-trot.json",
        synthetic_forms,
    )

    save_json(
        args.output_dir
        / "results-probe.json",
        [
            {
                "status":
                    200,
                "method":
                    "GET",
                "url":
                    (
                        f"{BASE}/api/"
                        f"results/racedays/"
                        f"{synthetic_key}/"
                        f"raceresults"
                    ),
                "content_type":
                    (
                        "application/json; "
                        "charset=utf-8"
                    ),
                "json":
                    synthetic_results,
            }
        ],
    )

    save_json(
        args.output_dir
        / "source-map.json",
        {
            "schemaVersion":
                "1.0",
            "adapter":
                "multitrack-fixture-v1",
            "date":
                args.date,
            "poolKey":
                meeting.get(
                    "poolKey"
                ),
            "syntheticRaceDayKey":
                synthetic_key,
            "sourceRaceDayKeys":
                race_day_keys,
            "legs":
                source_map,
            "guardrails": {
                "horseDataRewritten":
                    False,
                "formDataRewritten":
                    False,
                "sourceRaceIdentityRemappedOnly":
                    True,
                "outcomesRetainedSeparatelyByNormalizer":
                    True,
            },
        },
    )

    print()
    print(
        "=== MULTI-TRACK FIXTURE COMPLETE ==="
    )

    print(
        "Source pool:",
        meeting.get(
            "poolKey"
        ),
    )

    print(
        "Component race days:",
        ", ".join(
            race_day_keys
        ),
    )

    for row in source_map:
        print(
            f"V75-{row['leg']}: "
            f"{row['sourceRaceKey']} "
            f"-> "
            f"{row['syntheticRaceKey']}"
        )

    print(
        "Saved:",
        args.output_dir,
    )


if __name__ == "__main__":
    main()
