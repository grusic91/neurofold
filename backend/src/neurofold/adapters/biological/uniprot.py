"""UniProtKB REST lookup. All source parsing/transport stays outside core."""

import io
import json
import re
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import BoundedSemaphore, RLock
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

from neurofold.adapters.biological.policy import (
    BoundedCache,
    Clock,
    Cursors,
    RetryPolicy,
)
from neurofold.adapters.biological.transport import (
    MAX_DOWNLOAD,
    MAX_EXPANDED,
    MAX_HEADERS,
    Response,
    Transport,
    TransportFailure,
    TransportTimeout,
)
from neurofold.core.biological import (
    Availability,
    ProteinPage,
    ProteinRecord,
    ProteinSummary,
    validate_accession,
)
from neurofold.core.canonical import (
    CanonicalObject,
    sequence_sha256,
    sha256_bytes,
)
from neurofold.core.errors import ArchiveConflict, ArchiveIntegrityError, ResourceLimit
from neurofold.core.lookup import (
    CursorError,
    FreshProtein,
    ProviderError,
    ProviderTimeout,
    ProviderValidationError,
    SourceArchive,
    UnsupportedIdentifier,
)
from neurofold.core.provenance import (
    ArtifactDescriptor,
    ArtifactRights,
    ArtifactStore,
    ContentHash,
    EvidenceKind,
    HashEncoding,
    Metadata,
    MetadataState,
    RedistributionStatus,
    ReferenceCollection,
    SourceReceipt,
)

BASE = "https://rest.uniprot.org/uniprotkb/"
VERSION = "uniprot-rest/3"
CACHE_VERSION = VERSION + ":neurofold-biological/1:neurofold-research/1"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"
# Shared across instances in this process; workers must not multiply this limit.
PROVIDER_SLOTS = BoundedSemaphore(2)


def present(value: str | int | bool) -> Metadata:
    return Metadata(state=MetadataState.PRESENT, value=value, reason=None)


def absent(reason: str, *, na: bool = False) -> Metadata:
    return Metadata(
        state=MetadataState.NOT_APPLICABLE if na else MetadataState.UNAVAILABLE,
        value=None,
        reason=reason,
    )


def references(values: list[str]) -> ReferenceCollection:
    return ReferenceCollection(
        state=MetadataState.PRESENT if values else MetadataState.UNAVAILABLE,
        values=tuple(sorted(set(values))),
        reason=None if values else "Not supplied by provider",
    )


def obj(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Expected provider object")
    return value


def text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError("Invalid provider text")
    return value


def positive(value: object) -> int:
    if type(value) is not int or not 0 < value <= 2**53 - 1:
        raise ValueError("Invalid provider integer")
    return value


def array(value: object) -> list[object]:
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError("Invalid provider array")
    return value


def provider_json(raw: bytes) -> object:
    # Provider annotations may contain decimal numbers; NF-08 canonical JSON
    # rules apply to our contracts, not opaque third-party annotation fields.
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate provider JSON key")
            result[key] = value
        return result

    def invalid(value: str) -> object:
        raise ValueError("Nonfinite provider number: " + value)

    value: object = json.loads(
        raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid
    )
    return value


def decode(response: Response) -> bytes:
    if len(response.body) > MAX_DOWNLOAD:
        raise ProviderValidationError("Download exceeds limit")
    length = response.headers.get("content-length")
    if length is not None:
        try:
            if int(length) != len(response.body):
                raise ValueError
        except ValueError as exc:
            raise ProviderValidationError("Invalid/truncated Content-Length") from exc
    encoding = response.headers.get("content-encoding", "identity").lower()
    if encoding == "identity":
        return response.body
    if encoding != "gzip":
        raise ProviderValidationError("Unsupported Content-Encoding")
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        expanded = decoder.decompress(response.body, MAX_EXPANDED + 1)
        if len(expanded) > MAX_EXPANDED or not decoder.eof or decoder.unused_data:
            raise ValueError("Expanded/truncated/multiple gzip members")
        return expanded
    except (ValueError, zlib.error) as exc:
        raise ProviderValidationError(
            "Invalid gzip or decompression limit exceeded"
        ) from exc


@dataclass(frozen=True)
class Cached:
    response: Response
    receipt: SourceReceipt | None
    expires: float
    headers: Mapping[str, str]


class UniProtCatalog:
    def __init__(
        self,
        transport: Transport,
        artifacts: ArtifactStore,
        archive: SourceArchive,
        *,
        clock: Clock | None = None,
        retry: RetryPolicy | None = None,
        cache: BoundedCache[Cached] | None = None,
        new_id: Callable[[], str] = lambda: uuid4().hex,
        cursor_token: Callable[[], str] | None = None,
        evidence: EvidenceKind = EvidenceKind.EXPERIMENTAL,
    ) -> None:
        self.transport, self.artifacts, self.archive = transport, artifacts, archive
        self.clock, self.retry, self.new_id, self.evidence = (
            clock or Clock(),
            retry or RetryPolicy(),
            new_id,
            evidence,
        )
        self.cache = cache if cache is not None else BoundedCache()
        self.cursors = (
            Cursors(self.clock)
            if cursor_token is None
            else Cursors(self.clock, cursor_token)
        )
        self.lock = RLock()

    def _request(
        self, url: str, headers: Mapping[str, str], deadline: float
    ) -> Response:
        remaining = deadline - self.clock.monotonic()
        if remaining <= 0 or not PROVIDER_SLOTS.acquire(timeout=max(0, remaining)):
            raise ProviderTimeout(
                "Provider call budget exhausted waiting for concurrency slot"
            )
        try:
            timed_out = False
            for attempt in range(self.retry.retries + 1):
                remaining = deadline - self.clock.monotonic()
                if remaining <= 0:
                    raise ProviderTimeout("Provider call budget exhausted")
                try:
                    response = self.transport.request(url, headers, timeout=remaining)
                    response = Response(
                        response.status,
                        {k.lower(): v for k, v in response.headers.items()},
                        response.body,
                    )
                    if self.clock.monotonic() >= deadline:
                        raise ProviderTimeout("Provider call budget exhausted")
                    if (
                        sum(len(k) + len(v) for k, v in response.headers.items())
                        > MAX_HEADERS
                    ):
                        raise ProviderValidationError("Headers exceed limit")
                    if len(response.body) > MAX_DOWNLOAD:
                        raise ProviderValidationError("Download exceeds limit")
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
                raise ProviderTimeout("Provider deadline exceeded")
            raise ProviderError("Provider retry budget exhausted")
        finally:
            PROVIDER_SLOTS.release()

    def _fetch(
        self,
        url: str,
        *,
        ttl: int,
        fresh: bool = False,
        validate: Callable[[dict[str, object]], None] | None = None,
    ) -> tuple[Cached, int, Mapping[str, str], str]:
        # Serialize mutable cache/cursor work per catalog; provider-wide gate also
        # bounds independent catalogs. Includes lock waiting in the 15s budget.
        deadline = self.clock.monotonic() + self.retry.budget
        if not self.lock.acquire(timeout=self.retry.budget):
            raise ProviderTimeout("Provider call budget exhausted waiting for catalog")
        try:
            cached = self.cache.get(CACHE_VERSION + url)
            if (
                cached is not None
                and not fresh
                and cached.expires > self.clock.monotonic()
            ):
                return cached, 0, {}, self.clock.stamp()
            # Prefer identity: observed UniProt gzip negotiation can wrap an
            # already-compressed entity without declaring the second layer.
            # Never guess/decode an undeclared layer; retain exact received bytes.
            headers = {"accept": "application/json", "accept-encoding": "identity"}
            if cached is not None and cached.receipt is not None:
                for key in ("etag", "last-modified"):
                    if key in cached.headers:
                        headers[
                            "if-none-match" if key == "etag" else "if-modified-since"
                        ] = cached.headers[key]
            response = self._request(url, headers, deadline)
            stamp = self.clock.stamp()
            if response.status == 304:
                if (
                    cached is None
                    or cached.receipt is None
                    or response.body
                    or not any(k.startswith("if-") for k in headers)
                ):
                    raise ProviderValidationError("Unsolicited or malformed 304")
                # Keep the original 200 bytes/receipt/Link; new validators belong
                # to the validation event and replaceable cache, never the receipt.
                merged = dict(cached.headers) | dict(response.headers)
                result = Cached(
                    cached.response,
                    cached.receipt,
                    self.clock.monotonic() + ttl,
                    merged,
                )
            elif response.status == 404:
                result = Cached(response, None, self.clock.monotonic() + 300, {})
            elif 300 <= response.status < 400:
                raise UnsupportedIdentifier(
                    "Redirected identifier; explicitly select the current accession"
                )
            elif response.status != 200:
                raise ProviderError(f"Unexpected provider status {response.status}")
            else:
                if (
                    response.headers.get("content-type", "").split(";")[0].lower()
                    != "application/json"
                ):
                    raise ProviderValidationError("Expected application/json")
                # Validate fully before persisting or caching. Malformed data is
                # never retained as a valid catalog response or negative result.
                parsed = obj(provider_json(decode(response)))
                if "/search?" in url:
                    records = array(parsed.get("results"))
                    if len(records) > 100:
                        raise ValueError("Too many search results")
                    requested = parse_qs(urlsplit(url).query)
                    if len(records) > int(requested["size"][0]):
                        raise ValueError("Provider exceeded requested limit")
                    identities = [self._fields(obj(item))[0] for item in records]
                    if identities != sorted(set(identities)):
                        raise ValueError("Provider ordering mismatch")
                    next_url = self._next(
                        response.headers.get("link"),
                        {k: v[0] for k, v in requested.items() if k != "cursor"},
                    )
                    if next_url and (not records or next_url == url):
                        raise ValueError("Non-progressing provider pagination")
                else:
                    accession = self._fields(parsed)[0]
                    if accession != urlsplit(url).path.rsplit("/", 1)[1].removesuffix(
                        ".json"
                    ):
                        raise UnsupportedIdentifier(
                            "Provider substituted accession; select explicitly"
                        )
                if validate is not None:
                    validate(parsed)
                receipt = self._receipt(
                    url, response, stamp, parsed if "/search?" not in url else None
                )
                result = Cached(
                    response,
                    receipt,
                    self.clock.monotonic() + ttl,
                    dict(response.headers),
                )
            payload_size = (
                len(result.response.body)
                + (len(result.receipt.to_json()) if result.receipt is not None else 0)
                + sum(len(k) + len(v) for k, v in result.headers.items())
                + 256
            )
            self.cache.put(CACHE_VERSION + url, result, payload_size)
            return result, response.status, response.headers, stamp
        except (ValueError, KeyError, RecursionError, UnicodeError) as exc:
            if isinstance(
                exc,
                (
                    UnsupportedIdentifier,
                    ArchiveIntegrityError,
                    ArchiveConflict,
                    ResourceLimit,
                ),
            ):
                raise
            raise ProviderValidationError(f"Invalid UniProt response: {exc}") from exc
        finally:
            self.lock.release()

    def _fields(
        self, entry: dict[str, object]
    ) -> tuple[str, str, int, list[str], str | None, int | None, bool | None]:
        if (
            entry.get("inactiveReason") is not None
            or entry.get("entryType") == "Inactive"
        ):
            raise UnsupportedIdentifier(
                "Obsolete identifier; select a current entry explicitly"
            )
        accession = text(entry.get("primaryAccession"))
        validate_accession(accession)
        sequence = obj(entry.get("sequence"))
        value = sequence.get("value")
        if not isinstance(value, str) or len(value) > 100_000:
            raise ValueError("Sequence exceeds 100000 residue limit")
        sequence_sha256(value)
        length = positive(sequence.get("length"))
        if len(value) != length:
            raise ValueError("Sequence length mismatch")
        genes: list[str] = []
        for gene in array(entry.get("genes", [])):
            fields = obj(gene)
            if "geneName" in fields:
                genes.append(text(obj(fields["geneName"]).get("value")))
            for key in ("synonyms", "orderedLocusNames", "orfNames"):
                for name in array(fields.get(key, [])):
                    genes.append(text(obj(name).get("value")))
        organism = obj(entry.get("organism", {}))
        name = (
            text(organism["scientificName"]) if "scientificName" in organism else None
        )
        taxon = positive(organism["taxonId"]) if "taxonId" in organism else None
        entry_type = entry.get("entryType")
        reviewed = {
            "UniProtKB reviewed (Swiss-Prot)": True,
            "UniProtKB unreviewed (TrEMBL)": False,
        }.get(str(entry_type))
        if "entryAudit" in entry:
            for version in obj(entry["entryAudit"]).values():
                if type(version) not in (str, int):
                    raise ValueError("Invalid entry audit")
            for key in ("entryVersion", "sequenceVersion"):
                audit = obj(entry["entryAudit"])
                if key in audit:
                    positive(audit[key])
        return accession, value, length, genes, name, taxon, reviewed

    def _receipt(
        self, url: str, response: Response, stamp: str, entry: dict[str, object] | None
    ) -> SourceReceipt:
        raw_hash = sha256_bytes(response.body)
        attribution = (
            "The UniProt Consortium; "
            + url
            + "; source JSON retained; fields extracted without sequence modification."
        )
        source_license = LICENSE
        if self.evidence is EvidenceKind.SYNTHETIC:
            source_license = "Apache-2.0"
            attribution = "NeuroFold contributors; authored synthetic example"
        if entry is not None and "copyright" in entry:
            attribution += " " + text(entry["copyright"])
        artifact = ArtifactDescriptor(
            artifact_id=self.new_id(),
            content_hash=ContentHash(sha256=raw_hash, encoding=HashEncoding.RAW),
            byte_size=len(response.body),
            media_type="application/gzip"
            if response.headers.get("content-encoding", "").lower() == "gzip"
            else "application/json",
            evidence=self.evidence,
            rights=ArtifactRights(
                license=present(source_license),
                attribution=present(attribution),
                redistribution=RedistributionStatus.ALLOWED,
                basis="Authored synthetic transport"
                if self.evidence is EvidenceKind.SYNTHETIC
                else (
                    "UniProt database CC BY 4.0; reviewed 2026-11-10. "
                    "Linked third-party data requires separate review."
                ),
            ),
            parents=(),
            transformation=absent("Original HTTP entity bytes", na=True),
        )
        missing = absent("Not supplied by provider")
        audit = obj(entry.get("entryAudit", {})) if entry else {}
        organism = obj(entry.get("organism", {})) if entry else {}
        accession = text(entry["primaryAccession"]) if entry else None
        citations: list[str] = []
        if entry:
            for reference in array(entry.get("references", [])):
                citation = obj(obj(reference).get("citation", {}))
                for cross in array(citation.get("citationCrossReferences", [])):
                    crossref = obj(cross)
                    citations.append(
                        text(crossref.get("database")) + ":" + text(crossref.get("id"))
                    )
        receipt = SourceReceipt(
            receipt_id=self.new_id(),
            provider="UniProtKB",
            query=url,
            retrieved_at=stamp,
            raw_artifact=artifact,
            accession=present(accession)
            if accession
            else absent("Search response contains multiple identities", na=True),
            isoform=present(accession)
            if accession and "-" in accession
            else absent("Canonical entry", na=True),
            taxon_id=present(positive(organism["taxonId"]))
            if "taxonId" in organism
            else missing,
            entry_version=present(positive(audit["entryVersion"]))
            if "entryVersion" in audit
            else missing,
            sequence_version=present(positive(audit["sequenceVersion"]))
            if "sequenceVersion" in audit
            else missing,
            release=present(response.headers["x-uniprot-release"])
            if "x-uniprot-release" in response.headers
            else missing,
            release_date=present(response.headers["x-uniprot-release-date"])
            if "x-uniprot-release-date" in response.headers
            else missing,
            etag=present(response.headers["etag"])
            if "etag" in response.headers
            else missing,
            last_modified=present(response.headers["last-modified"])
            if "last-modified" in response.headers
            else missing,
            license_references=references([source_license]),
            citation_references=references(citations),
        )
        self.artifacts.publish(io.BytesIO(response.body), descriptor=artifact)
        self.archive.publish_receipt(receipt)
        return receipt

    def _summary(
        self, entry: dict[str, object], receipt: SourceReceipt
    ) -> ProteinSummary:
        accession, _, length, genes, name, taxon, reviewed = self._fields(entry)
        return ProteinSummary(
            accession=accession,
            canonical="-" not in accession,
            isoform=present(accession)
            if "-" in accession
            else absent("Canonical entry", na=True),
            gene_names=references(genes),
            organism_name=present(name) if name else absent("Not supplied by provider"),
            taxon_id=present(taxon) if taxon else absent("Not supplied by provider"),
            reviewed=present(reviewed)
            if reviewed is not None
            else absent("Unknown provider entry type"),
            sequence_length=length,
            source_receipt_id=receipt.receipt_id,
        )

    def _record(
        self, entry: dict[str, object], receipt: SourceReceipt
    ) -> ProteinRecord:
        sequence = self._fields(entry)[1]
        return ProteinRecord(
            summary=self._summary(entry, receipt),
            sequence=sequence,
            sequence_hash=ContentHash(
                sha256=sequence_sha256(sequence), encoding=HashEncoding.SEQUENCE
            ),
            source_receipt=receipt,
            normalization=(
                "Exact provider sequence; no case, whitespace, residue "
                "or isoform substitution"
            ),
        )

    def _get(self, accession: str, *, fresh: bool) -> FreshProtein:
        validate_accession(accession)
        if "-" in accession:
            raise UnsupportedIdentifier(
                "Isoform lookup unsupported; suffix was retained, not substituted"
            )
        cached, status, headers, stamp = self._fetch(
            BASE + accession + ".json", ttl=86400, fresh=fresh
        )
        if cached.receipt is None:
            raise KeyError(accession)
        try:
            record = self._record(
                obj(provider_json(decode(cached.response))), cached.receipt
            )
        except (ValueError, KeyError) as exc:
            if isinstance(exc, (ArchiveIntegrityError, ArchiveConflict, ResourceLimit)):
                raise
            raise ProviderValidationError("Invalid entry") from exc
        if record.summary.accession != accession:
            raise UnsupportedIdentifier(
                "Provider substituted accession; select explicitly"
            )
        return FreshProtein(
            record,
            stamp,
            304 if status == 304 else 200,
            CanonicalObject.from_value(dict(headers)),
            VERSION,
        )

    def get(self, accession: str) -> ProteinRecord:
        return self._get(accession, fresh=False).protein

    def get_fresh(self, accession: str) -> FreshProtein:
        return self._get(accession, fresh=True)

    def search(
        self,
        *,
        gene: str,
        taxon_id: int | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ProteinPage:
        if (
            not isinstance(gene, str)
            or not 1 <= len(gene) <= 128
            or any(c.isspace() or ord(c) < 32 for c in gene)
        ):
            raise ValueError("Expected one nonblank gene token, at most 128 characters")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Page limit must be 1–100")
        if taxon_id is not None:
            positive(taxon_id)
        escaped = gene.replace("\\", "\\\\").replace('"', '\\"')
        query = f'gene_exact:"{escaped}"'
        if taxon_id is not None:
            query += f" AND organism_id:{taxon_id}"
        params = {
            "query": query,
            "format": "json",
            "size": str(limit),
            "sort": "accession asc",
        }
        first_url = BASE + "search?" + urlencode(params)
        binding = CACHE_VERSION + ":" + first_url
        page, previous, expires = 1, "", self.clock.monotonic() + 3600
        url = first_url
        if cursor is not None:
            capability = self.cursors.resolve(cursor, binding)
            url, page, previous, expires = (
                capability.url,
                capability.page,
                capability.previous,
                capability.expires,
            )
        if page > 20:
            raise CursorError("Pagination limit reached")

        def validate_search(parsed: dict[str, object]) -> None:
            for item in array(parsed.get("results")):
                accession, _, _, names, _, taxon, _ = self._fields(obj(item))
                if accession <= previous:
                    raise ValueError("Provider pagination did not advance")
                if gene.casefold() not in {name.casefold() for name in names}:
                    raise ValueError("Provider gene mismatch")
                if taxon_id is not None and taxon != taxon_id:
                    raise ValueError("Provider taxon mismatch")

        cached, _, _, _ = self._fetch(url, ttl=3600, validate=validate_search)
        if cached.receipt is None:
            raise KeyError("Search endpoint absent")
        try:
            entries = array(obj(provider_json(decode(cached.response))).get("results"))
            records = [self._summary(obj(entry), cached.receipt) for entry in entries]
            if len(records) > limit:
                raise ValueError("Provider exceeded requested page limit")
            accessions = [r.accession for r in records]
            if accessions != sorted(set(accessions)) or (
                accessions and accessions[0] <= previous
            ):
                raise ValueError("Provider ordering/duplicate mismatch")
            for record in records:
                if gene.casefold() not in {
                    name.casefold() for name in record.gene_names.values
                }:
                    raise ValueError("Provider gene mismatch")
                if taxon_id is not None and record.taxon_id.value != taxon_id:
                    raise ValueError("Provider taxon mismatch")
            next_url = self._next(cached.headers.get("link"), params)
            if next_url and (not records or next_url == url):
                raise ValueError("Non-progressing provider pagination")
            warnings: tuple[str, ...]
            if next_url and page >= 20:
                next_cursor = absent(
                    "20 page/2000 result session limit reached", na=True
                )
                warnings = (
                    "Search truncated at 20 pages; narrow the query and restart.",
                )
                availability = Availability.PARTIAL
            else:
                next_cursor = (
                    present(
                        self.cursors.issue(
                            binding, next_url, page + 1, accessions[-1], expires
                        )
                    )
                    if next_url
                    else absent("No further results", na=True)
                )
                warnings, availability = (), Availability.COMPLETE
            return ProteinPage(
                items=tuple(records),
                next_cursor=next_cursor,
                availability=availability,
                warnings=warnings,
                source_receipts=(cached.receipt,),
            )
        except (ValueError, KeyError, RecursionError) as exc:
            raise ProviderValidationError(
                f"Invalid UniProt search response: {exc}"
            ) from exc

    def _next(self, link: str | None, params: dict[str, str]) -> str | None:
        if link is None:
            return None
        matches = re.findall(r'<([^<>]+)>;\s*rel="next"', link)
        if len(matches) != 1 or len(matches[0]) > 8192:
            raise ValueError("Invalid next-page Link")
        url = matches[0]
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.netloc != "rest.uniprot.org"
            or parts.path != "/uniprotkb/search"
            or parts.fragment
        ):
            raise ValueError("Forbidden pagination destination")
        received = parse_qs(parts.query, strict_parsing=True)
        expected = {k: [v] for k, v in params.items()}
        token = received.pop("cursor", [])
        if received != expected or len(token) != 1 or not 1 <= len(token[0]) <= 1024:
            raise ValueError("Pagination query/order mismatch")
        # Rebuild rather than blindly dereference a provider-supplied URL.
        return BASE + "search?" + urlencode(params | {"cursor": token[0]})
