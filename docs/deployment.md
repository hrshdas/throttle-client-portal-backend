# Throttle Backend Deployment Architecture & Runbook

This document outlines the deployment architecture, configuration guidelines, production checklist, and current deployment status for the Throttle backend.

---

## 1. Production Architecture Overview

```
                      Internet Client Requests
                                 │
                                 ▼
                     Reverse Proxy / SSL Terminator
                   (Nginx / AWS ALB / Cloudflare)
                                 │
                                 ▼
                    FastAPI Uvicorn ASGI Server
                   (Multiple Workers via systemd/Docker)
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
      PostgreSQL Database             Meta Graph API (v26.0)
     (Managed RDS / Supabase)           (External HTTPS)
```

---

## 2. Infrastructure Requirements

- **Runtime**: Python 3.12+
- **Application Server**: `uvicorn` (ASGI server with UVLoop)
- **Database**: PostgreSQL 14+ with `asyncpg` async driver
- **Process Manager**: systemd, Supervisor, or Docker/Kubernetes container orchestration
- **SSL Termination**: Nginx, Caddy, or AWS Application Load Balancer (ALB)

---

## 3. Production Configuration Setup

### 3.1 Environment Variables
Set production environment variables in your deployment environment (e.g., AWS Secrets Manager, Doppler, or environment configuration):

```ini
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://throttle_prod_user:<SECURE_PASSWORD>@db.internal:5432/throttle_production
SECRET_KEY=<64_CHAR_CRYPTOGRAPHICALLY_SECURE_RANDOM_HEX>
FRONTEND_URL=https://portal.throttle.agency

META_APP_ID=<PRODUCTION_META_APP_ID>
META_APP_SECRET=<PRODUCTION_META_APP_SECRET>
META_API_VERSION=v26.0
META_REDIRECT_URI=https://api.throttle.agency/api/v1/meta/connect/callback
META_ENCRYPTION_KEY=<FERNET_KEY_32_BYTES_BASE64>
```

### 3.2 Uvicorn Production Command
Run Uvicorn with multiple worker processes proportional to available CPU cores:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers --forwarded-allow-ips '*'
```

---

## 4. Production Security Checklist

- [x] Disable verbose debug logs (`ENVIRONMENT=production` automatically sets database `echo=False`).
- [x] Configure strict `FRONTEND_URL` origin for CORS middleware in `app/main.py`.
- [x] Enforce HTTPS on reverse proxy level (`X-Forwarded-Proto: https`).
- [x] Generate cryptographically random `SECRET_KEY` and `META_ENCRYPTION_KEY`.
- [x] Verify `.env` file is excluded from git version control via `.gitignore`.
- [x] Ensure PostgreSQL user permissions follow least-privilege principles.

---

## 5. Current Deployment Status

> [!NOTE]
> **Deployment Status**: Development & Staging Ready.
> Production containerization (Dockerfile & docker-compose) or Kubernetes manifests can be added based on the target cloud infrastructure provider (AWS ECS, Google Cloud Run, DigitalOcean App Platform, or self-hosted Bare Metal).
