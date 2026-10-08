from __future__ import annotations

from v75.system_optimizer_v1 import (
    optimize_system,
)
from v75.system_optimizer_v3_profiles import (
    build_risk_profiles,
    optimize_system_constrained,
)


legs = []

for leg_number in range(
    1,
    8,
):
    legs.append(
        {
            "leg":
                leg_number,
            "rankings": [
                {
                    "rank": 1,
                    "startNumber": 1,
                    "score": 1.0,
                },
                {
                    "rank": 2,
                    "startNumber": 2,
                    "score": 0.4,
                },
                {
                    "rank": 3,
                    "startNumber": 3,
                    "score": 0.0,
                },
            ],
        }
    )


original = optimize_system(
    legs,
    max_rows=128,
)

unconstrained = (
    optimize_system_constrained(
        legs,
        max_rows=128,
    )
)

assert (
    unconstrained[
        "actualRows"
    ]
    == original[
        "actualRows"
    ]
)

assert abs(
    unconstrained[
        "estimatedAll7Coverage"
    ]
    - original[
        "estimatedAll7Coverage"
    ]
) < 1e-12

assert [
    leg[
        "selectedStartNumbers"
    ]
    for leg
    in unconstrained[
        "legs"
    ]
] == [
    leg[
        "selectedStartNumbers"
    ]
    for leg
    in original[
        "legs"
    ]
]

print(
    "PASS: unconstrained v3 matches "
    "canonical v1 optimizer."
)


forced = (
    optimize_system_constrained(
        legs,
        max_rows=128,
        min_k_by_leg={
            1: 2,
            3: 2,
        },
    )
)

by_leg = {
    int(leg["leg"]):
        int(leg["k"])
    for leg
    in forced[
        "legs"
    ]
}

assert by_leg[1] >= 2
assert by_leg[3] >= 2

print(
    "PASS: per-leg minimum selection "
    "constraints enforced."
)


flat_legs = []

for leg_number in range(
    1,
    8,
):
    flat_legs.append(
        {
            "leg":
                leg_number,
            "rankings": [
                {
                    "rank": rank,
                    "startNumber": rank,
                    "score": 0.0,
                }
                for rank
                in range(
                    1,
                    5,
                )
            ],
        }
    )


profiles = build_risk_profiles(
    flat_legs,
    total_budget_nok=400,
    row_price_nok=0.5,
    min_banker_probability=0.35,
)

profile_map = {
    row["profile"]:
        row
    for row
    in profiles[
        "profiles"
    ]
}

for leg in profile_map[
    "NO_WEAK_BANKER"
][
    "legs"
]:
    assert (
        int(
            leg["k"]
        )
        >= 2
    )

for leg in profile_map[
    "NO_BANKER"
][
    "legs"
]:
    assert (
        int(
            leg["k"]
        )
        >= 2
    )

assert (
    profile_map[
        "MAX_P7"
    ][
        "estimatedAll7Coverage"
    ]
    + 1e-12
    >= profile_map[
        "NO_WEAK_BANKER"
    ][
        "estimatedAll7Coverage"
    ]
)

assert (
    profile_map[
        "MAX_P7"
    ][
        "estimatedAll7Coverage"
    ]
    + 1e-12
    >= profile_map[
        "NO_BANKER"
    ][
        "estimatedAll7Coverage"
    ]
)

print(
    "PASS: risk profiles obey banker "
    "constraints."
)

print(
    "PASS: constrained profiles cannot "
    "beat unconstrained MAX P7 objective."
)

print(
    "PASS: System Optimizer v3 "
    "risk-profile contract."
)
