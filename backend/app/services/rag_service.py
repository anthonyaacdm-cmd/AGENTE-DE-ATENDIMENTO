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
from app.services.reranker import rerank
from app.utils import strip_pii as _strip_pii
from app.models.schemas import (
    ConversationTurn, GenerateResponse,
    ConversationSession, AnalyzePageResponse,
    KnowledgeMatch,
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
- Se a resposta usar a base de conhecimento, cite a fonte entre colchetes ao final, ex: [Fonte: Nome do documento]

Conhecimento relevante:
{knowledge_context}

Histórico da conversa:
{conversation_history}

Conteúdo extraído de anexo:
{attachment_context}"""

ANALYZE_PROMPT = """Você é um assistente especializado em análise profunda de páginas de plataformas de atendimento ao cliente.

Analise o conteúdo abaixo com atenção aos detalhes e extraia o máximo de informação possível.

Contexto da página:
- Título: {page_title}
- URL: {page_url}
- Tipo: {content_type}

Conteúdo textual:
{page_text}

Dados estruturados da página:
{structured_data}

Conhecimento relacionado encontrado na base:
{knowledge_context}

Instruções:
1. Faça um resumo CONCISO mas COMPLETO do que se trata a página
2. Identifique os principais tópicos abordados (máx 8)
3. Liste pontos-chave importantes e dados específicos (nomes, prazos, valores, protocolos)
4. Classifique o TIPO da página (ex: ticket_atendimento, chat_transcricao, faq, artigo_conhecimento, formulario, painel_admin, perfil_usuario, lista_processos, dashboard, erro, outro)
5. Extraia entidades mencionadas: nomes de pessoas, departamentos, números de protocolo, valores, datas, cursos, disciplinas
6. Classifique a intenção principal da página (ex: duvida_matricula, problema_financeiro, suporte_tecnico, informacao_academica, reclamacao, solicitacao_documento, cancelamento, consulta, outro)
7. Classifique o sentimento/tonalidade predominante (positivo, neutro, negativo, irritado, urgente)
8. Sugira ações que o atendente deve tomar com base no conteúdo
9. Sugira um título e categoria para adicionar à base de conhecimento (se relevante)
10. Conhecimentos relacionados: mencione os títulos da base que são relevantes para esta página

Responda APENAS em JSON válido, sem markdown:
{{
  "summary": "resumo completo e detalhado",
  "topics": ["tópico1", "tópico2"],
  "key_points": ["ponto específico 1", "ponto específico 2"],
  "page_type": "ticket_atendimento",
  "entities": ["Nome: João Silva", "Protocolo: #12345", "Departamento: Financeiro"],
  "intent": "problema_financeiro",
  "sentiment": "negativo",
  "suggested_actions": ["Ação 1", "Ação 2"],
  "suggested_knowledge_title": "Título sugerido",
  "suggested_knowledge_category": "categoria"
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

    async def _summarize_old_turns(self, turns: list[ConversationTurn]) -> str:
        if len(turns) <= 10:
            return self._format_conversation(turns)
        old = turns[:-6]
        recent = turns[-6:]
        old_text = self._format_conversation(old)
        try:
            prompt = f"Resuma o histórico abaixo em 2-3 frases, mantendo apenas fatos relevantes:\n{old_text}\nResumo:"
            result = await self.llm.ainvoke(prompt)
            summary = result.content.strip()[:500]
            recent_text = self._format_conversation(recent)
            return f"Resumo de conversas anteriores:\n{summary}\n\nMensagens recentes:\n{recent_text}"
        except Exception:
            return self._format_conversation(turns)

    async def _web_search_fallback(self, query: str) -> list[dict]:
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for i, r in enumerate(ddgs.text(query, max_results=3)):
                    results.append({"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")})
            return results
        except ImportError:
            logger.warning("duckduckgo_search not installed; skipping web fallback")
            return []
        except Exception as e:
            logger.warning(f"Web search error: {e}")
            return []

    async def generate_response(
        self, conversation: list[ConversationTurn], ticket_title: str = "",
        attachment_text: str = "", conversation_id: Optional[str] = None,
    ) -> GenerateResponse:
        conversation_text = await self._summarize_old_turns(conversation)
        combined_text = f"{ticket_title}\n{conversation_text}" if ticket_title else conversation_text
        combined_text = _strip_pii(combined_text)

        last_message = conversation[-1].message if conversation else combined_text
        intent = await self._detect_intent(last_message)
        sentiment = await self._detect_sentiment(last_message)

        qdrant_ok = qdrant_service.is_ready()
        knowledge_results = []
        web_results = []
        if qdrant_ok and self._ready:
            try:
                query_embedding = await self.embeddings.aembed_query(combined_text)
                knowledge_results = await qdrant_service.search_hybrid(query_embedding, combined_text, limit=15)
            except Exception:
                try:
                    query_embedding = await self.embeddings.aembed_query(combined_text)
                    knowledge_results = await qdrant_service.search(query_embedding, limit=15)
                except Exception:
                    knowledge_results = []

            if knowledge_results:
                reranked = rerank(combined_text, [(r.title, r.content) for r in knowledge_results])
                if reranked is not None:
                    for i, score in enumerate(reranked):
                        if i < len(knowledge_results):
                            knowledge_results[i].score = float(score)
                    knowledge_results.sort(key=lambda x: -x.score)
                knowledge_results = [r for r in knowledge_results if r.score > 0][:5]

            if not knowledge_results:
                web_results = await self._web_search_fallback(last_message)

        knowledge_context = self._format_knowledge(knowledge_results)
        if web_results:
            web_parts = [f"[Web] {r['title']}: {r['body']}" for r in web_results]
            knowledge_context += "\n\n---\n\nResultados da web:\n" + "\n\n".join(web_parts)

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

        sources = []
        for r in knowledge_results:
            if r.score > 0.3:
                sources.append(f"{r.title} [{r.category}]")

        return GenerateResponse(
            suggested_response=response.strip(),
            sources=sources,
            confidence=round(min(avg_score, 1.0), 4),
            conversation_id=conversation_id,
            intent=intent,
            sentiment=sentiment,
        )

    async def analyze_page(self, url: str, title: str, text: str, html: str = "",
                           structured: Optional[dict] = None, screenshot: Optional[str] = None) -> AnalyzePageResponse:
        if not self._ready:
            return AnalyzePageResponse(summary="IA não configurada.", topics=[], key_points=[])

        content_type = "página web"
        text_preview = text[:12000]

        structured_text = ""
        if structured:
            parts = []
            if structured.get("forms"):
                for f in structured["forms"]:
                    inputs = "; ".join(f"{i.get('label','')} ({i.get('type','')}): {i.get('value','')}" for i in f["inputs"])
                    parts.append(f"Formulário: {inputs}")
            if structured.get("tables"):
                for t in structured["tables"]:
                    h = ", ".join(t.get("headers", []))
                    rows = "; ".join(" | ".join(r) for r in t.get("rows", [])[:5])
                    parts.append(f"Tabela: {h} | Dados: {rows}")
            if structured.get("alerts"):
                parts.append(f"Alertas: {'; '.join(a['text'] for a in structured['alerts'])}")
            if structured.get("buttons"):
                parts.append(f"Botões: {'; '.join(b['text'] for b in structured['buttons'][:15])}")
            if structured.get("cards"):
                cards = [c["title"] + ": " + c["text"][:200] for c in structured["cards"][:10]]
                parts.append(f"Cards: {'; '.join(cards)}")
            if structured.get("user_info"):
                parts.append(f"Usuário: {'; '.join(structured['user_info'])}")
            if structured.get("breadcrumbs"):
                parts.append(f"Navegação: {' > '.join(structured['breadcrumbs'])}")
            if structured.get("tabs_found"):
                parts.append(f"Abas: {'; '.join(structured['tabs_found'])}")
            if structured.get("badges"):
                parts.append(f"Status/Badges: {'; '.join(structured['badges'])}")
            if structured.get("selects"):
                sel = [f"{s.get('name','')}={s.get('value','')}" for s in structured["selects"]]
                parts.append(f"Seleções: {'; '.join(sel)}")
            structured_text = "\n".join(parts)

        knowledge_context = "Nenhum conhecimento relacionado encontrado."
        knowledge_matches = []
        if qdrant_service.is_ready():
            try:
                query_embedding = await self.embeddings.aembed_query(f"{title} {text[:3000]}")
                results = await qdrant_service.search_hybrid(query_embedding, text[:3000], limit=5)
                if results:
                    formatted = self._format_knowledge(results)
                    knowledge_context = formatted if formatted else knowledge_context
                    knowledge_matches = [
                        KnowledgeMatch(title=r.title, category=r.category, score=round(float(r.score), 3),
                                       content_preview=r.content[:200])
                        for r in results[:5] if r.score > 0.2
                    ]
            except Exception:
                pass

        try:
            result = await self.llm.ainvoke(
                ANALYZE_PROMPT.format(
                    content_type=content_type,
                    page_title=title,
                    page_url=url,
                    page_text=text_preview,
                    structured_data=structured_text or "Nenhum dado estruturado encontrado.",
                    knowledge_context=knowledge_context,
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
                page_type=data.get("page_type", "outro"),
                entities=data.get("entities", []),
                intent=data.get("intent"),
                sentiment=data.get("sentiment"),
                knowledge_matches=knowledge_matches,
                suggested_actions=data.get("suggested_actions", []),
            )
        except Exception as e:
            logger.error(f"Page analysis error: {e}")
            return AnalyzePageResponse(
                summary="Não foi possível analisar a página.",
                topics=[], key_points=[],
                page_type="outro",
                knowledge_matches=knowledge_matches,
            )


rag_service = RAGService()
