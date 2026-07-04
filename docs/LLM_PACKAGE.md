# 🧠 LLM Package

The `llm` package is responsible for initializing and configuring Language Models (LLMs) and embedding models used throughout the application. It acts as a factory that returns the appropriate model instances based on configuration settings.

## 📁 Package Structure

```
educosys_claude/llm/
├── __init__.py
└── factory.py          # LLM and embedder factory
```

## 🧩 Components

### Factory (`factory.py`)

**Purpose**: Creates and returns the appropriate LangChain LLM and embedding model instances based on configuration in `config.yaml`.

**Key Functions**:
- `get_llm()`: Returns the configured LLM (Language Model) instance
- `get_embedder()`: Returns the configured embedding model instance

**How It Works**:
1. Reads configuration from `educosys_claude.config.config`
2. Determines provider and model from config sections:
   - LLM: `config["llm"]["provider"]` and `config["llm"]["model"]`
   - Embeddings: `config["embeddings"]["provider"]` and `config["embeddings"]["model"]`
3. Dynamically imports and instantiates the appropriate LangChain class
4. Logs the selection for observability

**Supported Providers**:
- **LLM Providers**:
  - `openai`: Uses `langchain_openai.ChatOpenAI`
  - `anthropic`: Uses `langchain_anthropic.ChatAnthropic`
- **Embedding Providers**:
  - `openai`: Uses `langchain_openai.OpenAIEmbeddings`
  - `huggingface`: Uses `langchain_huggingface.HuggingFaceEmbeddings`

**Configuration Examples**:

For OpenAI GPT-4o:
```yaml
llm:
  provider: openai
  model: gpt-4o

embeddings:
  provider: openai
  model: text-embedding-3-small
```

For Anthropic Claude 3 Opus:
```yaml
llm:
  provider: anthropic
  model: claude-3-opus-20240229

embeddings:
  provider: openai
  model: text-embedding-3-small
```

For HuggingFace embeddings (with OpenAI LLM):
```yaml
llm:
  provider: openai
  model: gpt-4o

embeddings:
  provider: huggingface
  model: sentence-transformers/all-MiniLM-L6-v2
```

## 🔧 How It Works Together

### LLM Initialization Flow
```
config.yaml Configuration Loader
     ↓
llm/config.py:load_config() reads config.yaml
     ↓
llm/factory.py:get_llm()
     ↓
  Reads llm.provider and llm.model
     ↓
  If provider == "anthropic":
      Import ChatAnthropic from langchain_anthropic
      Return ChatAnthropic(model=model)
     ↓
  Else (default to openai):
      Import ChatOpenAI from langchain_openai
      Return ChatOpenAI(model=model)
     ↓
Return LLM instance to caller
```

### Embedder Initialization Flow
```
 Configuration Loader
     ↓
llm/config.py:load_config() reads config.yaml
     ↓
llm/factory.py:get_embedder()
     ↓
  Reads embeddings.provider and embeddings.model
     ↓
  If provider == "huggingface":
      Import HuggingFaceEmbeddings from langchain_huggingface
      Return HuggingFaceEmbeddings(model_name=model)
     ↓
  Else (default to openai):
      Import OpenAIEmbeddings from langchain_openai
      Return OpenAIEmbeddings(model=model)
     ↓
Return embedding instance to caller
```

## ⚙️ Configuration

The LLM package is configured through `educosys_claude/config.yaml`:

```yaml
llm:
  provider: openai        # openai | anthropic
  model: gpt-4o           # Model name specific to provider

embeddings:
  provider: openai        # openai | huggingface
  model: text-embedding-3-small  # Model name specific to provider
```

### Provider-Specific Model Examples

**OpenAI LLM Models**:
- `gpt-4o` (default)
- `gpt-4-turbo`
- `gpt-4`
- `gpt-3.5-turbo`

**Anthropic LLM Models**:
- `claude-3-opus-20240229`
- `claude-3-sonnet-20240229`
- `claude-3-haiku-20240307`

**OpenAI Embedding Models**:
- `text-embedding-3-small` (default)
- `text-embedding-3-large`
- `text-embedding-ada-002`

**HuggingFace Embedding Models**:
- `sentence-transformers/all-MiniLM-L6-v2` (fast, good quality)
- `sentence-transformers/all-mpnet-base-v2` (higher quality, slower)
- `BAAI/bge-small-en-v1.5`
- `BAAI/bge-large-en-v1.5`

## 📝 Usage Examples

### Direct Usage
```python
from educosys_claude.llm.factory import get_llm, get_embedder

# Get LLM instance
llm = get_llm()
# Returns: ChatOpenAI or ChatAnthropic instance

# Get embedder instance
embedder = get_embedder()
# Returns: OpenAIEmbeddings or HuggingFaceEmbeddings instance
```

### Usage in Agent Factory
```python
# In educosys_claude/agent/factory.py
from educosys_claude.llm.factory import get_llm

def build_agent(checkpointer):
    llm = get_llm()  # Gets configured LLM
    # ... rest of agent creation
```

### Usage in Memory Summarization
```python
# In educosys_claude/memory/short_term.py
from educosys_claude.llm.factory import get_llm
from langchain.agents.middleware import SummarizationMiddleware

def get_summarization_middleware():
    return SummarizationMiddleware(
        model=get_llm(),  # Uses same LLM for summarization
        trigger=("tokens", config["memory"]["summarize_at_tokens"]),
        keep=("messages", config["memory"]["keep_last_messages"]),
    )
```

## 🔄 Integration Points

The LLM package is used by:
1. **Agent Package**: For the main reasoning model (`agent/factory.py`)
2. **Memory Package**: For conversation summarization (`memory/short_term.py`)
3. **Context Package**: For embeddings in indexing and retrieval (`context/indexers/*` and `context/retrievers/*`)

## 📊 Performance Notes

- **LLM Choice**: Affects response quality, speed, and cost
  - Opus/Sonnet models: Higher quality, slower, more expensive
  - Haiku models: Faster, lower cost, good for simple tasks
  - GPT-4 Turbo: Balanced performance and cost
- **Embedding Choice**: Affects search quality and dimensionality
  - Larger models (3-large): Better quality, larger vectors, more storage
  - Smaller models (3-small): Good quality, efficient storage and retrieval
- **Provider Trade-offs**:
  - OpenAI: Wide model range, good API reliability
  - Anthropic: Strong reasoning, longer context windows
  - HuggingFace: Local execution possible, privacy-focused, no API costs

## 🛠️ Extending the Factory

To add a new LLM provider:
1. Add the provider to the `if/elif` chain in `get_llm()`
2. Import the appropriate LangChain class
3. Instantiate with the model parameter
4. Update config validation if needed

To add a new embedding provider:
1. Add the provider to the `if/elif` chain in `get_embedder()`
2. Import the appropriate embedding class
3. Instantiate with the model parameter
4. Handle any provider-specific parameters if needed