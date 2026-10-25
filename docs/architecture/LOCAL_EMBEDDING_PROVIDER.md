# Zero-paid-API local semantic retrieval

Tropos supports the existing OpenAI embedding adapter and a local Ollama embedding
adapter implementing the same application-owned `EmbeddingProvider` interface.

The Ollama adapter calls `http://127.0.0.1:11434/api/embed` with an installed
`nomic-embed-text` model. No OpenAI account or API key is necessary. Document
and query embeddings use the same model and 768-dimensional vectors. The stored
derived embedding strategy version includes provider/model/dimensions so that
previous OpenAI vectors are not accidentally reused.

## Windows PowerShell setup

Install Ollama from https://ollama.com/download/windows and start the Ollama
application. Pull the embedding model once:

```powershell
ollama pull nomic-embed-text
```

In the PowerShell session that launches Tropos:

```powershell
$env:TROPOS_EMBEDDING_PROVIDER = "ollama"
$env:TROPOS_EMBEDDING_MODEL = "nomic-embed-text"
$env:TROPOS_EMBEDDING_DIMENSIONS = "768"
```

Open Tropos and select **Build semantic index** to create local embeddings, then
test **Dense exact** and **Hybrid RRF**. Groq still handles LLM generation and
uses the separate existing Groq key. Keep Ollama running during search.

The built-in embedding provider remains OpenAI unless Ollama is explicitly
selected. The local model must be installed; changing models requires rebuilding
the semantic index. No external embedding API is called in Ollama mode.

## Validation

The local adapter validates embedding vector count and dimensions, and the
test suite mocks the local endpoint (no network or paid services). Existing
retrieval access controls and exact/hybrid algorithms are unchanged.
