import logging
import traceback
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    GenerateRequest, GenerateResponse, KnowledgeEntry,
    KnowledgeSearchResult, KnowledgeCreateResponse, ErrorResponse,
)
from app.services.rag_service import rag_service
from app.services.qdrant_service import qdrant_service
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/generate",
    response_model=GenerateResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def generate_response(request: GenerateRequest):
    if not request.conversation:
        raise HTTPException(status_code=400, detail="Conversa vazia")

    if not rag_service.is_ready():
        raise HTTPException(
            status_code=503,
            detail="IA não configurada. Defina OPENAI_API_KEY no .env do servidor",
        )

    if not qdrant_service.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Banco de conhecimento (Qdrant) indisponível",
        )

    try:
        result = await rag_service.generate_response(
            conversation=request.conversation,
            ticket_title=request.ticket_title or "",
        )
        return result
    except Exception as e:
        logger.error(f"Generate error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/knowledge",
    response_model=KnowledgeCreateResponse,
    status_code=201,
)
async def add_knowledge(entry: KnowledgeEntry):
    if not rag_service.is_ready():
        raise HTTPException(status_code=503, detail="IA não configurada")

    try:
        embedding = await rag_service.embeddings.aembed_query(entry.content)
        point_id = qdrant_service.upsert_knowledge(entry, embedding)
        return KnowledgeCreateResponse(id=point_id, message="Conhecimento adicionado com sucesso")
    except Exception as e:
        logger.error(f"Knowledge add error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/search")
async def search_knowledge(query: str = "", limit: int = 5):
    if query:
        if not rag_service.is_ready():
            raise HTTPException(status_code=503, detail="IA não configurada")
        embedding = await rag_service.embeddings.aembed_query(query)
        results = qdrant_service.search(embedding, limit=limit)
    else:
        results = qdrant_service.list_all(limit=limit)
    return {"results": results}


@router.delete("/knowledge/{point_id}")
async def delete_knowledge(point_id: str):
    try:
        qdrant_service.delete_point(point_id)
        return {"message": "Conhecimento removido"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Ponto não encontrado: {e}")


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "qdrant": qdrant_service.is_ready(),
        "ai": rag_service.is_ready(),
    }


@router.get("/debug/embedding")
async def debug_embedding(text: str = "test"):
    try:
        embedding = await rag_service.embeddings.aembed_query(text)
        return {"status": "ok", "embedding_length": len(embedding), "first_5": embedding[:5]}
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "embeddings_type": str(type(rag_service.embeddings)),
            "embeddings_repr": repr(rag_service.embeddings),
            "gemini_key_set": bool(settings.gemini_api_key),
            "traceback": traceback.format_exc(),
        }
