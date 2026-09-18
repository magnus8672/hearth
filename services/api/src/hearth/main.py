import contextlib
import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from hearth import __version__
from hearth.channels import router as channels_router
from hearth.chat import router as chat_router
from hearth.client_api import router as client_api_router
from hearth.client_keys import router as client_keys_router
from hearth.config import Settings, get_settings
from hearth.contracts import ErrorDetail, ErrorResponse
from hearth.database import make_engine, verify_application_role
from hearth.head_settings import router as head_settings_router
from hearth.identity import router as identity_router
from hearth.images import router as images_router
from hearth.inference import ProviderError
from hearth.memory import router as memory_router
from hearth.middleware import BodyLimitMiddleware, request_body_limit
from hearth.notes import router as notes_router
from hearth.policy import PolicyDenied
from hearth.providers import router as providers_router
from hearth.routing import router as routing_router
from hearth.speech import router as speech_router
from hearth.toolbox import router as toolbox_router
from hearth.transcription import router as transcription_router
from hearth.vision import router as vision_router
from hearth.workspace import router as workspace_router

logger = logging.getLogger("hearth")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings.database_url.get_secret_value()) if settings.database_url.get_secret_value() else None
        app.state.engine = engine
        app.state.inference_executor = ThreadPoolExecutor(max_workers=32, thread_name_prefix='hearth-inference')
        if engine is not None:
            verify_application_role(engine)
        checks = None
        if engine is not None and settings.farm_id and settings.audience == 'admin' and settings.mode != 'test':
            from hearth.provider_health import StartupChecks
            checks = StartupChecks(engine, settings)
        vaults = None
        if engine is not None and settings.farm_id and settings.memory_vault_path and settings.audience == 'admin' and settings.mode != 'test':
            from hearth.memory_vault import VaultProjector
            vaults = VaultProjector(engine, settings)
        if settings.audience == 'user':
            async with app.state.mcp_server.session_manager.run():
                yield
        else:
            yield
        if vaults:
            vaults.close()
        if checks:
            checks.close()
        app.state.inference_executor.shutdown(wait=True)
        if engine is not None:
            engine.dispose()

    app = FastAPI(title="hearth control plane", version=__version__, lifespan=lifespan,
                  docs_url="/docs" if settings.mode != "production" else None,
                  redoc_url=None, openapi_url="/openapi.json" if settings.mode != "production" else None)
    app.state.settings = settings
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.trace_id = uuid4()
        # Header is never accepted as a principal. Worker identity has a separate authenticated boundary.
        if request.headers.get("content-length", "0").isdigit() and int(request.headers.get("content-length", "0")) > request_body_limit(request.url.path, request.method):
            return error(request, 413, "body_too_large", "This request exceeds the permitted size.")
        response = await call_next(request)
        response.headers["X-Trace-ID"] = str(request.state.trace_id)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def error(request: Request, status: int, code: str, message: str):
        if request.url.path.startswith('/v1/'):
            from hearth.client_api import error_body
            return JSONResponse(error_body(message, code), status_code=status)
        body = ErrorResponse(error=ErrorDetail(code=code, message=message, trace_id=request.state.trace_id))
        return JSONResponse(body.model_dump(mode="json"), status_code=status)

    @app.exception_handler(PolicyDenied)
    async def denied(request: Request, exc: PolicyDenied):
        return error(request, 403, exc.code, "The current identity is not authorized for this action.")

    @app.exception_handler(ProviderError)
    async def provider_error(request: Request, exc: ProviderError):
        return error(request, 400, 'provider_rejected', str(exc))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        # Do not echo inputs, including credentials, into validation responses or logs.
        return error(request, 422, "invalid_request", "The request does not match the required contract.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error(request, exc.status_code, 'authentication_required' if exc.status_code == 401 else 'request_rejected', str(exc.detail))

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "live", "version": __version__}

    @app.get("/health/ready", tags=["health"])
    def ready(request: Request):
        engine = request.app.state.engine
        if engine is None:
            return error(request, 503, "database_unconfigured", "The control database is not configured.")
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM capabilities LIMIT 1"))
        except Exception:
            return error(request, 503, "database_unavailable", "The control database is not ready.")
        return {"status": "ready", "version": __version__}

    app.include_router(identity_router)
    app.include_router(workspace_router)
    app.include_router(head_settings_router)
    app.include_router(providers_router)
    app.include_router(routing_router)
    app.include_router(chat_router)
    app.include_router(vision_router)
    app.include_router(speech_router)
    app.include_router(transcription_router)
    app.include_router(memory_router)
    app.include_router(notes_router)
    app.include_router(channels_router)
    app.include_router(images_router)
    app.include_router(client_keys_router)
    app.include_router(client_api_router)
    app.include_router(toolbox_router)
    if settings.audience == 'user':
        from starlette.routing import Route

        from hearth.mcp_gateway import create_gateway
        app.state.mcp_server, gateway = create_gateway(app)
        app.router.routes.append(Route('/mcp', gateway, methods=['GET', 'POST', 'DELETE']))

    return app


def main():
    import uvicorn
    uvicorn.run("hearth.main:create_app", factory=True, host="127.0.0.1", port=8080, access_log=False)


if __name__ == "__main__":
    main()
