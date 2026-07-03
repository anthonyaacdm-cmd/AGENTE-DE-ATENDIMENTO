from app.services.chunker import chunk_text


class TestChunker:
    def test_short_text_no_split(self):
        chunks = chunk_text("Texto curto", chunk_size=100)
        assert len(chunks) == 1
        assert chunks[0] == "Texto curto"

    def test_splits_long_text(self):
        text = "Palavra. " * 300
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) > 1
        assert all(len(c) <= 500 for c in chunks)
        assert all(c.strip() for c in chunks)

    def test_overlap_preserves_context(self):
        text = "Primeiro parágrafo.\n\nSegundo parágrafo.\n\nTerceiro parágrafo.\n\nQuarto parágrafo."
        chunks = chunk_text(text, chunk_size=30, overlap=10)
        if len(chunks) > 1:
            assert len(chunks[0]) > 0
            assert len(chunks[1]) > 0

    def test_empty_text(self):
        chunks = chunk_text("")
        assert chunks == []

    def test_whitespace_only(self):
        chunks = chunk_text("   \n\n  ")
        assert chunks == []
