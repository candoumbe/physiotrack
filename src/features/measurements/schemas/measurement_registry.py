from __future__ import annotations

from typing import get_args

from . import Measurement, MeasurementType


def plural_resource_name(measurement_type: MeasurementType) -> str:
    parts = measurement_type.value.split("_")
    final_part = parts[-1]

    if final_part.endswith("y") and final_part[-2:-1] not in "aeiou":
        parts[-1] = f"{final_part[:-1]}ies"
    elif final_part.endswith(("s", "x", "z", "ch", "sh")):
        parts[-1] = f"{final_part}es"
    else:
        parts[-1] = f"{final_part}s"

    return "_".join(parts)


def resolve_measurement_type(resource_name: str) -> MeasurementType | None:
    measurement_union = get_args(Measurement)[0]
    registered_types = {
        model.model_fields["type"].default for model in get_args(measurement_union)
    }

    for measurement_type in MeasurementType:
        if measurement_type not in registered_types:
            continue
        if resource_name in (
            measurement_type.value,
            plural_resource_name(measurement_type),
        ):
            return measurement_type

    return None
