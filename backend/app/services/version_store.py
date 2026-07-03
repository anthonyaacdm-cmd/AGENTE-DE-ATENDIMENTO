import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
VERSIONS_PATH = os.path.join(DATA_DIR, "knowledge_versions.jsonl")


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def save_version(knowledge_id: str, title: str, content: str, category: str, tags: list[str], changed_by: str = "extension"):
    _ensure_dir()
    entry = {
        "id": str(uuid.uuid4()),
        "knowledge_id": knowledge_id,
        "title": title,
        "content": content,
        "category": category,
        "tags": tags,
        "changed_by": changed_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(VERSIONS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    return entry["id"]


def list_versions(knowledge_id: str, limit: int = 20) -> list[dict]:
    _ensure_dir()
    if not os.path.exists(VERSIONS_PATH):
        return []
    versions = []
    with open(VERSIONS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("knowledge_id") == knowledge_id:
                    versions.append(entry)
            except json.JSONDecodeError:
                continue
    return versions[-limit:]
