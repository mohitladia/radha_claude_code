"""
Logging configuration for Educosys Claude.

Provides structured logging with:
- Console output (configurable)
- Rotating file output (configurable path, size, backup count)
- Per-module loggers at DEBUG level
- Third-party library suppression at WARNING
"""

import logging
import logging.handlers
from pathlib import Path

from educosys_claude.config import config


def setup_logging() -> None:
    """
    Initialize logging based on config.yaml settings.

    Called once at application startup (in main.py).
    """
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "DEBUG").upper(), logging.DEBUG)
    file_path = log_cfg.get("file_path", ".radha/logs/agent.log")
    max_bytes = log_cfg.get("max_bytes", 10_485_760)
    backup_count = log_cfg.get("backup_count", 5)
    fmt = log_cfg.get("format", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    console_enabled = log_cfg.get("console", True)

    # Ensure log directory exists
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)

    # Create formatters
    formatter = logging.Formatter(fmt)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers (avoid duplicates on reload)
    root_logger.handlers.clear()

    # Console handler
    if console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        file_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Suppress noisy third-party libraries
    for noisy in [
        "openai",
        "httpx",
        "httpcore",
        "urllib3",
        "chromadb",
        "qdrant_client",
        "langchain",
        "langgraph",
        "langchain_core",
        "langchain_openai",
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Our loggers run at DEBUG level (set by root logger).
    Third-party libraries are suppressed to WARNING.
    """
    return logging.getLogger(name)


# Initialize on import
setup_logging()