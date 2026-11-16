import sqlite3
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import sqlite_vec

from .documents import ParsedChunk
from .errors import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    IndexCompatibilityError,
)


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    filename: str
    stored_name: str
    sha256: str
    size: int
    chunk_count: int
    created_at: str


@dataclass(frozen=True)
class SearchMatch:
    document_id: str
    filename: str
    chunk_index: int
    page_start: int | None
    page_end: int | None
    text: str
    distance: float


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.uploads_dir = data_dir / "uploads"
        self.database_path = data_dir / "slimseek.db"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    sha256 TEXT NOT NULL UNIQUE,
                    size INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    page_start INTEGER,
                    page_end INTEGER,
                    text TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chunks_document_idx
                    ON chunks(document_id);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        return connection

    @staticmethod
    def _serialize(vector: list[float]) -> bytes:
        return struct.pack(f"<{len(vector)}f", *vector)

    @staticmethod
    def _document(row: sqlite3.Row) -> DocumentRecord:
        return DocumentRecord(**dict(row))

    @staticmethod
    def _check_compatibility(
        connection: sqlite3.Connection, provider: str, model: str, dimensions: int | None
    ) -> None:
        values = dict(
            connection.execute(
                "SELECT key, value FROM metadata WHERE key IN "
                "('embedding_provider', 'embedding_model', 'embedding_dimensions')"
            ).fetchall()
        )
        if not values:
            return
        expected = (provider, model)
        actual = (values.get("embedding_provider"), values.get("embedding_model"))
        if actual != expected or (
            dimensions is not None
            and values.get("embedding_dimensions") != str(dimensions)
        ):
            raise IndexCompatibilityError(
                "当前嵌入配置与已有索引不一致，请使用新数据目录，或删除全部文档后重新导入"
            )

    def find_by_hash(self, sha256: str) -> DocumentRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE sha256 = ?", (sha256,)
            ).fetchone()
        return self._document(row) if row else None

    def get_document(self, document_id: str) -> DocumentRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        if not row:
            raise DocumentNotFoundError("文档不存在或已删除")
        return self._document(row)

    def list_documents(self) -> list[DocumentRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM documents ORDER BY created_at DESC"
            ).fetchall()
        return [self._document(row) for row in rows]

    def document_count(self) -> int:
        with self._connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def add_document(
        self,
        filename: str,
        stored_name: str,
        sha256: str,
        size: int,
        chunks: list[ParsedChunk],
        embeddings: list[list[float]],
        provider: str,
        model: str,
    ) -> DocumentRecord:
        document_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        dimensions = len(embeddings[0])
        with self._connect() as connection:
            if connection.execute(
                "SELECT 1 FROM documents WHERE sha256 = ?", (sha256,)
            ).fetchone():
                raise DuplicateDocumentError("该文件已经导入，无需重复上传")
            self._check_compatibility(connection, provider, model, dimensions)
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
                f"USING vec0(embedding float[{dimensions}])"
            )
            connection.executemany(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                [
                    ("embedding_provider", provider),
                    ("embedding_model", model),
                    ("embedding_dimensions", str(dimensions)),
                ],
            )
            connection.execute(
                "INSERT INTO documents"
                "(id, filename, stored_name, sha256, size, chunk_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    document_id,
                    filename,
                    stored_name,
                    sha256,
                    size,
                    len(chunks),
                    created_at,
                ),
            )
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                cursor = connection.execute(
                    "INSERT INTO chunks"
                    "(document_id, chunk_index, page_start, page_end, text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        document_id,
                        index,
                        chunk.page_start,
                        chunk.page_end,
                        chunk.text,
                    ),
                )
                connection.execute(
                    "INSERT INTO vec_chunks(rowid, embedding) VALUES (?, ?)",
                    (cursor.lastrowid, self._serialize(embedding)),
                )
        return DocumentRecord(
            document_id,
            filename,
            stored_name,
            sha256,
            size,
            len(chunks),
            created_at,
        )

    def delete_document(self, document_id: str) -> DocumentRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            if not row:
                raise DocumentNotFoundError("文档不存在或已删除")
            chunk_ids = [
                item[0]
                for item in connection.execute(
                    "SELECT id FROM chunks WHERE document_id = ?", (document_id,)
                ).fetchall()
            ]
            connection.executemany(
                "DELETE FROM vec_chunks WHERE rowid = ?",
                [(chunk_id,) for chunk_id in chunk_ids],
            )
            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            if connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0:
                connection.execute("DROP TABLE IF EXISTS vec_chunks")
                connection.execute(
                    "DELETE FROM metadata WHERE key IN "
                    "('embedding_provider', 'embedding_model', 'embedding_dimensions')"
                )
        return self._document(row)

    def search(
        self, embedding: list[float], top_k: int, provider: str, model: str
    ) -> list[SearchMatch]:
        with self._connect() as connection:
            self._check_compatibility(connection, provider, model, len(embedding))
            rows = connection.execute(
                "SELECT c.document_id, d.filename, c.chunk_index, "
                "c.page_start, c.page_end, c.text, "
                "vec_distance_cosine(v.embedding, ?) AS distance "
                "FROM vec_chunks v "
                "JOIN chunks c ON c.id = v.rowid "
                "JOIN documents d ON d.id = c.document_id "
                "ORDER BY distance ASC LIMIT ?",
                (self._serialize(embedding), top_k),
            ).fetchall()
        return [SearchMatch(**dict(row)) for row in rows]
