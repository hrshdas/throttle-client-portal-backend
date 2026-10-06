# Throttle Backend API Specification

This document provides a comprehensive reference of all API endpoints implemented in the Throttle backend.

---

## Interactive Documentation & OpenAPI

When the backend application is running, OpenAPI / Swagger documentation is available at:
- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **ReDoc UI**: `http://localhost:8000/redoc`
- **OpenAPI Schema JSON**: `http://localhost:8000/openapi.json`

---

## Standard Response & Error Format

All protected endpoints require an `Authorization` header containing a valid JWT access token:
```
Authorization: Bearer <access_token>
```

### Standard Error Responses

- **401 Unauthorized**: Missing, invalid, or expired JWT token.
  ```json
  { "detail": "Could not validate credentials" }
  ```
- **403 Forbidden**: User account disabled or insufficient RBAC privileges.
  ```json
  { "detail": "Admin access required" }
  ```
- **404 Not Found**: Resource does not exist or belongs to another tenant organization.
  ```json
  { "detail": "Project not found" }
  ```
- **422 Unprocessable Entity**: Invalid request body payload schema.

---

## Endpoint Inventory

### 1. Authentication & Account Management (`/api/v1/auth`)

#### `POST /api/v1/auth/register`
- **Purpose**: Register a new client organization and client admin account.
- **Authentication**: Public
- **Request Body**: `{ "email": "admin@company.com", "password": "secure_password", "name": "Admin User", "company_name": "Acme Inc" }`
- **Response**: `{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }`
- **Errors**: `400 Bad Request` (Email address already registered).

#### `POST /api/v1/auth/login`
- **Purpose**: Authenticate user and issue JWT access/refresh token pair.
- **Authentication**: Public
- **Request Body**: `{ "email": "user@domain.com", "password": "password123" }`
- **Response**: `{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }`
- **Errors**: `401 Unauthorized` (Incorrect credentials), `403 Forbidden` (Account disabled).

#### `POST /api/v1/auth/refresh`
- **Purpose**: Rotate refresh token and obtain a new access token.
- **Authentication**: Public
- **Request Body**: `{ "refresh_token": "..." }`
- **Response**: `{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }`
- **Errors**: `401 Unauthorized` (Revoked or invalid refresh token).

#### `POST /api/v1/auth/logout`
- **Purpose**: Revoke active refresh token.
- **Authentication**: Public
- **Request Body**: `{ "refresh_token": "..." }`
- **Response**: `{ "message": "Successfully logged out" }`

#### `GET /api/v1/auth/invitation/{token}`
- **Purpose**: Retrieve invitation details prior to account creation.
- **Authentication**: Public
- **Response**: `{ "email": "user@domain.com", "name": "John", "organization_name": "Acme", "role": "CLIENT_STAFF" }`
- **Errors**: `404 Not Found` (Expired or invalid invitation token).

#### `POST /api/v1/auth/accept-invitation`
- **Purpose**: Accept team invitation and set up user account.
- **Authentication**: Public
- **Request Body**: `{ "token": "...", "name": "John Doe", "password": "new_password" }`
- **Response**: `{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }`

#### `POST /api/v1/auth/forgot-password`
- **Purpose**: Trigger password reset token generation.
- **Authentication**: Public
- **Request Body**: `{ "email": "user@domain.com" }`
- **Response**: `{ "message": "If an account with that email exists, password reset instructions have been sent." }`

#### `POST /api/v1/auth/reset-password`
- **Purpose**: Complete password reset using token.
- **Authentication**: Public
- **Request Body**: `{ "token": "...", "new_password": "..." }`
- **Response**: `{ "message": "Password successfully reset" }`

---

### 2. User Profile (`/api/v1/client`)

#### `GET /api/v1/client/me`
- **Purpose**: Get current authenticated user details and organization information.
- **Authentication**: Bearer Token (Any active user)
- **Response**: `{ "id": "...", "email": "...", "name": "...", "role": "...", "organization": { ... } }`

#### `PATCH /api/v1/client/me`
- **Purpose**: Update current authenticated user's profile details.
- **Authentication**: Bearer Token (Any active user)
- **Request Body**: `{ "name": "Updated Name" }`
- **Response**: Updated `UserResponse`.

---

### 3. Administration & Multi-Tenant Management (`/api/v1/admin`)

#### `GET /api/v1/admin/organizations`
- **Purpose**: List all tenant organizations with active user counts.
- **Authentication**: Bearer Token (`THROTTLE_ADMIN`, `THROTTLE_STAFF`)
- **Response**: `[ { "id": "...", "name": "...", "slug": "...", "user_count": 5, "created_at": "..." } ]`

#### `POST /api/v1/admin/organizations`
- **Purpose**: Create a new tenant organization.
- **Authentication**: Bearer Token (`THROTTLE_ADMIN`)
- **Request Body**: `{ "name": "New Client Corp", "slug": "new-client-corp" }`
- **Response**: `OrganizationResponse`

#### `GET /api/v1/admin/organizations/{org_id}/users`
- **Purpose**: List users in a specific tenant organization.
- **Authentication**: Bearer Token (`THROTTLE_ADMIN`, `THROTTLE_STAFF`)
- **Response**: List of `UserResponse`

#### `POST /api/v1/admin/organizations/{org_id}/invite`
- **Purpose**: Send invitation to join an organization.
- **Authentication**: Bearer Token (`THROTTLE_ADMIN` or `CLIENT_ADMIN`)
- **Request Body**: `{ "email": "member@client.com", "name": "Member", "role": "CLIENT_STAFF" }`
- **Response**: `{ "message": "Invitation sent", "invitation_token": "..." }`

#### `PATCH /api/v1/admin/users/{user_id}/disable`
- **Purpose**: Disable or re-enable a user account.
- **Authentication**: Bearer Token (`THROTTLE_ADMIN`)
- **Response**: Updated `UserResponse`

#### `GET /api/v1/admin/stats`
- **Purpose**: System-wide administrative dashboard statistics.
- **Authentication**: Bearer Token (`THROTTLE_ADMIN`, `THROTTLE_STAFF`)
- **Response**: `{ "total_organizations": 10, "total_users": 45, "active_projects": 12, "active_tasks": 88 }`

---

### 4. Projects Management (`/api/v1/projects`)

#### `GET /api/v1/projects`
- **Purpose**: List projects belonging to the user's organization.
- **Authentication**: Bearer Token
- **Query Params**: `?status=IN_PROGRESS&org_id=...` (org_id restricted for client users)
- **Response**: List of `ProjectResponse`

#### `GET /api/v1/projects/{project_id}`
- **Purpose**: Get project details by ID.
- **Authentication**: Bearer Token
- **Response**: `ProjectResponse`

#### `POST /api/v1/projects`
- **Purpose**: Create a new project.
- **Authentication**: Bearer Token (`THROTTLE_ADMIN`, `CLIENT_ADMIN`)
- **Request Body**: `{ "name": "Website Redesign", "description": "...", "budget": 15000.0 }`
- **Response**: `ProjectResponse`

#### `PATCH /api/v1/projects/{project_id}`
- **Purpose**: Update project status, budget, or details.
- **Authentication**: Bearer Token (`THROTTLE_ADMIN`, `CLIENT_ADMIN`)
- **Response**: `ProjectResponse`

#### `GET /api/v1/projects/{project_id}/milestones`
- **Purpose**: List milestones for a project.
- **Authentication**: Bearer Token
- **Response**: List of `ProjectMilestoneResponse`

#### `POST /api/v1/projects/{project_id}/milestones`
- **Purpose**: Add a milestone to a project.
- **Authentication**: Bearer Token (`THROTTLE_ADMIN`, `CLIENT_ADMIN`)
- **Request Body**: `{ "title": "Design Sign-off", "due_date": "2026-11-01" }`
- **Response**: `ProjectMilestoneResponse`

---

### 5. Task Workflow & Client Approvals (`/api/v1/tasks`)

#### `GET /api/v1/tasks`
- **Purpose**: List tasks for current tenant.
- **Authentication**: Bearer Token
- **Query Params**: `?project_id=...&status=IN_REVIEW&priority=HIGH`
- **Response**: List of `TaskResponse`

#### `GET /api/v1/tasks/{task_id}`
- **Purpose**: Get task details.
- **Authentication**: Bearer Token
- **Response**: `TaskResponse`

#### `POST /api/v1/tasks`
- **Purpose**: Create a new task under a project.
- **Authentication**: Bearer Token
- **Request Body**: `{ "project_id": "...", "title": "Review Copywriting", "priority": "HIGH" }`
- **Response**: `TaskResponse`

#### `PATCH /api/v1/tasks/{task_id}`
- **Purpose**: Update task status, description, or assignment.
- **Authentication**: Bearer Token
- **Response**: `TaskResponse`

#### `POST /api/v1/tasks/{task_id}/approve`
- **Purpose**: Client approval endpoint for tasks in `IN_REVIEW` status.
- **Authentication**: Bearer Token (`CLIENT_ADMIN`, `CLIENT_STAFF`, `THROTTLE_ADMIN`)
- **Request Body**: `{ "notes": "Approved! Looks great." }`
- **Response**: Updated `TaskResponse` (`status` transitions to `APPROVED`)

#### `POST /api/v1/tasks/{task_id}/request-changes`
- **Purpose**: Client revision request endpoint for tasks.
- **Authentication**: Bearer Token (`CLIENT_ADMIN`, `CLIENT_STAFF`, `THROTTLE_ADMIN`)
- **Request Body**: `{ "notes": "Please update hero section copy." }`
- **Response**: Updated `TaskResponse` (`status` transitions to `CHANGES_REQUESTED`)

#### `GET /api/v1/tasks/{task_id}/comments`
- **Purpose**: List discussion comments on a task.
- **Authentication**: Bearer Token
- **Response**: List of `TaskCommentResponse`

#### `POST /api/v1/tasks/{task_id}/comments`
- **Purpose**: Add a comment to a task.
- **Authentication**: Bearer Token
- **Request Body**: `{ "comment_text": "Updates uploaded to Figma." }`
- **Response**: `TaskCommentResponse`

---

### 6. Communication & Real-time Messaging (`/api/v1/chat`)

#### `GET /api/v1/chat`
- **Purpose**: List active chat conversations for current tenant.
- **Authentication**: Bearer Token
- **Response**: List of `ConversationResponse`

#### `GET /api/v1/chat/{conversation_id}/messages`
- **Purpose**: Fetch message thread history for a conversation.
- **Authentication**: Bearer Token
- **Response**: List of `MessageResponse`

#### `POST /api/v1/chat/{conversation_id}/messages`
- **Purpose**: Send a message in a chat thread.
- **Authentication**: Bearer Token
- **Request Body**: `{ "content": "When can we expect the next deliverable?" }`
- **Response**: `MessageResponse`

#### `POST /api/v1/chat/{conversation_id}/read`
- **Purpose**: Mark conversation messages as read.
- **Authentication**: Bearer Token
- **Response**: `{ "message": "Marked read" }`

---

### 7. Notifications & Activity Audit (`/api/v1/notifications`, `/api/v1/activities`)

#### `GET /api/v1/notifications`
- **Purpose**: Fetch unread/all notifications for authenticated user.
- **Authentication**: Bearer Token
- **Response**: List of `NotificationResponse`

#### `POST /api/v1/notifications/{notification_id}/read`
- **Purpose**: Mark a specific notification as read.
- **Authentication**: Bearer Token
- **Response**: `NotificationResponse`

#### `POST /api/v1/notifications/read-all`
- **Purpose**: Mark all user notifications as read.
- **Authentication**: Bearer Token
- **Response**: `{ "message": "All notifications marked read" }`

#### `GET /api/v1/activities`
- **Purpose**: Fetch audit log activities for current tenant.
- **Authentication**: Bearer Token
- **Response**: List of `ActivityResponse`

---

### 8. Analytics Engine (`/api/v1/analytics`)

#### `GET /api/v1/analytics/overview`
- **Purpose**: Retrieve aggregate marketing performance KPIs (spend, impressions, clicks, leads, purchases, revenue, CPM, CTR, CPC, CPL, ROAS).
- **Authentication**: Bearer Token
- **Query Params**: `?range=7d` | `30d` | `90d`
- **Response**: `AnalyticsOverviewResponse`

#### `GET /api/v1/analytics/timeseries`
- **Purpose**: Retrieve daily historical analytics timeseries for plotting charts.
- **Authentication**: Bearer Token
- **Query Params**: `?range=30d`
- **Response**: List of `TimeSeriesPoint`

#### `GET /api/v1/analytics/campaigns`
- **Purpose**: Campaign-level breakdown of performance analytics.
- **Authentication**: Bearer Token
- **Query Params**: `?range=30d`
- **Response**: List of `CampaignAnalyticsResponse`

---

### 9. Meta Marketing API Integration (`/api/v1/meta`)

#### `POST /api/v1/meta/demo-connect`
- **Purpose**: Enable demo connection mode with simulated Meta marketing dataset for development/demo environments.
- **Authentication**: Bearer Token (`CLIENT_ADMIN`, `THROTTLE_ADMIN`)
- **Response**: `MetaConnectionResponse`

#### `POST /api/v1/meta/connect/start`
- **Purpose**: Initiate real Meta OAuth 2.0 authorization code flow. Generates CSRF state token and returns official Meta authorization URL.
- **Authentication**: Bearer Token (`CLIENT_ADMIN`, `THROTTLE_ADMIN`)
- **Response**: `{ "authorization_url": "https://www.facebook.com/v26.0/dialog/oauth?...", "state": "..." }`

#### `GET /api/v1/meta/connect/callback`
- **Purpose**: Meta OAuth redirect callback receiver. Exchanges authorization code for long-lived user access token.
- **Authentication**: Public (CSRF protected via state parameter)
- **Query Params**: `code=...&state=...`

#### `GET /api/v1/meta/ad-accounts`
- **Purpose**: List Meta Ad Accounts accessible by the connected Meta user.
- **Authentication**: Bearer Token
- **Response**: List of `MetaAdAccountResponse`

#### `POST /api/v1/meta/select-ad-account`
- **Purpose**: Bind a specific Meta Ad Account to the tenant organization and trigger initial historical data sync.
- **Authentication**: Bearer Token (`CLIENT_ADMIN`, `THROTTLE_ADMIN`)
- **Request Body**: `{ "ad_account_id": "act_1020304050" }`
- **Response**: `MetaConnectionResponse`

#### `GET /api/v1/meta/connection`
- **Purpose**: Get current tenant Meta Connection status and sync state.
- **Authentication**: Bearer Token
- **Response**: `MetaConnectionResponse`

#### `POST /api/v1/meta/sync`
- **Purpose**: Trigger on-demand background resynchronization of Meta campaigns, ad sets, ads, and daily insights.
- **Authentication**: Bearer Token (`CLIENT_ADMIN`, `THROTTLE_ADMIN`)
- **Response**: `MetaConnectionResponse`

#### `POST /api/v1/meta/disconnect`
- **Purpose**: Disconnect Meta integration and clear token credentials.
- **Authentication**: Bearer Token (`CLIENT_ADMIN`, `THROTTLE_ADMIN`)
- **Response**: `{ "message": "Meta account disconnected successfully" }`
