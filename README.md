# radha-claude-code

Radha Claude Code is a sophisticated and modular code assistant that leverages advanced Retrieval-Augmented Generation (RAG) techniques to assist developers in querying and understanding complex codebases. By utilizing state-of-the-art language models and embedding technologies, it provides a dynamic, interactive question-answer interface tailored for both developers and learners.

## Project Overview

Radha Claude Code is engineered to integrate seamlessly with diverse codebases, offering efficient indexing, searching, and querying capabilities through a combination of keyword and vector-based approaches.

## Key Features

- **Advanced Language Processing**: Employs OpenAI's language models for superior language understanding and context-aware embedding generation.
- **Flexible Indexing and Retrieval**: Supports multiple retrieval modes including hybrid, vector, and keyword with integration options for Qdrant and ChromaDB.
- **Highly Configurable**: Enables users to customize architecture and functionality by simply altering configuration settings.
- **Robust Session Management**: Facilitates smooth session transitions and context retention across multiple queries.

## Project Architecture

Radha Claude Code is structured around several modular components each fulfilling a specific role in the querying process.

### Core Components

1. **Language Models and Embeddings**: Configurable via `config.yaml`, these are crucial for processing user queries and generating embeddings.
2. **Indexers**: Located in `educosys_claude/context/indexers`, these components utilize configured strategies to index the codebase efficiently.
3. **Retrievers**: Implement different retrieval strategies to fetch indexed data, found in `educosys_claude/context/retrievers`.
4. **Session Handlers**: Manage ongoing user sessions to ensure context continuity and efficient session switching.

### Detailed Component Interaction

1. **Initialization**: Begins with setting up language models and embedding configurations.
2. **Query Processing**: Upon receiving a query, selects appropriate retrieval mode and accesses indexed data.
3. **Response Generation**: Utilizes the LLM to generate and return user-specific responses.

### Configuration Details

Configurations are centralized in the `config.yaml` file, offering flexibility through:

- **Language Models and Providers**: Define the preferred models and service providers.
- **Retrieval Strategies**: Choose among hybrid, vector, and keyword modes to meet specific indexing needs.
- **Database Settings**: Elaborate configurations for ChromaDB and Qdrant supporting persistence and efficient data retrieval.

### Modules

- **Core Module (`educosys_claude/main.py`)**: Initiates setup and manages command processing.
- **Agent Management**: Directs query handling through orchestrated agents.
- **Indexing and Retrieval Modules**: Adapt to configured indexing and retrieval strategies.
- **Memory and Session Modules**: Located in `educosys_claude/memory`, these manage persistent session states and memory.

## Use Cases

Radha Claude Code caters to a variety of scenarios, including:

- **In-depth Codebase Analysis**: Offers clarity on codebase interdependencies and documentation access.
- **Development Assistance**: Provides contextual examples and retrieves relevant coding documentation.
- **Educational Exploration**: Facilitates the learning of programming techniques through comprehensive codebase insights.

## Installation

Ensure Python 3.12+ is installed. Radha Claude Code employs Poetry for managing dependencies.

1. Clone the repository.
2. Navigate to the project directory.
3. Install dependencies using:
   ```bash
   poetry install
   ```

## Usage

Start the assistant with:
```bash
poetry run educosys_claude
```

Supported commands include:
- **`/ask <question>`**: Query the codebase.
- **`/show_index`**: View all indexed sections.
- **`/new_session`**: Initiate a new interactive session.
- **`/switch <session_id>`**: Transition to another session.
- **`/session`**: Display the current session ID.

## Configuration

Edit `config.yaml` to personalize settings related to:

- **LLM and Embeddings Providers**: Options like `openai`.
- **Retrieval Modes**: Choose from providers such as `qdrant` or `chromadb`.

## Dependencies

Core dependencies involve:
- **`openai`**: Powers the language models and embeddings.
- **`chromadb`, `qdrant`**: Critical for vector storage.
- **`rich`**: Enhances console interactivity.
- Additional libraries: `langchain`, `pydantic`, `python-dotenv`, `fastembed`.

## Contributing

Contributions enhance project utility! Submit issues or pull requests for potential improvements.

## Author

Mohit Ladia  
Email: ladiamohit92@gmail.com
