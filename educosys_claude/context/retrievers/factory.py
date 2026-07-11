"""
Retriever factory — returns the appropriate code retrieval function based on config.

Supported modes (config.yaml):
    rag.mode: "hybrid" | "vector" | "keyword"
    rag.vector_store.provider: "qdrant" | "chromadb" | "elasticsearch"

Retrieval implementations:
    - hybrid + qdrant     -> hybrid_qdrant.py (BM25 + vector)
    - vector + qdrant     -> semantic_qdrant.py (vector only)
    - vector + chromadb   -> semantic_chroma.py (vector only)
    - vector + elasticsearch -> semantic_qdrant.py (using Qdrant as fallback)
"""

from educosys_claude.config import config
from educosys_claude.observability.logger import get_logger


logger = get_logger(__name__)


def get_retriever():
    """
    Return a retriever function matching the configured RAG mode and vector store.

    Returns:
        Callable: function(query: str, k: int = 5) -> List[dict]
                  Each dict has: source, start_line, end_line, type, name, content
    """
    mode = config["rag"]["mode"]
    provider = config["vector_store"]["provider"]

    logger.debug(f"Retriever config: mode={mode}, provider={provider}")

    if mode == "hybrid" and provider == "qdrant":
        from .hybrid_qdrant import retrieve
        logger.info("Using hybrid Qdrant retriever (BM25 + vector)")
    elif provider == "qdrant":
        from .semantic_qdrant import retrieve
        logger.info("Using semantic Qdrant retriever (vector only)")
    else:
        from .semantic_chroma import retrieve
        logger.info("Using semantic ChromaDB retriever (vector only)")

    return retrieve