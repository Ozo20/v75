from __future__ import annotations

import re
import unicodedata
from typing import Any


SCANDINAVIAN_TRANSLATION = str.maketrans(
    {
        "ø": "o",
        "Ø": "O",
        "æ": "ae",
        "Æ": "Ae",
        "å": "a",
        "Å": "A",
    }
)


def canonical_driver_name(
    value: Any,
) -> str | None:
    """
    Conservative driver-name identity normalization.

    Observed source variation includes:
      Bjørn Goop / Björn Goop
      Magnus A Djuse / Magnus A. Djuse
      Mats E Djuse / Mats E. Djuse

    Identity is based on canonicalized full name.
    formRowKey driver suffixes are NOT identities:
    one observed token ('To Gud') maps to both
    Tormod Gudmestad and Torstein Gudmestad.
    """

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    text = text.translate(
        SCANDINAVIAN_TRANSLATION
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(
            char
        )
    )

    text = re.sub(
        r"[^0-9A-Za-z]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return (
        text.casefold()
        if text
        else None
    )
