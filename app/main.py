"""
The Life Shield - Main FastAPI Application
Multi-channel credit repair platform with AI agents
"""

from fastapi import FastAPI, HTTPException, Depends, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="The Life Shield API",
    description="AI-Powered Credit Repair Platform",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================
# DATABASE CONNECTION
# ========================================

from database.connection import get_db, init_db

# Initialize database
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()
    logger.info("Database initialized")

# ========================================
# ROUTE IMPORTS
# ========================================

from api.auth import router as auth_router
from api.credit.routes import router as credit_router
from api.disputes.routes import router as disputes_router
from api.agents.routes import router as agents_router
from api.portal.routes import router as portal_router

# ========================================
# REGISTER ROUTES
# ========================================

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "The Life Shield"}

# API routes
app.include_router(auth_router)
app.include_router(credit_router)
app.include_router(disputes_router)
app.include_router(agents_router)
app.include_router(portal_router)

# ========================================
# STATIC FILES & SPA
# ========================================

# Mount static files (React build)
if os.path.exists("frontend/build"):
    app.mount("/static", StaticFiles(directory="frontend/build/static"), name="static")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA for all non-API routes"""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse("frontend/build/index.html")

# ========================================
# WEBSOCKET SUPPORT (REAL-TIME CHAT)
# ========================================

from api.websocket import manager

@app.websocket("/ws/chat/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for real-time portal chat with Tim Shaw"""
    await manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            
            # Route message to Tim Shaw agent
            from agents.tim_shaw import TimShaw
            from database.connection import SessionLocal
            
            db = SessionLocal()
            tim = TimShaw(client_id, db)
            response = tim.respond_to_message(data, channel="portal")
            
            await websocket.send_json(response)
            db.close()
    
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        manager.disconnect(client_id)

# ========================================
# ERROR HANDLERS
# ========================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return {
        "success": False,
        "error": exc.detail,
        "status_code": exc.status_code
    }

# ========================================
# STARTUP TASKS
# ========================================

@app.on_event("startup")
async def startup_background_tasks():
    """Start background tasks"""
    from tasks.monitor_disputes import monitor_all_disputes
    from tasks.soft_pull_monitoring import soft_pull_monitor
    
    # Start monitoring tasks
    import asyncio
    asyncio.create_task(monitor_all_disputes())
    asyncio.create_task(soft_pull_monitor())
    
    logger.info("Background tasks started")

# ========================================
# RUN
# ========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
