"""
Configuration loader — reads settings from config.yaml at the package root.

The config dict is a module-level singleton loaded on import.
All modules import `from educosys_claude.config import config` to access settings.

Example config.yaml structure:
    llm:
      provider: openai          # openai | anthropic
      model: gpt-4o

    embeddings:
      provider: openai
      model: text-embedding-3-small

    chromadb:
      persist_dir: .radha/chromadb/
      collection_name: codebase

    qdrant:
      collection_name: my_project

    rag:
      mode: hybrid              # hybrid | vector | keyword
      vector_store:
        provider: qdrant        # qdrant | chromadb | elasticsearch

    memory:
      db_path: .radha/memory/memory.db
      summarize_at_tokens: 4000
      keep_last_messages: 20

    skills:
      skills_dir: .radha/skills
"""

import yaml
from pathlib import Path


def load_config() -> dict:
    """Load and parse config.yaml from the package directory."""
    config_path = Path(__file__).parent / "config.yaml"
    return yaml.safe_load(config_path.read_text())


# Module-level singleton — loaded once on first import
config = load_config()