"""
Indexer factory — returns the appropriate codebase indexing function based on config.

Config (config.yaml):
    rag.mode: "hybrid" | "vector" | "keyword"
    rag.vector_store.provider: "qdrant" | "chromadb" | "elasticsearch"

Implementations:
    - hybrid + qdrant     -> hybrid_qdrant.index_codebase (BM25 + vector)
    - vector + qdrant     -> semantic_qdrant.index_codebase (vector only)
    - vector + chromadb   -> semantic_chroma.index_codebase (vector only)
"""

from educosys_claude.config import config
from educosys_claude.observability.logger import get_logger


logger = get_logger(__name__)


def get_indexer():
    """
    Return an indexer function matching the configured RAG mode and vector store.

    Returns:
        Callable: function(repo_path: str) -> Indexer
                  Indexer has .index() to build/index the codebase
    """
    mode = config["rag"]["mode"]
    provider = config["vector_store"]["provider"]

    logger.debug(f"Indexer config: mode={mode}, provider={provider}")

    if mode == "hybrid" and provider == "qdrant":
        from .hybrid_qdrant import index_codebase
        logger.info("Using hybrid Qdrant indexer (BM25 + vector)")
    elif provider == "qdrant":
        from .semantic_qdrant import index_codebase
        logger.info("Using semantic Qdrant indexer (vector only)")
    else:
        from .semantic_chroma import index_codebase
        logger.info("Using semantic ChromaDB indexer (vector only)")

    return index_codebase


def get_index_inspector():
    """
    Return a function to inspect/print the current index contents.

    Used by CLI command: /show_index

    Returns:
        Callable: function(index) -> None (prints to console)
    """
    mode = config["rag"]["mode"]
    provider = config["vector_store"]["provider"]

    if mode == "hybrid" and provider == "qdrant":
        from .hybrid_qdrant import show_index
    elif provider == "qdrant":
        from .semantic_qdrant import show_index
    else:
        from .semantic_chroma import show_index

    return show_index