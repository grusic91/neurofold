"""Strict standard-library wire codec for the small shared contract vocabulary."""

from dataclasses import fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import Literal, Self, cast, get_args, get_origin, get_type_hints

from neurofold.core.canonical import CanonicalObject, canonical_json, parse_json


def _check(annotation: object, value: object) -> bool:
    origin, arguments = get_origin(annotation), get_args(annotation)
    if origin is Literal:
        return any(type(value) is type(item) and value == item for item in arguments)
    if origin is UnionType:
        return any(_check(item, value) for item in arguments)
    if origin is tuple:
        return type(value) is tuple and all(
            _check(arguments[0], item) for item in value
        )
    return isinstance(annotation, type) and type(value) is annotation


def _encode(value: object) -> object:
    if isinstance(value, CanonicalObject):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _encode(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def _decode(annotation: object, value: object) -> object:
    origin, arguments = get_origin(annotation), get_args(annotation)
    if origin is UnionType:
        for item in arguments:
            try:
                return _decode(item, value)
            except ValueError:
                pass
        raise ValueError("Value does not match the contract union")
    if origin is tuple:
        if type(value) is not list:
            raise ValueError("Expected an array")
        return tuple(_decode(arguments[0], item) for item in value)
    if annotation is CanonicalObject:
        return CanonicalObject.from_value(value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if type(value) is not str:
            raise ValueError("Expected an enum string")
        return annotation(value)
    if isinstance(annotation, type) and issubclass(annotation, Contract):
        if type(value) is not dict:
            raise ValueError("Expected a record object")
        hints = get_type_hints(annotation)
        assert is_dataclass(annotation)
        if set(value) != {field.name for field in fields(annotation)}:
            raise ValueError("Missing or unknown contract fields; unsupported schema")
        return annotation(
            **{key: _decode(hints[key], item) for key, item in value.items()}
        )
    if not _check(annotation, value):
        raise ValueError("Value has the wrong contract type or schema version")
    return value


class Contract:
    """Frozen dataclass mixin with strict types and explicit wire defaults."""

    def __post_init__(self) -> None:
        hints = get_type_hints(type(self))
        assert is_dataclass(self)
        for field in fields(self):
            if not _check(hints[field.name], getattr(self, field.name)):
                raise ValueError(f"Invalid contract field: {field.name}")
        canonical_json(self.to_dict())
        self._validate()

    def _validate(self) -> None:
        """Additional scientific invariants supplied by concrete records."""

    def to_dict(self) -> dict[str, object]:
        return cast(dict[str, object], _encode(self))

    def to_json(self) -> bytes:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: object) -> Self:
        canonical_json(value)
        return cast(Self, _decode(cls, value))

    @classmethod
    def from_json(cls, data: bytes) -> Self:
        return cls.from_dict(parse_json(data))
