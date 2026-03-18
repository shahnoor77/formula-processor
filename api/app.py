"""FastAPI application."""
from contextlib import asynccontextmanager
import threading
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.batch_loader import batch_loader
from api.tag_routes import router as tag_router
from api.system_routes import router as system_router
from api.formula_routes import router as formula_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

# Background thread for batch processing
batch_thread = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global batch_thread
    
    # Startup
    logger.info("application_starting")
    
    # Start batch processing in background thread
    batch_thread = threading.Thread(target=batch_loader.run, daemon=True)
    batch_thread.start()
    logger.info("batch_processing_started")
    
    yield
    
    # Shutdown
    logger.info("application_shutting_down")
    batch_loader.stop()
    if batch_thread:
        batch_thread.join(timeout=5)


# Create FastAPI app
app = FastAPI(
    title="Tag Processor",
    description="Modular event-driven tag processing system",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(tag_router)
app.include_router(system_router)
app.include_router(formula_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "tag-processor",
        "version": "2.0.0",
        "status": "running"
    }
