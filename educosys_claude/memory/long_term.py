"""
Long-term memory for Educosys Claude.

Extracts, stores, and retrieves semantic facts across conversation sessions.
Uses a separate vector store collection from the codebase index.
"""

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from educosys_claude.config import config
from educosys_claude.llm.factory import get_llm, get_embedder
from educosys_claude.observability.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MemoryFact:
    """A single extracted fact/preference/pattern from conversation history."""
    id: str                    # UUID
    content: str               # Natural language fact (e.g., "User prefers pytest over unittest")
    category: str              # "preference" | "pattern" | "fact" | "project_context"
    confidence: float          # 0.0 - 1.0
    source_thread_id: str      # Which conversation this came from
    created_at: str = ""       # ISO timestamp (set automatically if empty)
    metadata: dict = None      # Flexible extra data (file paths, tech stack, etc.)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryFact":
        return cls(**data)


# ---------------------------------------------------------------------------
# Prompts for fact extraction
# ---------------------------------------------------------------------------

EXTRACT_FACTS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a memory extraction system. Analyze the conversation and extract
salient, durable facts that would be useful in FUTURE conversations.

Extract ONLY facts that are:
- Persistent across sessions (preferences, patterns, project context)
- Specific and actionable (not vague generalities)
- Not already obvious from the codebase itself

Categories:
- "preference": User's coding style, tool preferences, workflow choices
- "pattern": Recurring patterns in how they work or what they ask
- "fact": Concrete information about the project/team/environment
- "project_context": Architectural decisions, tech stack, conventions

Return JSON array of objects with fields:
  content, category, confidence (0.0-1.0), metadata (optional dict)

Examples:
[
  {{"content": "User prefers pytest with fixtures over unittest", "category": "preference", "confidence": 0.9}},
  {{"content": "Project uses FastAPI with async SQLAlchemy", "category": "project_context", "confidence": 0.95}},
  {{"content": "User often asks for tests before implementation", "category": "pattern", "confidence": 0.7}}
]

If no extractable facts, return empty array []."""),
    ("human", "Conversation:\n{conversation}\n\nExtract facts as JSON array:"),
])


# ---------------------------------------------------------------------------
# LongTermMemory class
# ---------------------------------------------------------------------------

class LongTermMemory:
    """
    Manages persistent semantic memory across conversation sessions.

    Architecture:
    - Separate vector store collection ("user_memory") from codebase index
    - Facts extracted by LLM after each conversation turn
    - Retrieved via semantic similarity at query time
    - Injected into agent context as relevant background
    """

    def __init__(self, collection_name: str = "user_memory"):
        self.collection_name = collection_name
        self.llm = get_llm()
        self.embedder = get_embedder()
        self._vector_store = None  # Lazy init

    def _get_vector_store(self):
        """Lazy-initialize the vector store for memory."""
        if self._vector_store is not None:
            return self._vector_store

        provider = config["vector_store"]["provider"]

        if provider == "qdrant":
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, VectorParams
            from langchain_qdrant import QdrantVectorStore

            client = QdrantClient(path=config["chromadb"]["persist_dir"].replace("chromadb", "qdrant"))
            # Ensure collection exists
            collections = client.get_collections().collections
            if not any(c.name == self.collection_name for c in collections):
                client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
                )

            self._vector_store = QdrantVectorStore(
                client=client,
                collection_name=self.collection_name,
                embedding=self.embedder,
            )

        elif provider == "chromadb":
            import chromadb
            from langchain_chroma import Chroma

            persist_dir = config["chromadb"]["persist_dir"]
            client = chromadb.PersistentClient(path=persist_dir)
            self._vector_store = Chroma(
                client=client,
                collection_name=self.collection_name,
                embedding_function=self.embedder,
            )

        else:
            raise ValueError(f"Unsupported vector store provider: {provider}")

        return self._vector_store

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def extract_and_store_facts(
        self,
        thread_id: str,
        messages: List[BaseMessage],
        max_facts: int = 10,
    ) -> List[MemoryFact]:
        """
        Extract facts from a conversation and store them.

        Called after agent completes a turn (in orchestrator or via hook).
        """
        # Format conversation for extraction
        conversation_text = self._format_conversation(messages)
        if not conversation_text.strip():
            return []

        # Extract facts via LLM
        chain = EXTRACT_FACTS_PROMPT | self.llm
        response = await chain.ainvoke({"conversation": conversation_text})

        try:
            facts_data = json.loads(response.content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse fact extraction response as JSON")
            return []

        # Convert to MemoryFact objects
        facts = []
        for i, f in enumerate(facts_data[:max_facts]):
            fact = MemoryFact(
                id=str(uuid.uuid4()),
                content=f.get("content", "").strip(),
                category=f.get("category", "fact"),
                confidence=float(f.get("confidence", 0.5)),
                source_thread_id=thread_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                metadata=f.get("metadata", {}),
            )
            if fact.content:
                facts.append(fact)

        # Store in vector store
        if facts:
            await self._store_facts(facts)

        logger.info(f"Extracted and stored {len(facts)} facts from thread {thread_id}")
        return facts

    async def retrieve_relevant(
        self,
        query: str,
        k: int = 5,
        min_score: float = 0.3,
        categories: Optional[List[str]] = None,
    ) -> List[MemoryFact]:
        """
        Retrieve facts relevant to a query via semantic search.

        Args:
            query: User's current question or context
            k: Number of facts to return
            min_score: Minimum similarity score (0-1)
            categories: Filter by category (e.g., ["preference", "project_context"])

        Returns:
            List of MemoryFact objects, most relevant first
        """
        store = self._get_vector_store()

        # Build filter if categories specified
        filter_dict = None
        if categories:
            filter_dict = {"category": {"$in": categories}}

        # Semantic search
        results = await store.asimilarity_search_with_relevance_scores(
            query, k=k, filter=filter_dict
        )

        facts = []
        for doc, score in results:
            if score < min_score:
                continue
            try:
                fact = MemoryFact.from_dict(json.loads(doc.page_content))
                facts.append(fact)
            except (json.JSONDecodeError, KeyError):
                continue

        logger.debug(f"Retrieved {len(facts)} relevant facts for query: {query[:50]}...")
        return facts

    async def get_context_for_query(self, query: str, k: int = 5) -> str:
        """
        Get formatted memory context string to inject into agent prompt.

        Returns empty string if no relevant facts.
        """
        facts = await self.retrieve_relevant(query, k=k)

        if not facts:
            return ""

        lines = ["=== Relevant Long-Term Memory ==="]
        for fact in facts:
            lines.append(f"- [{fact.category}] {fact.content} (confidence: {fact.confidence:.2f})")
        lines.append("")

        return "\n".join(lines)

    async def delete_facts_by_thread(self, thread_id: str) -> int:
        """Delete all facts originating from a specific thread (e.g., on session reset)."""
        store = self._get_vector_store()
        # Note: Exact deletion by metadata depends on vector store capabilities
        # This is a placeholder - implement based on your vector store
        logger.warning("delete_facts_by_thread not fully implemented for all vector stores")
        return 0

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _format_conversation(self, messages: List[BaseMessage]) -> str:
        """Format messages for fact extraction prompt."""
        parts = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                parts.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                # Skip tool calls, only include actual responses
                if msg.content and not msg.tool_calls:
                    parts.append(f"Assistant: {msg.content}")
            elif isinstance(msg, SystemMessage):
                continue  # Skip system prompts
        return "\n\n".join(parts)

    async def _store_facts(self, facts: List[MemoryFact]) -> None:
        """Store facts in vector store."""
        store = self._get_vector_store()

        texts = [json.dumps(fact.to_dict()) for fact in facts]
        metadatas = [
            {
                "fact_id": fact.id,
                "category": fact.category,
                "confidence": fact.confidence,
                "source_thread_id": fact.source_thread_id,
                "created_at": fact.created_at,
            }
            for fact in facts
        ]

        await store.aadd_texts(texts=texts, metadatas=metadatas)


# ---------------------------------------------------------------------------
# Singleton getter for easy integration
# ---------------------------------------------------------------------------

_long_term_memory: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    """Get or create the global LongTermMemory instance."""
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemory()
    return _long_term_memory
