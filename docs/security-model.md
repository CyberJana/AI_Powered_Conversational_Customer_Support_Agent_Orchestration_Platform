# Security Model — AICSP

## 1. Threat Model Summary

| Asset | Threats | Mitigations |
|---|---|---|
| User credentials | Credential stuffing, weak hashing | bcrypt/argon2 hashing, rate-limited login, JWT short expiry + refresh tokens |
| LLM system prompt / instructions | Prompt injection / extraction | Layered prompt-injection detection, instruction isolation, output guardrails |
| Customer PII | Leakage via logs/LLM output | PII detection & masking on input and output, redacted logging |
| Knowledge base documents | Malicious/instruction-laden uploads | Pre-index content validation, suspicious pattern scanning |
| Tools (order/refund/ticket APIs) | Abuse, unauthorized calls, injection | Allow-list, JSON schema validation, per-tool permission, timeout, audit log |
| Admin endpoints | Privilege escalation | RBAC middleware on every route, role checked server-side |
| API availability | Abuse / DoS | Rate limiting middleware (per-IP and per-user) |

## 2. Prompt Injection Detection (Layered)

1. **Heuristic pattern layer**: regex/keyword detection for known patterns — "ignore previous instructions", "reveal your system prompt", "you are now in developer mode", role-play override attempts, tool-manipulation phrases ("call get_order with admin=true"), delimiter/escape sequences (`"""`, `<|...|>`) used to break out of context.
2. **Structural layer**: detects anomalies such as embedded fake conversation turns, attempts to redefine the assistant's role, or instructions embedded inside retrieved document content (as opposed to the user's own message).
3. **LLM-based classifier layer** (optional, cost-aware): a lightweight classification call asking the model to rate injection likelihood, used only when heuristic score is borderline, to reduce false positives/negatives from keyword matching alone.

Each layer produces a score; scores are combined into a single `injection_risk` (0–1). Above a configurable threshold, the message is blocked (not sent to the main LLM) and a `security_events` row is logged with the evidence.

## 3. PII Detection

Detected categories: email addresses, phone numbers, credit-card-like numbers (Luhn-validated), SSN-like patterns, generic API-key/secret patterns (`sk-...`, `AKIA...`, long high-entropy tokens), and common credential phrases ("my password is").

Policy: 
- On **input**: PII is masked before being included in LLM prompts/logs (never before storage of the raw message itself in the DB, which is access-controlled) — configurable to block entirely for certain categories (e.g., credentials, API keys).
- On **output**: any PII-shaped content the model generates is masked before it reaches the client, and logged as a security event (possible leakage from context).

## 4. RAG / Document Security

Before a document chunk is embedded and indexed:
- Scan for hidden/invisible instructions (e.g., zero-width characters, HTML comments containing directives, "SYSTEM:" prefixes).
- Reuse the prompt-injection heuristic layer against document content.
- Flag suspicious metadata (mismatched declared vs. detected file type, executable content).
Documents failing validation are marked `FAILED` with a reported reason; admins may override after review.

## 5. Output Guardrails

Before returning a generated answer:
- Re-run PII detection on the output.
- Check for leaked secrets/API-key-shaped strings.
- Verify the answer does not contain unsupported factual claims beyond retrieved context when RAG grounding is required (basic overlap/citation check — not a full factuality model).

## 6. Tool Security

- Tools are defined in a static Python allow-list (`backend/app/agents/tools/`); the LLM can only select by name from this list — no dynamic code generation/execution.
- Every tool call is validated against a Pydantic input schema before execution.
- Every tool has a per-call timeout and a per-conversation/per-minute rate limit.
- All tool invocations (input, output, duration, success/failure) are written to `tool_calls` and `audit_logs`.

## 7. Authentication & Authorization

- Passwords hashed with bcrypt (via `passlib`).
- JWT access tokens (short-lived, e.g. 15–30 min) + refresh tokens (longer-lived, stored hashed).
- Role-based dependency injection in FastAPI (`require_role("admin")`) enforced on every admin/agent route.

## 8. Logging & Data Handling

- Structured JSON logs include request/conversation/user IDs, latencies, token usage, retrieval and tool metadata, confidence, and security events.
- Logs never include: plaintext passwords, JWTs, OpenAI API keys, or raw unmasked PII.

## 9. Rate Limiting

- Global per-IP limiter on auth endpoints (mitigate brute force).
- Per-user limiter on `/chat` to prevent cost abuse.
- Implemented via middleware using an in-memory/Redis-ready token bucket (configurable backend).

## 10. Known Limitations

- Prompt-injection and PII detection are heuristic-based; they reduce but do not eliminate risk. No claim of formal guarantee is made.
- Output factuality checking is a lightweight grounding/overlap heuristic, not a full hallucination-detection model.
