from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def find_results_payload(
    probe: list[dict[str, Any]],
    race_day_key: str,
) -> dict[str, Any]:
    suffix = (
        f"/api/results/racedays/"
        f"{race_day_key}/raceresults"
    )

    matches = [
        item
        for item in probe
        if isinstance(item, dict)
        and item.get("status") == 200
        and str(item.get("url", "")).endswith(suffix)
        and isinstance(item.get("json"), dict)
    ]

    if not matches:
        raise ValueError(
            f"No race-results response found "
            f"for {race_day_key}"
        )

    payload = unwrap(matches[-1]["json"])

    if not isinstance(payload, dict):
        raise ValueError(
            "Unexpected race-results payload shape"
        )

    if payload.get("raceDay") != race_day_key:
        raise ValueError(
            "Race-results payload raceDay mismatch"
        )

    return payload


def index_by(
    items: list[dict[str, Any]],
    key: str,
) -> dict[Any, dict[str, Any]]:
    result: dict[Any, dict[str, Any]] = {}

    for item in items:
        value = item[key]

        if value in result:
            raise ValueError(
                f"Duplicate {key}={value!r}"
            )

        result[value] = item

    return result


def normalize_annual_statistics(
    raw: dict[str, Any] | None,
) -> dict[str, Any]:
    raw = raw or {}

    result: dict[str, Any] = {}

    for bucket in (
        "total",
        "currentYear",
        "previousYear",
    ):
        value = raw.get(bucket)

        if not isinstance(value, dict):
            result[bucket] = None
            continue

        result[bucket] = {
            "year": value.get("year"),
            "starts": value.get(
                "numberOfStarts"
            ),
            "wins": value.get(
                "numberOfFirstPlaces"
            ),
            "seconds": value.get(
                "numberOfSecondPlaces"
            ),
            "thirds": value.get(
                "numberOfThirdPlaces"
            ),
            "record": value.get("record"),
            "earnings": value.get(
                "totalEarnings"
            ),
        }

    return result


def normalize_history_row(
    row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "formRowKey": row.get("formRowKey"),
        "raceDate": row.get("raceDate"),
        "trackCode": row.get("trackCode"),
        "sportTrack": row.get("sportTrack"),
        "raceNumber": row.get("raceNumber"),
        "startNumber": row.get("startNumber"),
        "distance": row.get("distance"),
        "monte": row.get("monte"),
        "driver": (
            row.get("driverFullName")
            or row.get("driver")
        ),
        "postPositionRaw": row.get(
            "postposition"
        ),
        "placeRaw": row.get("place"),
        "timeRaw": row.get("time"),
        "winOddsRaw": row.get("winOdds"),
        "favorite": row.get("favorite"),
        "firstPrizeRaw": row.get(
            "firstPrize"
        ),
        "videoKey": row.get("videoKey"),
        "comment": row.get(
            "raceCommentExternal"
        ),
        "organizationCode": row.get(
            "organizationCode"
        ),
        "shoes": row.get("shoes"),
        "sulky": row.get("sulky"),
        "raceTop3": (
            row.get("raceResults") or []
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--snapshot-dir",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--results-probe",
        required=False,
        type=Path,
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    snapshot = args.snapshot_dir
    out = args.output_dir

    pool_doc = load_json(
        snapshot / "v75-pool.json"
    )

    race_day_key = pool_doc["raceDayKey"]
    race_day_name = pool_doc["raceDayName"]
    race_date = pool_doc["date"]
    pool = pool_doc["pool"]
    legs = pool_doc["legs"]

    if pool.get("product") != "V75":
        raise ValueError(
            "Expected V75 pool"
        )

    if len(legs) != 7:
        raise ValueError(
            f"Expected 7 V75 legs, "
            f"found {len(legs)}"
        )

    race_info = unwrap(
        load_json(
            snapshot / "race-info.json"
        )
    )

    starts_by_race = unwrap(
        load_json(
            snapshot / "starts.json"
        )
    )

    form_races = unwrap(
        load_json(
            snapshot
            / "form-rows-trot.json"
        )
    )

    has_results = (
        args.results_probe
        is not None
    )

    if has_results:
        results_probe = load_json(
            args.results_probe
        )

        results_payload = (
            find_results_payload(
                results_probe,
                race_day_key,
            )
        )
    else:
        results_payload = {}

    if not isinstance(race_info, list):
        raise ValueError(
            "Unexpected race-info shape"
        )

    if not isinstance(
        starts_by_race,
        dict,
    ):
        raise ValueError(
            "Unexpected starts shape"
        )

    if not isinstance(form_races, list):
        raise ValueError(
            "Unexpected form-history shape"
        )

    race_info_idx = index_by(
        race_info,
        "raceNumber",
    )

    form_race_idx = index_by(
        form_races,
        "raceNumber",
    )

    race_results = (
        results_payload.get(
            "raceResults"
        )
        or {}
    )

    race_winners = (
        results_payload.get(
            "raceWinners"
        )
        or {}
    )

    winner_ranks = (
        results_payload.get(
            "vGameWinnerRanks"
        )
        or {}
    )

    pre_race_legs: list[
        dict[str, Any]
    ] = []

    outcomes: list[
        dict[str, Any]
    ] = []

    total_entries = 0
    total_scratched = 0
    total_history_rows = 0

    latest_history_date: (
        str | None
    ) = None

    for leg in legs:
        leg_no = int(leg["leg"])

        race_number = int(
            leg["raceNumber"]
        )

        race_key = leg["raceKey"]

        program_doc = unwrap(
            load_json(
                snapshot
                / "program"
                / f"v75-{leg_no}.json"
            )
        )

        if (
            not isinstance(
                program_doc,
                list,
            )
            or len(program_doc) != 1
        ):
            raise ValueError(
                f"Unexpected program shape "
                f"for V75-{leg_no}"
            )

        program = program_doc[0]

        if (
            program.get("raceNumber")
            != race_number
            or program.get("raceKey")
            != race_key
        ):
            raise ValueError(
                f"Program identity mismatch "
                f"for V75-{leg_no}"
            )

        info = race_info_idx[
            race_number
        ]

        for field in (
            "distance",
            "startMethod",
        ):
            if (
                program.get(field)
                != info.get(field)
            ):
                raise ValueError(
                    f"{field} mismatch "
                    f"for V75-{leg_no}"
                )

        starts = starts_by_race.get(
            str(race_number)
        )

        if not isinstance(
            starts,
            list,
        ):
            raise ValueError(
                f"Missing starts for "
                f"race {race_number}"
            )

        start_idx = index_by(
            starts,
            "startNumber",
        )

        form_race = form_race_idx[
            race_number
        ]

        form_groups = (
            form_race.get(
                "formRowsForStarts"
            )
            or []
        )

        if not isinstance(
            form_groups,
            list,
        ):
            raise ValueError(
                f"Unexpected form rows "
                f"for race {race_number}"
            )

        form_idx = index_by(
            form_groups,
            "startNumber",
        )

        entries: list[
            dict[str, Any]
        ] = []

        for program_start in (
            program.get("starts")
            or []
        ):
            number = int(
                program_start[
                    "startNumber"
                ]
            )

            total_entries += 1

            start = start_idx.get(
                number
            )

            if start is None:
                raise ValueError(
                    f"No /starts match "
                    f"for V75-{leg_no} "
                    f"#{number}"
                )

            if (
                program_start.get(
                    "horseRegistrationNumber"
                )
                != start.get(
                    "horseRegistrationNumber"
                )
            ):
                raise ValueError(
                    f"Horse registration "
                    f"mismatch for "
                    f"V75-{leg_no} "
                    f"#{number}"
                )

            form_group = form_idx.get(
                number
            )

            if form_group is None:
                raise ValueError(
                    f"No form-history match "
                    f"for V75-{leg_no} "
                    f"#{number}"
                )

            history_raw = (
                form_group.get(
                    "formRows"
                )
                or []
            )

            if not isinstance(
                history_raw,
                list,
            ):
                raise ValueError(
                    f"Unexpected history "
                    f"for V75-{leg_no} "
                    f"#{number}"
                )

            history_raw = sorted(
                history_raw,
                key=lambda row: parse_dt(
                    row["raceDate"]
                ),
            )

            for row in history_raw:
                history_date = (
                    parse_dt(
                        row["raceDate"]
                    )
                    .date()
                    .isoformat()
                )

                if (
                    history_date
                    >= race_date
                ):
                    raise ValueError(
                        "DATA LEAKAGE: "
                        f"V75-{leg_no} "
                        f"#{number} has "
                        f"history row "
                        f"{row['raceDate']} "
                        f"on/after "
                        f"{race_date}"
                    )

                if (
                    latest_history_date
                    is None
                    or row["raceDate"]
                    > latest_history_date
                ):
                    latest_history_date = (
                        row["raceDate"]
                    )

            total_history_rows += len(
                history_raw
            )

            scratched = bool(
                start.get(
                    "isScratched"
                )
            )

            total_scratched += int(
                scratched
            )

            entries.append(
                {
                    "startNumber": number,
                    "horse": {
                        "registrationNumber":
                            program_start.get(
                                "horseRegistrationNumber"
                            ),
                        "name":
                            program_start.get(
                                "horseName"
                            ),
                        "age":
                            program_start.get(
                                "age"
                            ),
                        "sex":
                            program_start.get(
                                "sex"
                            ),
                        "color":
                            program_start.get(
                                "color"
                            ),
                        "father":
                            program_start.get(
                                "father"
                            ),
                        "mother":
                            program_start.get(
                                "mother"
                            ),
                        "grandfather":
                            program_start.get(
                                "grandfather"
                            ),
                        "trainer":
                            program_start.get(
                                "trainer"
                            ),
                        "owner":
                            program_start.get(
                                "owner"
                            ),
                        "breeder":
                            program_start.get(
                                "breeder"
                            ),
                    },
                    "driver": {
                        "id":
                            program_start.get(
                                "driverId"
                            ),
                        "name":
                            program_start.get(
                                "driver"
                            ),
                    },
                    "start": {
                        "postPosition":
                            program_start.get(
                                "postPosition"
                            ),
                        "extraDistance":
                            program_start.get(
                                "extraDistance"
                            ),
                        "scratched":
                            scratched,
                        "eligibleForPrediction":
                            not scratched,
                    },
                    "career": {
                        "programTotalEarningsRaw":
                            program_start.get(
                                "totalEarnings"
                            ),
                        "recordVoltRaw":
                            program_start.get(
                                "recordVolt"
                            ),
                        "recordAutoRaw":
                            program_start.get(
                                "recordAuto"
                            ),
                        "winPercentage":
                            program_start.get(
                                "winPercentage"
                            ),
                        "triplePercentage":
                            program_start.get(
                                "triplePercentage"
                            ),
                        "gallopPercentage":
                            program_start.get(
                                "gallopPercentage"
                            ),
                    },
                    "annualStatistics":
                        normalize_annual_statistics(
                            program_start.get(
                                "horseAnnualStatistics"
                            )
                        ),
                    "equipment": {
                        "shoes":
                            program_start.get(
                                "shoes"
                            ),
                        "previousStartShoes":
                            program_start.get(
                                "previousStartShoes"
                            ),
                        "sulky":
                            program_start.get(
                                "sulky"
                            ),
                        "previousStartSulky":
                            program_start.get(
                                "previousStartSulky"
                            ),
                    },
                    "previewComment":
                        program_start.get(
                            "previewComment"
                        ),
                    "history": [
                        normalize_history_row(
                            row
                        )
                        for row
                        in history_raw
                    ],
                }
            )

        pre_race_legs.append(
            {
                "leg": leg_no,
                "raceKey": race_key,
                "raceNumber":
                    race_number,
                "race": {
                    "name":
                        program.get(
                            "raceName"
                        ),
                    "distance":
                        program.get(
                            "distance"
                        ),
                    "startMethod":
                        program.get(
                            "startMethod"
                        ),
                    "propositions":
                        program.get(
                            "propositions"
                        ),
                    "raceForm":
                        program.get(
                            "raceForm"
                        ),
                    "isMonte":
                        program.get(
                            "isMonte"
                        ),
                    "sportType":
                        info.get(
                            "sportType"
                        ),
                    "trackSurfaceType":
                        info.get(
                            "trackSurfaceType"
                        ),
                    "gallopType":
                        info.get(
                            "gallopType"
                        ),
                },
                "entries": entries,
            }
        )

        if not has_results:
            continue

        result_rows = (
            race_results.get(
                str(race_number)
            )
            or []
        )

        winner_rows = (
            race_winners.get(
                str(race_number)
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
            raise ValueError(
                f"Expected one winner "
                f"for race {race_number}"
            )

        winner_number = int(
            winner_rows[0][
                "startNumber"
            ]
        )

        winner_entry = next(
            (
                entry
                for entry in entries
                if entry[
                    "startNumber"
                ]
                == winner_number
            ),
            None,
        )

        if winner_entry is None:
            raise ValueError(
                f"Winner #{winner_number} "
                f"missing from V75-{leg_no}"
            )

        if winner_entry[
            "start"
        ]["scratched"]:
            raise ValueError(
                f"Winner #{winner_number} "
                f"is marked scratched "
                f"in V75-{leg_no}"
            )

        market_rank = None

        rank_rows = (
            winner_ranks.get(
                str(race_number)
            )
            or []
        )

        if (
            rank_rows
            and isinstance(
                rank_rows[0],
                dict,
            )
        ):
            rank = (
                rank_rows[0].get(
                    "rank"
                )
                or {}
            )

            market_rank = rank.get(
                "V75"
            )

        outcomes.append(
            {
                "leg": leg_no,
                "raceKey": race_key,
                "raceNumber":
                    race_number,
                "winnerStartNumber":
                    winner_number,
                "top3": result_rows,
                "winnerV75MarketRank":
                    market_rank,
            }
        )

    pre_race = {
        "schemaVersion": "1.0",
        "datasetType":
            "v75-pre-race",
        "raceDate": race_date,
        "raceDayKey":
            race_day_key,
        "raceDayName":
            race_day_name,
        "pool": {
            "product": "V75",
            "poolKey":
                pool.get("poolKey"),
            "startTime":
                pool.get("startTime"),
            "isMultiTrack":
                pool.get(
                    "isMultiTrack"
                ),
        },
        "legs": pre_race_legs,
    }

    outcome_doc = {
        "schemaVersion": "1.0",
        "datasetType":
            "v75-outcomes",
        "raceDate": race_date,
        "raceDayKey":
            race_day_key,
        "raceDayName":
            race_day_name,
        "legs": outcomes,
    }

    manifest = {
        "schemaVersion": "1.0",
        "raceDate": race_date,
        "raceDayKey":
            race_day_key,
        "raceDayName":
            race_day_name,
        "counts": {
            "legs":
                len(pre_race_legs),
            "programEntries":
                total_entries,
            "scratchedEntries":
                total_scratched,
            "eligibleEntries":
                total_entries
                - total_scratched,
            "historyRows":
                total_history_rows,
        },
        "latestHistoryDate":
            latest_history_date,
        "winnerStartNumbers": [
            outcome[
                "winnerStartNumber"
            ]
            for outcome
            in outcomes
        ],
        "files": {
            "preRace":
                "pre-race.json",
            "outcomes":
                "outcomes.json",
        },
        "guardrails": {
            "outcomesSeparatedFromPreRace":
                True,
            "allHistoryStrictlyBeforeRaceDate":
                True,
            "scratchedEntriesRetainedButIneligible":
                True,
        },
    }

    if not has_results:
        manifest.pop(
            "winnerStartNumbers",
            None,
        )

        manifest["files"].pop(
            "outcomes",
            None,
        )

        manifest["mode"] = (
            "pre-race"
        )

        manifest[
            "guardrails"
        ][
            "resultsAvailable"
        ] = False

    save_json(
        out / "pre-race.json",
        pre_race,
    )

    if has_results:
        save_json(
            out / "outcomes.json",
            outcome_doc,
        )

    save_json(
        out / "manifest.json",
        manifest,
    )

    print(
        "=== V75 NORMALIZATION "
        "COMPLETE ==="
    )

    print(
        f"Race day:          "
        f"{race_day_name} "
        f"{race_date} "
        f"({race_day_key})"
    )

    print(
        f"V75 legs:          "
        f"{len(pre_race_legs)}"
    )

    print(
        f"Program entries:   "
        f"{total_entries}"
    )

    print(
        f"Scratched:         "
        f"{total_scratched}"
    )

    print(
        f"Eligible starters: "
        f"{total_entries - total_scratched}"
    )

    print(
        f"History rows:      "
        f"{total_history_rows}"
    )

    print(
        f"Latest history:    "
        f"{latest_history_date}"
    )

    print(
        "Winners:           "
        + ", ".join(
            str(
                outcome[
                    "winnerStartNumber"
                ]
            )
            for outcome
            in outcomes
        )
    )

    print(
        f"Output:            "
        f"{out}"
    )


if __name__ == "__main__":
    main()
