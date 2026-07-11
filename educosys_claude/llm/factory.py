"""
LLM and Embedding factory — creates configured model instances based on config.yaml.
"""

from educosys_claude.config import config
from educosys_claude.observability.logger import get_logger


logger = get_logger(__name__)


def get_llm():
    """
    Return the configured LangChain LLM based on config.yaml settings.

    Config keys (config.yaml):
        llm.provider: "openai" | "anthropic"
        llm.model: model name (e.g., "gpt-4o", "claude-3-5-sonnet")

    Returns:
        LangChain chat model instance (ChatOpenAI or ChatAnthropic).
    """
    provider = config["llm"]["provider"]
    model = config["llm"]["model"]
    logger.info(f"Using LLM provider: {provider}, model: {model}")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model)

    # Default: OpenAI
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model)


def get_embedder():
    """
    Return the configured LangChain embeddings model based on config.yaml.

    Config keys (config.yaml):
        embeddings.provider: "openai" | "huggingface"
        embeddings.model: model name

    Returns:
        LangChain embeddings instance.
    """
    provider = config["embeddings"]["provider"]
    model = config["embeddings"]["model"]
    logger.info(f"Using embeddings provider: {provider}, model: {model}")

    if provider == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name=model)

    # Default: OpenAI
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model=model)