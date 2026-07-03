from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from app.core.config import settings
from app.models.schemas import KnowledgeEntry, KnowledgeSearchResult, KnowledgeDetail
import uuid
import os
import asyncio


async def _run_sync(fn, *args, **kwargs):
    return await asyncio.to_thread(lambda: fn(*args, **kwargs))


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
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="content",
                    field_type=models.PayloadSchemaType.TEXT,
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="title",
                    field_type=models.PayloadSchemaType.KEYWORD,
                )
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="category",
                    field_type=models.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass
            self._ready = True
        except Exception as e:
            print(f"[Qdrant] Connection failed (server may be starting): {e}")
            self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    async def upsert_knowledge(self, entry: KnowledgeEntry, embedding: list[float]) -> str:
        self.ensure_collection()
        point_id = entry.id or str(uuid.uuid4())
        await _run_sync(
            self.client.upsert,
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

    async def search_hybrid(self, query_embedding: list[float], query_text: str, limit: int = 10) -> list[KnowledgeSearchResult]:
        self.ensure_collection()
        if not self._ready:
            return []
        try:
            vector_results = await _run_sync(
                self.client.query_points,
                collection_name=self.collection_name,
                query=query_embedding,
                limit=limit,
                with_payload=True,
            )
            from app.services.chunker import chunk_text
            text_results = []
            if query_text.strip():
                scroll = await _run_sync(
                    self.client.scroll,
                    collection_name=self.collection_name,
                    limit=200,
                    with_payload=True,
                    with_vectors=False,
                )
                query_lower = query_text.lower()
                query_terms = set(query_lower.split())
                scored = []
                for p in scroll[0]:
                    content = (p.payload.get("content", "") or "").lower()
                    title = (p.payload.get("title", "") or "").lower()
                    score = 0
                    for term in query_terms:
                        if len(term) < 3:
                            continue
                        if term in content:
                            score += content.count(term) * 0.05
                        if term in title:
                            score += 2
                    if score > 0:
                        scored.append((score, p))
                scored.sort(key=lambda x: -x[0])
                text_results = scored[:limit]

            seen_ids = set()
            combined = []
            for res in vector_results.points:
                rid = str(res.id)
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    combined.append(KnowledgeSearchResult(
                        id=rid,
                        title=res.payload.get("title", ""),
                        content=res.payload.get("content", ""),
                        score=res.score,
                        category=res.payload.get("category", ""),
                    ))
            for score, p in text_results:
                pid = str(p.id)
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    combined.append(KnowledgeSearchResult(
                        id=pid,
                        title=p.payload.get("title", ""),
                        content=p.payload.get("content", ""),
                        score=score * 0.5,
                        category=p.payload.get("category", ""),
                    ))
            combined.sort(key=lambda x: -x.score)
            return combined[:limit]
        except Exception as e:
            print(f"[Qdrant] Hybrid search error: {e}")
            return []

    async def search(self, query_embedding: list[float], limit: int = 5) -> list[KnowledgeSearchResult]:
        self.ensure_collection()
        if not self._ready:
            return []
        try:
            results = await _run_sync(
                self.client.query_points,
                collection_name=self.collection_name,
                query=query_embedding,
                limit=limit,
                with_payload=True,
            )
            return [
                KnowledgeSearchResult(
                    id=str(res.id),
                    title=res.payload.get("title", ""),
                    content=res.payload.get("content", ""),
                    score=res.score,
                    category=res.payload.get("category", ""),
                )
                for res in results.points
            ]
        except Exception as e:
            print(f"[Qdrant] Search error: {e}")
            return []

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[KnowledgeDetail]:
        self.ensure_collection()
        if not self._ready:
            return []
        try:
            results = await _run_sync(
                self.client.scroll,
                collection_name=self.collection_name,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            return [
                KnowledgeDetail(
                    id=str(p.id),
                    title=p.payload.get("title", ""),
                    content=p.payload.get("content", ""),
                    category=p.payload.get("category", ""),
                    tags=p.payload.get("tags", []),
                    source_url=p.payload.get("source_url"),
                )
                for p in results[0]
            ]
        except Exception as e:
            print(f"[Qdrant] List error: {e}")
            return []

    async def get_point(self, point_id: str) -> KnowledgeDetail | None:
        self.ensure_collection()
        try:
            results = await _run_sync(
                self.client.retrieve,
                collection_name=self.collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                return None
            p = results[0]
            return KnowledgeDetail(
                id=str(p.id),
                title=p.payload.get("title", ""),
                content=p.payload.get("content", ""),
                category=p.payload.get("category", ""),
                tags=p.payload.get("tags", []),
                source_url=p.payload.get("source_url"),
            )
        except Exception as e:
            print(f"[Qdrant] Get point error: {e}")
            return None

    async def update_point(self, point_id: str, entry: KnowledgeEntry, embedding: list[float] | None = None):
        self.ensure_collection()
        payload = {
            "title": entry.title,
            "content": entry.content,
            "category": entry.category,
            "tags": entry.tags,
            "source_url": entry.source_url,
        }
        await _run_sync(
            self.client.set_payload,
            collection_name=self.collection_name,
            payload=payload,
            points=[point_id],
        )
        if embedding:
            await _run_sync(
                self.client.update_vectors,
                collection_name=self.collection_name,
                points=[models.PointStruct(id=point_id, vector=embedding, payload={})],
            )

    def count_points(self) -> int:
        try:
            result = self.client.count(collection_name=self.collection_name)
            return result.count
        except Exception:
            return 0

    async def delete_point(self, point_id: str):
        self.ensure_collection()
        await _run_sync(
            self.client.delete,
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=[point_id]),
        )


qdrant_service = QdrantService()
