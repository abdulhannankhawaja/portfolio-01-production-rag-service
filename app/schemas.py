from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    chunk_count: int
    sha256: str


class Citation(BaseModel):
    document_id: str
    filename: str
    page: int | None = None
    section: str | None = None
    chunk_index: int
    text: str
    score: float


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class QuestionResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieved_chunks: list[Citation]
    grounded: bool
    refusal: bool
    model: str
