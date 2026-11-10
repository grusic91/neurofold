# Operational compatibility checks

These checks exercise deployment and provider compatibility. They do not establish
biological accuracy or satisfy the [independent scientific gates](scientific-review.md).
The [2026-11-10 evidence](nf02-operational-evidence.md) records the executed scope.
Ordinary pytest/browser tests remain synthetic and offline.

## Locked Linux checks

From the repository root with a Linux Docker daemon, build the disposable runner:

```sh
docker build -f infra/docker/checks.Dockerfile -t neurofold-checks:local .
mkdir -p outputs/linux-checks
git ls-files --cached --others --exclude-standard -z |
  tar --null -T - -cf outputs/linux-checks/source.tar
docker run --rm --shm-size=1g \
  --mount type=bind,source="$PWD/outputs/linux-checks/source.tar",target=/input/source.tar,readonly \
  neurofold-checks:local python312
docker run --rm --shm-size=1g \
  --mount type=bind,source="$PWD/outputs/linux-checks/source.tar",target=/input/source.tar,readonly \
  neurofold-checks:local python313
docker run --rm --shm-size=1g \
  --mount type=bind,source="$PWD/outputs/linux-checks/source.tar",target=/input/source.tar,readonly \
  neurofold-checks:local frontend
```

The archive includes authored CIF fixtures, excludes ignored local artifacts, and
is extracted into a disposable container filesystem. Review untracked files before
packing; do not include private inputs or environment files. The runner uses uv
0.13.7, installs Python 3.12/3.13 and locked dependencies, and installs lockfile-pinned
Chromium with Linux system libraries. Frontend mode includes component, mocked
browser and actual local synthetic API/proxy tests. Installation requires network;
behavior tests prohibit provider traffic. Record resolved runtime/image versions;
base tags and Python patch selection are not immutable. CI independently runs
the same checks on Ubuntu runners; local Linux execution is not a GitHub CI result.

## Container execution and retention

Follow [the integration smoke procedure](../integration.md) for normal health/proxy
checks, the separate synthetic Compose override, and retained reads after forced
backend recreation. `infra/testing/smoke.py --help` documents `--base-url` for an
isolated project's proxy port. Use a distinct Compose project/ports so existing
archives are untouched. Capture container/image IDs and volume permissions.
Normal `down` retains the archive; never use `down --volumes` when retaining evidence.

## Explicit live probe

After `uv sync --locked` in `backend/`, run this only when public provider access
is intended, choosing a new ignored output directory for every attempt:

```sh
uv run --locked python scripts/live_probe.py --enable-live \
  --output "$PWD/../outputs/live-probe-YYYYMMDD-attempt01" \
  --accession P69905 --taxon 9606 --entry 1A3N \
  --entity 1 --chain A --model 1 --asymmetric-unit
```

This small public pair is a technical compatibility sample, not a disease panel.
The target is predeclared rather than chosen from the first discovery result.
The probe exercises production routes/services via ASGI, production bounded HTTPX,
one discovery page, fresh explicit target inspection, sequence-hash pinning,
revision-bound import, receipt/audit inspection, exact original download, mapping
denominators and reopening with provider access forbidden. It does not run a live
browser or prove live-provider connectivity from inside the development containers.
The transport budget is 32 requests/300 seconds in addition to provider limits.
The probe never automatically retries mutations.

`report.json` records exact inputs, times, code revision/diff/probe hashes, lock
identities, package/runtime versions, outcomes and limits. `api/` retains requests
and response metadata/bodies; `transport/` retains original provider entity bytes
and headers, including failures. `archive/` retains published immutable records;
`inventory.json` hashes all attempt files except itself. Retain the corresponding
source snapshot and its per-file hashes alongside reports to identify uncommitted
and untracked implementation. Do not copy these real records into fixtures or git.
Restrict local access, retain provider rights/attribution, and review source terms
before redistributing any artifact.

On failure, preserve the attempt and diagnose from retained responses. Author a
small synthetic offline regression, record its failure before editing production
code, then verify it passes with the correction. Use a new attempt directory for
the next live run. Do not weaken identity/revision checks or substitute another
target merely to obtain a passing result. Broader providers, record types,
assemblies, architectures and scientific interpretation need separate evidence.
