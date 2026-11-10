"""NeuroFold canonical JSON v1 and distinct scientific byte identities.

This is deliberately not RFC 8785. No implicit biological, Unicode, decimal,
collection-order, or default normalization takes place here.
"""

import hashlib
import json
import re
from dataclasses import dataclass

CANONICALIZATION_VERSION = "neurofold-json/1"
MAX_SAFE_INTEGER = 2**53 - 1


def _json_value(value: object, ancestors: frozenset[int] = frozenset()) -> object:
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if abs(value) > MAX_SAFE_INTEGER:
            raise ValueError("Integers outside the safe range must be strings")
        return value
    if type(value) is str:
        value.encode("utf-8", errors="strict")  # Reject lone Unicode surrogates.
        return value
    if type(value) not in (dict, list, tuple):
        raise ValueError("Canonical JSON accepts no floats or implicit conversions")
    if id(value) in ancestors:
        raise ValueError("Canonical JSON cannot contain cycles")
    ancestors = ancestors | {id(value)}
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str or not key.isascii():
                raise ValueError("Schema keys must be ASCII strings")
            result[key] = _json_value(item, ancestors)
        return result
    assert isinstance(value, (list, tuple))
    return [_json_value(item, ancestors) for item in value]


def canonical_json(value: object) -> bytes:
    """Serialize supported values to exact UTF-8 bytes, with sorted ASCII keys."""
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def parse_json(data: bytes) -> object:
    """Read strict UTF-8 JSON; reject duplicates and noncanonical value types.

    Whitespace and object key order may differ on input. Hashing a raw artifact
    still uses the original bytes, never this parsed representation.
    """
    value: object = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    canonical_json(value)
    return value


def canonical_decimal(value: str) -> str:
    """Validate an exact decimal setting; do not round or reformat user input."""
    if not re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?", value) or value == "-0":
        raise ValueError("Expected a canonical decimal without exponent/trailing zeros")
    return value


def sha256_bytes(data: bytes) -> str:
    """Hash original bytes without normalization (also valid for empty files)."""
    return hashlib.sha256(data).hexdigest()


def sequence_sha256(sequence: str) -> str:
    """Hash an exact stored uppercase ASCII sequence, never FASTA or whitespace.

    Printable nonletter symbols are preserved, allowing an NF-02 snapshot to
    remain inspectable even when NF-03/04 reject its biological alphabet.
    """
    if (
        not sequence
        or not sequence.isascii()
        or not sequence.isprintable()
        or any(character.isspace() for character in sequence)
        or sequence != sequence.upper()
    ):
        raise ValueError("Expected a nonempty uppercase single-line ASCII sequence")
    if sequence.startswith(">"):
        raise ValueError("A FASTA header is not a stored sequence")
    return sha256_bytes(sequence.encode("ascii"))


def canonical_set(values: tuple[object, ...]) -> tuple[object, ...]:
    """Explicit schema opt-in for unordered sets, ordered by canonical UTF-8 bytes.

    Ordered scientific selections must not call this helper. Duplicate members
    are errors rather than silently removed data.
    """
    keyed = sorted((canonical_json(value), index) for index, value in enumerate(values))
    if len({key for key, _ in keyed}) != len(keyed):
        raise ValueError("Duplicate unordered collection member")
    return tuple(values[index] for _, index in keyed)


@dataclass(frozen=True)
class CanonicalObject:
    """Deeply immutable object snapshot; exposed decoded values are fresh copies."""

    data: bytes

    def __post_init__(self) -> None:
        if type(self.data) is not bytes:
            raise ValueError("CanonicalObject requires immutable bytes")
        value = parse_json(self.data)
        if not isinstance(value, dict) or canonical_json(value) != self.data:
            raise ValueError("Expected canonical object bytes")

    @classmethod
    def from_value(cls, value: object) -> "CanonicalObject":
        return cls(canonical_json(value))

    def to_dict(self) -> dict[str, object]:
        value = parse_json(self.data)
        assert isinstance(value, dict)
        return value
