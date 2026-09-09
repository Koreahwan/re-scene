import asyncio

import pytest

from apps.api.request_limits import RequestBodyLimitMiddleware


@pytest.mark.asyncio
@pytest.mark.parametrize("headers,chunks,status,forwarded", [
    ([(b"content-length", b"5")], [b"hello"], 200, True),
    ([], [b"he", b"llo"], 200, True),
    ([], [b"hello", b"!"], 413, False),
    ([(b"content-length", b"6")], [], 413, False),
    ([(b"content-length", b"-1")], [], 400, False),
    ([(b"content-length", b"0"), (b"content-length", b"0")], [], 400, False),
    ([(b"content-length", b"5")], [b"a"], 400, False),
    ([(b"content-length", b"1")], [b"abc"], 400, False),
])
async def test_request_limits(headers, chunks, status, forwarded):
    calls, responses = [], []
    messages = [{"type": "http.request", "body": body, "more_body": i < len(chunks) - 1}
                for i, body in enumerate(chunks)]

    async def receive():
        assert messages, "Rejected headers must not trigger a body read"
        return messages.pop(0)

    async def send(message):
        responses.append(message)

    async def endpoint(scope, receive, send):
        calls.append((await receive())["body"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    await RequestBodyLimitMiddleware(endpoint, max_bytes=5)(
        {"type": "http", "method": "POST", "headers": headers}, receive, send)
    assert responses[0]["status"] == status
    assert bool(calls) == forwarded
    if forwarded:
        assert calls[0] == b"".join(chunks)


@pytest.mark.asyncio
async def test_body_receive_timeout():
    responses = []

    async def receive():
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b""}

    async def endpoint(*args):
        pytest.fail("Timed-out body must not reach the application")

    async def send(message):
        responses.append(message)

    await RequestBodyLimitMiddleware(endpoint, timeout_seconds=0.01)(
        {"type": "http", "method": "POST", "headers": []}, receive, send)
    assert responses[0]["status"] == 408
