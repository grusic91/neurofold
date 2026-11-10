"""Experimental RCSB discovery and authoritative bounded source acquisition."""

import io
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import BoundedSemaphore, RLock
from urllib.parse import quote, urlencode, urlsplit
from uuid import uuid4

from neurofold.adapters.biological.policy import (
    BoundedCache,
    Clock,
    Cursors,
    RetryPolicy,
)
from neurofold.adapters.biological.transport import (
    MAX_DOWNLOAD,
    MAX_HEADERS,
    Response,
    Transport,
    TransportFailure,
    TransportTimeout,
)
from neurofold.adapters.biological.uniprot import (
    absent,
    array,
    decode,
    obj,
    positive,
    present,
    provider_json,
    references,
    text,
)
from neurofold.core.biological import (
    Availability,
    ExperimentalStructureSummary,
    ReferenceSnapshot,
    Resolution,
    StructurePage,
)
from neurofold.core.canonical import (
    CanonicalObject,
    canonical_json,
    sequence_sha256,
    sha256_bytes,
)
from neurofold.core.errors import ArchiveConflict, ArchiveIntegrityError, ResourceLimit
from neurofold.core.lookup import (
    CursorError,
    ProviderError,
    ProviderNotFound,
    ProviderSelectionError,
    ProviderTimeout,
    ProviderValidationError,
    SourceArchive,
)
from neurofold.core.provenance import (
    ArtifactDescriptor,
    ArtifactRights,
    ArtifactStore,
    ContentHash,
    EvidenceKind,
    HashEncoding,
    Metadata,
    RedistributionStatus,
    SourceReceipt,
)
from neurofold.core.structures import (
    RevisionUnavailable,
    StructureCheck,
    StructureDownload,
    StructureSource,
    StructureSourceChanged,
    UnsupportedStructure,
)

VERSION = "rcsb-rest/2"
BINDING = VERSION + ":neurofold-biological/1:neurofold-research/1:structure-import/1"
DATA = "https://data.rcsb.org/rest/v1/core/"
SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"
PROVIDER_SLOTS = BoundedSemaphore(2)
METHODS = {
    "X-RAY DIFFRACTION",
    "SOLUTION NMR",
    "SOLID-STATE NMR",
    "ELECTRON MICROSCOPY",
    "ELECTRON CRYSTALLOGRAPHY",
    "NEUTRON DIFFRACTION",
    "FIBER DIFFRACTION",
    "POWDER DIFFRACTION",
    "SOLUTION SCATTERING",
    "EPR",
    "FLUORESCENCE TRANSFER",
}


def validate_entry_id(value: str) -> str:
    if not re.fullmatch(r"[1-9][A-Z0-9]{3}", value):
        raise UnsupportedStructure(
            "Select an explicit supported four-character PDB entry"
        )
    return value


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise UnsupportedStructure("Unsupported entity/instance identifier")
    return value


def source_revision(entry: dict[str, object]) -> Metadata:
    raw = obj(entry.get("rcsb_accession_info", {}))
    major, minor, date = (
        raw.get("major_revision"),
        raw.get("minor_revision"),
        raw.get("revision_date"),
    )
    if major is None or minor is None or date is None:
        return absent("Authoritative revision tuple not supplied")
    if type(major) is not int or major < 1 or type(minor) is not int or minor < 0:
        raise ValueError("Invalid source revision numbers")
    date = text(date)
    # RCSB dates may include midnight time. Preserve full source value.
    from datetime import datetime

    datetime.fromisoformat(date.replace("Z", "+00:00"))
    return present(f"{major}.{minor}@{date}")


def experimental(entry: dict[str, object], expected: str) -> tuple[str, ...]:
    if entry.get("rcsb_id") != expected:
        raise ValueError("Entry identity mismatch")
    if (
        obj(entry.get("rcsb_entry_info")).get("structure_determination_methodology")
        != "experimental"
    ):
        raise ValueError("Computed/unknown methodology is not experimental evidence")
    methods = tuple(text(obj(item).get("method")) for item in array(entry.get("exptl")))
    if (
        not methods
        or len(set(methods)) != len(methods)
        or any(m not in METHODS for m in methods)
    ):
        raise ValueError("Unsupported or nonexperimental method")
    return methods


@dataclass(frozen=True)
class CachedSource:
    response: Response
    receipt: SourceReceipt | None
    headers: Mapping[str, str]
    expires: float


class RcsbCatalog:
    def __init__(
        self,
        transport: Transport,
        artifacts: ArtifactStore,
        archive: SourceArchive,
        *,
        clock: Clock | None = None,
        retry: RetryPolicy | None = None,
        new_id: Callable[[], str] = lambda: uuid4().hex,
        cursor_token: Callable[[], str] | None = None,
        evidence: EvidenceKind = EvidenceKind.EXPERIMENTAL,
        download_host: str = "files.rcsb.org",
    ) -> None:
        if download_host != "files.rcsb.org" or evidence is EvidenceKind.PREDICTED:
            raise ValueError("Unsupported RCSB host/evidence configuration")
        self.transport, self.artifacts, self.archive = transport, artifacts, archive
        self.clock, self.retry = clock or Clock(), retry or RetryPolicy()
        self.new_id, self.evidence, self.download_host = new_id, evidence, download_host
        self.cache: BoundedCache[CachedSource] = BoundedCache()
        self.cursors = (
            Cursors(self.clock)
            if cursor_token is None
            else Cursors(self.clock, cursor_token)
        )
        self.lock = RLock()

    def _request(
        self, url: str, headers: Mapping[str, str], deadline: float
    ) -> Response:
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.netloc
            not in {"search.rcsb.org", "data.rcsb.org", self.download_host}
            or parts.fragment
        ):
            raise ProviderValidationError("Forbidden RCSB destination")
        remaining = deadline - self.clock.monotonic()
        if remaining <= 0 or not PROVIDER_SLOTS.acquire(timeout=max(0, remaining)):
            raise ProviderTimeout("RCSB concurrency/budget exhausted")
        try:
            timed_out = False
            for attempt in range(self.retry.retries + 1):
                remaining = deadline - self.clock.monotonic()
                if remaining <= 0:
                    raise ProviderTimeout("RCSB budget exhausted")
                try:
                    received = self.transport.request(url, headers, timeout=remaining)
                    response = Response(
                        received.status,
                        {k.lower(): v for k, v in received.headers.items()},
                        received.body,
                    )
                    if self.clock.monotonic() >= deadline:
                        raise ProviderTimeout("RCSB budget exhausted")
                    if (
                        sum(len(k) + len(v) for k, v in response.headers.items())
                        > MAX_HEADERS
                        or len(response.body) > MAX_DOWNLOAD
                    ):
                        raise ProviderValidationError("RCSB response exceeds bounds")
                    if response.status not in (429, 502, 503, 504):
                        return response
                    timed_out = response.status == 504
                    retry_after = response.headers.get("retry-after")
                except TransportFailure as exc:
                    timed_out = isinstance(exc, TransportTimeout)
                    retry_after = None
                if attempt == self.retry.retries:
                    break
                delay = self.retry.delay(attempt, retry_after, self.clock)
                if delay >= deadline - self.clock.monotonic():
                    break
                self.clock.sleep(delay)
            if timed_out:
                raise ProviderTimeout("RCSB deadline exceeded")
            raise ProviderError("RCSB retry budget exhausted")
        finally:
            PROVIDER_SLOTS.release()

    def _receipt(
        self, url: str, response: Response, stamp: str, version: Metadata
    ) -> SourceReceipt:
        rights = ArtifactRights(
            license=present(
                "Apache-2.0" if self.evidence is EvidenceKind.SYNTHETIC else LICENSE
            ),
            attribution=present(
                "NeuroFold contributors; authored synthetic example"
                if self.evidence is EvidenceKind.SYNTHETIC
                else "wwPDB / RCSB PDB; retain original structure citations"
            ),
            redistribution=RedistributionStatus.ALLOWED,
            basis="Authored synthetic transport"
            if self.evidence is EvidenceKind.SYNTHETIC
            else (
                "RCSB usage policy: API and PDB archive data CC0; "
                "unrelated third-party rights require separate review"
            ),
        )
        artifact = ArtifactDescriptor(
            artifact_id=self.new_id(),
            content_hash=ContentHash(
                sha256=sha256_bytes(response.body), encoding=HashEncoding.RAW
            ),
            byte_size=len(response.body),
            media_type="application/gzip"
            if response.headers.get("content-encoding") == "gzip"
            else ("chemical/x-mmcif" if url.endswith(".cif") else "application/json"),
            evidence=self.evidence,
            rights=rights,
            parents=(),
            transformation=absent("Original HTTP entity bytes", na=True),
        )
        self.artifacts.publish(io.BytesIO(response.body), descriptor=artifact)
        supplied_citations: list[str] = []
        if "/entry/" in url:
            primary = obj(
                obj(provider_json(decode(response))).get("rcsb_primary_citation", {})
            )
            if primary.get("pdbx_database_id_DOI") is not None:
                supplied_citations.append(
                    "doi:" + text(primary["pdbx_database_id_DOI"])
                )
            if primary.get("pdbx_database_id_PubMed") is not None:
                supplied_citations.append(
                    "pubmed:" + str(positive(primary["pdbx_database_id_PubMed"]))
                )
        receipt = SourceReceipt(
            receipt_id=self.new_id(),
            provider="RCSB PDB",
            query=url,
            retrieved_at=stamp,
            raw_artifact=artifact,
            accession=absent(
                "PDB identity is retained in query; not a UniProt accession", na=True
            ),
            isoform=absent("Not a UniProt sequence retrieval", na=True),
            taxon_id=absent("See entity metadata"),
            entry_version=version,
            sequence_version=absent("No independent polymer sequence version supplied"),
            release=absent("No archive release supplied"),
            release_date=absent("See entry revision metadata"),
            etag=present(response.headers["etag"])
            if "etag" in response.headers
            else absent("ETag not supplied"),
            last_modified=present(response.headers["last-modified"])
            if "last-modified" in response.headers
            else absent("Last-Modified not supplied"),
            license_references=references([str(rights.license.value)]),
            citation_references=references(supplied_citations),
        )
        self.archive.publish_receipt(receipt)
        return receipt

    def _fetch(
        self,
        url: str,
        deadline: float,
        *,
        fresh: bool = False,
        ttl: int = 86400,
        validate: Callable[[bytes], Metadata] | None = None,
    ) -> tuple[CachedSource, StructureCheck | None]:
        cached = self.cache.get(BINDING + url)
        if cached is not None and not fresh and cached.expires > self.clock.monotonic():
            if cached.receipt is None:
                raise ProviderNotFound(url)
            return cached, None
        headers = {
            "accept": "chemical/x-mmcif"
            if url.endswith(".cif")
            else "application/json",
            "accept-encoding": "gzip",
        }
        if cached is not None and cached.receipt is not None:
            for key, conditional in (
                ("etag", "if-none-match"),
                ("last-modified", "if-modified-since"),
            ):
                if key in cached.headers:
                    headers[conditional] = cached.headers[key]
        response = self._request(url, headers, deadline)
        stamp = self.clock.stamp()
        if response.status == 304:
            if (
                cached is None
                or cached.receipt is None
                or response.body
                or not any(k.startswith("if-") for k in headers)
            ):
                raise ProviderValidationError("Unsolicited/body-bearing RCSB 304")
            result = CachedSource(
                cached.response,
                cached.receipt,
                dict(cached.headers) | dict(response.headers),
                self.clock.monotonic() + ttl,
            )
        elif response.status == 404:
            self.cache.put(
                BINDING + url,
                CachedSource(response, None, {}, self.clock.monotonic() + 300),
                256,
            )
            raise ProviderNotFound(url)
        elif 300 <= response.status < 400:
            raise ProviderValidationError(
                "RCSB redirects require explicit new selection"
            )
        elif response.status == 204 and url.startswith(SEARCH):
            if response.body:
                raise ProviderValidationError("Body-bearing RCSB 204")
            receipt = self._receipt(
                url, response, stamp, absent("Search has no entry revision")
            )
            result = CachedSource(
                response, receipt, response.headers, self.clock.monotonic() + ttl
            )
            self.cache.put(BINDING + url, result, len(receipt.to_json()) + MAX_HEADERS)
            return result, None
        elif response.status != 200:
            raise ProviderError(f"Unexpected RCSB status {response.status}")
        else:
            decoded = decode(response)
            content_type = (
                response.headers.get("content-type", "").split(";")[0].lower()
            )
            if content_type not in (
                {
                    "chemical/x-mmcif",
                    "chemical/x-cif",
                    "text/plain",
                    "application/octet-stream",
                }
                if url.endswith(".cif")
                else {"application/json"}
            ):
                raise ProviderValidationError("Unexpected RCSB content type")
            version = (
                validate(decoded)
                if validate
                else absent("Revision carried by entry metadata")
            )
            receipt = self._receipt(url, response, stamp, version)
            result = CachedSource(
                response, receipt, response.headers, self.clock.monotonic() + ttl
            )
        assert result.receipt is not None
        # Even a 304 must pass the current caller's identity/revision validator.
        if validate:
            validate(decode(result.response))
        self.cache.put(
            BINDING + url,
            result,
            len(result.response.body) + len(result.receipt.to_json()) + MAX_HEADERS,
        )
        return result, StructureCheck(
            source_receipt_id=result.receipt.receipt_id,
            checked_at=stamp,
            response_status=200 if response.status == 200 else 304,
            response_headers=CanonicalObject.from_value(dict(response.headers)),
            adapter_version=VERSION,
        )

    def _entry(
        self, identity: str, deadline: float, fresh: bool
    ) -> tuple[dict[str, object], SourceReceipt, StructureCheck | None]:
        def validate(raw: bytes) -> Metadata:
            try:
                value = obj(provider_json(raw))
                experimental(value, identity)
                return source_revision(value)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise ProviderValidationError(
                    f"Invalid authoritative RCSB entry: {exc}"
                ) from exc

        cached, check = self._fetch(
            DATA + "entry/" + identity, deadline, fresh=fresh, validate=validate
        )
        assert cached.receipt is not None
        return obj(provider_json(decode(cached.response))), cached.receipt, check

    def inspect(
        self,
        reference: ReferenceSnapshot,
        entry_id: str,
        label_asym_id: str,
        *,
        fresh: bool,
        _deadline: float | None = None,
    ) -> StructureSource:
        identity, chain = validate_entry_id(entry_id), identifier(label_asym_id)
        deadline = (
            _deadline
            if _deadline is not None
            else self.clock.monotonic() + self.retry.budget
        )
        remaining = deadline - self.clock.monotonic()
        if remaining <= 0 or not self.lock.acquire(timeout=remaining):
            raise ProviderTimeout("RCSB catalog budget exhausted")
        try:
            entry, receipt, check = self._entry(identity, deadline, fresh)
            checks = [check] if check else []
            instance, event = self._fetch(
                DATA + f"polymer_entity_instance/{identity}/{quote(chain)}",
                deadline,
                fresh=fresh,
            )
            assert instance.receipt is not None
            if event:
                checks.append(event)
            inst = obj(provider_json(decode(instance.response)))
            ids = obj(inst.get("rcsb_polymer_entity_instance_container_identifiers"))
            if (
                inst.get("rcsb_id") != identity + "." + chain
                or ids.get("entry_id") != identity
                or ids.get("asym_id") != chain
            ):
                raise ValueError("Instance identity mismatch")
            entity = identifier(text(ids.get("entity_id")))
            entity_response, event = self._fetch(
                DATA + f"polymer_entity/{identity}/{entity}", deadline, fresh=fresh
            )
            assert entity_response.receipt is not None
            if event:
                checks.append(event)
            ent = obj(provider_json(decode(entity_response.response)))
            ent_ids = obj(ent.get("rcsb_polymer_entity_container_identifiers"))
            if (
                ent.get("rcsb_id") != identity + "_" + entity
                or ent_ids.get("entry_id") != identity
                or ent_ids.get("entity_id") != entity
                or chain not in array(ent_ids.get("asym_ids"))
            ):
                raise ValueError("Entity/chain identity mismatch")
            crossrefs = [
                obj(item)
                for item in array(ent_ids.get("reference_sequence_identifiers", []))
            ]
            if not any(
                item.get("database_name") == "UniProt"
                and item.get("database_accession")
                == reference.protein.summary.accession
                for item in crossrefs
            ):
                raise ProviderSelectionError(
                    "Selected entity lacks pinned UniProt identity"
                )
            taxa = [
                obj(item).get("ncbi_taxonomy_id")
                for item in array(ent.get("rcsb_entity_source_organism", []))
            ]
            if any(type(taxon) is not int or taxon <= 0 for taxon in taxa):
                raise ValueError("Invalid source taxonomy identifier")
            if reference.protein.summary.taxon_id.value not in taxa:
                raise ProviderSelectionError(
                    "Selected entity taxon mismatch/unavailable"
                )
            poly = obj(ent.get("entity_poly"))
            if poly.get("type") != "polypeptide(L)":
                raise UnsupportedStructure("Only L-polypeptide entities are supported")
            raw_sequence = poly.get("pdbx_seq_one_letter_code_can")
            if not isinstance(raw_sequence, str) or len(raw_sequence) > 20000:
                raise ResourceLimit("Polymer source text exceeds limit")
            sequence = "".join(raw_sequence.split())
            sequence_sha256(sequence)
            if len(sequence) > 10000:
                raise ResourceLimit("Polymer sequence exceeds limit")
            methods = experimental(entry, identity)
            info = obj(entry.get("rcsb_accession_info", {}))
            resolution = array(
                obj(entry.get("rcsb_entry_info")).get("resolution_combined", [])
            )
            resolutions = tuple(
                Resolution(
                    method=method,
                    value=present(
                        str(resolution[0]).rstrip("0").rstrip(".")
                        if "." in str(resolution[0])
                        else str(resolution[0])
                    )
                    if len(methods) == 1 and len(resolution) == 1
                    else absent("No unambiguous per-method resolution supplied"),
                )
                for method in methods
            )
            assembly_ids = array(
                obj(entry.get("rcsb_entry_container_identifiers", {})).get(
                    "assembly_ids", []
                )
            )
            citation = obj(entry.get("rcsb_primary_citation", {}))
            citations: list[str] = []
            if citation.get("pdbx_database_id_PubMed") is not None:
                citations.append(
                    "pubmed:" + str(positive(citation["pdbx_database_id_PubMed"]))
                )
            if citation.get("pdbx_database_id_DOI") is not None:
                citations.append("doi:" + text(citation["pdbx_database_id_DOI"]))
            summary = ExperimentalStructureSummary(
                entry_id=identity,
                entity_id=entity,
                label_asym_id=chain,
                auth_asym_id=present(text(ids["auth_asym_id"]))
                if ids.get("auth_asym_id") is not None
                else absent("Author chain not supplied"),
                experimental_methods=methods,
                resolutions=resolutions,
                source_revision=source_revision(entry),
                revision_date=present(text(info["revision_date"]))
                if info.get("revision_date")
                else absent("Revision date not supplied"),
                assembly_ids=references([text(item) for item in assembly_ids]),
                polymer_sequence=present(sequence),
                mapped_coverage=absent(
                    "Mapping requires explicit import and model selection"
                ),
                citations=references(citations),
                source_receipt=receipt,
            )
            return StructureSource(summary, tuple(checks))
        except (ValueError, KeyError, UnicodeError, RecursionError) as exc:
            if isinstance(
                exc,
                (
                    UnsupportedStructure,
                    ProviderNotFound,
                    ArchiveIntegrityError,
                    ArchiveConflict,
                    ResourceLimit,
                ),
            ):
                raise
            raise ProviderValidationError(f"Invalid RCSB metadata: {exc}") from exc
        finally:
            self.lock.release()

    def download(self, entry_id: str, revision: str) -> StructureDownload:
        identity = validate_entry_id(entry_id)
        cached, check = self._fetch(
            f"https://{self.download_host}/download/{identity}.cif",
            self.clock.monotonic() + self.retry.budget,
            fresh=True,
            validate=lambda raw: absent(
                "Coordinate revision independently checked during parsing"
            ),
        )
        assert cached.receipt is not None and check is not None
        return StructureDownload(cached.receipt, decode(cached.response), check)

    def revalidate(self, entry_id: str, revision: str) -> StructureCheck:
        entry, _, check = self._entry(
            validate_entry_id(entry_id),
            self.clock.monotonic() + self.retry.budget,
            True,
        )
        actual = source_revision(entry).value
        if actual is None:
            raise RevisionUnavailable("Cannot revalidate missing revision")
        if actual != revision:
            raise StructureSourceChanged(revision, str(actual))
        assert check is not None
        return check

    def discover(
        self,
        reference: ReferenceSnapshot,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> StructurePage:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Discovery limit must be 1..100")
        binding = BINDING + reference.content_hash.sha256 + f":{limit}:rcsb_id asc"
        start, page, previous, expires = 0, 1, "", self.clock.monotonic() + 3600
        if cursor is not None:
            state = self.cursors.resolve(cursor, binding)
            start, page, previous, expires = (
                int(state.url),
                state.page,
                state.previous,
                state.expires,
            )
        query = {
            "query": {
                "type": "terminal",
                "service": "text",
                "parameters": {
                    "attribute": (
                        "rcsb_polymer_entity_container_identifiers."
                        "reference_sequence_identifiers.database_accession"
                    ),
                    "operator": "exact_match",
                    "value": reference.protein.summary.accession,
                },
            },
            "return_type": "polymer_instance",
            "request_options": {
                "results_content_type": ["experimental"],
                "paginate": {"start": start, "rows": limit},
                "sort": [{"sort_by": "rcsb_id", "direction": "asc"}],
            },
        }
        url = SEARCH + "?" + urlencode({"json": canonical_json(query).decode()})
        deadline = self.clock.monotonic() + self.retry.budget
        items: list[ExperimentalStructureSummary] = []
        receipts: dict[str, SourceReceipt] = {}
        warnings: list[str] = []
        try:

            def validate(raw: bytes) -> Metadata:
                value = obj(provider_json(raw))
                results = array(value.get("result_set"))
                total = value.get("total_count")
                if (
                    type(total) is not int
                    or total < start + len(results)
                    or len(results) > limit
                ):
                    raise ValueError("Invalid discovery counts")
                ids = [text(obj(item).get("identifier")) for item in results]
                if (
                    ids != sorted(set(ids))
                    or (ids and ids[0] <= previous)
                    or (not ids and total > start)
                ):
                    raise ValueError("Nonprogressing discovery ordering")
                if any(
                    not re.fullmatch(r"[1-9][A-Z0-9]{3}\.[A-Za-z0-9_-]{1,64}", value)
                    for value in ids
                ):
                    raise ValueError("Unsupported/computed search identifier")
                return absent("Search is not a versioned entry")

            cached, _ = self._fetch(url, deadline, ttl=3600, validate=validate)
            if cached.response.status == 204:
                if start:
                    raise ProviderValidationError(
                        "Search changed during pagination; restart"
                    )
                return StructurePage(
                    items=(),
                    next_cursor=absent("No structures", na=True),
                    availability=Availability.COMPLETE,
                    warnings=(),
                    source_receipts=(cached.receipt,)
                    if cached.receipt is not None
                    else (),
                )
            assert cached.receipt is not None
            receipts[cached.receipt.receipt_id] = cached.receipt
            value = obj(provider_json(decode(cached.response)))
            validate(decode(cached.response))
            results = [
                text(obj(item).get("identifier")) for item in array(value["result_set"])
            ]
            total = int(str(value["total_count"]))
            for result in results:
                identity, chain = result.split(".")
                try:
                    source = self.inspect(
                        reference, identity, chain, fresh=False, _deadline=deadline
                    )
                    items.append(source.summary)
                    receipts[source.summary.source_receipt.receipt_id] = (
                        source.summary.source_receipt
                    )
                except (ProviderError, UnsupportedStructure, ProviderNotFound) as exc:
                    warnings.append(
                        f"{result}: metadata unavailable or unsupported "
                        f"({type(exc).__name__})."
                    )
            next_cursor = absent("No further results", na=True)
            if start + len(results) < total:
                if page >= 20:
                    warnings.append(
                        "20-page discovery limit reached; narrow and restart"
                    )
                else:
                    next_cursor = present(
                        self.cursors.issue(
                            binding,
                            str(start + len(results)),
                            page + 1,
                            results[-1],
                            expires,
                        )
                    )
            availability = Availability.PARTIAL if warnings else Availability.COMPLETE
        except CursorError:
            raise
        except (
            ProviderError,
            KeyError,
            ValueError,
            UnicodeError,
            RecursionError,
        ) as exc:
            if isinstance(exc, (ArchiveIntegrityError, ArchiveConflict, ResourceLimit)):
                raise
            warnings.append(
                f"RCSB discovery unavailable ({type(exc).__name__}); retry discovery."
            )
            availability, next_cursor = (
                Availability.UNAVAILABLE,
                absent("Restart discovery after provider recovery"),
            )
        return StructurePage(
            items=tuple(items),
            next_cursor=next_cursor,
            availability=availability,
            warnings=tuple(warnings),
            source_receipts=tuple(receipts.values()),
        )
