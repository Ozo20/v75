from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


BASE = "https://www.rikstoto.no"


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
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


def get_json(request, path: str) -> Any:
    response = request.get(
        path,
        headers={
            "Accept": "application/json",
            "Referer": f"{BASE}/",
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

    payload = response.json()

    # Be deliberately gentle with
    # the public service.
    time.sleep(0.20)

    return payload


def find_meeting(
    discovery: dict[str, Any],
    race_day_key: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in discovery.get(
            "meetings",
            [],
        )
        if item.get("raceDayKey")
        == race_day_key
    ]

    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one "
            f"discovery match for "
            f"{race_day_key}, "
            f"found {len(matches)}"
        )

    meeting = matches[0]

    if meeting.get("singleTrack") is not True:
        raise ValueError(
            f"{race_day_key} is not "
            f"a single-track V75"
        )

    if meeting.get("legCount") != 7:
        raise ValueError(
            f"{race_day_key} does not "
            f"contain 7 V75 legs"
        )

    if meeting.get("countryIsoCode") != "NO":
        raise ValueError(
            f"{race_day_key} is not "
            f"Norwegian"
        )

    return meeting


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--discovery",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--race-day-key",
        required=True,
    )

    parser.add_argument(
        "--output-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--pre-race-only",
        action="store_true",
        help=(
            "Collect only information available "
            "before the V75 races. The results "
            "endpoint is not called."
        ),
    )

    args = parser.parse_args()

    discovery = load_json(
        args.discovery
    )

    meeting = find_meeting(
        discovery,
        args.race_day_key,
    )

    race_day_key = meeting[
        "raceDayKey"
    ]

    race_day_name = meeting[
        "raceDayName"
    ]

    race_date = meeting["date"]

    meeting_date = date.fromisoformat(
        race_date
    )

    race_keys = meeting[
        "raceKeys"
    ]

    race_numbers = meeting[
        "raceNumbers"
    ]

    if len(race_keys) != 7:
        raise ValueError(
            "Expected seven race keys"
        )

    output = (
        args.output_root
        / race_date
    )

    if output.exists():
        raise SystemExit(
            f"REFUSING: output already "
            f"exists: {output}"
        )

    output.mkdir(
        parents=True,
        exist_ok=False,
    )

    legs = [
        {
            "leg": index,
            "raceKey": race_key,
            "raceNumber": race_number,
        }
        for index, (
            race_key,
            race_number,
        )
        in enumerate(
            zip(
                race_keys,
                race_numbers,
                strict=True,
            ),
            1,
        )
    ]

    pool = {
        "product": "V75",
        "poolKey":
            meeting.get("poolKey"),
        "isMultiTrack":
            meeting.get(
                "isMultiTrack"
            ),
        "races": race_keys,
    }

    save_json(
        output / "v75-pool.json",
        {
            "date": race_date,
            "raceDayKey":
                race_day_key,
            "raceDayName":
                race_day_name,
            "pool": pool,
            "legs": legs,
        },
    )

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

        print(
            "\n=== COLLECT "
            f"{race_day_name} "
            f"{race_date} ==="
        )

        race_info_raw = get_json(
            request,
            f"/api/racedays/"
            f"{race_day_key}/raceInfo",
        )

        save_json(
            output / "race-info.json",
            race_info_raw,
        )

        starts_raw = get_json(
            request,
            f"/api/racedays/"
            f"{race_day_key}/starts",
        )

        save_json(
            output / "starts.json",
            starts_raw,
        )

        form_raw = get_json(
            request,
            f"/api/game/program/"
            f"{race_day_key}/"
            f"formrowstrot",
        )

        save_json(
            output
            / "form-rows-trot.json",
            form_raw,
        )

        program_dir = (
            output / "program"
        )

        program_dir.mkdir()

        program_docs = {}

        for leg in legs:
            leg_no = leg["leg"]
            race_number = (
                leg["raceNumber"]
            )

            program_raw = get_json(
                request,
                f"/api/game/program/"
                f"{race_day_key}/V/"
                f"trot/{race_number}",
            )

            save_json(
                program_dir
                / f"v75-{leg_no}.json",
                program_raw,
            )

            program_docs[
                race_number
            ] = unwrap(
                program_raw
            )

        results_raw = None

        if not args.pre_race_only:
            results_path = (
                f"/api/results/racedays/"
                f"{race_day_key}/"
                f"raceresults"
            )

            results_raw = get_json(
                request,
                results_path,
            )

            # Keep compatibility with the
            # historical normalizer path,
            # which reads the original
            # results-probe shape.
            save_json(
                output
                / "results-probe.json",
                [
                    {
                        "status": 200,
                        "method": "GET",
                        "url":
                            BASE
                            + results_path,
                        "content_type":
                            "application/json; "
                            "charset=utf-8",
                        "json":
                            results_raw,
                    }
                ],
            )

        request.dispose()

    print(
        "\n=== VALIDATE SNAPSHOT ==="
    )

    starts = unwrap(starts_raw)
    forms = unwrap(form_raw)

    results = (
        None
        if args.pre_race_only
        else unwrap(results_raw)
    )

    if not isinstance(starts, dict):
        raise ValueError(
            "Unexpected starts shape"
        )

    if not isinstance(forms, list):
        raise ValueError(
            "Unexpected form-history shape"
        )

    if (
        not args.pre_race_only
        and not isinstance(
            results,
            dict,
        )
    ):
        raise ValueError(
            "Unexpected results shape"
        )

    form_by_race = {
        int(item["raceNumber"]):
            item
        for item in forms
    }

    program_entries = 0
    scratched_entries = 0
    eligible_entries = 0
    history_rows = 0
    latest_history_date = None

    for leg in legs:
        race_number = leg[
            "raceNumber"
        ]

        docs = program_docs[
            race_number
        ]

        if (
            not isinstance(docs, list)
            or len(docs) != 1
        ):
            raise ValueError(
                f"Unexpected program "
                f"shape for race "
                f"{race_number}"
            )

        program = docs[0]

        entries = (
            program.get("starts")
            or []
        )

        program_entries += len(
            entries
        )

        race_starts = (
            starts.get(
                str(race_number)
            )
            or []
        )

        scratch_by_number = {
            int(item["startNumber"]):
                bool(
                    item.get(
                        "isScratched"
                    )
                )
            for item in race_starts
        }

        if (
            len(scratch_by_number)
            != len(entries)
        ):
            raise ValueError(
                f"Program / starts "
                f"count mismatch in "
                f"race {race_number}"
            )

        for entry in entries:
            number = int(
                entry["startNumber"]
            )

            if number not in (
                scratch_by_number
            ):
                raise ValueError(
                    f"Missing start "
                    f"#{number} in "
                    f"race {race_number}"
                )

            if scratch_by_number[
                number
            ]:
                scratched_entries += 1
            else:
                eligible_entries += 1

        form_race = form_by_race.get(
            race_number
        )

        if form_race is None:
            raise ValueError(
                f"Missing form history "
                f"for race "
                f"{race_number}"
            )

        groups = (
            form_race.get(
                "formRowsForStarts"
            )
            or []
        )

        if len(groups) != len(entries):
            raise ValueError(
                f"Program / form "
                f"count mismatch in "
                f"race {race_number}"
            )

        for group in groups:
            rows = (
                group.get("formRows")
                or []
            )

            history_rows += len(rows)

            for row in rows:
                dt = str(
                    row["raceDate"]
                )

                row_date = (
                    date.fromisoformat(
                        dt[:10]
                    )
                )

                if row_date >= meeting_date:
                    raise ValueError(
                        "DATA LEAKAGE: "
                        f"{race_day_key} "
                        f"contains form row "
                        f"{dt}"
                    )

                if (
                    latest_history_date
                    is None
                    or dt
                    > latest_history_date
                ):
                    latest_history_date = (
                        dt
                    )

    winners = []

    if not args.pre_race_only:
        assert isinstance(
            results,
            dict,
        )

        race_winners = (
            results.get(
                "raceWinners"
            )
            or {}
        )

        for leg in legs:
            race_number = leg[
                "raceNumber"
            ]

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
                    f"for race "
                    f"{race_number}"
                )

            winners.append(
                int(
                    winner_rows[0][
                        "startNumber"
                    ]
                )
            )

    manifest = {
        "schemaVersion": "1.0",
        "raceDate": race_date,
        "raceDayKey":
            race_day_key,
        "raceDayName":
            race_day_name,
        "counts": {
            "legs": 7,
            "programEntries":
                program_entries,
            "scratchedEntries":
                scratched_entries,
            "eligibleEntries":
                eligible_entries,
            "historyRows":
                history_rows,
        },
        "latestHistoryDate":
            latest_history_date,
        "winnerStartNumbers":
            winners,
        "guardrails": {
            "singleTrackV75":
                True,
            "allHistoryStrictlyBeforeRaceDate":
                True,
            "resultsStoredSeparately":
                True,
        },
    }

    if args.pre_race_only:
        manifest.pop(
            "winnerStartNumbers",
            None,
        )

        manifest["mode"] = (
            "pre-race"
        )

        manifest[
            "guardrails"
        ].pop(
            "resultsStoredSeparately",
            None,
        )

        manifest[
            "guardrails"
        ][
            "resultsFetched"
        ] = False

    save_json(
        output / "manifest.json",
        manifest,
    )

    print(
        f"Race day:          "
        f"{race_day_name} "
        f"{race_date}"
    )

    print(
        f"Race day key:      "
        f"{race_day_key}"
    )

    print(
        f"V75 legs:          7"
    )

    print(
        f"Program entries:   "
        f"{program_entries}"
    )

    print(
        f"Scratched:         "
        f"{scratched_entries}"
    )

    print(
        f"Eligible starters: "
        f"{eligible_entries}"
    )

    print(
        f"History rows:      "
        f"{history_rows}"
    )

    print(
        f"Latest history:    "
        f"{latest_history_date}"
    )

    if args.pre_race_only:
        print(
            "Results:           "
            "NOT FETCHED "
            "(pre-race-only)"
        )
    else:
        print(
            "Winners:           "
            + ", ".join(
                str(value)
                for value in winners
            )
        )

    print(
        f"Saved:             "
        f"{output}"
    )


if __name__ == "__main__":
    main()
