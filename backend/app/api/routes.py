import logging
import traceback
import json
import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, status, Depends, Header
from fastapi.responses import StreamingResponse
from app.models.schemas import (
    GenerateRequest, GenerateResponse, KnowledgeEntry,
    KnowledgeSearchResult, KnowledgeCreateResponse, ErrorResponse,
    KnowledgeListResponse, KnowledgeDetail, KnowledgeUpdateRequest,
    ExtractTextResponse, FeedbackRequest, AnalyzePageRequest,
    AnalyzePageResponse,
)
from app.services.rag_service import rag_service, conversation_store
from app.services.qdrant_service import qdrant_service
from app.services.file_extraction import extract_text, is_supported
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


async def require_api_key(x_api_key: str = Header("")):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="API key inválida")


async def optional_api_key(x_api_key: str = Header("")):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="API key inválida")


@router.post(
    "/generate",
    response_model=GenerateResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def generate_response(request: GenerateRequest, _=Depends(require_api_key)):
    if not request.conversation:
        raise HTTPException(status_code=400, detail="Conversa vazia")

    if not rag_service.is_ready():
        raise HTTPException(
            status_code=503,
            detail="IA não configurada. Defina GEMINI_API_KEY no .env do servidor",
        )

    session_id = request.conversation_id
    if session_id:
        session = conversation_store.add_turns(session_id, request.conversation)
        if not session:
            raise HTTPException(status_code=404, detail="Sessão de conversa não encontrada")
        all_turns = session.turns
    else:
        session = conversation_store.create(
            ticket_title=request.ticket_title or "",
            platform=request.platform or "",
        )
        conversation_store.add_turns(session.id, request.conversation)
        all_turns = request.conversation
        session_id = session.id

    try:
        result = await rag_service.generate_response(
            conversation=all_turns,
            ticket_title=request.ticket_title or "",
            attachment_text=request.attachment_text or "",
            conversation_id=session_id,
        )
        return result
    except Exception as e:
        logger.error(f"Generate error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate/stream")
async def generate_stream(request: GenerateRequest, _=Depends(require_api_key)):
    if not request.conversation:
        raise HTTPException(status_code=400, detail="Conversa vazia")

    if not rag_service.is_ready():
        raise HTTPException(status_code=503, detail="IA não configurada")

    session_id = request.conversation_id
    if session_id:
        session = conversation_store.add_turns(session_id, request.conversation)
        if not session:
            raise HTTPException(status_code=404, detail="Sessão não encontrada")
        all_turns = session.turns
    else:
        session = conversation_store.create(
            ticket_title=request.ticket_title or "",
            platform=request.platform or "",
        )
        conversation_store.add_turns(session.id, request.conversation)
        all_turns = request.conversation
        session_id = session.id

    conversation_text = "\n".join(
        f"{t.author}: {t.message}" for t in all_turns
    )

    async def event_stream():
        try:
            async for chunk in rag_service.llm.astream(
                f"Com base na conversa a seguir, gere uma resposta sugerida para o atendente.\n\n{conversation_text}"
            ):
                if chunk.content:
                    yield f"data: {json.dumps({'token': chunk.content})}\n\n"
            yield f"data: {json.dumps({'done': True, 'conversation_id': session_id})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/analyze-page", response_model=AnalyzePageResponse)
async def analyze_page(request: AnalyzePageRequest, _=Depends(require_api_key)):
    if not request.text:
        raise HTTPException(status_code=400, detail="Texto da página vazio")

    if not rag_service.is_ready():
        raise HTTPException(status_code=503, detail="IA não configurada")

    try:
        result = await rag_service.analyze_page(
            url=request.url,
            title=request.title,
            text=request.text,
            html=request.html or "",
        )
        return result
    except Exception as e:
        logger.error(f"Analyze page error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def submit_feedback(feedback: FeedbackRequest, _=Depends(require_api_key)):
    try:
        from datetime import datetime
        import uuid
        entry = {
            "id": str(uuid.uuid4()),
            "conversation_id": feedback.conversation_id,
            "response_text": feedback.response_text,
            "rating": feedback.rating,
            "comment": feedback.comment or "",
            "created_at": datetime.utcnow().isoformat(),
        }
        import json, os
        fb_path = os.path.join("data", "feedback.jsonl")
        os.makedirs("data", exist_ok=True)
        with open(fb_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return {"message": "Feedback registrado", "id": entry["id"]}
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/knowledge",
    response_model=KnowledgeCreateResponse,
    status_code=201,
)
async def add_knowledge(entry: KnowledgeEntry, _=Depends(require_api_key)):
    if not rag_service.is_ready():
        raise HTTPException(status_code=503, detail="IA não configurada")

    try:
        embedding = await rag_service.embeddings.aembed_query(entry.content)
        point_id = await qdrant_service.upsert_knowledge(entry, embedding)
        return KnowledgeCreateResponse(id=point_id, message="Conhecimento adicionado com sucesso")
    except Exception as e:
        logger.error(f"Knowledge add error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge", response_model=KnowledgeListResponse)
async def list_knowledge(
    query: str = Query("", description="Busca textual"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _=Depends(optional_api_key),
):
    if query:
        if not rag_service.is_ready():
            raise HTTPException(status_code=503, detail="IA não configurada")
        embedding = await rag_service.embeddings.aembed_query(query)
        results = await qdrant_service.search(embedding, limit=limit)
        total = len(results)
    else:
        total = qdrant_service.count_points()
        results = await qdrant_service.list_all(limit=limit, offset=offset)
    return KnowledgeListResponse(results=results, total=total, offset=offset, limit=limit)


@router.get("/knowledge/search")
async def search_knowledge(query: str = "", limit: int = 5, _=Depends(optional_api_key)):
    if query:
        if not rag_service.is_ready():
            raise HTTPException(status_code=503, detail="IA não configurada")
        embedding = await rag_service.embeddings.aembed_query(query)
        results = await qdrant_service.search(embedding, limit=limit)
    else:
        results = await qdrant_service.list_all(limit=limit)
    return {"results": results}


@router.get("/knowledge/{point_id}", response_model=KnowledgeDetail)
async def get_knowledge(point_id: str, _=Depends(optional_api_key)):
    result = await qdrant_service.get_point(point_id)
    if not result:
        raise HTTPException(status_code=404, detail="Conhecimento não encontrado")
    return result


@router.put("/knowledge/{point_id}", response_model=KnowledgeCreateResponse)
async def update_knowledge(point_id: str, update: KnowledgeUpdateRequest, _=Depends(require_api_key)):
    existing = await qdrant_service.get_point(point_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Conhecimento não encontrado")

    entry = KnowledgeEntry(
        id=point_id,
        title=update.title if update.title is not None else existing.title,
        content=update.content if update.content is not None else existing.content,
        category=update.category if update.category is not None else existing.category,
        tags=update.tags if update.tags is not None else existing.tags,
        source_url=update.source_url if update.source_url is not None else existing.source_url,
    )

    if update.content:
        embedding = await rag_service.embeddings.aembed_query(entry.content)
        await qdrant_service.update_point(point_id, entry, embedding)
    else:
        await qdrant_service.update_point(point_id, entry)

    return KnowledgeCreateResponse(id=point_id, message="Conhecimento atualizado com sucesso")


@router.delete("/knowledge/{point_id}")
async def delete_knowledge(point_id: str, _=Depends(require_api_key)):
    try:
        await qdrant_service.delete_point(point_id)
        return {"message": "Conhecimento removido"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Ponto não encontrado: {e}")


@router.post("/knowledge/extract", response_model=ExtractTextResponse)
async def extract_file_text(file: UploadFile = File(...), _=Depends(require_api_key)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")

    if not is_supported(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"Formato não suportado: {file.filename}. Use PDF, DOCX, TXT, PNG, JPG, GIF, BMP ou WEBP.",
        )

    MAX_SIZE = 10 * 1024 * 1024
    if file.size and file.size > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Máximo: 10 MB.")

    try:
        content = await file.read()
        result = await extract_text(file.filename, content)
        return ExtractTextResponse(**result)
    except Exception as e:
        logger.error(f"Extract error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "qdrant": qdrant_service.is_ready(),
        "ai": rag_service.is_ready(),
        "auth": bool(settings.api_key),
    }


@router.get("/debug/embedding")
async def debug_embedding(text: str = "test", _=Depends(optional_api_key)):
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
