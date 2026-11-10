"""OpenAPI shapes for strict M1 projections, without runtime filesystem reads."""

from dataclasses import fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import Any, Literal, get_args, get_origin, get_type_hints

from neurofold.core._contracts import Contract
from neurofold.core.canonical import MAX_SAFE_INTEGER, CanonicalObject


def scientific_schema(
    record: type[Contract], definitions: dict[str, Any]
) -> dict[str, Any]:
    def describe(value: Any) -> dict[str, Any]:
        origin, args = get_origin(value), get_args(value)
        if origin is Literal:
            return {"enum": list(args)}
        if origin is UnionType:
            return {"anyOf": [describe(item) for item in args]}
        if origin is tuple:
            return {"type": "array", "items": describe(args[0])}
        if value is CanonicalObject:
            return {"type": "object"}
        if isinstance(value, type) and issubclass(value, Enum):
            return {"type": "string", "enum": [item.value for item in value]}
        if isinstance(value, type) and issubclass(value, Contract):
            assert is_dataclass(value)
            name = "NF04" + value.__name__
            if name not in definitions:
                definitions[name] = {}
                hints = get_type_hints(value)
                definitions[name] = {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [f.name for f in fields(value)],
                    "properties": {
                        f.name: describe(hints[f.name]) for f in fields(value)
                    },
                }
            return {"$ref": "#/components/schemas/" + name}
        if value is int:
            return {
                "type": "integer",
                "minimum": -MAX_SAFE_INTEGER,
                "maximum": MAX_SAFE_INTEGER,
            }
        return {"type": {str: "string", bool: "boolean", type(None): "null"}[value]}

    return describe(record)
