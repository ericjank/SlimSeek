from pydantic import BaseModel, Field, field_validator


class DocumentOut(BaseModel):
    id: str
    filename: str
    size: int
    chunk_count: int
    created_at: str


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("问题不能为空")
        return value


class CitationOut(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    page_start: int | None
    page_end: int | None
    text: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]


class HealthOut(BaseModel):
    status: str
    provider: str
    embedding_model: str
    chat_model: str
    document_count: int
