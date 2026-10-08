from v75.driver_identity import (
    canonical_driver_name,
)


assert (
    canonical_driver_name(
        "Bjørn Goop"
    )
    == "bjorn goop"
)

assert (
    canonical_driver_name(
        "Björn Goop"
    )
    == "bjorn goop"
)

assert (
    canonical_driver_name(
        "Magnus A Djuse"
    )
    == canonical_driver_name(
        "Magnus A. Djuse"
    )
)

assert (
    canonical_driver_name(
        "Mats E Djuse"
    )
    == canonical_driver_name(
        "Mats E. Djuse"
    )
)

assert (
    canonical_driver_name(
        "Åsbjørn Tengsareid"
    )
    == "asbjorn tengsareid"
)

assert (
    canonical_driver_name(
        "Tormod Gudmestad"
    )
    != canonical_driver_name(
        "Torstein Gudmestad"
    )
)

assert (
    canonical_driver_name(None)
    is None
)

assert (
    canonical_driver_name("   ")
    is None
)

print(
    "PASS: conservative driver identity "
    "normalization contract verified."
)
