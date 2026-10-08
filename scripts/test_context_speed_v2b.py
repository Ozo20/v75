from v75.context_speed_v2b import (
    context_weighted_speed,
)


history = [
    {
        "raceDate":
            "2026-08-20T00:00:00",
        "distance":
            2100,
        "timeRaw":
            "14,0a",
    },
    {
        "raceDate":
            "2026-08-10T00:00:00",
        "distance":
            2140,
        "timeRaw":
            "14,4",
    },
    {
        "raceDate":
            "2026-08-01T00:00:00",
        "distance":
            1609,
        "timeRaw":
            "12,9a",
    },
    {
        "raceDate":
            "2026-07-20T00:00:00",
        "distance":
            2100,
        "timeRaw":
            "15,0 g",
    },
]

result = context_weighted_speed(
    history,
    current_distance=2040,
    current_start_method="Auto",
)

assert (
    result["tier"]
    == "SAME_METHOD_WITHIN_200M"
), result

assert (
    result["rowsUsed"]
    == 1
), result

assert abs(
    result["contextKmTime"]
    - 14.0
) < 1e-9

print(
    "PASS: same-method + "
    "distance context selected."
)

fallback = context_weighted_speed(
    history,
    current_distance=2640,
    current_start_method="Volt",
)

assert (
    fallback["tier"]
    == "SAME_METHOD"
), fallback

assert (
    fallback["contextKmTime"]
    == 14.4
), fallback

print(
    "PASS: same-method fallback selected."
)

print(
    "PASS: context feature contract."
)
