# Connects — AI-Powered Startup Orchestration Platform

> **One Goal. Connected Tools. Real Outcomes.**

Connects is an AI-powered startup operating system and application orchestration platform that turns software prototypes into monetized, production-grade businesses by coordinating existing AI builders, repositories, hosting, payment gateways, and analytics.

---

## Phase 1 Capabilities

Connects Phase 1 implements a functional end-to-end execution layer:

1. **Authentication & Multi-Tenant Workspaces**:
   - Secure user registration and login with bcrypt password hashing and dual-mode token delivery (HttpOnly cookie and Authorization Bearer header).
   - Atomic workspace creation provisioning a PostgreSQL `tenant`, owner `membership`, and immutable `audit_log` entry.
   - Strict tenant isolation enforced at the database layer via transaction-local `SET LOCAL app.current_tenant_id` and PostgreSQL Row-Level Security (RLS) policies.

2. **Project Management & Business Context Graph**:
   - Project lifecycle: creation, primary goal definition, categorization, target launch date, and non-destructive archival.
   - Directed context graph modeling nodes (`goal`, `requirement`, `constraint`, `decision`) and typed relationships (`REQUIRES`, `DEPENDS_ON`, `IMPLEMENTS`, `VERIFIES`).

3. **Goal Decomposition & Planning Engine**:
   - Rule-based deterministic planning engine (`rule_based_planner_v1`) generating structured execution plans directly from business goals.
   - Transparent planning engine attribution, explicit capability requirements, risk classifications, and human approval gates.
   - Depth-First Search (DFS) 3-color DAG cycle validation ensuring zero circular task dependencies.
   - Plan approval and rejection lifecycle producing immutable execution snapshots.

4. **Durable Execution Engine**:
   - PostgreSQL-backed execution engine with wave dispatch, transaction isolation, and task idempotency.
   - Genuine internal capability handlers executing real validation and record generation.
   - Bounded exponential retries for transient faults and explicit classification for fatal errors.
   - Founder approval gates (`awaiting_approval`) pausing critical tasks until human authorization.
   - Manual handoff transitions (`manual_handoff`) for unsupported external integrations (e.g. GitHub repos, Stripe keys, Vercel deployments), preventing fake or simulated external execution.

5. **Production Next.js 14 Web Application**:
   - Modern, dark-themed responsive UI built with Next.js App Router, TypeScript, and Tailwind CSS.
   - Screens: Sign In, Sign Up, Workspace Switcher, Workspace Creation, Project Management, Project Detail with Context Graph, Plan Review & Approval with DAG visualization, Workflow Execution with live task stepping and payload inspection drawer, Workspace Approval Queue, and Activity Audit Trail.

6. **Phase 2: GitHub Integration & Repository Intelligence**:
   - Production-conscious GitHub App integration with strictly read-only permissions (`metadata: read`, `contents: read`).
   - Server-side RS256 JWT signing, installation access token generation, and caching.
   - Project repository linking with immutable GitHub repository IDs and connection lifecycle management (`connected`, `disconnected`).
   - Deterministic, commit-pinned `RepositoryInspector`:
     - Excludes sensitive files (`.env`, `*.pem`, `id_rsa`) from ordinary content fetches.
     - Scans for committed secret patterns (AWS, Stripe, GitHub tokens) and strictly redacts all evidence excerpts.
     - Detects languages, web frameworks (Next.js, React, FastAPI, Express), database tools (Alembic, Prisma), deployment configs (Dockerfile, Docker Compose, `.env.example`), and testing infrastructure.
     - Enforces honest verification statuses (`OBSERVED`, `NEEDS_REVIEW`, `NOT_FOUND_IN_SCANNED_SCOPE`, `UNVERIFIED`)—finding test files does NOT claim tests pass without execution.
     - Treats repository files as untrusted data, immune to prompt-injection override attempts.
   - Context Graph & Planning Synthesis:
     - Automatically synchronizes repository nodes, detected technologies, and launch gaps into the Business Context Graph.
     - Synthesizes findings into reviewable execution plans (`repo_intelligence_planner_v1`) ready for founder approval.
   - Database isolation:
     - 4 new tables (`github_installations`, `connected_repositories`, `repository_scans`, `repository_findings`) with `FORCE ROW LEVEL SECURITY`.

---

## Repository Structure

```
connects/
├── apps/
│   └── web/                # Next.js 14+ App Router, Tailwind CSS, Dark Theme
├── packages/
│   └── shared/             # Shared TypeScript schemas, enums, and types
├── services/
│   └── api/                # Python 3.11+, FastAPI, SQLAlchemy 2.0 Async, Alembic
│       ├── migrations/     # Alembic database migrations & RLS policies
│       ├── src/
│       │   ├── core/       # Settings, Logging, CredentialVault, Auth
│       │   ├── database/   # Database engine, models, session manager
│       │   ├── domain/     # Workflow state machines & DAG validator
│       │   └── api/        # REST routes (health, tenants, projects, workflows)
│       └── tests/          # Automated test suite (vault, tenant isolation, DAGs)
├── docker-compose.yml      # Local PostgreSQL 16 & Redis 7 services
├── .env.example            # Environment variables template
└── ARCHITECTURE.md         # Tenant isolation & security architecture notes
```

---

## Quickstart & Local Setup

### 1. Prerequisites
- **Python**: 3.11+
- **Node.js**: 18.18+ (Node 20+ recommended) & npm
- **Docker & Docker Compose**: For local PostgreSQL 16 and Redis 7 (or local PostgreSQL service)
- **uv** (recommended for Python package management): `pip install uv`

### 2. Environment Configuration
Copy `.env.example` to `.env` in the repository root:
```bash
cp .env.example .env
```

Generate a secure 32-byte base64 encryption key for `VAULT_MASTER_KEY_V1`:
```bash
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```
Paste the generated key into your `.env` file under `VAULT_MASTER_KEY_V1`.

#### GitHub App Setup (Phase 2):
1. In your GitHub account, navigate to **Settings > Developer Settings > GitHub Apps > New GitHub App**.
2. **App Name**: e.g., `connects-app-dev` (must be globally unique).
3. **Homepage URL**: `http://localhost:3000`
4. **Setup URL (optional)**: `http://localhost:3000/workspaces`
5. **Callback URL**: `http://localhost:8000/workspaces/{tenant_id}/github/install-callback`
6. **Webhook**: Uncheck Active (webhooks not required for Phase 2 read-only analysis).
7. **Repository Permissions**:
   - `Contents`: Read-only
   - `Metadata`: Read-only
8. Click **Create GitHub App**.
9. Generate and download an **RSA Private Key** (.pem).
10. Copy `App ID`, `Client ID`, and paste the PEM key into `.env` under:
    - `GITHUB_APP_ID=123456`
    - `GITHUB_APP_NAME=connects-app-dev`
    - `GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n..."`


### 3. Start Database & Redis Services
Start PostgreSQL 16 and Redis containers:
```bash
docker compose up -d
```
Verify containers are healthy:
```bash
docker compose ps
```

### 4. Database Migrations
Apply the initial schema migration containing all 13 core tables and RLS policies:
```bash
cd services/api
alembic upgrade head
```

To rollback a migration:
```bash
alembic downgrade -1
```

### 5. Run the Backend API Service
Using `uv`:
```bash
cd services/api
uv run uvicorn src.main:app --reload --port 8000
```
Or with standard virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8000
```

Verify the API is running:
- Health check: `http://localhost:8000/health/ready`
- OpenAPI docs: `http://localhost:8000/docs`

### 6. Run the Frontend Web Application
```bash
npm install
npm run dev:web
```
Open `http://localhost:3000` in your browser.

---

## Running Automated Tests

Run the full backend test suite covering AES-256-GCM vault security, multi-tenant isolation, DAG cycle validation, and schema integrity:

```bash
cd services/api
uv run pytest -v
```

Or using active virtual environment:
```bash
pytest -v
```

---

## Troubleshooting

- **Database connection refused**: Ensure PostgreSQL is running on port 5432 (`docker compose ps`). Check your credentials in `.env`.
- **Vault initialization error**: `VAULT_MASTER_KEY_V1` must be exactly 32 bytes base64-encoded. Ensure you generated it using the command in step 2.
- **Cross-tenant 403 Forbidden**: Tenant isolation strictly requires that the authenticated user possesses an authorized membership record for the requested tenant.
