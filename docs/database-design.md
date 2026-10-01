# Database Design — AICSP

PostgreSQL 15+ with `pgvector` extension. All tables use UUID primary keys
(`uuid_generate_v4()` / `gen_random_uuid()`), `created_at`/`updated_at`
timestamps (UTC), and foreign keys with `ON DELETE` behavior noted below.

## Entity List & Key Columns

### organizations
- id (PK), name, created_at, updated_at

### users
- id (PK), organization_id (FK→organizations, CASCADE), email (unique), hashed_password, full_name, role (enum: admin/agent/customer), is_active, created_at, updated_at

### roles
- id (PK), name (unique), description — (reference table backing the `users.role` enum's permissions matrix)

### knowledge_bases
- id (PK), organization_id (FK), name, description, created_at, updated_at

### documents
- id (PK), knowledge_base_id (FK→knowledge_bases, CASCADE), filename, file_type (pdf/txt/md/csv), status (PENDING/PROCESSING/COMPLETED/FAILED), error_message, uploaded_by (FK→users), created_at, updated_at

### document_chunks
- id (PK), document_id (FK→documents, CASCADE), chunk_index, content (text), metadata (jsonb), embedding (vector(1536)), created_at
- Index: ivfflat/hnsw index on `embedding` for cosine similarity; btree on `document_id`.

### conversations
- id (PK), organization_id (FK), customer_id (FK→users, nullable for anonymous), knowledge_base_id (FK, nullable), status (open/escalated/resolved/closed), intent (text, nullable), created_at, updated_at

### messages
- id (PK), conversation_id (FK→conversations, CASCADE), sender (customer/assistant/agent), content (text), confidence (float, nullable), intent (text, nullable), sources (jsonb, nullable), created_at

### intents
- id (PK), name (unique), description — reference/config table for the intent taxonomy.

### agents
- id (PK), organization_id (FK), name, description, system_instructions (text), confidence_threshold (float), escalation_policy (jsonb), created_at, updated_at

### playbooks
- id (PK), agent_id (FK→agents, CASCADE), name, intent (FK→intents.name), steps (jsonb — ordered step definitions), created_at, updated_at

### tools
- id (PK), name (unique), description, input_schema (jsonb), permission (text), timeout_seconds (int), enabled (bool), created_at, updated_at

### agent_runs
- id (PK), conversation_id (FK→conversations, CASCADE), agent_id (FK→agents), playbook_id (FK→playbooks, nullable), status, started_at, finished_at

### tool_calls
- id (PK), agent_run_id (FK→agent_runs, CASCADE), tool_id (FK→tools), input (jsonb), output (jsonb, nullable), success (bool), duration_ms (int), error_message (text, nullable), created_at

### evaluations
- id (PK), name, dataset_size (int), started_at, finished_at, status, created_by (FK→users)

### evaluation_results
- id (PK), evaluation_id (FK→evaluations, CASCADE), test_case_id (text), metric_name, metric_value (float), details (jsonb), created_at

### feedback
- id (PK), message_id (FK→messages, CASCADE), user_id (FK→users, nullable), rating (up/down), comment (text, nullable), created_at

### security_events
- id (PK), conversation_id (FK→conversations, nullable), event_type (prompt_injection/pii_detected/tool_abuse/rate_limit/output_guardrail), severity, details (jsonb), created_at

### audit_logs
- id (PK), user_id (FK→users, nullable), action, resource_type, resource_id, details (jsonb), created_at

### escalations
- id (PK), conversation_id (FK→conversations, CASCADE), reason, ai_confidence (float, nullable), status (open/in_progress/resolved), assigned_to (FK→users, nullable), created_at, updated_at, resolved_at

## Indexing Strategy

- All FK columns indexed.
- `document_chunks.embedding`: vector index (`ivfflat`, `vector_cosine_ops`) for ANN search.
- `messages.conversation_id`, `conversations.organization_id`, `conversations.status`, `escalations.status` indexed for dashboard queries.
- Unique constraint on `users.email`, `tools.name`, `intents.name`.

## Migrations

Managed via Alembic (`backend/migrations/`). Initial migration creates the
`vector` extension, all tables, indexes, and constraints. Seed data (dev-only)
inserts a default organization, admin user (password from env, never
hardcoded), the intent taxonomy, and the initial tool allow-list.
