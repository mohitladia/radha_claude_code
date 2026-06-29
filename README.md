# radha-claude-code

Radha Claude Code is a powerful code assistant designed to answer questions regarding any codebase using Retrieval-Augmented Generation (RAG) techniques. It leverages advanced language models and embeddings to provide an interactive question-answer interface for developers and users.

## Project Overview

The project is designed with a modular architecture, integrating various components for indexing, searching, and querying codebases using both keyword and vector-based approaches.

## Key Features

- **Language Models (LLM) and Embeddings**: Utilizes models from OpenAI for processing language and embedding data.
- **Modular Indexing and Retrieval**: Supports hybrid, vector, and keyword retrieval modes using Qdrant and ChromaDB.
- **Configurable Architecture**: Components can be dynamically loaded and configured based on user preferences.
- **Session Management**: Allows for session tracking and switching, useful for maintaining conversational context.

## Project Architecture

The architecture of the Radha Claude Code system is designed around modular components that work together to provide seamless code querying capabilities.

### Components

1. **LLM and Embeddings**: Used for natural language understanding and embedding generation, configured via `config.yaml`.
2. **Indexers**: Responsible for indexing the codebase using different strategies based on configuration (`educosys_claude/context/indexers`).
3. **Retrievers**: Fetch data from the indexed storage using either vector or keyword-based retrieval (`educosys_claude/context/retrievers`).
4. **Session Management**: Handles user sessions to maintain conversational context across queries.

### Component Interaction

Below is how components typically interact during a request:

- A user query is received via a command.
- The query is processed to determine the required retrieval mode and indexed data.
- The LLM generates a response, which is returned to the user.

### Configuration Options

The `config.yaml` file specifies various configuration options:

- **LLM Settings**: Define the language model and provider, such as OpenAI.
- **Embeddings Settings**: Configurable embedding models and providers.
- **Indexing and Retrieval Modes**: Options include hybrid, vector, and keyword modes.
- **Databases**: Integration settings for ChromaDB and Qdrant for data persistence and retrieval.

### Modules Description

- **Main (`educosys_claude/main.py`)**: Handles the initial setup and runs the main interactive loop for processing user commands.
- **Agent Orchestrator**: Manages agents for handling specific user queries.
- **Indexers and Retrievers**: Provide various strategies for indexing and retrieval based on the configuration.
- **Memory Management**: Supports persistent memory across sessions, defined in `educosys_claude/memory`.

## Use Cases

Radha Claude Code can be used for:

- **Codebase Analysis**: Quickly querying large codebases to understand module interdependencies or fetch documentation snippets.
- **Development Support**: Assisting developers with code examples and documentation retrieval.
- **Educational Purposes**: Learning and exploring programming techniques from existing codebases.

## Installation

Ensure you have Python 3.12 or above installed. This project uses Poetry for dependency management.

1. Clone the repository.
2. Navigate to the project directory.
3. Install dependencies:
   ```bash
   poetry install
   ```

## Usage

To run the code assistant, use the following command:

```bash
poetry run educosys_claude
```

The system supports several commands:
- `/ask <question>`: Ask a question about the codebase.
- `/show_index`: Display all indexed chunks.
- `/new_session`: Start a fresh conversation session.
- `/switch <session_id>`: Switch to a specific session.
- `/session`: Display the current session ID.

## Configuration

Modify the `config.yaml` file to change the settings for LLM, embeddings, databases, and retrieval modes.

- Language Model Provider: `openai`
- Embeddings Provider: `openai`
- Vector Store and Retrieval Mode: Supports providers like `qdrant` and `chromadb`.

## Dependencies

Key dependencies include:
- `openai`: For language models and embeddings.
- `chromadb` and `qdrant`: For data persistence and vector storage.
- `rich`: For formatted console output.
- Others: `langchain`, `pydantic`, `python-dotenv`, `fastembed`.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request with improvements.

## Author

Mohit Ladia  
Email: ladiamohit92@gmail.com
