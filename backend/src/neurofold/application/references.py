"""Explicit canonical selection and authoritative fresh reference pinning."""

from collections.abc import Callable
from uuid import uuid4

from neurofold.core.biological import (
    ReferenceRepository,
    ReferenceSnapshot,
    validate_accession,
)
from neurofold.core.lookup import (
    FreshProteinCatalog,
    PinReceipt,
    SourceArchive,
    SourceChanged,
    UnsupportedIdentifier,
)
from neurofold.core.provenance import ContentHash, HashEncoding


class ReferenceService:
    def __init__(
        self,
        catalog: FreshProteinCatalog,
        repository: ReferenceRepository,
        archive: SourceArchive,
        *,
        new_id: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self.catalog, self.repository, self.archive = catalog, repository, archive
        self.new_id = new_id

    def pin(self, accession: str, expected_sequence_sha256: str) -> ReferenceSnapshot:
        validate_accession(accession)
        if "-" in accession:
            raise UnsupportedIdentifier(
                "Isoform references are unsupported; select explicitly"
            )
        expected = ContentHash(
            sha256=expected_sequence_sha256, encoding=HashEncoding.SEQUENCE
        )
        fresh = self.catalog.get_fresh(accession)
        if fresh.protein.summary.accession != accession:
            raise UnsupportedIdentifier("Catalog returned a different accession")
        if fresh.protein.sequence_hash != expected:
            raise SourceChanged(expected.sha256, fresh.protein.sequence_hash.sha256)
        snapshot = ReferenceSnapshot(
            reference_id=self.new_id(),
            protein=fresh.protein,
            captured_at=fresh.checked_at,
        )
        # Dependencies are durable before publication. A failed snapshot write can
        # leave an orphan receipt, but never a readable snapshot missing its audit.
        self.archive.publish_pin_receipt(
            PinReceipt(
                reference_id=snapshot.reference_id,
                source_receipt_id=fresh.protein.source_receipt.receipt_id,
                checked_at=fresh.checked_at,
                response_status=fresh.response_status,
                response_headers=fresh.response_headers,
                adapter_version=fresh.adapter_version,
            )
        )
        self.repository.publish(snapshot)
        return snapshot

    def get(self, reference_id: str) -> ReferenceSnapshot:
        return self.repository.get(reference_id)
