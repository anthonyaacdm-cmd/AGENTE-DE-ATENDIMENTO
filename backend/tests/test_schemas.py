import pytest
from app.models.schemas import (
    ConversationTurn, GenerateRequest, GenerateResponse,
    KnowledgeEntry, ExtractTextResponse, AnalyzePageResponse,
    FeedbackRequest,
)


class TestConversationTurn:
    def test_minimal(self):
        t = ConversationTurn(author="Aluno", message="Olá")
        assert t.author == "Aluno"
        assert t.message == "Olá"
        assert t.timestamp is None

    def test_with_timestamp(self):
        t = ConversationTurn(author="Atendente", message="Como ajudar?", timestamp="10:30")
        assert t.timestamp == "10:30"


class TestGenerateRequest:
    def test_defaults(self):
        req = GenerateRequest(conversation=[ConversationTurn(author="A", message="B")])
        assert req.ticket_title == ""
        assert req.platform == ""
        assert req.attachment_text == ""

    def test_conversation_id_optional(self):
        req = GenerateRequest(conversation=[], conversation_id="abc123")
        assert req.conversation_id == "abc123"


class TestGenerateResponse:
    def test_defaults(self):
        resp = GenerateResponse(suggested_response="Resposta")
        assert resp.sources == []
        assert resp.confidence == 0.0
        assert resp.error is None
        assert resp.conversation_id is None
        assert resp.intent is None
        assert resp.sentiment is None

    def test_with_all_fields(self):
        resp = GenerateResponse(
            suggested_response="Teste",
            sources=["fonte1"],
            confidence=0.85,
            conversation_id="sessao1",
            intent="duvida_matricula",
            sentiment="neutro",
        )
        assert resp.conversation_id == "sessao1"
        assert resp.intent == "duvida_matricula"


class TestKnowledgeEntry:
    def test_defaults(self):
        k = KnowledgeEntry(title="Título", content="Conteúdo")
        assert k.category == "geral"
        assert k.tags == []
        assert k.source_url is None
        assert k.id is None


class TestExtractTextResponse:
    def test_error_response(self):
        r = ExtractTextResponse(text="", format="image", error="Falha")
        assert r.error == "Falha"


class TestAnalyzePageResponse:
    def test_defaults(self):
        a = AnalyzePageResponse(summary="Resumo")
        assert a.topics == []
        assert a.key_points == []
        assert a.suggested_knowledge_title is None

    def test_with_data(self):
        a = AnalyzePageResponse(
            summary="Sumário", topics=["a", "b"],
            key_points=["p1"], suggested_knowledge_title="Título",
        )
        assert len(a.topics) == 2


class TestFeedbackRequest:
    def test_valid(self):
        f = FeedbackRequest(conversation_id="c1", response_text="ok", rating=4)
        assert f.rating == 4
        assert f.comment == ""

    def test_with_comment(self):
        f = FeedbackRequest(conversation_id="c1", response_text="ok", rating=3, comment="Boa resposta")
        assert f.comment == "Boa resposta"
