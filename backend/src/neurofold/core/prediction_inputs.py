"""Versioned declarative capabilities and exact immutable prediction inputs."""

from dataclasses import dataclass
from typing import Literal

from neurofold.core.biological import ReferenceSnapshot
from neurofold.core.canonical import MAX_SAFE_INTEGER, sequence_sha256, sha256_bytes
from neurofold.core.prediction_base import (
    PredictionError,
    PredictionRecord,
    SoftwareIdentity,
    domain,
    identifier,
    require,
    unique,
)
from neurofold.core.prediction_base import (
    PredictionErrorCode as E,
)
from neurofold.core.prediction_base import (
    ValidationStage as S,
)
from neurofold.core.provenance import (
    ContentHash,
    ContentReference,
    EvidenceKind,
    HashEncoding,
    Metadata,
    MetadataState,
    _text,
)
from neurofold.core.variants import VariantDefinition, VariantError


@dataclass(frozen=True, kw_only=True)
class InputRecord(PredictionRecord):
    schema_version: Literal["neurofold-prediction/1"] = "neurofold-prediction/1"


@dataclass(frozen=True, kw_only=True)
class ParameterValue(InputRecord):
    name: str
    value: int | bool | str

    def _validate(self) -> None:
        identifier(self.name)


@dataclass(frozen=True, kw_only=True)
class ParameterDefinition(InputRecord):
    name: str
    kind: Literal["integer", "boolean", "choice"]
    default: int | bool | str
    minimum: int | None
    maximum: int | None
    choices: tuple[str, ...]

    def accepts(self, value: object) -> bool:
        if self.kind == "integer":
            assert self.minimum is not None and self.maximum is not None
            return type(value) is int and self.minimum <= value <= self.maximum
        if self.kind == "boolean":
            return type(value) is bool
        return type(value) is str and value in self.choices

    def _validate(self) -> None:
        identifier(self.name)
        unique(self.choices)
        if self.kind == "integer":
            require(self.minimum is not None and self.maximum is not None)
            assert self.minimum is not None and self.maximum is not None
            require(self.minimum <= self.maximum and not self.choices)
        else:
            require(self.minimum is None and self.maximum is None)
            require(bool(self.choices) == (self.kind == "choice"))
        require(self.accepts(self.default))


@dataclass(frozen=True, kw_only=True)
class ParameterRequirement(InputRecord):
    when: ParameterValue
    requires: ParameterValue


@dataclass(frozen=True, kw_only=True)
class ResourceLimits(InputRecord):
    min_residues: int
    max_residues: int
    max_samples: int
    max_seconds: int
    max_memory_bytes: int
    max_output_bytes: int

    def _validate(self) -> None:
        require(1 <= self.min_residues <= self.max_residues)
        require(
            min(
                self.max_samples,
                self.max_seconds,
                self.max_memory_bytes,
                self.max_output_bytes,
            )
            > 0
        )


@dataclass(frozen=True, kw_only=True)
class PredictionProfile(InputRecord):
    adapter: SoftwareIdentity
    profile: SoftwareIdentity
    evidence: EvidenceKind
    availability: Literal["available", "unavailable", "contract_only"]
    availability_reason: str | None
    molecule_types: tuple[Literal["protein"], ...]
    alphabet: str
    parameters: tuple[ParameterDefinition, ...]
    requirements: tuple[ParameterRequirement, ...]
    seed_min: int
    seed_max: int
    limits: ResourceLimits
    msa_modes: tuple[Literal["none", "local", "remote"], ...]
    template_modes: tuple[Literal["none", "local", "remote"], ...]
    constraint_modes: tuple[Literal["none", "local", "remote"], ...]

    def _validate(self) -> None:
        require(self.evidence in (EvidenceKind.SYNTHETIC, EvidenceKind.PREDICTED))
        require(bool(self.molecule_types) and len(set(self.molecule_types)) == 1)
        require(
            bool(self.alphabet)
            and len(set(self.alphabet)) == len(self.alphabet)
            and set(self.alphabet) <= set("ACDEFGHIKLMNPQRSTVWY")
        )
        require(0 <= self.seed_min <= self.seed_max <= MAX_SAFE_INTEGER)
        if self.availability == "available":
            require(self.availability_reason is None)
        else:
            require(self.availability_reason is not None)
            assert self.availability_reason is not None
            _text(self.availability_reason)
        for modes in (self.msa_modes, self.template_modes, self.constraint_modes):
            require(bool(modes) and len(set(modes)) == len(modes))
        names = tuple(item.name for item in self.parameters)
        unique(names)
        require(names == tuple(sorted(names)))
        definitions = {item.name: item for item in self.parameters}
        require("samples" in definitions)
        samples = definitions["samples"]
        require(samples.kind == "integer" and samples.minimum is not None)
        assert samples.minimum is not None and samples.maximum is not None
        require(1 <= samples.minimum <= samples.maximum <= self.limits.max_samples)
        for rule in self.requirements:
            for value in (rule.when, rule.requires):
                require(value.name in definitions)
                require(definitions[value.name].accepts(value.value))
        # A profile cannot advertise incompatible defaults.
        resolve_parameters(self, {})


@dataclass(frozen=True, kw_only=True)
class AdapterCapability(InputRecord):
    adapter_id: str
    adapter_version: Metadata
    availability: Literal["available", "unavailable", "contract_only"]
    reason: str | None
    profiles: tuple[PredictionProfile, ...]

    def _validate(self) -> None:
        identifier(self.adapter_id)
        unique(tuple(item.profile.name for item in self.profiles))
        require((self.availability == "available") == (self.reason is None))
        if self.reason is not None:
            _text(self.reason)
        if self.profiles:
            require(self.adapter_version.state is MetadataState.PRESENT)
            require(type(self.adapter_version.value) is str)
            require(
                all(
                    item.adapter.name == self.adapter_id
                    and item.adapter.version == self.adapter_version.value
                    and item.availability == self.availability
                    for item in self.profiles
                )
            )
        else:
            require(self.availability == "unavailable")


def resolve_parameters(
    profile: PredictionProfile, supplied: object
) -> tuple[ParameterValue, ...]:
    """Resolve defaults, never coerce, then apply typed implications."""
    require(type(profile) is PredictionProfile and type(supplied) is dict)
    assert isinstance(supplied, dict)
    definitions = {item.name: item for item in profile.parameters}
    require(
        all(type(key) is str and key in definitions for key in supplied),
        E.UNSUPPORTED_PARAMETER,
        S.PARAMETERS,
    )
    values: list[ParameterValue] = []
    for name, definition in definitions.items():
        value = supplied.get(name, definition.default)
        require(definition.accepts(value), E.UNSUPPORTED_PARAMETER, S.PARAMETERS)
        assert type(value) in (str, int, bool)
        values.append(ParameterValue(name=name, value=value))
    resolved = {item.name: item.value for item in values}
    for rule in profile.requirements:
        require(
            resolved[rule.when.name] != rule.when.value
            or resolved[rule.requires.name] == rule.requires.value,
            E.UNSUPPORTED_PARAMETER,
            S.PARAMETERS,
        )
    return tuple(values)


@dataclass(frozen=True, kw_only=True)
class AuxiliaryInput(InputRecord):
    mode: Literal["none", "local", "remote"]
    artifacts: tuple[ContentReference, ...]
    reason: str | None
    query_sequence_hash: ContentHash | None
    transformation: str | None

    def _validate(self) -> None:
        unique(tuple(item.record_id for item in self.artifacts))
        for item in self.artifacts:
            domain(item, HashEncoding.RAW)
        if self.mode == "local":
            require(bool(self.artifacts) and self.reason is None)
            require(self.query_sequence_hash is not None)
            assert self.query_sequence_hash is not None
            require(self.query_sequence_hash.encoding is HashEncoding.SEQUENCE)
        else:
            require(not self.artifacts and self.reason is not None)
            assert self.reason is not None
            _text(self.reason)
            require(self.query_sequence_hash is None and self.transformation is None)
        if self.transformation is not None:
            _text(self.transformation)


@dataclass(frozen=True, kw_only=True)
class CodeIdentity(InputRecord):
    revision: str
    dirty: bool
    patch: ContentReference | None

    def _validate(self) -> None:
        identifier(self.revision)
        require(self.dirty == (self.patch is not None))
        if self.patch is not None:
            domain(self.patch, HashEncoding.RAW)


@dataclass(frozen=True, kw_only=True)
class PredictionSpec(InputRecord):
    reference: ContentReference
    reference_sequence_hash: ContentHash
    variant: ContentReference | None
    sequence: str
    sequence_hash: ContentHash
    profile: PredictionProfile
    parameters: tuple[ParameterValue, ...]
    seed: int
    msa: AuxiliaryInput
    templates: AuxiliaryInput
    constraints: AuxiliaryInput
    code: CodeIdentity
    transformations: tuple[str, ...]

    def _validate(self) -> None:
        domain(self.reference, HashEncoding.CANONICAL_JSON)
        require(self.reference_sequence_hash.encoding is HashEncoding.SEQUENCE)
        if self.variant is not None:
            domain(self.variant, HashEncoding.CANONICAL_JSON)
        require(self.sequence_hash.encoding is HashEncoding.SEQUENCE)
        require(self.sequence_hash.sha256 == sequence_sha256(self.sequence))
        names = tuple(item.name for item in self.parameters)
        unique(names)
        supplied = {item.name: item.value for item in self.parameters}
        require(
            self.parameters == resolve_parameters(self.profile, supplied),
            E.UNSUPPORTED_PARAMETER,
            S.PARAMETERS,
        )
        require(
            self.profile.seed_min <= self.seed <= self.profile.seed_max,
            E.UNSUPPORTED_PARAMETER,
            S.PARAMETERS,
        )
        require(
            set(self.sequence) <= set(self.profile.alphabet),
            E.UNSUPPORTED_CAPABILITY,
            S.PROFILE,
        )
        require(
            self.profile.limits.min_residues
            <= len(self.sequence)
            <= self.profile.limits.max_residues,
            E.RESOURCE_LIMIT,
            S.INPUTS,
        )
        for auxiliary, modes in (
            (self.msa, self.profile.msa_modes),
            (self.templates, self.profile.template_modes),
            (self.constraints, self.profile.constraint_modes),
        ):
            require(auxiliary.mode in modes, E.UNSUPPORTED_CAPABILITY, S.PROFILE)
            require(
                auxiliary.query_sequence_hash is None
                or auxiliary.query_sequence_hash == self.sequence_hash,
                E.INCONSISTENT_INPUT,
                S.INPUTS,
            )
        for step in self.transformations:
            _text(step)


def validate_inputs(
    spec: PredictionSpec,
    *,
    reference: ReferenceSnapshot,
    variant: VariantDefinition | None,
    profile: PredictionProfile,
) -> None:
    """Supplied dependencies must have been verified by their owning repositories."""
    require(
        type(spec) is PredictionSpec
        and type(reference) is ReferenceSnapshot
        and (variant is None or type(variant) is VariantDefinition)
        and type(profile) is PredictionProfile
    )
    require(spec.profile == profile, E.UNSUPPORTED_CAPABILITY, S.PROFILE)
    require(
        spec.reference.record_id == reference.reference_id
        and spec.reference.content_hash == reference.content_hash
        and spec.reference_sequence_hash == reference.protein.sequence_hash
        and reference.protein.sequence_hash.sha256
        == sequence_sha256(reference.protein.sequence),
        E.INCONSISTENT_INPUT,
        S.INPUTS,
    )
    sequence = reference.protein.sequence
    if variant is None:
        require(spec.variant is None, E.INCONSISTENT_INPUT, S.INPUTS)
    else:
        try:
            variant.validate_reference(reference)
        except VariantError as exc:
            raise PredictionError(E.INCONSISTENT_INPUT, S.INPUTS) from exc
        require(
            spec.variant
            == ContentReference(
                record_id=variant.variant_id,
                content_hash=ContentHash(
                    sha256=sha256_bytes(variant.to_json()),
                    encoding=HashEncoding.CANONICAL_JSON,
                ),
            ),
            E.INCONSISTENT_INPUT,
            S.INPUTS,
        )
        sequence = variant.sequence
    require(spec.sequence == sequence, E.INCONSISTENT_INPUT, S.INPUTS)


def synthetic_profile() -> PredictionProfile:
    """Authored contract bounds, never measured capacity or executable inference."""
    return PredictionProfile(
        adapter=SoftwareIdentity(name="authored-synthetic", version="1"),
        profile=SoftwareIdentity(name="contract-monomer", version="1"),
        evidence=EvidenceKind.SYNTHETIC,
        availability="contract_only",
        availability_reason="Authored contracts only; no executable adapter exists.",
        molecule_types=("protein",),
        alphabet="ACDEFGHIKLMNPQRSTVWY",
        parameters=(
            ParameterDefinition(
                name="samples",
                kind="integer",
                default=1,
                minimum=1,
                maximum=2,
                choices=(),
            ),
        ),
        requirements=(),
        seed_min=0,
        seed_max=2**32 - 1,
        limits=ResourceLimits(
            min_residues=1,
            max_residues=32,
            max_samples=2,
            max_seconds=10,
            max_memory_bytes=1048576,
            max_output_bytes=4096,
        ),
        msa_modes=("none",),
        template_modes=("none",),
        constraint_modes=("none",),
    )


def capabilities() -> tuple[AdapterCapability, ...]:
    """Static declarations only: no discovery, imports, file reads or providers."""
    profile = synthetic_profile()
    return (
        AdapterCapability(
            adapter_id=profile.adapter.name,
            adapter_version=Metadata(
                state=MetadataState.PRESENT,
                value="1",
                reason=None,
            ),
            availability="contract_only",
            reason=profile.availability_reason,
            profiles=(profile,),
        ),
        AdapterCapability(
            adapter_id="boltz-2",
            adapter_version=Metadata(
                state=MetadataState.UNAVAILABLE,
                value=None,
                reason="No release or weight/license review selected; M4 gate pending.",
            ),
            availability="unavailable",
            reason="Release, weights, licenses and runtime limits unresolved.",
            profiles=(),
        ),
    )
