# 📚 Context Package

The `context` package handles the core Retrieval-Augmentation (RAG) functionality: indexing the codebase and retrieving relevant code snippets in response to user queries. It contains the indexing and retrieval subsystems that power the semantic search capabilities.

## 📁 Package Structure

```
educosys_claude/context/
├── __init__.py
├── indexers/           # Code indexing implementations
│   ├── __init__.py
│   ├── code_parser.py  # AST-based code parsing
│   ├── factory.py      # Factory for selecting indexer
│   ├── hybrid_qdrant.py # Hybrid (dense+sparse) Qdrant indexer
│   ├── semantic_chroma.py # Semantic ChromaDB indexer
│   ├── semantic_qdrant.py               │    #      │   service to indexer/binder mapping   │
│   └── semantic_qdrant.py # Semantic Qdrant indexer                        │
│                                                                           │
└── retrievers/       # Code retrieval implementations                      │
    ├── __init__.py   │                                                     │
    ├── factory.py    │ # Factory for selecting retriever                   │
    ├── hybrid_qdrant.py # Hybrid (dense+sparse) Qdrant retriever          │
    ├── semantic_chroma.py # Semantic ChromaDB retriever                   │
    └── semantic_qdrant.py # Semantic Qdrant retriever                    │
                                                                              │
```

## 🧩 Components

### 1. Code Parsing (`code_parser.py`)

**Purpose**: Parses source code files into structured chunks suitable for indexing and retrieval. Uses tree-sitter for AST-based parsing of programming languages and falling back to sliding window for text files.

**Key Components**:
- `ParsedChunk` dataclass: Represents a code chunk with metadata
- `parse_file(filepath) -> list[ParsedChunk]`: Main entry point - routes to AST or sliding window parsing
- `_parse_with_treesitter()`: Extracts functions, classes, and other code blocks using tree-sitter grammars
- `_sliding_window()`: Fallback for text files and when AST parsing finds nothing
- `get_source_files()`: Discovers all indexable files in a repository

**How It Works**:
1. Determines file type by extension
2. For code files: Uses tree-sitter to parse AST and extract named blocks (functions, classes, etc.)
3. For text files or when AST yields no blocks: Uses sliding window approach
4. Each chunk includes:
   - Content: The actual code/text
   - Metadata: File path, name, type (function/class/block), line numbers
   - Language-specific parsing via tree-sitter grammars

**Supported Languages**: Python, JavaScript/TypeScript, Java, Go, Rust, C/C++, C#, Ruby, PHP, Swift, Kotlin, Bash
**Text Formats**: Markdown, plain text, YAML, YML, JSON, TOML

### 2. Indexer Factory (`indexers/factory.py`)

**Purpose**: Selects the appropriate indexer implementation based on configuration.

**Key Functions**:
- `get_indexer() -> callable`: Returns the indexing function based on `rag.mode` and `vector_store.provider`
- `get_index_inspector() -> callable`: Returns the index display function based on same config

**Selection Logic**:
- If `rag.mode == "hybrid"` AND `vector_store.provider == "qdrant"` → `hybrid_qdrant.index_codebase`
- Else if `vector_store.provider == "qdrant"` → `semantic_qdrant.index_codebase`
- Else (default) → `semantic_chroma.index_codebase`

The same logic applies to the index inspector (show_index function).

### 3. Indexer Implementations

#### a) ChromaDB Semantic Indexer (`indexers/semantic_chroma.py`)
- Uses ChromaDB vector store
- Dense vector embeddings only
- Persistent storage in `.chroma: .chromadb/ directory
- Collection name from config: `chromadb.collection_name`

#### b) Qdrant Semantic Indexer (`indexers/semantic_qdrant.py`)
- Uses Qdrant vector store
- Dense vector embeddings only
- Supports local or cloud Qdrant instances
- URL and API key from environment variables
- Collection name from config: `qdrant.collection_name`

#### c) Hybrid Qdrant Indexer (`indexers/hybrid_qdrant.py`)
- Uses Qdrant with both dense and sparse vectors
- Dense: Semantic embeddings from OpenAI/HuggingFace
- Sparse: BM25-style keyword matching (FastEmbedSparse)
- Configurable retrieval mode: dense, sparse, or hybrid
- Same connection parameters as semantic_qdrant

### 4. Retriever Factory (`retrievers/factory.py`)

**Purpose**: Selects the appropriate retriever implementation based on configuration.

**Key Function**:
- `get_retriever() -> callable`: Returns the retrieval function based on `rag.mode` and `vector_store.provider`

**Selection Logic**: Identical to indexer factory.

### 5. Retriever Implementations

#### a) ChromaDB Semantic Retriever (`retrievers/semantic_chroma.py`)
- Queries ChromaDB for similar vectors
- Returns top-k results with metadata

#### b) Qdrant Semantic Retriever (`retrievers/semantic_qdrant.py`)
- Queries Qdrant for similar dense vectors
- Returns top-k results with metadata

#### c) Hybrid Qdrant Retriever (`retrievers/hybrid_qdrant.py`)
- Queries Qdrant using dense, sparse, or hybrid search
- Mode controlled by `vector_store.retrieval_mode` (dense/sparse/hybrid)
- Returns top-k results with metadata and distance scores

## 🔧 How It All Works Together

### Indexing Process
```
1. Application Start
     ↓
2. main.py calls get_or_create_index()
     ↓
3. context/indexers/factory.py:get_indexer()
     ↓
4. Based on config, returns specific indexer function
     ↓
5. indexer(repo_path) called:
     ↓
   a. context/indexers/code_parser.py:get_source_files()
        ↓
        Finds all indexable files in repo
     ↓
   b. For each file:
        context/indexers/code_parser.py:parse_file()
        ↓
        Returns list of ParsedChunk objects
     ↓
   c. Convert chunks to Documents with metadata
     ↓
   d. Generate embeddings:
        llm/factory.py:get_embedder()
        ↓
        Returns OpenAIEmbeddings or HuggingFaceEmbeddings
     ↓
   e. Store in vector store:
        ChromaDB: from_documents() with persist directory
        Qdrant: from_documents() with URL/API key
        Hybrid Qdrant: same + sparse embeddings
     ↓
6. Return vector store instance
```

### Query Processing
```
1. User asks: "/ask How does the authentication work?"
     ↓
2. main.py → agent/tools.py:search_codebase()
     ↓
3. tools/search_codebase.py:
     ↓
   a. context/retrievers/factory.py:get_retriever()
        ↓
        Returns specific retriever function
     ↓
   b. retriever(query, k=5) called:
        ↓
      i. Get embedder: llm/factory.py:get_embedder()
      ii. Initialize vector store from existing collection
      iii. Perform similarity_search_with_score(query, k=k)
      iv. Format results as list of dicts with:
           - content: text chunk
           - source: file path
           - name: function/class name
           - type: function/class/block
           - start_line/end_line: line numbers
           - distance: relevance score
     ↓
   c. Return formatted results
     ↓
4. Agent uses results to answer question with citations
```

## ⚙️ Configuration

Configuration occurs in `educosys_claude/config.yaml`:

```yaml
# RAG Configuration
rag:
  mode: hybrid          # hybrid | vector | keyword

# Vector Store Configuration
vector_store:
  provider: qdrant      # chromadb | elasticsearch | qdrant
  retrieval_mode: hybrid # chromadb | elasticsearch | qdrant (for qdrant provider)

# ChromaDB Settings
chromadb:
  persist_dir: .chromadb/
  collection_name: codebase

# Elasticsearch Settings  
elasticsearch:
  url: http://localhost:9200
  index_name: codebase

# Qdrant Settings
qdrant:
  collection_name: ladiamohit
  # URL and API key from environment variables:
  # QDRANT_URL, QDRANT_API_KEY

# Embedding/Model Configuration (in llm section)
embeddings:
  provider: openai      # openai | huggingface
  model: text-embedding-3-small
```

### Configuration Matrix

The system supports these combinations:

| RAG Mode | Vector Store | Description |
|----------|--------------|-------------|
| vector | chromadb | Dense vectors only with ChromaDB |
| vector | qdrant | Dense vectors only with Qdrant |
| vector | elasticsearch | Dense vectors only with Elasticsearch |
| hybrid | qdrant | Dense + sparse vectors with Qdrant (BM25) |
| keyword | any | Traditional keyword search (not fully implemented in current code) |

**Note**: The keyword mode appears to fall back to semantic_chroma in the current implementation.

## 🔍 Retrieval Modes (Qdrant Hybrid Only)

When using Qdrant with hybrid capabilities:
```yaml
vector_store:
  retrieval_mode: hybrid  # dense | sparse | hybrid
```

- **dense**: Uses only semantic embeddings (best for conceptual similarity)
- **sparse**: Uses only BM25-style keyword matching (best for exact term matches)
- **hybrid**: Combines both with configurable weighting (best overall performance)

## 📝 Usage Examples

### Direct Indexing
```python
from educosys_claude.context.indexers.factory import get_indexer

# Get the appropriate indexer
indexer = get_indexer()

# Index a repository
vector_store = indexer("/path/to/repository")
```

### Direct Retrieval
```python
from educosys_claude.context.retrievers.factory import get_retriever

# Get the appropriate retriever
retriever = get_retriever()

# Search for code
results = retriever("How does authentication work?", k=5)
# Returns list of dicts with content, source, name, type, line numbers
```

### Integration Points

1. **Main Application** (`main.py`):
   - Calls `get_or_create_index()` to initialize/get vector store
   - Uses `/show_index` command to display indexed content

2. **Agent Tools** (`agent/tools.py`):
   - `search_codebase()` tool uses `get_retriever()` to search codebase
   - Returns formatted results to LLM for answer generation

3. **Index Inspection** (`main.py` `/show_index` command):
   - Calls `get_index_inspector()` to get display function
   - Shows indexed chunks with metadata

## 📊 Performance Characteristics

### Indexing Speed
- **ChromaDB**: Fastest for small-medium corpora (<100K documents)
- **Qdrant**: Better for large-scale deployments, horizontal scaling
- **Factors affecting speed**:
  - File count and size
  - Embedding model complexity
  - Vector store performance
  - Whether parsing uses AST (fast) or sliding window (slower)

### Query Speed
- **ChromaDB**: Good for local development, scales to ~100K vectors
- **Qdrant**: Designed for production scale (millions of vectors)
- **Hybrid search**: Slightly slower than pure dense or sparse but often more accurate

### Storage Requirements
- **Embeddings**: 384-1536 dimensions depending on model
  - text-embedding-3-small: 384 dimensions
  - text-embedding-3-large: 3072 dimensions  
- **Storage per vector**: ~4 bytes/dimension for float32
  - Small model: ~1.5KB/vector
  - Large model: ~12KB/vector
- **Plus overhead**: Metadata, indexes, storage format

## 🛠️ Customization & Extension

### Adding New Vector Stores
To add a new vector store (e.g., Pinecone, Weaviate):
1. Create `indexers/<new_store>_indexer.py` with `index_codebase()` function
2. Create `retrievers/<new_store>_retriever.py` with `retrieve()` function
3. Update `indexers/factory.py` and `retrievers/factory.py` to handle new provider
4. Add configuration section to `config.yaml`
5. Add environment variable handling if needed

### Adding New Languages
To add support for a new programming language:
1. Add file extension to `EXTENSION_TO_LANGUAGE` in `code_parser.py`
2. Ensure tree-sitter-languages supports the grammar
3. Test parsing with sample files
4. Verify BLOCK_NODE_TYPES covers key constructs for that language

### Custom Chunking Strategies
To change how code is chunked:
1. Modify `_walk()` function in `code_parser.py` for different AST node handling
2. Adjust `BLOCK_NODE_TYPES` set to include/exclude node types
3. Modify `_sliding_window()` parameters (CHUNK_SIZE, CHUNK_OVERLAP)
4. Add new parsing modes in `parse_file()` dispatcher

## 💡 Best Practices

### For Development
1. **Use ChromaDB locally**: Fast setup, no external dependencies
2. **Start with hybrid Qdrant**: Best balance of semantic and keyword search
3. **Monitor indexing time**: Large codebases may take minutes to hours
4. **Test with representative queries**: Ensure your embedding model works well for your code domain

### For Production
1. **Consider Qdrant cloud**: For scalable, managed vector search
2. **Monitor embedding costs**: OpenAI embeddings have per-token costs
3. **Backup vector stores**: Especially for ChromaDB (portable) or Qdrant snapshots
4. **Set appropriate chunk size**: Too small loses context; too large reduces precision
5. **Consider hybrid search**: Often provides best results for code search

### Configuration Tips
1. **Start with defaults**: `rag.mode: hybrid`, `vector_store.provider: qdrant`, `vector_store.retrieval_mode: hybrid`
2. **Adjust embedding model**: Use `text-embedding-3-small` for cost-effectiveness, `text-embedding-3-large` for maximum quality
3. **Tune chunk size**: Default 50 lines with 10 line overlap works well for most code
4. **Environment variables**: Use for sensitive data like API keys:
   ```bash
   export QDRANT_URL="https://your-cluster.qdrant.io"
   export QDRANT_API_KEY="your-key-here"
   ```

## 🔧 Troubleshooting

### Common Issues
1. **"No such file or directory" for .chromadb/**:
   - Ensure the directory exists or is creatable
   - Check permissions on the directory

2. **Connection errors to Qdrant/Elasticsearch**:
   - Verify URL and API key environment variables
   - Check network connectivity
   - Confirm service is running and accessible

3. **Embedding model errors**:
   - For OpenAI: Validate API key and billing status
   - For HuggingFace: Ensure model name is correct and internet connectivity

4. **Slow indexing**:
   - Check if using slowing embedding model
   - Verify file parsing is working (check logs for "Parsed X chunks")
   - Consider excluding large binary or generated files

5. **Poor search results**:
   - Try different retrieval modes (dense/sparse/hybrid)
   - Consider different embedding models
   - Adjust chunk size - smaller for precise matches, larger for context
   - Check if code is being parsed correctly (look at indexing logs)

### Performance Optimization
1. **Batch processing**: Indexers already use batches (size 50 for Qdrant)
2. **Embedding caching**: Consider caching embeddings for frequently accessed files
3. **Selective indexing**: Modify `get_source_files()` to exclude irrelevant directories
4. **Vector store tuning**: For Qdrant, consider adjusting hnsw_config parameters
5. **Query optimization**: Use appropriate k values - too high increases latency unnecessarily