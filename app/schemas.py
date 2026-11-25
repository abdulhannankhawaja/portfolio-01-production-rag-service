from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str = Field(description="Generated document identifier")
    filename: str = Field(description="Original uploaded filename")
    file_type: str = Field(description="Validated file extension")
    size_bytes: int = Field(description="Uploaded file size in bytes")
    chunk_count: int = Field(description="Number of indexed text chunks")
    sha256: str = Field(description="SHA-256 digest used for duplicate detection")


class Citation(BaseModel):
    chunk_id: str = Field(description="Stable identifier of a retrieved chunk")
    document_id: str
    filename: str
    page: int | None = None
    section: str | None = None
    chunk_index: int
    rank: int = Field(ge=1, description="One-based rank in this query's results")
    text: str
    score: float = Field(ge=-1, le=1, description="Cosine similarity, not confidence")


class QuestionRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=2000,
        description="Question to answer from the indexed documents",
        examples=["What does the document say about AI risk management?"],
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Optional number of ranked chunks to retrieve (1-20)",
        examples=[5],
    )


class QuestionResponse(BaseModel):
    answer: str
    citations: list[Citation]
    retrieved_chunks: list[Citation]
    grounded: bool
    refusal: bool
    model: str
