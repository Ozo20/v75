from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PATH = (
    ROOT
    / "scripts"
    / "decide_v75_notification.py"
)


def load_module():
    spec = (
        importlib.util
        .spec_from_file_location(
            "notification_decision",
            PATH,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Could not load notification "
            "decision module."
        )

    module = (
        importlib.util
        .module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


module = load_module()

KEY = "BT_NR_2026-10-17"
NAME = "Bergen"


def decide(
    minutes,
    *,
    opportunity="UNKNOWN",
    recommendation="PENDING",
    stake=0,
    sent=(),
):
    return (
        module.decide_notification(
            race_day_key=KEY,
            race_day_name=NAME,
            minutes_to_start=minutes,
            opportunity=opportunity,
            recommendation=
                recommendation,
            stake_nok=stake,
            sent_keys=set(sent),
        )
    )


early = decide(
    61,
    opportunity="INTERESTING",
)

assert early["action"] == "SILENT"
assert (
    early["reason"]
    == "BEFORE_NOTIFICATION_HORIZON"
)

print(
    "PASS: no notification before "
    "60-minute horizon."
)


heads_up = decide(
    60,
    opportunity="INTERESTING",
)

assert (
    heads_up["action"]
    == "HEADS_UP"
)

assert (
    heads_up["stage"]
    == "HEADS_UP"
)

assert (
    heads_up["notificationKey"]
    == f"{KEY}:HEADS_UP"
)

assert (
    "Ca. 1 time"
    in heads_up["message"]
)

print(
    "PASS: interesting opportunity "
    "creates T-60 heads-up."
)


late_heads_up = decide(
    40,
    opportunity="INTERESTING",
)

assert (
    late_heads_up["action"]
    == "HEADS_UP"
)

assert (
    "Ca. 40 min til V75-1."
    in late_heads_up["message"]
)

print(
    "PASS: delayed heads-up reports "
    "actual remaining time."
)


quiet = decide(
    60,
    opportunity="NOT_INTERESTING",
)

assert quiet["action"] == "SILENT"

print(
    "PASS: uninteresting card remains "
    "silent at T-60."
)


duplicate_heads_up = decide(
    45,
    opportunity="INTERESTING",
    sent=(f"{KEY}:HEADS_UP",),
)

assert (
    duplicate_heads_up["action"]
    == "SILENT"
)

assert (
    duplicate_heads_up["reason"]
    == "HEADS_UP_ALREADY_SENT"
)

print(
    "PASS: heads-up is idempotent."
)


final_value = decide(
    15,
    opportunity="INTERESTING",
    recommendation="VALUE",
    stake=200,
)

assert (
    final_value["action"]
    == "PLAY"
)

assert (
    final_value["stage"]
    == "FINAL"
)

assert (
    final_value["notificationKey"]
    == f"{KEY}:FINAL"
)

assert (
    "VALUE 200 kr"
    in final_value["message"]
)

print(
    "PASS: VALUE recommendation creates "
    "final play notification."
)


delayed_final = decide(
    10,
    opportunity="INTERESTING",
    recommendation="VALUE",
    stake=200,
)

assert (
    delayed_final["action"]
    == "PLAY"
)

assert (
    "Ca. 10 min til V75-1."
    in delayed_final["message"]
)

print(
    "PASS: delayed final notification "
    "reports actual remaining time."
)


final_no_bet = decide(
    15,
    opportunity="INTERESTING",
    recommendation="NO_BET",
    stake=0,
)

assert (
    final_no_bet["action"]
    == "NO_BET"
)

assert (
    final_no_bet["notificationKey"]
    == f"{KEY}:FINAL"
)

print(
    "PASS: NO BET creates one final "
    "decision notification."
)


pending = decide(
    10,
    opportunity="INTERESTING",
    recommendation="PENDING",
)

assert pending["action"] == "SILENT"

assert (
    pending["reason"]
    == "FINAL_RECOMMENDATION_PENDING"
)

print(
    "PASS: pending final decision does "
    "not fabricate a recommendation."
)


duplicate_final = decide(
    10,
    opportunity="INTERESTING",
    recommendation="ATTACK",
    stake=400,
    sent=(f"{KEY}:FINAL",),
)

assert (
    duplicate_final["action"]
    == "SILENT"
)

print(
    "PASS: final stage is deduplicated "
    "independently of recommendation."
)


last_call = decide(
    5,
    opportunity="INTERESTING",
    recommendation="ATTACK",
    stake=400,
)

assert (
    last_call["action"]
    == "LAST_CALL"
)

assert (
    last_call["notificationKey"]
    == f"{KEY}:LAST_CALL"
)

assert (
    "5 min igjen"
    in last_call["message"]
)

print(
    "PASS: active play recommendation "
    "creates last call at T-5."
)


no_bet_last_call = decide(
    5,
    recommendation="NO_BET",
    stake=0,
)

assert (
    no_bet_last_call["action"]
    == "SILENT"
)

print(
    "PASS: NO BET does not generate "
    "a last-call reminder."
)


duplicate_last_call = decide(
    3,
    recommendation="VALUE",
    stake=200,
    sent=(f"{KEY}:LAST_CALL",),
)

assert (
    duplicate_last_call["action"]
    == "SILENT"
)

print(
    "PASS: last-call stage is idempotent."
)


started = decide(
    -0.1,
    recommendation="VALUE",
    stake=200,
)

assert started["action"] == "SILENT"

assert (
    started["reason"]
    == "RACE_ALREADY_STARTED"
)

print(
    "PASS: post-start notifications "
    "fail closed."
)


assert (
    module.notification_key(
        KEY,
        "FINAL",
    )
    == f"{KEY}:FINAL"
)

print(
    "PASS: notification key is stable "
    "per stage, not recommendation."
)


valid_cases = (
    ("NO_BET", 0),
    ("HARVEST", 50),
    ("HARVEST", 100),
    ("VALUE", 200),
    ("ATTACK", 400),
    ("ATTACK", 800),
)

for recommendation, stake in valid_cases:
    module.validate_inputs(
        opportunity="UNKNOWN",
        recommendation=
            recommendation,
        stake_nok=stake,
    )

print(
    "PASS: canonical stake classes "
    "are accepted."
)


invalid_cases = (
    ("NO_BET", 100),
    ("HARVEST", 200),
    ("VALUE", 400),
    ("ATTACK", 200),
)

for recommendation, stake in invalid_cases:
    try:
        module.validate_inputs(
            opportunity="UNKNOWN",
            recommendation=
                recommendation,
            stake_nok=stake,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Invalid recommendation/stake "
            "combination did not fail."
        )

print(
    "PASS: invalid stake classes "
    "fail closed."
)


source = PATH.read_text(
    encoding="utf-8"
)

for forbidden in (
    "urllib",
    "requests",
    "playwright",
    "subprocess",
    "smtplib",
):
    assert forbidden not in source

print(
    "PASS: notification decision v1 "
    "contains no delivery mechanism."
)
