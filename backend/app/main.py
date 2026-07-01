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
    has_key = bool(settings.openai_api_key)
    print(f"[Server] OpenAI key: {'configurada' if has_key else 'NÃO configurada'}")
    print(f"[Server] Qdrant URL: {settings.qdrant_url}")
    print(f"[Server] Docs: http://localhost:8000/docs")


@app.get("/")
async def root():
    return {
        "app": "Agente de Atendimento",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
