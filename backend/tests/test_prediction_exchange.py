"""Frozen additive exchange shapes plus strict direct/codec validation."""

import json
import subprocess
import sys
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import Any, get_type_hints

import jsonschema
import pytest
from prediction_examples import example
from test_prediction_inputs import extended_profile
from test_prediction_jobs import state_record
from test_prediction_outputs import predicted_example

from neurofold.core.prediction_base import PredictionError, PredictionRecord
from neurofold.core.prediction_inputs import capabilities

ROOT = Path(__file__).resolve().parents[2]


def records() -> dict[str, PredictionRecord]:
    found: dict[str, PredictionRecord] = {}

    def visit(value: object) -> None:
        if isinstance(value, PredictionRecord):
            found[type(value).__name__] = value
            assert is_dataclass(value)
            for field in fields(value):
                visit(getattr(value, field.name))
        elif isinstance(value, tuple):
            for item in value:
                visit(item)

    e = example()
    for value in (
        e.job,
        e.result,
        e.manifest,
        capabilities(),
        extended_profile(),
        state_record("failed"),
        predicted_example().manifest,
    ):
        visit(value)
    return found


RECORDS = records()
MISSING = [
    (name, field) for name, record in RECORDS.items() for field in record.to_dict()
]


@pytest.mark.parametrize("name", list(RECORDS))
def test_strict_roundtrip_and_schema_agree(name: str) -> None:
    record = RECORDS[name]
    assert type(record).from_json(record.to_json()) == record
    assert type(record).from_dict(record.to_dict()) == record
    version = record.to_dict().get("schema_version")
    if version is None:  # SoftwareIdentity is a typed value, not an exchange root.
        return
    family = str(version).replace("neurofold-", "").replace("/1", "")
    schema: dict[str, Any] = json.loads(
        (ROOT / f"docs/schemas/neurofold-{family}-1.schema.json").read_bytes()
    )
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(record.to_dict(), schema)


@pytest.mark.parametrize("name,field", MISSING)
def test_every_field_is_required_in_codec_and_schema(name: str, field: str) -> None:
    record = RECORDS[name]
    data = record.to_dict()
    data.pop(field)
    with pytest.raises(PredictionError):
        type(record).from_dict(data)
    version = record.to_dict().get("schema_version")
    if version is not None:
        family = str(version).replace("neurofold-", "").replace("/1", "")
        schema: dict[str, Any] = json.loads(
            (ROOT / f"docs/schemas/neurofold-{family}-1.schema.json").read_bytes()
        )
        # Use the exact root definition: support records may share other shapes.
        schema["anyOf"] = [{"$ref": f"#/$defs/{name}"}]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(data, schema)


@pytest.mark.parametrize("name", list(RECORDS))
def test_unknown_fields_versions_and_direct_types(name: str) -> None:
    record = RECORDS[name]
    data = record.to_dict() | {"unexpected": "sensitive text"}
    with pytest.raises(PredictionError):
        type(record).from_dict(data)
    if "schema_version" in record.to_dict():
        with pytest.raises(PredictionError):
            type(record).from_dict(
                record.to_dict() | {"schema_version": "unsupported/99"}
            )
    assert is_dataclass(record)
    first = fields(record)[0]
    with pytest.raises(PredictionError):
        replace(record, **{first.name: {"raw": "SECRET"}})


INT_FIELDS = [
    (name, field)
    for name, record in RECORDS.items()
    for field in record.to_dict()
    if get_type_hints(type(record))[field] is int
]


@pytest.mark.parametrize("name,field", INT_FIELDS)
@pytest.mark.parametrize("bad", [True, 1.0, "1", 2**53])
def test_all_integer_fields_reject_coercion_and_unsafe_values(
    name: str, field: str, bad: object
) -> None:
    with pytest.raises(PredictionError):
        type(RECORDS[name]).from_dict(RECORDS[name].to_dict() | {field: bad})


def test_schema_generator_is_reproducible_and_part_of_strict_checkpoint() -> None:
    paths = [
        ROOT / "docs/schemas" / f"neurofold-{family}-1.schema.json"
        for family in (
            "prediction",
            "prediction-job",
            "prediction-result",
            "prediction-provenance",
        )
    ]
    assert len(paths) == 4
    before = {path: path.read_bytes() for path in paths}
    result = subprocess.run(
        [sys.executable, str(ROOT / "backend/scripts/prediction_schema.py")],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert before == {path: path.read_bytes() for path in paths}


def test_frozen_exchange_examples_match_authoritative_records() -> None:
    fixture: dict[str, Any] = json.loads(
        (Path(__file__).parent / "fixtures/prediction-v1.json").read_bytes()
    )
    e = example()
    assert fixture["job"] == e.job.to_dict()
    assert fixture["result"] == e.result.to_dict()
    assert fixture["manifest"] == e.manifest.to_dict()
    assert fixture["capabilities"] == [item.to_dict() for item in capabilities()]
