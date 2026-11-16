from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .errors import (
    DocumentError,
    DocumentNotFoundError,
    DuplicateDocumentError,
    IndexCompatibilityError,
    ProviderError,
    SlimSeekError,
)
from .providers import create_provider
from .schemas import DocumentOut, HealthOut, QueryRequest, QueryResponse
from .service import SlimSeekService
from .storage import Store


STATIC_DIR = Path(__file__).parent / "static"


def _as_http_error(error: SlimSeekError) -> HTTPException:
    if isinstance(error, DocumentNotFoundError):
        status = 404
    elif isinstance(error, (DuplicateDocumentError, IndexCompatibilityError)):
        status = 409
    elif isinstance(error, ProviderError):
        status = 503
    else:
        status = 400
    return HTTPException(status_code=status, detail=str(error))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(settings.data_dir)
        app.state.service = SlimSeekService(
            settings, store, create_provider(settings)
        )
        yield

    app = FastAPI(title="SlimSeek", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health", response_model=HealthOut)
    async def health():
        service = app.state.service
        return HealthOut(
            status="ok",
            provider=settings.provider,
            embedding_model=settings.embedding_model,
            chat_model=settings.chat_model,
            document_count=service.store.document_count(),
        )

    @app.get("/api/documents", response_model=list[DocumentOut])
    async def documents():
        return app.state.service.list_documents()

    @app.post("/api/documents", response_model=DocumentOut, status_code=201)
    async def upload_document(file: UploadFile = File(...)):
        content = await file.read(settings.upload_max_mb * 1024 * 1024 + 1)
        await file.close()
        if len(content) > settings.upload_max_mb * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"文件不能超过 {settings.upload_max_mb} MB",
            )
        try:
            return await app.state.service.import_document(
                file.filename or "upload", content
            )
        except SlimSeekError as error:
            raise _as_http_error(error) from None

    @app.delete("/api/documents/{document_id}", status_code=204)
    async def delete_document(document_id: str):
        try:
            await app.state.service.delete_document(document_id)
        except SlimSeekError as error:
            raise _as_http_error(error) from None
        return Response(status_code=204)

    @app.post("/api/query", response_model=QueryResponse)
    async def query(request: QueryRequest):
        try:
            return await app.state.service.query(request.question, request.top_k)
        except SlimSeekError as error:
            raise _as_http_error(error) from None

    return app
