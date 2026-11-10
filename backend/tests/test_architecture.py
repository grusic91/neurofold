"""Keep prediction contracts usable without installed third-party packages."""

import subprocess
import sys
from pathlib import Path

from neurofold.core import prediction


def test_all_core_contracts_import_with_only_standard_library() -> None:
    source_root = Path(prediction.__file__).resolve().parents[2]
    # -I ignores user configuration; -S removes all site-packages, including
    # FastAPI and any potential model runtime. Only the source tree is added.
    script = (
        f"import sys; sys.path.insert(0, {str(source_root)!r}); "
        "import pkgutil, neurofold.core; "
        "[__import__(module.name) for module in "
        "pkgutil.walk_packages(neurofold.core.__path__, 'neurofold.core.')]"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
