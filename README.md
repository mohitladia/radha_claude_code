# 🚀 Radha Claude Code

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/dependency-poetry-blueviolet)](https://python-poetry.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A sophisticated, modular code assistant powered by Retrieval-Augmented Generation (RAG) that enables natural language querying of codebases. Built with advanced language models, flexible indexing strategies, and persistent session management for seamless developer productivity.

## ✨ Key Features

- **🧠 Advanced Language Understanding**: Leverages state-of-the-art LLMs (OpenAI/Anthropic) for contextual code comprehension
- **🔍 Flexible Retrieval Strategies**: Hybrid, vector, and keyword-based search with pluggable backends (ChromaDB, Qdrant, Elasticsearch)
- **⚙️ Highly Configurable**: YAML-driven architecture allowing easy customization of models, providers, and retrieval modes
- **💾 Persistent Session Management**: SQLite-based checkpointer with token-aware summarization for context retention
- **🔌 Extensible Tool System**: Plugin-based architecture for adding custom capabilities via MCP servers
- **📊 Observability Built-in**: Structured logging and monitoring for performance insights
- **💬 Interactive REPL**: Rich terminal interface with slash commands for intuitive interaction

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌────────────────────┐
│   User Input    │───▶│   Query Handler  │───▶│   Agent Orchestrator │
└─────────────────┘    └──────────────────┘    └────────────────────┘
                              │                         │
                              ▼                         ▼
                     ┌──────────────────┐    ┌────────────────────┐
                     │   Retrieval Mode │    │   Memory System    │
                     │ (Hybrid/Vector/  │    │ (Short-term +      │
                     │  Keyword)        │    │  Session Mgmt)     │
                     └──────────────────┘    └────────────────────┘
                              │                         │
                              ▼                         ▼
                     ┌──────────────────┐    ┌────────────────────┐
                     │   Indexers       │    │   Response Gen     │
                     │ (ChromaDB/       │    │   (LLM-powered)    │
                     │  Qdrant/ES)      │    │                    │
                     └──────────────────┘    └────────────────────┘
                              │                         │
                              └───────────┬─────────────┘
                                          ▼
                                  ┌──────────────────┐
                                  │  Codebase Index  │
                                  │  (Vector Store)  │
                                  └──────────────────┘
```

## 📦 Installation

### Prerequisites
- Python 3.12 or higher
- [Poetry](https://python-poetry.org/) for dependency management
- API keys for your chosen LLM provider (OpenAI or Anthropic)

### Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/radha_claude_code.git
   cd radha_claude_code
   ```

2. **Install dependencies**
   ```bash
   poetry install
   ```

3. **Configure environment variables**
   Create a `.env` file in the project root:
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   # OR
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

4. **Review and adjust configuration** (optional)
   Edit `educosys_claude/config.yaml` to customize:
   - LLM provider and model
   - Embedding provider and model
   - Retrieval mode (hybrid/vector/keyword)
   - Vector store provider (ChromaDB/Qdrant/Elasticsearch)
   - Memory settings

5. **Initialize the codebase index**
   The system automatically creates an index on first run, or you can trigger it manually:
   ```bash
   poetry run educosys_claude
   # Then use /show_index command in the REPL
   ```

## 🚀 Usage

Start the interactive assistant:
```bash
poetry run educosys_claude
```

### Available Commands

| Command | Description |
|---------|-------------|
| `/ask <question>` | Query the codebase using natural language |
| `/show_index` | Display all indexed code chunks and statistics |
| `/new_session` | Start a fresh conversation session |
| `/switch <session_id>` | Switch to an existing session by ID |
| `/session` | Show current session ID |
| `/exit` or `/quit` | Terminate the assistant |

### Example Workflow

```bash
> /ask How does the authentication system work in this codebase?
[dim]Searching for: How does the authentication system work in this codebase?...[/dim]
[Response generated based on indexed code]

> /new_session
[green]New session started: abc123[/green]

> /ask Explain the vector storage implementation
[dim]Searching for: Explain the vector storage implementation...[/dim]
[Response generated]

> /session
[dim]Current session: abc123[/dim]

> /switch def456
[green]Switched to session: def456[/green]
```

## ⚙️ Configuration

All configuration is managed through `educosys_claude/config.yaml`:

```yaml
llm:
  provider: openai        # openai | anthropic
  model: gpt-4o

embeddings:
  provider: openai             
  model: text-embedding-3-small

chromadb:
  persist_dir: .chromadb/
  collection_name: codebase

elasticsearch:
  url: http://localhost:9200
  index_name: codebase

rag:
  mode: hybrid          # hybrid | vector | keyword

vector_store:
  provider: qdrant
  retrieval_mode: hybrid        # chromadb | elasticsearch | qdrant

qdrant:
  collection_name: ladiamohit

memory:
  db_path: .memory/memory.db
  summarize_at_tokens: 4000
  keep_last_messages: 20
```

### Supported Providers

- **LLM Providers**: OpenAI (`gpt-4o`, `gpt-4-turbo`, etc.), Anthropic (`claude-3-opus`, `claude-3-sonnet`, etc.)
- **Embedding Providers**: OpenAI (`text-embedding-3-small`, `text-embedding-3-large`)
- **Vector Stores**: ChromaDB (local), Qdrant (local/cloud), Elasticsearch
- **Retrieval Modes**: 
  - `hybrid`: Combines vector similarity and keyword matching (BM25)
  - `vector`: Pure vector similarity search
  - `keyword`: Traditional text-based search

## 🔧 Development

### Project Structure
```
radha_claude_code/
├── educosys_claude/              # Main package
│   ├── __init__.py
│   ├── main.py                   # Application entry point
│   ├── config.py                 # Configuration loader
│   ├── config.yaml               # Default configuration
│   ├── agent/                    # Agent factory and orchestrator
│   ├── context/                  # Indexing and retrieval systems
│   │   ├── indexers/             # Vector store implementations
│   │   └── retrievers/           # Retrieval strategies
│   ├── llm/                      # LLM and embedding providers
│   ├── memory/                   # Session and memory management
│   ├── observability/            # Logging and monitoring
│   ├── tools/                    # Available tools for agents
│   └── mcp/                      # Model Context Protocol servers
├── .env                          # Environment variables (not in repo)
├── poetry.lock                   # Dependency lock file
├── pyproject.toml                # Poetry configuration
└── README.md                     # This file
```

### Running Tests
```bash
# Install test dependencies
poetry install --with test

# Run tests
poetry run pytest
```

### Code Formatting
```bash
# Format code with Black
poetry run black .

# Check formatting
poetry run black --check .
```

## 📚 API Reference

The core functionality is accessible through the `educosys_claude` package:

### Main Application
```python
from educosys_claude.main import run

# Start the assistant programmatically
run()
```

### Key Modules
- `educosys_claude.agent.factory`: Build and configure agents
- `educosys_claude.context.indexers.factory`: Get indexer implementations
- `educosys_claude.llm.factory`: Initialize LLM and embedding models
- `educosys_claude.memory.session`: Manage user sessions
- `educosys_claude.memory.short_term`: Handle conversation history

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Contribution Guidelines
- Follow the existing code style (Black formatter)
- Write clear, descriptive commit messages
- Add tests for new functionality
- Update documentation as needed
- Ensure all CI checks pass before submitting

### Reporting Issues
Please use the [issue tracker](https://github.com/yourusername/radha_claude_code/issues) to report bugs or request features. Include:
- Detailed description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Environment details (Python version, OS, etc.)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [LangChain](https://www.langchain.com/) for RAG foundations
- [Rich](https://github.com/Textualize/rich) for beautiful terminal UI
- [Poetry](https://python-poetry.org/) for dependency management
- [OpenAI](https://openai.com/) and [Anthropic](https://www.anthropic.com/) for advanced language models
- All contributors who have helped shape this project

## 📞 Support

For questions, feedback, or support:
- Open an issue on GitHub
- Email: ladiamohit92@gmail.com
- Discussions: [GitHub Discussions](https://github.com/yourusername/radha_claude_code/discussions)

---

**Radha Claude Code** - Making codebases understandable through intelligent interaction. 🚀