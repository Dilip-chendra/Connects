# Connects Architecture Note: Foundations & Execution Engine

This document provides a concise technical explanation of the security, tenant isolation, credential encryption, planning engine, execution engine, and workflow durability patterns implemented in Connects.

---

## 1. Multi-Tenant Isolation Architecture

Connects enforces a **defense-in-depth, deny-by-default** isolation model:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Authentication Layer (JWT with Cryptographic Signature)   │
│    - Extracts user identity and verified tenant memberships │
├─────────────────────────────────────────────────────────────┤
│ 2. FastAPI Tenant Context Dependency                         │
│    - Verifies user's active membership in target tenant     │
│    - Rejects unauthorized cross-tenant requests with 403    │
│    - Binds TenantContext to async context variable          │
├─────────────────────────────────────────────────────────────┤
│ 3. Database Layer (Transaction-Local RLS Binding)            │
│    - Emits: SET LOCAL app.current_tenant_id = :tenant_id    │
│    - Transaction-local: Cleared automatically on commit/pool│
│    - Explicit tenant_id filtering on all ORM queries        │
├─────────────────────────────────────────────────────────────┤
│ 4. PostgreSQL Row-Level Security (RLS) Policies              │
│    - Kernel-level enforcement on tenant-owned tables        │
│    - Prevents data leakage even under raw SQL regressions   │
└─────────────────────────────────────────────────────────────┘
```

### Key Principles
- **No Untrusted Header Trust**: The active tenant is NEVER derived from an unverified `X-Tenant-ID` header alone. The user's JWT claims are validated against tenant memberships.
- **Pooled Session Isolation**: Connection pooling can leak state if global session settings are used. Connects utilizes `SET LOCAL app.current_tenant_id`, which is bound strictly to the active transaction and resets when the transaction concludes.
- **Safe 404/403 Responses**: When a tenant queries an ID belonging to another tenant, the API responds with `404 Not Found in this tenant` or `403 Forbidden`, preventing enumeration of other tenants' existence.

---

## 2. CredentialVault & Envelope Encryption

Connects manages privileged third-party access credentials (GitHub Personal Access Tokens, Vercel API Tokens, Stripe Secret Keys) through an authenticated envelope encryption vault.

### Cryptographic Profile
- **Algorithm**: `AES-256-GCM` (Galois/Counter Mode).
- **Nonce Generation**: 96-bit (12-byte) cryptographically secure pseudorandom nonces generated via `os.urandom(12)` on every single encryption call. Nonce reuse is mathematically prevented.
- **Authenticated Additional Data (AAD)**: 
  Every secret is cryptographically bound to its tenant and connector identity:
  `AAD = "tenant:{tenant_id}|connector:{connector_id}|ver:{key_version}"`
  If an attacker copies encrypted ciphertext from Tenant A to Tenant B, or from GitHub to Stripe, decryption immediately fails closed with `DecryptionError`.
- **Key Versioning & Rotation**: Master keys are designated with versions (`v1`, `v2`). The `reencrypt` method allows zero-downtime key rotation without exposing plaintext credentials.
- **Secret Redaction**: Structured logging formats intercept and redact authorization headers, passwords, and tokens before writing to stdout.

---

## 3. Workflow State Durability & Crash Recovery

Workflow executions and task transitions are modeled as deterministic state machines:

```
  [PLANNED] ──► [READY] ──► [RUNNING] ──┬──► [AWAITING_APPROVAL] ──► [RUNNING]
                                        ├──► [VERIFYING] ──► [COMPLETED]
                                        ├──► [FAILED] ──► [READY] (retry)
                                        │             └──► [BLOCKED] (exhausted)
                                        └──► [MANUAL_HANDOFF] ──► [VERIFYING]
```

### Durability Principles
- **PostgreSQL as Source of Truth**: Task state, inputs, outputs, and verification records are persisted in PostgreSQL. Redis is used strictly as a lightweight transport for job dispatch, not durable state storage.
- **Idempotency Keys**: Tasks enforce a database-level unique constraint on `(workflow_execution_id, idempotency_key)`. Retried operations do not duplicate execution records.
- **Error Classification**:
  - `TRANSIENT` (e.g., HTTP 429, socket timeout): Retries with exponential backoff up to `max_retries`.
  - `FATAL` (e.g., HTTP 401, validation error): Transitions immediately to `BLOCKED`.
  - `MANUAL_REQUIRED`: Transitions to `MANUAL_HANDOFF` for guided founder completion.
- **DAG Cycle Prevention**: Graph dependencies are verified before scheduling using Depth-First Search 3-color cycle detection. Circular dependencies are rejected immediately.

---

## 4. Goal Decomposition & Planning Engine

Connects separates planning from execution to provide predictability, transparency, and safety:

```
[ Natural Language Goal ] 
          │
          ▼
[ Rule-Based Plan Generator (rule_based_planner_v1) ]
          │
          ├── Task 1: validate_project_metadata   (Internal Capability)
          ├── Task 2: validate_plan_structure     (Internal Capability)
          ├── Task 3: check_required_config       (Internal Capability, Approval Gate)
          ├── Task 4: create_context_record       (Internal Capability)
          ├── Task 5: generate_launch_checklist   (Internal Capability)
          ├── Task 6: setup_code_repository       (Manual Handoff: External git:init)
          ├── Task 7: configure_deployment_pipeline (Manual Handoff: External deploy:ci)
          └── Task 8: verify_internal_record      (Internal Capability)
          │
          ▼
[ DFS Cycle Validation: DependencyGraphValidator ]
          │
          ▼
[ Draft Plan Snapshot ] ──► [ Founder Review & Approval ] ──► [ Immutable Execution Plan ]
```

### Key Planning Guarantees:
- **Transparent Attribution**: Every plan explicitly records its planning source engine (`rule_based_planner_v1` or future LLM engines) and timestamp.
- **Explicit Capability Tagging**: Every task specifies whether it is supported internally by Connects or requires an external integration capability (`repo:write`, `deploy:trigger`, `payment:mutate`).
- **No Simulation of External Services**: When external connectors are not active, the plan explicitly marks the task as requiring manual founder handoff, accompanied by a structured explanation.
- **Approval Gate Flagging**: Tasks involving high risks, infrastructure costs, or security implications require explicit founder approval prior to running.

---

## 5. Execution Engine & Safety Architecture

The Connects `ExecutionEngine` operates as a transactional, multi-tenant workflow dispatch engine:

1. **Wave Dispatch**: Iteratively identifies all tasks whose prerequisites are completely satisfied (`status == 'completed'`).
2. **Approval Gate Interception**: Tasks with `requires_approval = True` automatically pause into `awaiting_approval`, generating an `approval_requests` entry with an impact assessment. Stepping halts until a founder approves or rejects the action.
3. **Manual Handoff Handling**: Tasks missing internal connectors transition to `manual_handoff`, pausing execution until the founder completes external setup and submits the completion signal.
4. **Internal Capability Execution**: Real internal tasks execute concrete domain handlers (`validate_project_metadata`, `create_context_record`, `check_required_config`, `generate_launch_checklist`, `verify_internal_record`), persisting outputs, execution attempts, and verification records in PostgreSQL.
5. **Auditing**: Every workspace mutation, plan review, approval decision, and workflow step appends an immutable record to `audit_logs` scoped to the active tenant.

---

## 6. GitHub Integration & Repository Intelligence Architecture

Connects Phase 2 introduces secure, commit-pinned repository intelligence for existing codebases.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        GitHub App Security Model                       │
│                                                                        │
│  Connects Backend                                         GitHub API   │
│  ┌───────────────────────┐                               ┌───────────┐ │
│  │ App ID + RSA PEM Key  │───[RS256 JWT (exp: 10m)]─────►│ /app      │ │
│  └───────────────────────┘                               └─────┬─────┘ │
│              │                                                 │       │
│  ┌───────────▼───────────┐       Scoped Installation Token     │       │
│  │ Installation Token    │◄──────(contents:read, metadata:read)┘       │
│  │ In-Memory Cache (TTL) │                                             │
│  └───────────────────────┘                                             │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  Commit-Pinned Repository Inspection                   │
│                                                                        │
│  1. Resolve default branch & Pin exact HEAD Commit SHA                 │
│  2. Fetch recursive git tree (100,000 file safety limit)               │
│  3. Detect tree truncation & record audit warning if truncated         │
│  4. Sensitive File Exclusion Filter:                                   │
│     - .env, .env.local, .env.production, id_rsa, *.pem, *.key          │
│     - Contents are NEVER fetched or retained                           │
│  5. Bounded text inspection (max 256 KB per file)                      │
│  6. Regex Secret Redaction Filter:                                     │
│     - AWS, Stripe, GitHub, Private Keys, generic secrets               │
│     - Replaced with [REDACTED:secret_type:first4...last2]              │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│             Deterministic Analysis & Evidence Generation               │
│                                                                        │
│  - Frameworks: Next.js, React, FastAPI, Express, Django                │
│  - Database: Alembic, Prisma, Drizzle, SQLAlchemy                      │
│  - Containerization & CI/CD: Dockerfile, compose.yml, GitHub Actions   │
│  - Launch Gaps: Missing tests, missing .env.example, exposed secrets   │
│  - Honest Verification: Test files marked UNVERIFIED (never passed)    │
│  - Launch Readiness Score: 0-100 calculated from weighted findings     │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
┌─────────────────────────────────┐   ┌──────────────────────────────────┐
│  Business Context Graph Sync    │   │ Launch Plan Synthesis            │
│                                 │   │                                  │
│  - Nodes: repository, tech, req │   │  - Engine:                       │
│  - Edges: SUPPORTS_GOAL,        │   │    repo_intelligence_planner_v1  │
│           IMPLEMENTS, REQUIRES  │   │  - Cycle-validated DAG           │
│  - Project-scoped state         │   │  - Founders review & approve     │
└─────────────────────────────────┘   └──────────────────────────────────┘
```

### Key Security & Architecture Guarantees:
- **Strict Read-Only Enforcement**: GitHub App tokens request permissions strictly restricted to `contents: read` and `metadata: read`. Connects cannot modify repositories, create commits, open pull requests, or alter permissions.
- **Zero-Simulation Configuration Transparency**: The platform inspects `is_github_configured()`. If GitHub App credentials (`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`) are missing, the UI renders an actionable setup guide with the required callback URL and permissions rather than presenting mock repositories or simulated connections.
- **Commit SHA Pinning**: Every scan is bound to an immutable Git commit SHA. Findings, architecture detections, and launch readiness scores reference the exact snapshot of code analyzed.
- **Sensitive File Boundaries & Redaction**: Connects enforces a deny-list preventing inspection of environment secret files or cryptographic private keys. Any sensitive tokens detected in tracked repository files (e.g., test mocks) are masked before persistence in `repository_findings.evidence`.
- **Honest Verification Tracking**: Finding test files or CI scripts records an `UNVERIFIED` state. Connects explicitly differentiates between code structure presence and actual passing execution.
- **Multi-Tenant Kernel-Level RLS**: All four Phase 2 tables (`github_installations`, `connected_repositories`, `repository_scans`, `repository_findings`) have PostgreSQL Row-Level Security enabled and forced (`FORCE ROW LEVEL SECURITY`), with tenant isolation strictly verified against live database catalogs.
