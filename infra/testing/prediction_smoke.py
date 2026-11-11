"""M2 Linux acceptance driver. Only the explicit controlled-child composition."""

import json
import os
import subprocess
import time
import urllib.request
from typing import Any

PROJECT = os.environ.get("NF04_COMPOSE_PROJECT", "neurofold-nf04-m2")
COMPOSE = [
    "docker",
    "compose",
    "-p",
    PROJECT,
    "-f",
    "compose.yaml",
    "-f",
    "compose.prediction-test.yaml",
]
BASE = os.environ.get("NF04_API_URL", "http://127.0.0.1:8000")
FRONT = os.environ.get("NF04_FRONTEND_URL", "http://127.0.0.1:5173")
BODY: dict[str, Any] = {
    "reference_id": "synthetic-variant-reference",
    "variant_id": None,
    "adapter_profile_id": "contract-monomer",
    "parameters": {},
    "seed": 0,
    "msa_artifact_id": None,
    "retry_of_job_id": None,
}


def compose(*args: str, mode: str = "copy") -> None:
    subprocess.run(
        [*COMPOSE, *args],
        env=os.environ | {"CONTROLLED_CHILD": mode},
        check=True,
        timeout=600,
    )


def request(
    path: str, *, body: dict[str, Any] | None = None, key: str | None = None
) -> Any:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Idempotency-Key"] = key
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def submit(key: str) -> str:
    return str(request("/v1/prediction-jobs", body=BODY, key=key)["job"]["job_id"])


def wait(job: str, state: str) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        value: dict[str, Any] = request("/v1/prediction-jobs/" + job)
        if value["job"]["state"] == state:
            return value
        if value["job"]["state"] in ("failed", "succeeded", "cancelled"):
            raise AssertionError(value)
        time.sleep(0.1)
    raise AssertionError("Acceptance job did not reach expected state")


def worker(mode: str) -> None:
    compose(
        "up",
        "--detach",
        "--force-recreate",
        "--no-deps",
        "controlled-worker",
        mode=mode,
    )


def main() -> None:
    # Use unique keys so rerunning this acceptance never rewrites retained history.
    prefix = "acceptance-" + str(time.time_ns())
    assert request("/health") == {"status": "ok"}
    with urllib.request.urlopen(FRONT + "/api/health", timeout=10) as response:
        assert json.load(response) == {"status": "ok"}
    with urllib.request.urlopen(FRONT, timeout=10) as response:
        assert response.status == 200
    # Proxy acceptance is complete; release the Vite process before CPU supervision.
    compose("stop", "frontend")
    compose(
        "exec",
        "-T",
        "backend",
        "python",
        "-c",
        "import os,pathlib; assert os.getuid()!=0; "
        "p=pathlib.Path('/app/data/archive/write-probe'); "
        "p.write_bytes(b'ok'); p.unlink()",
    )
    worker("copy")
    job = submit(prefix + "-success")
    wait(job, "succeeded")
    result = request("/v1/prediction-jobs/" + job + "/result")
    assert result["evidence"] == "synthetic"
    compose("up", "--detach", "--force-recreate", "--no-deps", "--wait", "backend")
    assert submit(prefix + "-success") == job
    assert request("/v1/prediction-jobs/" + job + "/result") == result
    print("PASS retained success/idempotency after backend recreation", flush=True)
    reference = request("/v1/references/" + BODY["reference_id"])
    variant_body = {
        "reference_id": BODY["reference_id"],
        "expected_reference_sha256": reference["protein"]["sequence_hash"]["sha256"],
        "notation": "A4V",
    }
    variant = request("/v1/variants", body=variant_body)
    assert request("/v1/variants", body=variant_body) == variant
    variant_job = request(
        "/v1/prediction-jobs",
        body=BODY | {"variant_id": variant["variant_id"]},
        key=prefix + "-variant",
    )["job"]["job_id"]
    wait(variant_job, "succeeded")
    variant_result = request("/v1/prediction-jobs/" + variant_job + "/result")
    variant_manifest = request("/v1/prediction-jobs/" + variant_job + "/manifest")
    assert variant_manifest["spec"]["variant"]["record_id"] == variant["variant_id"]
    assert (
        variant_result["samples"][0]["mapping"]["sequence_hash"]
        == variant["sequence_hash"]
    )
    compose("up", "--detach", "--force-recreate", "--no-deps", "--wait", "backend")
    assert request("/v1/variants/" + variant["variant_id"]) == variant
    assert request("/v1/prediction-jobs/" + variant_job + "/result") == variant_result
    print(
        "PASS variant POST/GET, publication and retained reference/variant linkage",
        flush=True,
    )
    worker("wait")
    cancel = submit(prefix + "-cancel")
    wait(cancel, "running")
    request("/v1/prediction-jobs/" + cancel + "/cancel", body={})
    assert wait(cancel, "cancelled")["job"]["termination_confirmed"]
    shutdown = submit(prefix + "-shutdown")
    wait(shutdown, "running")
    compose("stop", "controlled-worker")
    assert wait(shutdown, "failed")["operational_failure"] == "SHUTDOWN"
    print("PASS cancellation and graceful worker shutdown", flush=True)
    worker("ignore")
    timeout = submit(prefix + "-timeout")
    assert wait(timeout, "failed")["operational_failure"] == "TIMEOUT"
    loss = submit(prefix + "-loss")
    wait(loss, "running")
    compose("kill", "--signal", "SIGKILL", "controlled-worker")
    # Lease expiry is observable protocol behavior, never used to coordinate races
    # in the storage tests below.
    time.sleep(7)
    worker("copy")
    assert wait(loss, "failed")["operational_failure"] == "WORKER_LOST"
    assert submit(prefix + "-loss") == loss
    print("PASS timeout/forced termination and worker-loss restart", flush=True)
    compose(
        "run",
        "--rm",
        "--no-deps",
        "controlled-worker",
        "pytest",
        "tests/test_prediction_hardening.py",
        "tests/test_prediction_rereview.py",
        "tests/test_prediction_durable.py",
        "tests/test_prediction_worker.py",
        "tests/test_prediction_http.py",
        "--no-cov",
    )
    print(
        "PASS Linux storage races, stale-owner rejection, "
        "abrupt publication and process cleanup",
        flush=True,
    )


if __name__ == "__main__":
    main()
