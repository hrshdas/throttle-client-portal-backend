# Throttle Multi-Tenancy & Data Isolation Model

This document explains the organization-level multi-tenancy architecture and data isolation safeguards in the Throttle backend.

---

## 1. Architectural Model

Throttle uses a **Logical Data Isolation Architecture** (shared database schema, tenant-keyed records). Every tenant in the system corresponds to an `Organization`.

```
Authenticated User (JWT)
       │
       ▼
Organization Context (user.organization_id)
       │
       ▼
Authorized Tenant Resources Only
  ├── Projects
  ├── Tasks & Milestones
  ├── Chat Conversations & Messages
  ├── Notifications & Activity Logs
  └── Meta Marketing Connection & Daily Insights
```

---

## 2. Strict Tenant Boundaries

### Key Rule
> **A client must NEVER be able to access another organization's data simply by supplying or modifying an `organization_id` parameter in API requests.**

### Implementation Blueprint

1. **Identity Binding**:
   When a user authenticates, their `organization_id` is retrieved directly from their validated `User` record in the database during JWT decoding in `app/core/dependencies.py`:
   ```python
   user = await db.execute(select(User).where(User.id == user_id))
   ```

2. **Query Scoping**:
   All entity queries scope results exclusively to `current_user.organization_id`. User-provided `organization_id` request query parameters are ignored or validated against `current_user.organization_id`.

   *Example from `app/api/v1/projects.py`:*
   ```python
   query = select(Project).where(Project.organization_id == current_user.organization_id)
   ```

   *Example from `app/api/v1/meta.py`:*
   ```python
   # Attempts by client users to supply a foreign org_id query param are overridden
   target_org_id = current_user.organization_id
   ```

---

## 3. Administrative Multi-Tenant Scoping

Agency administrators (`THROTTLE_ADMIN`, `THROTTLE_STAFF`) are granted cross-tenant visibility. When an agency admin calls tenant endpoints:
- Agency admins may explicitly query an organization using `?org_id=<id>`.
- Client users (`CLIENT_ADMIN`, `CLIENT_STAFF`, `CLIENT_VIEWER`) attempting to supply `?org_id=<id>` are restricted strictly to their own `current_user.organization_id`.

---

## 4. Empirical Tenant Isolation Verification

Tenant isolation is verified by automated pytest test suites:
- `tests/test_tenant_isolation.py`: Tests project and message isolation across distinct tenant organizations (`Blueforce` vs `Acme`).
- `tests/test_meta_tenant_isolation.py`: Tests Meta ad connections, campaigns, overview analytics, and timeseries metric isolation. Confirms cross-tenant access attempts return `404 Not Found` or empty datasets rather than leaking foreign tenant data.
