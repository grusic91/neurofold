"""Static coverage of authored integrity messages, without importing adapters."""

import ast
from pathlib import Path

from neurofold.application.prediction_worker import _AUTHORED_INTEGRITY_MESSAGES


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def test_integrity_message_literals_are_allowlisted_or_explicitly_excluded() -> None:
    sources = [
        ast.parse(path.read_text())
        for path in (Path(__file__).resolve().parents[1] / "src").rglob("*.py")
    ]
    classes = {"ArchiveIntegrityError"}
    while True:
        derived = {
            node.name
            for source in sources
            for node in ast.walk(source)
            if isinstance(node, ast.ClassDef)
            and any(_name(base) in classes for base in node.bases)
        }
        if derived <= classes:
            break
        classes |= derived
    messages: set[str] = set()
    for source in sources:
        names = classes | {
            alias.asname or alias.name
            for node in ast.walk(source)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if alias.name in classes
        }
        for node in ast.walk(source):
            if (
                isinstance(node, ast.Call)
                and _name(node.func) in names
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                messages.add(node.args[0].value)
    excluded = {
        "Uninventoried staged output": "Child rejection, not queue damage.",
        "Child proposal ownership mismatch": "Child rejection, not queue damage.",
        "Child output linkage mismatch": "Child rejection, not queue damage.",
    }
    assert messages
    assert set(excluded) <= messages, "Remove stale diagnostic exclusions"
    assert all(excluded.values())
    missing = {
        message
        for message in messages
        if message not in _AUTHORED_INTEGRITY_MESSAGES and message not in excluded
    }
    assert not missing, (
        f"Authored integrity messages need a disposition: {sorted(missing)}"
    )
