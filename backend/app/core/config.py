from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    gemini_api_key: str = ""
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    embedding_model: str = "text-embedding-004"
    llm_model: str = "gemini-1.5-flash"
    collection_name: str = "knowledge_base"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
