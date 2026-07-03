import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.core.config import settings

client = TestClient(app)


class TestHealth:
    def test_health_endpoint(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "qdrant" in data
        assert "ai" in data
        assert "auth" in data

    def test_root_endpoint(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["app"] == "Agente de Atendimento"


class TestGenerateValidation:
    @patch("app.api.routes.qdrant_service.is_ready")
    @patch("app.api.routes.rag_service.is_ready")
    def test_empty_conversation(self, mock_rag, mock_qdrant):
        mock_rag.return_value = True
        mock_qdrant.return_value = True
        resp = client.post("/api/v1/generate", json={"conversation": []})
        assert resp.status_code == 400
        assert "vazia" in resp.json()["detail"]

    def test_missing_conversation(self):
        resp = client.post("/api/v1/generate", json={})
        assert resp.status_code == 422

    def test_invalid_turn_format(self):
        resp = client.post("/api/v1/generate", json={
            "conversation": [{"author": "Aluno"}]
        })
        assert resp.status_code == 422


class TestKnowledgeValidation:
    def test_create_missing_fields(self):
        resp = client.post("/api/v1/knowledge", json={})
        assert resp.status_code == 422

    def test_create_invalid_category(self):
        resp = client.post("/api/v1/knowledge", json={
            "title": "Teste", "content": "Conteúdo", "category": 123
        })
        assert resp.status_code == 422


class TestAuth:
    def test_auth_not_configured_still_allows(self):
        original = settings.api_key
        settings.api_key = ""
        resp = client.post("/api/v1/generate", json={
            "conversation": [{"author": "A", "message": "B"}]
        })
        settings.api_key = original
        assert resp.status_code in (400, 500, 503, 200)

    def test_auth_blocks_without_key(self):
        original = settings.api_key
        settings.api_key = "secret123"
        resp = client.post("/api/v1/generate", json={
            "conversation": [{"author": "A", "message": "B"}]
        })
        settings.api_key = original
        assert resp.status_code == 401

    def test_auth_accepts_valid_key(self):
        original = settings.api_key
        settings.api_key = "secret123"
        resp = client.post("/api/v1/generate", json={
            "conversation": [{"author": "A", "message": "B"}]
        }, headers={"X-API-Key": "secret123"})
        settings.api_key = original
        assert resp.status_code in (400, 500, 503, 200)


class TestAnalyzePageValidation:
    def test_empty_text(self):
        resp = client.post("/api/v1/analyze-page", json={
            "url": "", "title": "", "text": ""
        })
        assert resp.status_code == 400

    def test_missing_fields(self):
        resp = client.post("/api/v1/analyze-page", json={})
        assert resp.status_code == 422


class TestKnowledgeSearch:
    def test_list_knowledge(self):
        resp = client.get("/api/v1/knowledge")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "total" in data

    def test_get_nonexistent(self):
        resp = client.get("/api/v1/knowledge/nonexistent-id")
        assert resp.status_code == 404


class TestFeedbackValidation:
    def test_missing_fields(self):
        resp = client.post("/api/v1/feedback", json={})
        assert resp.status_code == 422

    def test_invalid_rating_type(self):
        resp = client.post("/api/v1/feedback", json={
            "conversation_id": "c1", "response_text": "ok", "rating": "bom"
        })
        assert resp.status_code == 422


class TestKnowledgeVersions:
    def test_versions_nonexistent(self):
        resp = client.get("/api/v1/knowledge/fake-id/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["knowledge_id"] == "fake-id"
        assert data["versions"] == []


class TestRateLimiterDependency:
    @patch("app.api.routes.rate_limiter.check")
    def test_rate_limited(self, mock_check):
        mock_check.return_value = False
        resp = client.post("/api/v1/generate", json={
            "conversation": [{"author": "A", "message": "B"}]
        })
        assert resp.status_code == 429
        assert "Muitas" in resp.json()["detail"]


class TestChatWidget:
    def test_chat_widget_html(self):
        resp = client.get("/chat-widget")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/html; charset=utf-8"
        assert "Agente de Atendimento" in resp.text
