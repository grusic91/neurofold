"""Build additive M1 exchange shape schemas; core enforces semantic invariants.

Run from backend: uv run --locked python scripts/prediction_schema.py
No dependencies beyond the standard library and local core contracts.
"""

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints

from neurofold.core._contracts import Contract
from neurofold.core.canonical import MAX_SAFE_INTEGER, CanonicalObject
from neurofold.core.prediction_inputs import (
    AdapterCapability,
    AuxiliaryInput,
    CodeIdentity,
    ParameterDefinition,
    ParameterRequirement,
    ParameterValue,
    PredictionProfile,
    PredictionSpec,
    ResourceLimits,
)
from neurofold.core.prediction_jobs import (
    PredictionAttempt,
    PredictionFailure,
    PredictionJob,
)
from neurofold.core.prediction_outputs import (
    AuxiliaryProvenance,
    ConfidenceDescriptor,
    EnvironmentProvenance,
    ExecutionProvenance,
    ModelProvenance,
    PredictionMapping,
    PredictionResidue,
    PredictionResult,
    PredictionSample,
    PreprocessingProvenance,
    SuccessfulPredictionProvenance,
    WeightIdentity,
)

GROUPS: dict[str, tuple[type[Contract], ...]] = {
    "prediction": (
        AdapterCapability,
        AuxiliaryInput,
        CodeIdentity,
        ParameterDefinition,
        ParameterRequirement,
        ParameterValue,
        PredictionProfile,
        PredictionSpec,
        ResourceLimits,
    ),
    "prediction-job": (PredictionAttempt, PredictionFailure, PredictionJob),
    "prediction-result": (
        AuxiliaryProvenance,
        ConfidenceDescriptor,
        PredictionMapping,
        PredictionResidue,
        PredictionResult,
        PredictionSample,
    ),
    "prediction-provenance": (
        AuxiliaryProvenance,
        EnvironmentProvenance,
        ExecutionProvenance,
        ModelProvenance,
        PreprocessingProvenance,
        SuccessfulPredictionProvenance,
        WeightIdentity,
    ),
}


def schema_for(roots: tuple[type[Contract], ...], family: str) -> dict[str, object]:
    definitions: dict[str, object] = {}

    def describe(annotation: object) -> dict[str, object]:
        origin, args = get_origin(annotation), get_args(annotation)
        if origin is Literal:
            return {"enum": list(args)}
        if origin is UnionType:
            return {"anyOf": [describe(arg) for arg in args]}
        if origin is tuple:
            return {"type": "array", "items": describe(args[0])}
        if annotation is CanonicalObject:
            # Only inherited NF-08 Metadata uses this; prediction sections are typed.
            return {"type": "object"}
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return {"type": "string", "enum": [value.value for value in annotation]}
        if isinstance(annotation, type) and issubclass(annotation, Contract):
            name = annotation.__name__
            if name not in definitions:
                definitions[name] = {}
                assert is_dataclass(annotation)
                hints = get_type_hints(annotation)
                definitions[name] = {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [field.name for field in fields(annotation)],
                    "properties": {
                        field.name: describe(hints[field.name])
                        for field in fields(annotation)
                    },
                }
            return {"$ref": f"#/$defs/{name}"}
        if annotation is int:
            return {
                "type": "integer",
                "minimum": -MAX_SAFE_INTEGER,
                "maximum": MAX_SAFE_INTEGER,
            }
        for python_type, json_type in (
            (str, "string"),
            (bool, "boolean"),
            (type(None), "null"),
        ):
            if annotation is python_type:
                return {"type": json_type}
        raise ValueError("Unsupported exchange annotation")

    options = [describe(root) for root in roots]
    # Express local scalar constraints where JSON Schema can faithfully do so.
    for name, definition in definitions.items():
        assert isinstance(definition, dict)
        properties = definition["properties"]
        assert isinstance(properties, dict)
        if name == "ContentHash":
            properties["sha256"] = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
        if name == "SoftwareIdentity":
            for key in ("name", "version"):
                properties[key] = {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$",
                }
        if name == "ResourceLimits":
            for key in properties:
                if key != "schema_version":
                    properties[key] = {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_SAFE_INTEGER,
                    }
        if name == "Metadata":
            definition["allOf"] = [
                {
                    "if": {"properties": {"state": {"const": "present"}}},
                    "then": {
                        "properties": {
                            "reason": {"type": "null"},
                            "value": {"not": {"type": "null"}},
                        }
                    },
                    "else": {
                        "properties": {
                            "value": {"type": "null"},
                            "reason": {"type": "string", "pattern": r"\S"},
                        }
                    },
                }
            ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:neurofold:{family}:1",
        "title": f"NeuroFold {family} v1 exchange shapes",
        "$comment": "Shape schema; strict codecs and semantic validation required.",
        "anyOf": options,
        "$defs": definitions,
    }


def main() -> None:
    destination = Path(__file__).resolve().parents[2] / "docs/schemas"
    for family, roots in GROUPS.items():
        (destination / f"neurofold-{family}-1.schema.json").write_bytes(
            (
                json.dumps(schema_for(roots, family), sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
        )


if __name__ == "__main__":
    main()
