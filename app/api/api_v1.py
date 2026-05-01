from fastapi import APIRouter

from app.api.routers import admin, ai, auth, certifications, dashboard, enrollments, exports, notifications, tasks, uploads, users, vouchers, profile, ai_suggestions, notifications_extended


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(certifications.router, prefix="/certifications", tags=["certifications"])
api_router.include_router(enrollments.router, prefix="/enrollments", tags=["enrollments"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(vouchers.router, prefix="/vouchers", tags=["vouchers"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(exports.router, prefix="/admin/exports", tags=["admin-exports"])
# New routers
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(ai_suggestions.router, prefix="/ai/suggestions", tags=["ai_suggestions"])
api_router.include_router(notifications_extended.router, prefix="/notifications", tags=["notifications_extended"])
