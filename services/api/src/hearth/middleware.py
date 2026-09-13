"""Bounded request bodies, including chunked requests without Content-Length."""

from uuid import uuid4

from starlette.responses import JSONResponse

from hearth.contracts import ErrorDetail, ErrorResponse


class BodyLimitMiddleware:
    def __init__(self, app, maximum_bytes=1_048_576):
        self.app, self.maximum_bytes = app, maximum_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        content = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            content.extend(message.get("body", b""))
            if len(content) > self.maximum_bytes:
                trace_id = scope.get("state", {}).get("trace_id", uuid4())
                body = ErrorResponse(error=ErrorDetail(code="body_too_large", message="This request exceeds the permitted size.", trace_id=trace_id))
                response = JSONResponse(body.model_dump(mode="json"), status_code=413)
                return await response(scope, receive, send)
            if not message.get("more_body", False):
                break
        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(content), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
