from v75.track_identity import (
    TRACK_IDENTITY_VERSION,
    history_track_code_for_race_day_key,
    race_day_prefix,
)


EXPECTED = {
    "BJ_NR_2026-06-13": "B",
    "OR_NR_2026-06-20": "OA",
    "FO_NR_2026-06-27": "F",
    "JA_NR_2026-07-04": "J",
    "HA_NR_2026-07-11": "HA",
    "ST_NR_2026-07-18": "ST",
    "BI_NR_2026-07-25": "BI",
    "MO_NR_2026-08-01": "M",
    "BT_NR_2026-08-08": "BT",
    "KL_NR_2026-08-29": "K",
}


assert (
    TRACK_IDENTITY_VERSION
    == "1.0"
)


for race_day_key, expected in (
    EXPECTED.items()
):
    actual = (
        history_track_code_for_race_day_key(
            race_day_key
        )
    )

    assert actual == expected, (
        race_day_key,
        expected,
        actual,
    )


assert (
    race_day_prefix(
        "BJ_NR_2026-06-13"
    )
    == "BJ"
)


try:
    history_track_code_for_race_day_key(
        "ZZ_NR_2026-01-01"
    )
except KeyError:
    pass
else:
    raise AssertionError(
        "Unknown track prefix must fail closed."
    )


print(
    "PASS: verified race-day prefixes "
    "map deterministically to historical "
    "trackCode values."
)
