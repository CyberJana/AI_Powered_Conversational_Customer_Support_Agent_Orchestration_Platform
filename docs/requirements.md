# Requirements — AI Customer Support & Secure Agent Platform (AICSP)

## 1. Overview

AICSP is a web-based AI customer-support platform combining conversational AI,
retrieval-augmented generation (RAG), configurable agent playbooks, tool
calling, security guardrails, and human escalation, with an admin dashboard
for operators.

This document defines functional and non-functional requirements, user roles,
and acceptance criteria used to drive implementation phase-by-phase.

## 2. User Roles

| Role     | Description                                                            |
|----------|-------------------------------------------------------------------------|
| Admin    | Manages organizations, users, knowledge bases, agents, playbooks, tools, security policy, and views all analytics. |
| Agent    | Human support agent. Handles escalated conversations, views AI context (confidence, sources, tool calls), can respond directly. |
| Customer | End-user chatting with the AI support assistant. Can send messages, view history, give feedback, and request a human. |

## 3. Functional Requirements

### 3.1 Conversational AI
- FR-1: Customers can start a conversation and exchange messages with an AI assistant.
- FR-2: Every AI response is generated using retrieved knowledge-base context when available (RAG), never fabricated when no context exists and confidence is required.
- FR-3: Conversations and messages are persisted with timestamps, confidence score, and cited sources.

### 3.2 Knowledge Base
- FR-4: Admins can create knowledge bases and upload PDF, TXT, Markdown, and CSV documents.
- FR-5: Uploaded documents go through an ingestion pipeline: extraction → cleaning → chunking → embedding → storage in pgvector, with status tracking (PENDING/PROCESSING/COMPLETED/FAILED).
- FR-6: Admins can view, delete, and re-index documents.

### 3.3 RAG Engine
- FR-7: The system exposes `retrieve(query, knowledge_base_id)` performing embedding generation, vector similarity search, metadata filtering, top-k retrieval, deduplication, and citation return.
- FR-8: If retrieved context is insufficient, the system explicitly states insufficient knowledge instead of hallucinating, and may trigger escalation.

### 3.4 Intent Detection
- FR-9: Each incoming message is classified into one of a fixed intent taxonomy with a confidence score, stored in conversation metadata.

### 3.5 Agents & Playbooks
- FR-10: Admins can define agents (name, description, system instructions, allowed tools, knowledge bases, confidence threshold, escalation policy).
- FR-11: Playbooks define ordered steps (e.g., Order Tracking) that combine intent detection, tool calls, RAG, and confidence evaluation.

### 3.6 Tool Calling
- FR-12: A fixed, explicitly allow-listed set of tools is available to agents, each with a name, description, JSON input schema, permission, timeout, and audit log entry. No arbitrary code/SQL execution from the LLM is permitted.

### 3.7 Confidence & Escalation
- FR-13: A composite confidence score is computed from intent confidence, retrieval relevance, source coverage, grounding validation, and tool success.
- FR-14: Conversations below threshold, or matching explicit triggers (user request, sensitive topic, repeated failure, security event, tool failure, policy restriction) are escalated to a human queue.

### 3.8 Evaluation & Continuous Learning
- FR-15: An evaluation harness runs a labeled test dataset and reports intent accuracy, retrieval precision/recall, groundedness, correctness, hallucination rate, tool success rate, escalation rate, latency, and token usage.
- FR-16: Low-confidence conversations, negative feedback, and failed retrievals/tool calls are captured into a review queue; only human-approved corrections are promoted into the evaluation/training dataset.

### 3.9 Security
- FR-17: Prompt-injection detection (layered: heuristic + pattern + structural), PII detection/masking, document ingestion validation, output guardrails, and tool authorization/rate limiting are enforced, with all security events audit-logged.

### 3.10 Observability & Admin
- FR-18: Structured logs are emitted for every request (request id, conversation id, user id, model, latencies, token usage, retrieved docs, tool calls, errors, confidence, security events) excluding secrets/raw PII.
- FR-19: An admin dashboard shows real, database-backed metrics: conversation volume, AI-resolution rate, escalation rate, average response time, retrieval quality, evaluation score, security events, failed requests.

## 4. Non-Functional Requirements

- NFR-1 (Security): No secrets in source control; environment-variable based configuration; password hashing (bcrypt/argon2); JWT-based auth with role-based authorization on every protected route.
- NFR-2 (Reliability): All external tool calls have timeouts and are logged; failures degrade gracefully to escalation rather than crashing.
- NFR-3 (Portability): Entire stack runs locally via `docker compose up` (frontend, backend, postgres+pgvector).
- NFR-4 (Testability): Backend and frontend have automated tests (unit, integration, security) runnable via `pytest` / `vitest`; CI fails the build on critical test failures.
- NFR-5 (Maintainability): Modular backend (`models/schemas/api/services/rag/agents/security/evaluation/utils/middleware`) and modular frontend (`components/pages/layouts/hooks/services/types/lib`).
- NFR-6 (Honesty): No fabricated benchmark numbers; evaluation reports state dataset size, method, and conditions.

## 5. Out of Scope (this iteration)
- Live cloud deployment execution (Vercel/Render/Supabase project provisioning) — configuration and docs are provided, but no live deployment is performed without user-provided credentials.
- Real external business systems (orders, billing) — replaced with clearly-labeled mock APIs with production-ready interfaces.
- Model fine-tuning execution — only dataset preparation for future fine-tuning is implemented.
