from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database import engine
from app.errors import AppError
from app.logging import configure_logging
from app.middleware import TraceIdMiddleware
from app.response import failure, success
from app.api import assets, auth, model_settings, projects, testing
from app.ws import router as ws_router

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.upload_root.mkdir(parents=True, exist_ok=True)
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceIdMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(projects.router, prefix=settings.api_prefix)
app.include_router(assets.router, prefix=settings.api_prefix)
app.include_router(testing.router, prefix=settings.api_prefix)
app.include_router(model_settings.router, prefix=settings.api_prefix)
app.include_router(ws_router)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=failure(exc.code, exc.message, exc.details, request.state.trace_id))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    errors = [
        {key: value for key, value in item.items() if key not in {"input", "url"}}
        for item in exc.errors()
    ]
    return JSONResponse(status_code=422, content=failure("VALIDATION_ERROR", "请求参数校验失败", errors, request.state.trace_id))


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException):
    code = "METHOD_NOT_ALLOWED" if exc.status_code == 405 else "ROUTE_NOT_FOUND"
    message = "请求方法不被支持" if exc.status_code == 405 else "路由不存在"
    return JSONResponse(status_code=exc.status_code, content=failure(code, message, trace_id=request.state.trace_id))


@app.get("/health")
async def health(request: Request):
    return success({"status": "ok", "service": settings.app_name}, request.state.trace_id)
