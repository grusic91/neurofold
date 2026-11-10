"""Immutable local bundles, atomically linked only after complete staging."""

import base64
import io
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from neurofold.core.biological import ReferenceSnapshot
from neurofold.core.canonical import canonical_json, parse_json, sha256_bytes
from neurofold.core.lookup import PinReceipt
from neurofold.core.provenance import ArtifactDescriptor, SourceReceipt

MAX_STORED_BYTES = 16 * 1024 * 1024


class FilesystemStore:
    """Implements ReferenceRepository/SourceArchive; exposes ArtifactStore facade.

    Use a private configured ignored root (e.g. project/data/uniprot). Caller IDs
    are hashed into filenames. Cache eviction never touches this archive.
    """

    def __init__(self, root: Path) -> None:
        root = root.absolute()
        if ".." in root.parts:
            raise ValueError("Storage root cannot contain parent traversal")
        if not {"data", "outputs", ".cache"}.intersection(root.parts):
            raise ValueError(
                "Storage root must be under ignored data/, outputs/ or .cache/"
            )
        if any(parent.is_symlink() for parent in (root, *root.parents)):
            raise ValueError("Symlink storage roots are unsupported")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root

    def _path(self, kind: str, identity: str) -> Path:
        return self.root / f"{kind}-{sha256_bytes(identity.encode('utf-8'))}.json"

    def _read(self, kind: str, identity: str) -> bytes:
        try:
            with self._path(kind, identity).open("rb") as source:
                data = source.read(MAX_STORED_BYTES + 1)
        except FileNotFoundError as exc:
            raise KeyError(identity) from exc
        if len(data) > MAX_STORED_BYTES:
            raise ValueError("Stored record exceeds limit")
        return data

    def _publish(self, kind: str, identity: str, data: bytes) -> None:
        if len(data) > MAX_STORED_BYTES:
            raise ValueError("Stored record exceeds limit")
        target = self._path(kind, identity)
        with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as stage:
            temporary = Path(stage.name)
            try:
                stage.write(data)
                stage.flush()
                os.fsync(stage.fileno())
                try:
                    os.link(
                        temporary, target
                    )  # Atomic, no-clobber even across processes.
                except FileExistsError:
                    if self._read(kind, identity) != data:
                        raise ValueError("Conflicting immutable write") from None
                directory = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary.unlink()

    def _validate_reference(self, snapshot: ReferenceSnapshot) -> None:
        receipt = snapshot.protein.source_receipt
        try:
            if self.get_receipt(receipt.receipt_id) != receipt:
                raise ValueError("Reference receipt integrity failure")
            audit = self.get_pin_receipt(snapshot.reference_id)
        except KeyError as exc:
            raise ValueError("Reference dependency is missing") from exc
        if (
            audit.source_receipt_id != receipt.receipt_id
            or audit.checked_at != snapshot.captured_at
        ):
            raise ValueError("Reference audit integrity failure")

    def publish(self, snapshot: ReferenceSnapshot) -> None:
        self._validate_reference(snapshot)
        self._publish("reference", snapshot.reference_id, snapshot.to_json())

    def get(self, reference_id: str) -> ReferenceSnapshot:
        snapshot = ReferenceSnapshot.from_json(self._read("reference", reference_id))
        if snapshot.reference_id != reference_id:
            raise ValueError("Reference identity mismatch")
        self._validate_reference(snapshot)
        return snapshot

    def publish_receipt(self, receipt: SourceReceipt) -> None:
        if self.describe(receipt.raw_artifact.artifact_id) != receipt.raw_artifact:
            raise ValueError("Receipt artifact mismatch")
        self._publish("receipt", receipt.receipt_id, receipt.to_json())

    def get_receipt(self, receipt_id: str) -> SourceReceipt:
        receipt = SourceReceipt.from_json(self._read("receipt", receipt_id))
        if receipt.receipt_id != receipt_id:
            raise ValueError("Receipt identity mismatch")
        try:
            descriptor = self.describe(receipt.raw_artifact.artifact_id)
        except KeyError as exc:
            raise ValueError("Receipt artifact is missing") from exc
        if descriptor != receipt.raw_artifact:
            raise ValueError("Receipt artifact integrity failure")
        return receipt

    def publish_pin_receipt(self, receipt: PinReceipt) -> None:
        self.get_receipt(receipt.source_receipt_id)
        self._publish("pin", receipt.reference_id, receipt.to_json())

    def get_pin_receipt(self, reference_id: str) -> PinReceipt:
        receipt = PinReceipt.from_json(self._read("pin", reference_id))
        if receipt.reference_id != reference_id:
            raise ValueError("Pin identity mismatch")
        return receipt

    def publish_artifact(
        self, source: BinaryIO, *, descriptor: ArtifactDescriptor
    ) -> None:
        # ArtifactStore.publish and ReferenceRepository.publish share a name.
        # artifact_store provides the existing streaming protocol without overloading.
        if descriptor.byte_size > 8 * 1024 * 1024:
            raise ValueError("Artifact exceeds storage limit")
        chunks: list[bytes] = []
        size = 0
        while size <= descriptor.byte_size:
            chunk = source.read(min(65536, descriptor.byte_size + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        raw = b"".join(chunks)
        if (
            len(raw) != descriptor.byte_size
            or sha256_bytes(raw) != descriptor.content_hash.sha256
        ):
            raise ValueError("Artifact size/checksum mismatch")
        self._publish(
            "artifact",
            descriptor.artifact_id,
            canonical_json(
                {
                    "descriptor": descriptor.to_dict(),
                    "raw": base64.b64encode(raw).decode("ascii"),
                }
            ),
        )

    def _artifact(self, artifact_id: str) -> tuple[ArtifactDescriptor, bytes]:
        value = parse_json(self._read("artifact", artifact_id))
        if not isinstance(value, dict) or set(value) != {"descriptor", "raw"}:
            raise ValueError("Invalid stored artifact bundle")
        descriptor = ArtifactDescriptor.from_dict(value["descriptor"])
        encoded = value["raw"]
        if not isinstance(encoded, str):
            raise ValueError("Invalid artifact encoding")
        raw = base64.b64decode(encoded, validate=True)
        if (
            descriptor.artifact_id != artifact_id
            or len(raw) != descriptor.byte_size
            or sha256_bytes(raw) != descriptor.content_hash.sha256
        ):
            raise ValueError("Artifact integrity failure")
        return descriptor, raw

    def describe(self, artifact_id: str) -> ArtifactDescriptor:
        return self._artifact(artifact_id)[0]

    def open(self, artifact_id: str) -> BinaryIO:
        return io.BytesIO(self._artifact(artifact_id)[1])

    @property
    def artifact_store(self) -> "FilesystemArtifacts":
        return FilesystemArtifacts(self)


class FilesystemArtifacts:
    def __init__(self, store: FilesystemStore) -> None:
        self.store = store

    def describe(self, artifact_id: str) -> ArtifactDescriptor:
        return self.store.describe(artifact_id)

    def open(self, artifact_id: str) -> BinaryIO:
        return self.store.open(artifact_id)

    def publish(self, source: BinaryIO, *, descriptor: ArtifactDescriptor) -> None:
        self.store.publish_artifact(source, descriptor=descriptor)
