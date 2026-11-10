"""Bounded Gemmi category parsing without hierarchy normalization or atom loss."""

import itertools
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from importlib.metadata import version as package_version
from typing import TYPE_CHECKING

from neurofold.adapters.biological.rcsb import METHODS
from neurofold.adapters.biological.transport import MAX_EXPANDED
from neurofold.adapters.biological.uniprot import absent, present
from neurofold.core.biological import ExperimentalStructureSummary, StructureSelection
from neurofold.core.canonical import CanonicalObject
from neurofold.core.lookup import ProviderValidationError
from neurofold.core.provenance import Metadata, MetadataState
from neurofold.core.structures import (
    ParsedStructure,
    PolymerResidue,
    RevisionUnavailable,
    StructureSourceChanged,
    UnsupportedStructure,
)

if TYPE_CHECKING:
    import gemmi

AMINO = dict(
    zip(
        (
            "ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO "
            "SER THR TRP TYR VAL SEC PYL"
        ).split(),
        "ARNDCQEGHILKMFPSTWYVUO",
        strict=True,
    )
)


@dataclass(frozen=True)
class ParseLimits:
    cells: int = 1_000_000
    token: int = 65536
    atoms: int = 50000
    residues: int = 10000
    chains: int = 64
    models: int = 20
    assemblies: int = 32
    operators: int = 128
    copies: int = 256
    expanded_atoms: int = 200000

    def __post_init__(self) -> None:
        maxima = (1_000_000, 65536, 50000, 10000, 64, 20, 32, 128, 256, 200000)
        if any(
            type(value) is not int or not 1 <= value <= maximum
            for value, maximum in zip(vars(self).values(), maxima, strict=True)
        ):
            raise ValueError("Parser limits must be positive and cannot exceed profile")


def metadata(token: str, field: str) -> Metadata:
    if token == "":
        return absent(f"{field}: column not supplied")
    if token == "?":
        return absent(f"{field}: deposited unknown (?)")
    if token == ".":
        return absent(f"{field}: deposited not applicable (.)", na=True)
    return present(token)


def number(token: str) -> Decimal:
    try:
        value = Decimal(token)
        if not value.is_finite():
            raise ValueError("Nonfinite coordinate/occupancy/operator")
        return value
    except InvalidOperation as exc:
        raise ValueError("Invalid coordinate/occupancy/operator") from exc


def operations(expression: str, maximum: int) -> tuple[tuple[str, ...], ...]:
    """Bounded PDBx union/range/cartesian-product operator grammar."""
    if len(expression) > 4096:
        raise UnsupportedStructure("Operator expression exceeds limit")
    groups = re.findall(r"\(([^()]*)\)", expression)
    if groups:
        if "".join(f"({g})" for g in groups) != expression:
            raise UnsupportedStructure("Unsupported operator expression")
    else:
        groups = [expression]
    expanded: list[list[str]] = []
    size = 1
    for group in groups:
        values: list[str] = []
        for term in group.split(","):
            if re.fullmatch(r"[0-9]+-[0-9]+", term):
                start, end = map(int, term.split("-"))
                if start > end or end - start + 1 > maximum:
                    raise UnsupportedStructure("Assembly range exceeds limit")
                values.extend(str(i) for i in range(start, end + 1))
            elif re.fullmatch(r"[A-Za-z0-9_]+", term):
                values.append(term)
            else:
                raise UnsupportedStructure("Unsupported assembly operator expression")
        if len(values) != len(set(values)):
            raise UnsupportedStructure("Duplicate assembly operators")
        size *= len(values)
        if size > maximum:
            raise UnsupportedStructure("Assembly product exceeds limit")
        expanded.append(values)
    return tuple(itertools.product(*expanded))


class MmcifParser:
    def __init__(self, limits: ParseLimits | None = None) -> None:
        self.limits = limits or ParseLimits()

    def parse(
        self,
        data: bytes,
        source: ExperimentalStructureSummary,
        selection: StructureSelection,
    ) -> ParsedStructure:
        import gemmi

        if len(data) > MAX_EXPANDED:
            raise UnsupportedStructure("Expanded CIF exceeds limit")
        try:
            document = gemmi.cif.read_string(data.decode("utf-8"))
            if len(document) != 1:
                raise UnsupportedStructure("Exactly one mmCIF data block required")
            block = document.sole_block()
            cells = 0
            for item in block:
                if item.frame is not None:
                    raise UnsupportedStructure("CIF save frames unsupported")
                values = (
                    list(item.loop.values)
                    if item.loop is not None
                    else list(item.pair or ())
                )
                cells += len(values)
                if cells > self.limits.cells or any(
                    len(v) > self.limits.token for v in values
                ):
                    raise UnsupportedStructure("CIF table/token limit exceeded")
            return self._parse(block, source, selection, package_version("gemmi"))
        except (ValueError, RuntimeError, UnicodeError, IndexError, KeyError) as exc:
            if isinstance(
                exc, (UnsupportedStructure, RevisionUnavailable, StructureSourceChanged)
            ):
                raise
            raise ProviderValidationError(f"Invalid mmCIF: {exc}") from exc

    @staticmethod
    def _rows(
        block: "gemmi.cif.Block",
        category: str,
        columns: tuple[str, ...],
        *,
        optional: bool = False,
        missing: tuple[str, ...] = (),
    ) -> list[dict[str, str]]:
        import gemmi

        values = [list(block.find_values(category + "." + col)) for col in columns]
        if not any(values) and optional:
            return []
        for index, col in enumerate(columns):
            if not values[index] and col in missing:
                values[index] = [""] * len(values[0])
        if not values[0] or any(len(v) != len(values[0]) for v in values):
            raise ValueError(f"Missing/inconsistent required category {category}")
        return [
            dict(
                zip(
                    columns,
                    (
                        token if token in {"?", "."} else gemmi.cif.as_string(token)
                        for token in row
                    ),
                    strict=True,
                )
            )
            for row in zip(*values, strict=True)
        ]

    def _parse(
        self,
        block: "gemmi.cif.Block",
        source: ExperimentalStructureSummary,
        selection: StructureSelection,
        version: str,
    ) -> ParsedStructure:
        limits = self.limits
        entry = self._rows(block, "_entry", ("id",))
        if entry != [{"id": source.entry_id}]:
            raise ValueError("Coordinate entry identity mismatch")
        methods = tuple(
            row["method"] for row in self._rows(block, "_exptl", ("method",))
        )
        if set(methods) != set(source.experimental_methods) or any(
            m not in METHODS for m in methods
        ):
            raise ValueError("Coordinate experimental methods disagree")
        if block.find_values("_ma_model_list.model_id"):
            raise ValueError("Computed ModelArchive content is not experimental")
        revisions = self._rows(
            block,
            "_pdbx_audit_revision_history",
            ("ordinal", "major_revision", "minor_revision", "revision_date"),
            optional=True,
        )
        if not revisions or any(not r["ordinal"].isdigit() for r in revisions):
            raise RevisionUnavailable("mmCIF revision unavailable")
        latest = max(revisions, key=lambda r: int(r["ordinal"]))
        if (
            not latest["major_revision"].isdigit()
            or not latest["minor_revision"].isdigit()
            or latest["revision_date"] in {"?", "."}
        ):
            raise RevisionUnavailable("mmCIF revision incomplete")
        actual = (
            latest["major_revision"]
            + "."
            + latest["minor_revision"]
            + "@"
            + latest["revision_date"]
        )
        # Data REST can append T00:00:00+0000 whereas CIF stores a date.
        expected = str(source.source_revision.value)
        if (
            actual.split("@", 1)[0] != expected.split("@", 1)[0]
            or actual.split("@", 1)[1] != expected.split("@", 1)[-1][:10]
        ):
            raise StructureSourceChanged(expected, actual)
        chains = self._rows(block, "_struct_asym", ("id", "entity_id"))
        if len(chains) > limits.chains or len({r["id"] for r in chains}) != len(chains):
            raise UnsupportedStructure("Chain limit/duplicate chain")
        chain_entities = {r["id"]: r["entity_id"] for r in chains}
        if chain_entities.get(selection.label_asym_id) != selection.entity_id:
            raise UnsupportedStructure("Selected chain/entity absent")
        poly_types = self._rows(block, "_entity_poly", ("entity_id", "type"))
        if {r["entity_id"]: r["type"] for r in poly_types}.get(
            selection.entity_id
        ) != "polypeptide(L)":
            raise UnsupportedStructure("Selected polymer type unsupported")
        polymers = self._rows(block, "_entity_poly_seq", ("entity_id", "num", "mon_id"))
        if len(polymers) > limits.residues or len(
            {(r["entity_id"], r["num"]) for r in polymers}
        ) != len(polymers):
            raise UnsupportedStructure("Polymer residue limit/microheterogeneity")
        selected = [r for r in polymers if r["entity_id"] == selection.entity_id]
        if [r["num"] for r in selected] != [
            str(i) for i in range(1, len(selected) + 1)
        ] or not selected:
            raise UnsupportedStructure(
                "Polymer numbering must be complete positive contiguous labels"
            )
        components = self._rows(
            block, "_chem_comp", ("id", "mon_nstd_parent_comp_id"), optional=True
        )
        parents = {r["id"]: r["mon_nstd_parent_comp_id"] for r in components}
        codes: list[str] = []
        modifications: list[dict[str, object]] = []
        for row in selected:
            component = row["mon_id"]
            parent = component if component in AMINO else parents.get(component, "?")
            code = AMINO.get(parent, "X")
            codes.append(code)
            if component not in AMINO:
                modifications.append(
                    {
                        "label_seq_id": int(row["num"]),
                        "component": component,
                        "parent": parent,
                        "normalized": code,
                    }
                )
        sequence = "".join(codes)
        if sequence != source.polymer_sequence.value:
            raise ValueError("mmCIF polymer differs from authoritative entity sequence")
        schemes = self._rows(
            block,
            "_pdbx_poly_seq_scheme",
            (
                "asym_id",
                "entity_id",
                "seq_id",
                "mon_id",
                "auth_seq_num",
                "pdb_strand_id",
                "pdb_ins_code",
            ),
            optional=True,
            missing=("auth_seq_num", "pdb_strand_id", "pdb_ins_code"),
        )
        # Scheme author numbering may differ from coordinate auth_seq_id.
        # Preserve both; pdb_seq_num is the coordinate numbering when supplied.
        scheme_pdb = [
            row["pdb_seq_num"]
            for row in self._rows(
                block, "_pdbx_poly_seq_scheme", ("pdb_seq_num",), optional=True
            )
        ]
        if scheme_pdb and len(scheme_pdb) != len(schemes):
            raise ValueError("Inconsistent scheme PDB numbering column")
        for row, token in zip(schemes, scheme_pdb, strict=bool(scheme_pdb)):
            row["pdb_seq_num"] = token
        scheme: dict[int, dict[str, str]] = {}
        for row in schemes:
            if row["asym_id"] != selection.label_asym_id:
                continue
            label = int(row["seq_id"])
            if (
                row["entity_id"] != selection.entity_id
                or not 1 <= label <= len(selected)
                or selected[label - 1]["mon_id"] != row["mon_id"]
                or label in scheme
            ):
                raise ValueError("Inconsistent/duplicate polymer scheme")
            chain_author = metadata(row["pdb_strand_id"], "author chain")
            if row["pdb_strand_id"] and (chain_author.state, chain_author.value) != (
                selection.auth_asym_id.state,
                selection.auth_asym_id.value,
            ):
                raise UnsupportedStructure("Author chain mismatch in polymer scheme")
            scheme[label] = row
        atoms = self._rows(
            block,
            "_atom_site",
            (
                "id",
                "label_entity_id",
                "label_asym_id",
                "auth_asym_id",
                "label_seq_id",
                "auth_seq_id",
                "pdbx_PDB_ins_code",
                "label_comp_id",
                "label_atom_id",
                "label_alt_id",
                "pdbx_PDB_model_num",
                "Cartn_x",
                "Cartn_y",
                "Cartn_z",
                "occupancy",
            ),
            missing=(
                "auth_asym_id",
                "auth_seq_id",
                "pdbx_PDB_ins_code",
                "label_alt_id",
            ),
        )
        if len(atoms) > limits.atoms or len({r["id"] for r in atoms}) != len(atoms):
            raise UnsupportedStructure("Atom limit/duplicate atom IDs")
        models = sorted({r["pdbx_PDB_model_num"] for r in atoms})
        if len(models) > limits.models or any(
            not m.isdigit() or int(m) <= 0 for m in models
        ):
            raise UnsupportedStructure("Model limit/invalid model identifiers")
        if selection.model_id not in models:
            raise UnsupportedStructure("Explicit model is absent")
        observed: dict[int, list[dict[str, str]]] = {}
        atom_keys: set[tuple[str, ...]] = set()
        atom_counts: dict[str, int] = {}
        for row in atoms:
            chain = row["label_asym_id"]
            if chain_entities.get(chain) != row["label_entity_id"]:
                raise ValueError("Atom entity/chain mismatch")
            atom_counts[chain] = atom_counts.get(chain, 0) + 1
            for key in ("Cartn_x", "Cartn_y", "Cartn_z"):
                if abs(number(row[key])) > Decimal("1e7"):
                    raise ValueError("Coordinate magnitude exceeds profile")
            occupancy = number(row["occupancy"])
            if not 0 <= occupancy <= 1:
                raise ValueError("Occupancy outside 0..1")
            key_tuple = tuple(
                row[k]
                for k in (
                    "pdbx_PDB_model_num",
                    "label_asym_id",
                    "label_seq_id",
                    "auth_seq_id",
                    "pdbx_PDB_ins_code",
                    "label_comp_id",
                    "label_atom_id",
                    "label_alt_id",
                )
            )
            if key_tuple in atom_keys:
                raise ValueError("Duplicate coordinate atom key")
            atom_keys.add(key_tuple)
            if (
                chain != selection.label_asym_id
                or row["pdbx_PDB_model_num"] != selection.model_id
            ):
                continue
            if (
                row["auth_asym_id"] not in {"?", ".", ""}
                and metadata(row["auth_asym_id"], "author chain")
                != selection.auth_asym_id
            ):
                raise ValueError("Atom author chain mismatch")
            if row["label_seq_id"] in {"?", "."}:
                # Selected polymer coordinates cannot be silently discarded.
                raise UnsupportedStructure(
                    "Selected polymer atom lacks label residue ID"
                )
            label = int(row["label_seq_id"])
            if (
                not 1 <= label <= len(selected)
                or selected[label - 1]["mon_id"] != row["label_comp_id"]
            ):
                raise ValueError("Atom residue differs from polymer")
            observed.setdefault(label, []).append(row)
        assembly_details = self._assemblies(
            block, chain_entities, atom_counts, selection
        )
        assembly_ids = {
            row["id"]
            for row in self._rows(
                block, "_pdbx_struct_assembly", ("id",), optional=True
            )
        }
        if source.assembly_ids.state is MetadataState.PRESENT and assembly_ids != set(
            source.assembly_ids.values
        ):
            raise ValueError(
                "Coordinate assembly inventory differs from authoritative metadata"
            )
        residues: list[PolymerResidue] = []
        selected_details: list[dict[str, object]] = []
        for label, code in enumerate(codes, 1):
            coordinate_rows = observed.get(label, [])
            author = (
                metadata(
                    scheme[label].get("pdb_seq_num", "?"), "coordinate author residue"
                )
                if label in scheme
                else absent("No author residue scheme supplied")
            )
            insertion = (
                metadata(scheme[label]["pdb_ins_code"], "insertion code")
                if label in scheme
                else absent("No insertion scheme supplied")
            )
            for field, value in (
                ("auth_seq_id", author),
                ("pdbx_PDB_ins_code", insertion),
            ):
                known = {
                    r[field] for r in coordinate_rows if r[field] not in {"?", ".", ""}
                }
                if len(known) > 1 or (
                    known
                    and value.state is MetadataState.PRESENT
                    and value.value not in known
                ):
                    raise ValueError("Inconsistent author/insertion identity")
                if known and value.state is not MetadataState.PRESENT:
                    replacement = metadata(next(iter(known)), field)
                    if field == "auth_seq_id":
                        author = replacement
                    else:
                        insertion = replacement
            coordinate_present = any(
                number(r["occupancy"]) > 0 for r in coordinate_rows
            )
            residues.append(
                PolymerResidue(
                    label, code, author, insertion, coordinate_present, code == "X"
                )
            )
            selected_details.append(
                {
                    "label_seq_id": label,
                    "component": selected[label - 1]["mon_id"],
                    "scheme_author_number": metadata(
                        scheme[label]["auth_seq_num"], "scheme author number"
                    ).to_dict()
                    if label in scheme
                    else absent("No scheme author number").to_dict(),
                    "scheme_pdb_number": metadata(
                        scheme[label].get("pdb_seq_num", "?"), "scheme PDB number"
                    ).to_dict()
                    if label in scheme
                    else absent("No scheme PDB number").to_dict(),
                    "atoms": [
                        {
                            "id": r["id"],
                            "name": r["label_atom_id"],
                            "auth_asym_id": metadata(
                                r["auth_asym_id"], "coordinate author chain"
                            ).to_dict(),
                            "alt_id": metadata(
                                r["label_alt_id"], "alternate location"
                            ).to_dict(),
                            "occupancy": r["occupancy"],
                            "auth_seq_id": metadata(
                                r["auth_seq_id"], "coordinate author residue"
                            ).to_dict(),
                            "insertion_code": metadata(
                                r["pdbx_PDB_ins_code"], "coordinate insertion"
                            ).to_dict(),
                        }
                        for r in coordinate_rows
                    ],
                }
            )
        return ParsedStructure(
            sequence,
            tuple(residues),
            CanonicalObject.from_value(
                {
                    "parser": "gemmi",
                    "version": version,
                    "profile": "neurofold-mmcif/1",
                    "limits": vars(limits),
                    "coordinate_unit": "angstrom",
                    "coordinate_frame": "original-deposited-cartesian",
                    "transform_applied": False,
                    "models": models,
                    "chains": chains,
                    "assemblies": assembly_details,
                    "modified_residues": modifications,
                    "selected_residues": selected_details,
                    "atom_count": len(atoms),
                    "decompression": (
                        "HTTP gzip when supplied; original entity bytes retained"
                    ),
                    "normalization": (
                        "Only local unambiguous standard component parents; "
                        "unknown X remains ambiguous"
                    ),
                    "alternate_locations": (
                        "All retained; no coordinate averaging or altloc selection"
                    ),
                }
            ),
        )

    def _assemblies(
        self,
        block: "gemmi.cif.Block",
        chains: dict[str, str],
        counts: dict[str, int],
        selection: StructureSelection,
    ) -> list[dict[str, object]]:
        limits = self.limits
        assemblies = self._rows(block, "_pdbx_struct_assembly", ("id",), optional=True)
        operators = self._rows(
            block,
            "_pdbx_struct_oper_list",
            ("id",)
            + tuple(f"matrix[{i}][{j}]" for i in range(1, 4) for j in range(1, 4))
            + tuple(f"vector[{i}]" for i in range(1, 4)),
            optional=True,
        )
        if (
            len(assemblies) > limits.assemblies
            or len(operators) > limits.operators
            or len({r["id"] for r in operators}) != len(operators)
            or len({r["id"] for r in assemblies}) != len(assemblies)
        ):
            raise UnsupportedStructure("Assembly/operator count limit or duplicate")
        op_dict = {r["id"]: r for r in operators}
        for row in operators:
            if any(
                abs(number(v)) > Decimal("1e7") for k, v in row.items() if k != "id"
            ):
                raise ValueError("Invalid operator magnitude")
        rows = self._rows(
            block,
            "_pdbx_struct_assembly_gen",
            ("assembly_id", "oper_expression", "asym_id_list"),
            optional=True,
        )
        copies: set[tuple[str, str, tuple[str, ...]]] = set()
        atom_total = 0
        details: list[dict[str, object]] = []
        found = False
        for row in rows:
            if row["assembly_id"] not in {a["id"] for a in assemblies}:
                raise ValueError("Assembly generation targets unknown assembly")
            chain_ids = row["asym_id_list"].split(",")
            if len(chain_ids) != len(set(chain_ids)) or any(
                c not in chains for c in chain_ids
            ):
                raise ValueError("Invalid assembly chain identifiers")
            paths = operations(row["oper_expression"], limits.copies)
            for chain, path in itertools.product(chain_ids, paths):
                if any(op not in op_dict for op in path):
                    raise ValueError("Unknown assembly operator")
                key = row["assembly_id"], chain, path
                if key in copies:
                    raise ValueError("Duplicate generated assembly copy")
                copies.add(key)
                atom_total += counts.get(chain, 0)
                if len(copies) > limits.copies or atom_total > limits.expanded_atoms:
                    raise UnsupportedStructure("Assembly expansion exceeds limit")
                if (
                    selection.assembly_id.value == row["assembly_id"]
                    and selection.label_asym_id == chain
                    and selection.operator_id.value == "*".join(path)
                ):
                    found = True
            details.append(
                {
                    "assembly_id": row["assembly_id"],
                    "expression": row["oper_expression"],
                    "chains": chain_ids,
                    "operator_paths": [list(path) for path in paths],
                    "operators": [
                        op_dict[key]
                        for key in sorted({op for path in paths for op in path})
                    ],
                    "application_order": (
                        "rightmost first; column vectors; matrices not applied"
                    ),
                }
            )
        if selection.assembly_id.state is MetadataState.PRESENT:
            if not found:
                raise UnsupportedStructure("Selected assembly/operator copy absent")
        elif selection.assembly_id.state is not MetadataState.NOT_APPLICABLE:
            raise UnsupportedStructure(
                "Select asymmetric unit or known assembly explicitly"
            )
        return details
