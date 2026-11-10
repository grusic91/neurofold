"""Authored synthetic provider events; never live compatibility/scientific evidence."""

import asyncio
import gzip
import io
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

from neurofold.adapters.biological.policy import BoundedCache, Clock, RetryPolicy
from neurofold.adapters.biological.storage import FilesystemStore
from neurofold.adapters.biological.transport import (
    MAX_DOWNLOAD,
    MAX_EXPANDED,
    MAX_HEADERS,
    HttpxTransport,
    Response,
    TransportFailure,
)
from neurofold.adapters.biological.uniprot import BASE, Cached, UniProtCatalog
from neurofold.application.references import ReferenceService
from neurofold.core.biological import Availability
from neurofold.core.canonical import sequence_sha256
from neurofold.core.lookup import (
    CursorError,
    ProviderError,
    ProviderValidationError,
    SourceChanged,
    UnsupportedIdentifier,
)
from neurofold.core.provenance import EvidenceKind, MetadataState

FIXTURE = Path(__file__).parent / "fixtures/uniprot-synthetic-v1.json"


def entry(accession: str = "P00001", **changes: object) -> dict[str, object]:
    value: dict[str, object] = json.loads(FIXTURE.read_bytes())
    value["primaryAccession"] = accession
    return value | changes


def response(value: object = None, status: int = 200, /, **headers: str) -> Response:
    return Response(
        status,
        {"content-type": "application/json", **headers},
        b"" if value is None else json.dumps(value).encode(),
    )


class Time:
    def __init__(self) -> None:
        self.seconds = 0.0
        self.sleeps: list[float] = []
        self.clock = Clock(
            lambda: self.seconds,
            lambda: (
                datetime(2026, 11, 10, tzinfo=UTC) + timedelta(seconds=self.seconds)
            ),
            self.sleep,
        )

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.seconds += seconds


class Fake:
    def __init__(self, *events: Response | Exception) -> None:
        self.events = list(events)
        self.calls: list[tuple[str, Mapping[str, str], float]] = []

    def request(
        self, url: str, headers: Mapping[str, str], *, timeout: float
    ) -> Response:
        self.calls.append((url, headers, timeout))
        assert self.events, "Unexpected transport call"
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event


def catalog(
    tmp_path: Path,
    fake: Fake,
    time: Time | None = None,
    cache: BoundedCache[Cached] | None = None,
    retry: RetryPolicy | None = None,
) -> tuple[UniProtCatalog, FilesystemStore, Time]:
    time = time or Time()
    store = FilesystemStore(tmp_path / "data")
    client = UniProtCatalog(
        fake,
        store.artifact_store,
        store,
        clock=time.clock,
        retry=retry or RetryPolicy(jitter=lambda: 0.0),
        cache=cache,
        evidence=EvidenceKind.SYNTHETIC,
    )
    return client, store, time


def next_link(
    gene: str = "SYNTH",
    *,
    cursor: str = "upstream+opaque",
    limit: int = 20,
    taxon: int | None = None,
) -> str:
    query = f'gene_exact:"{gene}"' + (f" AND organism_id:{taxon}" if taxon else "")
    params = {
        "query": query,
        "format": "json",
        "size": str(limit),
        "sort": "accession asc",
        "cursor": cursor,
    }
    return f'<{BASE}search?{urlencode(params)}>; rel="next"'


def test_lookup_raw_identity_receipt_and_unknowns(tmp_path: Path) -> None:
    raw = FIXTURE.read_bytes()
    fake = Fake(
        Response(
            200,
            {
                "Content-Type": "application/json",
                "ETag": '"a"',
                "x-uniprot-release": "synthetic-1",
            },
            raw,
        )
    )
    client, store, _ = catalog(tmp_path, fake)
    protein = client.get("P00001")
    assert protein.sequence == "ACDEFG"
    assert (
        protein.sequence_hash.sha256
        == "443c1c9d0b0605f650b20465b79e545d06dd27fc1cb01984a516aef66266a318"
    )
    receipt = protein.source_receipt
    assert receipt.entry_version.value == 2
    assert receipt.etag.value == '"a"'
    assert receipt.release.value == "synthetic-1"
    assert receipt.citation_references.state is MetadataState.UNAVAILABLE
    with store.artifact_store.open(receipt.raw_artifact.artifact_id) as source:
        assert source.read() == raw
    assert store.get_receipt(receipt.receipt_id) == receipt
    assert client.get("P00001") == protein
    assert len(fake.calls) == 1
    assert fake.calls[0][0] == BASE + "P00001.json"
    assert fake.calls[0][2] == 15


@pytest.mark.parametrize(
    "accession", ["../P00001", "p00001", "P00001?evil=1", "P00001-0", ""]
)
def test_invalid_identifier_never_fetches(tmp_path: Path, accession: str) -> None:
    client, _, _ = catalog(tmp_path, Fake())
    with pytest.raises(ValueError):
        client.get(accession)


def test_isoform_and_obsolete_and_substitution(tmp_path: Path) -> None:
    fake = Fake(
        response({"entryType": "Inactive", "inactiveReason": {"reason": "DELETED"}}),
        response(entry("P00002")),
        response(None, 301, location=BASE + "P00002.json"),
    )
    client, _, _ = catalog(tmp_path, fake)
    for accession in ("P00001-2",):
        with pytest.raises(UnsupportedIdentifier, match="suffix"):
            client.get(accession)
    for _ in range(3):
        with pytest.raises(UnsupportedIdentifier):
            client.get("P00001")
    assert len(fake.calls) == 3
    assert not client.cache.entries


def test_search_multiple_hits_isoforms_taxon_and_empty(tmp_path: Path) -> None:
    fake = Fake(
        response({"results": [entry(), entry("P00001-2"), entry("P00002")]}),
        response({"results": []}),
    )
    client, _, _ = catalog(tmp_path, fake)
    page = client.search(gene="SYNTH", taxon_id=1)
    assert [p.accession for p in page.items] == ["P00001", "P00001-2", "P00002"]
    assert page.items[1].isoform.value == "P00001-2"
    assert page.availability is Availability.COMPLETE
    assert page.next_cursor.state is MetadataState.NOT_APPLICABLE
    assert parse_qs(urlsplit(fake.calls[0][0]).query)["query"] == [
        'gene_exact:"SYNTH" AND organism_id:1'
    ]
    assert not client.search(gene="MISSING").items


@pytest.mark.parametrize("gene", ['X"OR:evil', r"X\Y", "X+Y&Z", "X:*()", "α"])
def test_query_escaping(tmp_path: Path, gene: str) -> None:
    fake = Fake(response({"results": []}))
    client, _, _ = catalog(tmp_path, fake)
    client.search(gene=gene)
    query = parse_qs(urlsplit(fake.calls[0][0]).query)["query"][0]
    escaped = gene.replace("\\", "\\\\").replace('"', '\\"')
    assert query == f'gene_exact:"{escaped}"'
    assert len(parse_qs(urlsplit(fake.calls[0][0]).query)) == 4


@pytest.mark.parametrize(
    "kwargs",
    [
        {"gene": ""},
        {"gene": "two words"},
        {"gene": "x" * 129},
        {"gene": "x\x00"},
        {"gene": "X", "limit": True},
        {"gene": "X", "limit": 101},
        {"gene": "X", "taxon_id": -1},
        {"gene": "X", "taxon_id": True},
    ],
)
def test_search_input_bounds(tmp_path: Path, kwargs: dict[str, object]) -> None:
    client, _, _ = catalog(tmp_path, Fake())
    with pytest.raises(ValueError):
        client.search(**kwargs)  # type: ignore[arg-type]


def test_pagination_binding_expiry_and_provider_tokens(tmp_path: Path) -> None:
    fake = Fake(
        response({"results": [entry()]}, link=next_link()),
        response({"results": [entry("P00002")]}),
    )
    client, _, time = catalog(tmp_path, fake)
    first = client.search(gene="SYNTH")
    token = str(first.next_cursor.value)
    assert "upstream" not in token
    for kwargs in (
        {"gene": "OTHER"},
        {"gene": "SYNTH", "taxon_id": 1},
        {"gene": "SYNTH", "limit": 1},
    ):
        with pytest.raises(CursorError, match="Restart"):
            client.search(cursor=token, **kwargs)
    second = client.search(gene="SYNTH", cursor=token)
    assert second.items[0].accession == "P00002"
    assert parse_qs(urlsplit(fake.calls[1][0]).query)["cursor"] == ["upstream+opaque"]
    time.seconds = 3600
    with pytest.raises(CursorError, match="Expired.*Restart"):
        client.search(gene="SYNTH", cursor=token)
    for token in ("unknown", "", "x" * 2049):
        with pytest.raises(CursorError, match="Restart"):
            client.search(gene="SYNTH", cursor=token)


@pytest.mark.parametrize(
    "link",
    [
        '<http://rest.uniprot.org/uniprotkb/search?x=y>; rel="next"',
        '<https://evil.invalid/search?x=y>; rel="next"',
        '<https://rest.uniprot.org@evil.invalid/uniprotkb/search?x=y>; rel="next"',
        '<https://rest.uniprot.org/uniprotkb/search?x=y>; rel="next"',
        "broken",
        next_link("WRONG"),
        next_link(cursor="x" * 1025),
    ],
)
def test_forbidden_next_links(tmp_path: Path, link: str) -> None:
    client, _, _ = catalog(tmp_path, Fake(response({"results": [entry()]}, link=link)))
    with pytest.raises(ProviderValidationError):
        client.search(gene="SYNTH")
    assert not client.cache.entries


@pytest.mark.parametrize(
    "results",
    [
        [entry("P00002"), entry()],
        [entry(), entry()],
        [entry(genes=[{"geneName": {"value": "WRONG"}}])],
        [entry(organism={"taxonId": 2})],
    ],
)
def test_search_rejects_order_gene_taxon_mismatch(
    tmp_path: Path, results: list[object]
) -> None:
    client, _, _ = catalog(tmp_path, Fake(response({"results": results})))
    with pytest.raises(ProviderValidationError):
        client.search(gene="SYNTH", taxon_id=1)
    assert not client.cache.entries


def test_conditional_304_and_fresh_pin_audit(tmp_path: Path) -> None:
    fake = Fake(
        response(
            entry(),
            etag='"original"',
            **{"last-modified": "Tue, 10 Nov 2026 00:00:00 GMT"},
        ),
        response(None, 304, etag='"checked"', **{"x-uniprot-release": "new-release"}),
    )
    client, store, time = catalog(tmp_path, fake)
    inspected = client.get("P00001")
    time.seconds = 20
    service = ReferenceService(client, store, store, new_id=lambda: "reference-1")
    pinned = service.pin("P00001", inspected.sequence_hash.sha256)
    assert pinned.protein == inspected
    assert pinned.captured_at != inspected.source_receipt.retrieved_at
    assert fake.calls[1][1]["if-none-match"] == '"original"'
    assert "if-modified-since" in fake.calls[1][1]
    audit = store.get_pin_receipt("reference-1")
    assert audit.response_status == 304
    assert audit.response_headers.to_dict()["etag"] == '"checked"'
    assert pinned.protein.source_receipt.etag.value == '"original"'
    assert len(list(store.root.glob("artifact-*"))) == 1
    assert len(list(store.root.glob("receipt-*"))) == 1
    restarted = FilesystemStore(store.root)
    assert restarted.get("reference-1") == pinned
    restarted.publish(pinned)
    with pytest.raises(ValueError, match="Conflicting"):
        restarted.publish_pin_receipt(replace(audit, adapter_version="different"))


def test_ttl_24_hours_search_hour_and_404_five_minutes(tmp_path: Path) -> None:
    fake = Fake(
        response(entry(), etag="a"),
        response(None, 304),
        response({"results": []}, etag="search"),
        response(None, 304),
        response(None, 404),
        response(entry("P00002")),
    )
    client, _, time = catalog(tmp_path, fake)
    original = client.get("P00001")
    time.seconds = 86399
    assert client.get("P00001") == original
    time.seconds = 86400
    assert client.get("P00001") == original
    client.search(gene="SYNTH")
    time.seconds += 3599
    client.search(gene="SYNTH")
    time.seconds += 1
    client.search(gene="SYNTH")
    with pytest.raises(KeyError):
        client.get("P00002")
    time.seconds += 299
    with pytest.raises(KeyError):
        client.get("P00002")
    time.seconds += 1
    assert client.get("P00002").summary.accession == "P00002"
    assert len(fake.calls) == 6


def test_fresh_pin_ignores_negative_and_positive_cache_and_source_changes(
    tmp_path: Path,
) -> None:
    changed = entry(
        sequence={"value": "ACDEFA", "length": 6},
        entryAudit={"entryVersion": 3, "sequenceVersion": 2},
    )
    fake = Fake(
        response(entry()),
        response(changed),
        response(changed),
        response(None, 503),
        response(None, 503),
        response(None, 503),
    )
    client, store, _ = catalog(tmp_path, fake)
    old = client.get("P00001")
    service = ReferenceService(client, store, store)
    with pytest.raises(SourceChanged) as conflict:
        service.pin("P00001", old.sequence_hash.sha256)
    assert conflict.value.actual == sequence_sha256("ACDEFA")
    pinned = service.pin("P00001", sequence_sha256("ACDEFA"))
    assert pinned.protein.source_receipt.entry_version.value == 3
    client.cache.entries.clear()
    with pytest.raises(ProviderError):
        service.pin("P00001", sequence_sha256("ACDEFA"))
    assert service.get(pinned.reference_id) == pinned
    with pytest.raises(UnsupportedIdentifier):
        service.pin("P00001-2", old.sequence_hash.sha256)
    with pytest.raises(ValueError):
        service.pin("P00001", "invalid")


@pytest.mark.parametrize(
    "failure",
    [
        TransportFailure("timeout"),
        response(None, 429),
        response(None, 502),
        response(None, 503),
        response(None, 504),
    ],
)
def test_two_retries_then_success(
    tmp_path: Path, failure: Response | Exception
) -> None:
    fake = Fake(failure, failure, response(entry()))
    client, _, time = catalog(tmp_path, fake)
    client.get("P00001")
    assert time.sleeps == [0.25, 0.5]
    assert [call[2] for call in fake.calls] == [15, 14.75, 14.25]


def test_retry_after_bounded_dates_and_budget_exhaustion(tmp_path: Path) -> None:
    fake = Fake(
        response(None, 429, **{"retry-after": "999999"}),
        response(None, 503, **{"retry-after": "Tue, 10 Nov 2026 00:00:10 GMT"}),
        response(None, 503),
        response(entry()),
    )
    client, _, time = catalog(tmp_path, fake)
    with pytest.raises(ProviderError, match="budget"):
        client.get("P00001")
    assert time.sleeps == [5.0, 5.0]
    assert not client.cache.entries
    assert client.get("P00001").sequence == "ACDEFG"
    fake2 = Fake(response(None, 429, **{"retry-after": "9"}))
    other, _, clock = catalog(tmp_path / "other", fake2, retry=RetryPolicy(budget=1))
    with pytest.raises(ProviderError):
        other.get("P00001")
    assert not clock.sleeps


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 500])
def test_no_retry_other_statuses(tmp_path: Path, status: int) -> None:
    fake = Fake(response(None, status))
    client, _, time = catalog(tmp_path, fake)
    with pytest.raises(KeyError if status == 404 else ProviderError):
        client.get("P00001")
    assert len(fake.calls) == 1
    assert not time.sleeps


@pytest.mark.parametrize(
    "bad",
    [
        Response(200, {"content-type": "text/html"}, b"x"),
        Response(200, {"content-type": "application/json"}, b'{"a":'),
        Response(200, {"content-type": "application/json"}, b'{"a":1,"a":2}'),
        response(entry(sequence={"value": "ACD", "length": 6})),
        response(entry(sequence={"value": "acd", "length": 3})),
        response(entry(organism={"taxonId": True})),
        response(entry(entryAudit={"entryVersion": 0})),
        response(entry(genes="bad")),
        response([]),
        response(None, 304),
        response(entry(), **{"content-length": "9999"}),
    ],
)
def test_malformed_responses_not_cached_or_retried(
    tmp_path: Path, bad: Response
) -> None:
    fake = Fake(bad)
    client, _, _ = catalog(tmp_path, fake)
    with pytest.raises(ProviderValidationError):
        client.get("P00001")
    assert not client.cache.entries
    assert len(fake.calls) == 1


def test_gzip_original_bytes_and_resource_bounds(tmp_path: Path) -> None:
    compressed = gzip.compress(FIXTURE.read_bytes(), mtime=0)
    fake = Fake(
        Response(
            200,
            {"content-type": "application/json", "content-encoding": "gzip"},
            compressed,
        )
    )
    client, store, _ = catalog(tmp_path, fake)
    receipt = client.get("P00001").source_receipt
    assert receipt.raw_artifact.media_type == "application/gzip"
    with store.open(receipt.raw_artifact.artifact_id) as raw:
        assert raw.read() == compressed
    for number, bad in enumerate(
        [
            Response(
                200, {"content-type": "application/json"}, b"x" * (MAX_DOWNLOAD + 1)
            ),
            Response(
                200,
                {"content-type": "application/json", "x-big": "x" * MAX_HEADERS},
                b"{}",
            ),
            Response(
                200,
                {"content-type": "application/json", "content-encoding": "gzip"},
                gzip.compress(b"x" * (MAX_EXPANDED + 1)),
            ),
            Response(
                200,
                {"content-type": "application/json", "content-encoding": "gzip"},
                compressed[:-1],
            ),
            Response(
                200,
                {"content-type": "application/json", "content-encoding": "gzip"},
                compressed + compressed,
            ),
            Response(
                200,
                {"content-type": "application/json", "content-encoding": "br"},
                b"x",
            ),
            response(entry(sequence={"value": "A" * 100001, "length": 100001})),
            response({"results": [entry()] * 101}),
        ]
    ):
        other, _, _ = catalog(tmp_path / str(number), Fake(bad))
        with pytest.raises(ProviderValidationError):
            if number == 7:
                other.search(gene="SYNTH")
            else:
                other.get("P00001")


def test_unknown_metadata_and_notices_are_explicit(tmp_path: Path) -> None:
    value = entry(
        copyright="Synthetic notice",
        references=[
            {
                "citation": {
                    "citationCrossReferences": [
                        {"database": "Synthetic", "id": "citation"}
                    ]
                }
            }
        ],
        extraAnnotation={"score": 1.25},
    )
    for field in ("genes", "organism", "entryAudit", "entryType"):
        value.pop(field)
    client, store, _ = catalog(tmp_path, Fake(response(value), response(value)))
    record = client.get("P00001")
    assert record.summary.reviewed.state is MetadataState.UNAVAILABLE
    assert record.summary.taxon_id.state is MetadataState.UNAVAILABLE
    assert record.source_receipt.sequence_version.state is MetadataState.UNAVAILABLE
    assert "Synthetic notice" in str(
        record.source_receipt.raw_artifact.rights.attribution.value
    )
    assert record.source_receipt.citation_references.values == ("Synthetic:citation",)
    with pytest.raises(ValueError, match="known positive taxon|known taxon"):
        ReferenceService(client, store, store).pin(
            "P00001", record.sequence_hash.sha256
        )


def test_bounded_lru_and_policy_controls() -> None:
    cache = BoundedCache[str](max_entries=2, max_bytes=5)
    cache.put("a", "A", 2)
    cache.put("b", "B", 2)
    assert cache.get("a") == "A"
    cache.put("c", "C", 2)
    assert cache.get("b") is None
    cache.put("big", "large", 6)
    assert cache.get("big") is None
    cache.put("a", "new", 4)
    assert cache.get("c") is None
    assert cache.get("a") == "new"
    for kwargs in ({"max_entries": 129}, {"max_bytes": 0}):
        with pytest.raises(ValueError):
            BoundedCache[str](**kwargs)  # type: ignore[arg-type]
    for kwargs in ({"retries": 3}, {"budget": 16}, {"budget": 0}):
        with pytest.raises(ValueError):
            RetryPolicy(**kwargs)  # type: ignore[arg-type]
    time = Time()
    retry = RetryPolicy(jitter=lambda: 100)
    assert retry.delay(0, "invalid", time.clock) == 0.5
    assert retry.delay(0, "-9", time.clock) == 0.5
    assert retry.delay(0, "nan", time.clock) == 0.5
    assert retry.delay(0, "inf", time.clock) == 5


def test_cache_eviction_does_not_evict_pinned_archive(tmp_path: Path) -> None:
    fake = Fake(response(entry()), response(entry()), response(entry("P00002")))
    client, store, _ = catalog(tmp_path, fake, cache=BoundedCache(max_entries=1))
    service = ReferenceService(client, store, store)
    first = client.get("P00001")
    pinned = service.pin("P00001", first.sequence_hash.sha256)
    client.get("P00002")
    assert len(client.cache.entries) == 1
    assert service.get(pinned.reference_id) == pinned
    with pytest.raises(KeyError):
        store.get("missing")


def test_negative_cache_cannot_answer_fresh_pin(tmp_path: Path) -> None:
    client, store, _ = catalog(tmp_path, Fake(response(None, 404), response(entry())))
    with pytest.raises(KeyError):
        client.get("P00001")
    pinned = ReferenceService(client, store, store).pin(
        "P00001", sequence_sha256("ACDEFG")
    )
    assert pinned.protein.sequence == "ACDEFG"


def test_pagination_session_limit_and_nonprogress(tmp_path: Path) -> None:
    events = [
        response(
            {"results": [entry(f"P{number:05}")]},
            link=next_link(cursor=f"page{number}"),
        )
        for number in range(1, 21)
    ]
    client, _, _ = catalog(tmp_path, Fake(*events))
    token = None
    for _ in range(20):
        page = client.search(gene="SYNTH", cursor=token)
        token = str(page.next_cursor.value)
    assert page.availability is Availability.PARTIAL
    assert page.next_cursor.state is MetadataState.NOT_APPLICABLE
    assert "narrow" in page.warnings[0]
    other, _, _ = catalog(
        tmp_path / "other", Fake(response({"results": []}, link=next_link()))
    )
    with pytest.raises(ProviderValidationError, match="progress"):
        other.search(gene="SYNTH")
    assert not other.cache.entries
    third, _, _ = catalog(
        tmp_path / "third",
        Fake(
            response({"results": [entry()]}, link=next_link()),
            response({"results": [entry()]}),
        ),
    )
    page = third.search(gene="SYNTH")
    with pytest.raises(ProviderValidationError, match="advance"):
        third.search(gene="SYNTH", cursor=str(page.next_cursor.value))


def test_cursor_eviction_and_collision(tmp_path: Path) -> None:
    client, _, time = catalog(tmp_path, Fake())
    cursors = client.cursors
    cursors.cache = BoundedCache(max_entries=1)
    first = cursors.issue("provider1/query/order", "url", 2, "previous", 3600)
    second = cursors.issue("provider2/query/order", "url", 2, "previous", 3600)
    with pytest.raises(CursorError, match="evicted"):
        cursors.resolve(first, "provider1/query/order")
    with pytest.raises(CursorError, match="mismatch"):
        cursors.resolve(second, "provider1/query/order")
    cursors.token = lambda: second
    with pytest.raises(ValueError, match="collision"):
        cursors.issue("binding", "url", 2, "", 3600)
    time.seconds = 3600
    with pytest.raises(CursorError, match="Expired"):
        cursors.resolve(second, "provider2/query/order")


class BytesStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes, block: bool = False) -> None:
        self.chunks, self.block, self.closed = chunks, block, False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk
        if self.block:
            await asyncio.Event().wait()

    async def aclose(self) -> None:
        self.closed = True


def test_real_http_dependency_streaming_and_redirect_policy() -> None:
    stream = BytesStream(b"exact", b" bytes")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == BASE + "P00001.json"
        assert request.extensions["timeout"] == {
            "connect": 3,
            "read": 15,
            "write": 15,
            "pool": 15,
        }
        return httpx.Response(
            200, headers={"Content-Type": "application/json"}, stream=stream
        )

    transport = HttpxTransport(httpx.MockTransport(handler))
    received = transport.request(BASE + "P00001.json", {}, timeout=15)
    assert received.body == b"exact bytes"
    assert stream.closed
    redirects = HttpxTransport(
        httpx.MockTransport(
            lambda _: httpx.Response(
                302, headers={"location": "https://evil.invalid"}, stream=BytesStream()
            )
        )
    )
    assert redirects.request(BASE + "P00001.json", {}, timeout=15).status == 302


def test_http_stream_download_header_limits_deadline_and_transport_errors() -> None:
    for headers, stream in (
        ({}, BytesStream(b"x" * MAX_DOWNLOAD, b"x")),
        ({"x-large": "x" * MAX_HEADERS}, BytesStream()),
    ):
        transport = HttpxTransport(
            httpx.MockTransport(
                lambda _, h=headers, s=stream: httpx.Response(200, headers=h, stream=s)
            )
        )
        with pytest.raises(ProviderValidationError):
            transport.request(BASE + "P00001.json", {}, timeout=15)
        assert stream.closed
    blocked = BytesStream(b"partial", block=True)
    transport = HttpxTransport(
        httpx.MockTransport(lambda _: httpx.Response(200, stream=blocked))
    )
    with pytest.raises(TransportFailure):
        transport.request(BASE + "P00001.json", {}, timeout=0.01)
    assert blocked.closed

    def failed(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic connection failure")

    transport = HttpxTransport(httpx.MockTransport(failed))
    with pytest.raises(TransportFailure):
        transport.request(BASE + "P00001.json", {}, timeout=15)


def test_total_budget_and_concurrency_wait_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neurofold.adapters.biological import uniprot

    client, _, time = catalog(tmp_path, Fake(response(entry())))

    class Denied:
        def acquire(self, *, timeout: float) -> bool:
            assert timeout <= 15
            return False

    monkeypatch.setattr(uniprot, "PROVIDER_SLOTS", Denied())
    with pytest.raises(ProviderError, match="concurrency"):
        client.get("P00001")
    monkeypatch.undo()
    original = client.transport.request

    def late(url: str, headers: Mapping[str, str], *, timeout: float) -> Response:
        time.seconds += 15
        return original(url, headers, timeout=timeout)

    monkeypatch.setattr(client.transport, "request", late)
    with pytest.raises(ProviderError, match="budget"):
        client.get("P00001")
    assert not client.cache.entries


def test_actual_provider_concurrency_is_two(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    active = 0
    peak = 0
    lock = Lock()
    two_entered, release = Event(), Event()

    class Blocking:
        def request(
            self, url: str, headers: Mapping[str, str], *, timeout: float
        ) -> Response:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                if active == 2:
                    two_entered.set()
            assert release.wait(5)
            with lock:
                active -= 1
            return response(entry())

    clients = []
    for index in range(3):
        store = FilesystemStore(tmp_path / str(index) / "data")
        clients.append(
            UniProtCatalog(
                Blocking(), store.artifact_store, store, evidence=EvidenceKind.SYNTHETIC
            )
        )
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = [pool.submit(client.get, "P00001") for client in clients]
        try:
            assert two_entered.wait(5)
            assert peak == 2
        finally:
            release.set()
        assert all(result.result().sequence == "ACDEFG" for result in pending)
    assert peak == 2


def test_storage_atomic_conflicts_failures_and_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    from concurrent.futures import ThreadPoolExecutor

    from neurofold.core.canonical import canonical_json

    client, store, _ = catalog(tmp_path, Fake(response(entry())))
    descriptor = client.get("P00001").source_receipt.raw_artifact
    with store.open(descriptor.artifact_id) as source:
        raw = source.read()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            pool.submit(
                store.artifact_store.publish, io.BytesIO(raw), descriptor=descriptor
            )
            for _ in range(2)
        ]
        for result in results:
            result.result()
    with pytest.raises(ValueError, match="Conflicting"):
        store.publish_artifact(
            io.BytesIO(raw), descriptor=replace(descriptor, media_type="text/plain")
        )
    with pytest.raises(ValueError, match="checksum"):
        store.publish_artifact(io.BytesIO(b"bad"), descriptor=descriptor)
    with pytest.raises(ValueError, match="limit"):
        store.publish_artifact(
            io.BytesIO(), descriptor=replace(descriptor, byte_size=9 * 1024 * 1024)
        )
    with pytest.raises(ValueError, match="ignored"):
        FilesystemStore(tmp_path / "tracked")
    (tmp_path / "link").symlink_to(store.root, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        FilesystemStore(tmp_path / "link" / "data")
    target = store._path("artifact", descriptor.artifact_id)
    old = target.read_bytes()
    target.write_bytes(
        canonical_json({"descriptor": descriptor.to_dict(), "raw": "YmFk"})
    )
    with pytest.raises(ValueError, match="integrity"):
        store.describe(descriptor.artifact_id)
    target.write_bytes(old)

    def interrupted(*args: object) -> None:
        raise OSError("synthetic fsync interruption")

    monkeypatch.setattr(os, "fsync", interrupted)
    with pytest.raises(OSError, match="interruption"):
        store._publish("test", "unpublished", b"data")
    assert not store._path("test", "unpublished").exists()
    assert all(path.name.endswith(".json") for path in store.root.iterdir())


def test_same_sequence_new_versions_pin_actual_receipt_and_immutable_id(
    tmp_path: Path,
) -> None:
    from neurofold.core.biological import ReferenceSnapshot

    fake = Fake(
        response(entry()),
        response(entry(entryAudit={"entryVersion": 9, "sequenceVersion": 4})),
    )
    client, store, _ = catalog(tmp_path, fake)
    inspected = client.get("P00001")
    pinned = ReferenceService(client, store, store).pin(
        "P00001", inspected.sequence_hash.sha256
    )
    assert pinned.protein.sequence_hash == inspected.sequence_hash
    assert (
        pinned.protein.source_receipt.receipt_id != inspected.source_receipt.receipt_id
    )
    assert pinned.protein.source_receipt.entry_version.value == 9
    assert pinned.protein.source_receipt.sequence_version.value == 4
    with pytest.raises(ValueError, match="Conflicting"):
        store.publish(
            replace(pinned, protein=replace(pinned.protein, normalization="different"))
        )
    with pytest.raises(ValueError, match="missing"):
        store.publish(
            ReferenceSnapshot(
                reference_id="not-audited",
                protein=pinned.protein,
                captured_at=pinned.captured_at,
            )
        )
    store._path(
        "artifact", pinned.protein.source_receipt.raw_artifact.artifact_id
    ).unlink()
    with pytest.raises(ValueError, match="missing"):
        store.get(pinned.reference_id)


def test_service_rejects_catalog_identity_substitution(tmp_path: Path) -> None:
    from neurofold.core.lookup import FreshProtein

    client, store, _ = catalog(tmp_path, Fake(response(entry("P00002"))))
    fresh = client.get_fresh("P00002")

    class WrongIdentity:
        def get_fresh(self, accession: str) -> FreshProtein:
            return fresh

    with pytest.raises(UnsupportedIdentifier, match="different accession"):
        ReferenceService(WrongIdentity(), store, store).pin(
            "P00001", fresh.protein.sequence_hash.sha256
        )
