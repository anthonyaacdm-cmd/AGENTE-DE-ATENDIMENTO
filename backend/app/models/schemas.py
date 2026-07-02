from pydantic import BaseModel
from typing import Optional, List


class ConversationTurn(BaseModel):
    author: str
    message: str
    timestamp: Optional[str] = None


class GenerateRequest(BaseModel):
    conversation: List[ConversationTurn]
    ticket_title: Optional[str] = ""
    platform: Optional[str] = ""
    attachment_text: Optional[str] = ""


class GenerateResponse(BaseModel):
    suggested_response: str
    sources: List[str] = []
    confidence: float = 0.0
    error: Optional[str] = None


class KnowledgeEntry(BaseModel):
    id: Optional[str] = None
    title: str
    content: str
    category: str = "geral"
    tags: List[str] = []
    source_url: Optional[str] = None


class KnowledgeSearchResult(BaseModel):
    id: str
    title: str
    content: str
    score: float
    category: str


class KnowledgeDetail(BaseModel):
    id: str
    title: str
    content: str
    category: str
    tags: List[str] = []
    source_url: Optional[str] = None


class KnowledgeCreateResponse(BaseModel):
    id: str
    message: str


class KnowledgeListResponse(BaseModel):
    results: List[KnowledgeDetail]
    total: int
    offset: int
    limit: int


class KnowledgeUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    source_url: Optional[str] = None


class ExtractTextResponse(BaseModel):
    text: str
    format: str
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    detail: str
