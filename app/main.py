"""
EKAIA Puerto - Main Application
FastAPI server for vehicle tracking and license plate recognition
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import get_settings
from app.models import DatabaseManager
from app.services import get_stream_manager, get_detector, get_ocr_service
from app.api import streams, detection, websocket

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""

    # Startup
    logger.info("🚀 Starting EKAIA Puerto...")

    # Initialize database
    db_manager = DatabaseManager(settings.database_url)
    try:
        await db_manager.init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database init failed: {e}")
        logger.warning("⚠️  Continuing without database...")

    # Initialize ML services
    try:
        detector = get_detector(
            settings.yolo_model_path,
            settings.yolo_device,
            settings.yolo_confidence
        )
        logger.info(f"✅ YOLO detector loaded: {settings.yolo_model_path}")
    except Exception as e:
        logger.error(f"❌ YOLO init failed: {e}")

    try:
        ocr = get_ocr_service(use_gpu=settings.ocr_gpu)
        logger.info("✅ OCR service initialized")
    except Exception as e:
        logger.error(f"❌ OCR init failed: {e}")

    # Start RTSP streams
    stream_manager = get_stream_manager()
    try:
        stream_manager.add_stream("entrada", settings.rtsp_entrada)
        logger.info(f"✅ Entrance stream started: {settings.rtsp_entrada}")
    except Exception as e:
        logger.error(f"❌ Entrance stream failed: {e}")

    try:
        stream_manager.add_stream("salida", settings.rtsp_salida)
        logger.info(f"✅ Exit stream started: {settings.rtsp_salida}")
    except Exception as e:
        logger.error(f"❌ Exit stream failed: {e}")

    logger.info("🎯 EKAIA Puerto ready!")

    yield

    # Shutdown
    logger.info("🛑 Shutting down EKAIA Puerto...")
    stream_manager.stop_all()
    logger.info("✅ All streams stopped")


# Create FastAPI app
app = FastAPI(
    title="EKAIA Puerto",
    description="Logistics platform for vehicle tracking at Iquique Port",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(streams.router)
app.include_router(detection.router)
app.include_router(websocket.router)

# Static files (frontend)
try:
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
except Exception:
    logger.warning("⚠️  Frontend directory not found")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve dashboard"""
    try:
        with open("frontend/index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return """
        <html>
            <body style="font-family: Arial; padding: 50px; text-align: center;">
                <h1>🚢 EKAIA Puerto</h1>
                <p>Vehicle Tracking System for Iquique Port</p>
                <p><a href="/docs">API Documentation</a></p>
            </body>
        </html>
        """


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    stream_manager = get_stream_manager()

    entrada = stream_manager.get_stream("entrada")
    salida = stream_manager.get_stream("salida")

    return {
        "status": "healthy",
        "streams": {
            "entrada": entrada.is_alive() if entrada else False,
            "salida": salida.is_alive() if salida else False
        }
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,  # Disable for production
        workers=1,  # Single worker for GPU
        log_level="info"
    )
