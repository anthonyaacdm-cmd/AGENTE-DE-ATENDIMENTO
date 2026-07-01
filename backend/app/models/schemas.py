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

class KnowledgeCreateResponse(BaseModel):
    id: str
    message: str

class ErrorResponse(BaseModel):
    detail: str
