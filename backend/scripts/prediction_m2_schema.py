"""Additive child/status exchange schemas; preserve every M1 schema byte."""

import json
from pathlib import Path

from neurofold.core.prediction_bundle import ChildBundle
from neurofold.core.prediction_failure import OperationalFailure
from neurofold.core.prediction_jobs import PredictionJob
from scripts.prediction_schema import schema_for


def schemas() -> dict[str, dict[str, object]]:
    child = schema_for((ChildBundle,), "child-proposal")
    status = schema_for((PredictionJob,), "prediction-status")
    status.pop("anyOf")
    status.update(
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "job", "operational_failure"],
            "properties": {
                "schema_version": {"const": "neurofold-prediction-status/1"},
                "job": {"$ref": "#/$defs/PredictionJob"},
                "operational_failure": {
                    "enum": [
                        None,
                        "WORKER_LOST",
                        "TIMEOUT",
                        "SHUTDOWN",
                        "CHILD_FAILED",
                        "INVALID_OUTPUT",
                        "PUBLICATION_FAILED",
                        "SUPERVISION_FAILED",
                    ]
                },
            },
        }
    )
    return {
        "child-proposal": child,
        "prediction-status": status,
        "prediction-failure": schema_for((OperationalFailure,), "prediction-failure"),
    }


def main() -> None:
    destination = Path(__file__).resolve().parents[2] / "docs/schemas"
    for family, schema in schemas().items():
        (destination / f"neurofold-{family}-1.schema.json").write_text(
            json.dumps(schema, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
