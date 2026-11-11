"""Synthetic proposal copier with same-group EOF helpers; no inference."""

import os
import subprocess
import sys
from pathlib import Path


def main(directory: Path) -> None:
    reader, writer = os.pipe()
    helpers = [subprocess.Popen(["/bin/sh", "-c", "read token"], stdin=reader)]
    os.close(reader)
    (directory / "bundle.json").write_bytes((directory / "proposal.json").read_bytes())
    with (directory / "go.fifo").open("rb", buffering=0) as gate:
        gate.read(1)
    # Keep writer and Popen alive until leader exit, making the helper exit on EOF.
    assert writer >= 0 and helpers


if __name__ == "__main__":
    main(Path(sys.argv[1]))
