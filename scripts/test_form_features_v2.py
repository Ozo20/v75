from v75.form_features_v2 import (
    parse_time_raw,
)


cases = [
    (
        "13,8a",
        13.8,
        "CLEAN_NUMERIC",
    ),
    (
        "14,2",
        14.2,
        "CLEAN_NUMERIC",
    ),
    (
        "30,5 g",
        30.5,
        "NUMERIC_GALLOP",
    ),
    (
        "dg a",
        None,
        "DISQUALIFIED",
    ),
    (
        "dg",
        None,
        "DISQUALIFIED",
    ),
    (
        "br ag",
        None,
        "BROKEN",
    ),
]

for raw, expected_time, expected_status in cases:
    parsed = parse_time_raw(
        raw
    )

    assert (
        parsed["kmTime"]
        == expected_time
    ), (
        raw,
        parsed,
    )

    assert (
        parsed["status"]
        == expected_status
    ), (
        raw,
        parsed,
    )

    print(
        f"PASS: "
        f"{raw!r:<10} -> "
        f"{expected_time!s:<5} "
        f"{expected_status}"
    )

print(
    "PASS: parser contract."
)
