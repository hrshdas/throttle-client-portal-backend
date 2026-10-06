# Throttle Client Portal Backend

[![Throttle Backend CI](https://github.com/throttle-agency/throttle-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/throttle-agency/throttle-backend/actions/workflows/ci.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?style=flat&logo=python)](https://www.python.org)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0.35-red.svg?style=flat)](https://www.sqlalchemy.org)
[![License](https://img.shields.io/badge/License-Proprietary-blue.svg)](#license)

Production-ready asynchronous Python backend powering the Throttle Client Portal. Built with FastAPI, SQLAlchemy 2.0 (asyncio), PostgreSQL, and OAuth2 JWT authentication. Designed for agency-to-client operations featuring multi-tenant organization isolation, client approval workflows, real-time messaging, activity auditing, and native Meta Marketing API integration.

---

## Architecture

```mermaid
flowchart TD
    subgraph Client Layer
        Web["Web Portal Client"]
        Mobile["Mobile Application"]
    end

    subgraph API Layer ["Backend API (FastAPI)"]
        Router["APIRouter (/api/v1)"]
        AuthMiddleware["JWT Authentication & RBAC Middleware"]
    end

    subgraph Application Services
        AuthService["Auth & Session Management"]
        ProjectService["Projects & Tasks Engine"]
        ChatService["Real-Time Messaging Service"]
        AnalyticsService["Analytics & Reporting Engine"]
        MetaService["Meta Integration & Sync Engine"]
    end

    subgraph Database Layer
        Postgres[(PostgreSQL / AsyncPG)]
        Crypto["Fernet Token Encryption"]
    end

    subgraph External Integrations
        MetaAPI["Meta Graph API (v26.0)"]
    end

    Web -->|HTTP / REST API| Router
    Mobile -->|HTTP / REST API| Router
    Router --> AuthMiddleware
    AuthMiddleware --> AuthService
    AuthMiddleware --> ProjectService
    AuthMiddleware --> ChatService
    AuthMiddleware --> AnalyticsService
    AuthMiddleware --> MetaService

    AuthService --> Postgres
    ProjectService --> Postgres
    ChatService --> Postgres
    AnalyticsService --> Postgres
    MetaService --> Crypto
    Crypto --> Postgres
    MetaService -->|OAuth 2.0 / Marketing API| MetaAPI
```

For detailed architectural diagrams and design decisions, view [docs/architecture.md](docs/architecture.md).

---

## Features

- **Authentication & Security**: OAuth2 JWT Bearer tokens with 30-minute access token expiry, 7-day refresh token rotation, and password hashing via `bcrypt`.
- **Organization-Level Multi-Tenancy**: Logical data isolation scoping all project, task, chat, and analytics queries strictly to `current_user.organization_id`.
- **Role-Based Authorization (RBAC)**: Fine-grained access control across 5 system roles (`THROTTLE_ADMIN`, `THROTTLE_STAFF`, `CLIENT_ADMIN`, `CLIENT_STAFF`, `CLIENT_VIEWER`).
- **Project & Task Workflow Engine**: Full lifecycle project tracking with milestones, task status transitions, task priorities, and discussion threads.
- **Client Approval System**: Dedicated review workflow endpoints allowing client stakeholders to approve tasks or request revisions with feedback notes.
- **Real-Time Client-Agency Messaging**: Multi-thread conversation messaging system with unread tracking and participant scoping.
- **Activity & Notification Engine**: Comprehensive activity audit logging for tenant actions and user notification management.
- **Analytics & Marketing Performance Engine**: Aggregated advertising metrics processing spend, impressions, clicks, leads, purchases, revenue, CPM, CTR, CPC, CPL, and ROAS with zero-division protection.
- **Meta Marketing API Integration**: Native OAuth 2.0 connection flow, Fernet token encryption at rest, ad account selection, historical sync, on-demand resync, and simulated demo mode fallback.

---

## Tech Stack

- **Framework**: FastAPI 0.115.0
- **Language**: Python 3.12+
- **ASGI Server**: Uvicorn 0.30.6
- **Database ORM**: SQLAlchemy 2.0.35 (Asyncio)
- **Database Drivers**: `asyncpg` 0.29.0 (PostgreSQL), `aiosqlite` 0.20.0 (SQLite / Testing)
- **Database Migrations**: Alembic 1.13.3
- **Data Validation & Settings**: Pydantic 2.9.2, Pydantic-Settings 2.5.2
- **Authentication**: `python-jose` 3.3.0 (JWT), `passlib` 1.7.4 & `bcrypt`
- **Token Encryption**: `cryptography` 41.0.7 (Fernet Symmetric Encryption)
- **HTTP Client**: HTTPX 0.27.2 (Async HTTP client for Meta API)
- **Testing Framework**: Pytest 8.3.3, `pytest-asyncio` 0.24.0, `pytest-httpx` 0.30.0

---

## Project Structure

```
throttle-backend/
├── alembic/                # Alembic database migration environment and scripts
├── app/
│   ├── api/                # API router modules organized by version
│   │   └── v1/             # API v1 endpoints (auth, admin, client, projects, tasks, chat, etc.)
│   ├── core/               # Core application setup (config, security, DB engine, dependencies)
│   ├── models/             # Declarative SQLAlchemy ORM models
│   ├── schemas/            # Pydantic request and response schemas
│   ├── services/           # Business logic, analytics calculations, Meta client & sync
│   └── main.py             # FastAPI application initialization & middleware setup
├── docs/                   # Developer & architecture documentation suite
│   ├── api.md
│   ├── architecture.md
│   ├── authentication.md
│   ├── database.md
│   ├── deployment.md
│   ├── integrations.md
│   └── multi-tenancy.md
├── scripts/                # Database initialization, seeding, and scheduled sync utilities
├── tests/                  # Automated test suite (unit, integration, tenant isolation)
├── .env.example            # Environment variables template with placeholders
├── .gitignore              # Repository exclusion rules
├── pytest.ini              # Pytest execution configuration
├── requirements.txt        # Python dependency manifest
└── alembic.ini             # Alembic migration configuration
```

---

## Getting Started

### Prerequisites
- Python 3.12+
- PostgreSQL 14+ (or SQLite for local testing)

### Installation Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/throttle-agency/throttle-backend.git
   cd throttle-backend
   ```

2. **Create and activate a Python virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```

5. **Initialize the database & seed initial data**:
   ```bash
   python3 scripts/init_db.py
   python3 scripts/seed_db.py
   ```

6. **Start the local development server**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

7. **Verify API health**:
   ```bash
   curl http://localhost:8000/health
   ```

---

## Environment Variables

All backend configuration parameters are managed via environment variables defined in [.env.example](.env.example):

| Variable | Required | Description | Default / Example |
|---|---|---|---|
| `DATABASE_URL` | Yes | Asynchronous database connection string | `postgresql+asyncpg://throttle:throttle123@localhost:5432/throttle` |
| `SECRET_KEY` | Yes | Cryptographic secret for signing JWT tokens | `dev-secret-key-change-in-production...` |
| `ALGORITHM` | Yes | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Yes | JWT access token validity period | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Yes | JWT refresh token validity period | `7` |
| `ENVIRONMENT` | Yes | Execution environment mode | `development` |
| `FRONTEND_URL` | Yes | Frontend application origin URL | `http://localhost:8080` |
| `META_APP_ID` | Optional | Meta App Dashboard App ID | `placeholder_meta_app_id` |
| `META_APP_SECRET` | Optional | Meta App Dashboard Secret | `placeholder_meta_app_secret` |
| `META_API_VERSION` | Yes | Meta Graph API release version | `v26.0` |
| `META_REDIRECT_URI` | Yes | Valid OAuth Redirect URI | `http://localhost:8000/api/v1/meta/connect/callback` |
| `META_ENCRYPTION_KEY` | Optional | Fernet base64 key for encrypting stored access tokens | Empty (derives key from `SECRET_KEY`) |

---

## Database Setup

### Direct Metadata Initialization
Create tables directly using SQLAlchemy ORM schemas:
```bash
python3 scripts/init_db.py
```

### Seeding Demo Data
Populate demo agency and client organization accounts (`Blueforce`, `Acme`), tasks, projects, chat history, and mock Meta ad insights:
```bash
python3 scripts/seed_db.py
```

### Alembic Migrations
Generate or apply database migrations:
```bash
# Generate migration revision
alembic revision --autogenerate -m "add_new_feature"

# Apply pending migrations
alembic upgrade head
```

For complete database schema and entity relationship diagrams, see [docs/database.md](docs/database.md).

---

## API & Documentation

When the application is running, interactive API documentation is generated automatically:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc UI**: `http://localhost:8000/redoc`
- **OpenAPI JSON Schema**: `http://localhost:8000/openapi.json`

For endpoint specifications and payload examples, see [docs/api.md](docs/api.md).

---

## Testing

Run the automated test suite with `pytest`:

```bash
pytest -v
```

### Test Suite Structure
- `tests/test_analytics_calculations.py`: Verifies KPI formulas (ROAS, CPM, CTR, CPL), zero-division safeguards, and range parameter parsing.
- `tests/test_meta_oauth.py`: Tests CSRF state token generation, single-use validation, TTL expiration, and OAuth callback handling.
- `tests/test_meta_sync.py`: Verifies Meta campaign upserts, connection state transitions, and sync idempotency.
- `tests/test_tenant_isolation.py`: Verifies strict multi-tenant isolation across project and messaging resources.
- `tests/test_meta_tenant_isolation.py`: Verifies tenant isolation across Meta connections, campaigns, overview analytics, and timeseries data.
- `tests/test_real_interaction_flow.py`: End-to-end integration test simulating multi-role agency-client workflows.

---

## Security

- **Authentication**: JWT token validation on protected endpoints via `app/core/dependencies.py`.
- **Role-Based Authorization**: Scoped endpoint access enforcing strict role checks (`THROTTLE_ADMIN`, `CLIENT_ADMIN`, etc.).
- **Tenant Isolation**: Database queries enforce tenant boundaries matching the verified JWT `organization_id`.
- **Secret Management**: Passwords hashed with `bcrypt`. Environment variables decoupled via `.env` and `.env.example`.
- **External Integration Security**: Meta access tokens encrypted at rest using Fernet symmetric key encryption. OAuth flow protected against CSRF via single-use state tokens.

For security implementation details, review [docs/security.md](docs/authentication.md) and [docs/multi-tenancy.md](docs/multi-tenancy.md).

---

## Deployment Architecture

The backend is built for cloud deployment with Uvicorn behind Nginx or AWS Application Load Balancers (ALB), connecting to PostgreSQL.

- **Current Status**: **Development & Staging Ready**.
- **Deployment Details**: View [docs/deployment.md](docs/deployment.md) for production checklists and ASGI deployment commands.

---

## Roadmap

### Implemented Functionality
- [x] Multi-tenant Organization Architecture & Schema
- [x] JWT Authentication, Refresh Rotation, and Invitation System
- [x] Role-Based Access Control (RBAC) across 5 Roles
- [x] Project, Task, and Milestone Management Engine
- [x] Client Task Approval & Revision Request Workflow
- [x] Multi-tenant Messaging & Chat Threads
- [x] Activity Audit Log & User Notifications
- [x] Analytics Processing Engine (11 KPI Metrics)
- [x] Meta Marketing API v26.0 Integration & Fernet Token Encryption
- [x] Demo Mode Connection Fallback for Development

### Planned Functionality
- [ ] Celery / Redis background worker queue for enterprise-scale batch syncing
- [ ] Webhook listener for real-time Meta ad account change notifications
- [ ] Multi-platform integrations (Google Ads, TikTok Ads, LinkedIn Ads)
- [ ] Exportable PDF client performance reports

---

## License

Proprietary — All Rights Reserved. Throttle Agency Inc.
# throttle-client-portal-backend
