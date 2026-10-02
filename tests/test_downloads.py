import json
from dataclasses import replace

import httpx
import pytest

from ventoy_library.downloader import HTTPDownloader, import_local
from ventoy_library.errors import LibraryError, SafetyError
from ventoy_library.library import execute
from ventoy_library.planner import build_plan
from ventoy_library.state import StateStore


def partial(root, release, content):
    part = root / "image.iso.part"
    part.write_bytes(content)
    marker = root / "image.iso.part.json"
    marker.write_text(
        json.dumps(
            {
                "url": release.url,
                "size": release.size,
                "checksum": release.checksum,
                "algorithm": release.checksum_algorithm,
                "version": release.version,
            }
        )
    )
    return part


class BytesStream(httpx.SyncByteStream):
    def __init__(self, data):
        self.data = data

    def __iter__(self):
        yield self.data


def response(code=200, data=b"abc", headers=None):
    return httpx.Response(code, stream=BytesStream(data), headers=headers)


def test_stream(root, release):
    with httpx.Client(transport=httpx.MockTransport(lambda req: response())) as client:
        downloader = HTTPDownloader(client)
        events = []
        path = downloader.fetch(release, release.url, root, root / "image.part", events.append)
        assert path.read_bytes() == b"abc"
        assert events == [0, 3]


@pytest.mark.parametrize("accept_range", [True, False])
def test_resume(root, release, accept_range):
    part = partial(root, release, b"a")

    def handler(req):
        assert req.headers["Range"] == "bytes=1-"
        if accept_range:
            return response(206, b"bc", {"Content-Range": "bytes 1-2/3"})
        return response()

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        events = []
        HTTPDownloader(client).fetch(release, release.url, root, part, events.append)
    assert part.read_bytes() == b"abc"
    assert events[0] == (1 if accept_range else 0)


def test_invalid_range_preserves_partial(root, release):
    part = partial(root, release, b"a")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda req: response(206, b"bc", {"Content-Range": "bytes 0-1/3"})
        )
    ) as client:
        with pytest.raises(LibraryError, match="Content-Range"):
            HTTPDownloader(client).fetch(release, release.url, root, part, lambda n: None)
    assert part.read_bytes() == b"a"


def test_unrecognized_partial_preserved(root, release):
    part = root / "image.part"
    part.write_bytes(b"user data")
    with httpx.Client(transport=httpx.MockTransport(lambda req: response())) as client:
        with pytest.raises(SafetyError, match="Unrecognized"):
            HTTPDownloader(client).fetch(release, release.url, root, part, lambda n: None)
    assert part.read_bytes() == b"user data"


def test_no_checksum_restarts(root, release):
    release = replace(release, checksum=None, checksum_algorithm=None)
    part = partial(root, release, b"a")

    def handler(req):
        assert "Range" not in req.headers
        return response()

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        HTTPDownloader(client).fetch(release, release.url, root, part, lambda n: None)
    assert part.read_bytes() == b"abc"


def test_complete_partial_avoids_network(root, release):
    part = partial(root, release, b"abc")

    def unexpected(req):
        pytest.fail("complete checksum-backed partial should go straight to verification")

    with httpx.Client(transport=httpx.MockTransport(unexpected)) as client:
        HTTPDownloader(client).fetch(release, release.url, root, part, lambda n: None)


def test_retry_transient(root, release):
    calls = []

    def handler(req):
        calls.append(req)
        return response(503) if len(calls) == 1 else response()

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        HTTPDownloader(client, sleep=lambda t: None).fetch(
            release, release.url, root, root / "image.part", lambda n: None
        )
    assert len(calls) == 2


def test_nontransient_no_retry(root, release):
    calls = []

    def handler(req):
        calls.append(req)
        return response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(LibraryError):
            HTTPDownloader(client).fetch(
                release, release.url, root, root / "image.part", lambda n: None
            )
    assert len(calls) == 1


def test_interrupted_and_resume(root, release):
    # Use tiny chunks to exercise a streaming exception after some bytes were flushed.
    import ventoy_library.downloader as module

    original = module.CHUNK_SIZE
    module.CHUNK_SIZE = 1

    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b"a"
            raise httpx.ReadError("disconnected")

    requests = []

    def handler(req):
        requests.append(req)
        if len(requests) == 1:
            return httpx.Response(200, stream=Interrupted())
        assert req.headers["Range"] == "bytes=1-"
        return response(206, b"bc", {"Content-Range": "bytes 1-2/3"})

    try:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            part = HTTPDownloader(client, sleep=lambda n: None).fetch(
                release, release.url, root, root / "image.part", lambda n: None
            )
        assert part.read_bytes() == b"abc"
    finally:
        module.CHUNK_SIZE = original


@pytest.mark.parametrize("data", [b"ab", b"abcd"])
def test_wrong_response_size(root, release, data):
    with httpx.Client(transport=httpx.MockTransport(lambda req: response(data=data))) as client:
        with pytest.raises(LibraryError):
            HTTPDownloader(client, retries=0).fetch(
                release, release.url, root, root / "image.part", lambda n: None
            )


def test_size_detection():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, headers={"Content-Length": "123"})
        )
    ) as client:
        assert HTTPDownloader(client).size("https://example.invalid") == 123
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(405))) as client:
        assert HTTPDownloader(client).size("https://example.invalid") is None


def test_local_import(root):
    local = root / "local.iso"
    local.write_bytes(b"abc")
    part = root / "image.part"
    import_local(local, root, part, 3, lambda n: None)
    assert part.read_bytes() == b"abc" and local.read_bytes() == b"abc"
    with pytest.raises(FileExistsError):
        import_local(local, root, part, 3, lambda n: None)
    with pytest.raises(LibraryError):
        import_local(local, root, root / "wrong.part", 2, lambda n: None)
    assert not (root / "wrong.part").exists()


@pytest.mark.parametrize("keep_old", [True, False])
def test_end_to_end_local_replacement(root, provider, record, keep_old):
    from ventoy_library.safety import contained

    store = StateStore(root)
    old = replace(
        record, version="0.9", filename="old.iso", relative_path="ISO/rescue/example/old.iso"
    )
    old_path = contained(root, old.relative_path)
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(b"old")
    store.save([old])
    source = root / "local.iso"
    source.write_bytes(b"abc")
    plan = build_plan([provider], root, [old], {"example": str(source)})
    with httpx.Client(transport=httpx.MockTransport(lambda req: pytest.fail("no HTTP"))) as client:
        with store.lock():
            records = execute(plan, root, store, HTTPDownloader(client), 0, keep_old=keep_old)
    assert records[0].verification_status == "verified"
    assert records[0].acquisition_method == "local-file"
    assert old_path.exists() == keep_old
    assert contained(root, records[0].relative_path).read_bytes() == b"abc"
    assert len(store.load()) == (2 if keep_old else 1)


def test_insufficient_space_never_downloads(root, provider, monkeypatch):
    plan = build_plan([provider], root, [])
    from ventoy_library.storage import StorageReport

    monkeypatch.setattr(
        "ventoy_library.library.inspect", lambda *args: StorageReport(1, 0, 1, 0, 3, 0)
    )
    with httpx.Client(transport=httpx.MockTransport(lambda req: pytest.fail("no downloads"))) as c:
        with pytest.raises(SafetyError):
            execute(plan, root, StateStore(root), HTTPDownloader(c), 0)
    assert list(root.iterdir()) == []


def test_http_service_installs_then_records(root, provider):
    store = StateStore(root)
    plan = build_plan([provider], root, [])
    with httpx.Client(transport=httpx.MockTransport(lambda req: response())) as client:
        with store.lock():
            records = execute(plan, root, store, HTTPDownloader(client), 0)
    assert store.load() == records
    assert records[0].verification_status == "verified"
    assert not list(root.rglob("*.part*"))


def test_verification_failure_preserves_old_image(root, provider, record):
    store = StateStore(root)
    old = replace(
        record, version="0.9", filename="old.iso", relative_path="ISO/rescue/example/old.iso"
    )
    path = root / old.relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old")
    store.save([old])
    plan = build_plan([provider], root, [old])
    with httpx.Client(transport=httpx.MockTransport(lambda req: response(data=b"bad"))) as client:
        with store.lock(), pytest.raises(LibraryError, match="Checksum mismatch"):
            execute(plan, root, store, HTTPDownloader(client), 0)
    assert path.read_bytes() == b"old"
    assert store.load() == [old]
    assert not plan.items[0].destination.exists()
