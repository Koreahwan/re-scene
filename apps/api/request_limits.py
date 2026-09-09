"""Bound request buffering before JSON/image decoding, including chunked input."""
import asyncio
import time

from starlette.responses import JSONResponse


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes=2 * 1024 * 1024, timeout_seconds=15):
        self.app = app
        self.max_bytes = max_bytes
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        lengths = [value for name, value in scope.get("headers", []) if name.lower() == b"content-length"]
        invalid = len(lengths) > 1 or (lengths and (
            not lengths[0].isdigit() or len(lengths[0]) > 10))
        if invalid:
            return await JSONResponse({"detail": "Invalid Content-Length"}, 400)(scope, receive, send)
        if lengths and int(lengths[0]) > self.max_bytes:
            return await JSONResponse({"detail": "Request body too large"}, 413)(scope, receive, send)
        body = bytearray()
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=max(0, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                return await JSONResponse({"detail": "Request body timed out"}, 408)(scope, receive, send)
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                return await JSONResponse({"detail": "Request body too large"}, 413)(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        if lengths and int(lengths[0]) != len(body):
            return await JSONResponse({"detail": "Incomplete request body"}, 400)(scope, receive, send)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
