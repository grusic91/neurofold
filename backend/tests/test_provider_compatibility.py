"""Authored regressions for observed upstream representations; no live data."""

import gzip
import hashlib
from collections.abc import Mapping
from pathlib import Path

import pytest
from test_uniprot import Fake, catalog, entry, response

from neurofold.adapters.biological.transport import Response
from neurofold.core.lookup import ProviderValidationError


class NegotiatedEncoding(Fake):
    def request(
        self, url: str, headers: Mapping[str, str], *, timeout: float
    ) -> Response:
        self.calls.append((url, headers, timeout))
        plain = response(entry())
        if headers["accept-encoding"] == "identity":
            return plain
        # The live failure declared one gzip encoding but nested another gzip
        # entity inside it. These are authored six-residue fixture bytes only.
        return Response(
            200,
            {"content-type": "application/json", "content-encoding": "gzip"},
            gzip.compress(gzip.compress(plain.body, mtime=0), mtime=0),
        )


def test_uniprot_requests_identity_to_avoid_misdeclared_nested_encoding(
    tmp_path: Path,
) -> None:
    fake = NegotiatedEncoding()
    client, _, _ = catalog(tmp_path, fake)
    protein = client.get("P00001")
    assert protein.sequence == "ACDEFG"
    assert fake.calls[0][1]["accept-encoding"] == "identity"
    assert protein.source_receipt.raw_artifact.media_type == "application/json"


def test_misdeclared_nested_gzip_is_still_rejected(tmp_path: Path) -> None:
    raw = gzip.compress(gzip.compress(response(entry()).body, mtime=0), mtime=0)
    client, store, _ = catalog(
        tmp_path,
        Fake(
            Response(
                200,
                {"content-type": "application/json", "content-encoding": "gzip"},
                raw,
            )
        ),
    )
    with pytest.raises(ProviderValidationError):
        client.get("P00001")
    assert not list(store.root.glob("reference-*.json"))


def test_standard_entry_does_not_require_ccd_only_parent_column(tmp_path: Path) -> None:
    from test_structures import CIF, imported

    # Author a tiny entry-style table; the parent column belongs to the CCD and
    # is optional in PDB entries. No downloaded structure bytes are used.
    raw = (
        CIF.read_bytes() + b"\nloop_\n_chem_comp.id\n_chem_comp.type\n"
        b"ALA 'L-peptide linking'\nGLY 'PEPTIDE LINKING'\n"
    )
    record, _, _, _, _ = imported(tmp_path, raw=raw)
    parent_column = record.parsing.to_dict()["component_parent_column"]
    assert isinstance(parent_column, dict)
    assert parent_column["state"] == "unavailable"
    assert record.parsing.to_dict()["transform_applied"] is False


def test_missing_parent_column_does_not_invent_a_modified_residue_parent(
    tmp_path: Path,
) -> None:
    from test_structures import (
        CIF,
        REVISION,
        coordinate_response,
        metadata_events,
        selection,
        service,
        setup,
    )
    from test_uniprot import response

    from neurofold.adapters.biological.uniprot import present

    raw = (
        CIF.read_bytes().replace(b"ALA", b"UNK")
        + b"\nloop_\n_chem_comp.id\n_chem_comp.type\nUNK 'L-peptide linking'\n"
    )
    provider, store, reference, _, _ = setup(
        tmp_path,
        metadata_events(sequence="XCDEFG")
        + [coordinate_response(raw), response(None, 304)],
    )
    record = service(provider, store).import_selected(
        reference.reference_id, "1SYN", selection(), present(REVISION)
    )
    modifications = record.parsing.to_dict()["modified_residues"]
    assert isinstance(modifications, list)
    modification = modifications[0]
    assert isinstance(modification, dict)
    assert modification["normalized"] == "X"
    parents = record.parsing.to_dict()["component_parents"]
    assert isinstance(parents, list)
    component_parent = parents[0]
    assert isinstance(component_parent, dict)
    parent = component_parent["metadata"]
    assert isinstance(parent, dict)
    assert parent["state"] == "unavailable"
    assert any(row.status == "ambiguous" for row in record.mapping.rows)
    assert record.parsing.to_dict()["profile"] == "neurofold-mmcif/2"


def test_rcsb_cif_media_type_retains_gzip_original(tmp_path: Path) -> None:
    from test_structures import (
        CIF,
        REVISION,
        coordinate_response,
        metadata_events,
        selection,
        service,
        setup,
    )

    from neurofold.adapters.biological.uniprot import present

    original = gzip.compress(CIF.read_bytes(), mtime=0)
    provider, store, reference, _, _ = setup(
        tmp_path,
        metadata_events()
        + [
            coordinate_response(
                original,
                **{"content-type": "chemical/x-cif", "content-encoding": "gzip"},
            ),
            response(None, 304),
        ],
    )
    record = service(provider, store).import_selected(
        reference.reference_id, "1SYN", selection(), present(REVISION)
    )
    artifact = record.descriptor.raw_artifact
    assert artifact.byte_size == len(original)
    # The archived artifact is the original compressed entity, not decoded CIF.
    assert artifact.media_type == "application/gzip"
    assert artifact.content_hash.sha256 == hashlib.sha256(original).hexdigest()
