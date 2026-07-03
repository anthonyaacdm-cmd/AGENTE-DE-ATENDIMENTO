from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ConversationTurn(BaseModel):
    author: str
    message: str
    timestamp: Optional[str] = None


class GenerateRequest(BaseModel):
    conversation: List[ConversationTurn]
    ticket_title: Optional[str] = ""
    platform: Optional[str] = ""
    attachment_text: Optional[str] = ""
    conversation_id: Optional[str] = None


class GenerateResponse(BaseModel):
    suggested_response: str
    sources: List[str] = []
    confidence: float = 0.0
    error: Optional[str] = None
    conversation_id: Optional[str] = None
    intent: Optional[str] = None
    sentiment: Optional[str] = None


class GenerateStreamEvent(BaseModel):
    event: str
    data: str


class FeedbackRequest(BaseModel):
    conversation_id: str
    response_text: str
    rating: int
    comment: Optional[str] = ""


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


class AnalyzePageRequest(BaseModel):
    url: str
    title: str
    text: str
    html: Optional[str] = ""
    structured: Optional[dict] = None
    screenshot: Optional[str] = None


class KnowledgeMatch(BaseModel):
    title: str
    category: str
    score: float
    content_preview: str


class AnalyzePageResponse(BaseModel):
    summary: str
    topics: List[str] = []
    key_points: List[str] = []
    suggested_knowledge_title: Optional[str] = None
    suggested_knowledge_category: Optional[str] = None
    page_type: Optional[str] = None
    entities: List[str] = []
    intent: Optional[str] = None
    sentiment: Optional[str] = None
    knowledge_matches: List[KnowledgeMatch] = []
    suggested_actions: List[str] = []


class ConversationSession(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    turns: List[ConversationTurn]
    ticket_title: str = ""
    platform: str = ""
    context: str = ""


class FeedbackEntry(BaseModel):
    id: str
    conversation_id: str
    response_text: str
    rating: int
    comment: str
    created_at: datetime
