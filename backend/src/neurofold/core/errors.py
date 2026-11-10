"""Typed integration failures; no HTTP or filesystem implementation dependency."""

from neurofold.core.structures import UnsupportedStructure


class ArchiveIntegrityError(ValueError):
    """Known retained data is damaged or a required dependency is missing."""


class ArchiveConflict(ValueError):
    """An immutable identifier is already bound to different bytes."""


class ResourceLimit(UnsupportedStructure):
    """A bounded local input/work profile was exceeded."""
