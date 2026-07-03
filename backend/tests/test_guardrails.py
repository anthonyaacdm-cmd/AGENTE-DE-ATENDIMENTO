import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils import strip_pii

_strip_pii = strip_pii


class TestPIIStrip:
    def test_cpf_removed(self):
        text = "Meu CPF é 123.456.789-09, favor registrar."
        result = _strip_pii(text)
        assert "123.456.789-09" not in result
        assert "[REDACTED]" in result

    def test_cnpj_removed(self):
        text = "CNPJ: 12.345.678/0001-90 da empresa"
        result = _strip_pii(text)
        assert "[REDACTED]" in result

    def test_raw_cpf_11_digits(self):
        text = "CPF 12345678909"
        result = _strip_pii(text)
        assert "[REDACTED]" in result

    def test_credit_card_removed(self):
        text = "Cartão: 4111-1111-1111-1111"
        result = _strip_pii(text)
        assert "[REDACTED]" in result

    def test_continuous_16_digits(self):
        text = "número 4111111111111111"
        result = _strip_pii(text)
        assert "[REDACTED]" in result

    def test_credit_card_with_spaces(self):
        text = "Cartão: 4111 1111 1111 1111 vence 12/28"
        result = _strip_pii(text)
        assert "[REDACTED]" in result

    def test_clean_text_unchanged(self):
        text = "Olá, preciso de ajuda com minha matrícula."
        result = _strip_pii(text)
        assert result == text

    def test_mixed_content(self):
        text = "Aluno João, CPF 123.456.789-09, solicitou cancelamento."
        result = _strip_pii(text)
        assert "João" in result
        assert "cancelamento" in result
        assert "[REDACTED]" in result
        assert "123.456.789-09" not in result

    def test_empty_string(self):
        assert _strip_pii("") == ""
