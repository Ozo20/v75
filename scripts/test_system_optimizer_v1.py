from v75.system_optimizer_v1 import (
    optimize_system,
)


legs = []

for leg_number in range(1, 8):
    legs.append(
        {
            "leg": leg_number,
            "rankings": [
                {
                    "rank": 1,
                    "startNumber": 1,
                    "score": 0.90,
                },
                {
                    "rank": 2,
                    "startNumber": 2,
                    "score": 0.50,
                },
                {
                    "rank": 3,
                    "startNumber": 3,
                    "score": 0.10,
                },
            ],
        }
    )


one_row = optimize_system(
    legs,
    max_rows=1,
)

assert (
    one_row["actualRows"]
    == 1
)

assert all(
    leg["k"] == 1
    for leg
    in one_row["legs"]
)

print(
    "PASS: one-row system "
    "selects one horse per leg."
)


system = optimize_system(
    legs,
    max_rows=128,
)

assert (
    system["actualRows"]
    <= 128
)

assert len(
    system["legs"]
) == 7

assert all(
    leg["k"] >= 1
    for leg
    in system["legs"]
)

print(
    "PASS: optimizer respects "
    "multiplicative row budget."
)

print(
    "PASS: optimizer contract."
)
