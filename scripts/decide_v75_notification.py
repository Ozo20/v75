from __future__ import annotations

import argparse
import json
import re
from typing import Any


OPPORTUNITY_STATES = (
    "UNKNOWN",
    "NOT_INTERESTING",
    "INTERESTING",
)

FINAL_RECOMMENDATIONS = (
    "PENDING",
    "NO_BET",
    "HARVEST",
    "VALUE",
    "ATTACK",
)

VALID_STAKES: dict[
    str,
    set[int],
] = {
    "PENDING":
        {0},
    "NO_BET":
        {0},
    "HARVEST":
        {50, 100},
    "VALUE":
        {200},
    "ATTACK":
        {400, 800},
}


def safe_race_day_key(
    value: str,
) -> str:
    key = value.strip()

    if not re.fullmatch(
        r"[A-Za-z0-9_-]+",
        key,
    ):
        raise ValueError(
            "Unsafe or missing raceDayKey."
        )

    return key


def notification_key(
    race_day_key: str,
    stage: str,
) -> str:
    key = safe_race_day_key(
        race_day_key
    )

    if stage not in {
        "HEADS_UP",
        "FINAL",
        "LAST_CALL",
    }:
        raise ValueError(
            f"Unknown notification stage: "
            f"{stage}"
        )

    return (
        f"{key}:{stage}"
    )


def validate_inputs(
    *,
    opportunity: str,
    recommendation: str,
    stake_nok: int,
) -> None:
    if (
        opportunity
        not in OPPORTUNITY_STATES
    ):
        raise ValueError(
            "Unknown opportunity state: "
            f"{opportunity}"
        )

    if (
        recommendation
        not in FINAL_RECOMMENDATIONS
    ):
        raise ValueError(
            "Unknown recommendation: "
            f"{recommendation}"
        )

    if (
        stake_nok
        not in VALID_STAKES[
            recommendation
        ]
    ):
        allowed = sorted(
            VALID_STAKES[
                recommendation
            ]
        )

        raise ValueError(
            f"Invalid stake {stake_nok} "
            f"for {recommendation}; "
            f"allowed={allowed}"
        )


def display_name(
    race_day_name: str | None,
    race_day_key: str,
) -> str:
    if (
        isinstance(
            race_day_name,
            str,
        )
        and race_day_name.strip()
    ):
        return race_day_name.strip()

    return race_day_key


def time_phrase(
    minutes_to_start: float,
) -> str:
    rounded = max(
        1,
        int(round(minutes_to_start)),
    )

    if 50 <= minutes_to_start <= 60:
        return (
            "Ca. 1 time til V75-1."
        )

    return (
        f"Ca. {rounded} min til V75-1."
    )


def base_result(
    *,
    race_day_key: str,
    race_day_name: str | None,
    minutes_to_start: float,
) -> dict[str, Any]:
    return {
        "schemaVersion":
            "1.0",
        "decision":
            "v75-notification-decision-v1",
        "raceDayKey":
            race_day_key,
        "raceDayName":
            race_day_name,
        "minutesToStart":
            minutes_to_start,
        "action":
            "SILENT",
        "stage":
            None,
        "notificationKey":
            None,
        "message":
            None,
        "reason":
            None,
        "guardrails": {
            "networkUsed":
                False,
            "notificationSent":
                False,
            "modelUsed":
                False,
            "repoWrites":
                False,
        },
    }


def decide_notification(
    *,
    race_day_key: str,
    race_day_name: str | None,
    minutes_to_start: float,
    opportunity: str,
    recommendation: str,
    stake_nok: int,
    sent_keys: set[str],
) -> dict[str, Any]:
    race_day_key = (
        safe_race_day_key(
            race_day_key
        )
    )

    validate_inputs(
        opportunity=opportunity,
        recommendation=
            recommendation,
        stake_nok=stake_nok,
    )

    result = base_result(
        race_day_key=
            race_day_key,
        race_day_name=
            race_day_name,
        minutes_to_start=
            minutes_to_start,
    )

    name = display_name(
        race_day_name,
        race_day_key,
    )

    if minutes_to_start < 0:
        result["reason"] = (
            "RACE_ALREADY_STARTED"
        )
        return result

    if minutes_to_start > 60:
        result["reason"] = (
            "BEFORE_NOTIFICATION_HORIZON"
        )
        return result

    # Final five-minute window takes
    # precedence over all earlier stages.
    if minutes_to_start <= 5:
        if recommendation in {
            "HARVEST",
            "VALUE",
            "ATTACK",
        }:
            key = notification_key(
                race_day_key,
                "LAST_CALL",
            )

            if key in sent_keys:
                result["reason"] = (
                    "LAST_CALL_ALREADY_SENT"
                )
                return result

            result.update(
                {
                    "action":
                        "LAST_CALL",
                    "stage":
                        "LAST_CALL",
                    "notificationKey":
                        key,
                    "message":
                        (
                            "⏰ 5 min igjen. "
                            f"V75 {name}: "
                            f"{recommendation} "
                            f"{stake_nok} kr. "
                            "Bong klar."
                        ),
                    "reason":
                        "PLAY_RECOMMENDATION_ACTIVE",
                }
            )

            return result

        result["reason"] = (
            "NO_PLAY_FOR_LAST_CALL"
        )
        return result

    # Final recommendation window:
    # 15 > minutes > 5.
    if minutes_to_start <= 15:
        key = notification_key(
            race_day_key,
            "FINAL",
        )

        if key in sent_keys:
            result["reason"] = (
                "FINAL_ALREADY_SENT"
            )
            return result

        if recommendation == "PENDING":
            result["reason"] = (
                "FINAL_RECOMMENDATION_PENDING"
            )
            return result

        if recommendation == "NO_BET":
            result.update(
                {
                    "action":
                        "NO_BET",
                    "stage":
                        "FINAL",
                    "notificationKey":
                        key,
                    "message":
                        (
                            f"⛔ V75 {name}: "
                            "NO BET. "
                            "Omgangen vurderes ikke "
                            "som god nok til spill."
                        ),
                    "reason":
                        "FINAL_NO_BET",
                }
            )

            return result

        result.update(
            {
                "action":
                    "PLAY",
                "stage":
                    "FINAL",
                "notificationKey":
                    key,
                "message":
                    (
                        f"🎯 V75 {name}: "
                        f"{recommendation} "
                        f"{stake_nok} kr. "
                        f"{time_phrase(minutes_to_start)} "
                        "Bong er klar."
                    ),
                "reason":
                    "FINAL_PLAY_RECOMMENDATION",
            }
        )

        return result

    # Heads-up window:
    # 60 >= minutes > 15.
    key = notification_key(
        race_day_key,
        "HEADS_UP",
    )

    if key in sent_keys:
        result["reason"] = (
            "HEADS_UP_ALREADY_SENT"
        )
        return result

    if opportunity != "INTERESTING":
        result["reason"] = (
            "OPPORTUNITY_NOT_INTERESTING"
        )
        return result

    result.update(
        {
            "action":
                "HEADS_UP",
            "stage":
                "HEADS_UP",
            "notificationKey":
                key,
            "message":
                (
                    "🐎 Heads up! "
                    f"V75 {name} begynner "
                    "å se interessant ut. "
                    "Det kan være "
                    "spillemuligheter her. "
                    f"{time_phrase(minutes_to_start)} "
                    "Endelig vurdering kommer "
                    "nærmere start."
                ),
            "reason":
                "INTERESTING_OPPORTUNITY",
        }
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--race-day-key",
        required=True,
    )

    parser.add_argument(
        "--race-day-name",
    )

    parser.add_argument(
        "--minutes-to-start",
        required=True,
        type=float,
    )

    parser.add_argument(
        "--opportunity",
        choices=OPPORTUNITY_STATES,
        default="UNKNOWN",
    )

    parser.add_argument(
        "--recommendation",
        choices=FINAL_RECOMMENDATIONS,
        default="PENDING",
    )

    parser.add_argument(
        "--stake-nok",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--sent-key",
        action="append",
        default=[],
    )

    args = parser.parse_args()

    result = decide_notification(
        race_day_key=
            args.race_day_key,
        race_day_name=
            args.race_day_name,
        minutes_to_start=
            args.minutes_to_start,
        opportunity=
            args.opportunity,
        recommendation=
            args.recommendation,
        stake_nok=
            args.stake_nok,
        sent_keys=set(
            args.sent_key
        ),
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
