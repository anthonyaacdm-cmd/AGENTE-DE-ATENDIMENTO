from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from app.core.config import settings
from app.models.schemas import KnowledgeEntry, KnowledgeSearchResult
import uuid
import os


class QdrantService:
    def __init__(self):
        self.collection_name = settings.collection_name
        self.vector_size = 3072
        self._ready = False
        self._local = False
        self.client = self._create_client()

    def _create_client(self):
        try:
            client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
                timeout=5,
            )
            client.get_collections()
            print(f"[Qdrant] Connected to server at {settings.qdrant_url}")
            return client
        except Exception:
            local_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "qdrant")
            os.makedirs(local_path, exist_ok=True)
            print(f"[Qdrant] Server unavailable. Using local mode at {local_path}")
            self._local = True
            return QdrantClient(path=local_path)

    def ensure_collection(self):
        if self._ready:
            return
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            if not exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
            self._ready = True
        except Exception as e:
            print(f"[Qdrant] Connection failed (server may be starting): {e}")
            self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    def upsert_knowledge(self, entry: KnowledgeEntry, embedding: list[float]) -> str:
        self.ensure_collection()
        point_id = entry.id or str(uuid.uuid4())
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "title": entry.title,
                        "content": entry.content,
                        "category": entry.category,
                        "tags": entry.tags,
                        "source_url": entry.source_url,
                    },
                )
            ],
        )
        return point_id

    def search(self, query_embedding: list[float], limit: int = 5) -> list[KnowledgeSearchResult]:
        self.ensure_collection()
        if not self._ready:
            return []
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
            )
            return [
                KnowledgeSearchResult(
                    id=str(res.id),
                    title=res.payload.get("title", ""),
                    content=res.payload.get("content", ""),
                    score=res.score,
                    category=res.payload.get("category", ""),
                )
                for res in results
            ]
        except Exception as e:
            print(f"[Qdrant] Search error: {e}")
            return []

    def list_all(self, limit: int = 50) -> list[KnowledgeSearchResult]:
        self.ensure_collection()
        if not self._ready:
            return []
        try:
            results = self.client.scroll(
                collection_name=self.collection_name,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            return [
                KnowledgeSearchResult(
                    id=str(p.id),
                    title=p.payload.get("title", ""),
                    content=p.payload.get("content", ""),
                    score=1.0,
                    category=p.payload.get("category", ""),
                )
                for p in results[0]
            ]
        except Exception as e:
            print(f"[Qdrant] List error: {e}")
            return []

    def delete_point(self, point_id: str):
        self.ensure_collection()
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=[point_id]),
        )


qdrant_service = QdrantService()
