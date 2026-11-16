from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from .errors import DocumentError


SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf"}


@dataclass(frozen=True)
class ParsedChunk:
    text: str
    page_start: int | None = None
    page_end: int | None = None


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()
    if not text:
        return []

    chunks = []
    start = 0
    boundaries = ("\n\n", "\n", "。", "！", "？", ".", "!", "?", " ")
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            minimum = start + size // 2
            positions = [
                (text.rfind(boundary, minimum, end), boundary)
                for boundary in boundaries
            ]
            position, boundary = max(positions, key=lambda item: item[0])
            if position >= minimum:
                end = position + len(boundary)

        value = text[start:end].strip()
        if value:
            chunks.append(value)
        if end >= len(text):
            break

        next_start = max(start + 1, end - overlap)
        while next_start < end and text[next_start].isspace():
            next_start += 1
        start = next_start

    return chunks


def parse_document(
    filename: str, content: bytes, chunk_size: int, chunk_overlap: int
) -> list[ParsedChunk]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentError("仅支持 PDF、TXT 和 Markdown 文件")
    if not content:
        raise DocumentError("不能导入空文件")

    if extension == ".pdf":
        return _parse_pdf(content, chunk_size, chunk_overlap)

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DocumentError("TXT 和 Markdown 文件必须使用 UTF-8 编码") from None

    chunks = [
        ParsedChunk(text=value)
        for value in chunk_text(text, chunk_size, chunk_overlap)
    ]
    if not chunks:
        raise DocumentError("文件中没有可索引的文本")
    return chunks


def _parse_pdf(content: bytes, chunk_size: int, chunk_overlap: int) -> list[ParsedChunk]:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise DocumentError("暂不支持加密 PDF")
        chunks = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            chunks.extend(
                ParsedChunk(text=value, page_start=page_number, page_end=page_number)
                for value in chunk_text(text, chunk_size, chunk_overlap)
            )
    except DocumentError:
        raise
    except Exception:
        raise DocumentError("PDF 解析失败，请确认文件未损坏且包含可提取文本") from None

    if not chunks:
        raise DocumentError("PDF 中没有可提取的文本，扫描件需要先进行 OCR")
    return chunks
