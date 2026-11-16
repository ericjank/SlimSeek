import asyncio
import hashlib
import math
from pathlib import Path

from .config import Settings
from .documents import parse_document
from .errors import DocumentError, DuplicateDocumentError, ProviderError
from .providers import ModelProvider
from .schemas import CitationOut, DocumentOut, QueryResponse
from .storage import DocumentRecord, SearchMatch, Store


SYSTEM_PROMPT = """你是 SlimSeek 知识库助手。只能依据用户消息中的上下文回答问题，不得使用上下文之外的知识补充事实。
每个关键事实后使用 [1]、[2] 等标记注明对应来源。可以综合多个来源，但不要编造引用。
如果上下文不足以回答问题，请明确说明知识库中没有足够信息，并指出缺少什么。
使用与用户问题相同的语言，回答简洁清晰。"""


class SlimSeekService:
    def __init__(self, settings: Settings, store: Store, provider: ModelProvider):
        self.settings = settings
        self.store = store
        self.provider = provider
        self._lock = asyncio.Lock()

    @staticmethod
    def _document_out(document: DocumentRecord) -> DocumentOut:
        return DocumentOut(
            id=document.id,
            filename=document.filename,
            size=document.size,
            chunk_count=document.chunk_count,
            created_at=document.created_at,
        )

    def list_documents(self) -> list[DocumentOut]:
        return [self._document_out(item) for item in self.store.list_documents()]

    async def import_document(self, filename: str, content: bytes) -> DocumentOut:
        async with self._lock:
            filename = Path(filename).name
            if len(content) > self.settings.upload_max_mb * 1024 * 1024:
                raise DocumentError(
                    f"文件不能超过 {self.settings.upload_max_mb} MB"
                )
            digest = hashlib.sha256(content).hexdigest()
            if self.store.find_by_hash(digest):
                raise DuplicateDocumentError("该文件已经导入，无需重复上传")
            chunks = parse_document(
                filename,
                content,
                self.settings.chunk_size,
                self.settings.chunk_overlap,
            )

            embeddings = []
            for start in range(0, len(chunks), 32):
                embeddings.extend(
                    await self.provider.embed(
                        [chunk.text for chunk in chunks[start : start + 32]]
                    )
                )
            self._validate_embeddings(embeddings, len(chunks))

            document_id = hashlib.sha256(
                f"{digest}:{filename}:{len(content)}".encode()
            ).hexdigest()[:32]
            stored_name = f"{document_id}{Path(filename).suffix.lower()}"
            path = self.store.uploads_dir / stored_name
            path.write_bytes(content)
            try:
                document = self.store.add_document(
                    filename=filename,
                    stored_name=stored_name,
                    sha256=digest,
                    size=len(content),
                    chunks=chunks,
                    embeddings=embeddings,
                    provider=self.settings.provider,
                    model=self.settings.embedding_model,
                )
            except Exception:
                path.unlink(missing_ok=True)
                raise
            return self._document_out(document)

    @staticmethod
    def _validate_embeddings(embeddings: list[list[float]], expected: int) -> None:
        if len(embeddings) != expected or not embeddings:
            raise ProviderError("嵌入接口返回的数量与文本块数量不一致")
        try:
            dimensions = len(embeddings[0])
            if dimensions == 0:
                raise ValueError
            for vector in embeddings:
                if len(vector) != dimensions:
                    raise ValueError
                values = [float(value) for value in vector]
                if not all(math.isfinite(value) for value in values):
                    raise ValueError
                vector[:] = values
        except (TypeError, ValueError):
            raise ProviderError("嵌入接口返回了无效或不一致的向量") from None

    async def delete_document(self, document_id: str) -> None:
        async with self._lock:
            document = self.store.delete_document(document_id)
            (self.store.uploads_dir / document.stored_name).unlink(missing_ok=True)

    async def query(self, question: str, top_k: int) -> QueryResponse:
        async with self._lock:
            if self.store.document_count() == 0:
                return QueryResponse(
                    answer="知识库中还没有文档，请先导入文档。", citations=[]
                )
            embeddings = await self.provider.embed([question])
            self._validate_embeddings(embeddings, 1)
            matches = self.store.search(
                embeddings[0],
                top_k,
                self.settings.provider,
                self.settings.embedding_model,
            )

        if not matches:
            return QueryResponse(answer="没有检索到相关内容。", citations=[])

        citations, context = self._build_context(matches)
        user_prompt = (
            f"问题：{question}\n\n"
            "上下文：\n"
            f"{context}\n\n"
            "请依据上下文回答，并在关键事实后标注来源编号。"
        )
        answer = await self.provider.chat(SYSTEM_PROMPT, user_prompt)
        return QueryResponse(answer=answer, citations=citations)

    def _build_context(
        self, matches: list[SearchMatch]
    ) -> tuple[list[CitationOut], str]:
        citations = []
        blocks = []
        used = 0
        for match in matches:
            location = (
                f"，第 {match.page_start} 页" if match.page_start else ""
            )
            block = (
                f"[{len(citations) + 1}] 文档：{match.filename}{location}\n"
                f"{match.text}"
            )
            if blocks and used + len(block) + 2 > self.settings.context_max_chars:
                break
            if len(block) > self.settings.context_max_chars:
                block = block[: self.settings.context_max_chars]
            blocks.append(block)
            used += len(block) + 2
            citations.append(
                CitationOut(
                    document_id=match.document_id,
                    filename=match.filename,
                    chunk_index=match.chunk_index,
                    page_start=match.page_start,
                    page_end=match.page_end,
                    text=match.text,
                    score=max(-1.0, min(1.0, 1.0 - match.distance)),
                )
            )
        return citations, "\n\n".join(blocks)
