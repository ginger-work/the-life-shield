"""
API v1 Router — wires all sub-routers under /api/v1
"""
from fastapi import APIRouter

from app.api.v1.auth.routes import router as auth_router
from app.api.v1.credit import router as credit_router
from app.api.v1.disputes import router as disputes_router
from app.api.v1.clients.routes import router as clients_router
from app.api.v1.agents.routes import router as agents_router
from app.api.v1.communications.routes import router as communications_router
from app.api.v1.products.routes import router as products_router
from app.api.v1.admin.routes import router as admin_router
from app.api.v1.email.routes import router as email_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(credit_router, prefix="/credit", tags=["credit"])
api_router.include_router(disputes_router, prefix="/disputes", tags=["disputes"])
api_router.include_router(clients_router, prefix="/clients", tags=["clients"])
api_router.include_router(agents_router, prefix="/agents", tags=["agents"])
api_router.include_router(communications_router, prefix="/communications", tags=["communications"])
api_router.include_router(products_router, prefix="/products", tags=["products"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(email_router, prefix="/email", tags=["email"])
