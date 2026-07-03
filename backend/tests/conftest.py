import os
os.environ["QDRANT_URL"] = "http://localhost:19999"
os.environ["GEMINI_API_KEY"] = "fake-test-key"

import sys
from unittest.mock import MagicMock, patch
import qdrant_client

# Mock Qdrant client to prevent local storage lock
mock_qdrant = MagicMock()
mock_qdrant.get_collections.return_value = MagicMock(collections=[])
mock_qdrant.count.return_value = MagicMock(count=0)

qdrant_patcher = patch("qdrant_client.QdrantClient", return_value=mock_qdrant)
qdrant_patcher.start()
