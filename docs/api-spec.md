# API Specification — AICSP (v1)

Base URL: `/api/v1`

All endpoints (except `/auth/signup`, `/auth/login`, `/health`) require header:
`Authorization: Bearer <JWT>`

Roles: `admin`, `agent`, `customer`.

## Authentication

### POST /api/v1/auth/signup
Request:
```json
{ "email": "user@example.com", "password": "string (min 8 chars)", "full_name": "Jane Doe", "role": "customer" }
```
Response `201`:
```json
{ "id": "uuid", "email": "user@example.com", "role": "customer", "access_token": "jwt", "refresh_token": "jwt" }
```

### POST /api/v1/auth/login
Request: `{ "email": "...", "password": "..." }`
Response `200`: `{ "access_token": "jwt", "refresh_token": "jwt", "token_type": "bearer" }`

### POST /api/v1/auth/refresh
Request: `{ "refresh_token": "jwt" }` → Response: `{ "access_token": "jwt" }`

### GET /api/v1/auth/me
Response: `{ "id", "email", "role", "organization_id" }`

## Chat

### POST /api/v1/chat
Roles: customer, agent, admin
Request:
```json
{ "conversation_id": "uuid|null", "message": "string", "knowledge_base_id": "uuid|null", "agent_id": "uuid|null" }
```
Response `200`:
```json
{
  "message_id": "uuid",
  "conversation_id": "uuid",
  "answer": "string",
  "confidence": 0.0,
  "sources": [{ "document_id": "uuid", "chunk_id": "uuid", "snippet": "string", "score": 0.0 }],
  "intent": "order_tracking",
  "escalated": false
}
```
`confidence` is a composite score (FR-13) blending intent confidence, retrieval relevance, source coverage, citation grounding, and tool success. `escalated` is true when that score is below the agent's (or default) confidence threshold, or an explicit FR-14 trigger fires (human agent request, sensitive topic, tool failure, security event, repeated low confidence) - in which case a real `Escalation` row is created (see below).

### GET /api/v1/conversations
List conversations (paginated, filterable by status/customer).

### GET /api/v1/conversations/{id}
Get conversation with full message history, sources, tool calls.

### POST /api/v1/conversations/{id}/feedback
Request: `{ "message_id": "uuid", "rating": "up|down", "comment": "string|null" }`

## Knowledge Base

### POST /api/v1/knowledge-bases (admin)
### GET /api/v1/knowledge-bases
### POST /api/v1/knowledge-bases/{id}/documents (multipart upload: pdf/txt/md/csv) (admin)
### GET /api/v1/knowledge-bases/{id}/documents
### DELETE /api/v1/documents/{id} (admin)
### POST /api/v1/documents/{id}/reindex (admin)

Document status lifecycle: `PENDING → PROCESSING → COMPLETED | FAILED`

## Agents & Playbooks

### GET/POST /api/v1/agents (admin)
### GET/PUT/DELETE /api/v1/agents/{id} (admin)
### GET/POST /api/v1/playbooks (admin)

## Tools

### GET /api/v1/tools (admin) — lists allow-listed tools with schema/permissions.

## Escalations

### POST /api/v1/escalations
Request: `{ "conversation_id": "uuid", "reason": "string" }`

### GET /api/v1/escalations (agent/admin) — queue with filters.
### POST /api/v1/escalations/{id}/resolve (agent/admin)

## Evaluation

### GET /api/v1/evaluations (admin) — list evaluation runs.
### POST /api/v1/evaluations/run (admin) — triggers evaluation runner.
### GET /api/v1/evaluations/{id} (admin) — report detail.

## Security

### GET /api/v1/security/events (admin) — paginated security_events.

## Analytics

### GET /api/v1/analytics/dashboard (admin/agent)
Response: real aggregate counts — total conversations, ai_resolved, escalations, avg_response_time_ms, retrieval_quality, evaluation_score, security_events_count, failed_requests_count.

## Health

### GET /health → `{ "status": "ok", "database": "ok" }`

## Error Format

```json
{ "error": { "code": "string", "message": "string", "request_id": "uuid" } }
```

Standard HTTP status codes: 400 (validation), 401 (auth), 403 (authorization), 404, 409, 422, 429 (rate limit), 500.
