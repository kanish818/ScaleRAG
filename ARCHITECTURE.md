# ScaleRAG Architecture

## Diagram

```mermaid
flowchart LR
    U["User"] --> F["React Frontend"]
    F -->|REST + SSE| B["FastAPI API"]
    B --> A["JWT Auth + OAuth"]
    B --> G["Prompt Injection Guard + Rate Limiter"]
    B --> C["Conversation Memory"]
    B --> I["Document Processor"]
    I --> P["Parsers: PDF / HTML / CSV"]
    P --> H["Semantic Chunker"]
    H --> E["Gemini Embeddings"]
    E --> V["Vector Store"]
    I --> S["Supabase Storage"]
    B --> R["Hybrid Retrieval"]
    R --> V
    R --> M["BM25 + RRF + Reranker"]
    M --> L["Groq LLM"]
    L -->|fallback| GF["Gemini Flash"]
    L --> D["Answer + Citations + Hallucination Score"]
    D --> F
```

## Key design choices

- Ingestion supports `PDF`, `HTML`, and `CSV`, with OCR fallback for scanned PDFs.
- Retrieval uses dense embeddings plus sparse BM25 and fuses both rankings with RRF before reranking.
- Context is compressed before generation to reduce latency and cost.
- Generation streams over SSE and persists conversation history for follow-up questions.
- Reliability features include prompt-injection checks, suspicious-context sanitization, rate limiting, worker retries, health checks, and model fallback.
- Production profile uses Supabase Postgres + pgvector; local/demo fallback works with SQLite plus Python cosine search.
