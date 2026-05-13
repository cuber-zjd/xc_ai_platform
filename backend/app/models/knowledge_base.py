from enum import Enum
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from app.models.base import BaseDBModel


class KnowledgeDocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"


class KnowledgeBase(BaseDBModel, table=True):
    """通用知识库。"""

    __tablename__ = "knowledge_base"

    name: str = Field(index=True, description="知识库名称")
    description: str | None = Field(default=None, description="知识库说明")
    owner_id: int | None = Field(default=None, index=True, description="创建人 ID")
    collection_name: str = Field(index=True, description="Milvus collection 名称")
    embedding_model: str | None = Field(default=None, description="向量模型名称")
    is_public: bool = Field(default=False, description="是否公开给所有智能体")


class KnowledgeDocument(BaseDBModel, table=True):
    """知识库文档元数据。"""

    __tablename__ = "knowledge_document"

    knowledge_base_id: int = Field(foreign_key="knowledge_base.id", index=True)
    title: str = Field(index=True, description="文档标题")
    file_name: str = Field(description="原始文件名")
    file_ext: str = Field(index=True, description="文件扩展名")
    file_path: str = Field(description="MinIO object path")
    content_type: str | None = Field(default=None)
    file_size: int = Field(default=0)
    status: KnowledgeDocumentStatus = Field(default=KnowledgeDocumentStatus.UPLOADED)
    chunk_count: int = Field(default=0)
    error_message: str | None = Field(default=None)
    doc_metadata: dict[str, Any] | None = Field(default=None, sa_type=JSONB)


class KnowledgeChunk(BaseDBModel, table=True):
    """知识库切片。"""

    __tablename__ = "knowledge_chunk"

    knowledge_base_id: int = Field(foreign_key="knowledge_base.id", index=True)
    document_id: int = Field(foreign_key="knowledge_document.id", index=True)
    chunk_index: int = Field(index=True)
    content: str = Field(description="切片文本")
    source_label: str | None = Field(default=None, description="页码、sheet 或段落定位")
    vector_id: str | None = Field(default=None, index=True)
    token_count: int = Field(default=0)
    chunk_metadata: dict[str, Any] | None = Field(default=None, sa_type=JSONB)


class KnowledgeIndexJob(BaseDBModel, table=True):
    """知识库索引任务。"""

    __tablename__ = "knowledge_index_job"

    knowledge_base_id: int = Field(foreign_key="knowledge_base.id", index=True)
    document_id: int | None = Field(default=None, foreign_key="knowledge_document.id", index=True)
    status: KnowledgeDocumentStatus = Field(default=KnowledgeDocumentStatus.UPLOADED)
    total_chunks: int = Field(default=0)
    indexed_chunks: int = Field(default=0)
    error_message: str | None = Field(default=None)
