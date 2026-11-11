"""Typed integration failures; no HTTP or filesystem implementation dependency."""

from neurofold.core.structures import UnsupportedStructure


class ArchiveIntegrityError(ValueError):
    """Known retained data is damaged or a required dependency is missing."""


class InvalidChildOutput(ArchiveIntegrityError):
    """An unregistered child proposal violates its output/ownership contract."""


class ArchiveConflict(ValueError):
    """An immutable identifier is already bound to different bytes."""


class ArchivePublicationError(OSError):
    """Publication I/O failed; reopen to determine if a complete record exists.

    A failure after the atomic link (e.g. directory fsync) may leave a complete
    visible record. Never retry by overwriting or deleting that record.
    """


class ResourceLimit(UnsupportedStructure):
    """A bounded local input/work profile was exceeded."""
