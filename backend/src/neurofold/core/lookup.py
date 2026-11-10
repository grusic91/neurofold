"""Additive M2 seams; frozen biological/research v1 identities are unchanged."""

from dataclasses import dataclass
from typing import Literal, Protocol

from neurofold.core._contracts import Contract
from neurofold.core.biological import ProteinRecord
from neurofold.core.canonical import CanonicalObject
from neurofold.core.provenance import SourceReceipt, _text, _utc


class ProviderError(RuntimeError):
    """Upstream unavailable or invalid; never an empty catalog result."""


class ProviderValidationError(ProviderError):
    """Malformed, inconsistent, redirected or oversized upstream content."""


class UnsupportedIdentifier(ValueError):
    """An isoform or obsolete/redirected identity needs explicit selection."""


class CursorError(ValueError):
    restart_hint = "Restart search without a cursor."

    def __init__(self, reason: str) -> None:
        super().__init__(f"{reason}. {self.restart_hint}")


class SourceChanged(ValueError):
    """Typed conflict for future HTTP 409 translation."""

    def __init__(self, expected: str, actual: str) -> None:
        self.expected, self.actual = expected, actual
        super().__init__(
            "Source sequence changed; inspect the current entry and retry."
        )


@dataclass(frozen=True)
class FreshProtein:
    protein: ProteinRecord
    checked_at: str
    response_status: Literal[200, 304]
    response_headers: CanonicalObject
    adapter_version: str


class FreshProteinCatalog(Protocol):
    def get_fresh(self, accession: str) -> FreshProtein: ...


@dataclass(frozen=True, kw_only=True)
class PinReceipt(Contract):
    """304 checks reference original bytes, never pretend to be full retrievals."""

    reference_id: str
    source_receipt_id: str
    checked_at: str
    response_status: Literal[200, 304]
    response_headers: CanonicalObject
    adapter_version: str
    schema_version: Literal["neurofold-reference-pin/1"] = "neurofold-reference-pin/1"

    def _validate(self) -> None:
        _text(self.reference_id)
        _text(self.source_receipt_id)
        _text(self.adapter_version)
        _utc(self.checked_at)


class SourceArchive(Protocol):
    def publish_receipt(self, receipt: SourceReceipt) -> None: ...

    def publish_pin_receipt(self, receipt: PinReceipt) -> None: ...
