from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str | None = None
    embedding_model: str | None = None
    is_public: bool = False


class KnowledgeBaseRead(KnowledgeBaseCreate):
    id: int
    collection_name: str
    owner_id: int | None = None
    create_time: datetime
    update_time: datetime

    class Config:
        from_attributes = True


class KnowledgeDocumentRead(BaseModel):
    id: int
    knowledge_base_id: int
    title: str
    file_name: str
    file_ext: str
    file_path: str
    status: str
    chunk_count: int
    error_message: str | None = None
    create_time: datetime
    update_time: datetime

    class Config:
        from_attributes = True


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchHit(BaseModel):
    document_id: int
    chunk_id: int
    title: str
    content: str
    source_label: str | None = None
    score: float = 0.0
    metadata: dict[str, Any] | None = None


class KnowledgeSearchResponse(BaseModel):
    query: str
    hits: list[KnowledgeSearchHit]
