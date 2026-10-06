# Throttle Database Specification & Schema

This document details the database architecture, table schemas, entity relationships, migrations system, and data seeding routines.

---

## 1. Overview & Engine Stack

- **ORM**: SQLAlchemy 2.0 (Declarative Mapping)
- **Drivers**: `asyncpg` (PostgreSQL - primary), `aiosqlite` (SQLite - testing/local fallback)
- **Migrations**: Alembic 1.13.3 (`alembic.ini`, `alembic/env.py`)
- **Naming Conventions**: Snake_case table names and explicit Foreign Key relationships

---

## 2. Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ USERS : "has members"
    ORGANIZATIONS ||--o{ PROJECTS : "owns"
    ORGANIZATIONS ||--o{ CONVERSATIONS : "owns"
    ORGANIZATIONS ||--o{ META_CONNECTIONS : "connects"
    ORGANIZATIONS ||--o{ META_CAMPAIGNS : "contains"
    ORGANIZATIONS ||--o{ INVITATIONS : "sends"

    USERS ||--o{ REFRESH_TOKENS : "issues"
    USERS ||--o{ TASK_COMMENTS : "authors"
    USERS ||--o{ MESSAGES : "sends"
    USERS ||--o{ ACTIVITIES : "performs"
    USERS ||--o{ NOTIFICATIONS : "receives"

    PROJECTS ||--o{ PROJECT_MILESTONES : "contains"
    PROJECTS ||--o{ TASKS : "contains"

    TASKS ||--o{ TASK_COMMENTS : "has comments"
    TASKS ||--o{ TASK_APPROVAL_HISTORY : "tracks approvals"

    CONVERSATIONS ||--o{ CONVERSATION_PARTICIPANTS : "includes"
    CONVERSATIONS ||--o{ MESSAGES : "contains"

    META_CONNECTIONS ||--o{ META_CAMPAIGNS : "manages"
    META_CAMPAIGNS ||--o{ META_AD_SETS : "contains"
    META_AD_SETS ||--o{ META_ADS : "contains"
    META_CAMPAIGNS ||--o{ META_DAILY_INSIGHTS : "tracks metrics"

    ORGANIZATIONS {
        string id PK
        string name
        string slug UK
        string logo_url
        datetime created_at
    }

    USERS {
        string id PK
        string organization_id FK
        string email UK
        string hashed_password
        string name
        string role
        boolean is_active
        datetime created_at
    }

    PROJECTS {
        string id PK
        string organization_id FK
        string name
        string description
        string status
        float budget
        date start_date
        date target_end_date
    }

    TASKS {
        string id PK
        string project_id FK
        string organization_id FK
        string title
        string description
        string status
        string priority
        string assignee_id FK
    }

    META_CONNECTIONS {
        string id PK
        string organization_id FK
        string meta_user_id
        string ad_account_id
        string encrypted_access_token
        string status
        datetime last_synced_at
    }
```

---

## 3. Key Model Definitions

### 3.1 Organization & User Management
- **`organizations`**: Multi-tenant isolation anchor (`id`, `name`, `slug`, `logo_url`).
- **`users`**: System user accounts (`id`, `organization_id`, `email`, `hashed_password`, `name`, `role`, `is_active`).
- **`refresh_tokens`**: Revocable refresh token store (`id`, `user_id`, `token_hash`, `expires_at`, `revoked_at`).
- **`invitations`**: Pending user organization invites (`id`, `organization_id`, `email`, `role`, `token`, `status`).

### 3.2 Projects & Task Management
- **`projects`**: Client projects (`id`, `organization_id`, `name`, `description`, `status`, `budget`, `start_date`, `target_end_date`).
- **`project_milestones`**: Key project progress targets (`id`, `project_id`, `title`, `status`, `due_date`).
- **`tasks`**: Work items (`id`, `project_id`, `organization_id`, `title`, `description`, `status`, `priority`, `assignee_id`).
- **`task_comments`**: Discussion on tasks (`id`, `task_id`, `user_id`, `comment_text`).
- **`task_approval_history`**: Audit trail for client task approvals and change requests (`id`, `task_id`, `status_from`, `status_to`, `action_by_user_id`, `notes`).

### 3.3 Messaging & Activities
- **`conversations`**: Chat thread metadata (`id`, `organization_id`, `title`, `project_id`).
- **`conversation_participants`**: Thread participants link (`id`, `conversation_id`, `user_id`, `last_read_at`).
- **`messages`**: Chat messages (`id`, `conversation_id`, `sender_id`, `content`).
- **`activities`**: Audit log events (`id`, `organization_id`, `user_id`, `action_type`, `entity_type`, `entity_id`, `description`).
- **`notifications`**: User alert notifications (`id`, `user_id`, `title`, `message`, `is_read`, `notification_type`).

### 3.4 Meta Marketing API Entities
- **`meta_connections`**: Meta OAuth ad connection details (`id`, `organization_id`, `meta_user_id`, `ad_account_id`, `encrypted_access_token`, `status`, `last_synced_at`).
- **`meta_campaigns`**: Meta ad campaigns (`id`, `organization_id`, `ad_account_id`, `meta_campaign_id`, `name`, `status`, `objective`, `daily_budget`, `lifetime_budget`).
- **`meta_ad_sets`**: Meta ad sets under campaigns (`id`, `meta_campaign_id`, `meta_ad_set_id`, `name`, `status`).
- **`meta_ads`**: Meta ads under ad sets (`id`, `meta_ad_set_id`, `meta_ad_id`, `name`, `status`).
- **`meta_daily_insights`**: Daily ad performance metrics (`id`, `organization_id`, `meta_campaign_id`, `date`, `spend`, `impressions`, `clicks`, `leads`, `purchases`, `conversion_value`, `cpm`, `ctr`, `cpc`, `cpl`, `roas`).

---

## 4. Migrations & Database Setup

### 4.1 Running Schema Initialization
To create tables directly from SQLAlchemy metadata:
```bash
python3 scripts/init_db.py
```

### 4.2 Seed Data
To populate demo tenant accounts (`Blueforce`, `Acme`), users, projects, tasks, chat threads, and mock Meta ad analytics:
```bash
python3 scripts/seed_db.py
```

### 4.3 Alembic Migrations
Alembic is configured in `alembic.ini` and `alembic/env.py`:
```bash
# Generate a new migration revision
alembic revision --autogenerate -m "describe_changes"

# Apply migrations
alembic upgrade head
```
