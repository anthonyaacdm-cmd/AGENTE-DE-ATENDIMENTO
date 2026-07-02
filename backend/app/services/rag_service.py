from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.core.config import settings
from app.services.qdrant_service import qdrant_service
from app.models.schemas import ConversationTurn, GenerateResponse

SYSTEM_PROMPT = """Você é um assistente especializado em atendimento ao aluno.

Você tem acesso a uma base de conhecimento com informações sobre os assuntos.
Use o contexto da conversa e o conhecimento recuperado para gerar uma resposta
útil, precisa e empática que o atendente humano possa usar ou adaptar.

Regras:
- Seja claro e direto
- Use linguagem profissional mas acolhedora
- Inclua informações específicas quando disponíveis
- Se não houver informação suficiente, sugira perguntar ao setor responsável

Conhecimento relevante:
{knowledge_context}

Histórico da conversa:
{conversation_history}"""


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
                max_tokens=1024,
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

    async def generate_response(
        self, conversation: list[ConversationTurn], ticket_title: str = ""
    ) -> GenerateResponse:
        if not self._ready:
            return GenerateResponse(
                suggested_response="",
                sources=[],
                confidence=0.0,
                error="API Gemini não configurada. Defina GEMINI_API_KEY no .env",
            )

        conversation_text = self._format_conversation(conversation)
        combined_text = f"{ticket_title}\n{conversation_text}" if ticket_title else conversation_text

        query_embedding = await self.embeddings.aembed_query(combined_text)
        knowledge_results = qdrant_service.search(query_embedding, limit=5)

        knowledge_context = self._format_knowledge(knowledge_results)

        response = await self.chain.ainvoke({
            "knowledge_context": knowledge_context,
            "conversation_history": conversation_text,
            "input": (
                f"Título do ticket: {ticket_title}\n\n"
                f"Com base na conversa e no conhecimento disponível, "
                f"gere uma resposta sugerida para o atendente."
            ),
        })

        avg_score = (
            sum(r.score for r in knowledge_results) / len(knowledge_results)
            if knowledge_results else 0.0
        )

        return GenerateResponse(
            suggested_response=response.strip(),
            sources=[r.title for r in knowledge_results if r.score > 0.5],
            confidence=round(avg_score, 4),
        )


rag_service = RAGService()
