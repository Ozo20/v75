from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "1.0"
PACKAGE = "hest-observation-v1"

OSLO = ZoneInfo("Europe/Oslo")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.resolve()

SAFE_COMPONENT = re.compile(
    r"^[A-Za-z0-9_.-]+$"
)

SOURCE_CATEGORIES = {
    "MARKET",
    "RACE_SCHEDULE",
    "START_LIST",
    "RACE_PROGRAM",
    "HORSE_HISTORY",
    "DRIVER_HISTORY",
    "TRAINER_HISTORY",
    "EQUIPMENT",
    "STALLTIPS",
    "EXPERT_TIPS",
    "WEATHER",
    "TRACK_CONDITION",
    "OTHER_PRE_RACE",
    "OUTCOME",
}


class ObjectStore(Protocol):
    network_used: bool

    def get_bytes(
        self,
        key: str,
    ) -> bytes | None:
        ...

    def put_if_absent(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str,
    ) -> bool:
        ...


class LocalImmutableObjectStore:
    network_used = False

    def __init__(
        self,
        root: Path,
    ) -> None:
        resolved = (
            root
            .expanduser()
            .resolve()
        )

        if (
            resolved == REPO_ROOT
            or resolved.is_relative_to(
                REPO_ROOT
            )
        ):
            raise ValueError(
                "Data output root must be "
                "outside the repository."
            )

        self.root = resolved

    def path_for(
        self,
        key: str,
    ) -> Path:
        relative = Path(key)

        if (
            relative.is_absolute()
            or ".." in relative.parts
        ):
            raise ValueError(
                f"Unsafe object key: {key!r}"
            )

        return (
            self.root
            / relative
        )

    def get_bytes(
        self,
        key: str,
    ) -> bytes | None:
        path = self.path_for(
            key
        )

        if not path.is_file():
            return None

        return path.read_bytes()

    def put_if_absent(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str,
    ) -> bool:
        del content_type

        path = self.path_for(
            key
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            with path.open(
                "xb"
            ) as handle:
                handle.write(
                    body
                )

            return True

        except FileExistsError:
            return False


def parse_datetime(
    value: str,
) -> datetime:
    candidate = value.strip()

    if candidate.endswith("Z"):
        candidate = (
            candidate[:-1]
            + "+00:00"
        )

    parsed = datetime.fromisoformat(
        candidate
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=OSLO
        )

    return parsed.astimezone(
        OSLO
    )


def require_aware(
    value: datetime,
    name: str,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{name} must be timezone-aware."
        )


def safe_component(
    value: str,
    name: str,
) -> str:
    candidate = value.strip()

    if (
        not candidate
        or SAFE_COMPONENT.fullmatch(
            candidate
        ) is None
    ):
        raise ValueError(
            f"Unsafe or missing {name}: "
            f"{value!r}"
        )

    return candidate


def normalized_prefix(
    value: str,
) -> str:
    candidate = (
        value.strip()
        .strip("/")
    )

    if not candidate:
        raise ValueError(
            "Empty data prefix."
        )

    parts = candidate.split(
        "/"
    )

    for part in parts:
        safe_component(
            part,
            "prefix component",
        )

    return "/".join(
        parts
    )


def normalize_category(
    value: str,
) -> str:
    category = (
        value.strip()
        .upper()
    )

    if category not in SOURCE_CATEGORIES:
        raise ValueError(
            "Unsupported source category: "
            f"{value!r}"
        )

    return category


def sha256_bytes(
    body: bytes,
) -> str:
    return hashlib.sha256(
        body
    ).hexdigest()


def json_bytes(
    payload: Any,
) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode(
        "utf-8"
    )


def effective_known_at(
    *,
    captured_at: datetime,
    source_published_at:
        datetime | None,
) -> datetime:
    require_aware(
        captured_at,
        "captured_at",
    )

    if source_published_at is None:
        return captured_at

    require_aware(
        source_published_at,
        "source_published_at",
    )

    # Conservative rule:
    # information cannot be considered
    # known before either its actual
    # capture or stated publication time.
    return max(
        captured_at,
        source_published_at,
    )


def knowledge_phase(
    *,
    known_at: datetime,
    race_start_at:
        datetime | None,
) -> tuple[
    str,
    float | None,
]:
    require_aware(
        known_at,
        "known_at",
    )

    if race_start_at is None:
        return (
            "UNKNOWN",
            None,
        )

    require_aware(
        race_start_at,
        "race_start_at",
    )

    minutes_to_start = (
        race_start_at
        - known_at
    ).total_seconds() / 60.0

    return (
        (
            "PRE_RACE"
            if minutes_to_start > 0
            else "POST_START"
        ),
        minutes_to_start,
    )


def storage_keys(
    *,
    prefix: str,
    source: str,
    race_day_key: str,
    captured_at: datetime,
    raw_sha256: str,
) -> tuple[
    str,
    str,
]:
    require_aware(
        captured_at,
        "captured_at",
    )

    prefix = normalized_prefix(
        prefix
    )

    source = safe_component(
        source,
        "source",
    )

    race_day_key = safe_component(
        race_day_key,
        "raceDayKey",
    )

    if not re.fullmatch(
        r"[0-9a-f]{64}",
        raw_sha256,
    ):
        raise ValueError(
            "raw_sha256 must be a "
            "64-character lowercase SHA256."
        )

    local = captured_at.astimezone(
        OSLO
    )

    date_path = (
        f"{local:%Y}/"
        f"{local:%m}/"
        f"{local:%d}"
    )

    stamp = local.strftime(
        "%Y%m%dT%H%M%S%f%z"
    )

    identity = (
        f"{stamp}-"
        f"{raw_sha256[:16]}"
    )

    raw_key = (
        f"{prefix}/raw/"
        f"{source}/"
        f"{date_path}/"
        f"{race_day_key}/"
        f"{identity}.bin"
    )

    observation_key = (
        f"{prefix}/observations/"
        f"{source}/"
        f"{date_path}/"
        f"{race_day_key}/"
        f"{identity}.json"
    )

    return (
        raw_key,
        observation_key,
    )


def normalize_entity_refs(
    value: dict[str, Any] | None,
) -> dict[str, str]:
    if value is None:
        return {}

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "entity_refs must be an object."
        )

    output: dict[
        str,
        str,
    ] = {}

    for key, raw_value in value.items():
        safe_key = safe_component(
            str(key),
            "entity ref key",
        )

        candidate = str(
            raw_value
        ).strip()

        if not candidate:
            raise ValueError(
                "Entity reference value "
                "cannot be empty."
            )

        output[
            safe_key
        ] = candidate

    return dict(
        sorted(
            output.items()
        )
    )


def build_observation(
    *,
    source: str,
    category: str,
    race_day_key: str,
    raw_body: bytes,
    captured_at: datetime,
    source_published_at:
        datetime | None = None,
    race_start_at:
        datetime | None = None,
    source_locator:
        str | None = None,
    raw_content_type:
        str = "application/json",
    entity_refs:
        dict[str, Any] | None = None,
    prefix:
        str = "hest-data",
) -> dict[str, Any]:
    if not isinstance(
        raw_body,
        bytes,
    ):
        raise TypeError(
            "raw_body must be bytes."
        )

    require_aware(
        captured_at,
        "captured_at",
    )

    source = safe_component(
        source,
        "source",
    )

    category = normalize_category(
        category
    )

    race_day_key = safe_component(
        race_day_key,
        "raceDayKey",
    )

    if source_published_at is not None:
        require_aware(
            source_published_at,
            "source_published_at",
        )

    if race_start_at is not None:
        require_aware(
            race_start_at,
            "race_start_at",
        )

    known_at = effective_known_at(
        captured_at=captured_at,
        source_published_at=
            source_published_at,
    )

    phase, minutes = knowledge_phase(
        known_at=known_at,
        race_start_at=
            race_start_at,
    )

    raw_sha = sha256_bytes(
        raw_body
    )

    (
        raw_key,
        observation_key,
    ) = storage_keys(
        prefix=prefix,
        source=source,
        race_day_key=
            race_day_key,
        captured_at=captured_at,
        raw_sha256=raw_sha,
    )

    eligible_for_pre_race = (
        phase == "PRE_RACE"
        and category != "OUTCOME"
    )

    source_clock_anomaly = (
        source_published_at
        is not None
        and source_published_at
        > captured_at
    )

    record = {
        "schemaVersion":
            SCHEMA_VERSION,
        "package":
            PACKAGE,
        "source": {
            "name":
                source,
            "category":
                category,
            "locator":
                source_locator,
            "publishedAt":
                (
                    source_published_at
                    .astimezone(OSLO)
                    .isoformat()
                    if source_published_at
                    is not None
                    else None
                ),
        },
        "subject": {
            "raceDayKey":
                race_day_key,
            "entities":
                normalize_entity_refs(
                    entity_refs
                ),
        },
        "observation": {
            "capturedAt":
                captured_at
                .astimezone(OSLO)
                .isoformat(),
            "effectiveKnownAt":
                known_at
                .astimezone(OSLO)
                .isoformat(),
            "raceStartAt":
                (
                    race_start_at
                    .astimezone(OSLO)
                    .isoformat()
                    if race_start_at
                    is not None
                    else None
                ),
            "knowledgePhase":
                phase,
            "minutesToStart":
                (
                    round(
                        minutes,
                        6,
                    )
                    if minutes
                    is not None
                    else None
                ),
            "sourceClockAnomaly":
                source_clock_anomaly,
        },
        "raw": {
            "sha256":
                raw_sha,
            "byteLength":
                len(raw_body),
            "contentType":
                raw_content_type,
            "objectKey":
                raw_key,
        },
        "storage": {
            "observationKey":
                observation_key,
        },
        "dataUse": {
            "eligibleForPreRaceFeatures":
                eligible_for_pre_race,
            "postStartData":
                phase == "POST_START",
            "outcomeData":
                category == "OUTCOME",
        },
        "guardrails": {
            "immutable":
                True,
            "rawPreserved":
                True,
            "knowledgePhaseDerived":
                True,
            "preRaceEligibilityDerived":
                True,
            "modelUsed":
                False,
            "modelRetuned":
                False,
            "outcomeUsedForPreRaceFeature":
                False,
        },
    }

    return record


def ensure_immutable_object(
    *,
    store: ObjectStore,
    key: str,
    body: bytes,
    content_type: str,
) -> bool:
    existing = store.get_bytes(
        key
    )

    if existing is not None:
        if existing != body:
            raise RuntimeError(
                "Immutable object collision "
                f"at {key}."
            )

        return False

    created = store.put_if_absent(
        key,
        body,
        content_type=
            content_type,
    )

    if created:
        return True

    # Another writer won the race.
    winner = store.get_bytes(
        key
    )

    if winner is None:
        raise RuntimeError(
            "Conditional create lost but "
            f"winner is missing: {key}"
        )

    if winner != body:
        raise RuntimeError(
            "Immutable object race produced "
            f"different bytes at {key}."
        )

    return False


def register_observation(
    *,
    store: ObjectStore,
    source: str,
    category: str,
    race_day_key: str,
    raw_body: bytes,
    captured_at: datetime,
    source_published_at:
        datetime | None = None,
    race_start_at:
        datetime | None = None,
    source_locator:
        str | None = None,
    raw_content_type:
        str = "application/json",
    entity_refs:
        dict[str, Any] | None = None,
    prefix:
        str = "hest-data",
) -> dict[str, Any]:
    observation = build_observation(
        source=source,
        category=category,
        race_day_key=
            race_day_key,
        raw_body=raw_body,
        captured_at=captured_at,
        source_published_at=
            source_published_at,
        race_start_at=
            race_start_at,
        source_locator=
            source_locator,
        raw_content_type=
            raw_content_type,
        entity_refs=
            entity_refs,
        prefix=prefix,
    )

    raw_key = observation[
        "raw"
    ][
        "objectKey"
    ]

    observation_key = (
        observation[
            "storage"
        ][
            "observationKey"
        ]
    )

    raw_created = (
        ensure_immutable_object(
            store=store,
            key=raw_key,
            body=raw_body,
            content_type=
                raw_content_type,
        )
    )

    observation_body = json_bytes(
        observation
    )

    observation_created = (
        ensure_immutable_object(
            store=store,
            key=observation_key,
            body=observation_body,
            content_type=
                "application/json",
        )
    )

    return {
        "schemaVersion":
            SCHEMA_VERSION,
        "logger":
            "hest-data-foundation-v1",
        "state":
            (
                "REGISTERED"
                if (
                    raw_created
                    or observation_created
                )
                else
                "ALREADY_REGISTERED"
            ),
        "source":
            observation[
                "source"
            ][
                "name"
            ],
        "category":
            observation[
                "source"
            ][
                "category"
            ],
        "raceDayKey":
            observation[
                "subject"
            ][
                "raceDayKey"
            ],
        "knowledgePhase":
            observation[
                "observation"
            ][
                "knowledgePhase"
            ],
        "eligibleForPreRaceFeatures":
            observation[
                "dataUse"
            ][
                "eligibleForPreRaceFeatures"
            ],
        "rawSha256":
            observation[
                "raw"
            ][
                "sha256"
            ],
        "rawObjectKey":
            raw_key,
        "observationObjectKey":
            observation_key,
        "guardrails": {
            "rawCreated":
                raw_created,
            "observationCreated":
                observation_created,
            "networkUsed":
                bool(
                    getattr(
                        store,
                        "network_used",
                        False,
                    )
                ),
            "repoWrites":
                False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Register one immutable Hest "
            "raw observation and metadata "
            "envelope."
        )
    )

    parser.add_argument(
        "--raw-file",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--source",
        required=True,
    )

    parser.add_argument(
        "--category",
        required=True,
    )

    parser.add_argument(
        "--race-day-key",
        required=True,
    )

    parser.add_argument(
        "--captured-at",
        required=True,
    )

    parser.add_argument(
        "--source-published-at",
    )

    parser.add_argument(
        "--race-start-at",
    )

    parser.add_argument(
        "--source-locator",
    )

    parser.add_argument(
        "--content-type",
        default="application/json",
    )

    parser.add_argument(
        "--prefix",
        default="hest-data",
    )

    args = parser.parse_args()

    raw_body = (
        args.raw_file
        .read_bytes()
    )

    store = (
        LocalImmutableObjectStore(
            args.output_root
        )
    )

    result = register_observation(
        store=store,
        source=args.source,
        category=args.category,
        race_day_key=
            args.race_day_key,
        raw_body=raw_body,
        captured_at=
            parse_datetime(
                args.captured_at
            ),
        source_published_at=
            (
                parse_datetime(
                    args.source_published_at
                )
                if args.source_published_at
                else None
            ),
        race_start_at=
            (
                parse_datetime(
                    args.race_start_at
                )
                if args.race_start_at
                else None
            ),
        source_locator=
            args.source_locator,
        raw_content_type=
            args.content_type,
        prefix=args.prefix,
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
