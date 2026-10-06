from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.auth import router as auth_router
from app.api.v1.client import router as client_router
from app.api.v1.admin import router as admin_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.projects import router as projects_router
from app.api.v1.chat import router as chat_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.activities import router as activities_router
from app.core.config import get_settings

from app.api.v1.meta import router as meta_router
from app.api.v1.analytics import router as analytics_router

settings = get_settings()

app = FastAPI(
    title="Throttle API",
    description="Multi-tenant client portal backend with real client-admin interaction engine",
    version="2.0.0",
)

# Enable CORS for Flutter app & web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers under /api/v1
app.include_router(auth_router, prefix="/api/v1")
app.include_router(client_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(activities_router, prefix="/api/v1")
app.include_router(meta_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "Throttle API 2.0", "environment": settings.ENVIRONMENT}
