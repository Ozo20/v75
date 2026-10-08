from __future__ import annotations


TRACK_IDENTITY_VERSION = "1.0"


# Rikstoto uses two track-code namespaces:
#
# 1. Current race-day keys:
#       BJ_NR_...
#       OR_NR_...
#
# 2. Historical form-row trackCode:
#       B
#       OA
#
# Keep the translation explicit rather than
# inferring it from strings.
#
# Scope below covers the development tracks
# plus Klosterskogen, which occurs in the
# already-defined validation set.
RACE_DAY_PREFIX_TO_HISTORY_TRACK_CODE = {
    "BJ": "B",   # Bjerke
    "OR": "OA",  # Varig Orkla
    "FO": "F",   # Forus
    "JA": "J",   # Jarlsberg
    "HA": "HA",  # Harstad
    "ST": "ST",  # Sørlandet
    "BI": "BI",  # Biri
    "MO": "M",   # Momarken
    "BT": "BT",  # Bergen
    "KL": "K",   # Klosterskogen
}


def race_day_prefix(
    race_day_key: str,
) -> str:
    marker = "_NR_"

    if marker not in race_day_key:
        raise ValueError(
            "Unsupported raceDayKey format: "
            f"{race_day_key!r}"
        )

    prefix, _ = race_day_key.split(
        marker,
        1,
    )

    if not prefix:
        raise ValueError(
            "Missing race-day prefix in "
            f"{race_day_key!r}"
        )

    return prefix


def history_track_code_for_race_day_key(
    race_day_key: str,
) -> str:
    prefix = race_day_prefix(
        race_day_key
    )

    try:
        return (
            RACE_DAY_PREFIX_TO_HISTORY_TRACK_CODE[
                prefix
            ]
        )
    except KeyError as exc:
        raise KeyError(
            "No verified historical track-code "
            f"mapping for race-day prefix "
            f"{prefix!r} "
            f"from {race_day_key!r}"
        ) from exc
