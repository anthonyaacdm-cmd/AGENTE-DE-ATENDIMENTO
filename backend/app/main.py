import json
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.services.qdrant_service import qdrant_service
from app.core.config import settings

app = FastAPI(
    title="Agente de Atendimento API",
    description="Gerador de respostas inteligente com RAG",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.on_event("startup")
async def startup():
    qdrant_service.ensure_collection()
    has_key = bool(settings.gemini_api_key)
    print(f"[Server] Gemini key: {'configurada' if has_key else 'NÃO configurada'}")
    print(f"[Server] Qdrant URL: {settings.qdrant_url}")
    print(f"[Server] Docs: http://localhost:8000/docs")

    count = qdrant_service.count_points()
    if count == 0:
        print("[Seed] Base vazia. Populando conhecimento padrão...")
        seed_path = os.path.join(os.path.dirname(__file__), "seed_data.json")
        await _seed_knowledge(seed_path)
    else:
        print(f"[Seed] Base já contém {count} registros. Pulando seed.")


async def _seed_knowledge(path: str):
    try:
        from app.services.rag_service import rag_service
        from app.models.schemas import KnowledgeEntry
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        for entry in entries:
            embedding = await rag_service.embeddings.aembed_query(entry["content"])
            qdrant_service.upsert_knowledge(KnowledgeEntry(**entry), embedding)
        print(f"[Seed] {len(entries)} conhecimentos adicionados com sucesso.")
    except Exception as e:
        print(f"[Seed] Erro ao popular base: {e}")


@app.get("/")
async def root():
    return {
        "app": "Agente de Atendimento",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
