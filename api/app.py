import threading
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.formula_processor_service import formula_processor_service
from api.system_routes import router as system_router
from api.variable_routes import router as variable_router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()
formula_thread = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global formula_thread
    formula_thread = threading.Thread(target=formula_processor_service.start, daemon=True)
    formula_thread.start()
    logger.info("service_started")
    yield
    formula_processor_service.stop()
    if formula_thread:
        formula_thread.join(timeout=5)


app = FastAPI(title="Formula Processor", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router)
app.include_router(variable_router)
