"""Explicit affine scoring and consensus across every bounded optimal path."""

from importlib.metadata import version as package_version
from itertools import islice

from neurofold.adapters.biological.uniprot import absent, present
from neurofold.core.biological import (
    MappingIdentity,
    MappingStatus,
    ReferenceSnapshot,
    ResidueMap,
    ResidueMapRow,
    StructureSelection,
)
from neurofold.core.canonical import CanonicalObject, sequence_sha256
from neurofold.core.provenance import ContentReference
from neurofold.core.structures import (
    ParsedStructure,
    StructureDownload,
    UnsupportedStructure,
)


class PolymerMapper:
    def __init__(self, *, max_cells: int = 4_000_000, max_paths: int = 256) -> None:
        if not 1 <= max_cells <= 4_000_000 or not 1 <= max_paths <= 256:
            raise ValueError("Alignment limits exceed profile")
        self.max_cells, self.max_paths = max_cells, max_paths

    def map(
        self,
        reference: ReferenceSnapshot,
        structure_id: str,
        download: StructureDownload,
        selection: StructureSelection,
        parsed: ParsedStructure,
    ) -> tuple[ResidueMap, CanonicalObject]:
        import Bio
        from Bio.Align import PairwiseAligner

        target, query = reference.protein.sequence, parsed.sequence
        sequence_sha256(query)
        if (
            not query
            or max(len(target), len(query)) > 10000
            or len(target) * len(query) > self.max_cells
        ):
            raise UnsupportedStructure("Alignment sequence/cell limit exceeded")
        if len(parsed.residues) != len(query) or any(
            r.label_seq_id != i or r.residue != query[i - 1]
            for i, r in enumerate(parsed.residues, 1)
        ):
            raise ValueError("Parsed polymer identities are incomplete")
        aligner = PairwiseAligner(  # type: ignore[no-untyped-call]
            mode="global",
            match_score=2,
            mismatch_score=-1,
            open_gap_score=-10,
            extend_gap_score=-0.5,
        )
        aligner.open_left_deletion_score = 0
        aligner.extend_left_deletion_score = 0
        aligner.open_right_deletion_score = 0
        aligner.extend_right_deletion_score = 0
        aligner.epsilon = 1e-6
        candidates: list[set[int | None]] = [set() for _ in query]
        count = 0
        score = ""
        paths = aligner.align(target, query)  # type: ignore[no-untyped-call]
        for path in islice(paths, self.max_paths + 1):
            count += 1
            if count > self.max_paths:
                raise UnsupportedStructure(
                    "Too many optimal alignments; ambiguity exceeds bounded profile"
                )
            score = str(path.score)
            coordinates = path.coordinates
            assigned: dict[int, int] = {}
            for column in range(coordinates.shape[1] - 1):
                r0, r1 = int(coordinates[0, column]), int(coordinates[0, column + 1])
                p0, p1 = int(coordinates[1, column]), int(coordinates[1, column + 1])
                if r1 > r0 and p1 > p0:
                    if r1 - r0 != p1 - p0:
                        raise ValueError("Unsupported alignment block")
                    assigned.update(
                        {p0 + offset: r0 + offset + 1 for offset in range(p1 - p0)}
                    )
            for index, values in enumerate(candidates):
                values.add(assigned.get(index))
        identity = MappingIdentity(
            reference=ContentReference(
                record_id=reference.reference_id,
                content_hash=reference.protein.sequence_hash,
            ),
            structure=ContentReference(
                record_id=structure_id,
                content_hash=download.receipt.raw_artifact.content_hash,
            ),
            selection=selection,
        )
        rows: list[ResidueMapRow] = []
        unique_reference: set[int] = set()
        ambiguous_positions: set[int] = set()
        unique_count = coordinate_count = identity_count = 0
        for residue, values in zip(parsed.residues, candidates, strict=True):
            positions = tuple(sorted(v for v in values if v is not None))
            unique = len(values) == 1 and len(positions) == 1 and not residue.uncertain
            position = positions[0] if unique else None
            reference_residue = target[position - 1] if position else None
            if unique:
                assert position is not None
                unique_reference.add(position)
                unique_count += 1
                coordinate_count += residue.coordinate_present
                identity_count += reference_residue == residue.residue
                if reference_residue != residue.residue:
                    status, reason = (
                        MappingStatus.MISMATCH,
                        "Construct substitution; coordinate presence is independent",
                    )
                elif residue.coordinate_present:
                    status, reason = MappingStatus.EXACT, None
                else:
                    status, reason = (
                        MappingStatus.UNOBSERVED,
                        (
                            "Polymer residue has no positive-occupancy "
                            "coordinates in selected model"
                        ),
                    )
            elif residue.uncertain or positions:
                status = MappingStatus.AMBIGUOUS
                reason = (
                    "Unknown/modified component lacks an unambiguous standard parent"
                    if residue.uncertain
                    else "Optimal alignment paths disagree"
                    + (" including a gap alternative" if None in values else "")
                )
                ambiguous_positions.update(positions)
            else:
                status, reason = (
                    MappingStatus.UNMAPPED,
                    "Polymer insertion/tag outside reference alignment",
                )
            rows.append(
                ResidueMapRow(
                    identity=identity,
                    reference_position=present(position)
                    if position
                    else absent("No unique reference assignment"),
                    reference_residue=present(reference_residue)
                    if reference_residue
                    else absent("No unique reference residue"),
                    label_seq_id=present(residue.label_seq_id),
                    auth_seq_id=residue.auth_seq_id,
                    insertion_code=residue.insertion_code,
                    observed_residue=present(residue.residue),
                    coordinate_present=residue.coordinate_present,
                    status=status,
                    reason=reason,
                    candidate_reference_positions=positions
                    if status is MappingStatus.AMBIGUOUS
                    else (),
                )
            )
        for position, residue_code in enumerate(target, 1):
            if position in unique_reference:
                continue
            rows.append(
                ResidueMapRow(
                    identity=identity,
                    reference_position=present(position),
                    reference_residue=present(residue_code),
                    label_seq_id=absent(
                        "No uniquely assigned polymer position", na=True
                    ),
                    auth_seq_id=absent("No assigned polymer residue", na=True),
                    insertion_code=absent("No assigned polymer residue", na=True),
                    observed_residue=absent("No assigned polymer residue", na=True),
                    coordinate_present=False,
                    status=MappingStatus.UNMAPPED,
                    reason="Possible coverage only through ambiguous polymer mapping"
                    if position in ambiguous_positions
                    else (
                        "Reference position absent from every optimal "
                        "construct alignment"
                    ),
                    candidate_reference_positions=(),
                )
            )
        mapping = ResidueMap(
            mapping_id=structure_id + ":map",
            identity=identity,
            reference_length=len(target),
            method="affine-semiglobal-consensus/1",
            method_version="biopython/" + Bio.__version__,
            rows=tuple(rows),
        )
        return mapping, CanonicalObject.from_value(
            {
                "library": "biopython",
                "numpy_version": package_version("numpy"),
                "limits": {"cells": self.max_cells, "optimal_paths": self.max_paths},
                "version": Bio.__version__,
                "profile": "affine-semiglobal-consensus/1",
                "match": "2",
                "mismatch": "-1",
                "gap_open": "-10",
                "gap_extend": "-0.5",
                "epsilon": "0.000001",
                "free_ends": "reference terminal overhangs only",
                "score": score,
                "optimal_path_count": count,
                "reference_coverage": {
                    "numerator": unique_count,
                    "denominator": len(target),
                },
                "polymer_coverage": {
                    "numerator": unique_count,
                    "denominator": len(query),
                },
                "coordinate_reference_coverage": {
                    "numerator": coordinate_count,
                    "denominator": len(target),
                },
                "unique_aligned_pair_identity": {
                    "numerator": identity_count,
                    "denominator": unique_count,
                },
                "unknown_components": "X never establishes unique correspondence",
            }
        )
