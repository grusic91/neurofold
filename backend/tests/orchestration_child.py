"""Controlled test child: copy authored bytes or wait; no prediction algorithm."""

import json
import os
import signal
import socket
import sys
from pathlib import Path
from typing import NoReturn


def denied(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError("Network is disabled in controlled children")


for name in (
    "socket",
    "getaddrinfo",
    "gethostbyname",
    "gethostbyname_ex",
    "gethostbyaddr",
):
    setattr(socket, name, denied)


def main(directory: Path) -> None:
    control = json.loads((directory / "control.json").read_bytes())
    (directory / "pid").write_text(str(os.getpid()))
    if control["mode"] == "ignore":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    liveness = directory.parent / "liveness.fifo"
    if liveness.exists():
        # Test observer receives EOF only when the orphan child actually exits.
        os.open(liveness, os.O_WRONLY)
    with (directory / "ready.fifo").open("wb", buffering=0) as ready:
        ready.write(b"ready")
    if control["mode"] in ("wait", "ignore"):
        while True:
            signal.pause()
    if control["mode"] == "crash":
        raise SystemExit(7)
    if control["mode"] == "missing":
        return
    if control["mode"] == "malformed":
        (directory / "bundle.json").write_bytes(b'{"bad":true}')
    elif control["mode"] == "oversized":
        with (directory / "bundle.json").open("wb") as output:
            output.write(b"x" * (16 * 1024 * 1024 + 1))
    else:
        (directory / "bundle.json").write_bytes(
            (directory / "proposal.json").read_bytes()
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
