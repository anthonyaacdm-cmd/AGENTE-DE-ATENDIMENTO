import asyncio
import re
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.core.config import settings
from app.services.qdrant_service import qdrant_service
from app.utils import strip_pii as _strip_pii
from app.models.schemas import (
    ConversationTurn, GenerateResponse,
    ConversationSession, AnalyzePageResponse,
)

logger = logging.getLogger(__name__)
RETRY_LIMIT = 3

SYSTEM_PROMPT = """Você é um assistente especializado em atendimento ao aluno.

Você tem acesso a uma base de conhecimento com informações sobre os assuntos.
Use o contexto da conversa e o conhecimento recuperado para gerar uma resposta
útil, precisa e empática que o atendente humano possa usar ou adaptar.

Regras:
- Seja claro e direto
- Use linguagem profissional mas acolhedora
- Inclua informações específicas quando disponíveis
- Se não houver informação suficiente, sugira perguntar ao setor responsável
- NÃO invente informações. Se não souber, diga que não tem essa informação.

Conhecimento relevante:
{knowledge_context}

Histórico da conversa:
{conversation_history}

Conteúdo extraído de anexo:
{attachment_context}"""

ANALYZE_PROMPT = """Você é um assistente que analisa páginas web de plataformas de atendimento.

Analise o conteúdo abaixo e extraia:
1. Um resumo conciso do que se trata a página
2. Principais tópicos abordados
3. Pontos-chave importantes
4. Uma sugestão de título e categoria para adicionar este conteúdo à base de conhecimento

Conteúdo da página ({content_type}):
Título: {page_title}
URL: {page_url}

{page_text}

Responda APENAS em JSON no formato:
{{
  "summary": "resumo aqui",
  "topics": ["tópico1", "tópico2"],
  "key_points": ["ponto1", "ponto2"],
  "suggested_knowledge_title": "título sugerido",
  "suggested_knowledge_category": "categoria sugerida"
}}"""

INTENT_CATEGORIES = [
    "duvida_matricula", "problema_financeiro", "suporte_tecnico",
    "informacao_academica", "reclamacao", "solicitacao_documento",
    "cancelamento", "outro"
]


class ConversationStore:
    def __init__(self):
        self._sessions: dict[str, ConversationSession] = {}

    def create(self, ticket_title: str = "", platform: str = "") -> ConversationSession:
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc)
        session = ConversationSession(
            id=session_id, created_at=now, updated_at=now,
            turns=[], ticket_title=ticket_title, platform=platform,
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[ConversationSession]:
        return self._sessions.get(session_id)

    def add_turns(self, session_id: str, turns: list[ConversationTurn]) -> Optional[ConversationSession]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.turns.extend(turns)
        if len(session.turns) > settings.max_conversation_turns:
            session.turns = session.turns[-settings.max_conversation_turns:]
        session.updated_at = datetime.now(timezone.utc)
        return session


conversation_store = ConversationStore()


class RAGService:
    def __init__(self):
        self.embeddings = None
        self.llm = None
        self.chain = None
        self._ready = False
        self._init_llm()

    def _init_llm(self):
        if not settings.gemini_api_key:
            print("[RAG] No Gemini API key configured. Using fallback mode.")
            self._ready = False
            return

        try:
            self.embeddings = GoogleGenerativeAIEmbeddings(
                model=settings.embedding_model,
                google_api_key=settings.gemini_api_key,
            )
            self.llm = ChatGoogleGenerativeAI(
                model=settings.llm_model,
                google_api_key=settings.gemini_api_key,
                temperature=0.3,
                max_tokens=4096,
            )

            prompt = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT),
                ("human", "{input}"),
            ])

            self.chain = prompt | self.llm | StrOutputParser()
            self._ready = True
        except Exception as e:
            print(f"[RAG] Initialization error: {e}")
            self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    def _format_conversation(self, turns: list[ConversationTurn]) -> str:
        lines = []
        for t in turns:
            ts = f" [{t.timestamp}]" if t.timestamp else ""
            lines.append(f"{t.author}{ts}: {t.message}")
        return "\n".join(lines) if lines else "Nenhuma mensagem."

    def _format_knowledge(self, results: list) -> str:
        if not results:
            return "Nenhum conhecimento relevante encontrado na base."
        parts = []
        for r in results:
            parts.append(f"[{r.category}] {r.title} (relevância: {r.score:.2f})\n{r.content}")
        return "\n\n---\n\n".join(parts)

    async def _call_with_retry(self, chain_input: dict) -> str:
        for attempt in range(RETRY_LIMIT):
            try:
                return await self.chain.ainvoke(chain_input)
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    match = re.search(r'retryDelay[^}]*"(\d+)s"', err_str)
                    wait = int(match.group(1)) + 2 if match else 5 * (attempt + 1)
                    wait = min(wait, 60)
                    logger.warning(f"Quota excedida (tentativa {attempt+1}/{RETRY_LIMIT}). Aguardando {wait}s...")
                    if attempt < RETRY_LIMIT - 1:
                        await asyncio.sleep(wait)
                    else:
                        raise
                else:
                    raise
        return ""

    async def _detect_intent(self, text: str) -> str:
        if not self._ready:
            return "outro"
        try:
            prompt = f"Classifique a intenção principal desta mensagem em uma categoria: {', '.join(INTENT_CATEGORIES)}.\nMensagem: {text}\nCategoria:"
            result = await self.llm.ainvoke(prompt)
            intent = result.content.strip().lower()
            for cat in INTENT_CATEGORIES:
                if cat in intent:
                    return cat
            return "outro"
        except Exception:
            return "outro"

    async def _detect_sentiment(self, text: str) -> str:
        if not self._ready:
            return "neutro"
        try:
            prompt = f"Classifique o sentimento desta mensagem como: positivo, negativo, neutro, irritado.\nMensagem: {text}\nSentimento:"
            result = await self.llm.ainvoke(prompt)
            sentiment = result.content.strip().lower()
            for s in ["positivo", "negativo", "neutro", "irritado"]:
                if s in sentiment:
                    return s
            return "neutro"
        except Exception:
            return "neutro"

    async def generate_response(
        self, conversation: list[ConversationTurn], ticket_title: str = "",
        attachment_text: str = "", conversation_id: Optional[str] = None,
    ) -> GenerateResponse:
        conversation_text = self._format_conversation(conversation)
        combined_text = f"{ticket_title}\n{conversation_text}" if ticket_title else conversation_text
        combined_text = _strip_pii(combined_text)

        last_message = conversation[-1].message if conversation else combined_text
        intent = await self._detect_intent(last_message)
        sentiment = await self._detect_sentiment(last_message)

        qdrant_ok = qdrant_service.is_ready()
        if qdrant_ok and self._ready:
            try:
                query_embedding = await self.embeddings.aembed_query(combined_text)
                knowledge_results = await qdrant_service.search(query_embedding, limit=5)
            except Exception:
                knowledge_results = []
        else:
            knowledge_results = []

        knowledge_context = self._format_knowledge(knowledge_results)
        attachment_context = attachment_text if attachment_text else "Nenhum anexo."

        sentiment_note = ""
        if sentiment == "irritado":
            sentiment_note = "\nNota: O cliente parece irritado. Seja paciente e empático."
        elif sentiment == "negativo":
            sentiment_note = "\nNota: O cliente parece insatisfeito. Ofereça soluções."

        if self._ready:
            response = await self._call_with_retry({
                "knowledge_context": knowledge_context,
                "conversation_history": conversation_text,
                "attachment_context": attachment_context,
                "input": (
                    f"Título do ticket: {ticket_title}\n"
                    f"Intenção: {intent}\n"
                    f"Sentimento: {sentiment}{sentiment_note}\n\n"
                    f"Com base na conversa, no anexo e no conhecimento disponível, "
                    f"gere uma resposta sugerida para o atendente."
                ),
            })
        else:
            response = await self._call_with_retry({
                "knowledge_context": "Base de conhecimento indisponível no momento.",
                "conversation_history": conversation_text,
                "attachment_context": attachment_context,
                "input": (
                    f"Título do ticket: {ticket_title}\n\n"
                    f"Gere uma resposta sugerida para o atendente com base apenas na conversa. "
                    f"Não há base de conhecimento disponível."
                ),
            })

        if not response:
            return GenerateResponse(
                suggested_response="", sources=[], confidence=0.0,
                error="Limite da API Gemini excedido. Aguarde ou use outro modelo.",
                conversation_id=conversation_id, intent=intent, sentiment=sentiment,
            )

        response = _strip_pii(response)

        avg_score = (
            sum(r.score for r in knowledge_results) / len(knowledge_results)
            if knowledge_results else 0.0
        )

        return GenerateResponse(
            suggested_response=response.strip(),
            sources=[r.title for r in knowledge_results if r.score > 0.5],
            confidence=round(avg_score, 4),
            conversation_id=conversation_id,
            intent=intent,
            sentiment=sentiment,
        )

    async def analyze_page(self, url: str, title: str, text: str, html: str = "") -> AnalyzePageResponse:
        if not self._ready:
            return AnalyzePageResponse(summary="IA não configurada.", topics=[], key_points=[])

        content_type = "página web"
        text_preview = text[:8000]

        try:
            result = await self.llm.ainvoke(
                ANALYZE_PROMPT.format(
                    content_type=content_type,
                    page_title=title,
                    page_url=url,
                    page_text=text_preview,
                )
            )
            raw = result.content.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            data = json.loads(raw)
            return AnalyzePageResponse(
                summary=data.get("summary", ""),
                topics=data.get("topics", []),
                key_points=data.get("key_points", []),
                suggested_knowledge_title=data.get("suggested_knowledge_title"),
                suggested_knowledge_category=data.get("suggested_knowledge_category"),
            )
        except Exception as e:
            logger.error(f"Page analysis error: {e}")
            return AnalyzePageResponse(
                summary="Não foi possível analisar a página.",
                topics=[], key_points=[],
            )


rag_service = RAGService()
