"""Golden identities and adversarial serialization without scientific packages."""

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from neurofold.core.canonical import (
    MAX_SAFE_INTEGER,
    CanonicalObject,
    canonical_decimal,
    canonical_json,
    canonical_set,
    parse_json,
    sequence_sha256,
    sha256_bytes,
)

FIXTURES = Path(__file__).parent / "fixtures"
VECTORS: list[dict[str, Any]] = json.loads((FIXTURES / "canonical-v1.json").read_text())


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_published_canonical_vectors(vector: dict[str, Any]) -> None:
    encoded = canonical_json(vector["value"])
    assert encoded == vector["canonical"].encode("utf-8")
    assert sha256_bytes(encoded) == vector["sha256"]
    assert canonical_json(parse_json(encoded)) == encoded


def test_key_order_is_irrelevant_but_array_order_and_scalar_types_matter() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})
    assert sha256_bytes(canonical_json([1, 2])) != sha256_bytes(canonical_json([2, 1]))
    assert len({canonical_json(v) for v in (1, True, "1", None, 0, False)}) == 6
    assert canonical_json({"A": 0, "a": 1, "_": 2}) == b'{"A":0,"_":2,"a":1}'


def test_unicode_is_not_normalized_and_bytes_are_utf8() -> None:
    assert canonical_json("é") == b'"\xc3\xa9"'
    assert canonical_json("é") != canonical_json("e\u0301")
    assert canonical_json("/\u2028") == '"/\u2028"'.encode()


@pytest.mark.parametrize(
    "value",
    [
        1.0,
        0.0,
        -0.0,
        float("nan"),
        float("inf"),
        float("-inf"),
        MAX_SAFE_INTEGER + 1,
        -MAX_SAFE_INTEGER - 1,
        {1: "integer key"},
        {"é": "non-ASCII key"},
        {"nested": [1, {"x": 0.5}]},
        {1, 2},
        b"bytes",
        object(),
        "\ud800",
        "\udfff",
    ],
)
def test_unsupported_values_are_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        canonical_json(value)


def test_cycles_fail_but_repeated_acyclic_values_are_allowed() -> None:
    cycle: list[object] = []
    cycle.append(cycle)
    with pytest.raises(ValueError, match="cycles"):
        canonical_json(cycle)
    shared = {"value": 1}
    assert canonical_json([shared, shared]) == b'[{"value":1},{"value":1}]'


@pytest.mark.parametrize(
    "data",
    [
        b'{"a":1,"a":2}',
        b'{"a":1,"\\u0061":2}',
        b'{"nested":[{"x":0,"x":1}]}',
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"1.0",
        b"1e2",
        b"-0.0",
        b'"\\ud800"',
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"{} trailing",
        b'{"a":01}',
        b"{} {}",
    ],
)
def test_strict_json_reader_rejects_ambiguity(data: bytes) -> None:
    with pytest.raises(ValueError):
        parse_json(data)


def test_reader_accepts_whitespace_and_canonicalizes_integer_negative_zero() -> None:
    assert canonical_json(parse_json(b' { "b": -0, "a": true }\n')) == (
        b'{"a":true,"b":0}'
    )


@pytest.mark.parametrize("value", ["0", "1", "-1", "0.001", "-0.125", "123.45"])
def test_canonical_decimal_preserves_exact_setting(value: str) -> None:
    assert canonical_decimal(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "-0",
        "+1",
        "01",
        "00.1",
        "1.0",
        "1.10",
        ".5",
        "1.",
        "1e-3",
        " 1",
        "NaN",
        "１",
    ],
)
def test_noncanonical_decimals_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        canonical_decimal(value)


def test_unordered_collections_require_explicit_schema_opt_in() -> None:
    assert canonical_set(("z", "a", "é")) == ("a", "z", "é")
    assert canonical_set((True, 1)) == (1, True)
    assert canonical_set(()) == ()
    with pytest.raises(ValueError, match="Duplicate"):
        canonical_set(({"a": 1, "b": 2}, {"b": 2, "a": 1}))


def test_canonical_object_is_deeply_immutable() -> None:
    original = {"settings": [1, {"flag": True}]}
    snapshot = CanonicalObject.from_value(original)
    original["settings"].append(2)
    exposed = snapshot.to_dict()
    exposed["settings"] = "mutated"
    assert snapshot.to_dict() == {"settings": [1, {"flag": True}]}
    with pytest.raises(FrozenInstanceError):
        snapshot.data = b"{}"  # type: ignore[misc]  # Exercise frozen runtime guard.


@pytest.mark.parametrize("data", [b"[]", b"null", b'{ "a":1}', b'{"b":2,"a":1}'])
def test_canonical_object_rejects_nonobject_or_noncanonical_bytes(data: bytes) -> None:
    with pytest.raises(ValueError):
        CanonicalObject(data)


def test_canonical_object_rejects_mutable_byte_buffers() -> None:
    with pytest.raises(ValueError):
        CanonicalObject(bytearray(b"{}"))  # type: ignore[arg-type]


def test_hashes_identify_exact_bytes_and_stored_sequence() -> None:
    # Published SHA-256 empty-string and 'abc' vectors, independent of our encoder.
    assert sha256_bytes(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert sha256_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert sequence_sha256("ACDXUO*-?") == sha256_bytes(b"ACDXUO*-?")
    assert sha256_bytes(b"ACD\n") != sequence_sha256("ACD")
    assert sha256_bytes(b"ACD") != sha256_bytes(b"ACE")
    assert sha256_bytes(b'{"a":1, "b":2}') != sha256_bytes(b'{"a":1,"b":2}')


@pytest.mark.parametrize(
    "sequence", ["", "acd", "AC D", "ACD\n", "ACD\r", "ÅCD", ">ACD", "AC\x00D"]
)
def test_sequence_hash_never_silently_normalizes(sequence: str) -> None:
    with pytest.raises(ValueError):
        sequence_sha256(sequence)
