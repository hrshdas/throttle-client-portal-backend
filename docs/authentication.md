# Throttle Authentication & Authorization

This document details the authentication mechanism, token lifecycle, password management, and role-based authorization model implemented in the Throttle backend.

---

## 1. Overview

Throttle implements an OAuth2 Bearer token authentication architecture using JSON Web Tokens (JWT) signed with HMAC-SHA256 (`HS256`). Passwords are hashed using `bcrypt` with automated salting.

---

## 2. Authentication Flow

### 2.1 User Registration (`POST /api/v1/auth/register`)
1. User provides `email`, `password`, `name`, and `company_name`.
2. System checks for existing email collisions.
3. System automatically creates a new `Organization` with a unique slug.
4. User password is hashed with `bcrypt` (`passlib` / `pyca/cryptography`).
5. User is assigned the `CLIENT_ADMIN` role for the newly created organization.
6. System issues an `access_token` (valid 30 minutes) and a `refresh_token` (valid 7 days).
7. Refresh token hash is stored in the database `refresh_tokens` table.

### 2.2 User Login (`POST /api/v1/auth/login`)
1. User provides `email` and `password`.
2. System verifies user existence and validates password hash using `bcrypt.checkpw`.
3. Checks if user `is_active` flag is true.
4. Returns fresh `access_token` and `refresh_token`.

### 2.3 Token Refresh & Rotation (`POST /api/v1/auth/refresh`)
1. Client sends existing `refresh_token`.
2. System verifies JWT validity and confirms token `type == "refresh"`.
3. System verifies token hash exists in `refresh_tokens` table and `revoked_at is Null`.
4. System revokes old refresh token (`revoked_at = utcnow()`).
5. System issues a new pair of access and refresh tokens (Refresh Token Rotation pattern).

### 2.4 Logout (`POST /api/v1/auth/logout`)
1. Client sends active `refresh_token`.
2. System marks the matching refresh token as revoked in the database.

---

## 3. Token Format & Payload

JWT access tokens contain the following claims:

```json
{
  "sub": "usr_9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "org_id": "org_11223344-5566-7788-9900-aabbccddeeff",
  "role": "CLIENT_ADMIN",
  "type": "access",
  "jti": "8f3b2a1c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "exp": 1791234567
}
```

---

## 4. Team Invitations & Password Reset

### 4.1 Invitation Flow
- Organization administrators (`THROTTLE_ADMIN` or `CLIENT_ADMIN`) can invite new users via `POST /api/v1/admin/organizations/{org_id}/invite`.
- An `Invitation` record is generated with a cryptographically secure token and designated `UserRole`.
- The invited user inspects details via `GET /api/v1/auth/invitation/{token}` and completes setup via `POST /api/v1/auth/accept-invitation`.

### 4.2 Password Reset Flow
- User requests reset via `POST /api/v1/auth/forgot-password`.
- System creates a short-lived reset token (`type == "reset"`).
- User submits new password with reset token to `POST /api/v1/auth/reset-password`.

---

## 5. Role Hierarchy & RBAC Permissions

| Role Identifier | Group | Permissions Summary |
|---|---|---|
| `THROTTLE_ADMIN` | Agency Staff | Full platform super-admin access across all tenant organizations. Can manage companies, invite users, disable accounts, and view platform-wide stats. |
| `THROTTLE_STAFF` | Agency Staff | Internal team member access. Can view and manage projects, tasks, and communications across client accounts. |
| `CLIENT_ADMIN` | Client Tenant | Organization admin. Full control over their organization's projects, tasks, team members, and Meta ad account connections. |
| `CLIENT_STAFF` | Client Tenant | Standard client user. Can view projects, submit/update tasks, add comments, and participate in chat. |
| `CLIENT_VIEWER` | Client Tenant | Read-only client user. Can view organization analytics, projects, and task statuses without edit rights. |
