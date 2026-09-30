# Architecture — AICSP

## 1. System Overview

AICSP is a three-tier application:

- **Frontend**: React + TypeScript + Vite SPA, talking to the backend over REST (JSON), using React Query for data fetching/caching and Tailwind/shadcn for UI.
- **Backend**: Python FastAPI service exposing versioned REST APIs (`/api/v1/*`), organized into API routers, services (business logic), a RAG subsystem, an agent/playbook engine, a security layer, and an evaluation subsystem.
- **Database**: PostgreSQL with the `pgvector` extension for both relational data and vector similarity search (no separate vector DB needed).

## 2. System Architecture Diagram

```mermaid
flowchart TB
    subgraph Client
        UI[React SPA]
    end

    subgraph Backend[FastAPI Backend]
        MW[Middleware: auth, rate limit, logging, CORS]
        API[API Routers /api/v1]
        SEC[Security Layer: prompt-injection, PII, guardrails]
        SVC[Services]
        RAG[RAG Engine]
        AGENTS[Agent/Playbook Engine]
        TOOLS[Tool Framework]
        EVAL[Evaluation Runner]
    end

    subgraph Data[Data Layer]
        PG[(PostgreSQL + pgvector)]
    end

    subgraph External[External Services]
        OPENAI[OpenAI API]
    end

    UI -->|HTTPS/JSON, JWT| MW --> API
    API --> SEC
    SEC --> SVC
    SVC --> RAG
    SVC --> AGENTS
    AGENTS --> TOOLS
    RAG -->|embeddings + completions| OPENAI
    AGENTS -->|completions| OPENAI
    SVC --> PG
    RAG --> PG
    TOOLS --> PG
    EVAL --> PG
    EVAL --> OPENAI
```

## 3. RAG Pipeline

```mermaid
flowchart LR
    Q[User Query] --> V[Validate & Sanitize]
    V --> E[Generate Query Embedding - OpenAI]
    E --> S[pgvector Similarity Search]
    S --> F[Metadata Filtering by knowledge_base_id]
    F --> TK[Select Top-K Chunks]
    TK --> R[Optional Reranking]
    R --> D[Deduplicate Overlapping Context]
    D --> C{Sufficient Context?}
    C -->|Yes| G[Grounded LLM Answer + Citations]
    C -->|No| I[Explicit 'insufficient knowledge' response]
    G --> OUT[Response + sources + confidence]
    I --> OUT
```

## 4. Agent / Playbook Execution

```mermaid
flowchart TB
    Msg[Incoming Message] --> Intent[Intent Classifier]
    Intent --> PB{Playbook for intent?}
    PB -->|Yes| Steps[Execute Playbook Steps]
    PB -->|No| RAGFlow[Default RAG Answer]
    Steps --> ToolCall[Tool Call - allow-listed only]
    ToolCall --> ToolLog[Audit Log Tool Call]
    ToolCall --> Ground[Combine Tool Result + RAG Context]
    Ground --> Conf[Confidence Engine]
    RAGFlow --> Conf
    Conf --> Decision{Confidence Tier}
    Decision -->|High| Answer[Return Answer]
    Decision -->|Medium| Clarify[Ask Clarifying Question]
    Decision -->|Low| Escalate[Create Escalation]
```

## 5. Authentication Flow

```mermaid
sequenceDiagram
    participant U as User (Browser)
    participant F as Frontend
    participant B as Backend API
    participant DB as PostgreSQL

    U->>F: Enter credentials (login/signup)
    F->>B: POST /api/v1/auth/login
    B->>DB: Lookup user, verify password hash
    DB-->>B: User record + role
    B-->>F: JWT access token (+ refresh token)
    F->>F: Store token (memory/secure storage)
    F->>B: Subsequent requests with Authorization: Bearer <token>
    B->>B: Middleware verifies JWT, extracts user/role
    B-->>F: Authorized response or 401/403
```

## 6. Conversation Flow

```mermaid
sequenceDiagram
    participant C as Customer
    participant API as Chat API
    participant SEC as Security Layer
    participant INT as Intent Classifier
    participant RAG as RAG Engine
    participant AG as Agent/Playbook
    participant CONF as Confidence Engine
    participant DB as Database

    C->>API: POST /api/v1/chat {conversation_id, message}
    API->>SEC: Validate input (prompt injection, PII)
    SEC-->>API: Sanitized message / blocked
    API->>INT: Classify intent
    INT-->>API: intent + confidence
    API->>AG: Route to playbook or default flow
    AG->>RAG: retrieve(query, kb_id)
    RAG-->>AG: chunks + citations
    AG->>CONF: compute confidence signals
    CONF-->>AG: final confidence + tier
    AG-->>API: answer, sources, confidence, escalated?
    API->>DB: persist message, sources, confidence, intent
    API-->>C: {message_id, answer, confidence, sources, escalated}
```

## 7. Security Pipeline

```mermaid
flowchart TB
    In[Inbound Message] --> PI[Prompt Injection Detection]
    PI -->|flagged| Block1[Block / Sanitize + Log security_event]
    PI -->|clean| PII[PII Detection]
    PII -->|found| Mask[Mask/Block per policy + Log]
    PII -->|clean| Proc[Process Normally]
    Proc --> ToolSec[Tool Authorization + Rate Limit]
    ToolSec --> Out[LLM Output]
    Out --> OG[Output Guardrails: secrets/PII/unsafe content]
    OG -->|flagged| Block2[Redact/Block + Log]
    OG -->|clean| Resp[Return Response]
```

## 8. Evaluation Pipeline

```mermaid
flowchart LR
    DS[Labeled Test Dataset] --> RUN[Evaluation Runner]
    RUN --> PIPE[Run each case through full chat pipeline]
    PIPE --> METRICS[Compute metrics: intent acc, retrieval P/R, groundedness, correctness, hallucination, tool success, escalation rate, latency, tokens]
    METRICS --> REPORT[evaluation_report.json / .md]
```

## 9. Data Flow Summary

1. Client authenticates → JWT issued.
2. Client sends chat message → backend validates/sanitizes → intent classified.
3. Backend selects playbook (if intent matches) or default RAG flow.
4. RAG retrieves context from pgvector; agent may call allow-listed tools.
5. Confidence engine scores the result; low confidence triggers escalation.
6. Response + metadata persisted; structured log emitted.
7. Admin dashboard reads aggregated data directly from PostgreSQL via read APIs.

## 10. Security Boundaries

- All mutating/admin endpoints require JWT + role check (Admin/Agent as appropriate).
- The LLM never receives direct DB access or shell access — only through the Tool Framework's allow-listed, schema-validated functions.
- Document ingestion content is scanned for hidden instructions before being embedded/indexed.
- Secrets live only in environment variables (`.env`, never committed); `.env.example` documents required keys.

## 11. API Boundaries

All application endpoints are versioned under `/api/v1/`. See `docs/api-spec.md` for full contract definitions.
