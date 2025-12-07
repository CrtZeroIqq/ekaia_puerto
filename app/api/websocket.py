"""
EKAIA Puerto - WebSocket Endpoint
Real-time detection updates
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import json
import logging
from datetime import datetime

from app.services import (
    VehicleTracker,
    get_detector,
    get_detection_cooldown,
    get_ocr_service,
    get_stream_manager,
)
from app.models import DatabaseManager
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

settings = get_settings()
db_manager = DatabaseManager(settings.database_url)


class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all clients"""
        dead_connections = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                dead_connections.append(connection)

        # Remove dead connections
        for conn in dead_connections:
            try:
                self.active_connections.remove(conn)
            except:
                pass


manager = ConnectionManager()


async def get_db():
    async for session in db_manager.get_session():
        yield session


@router.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket):
    """
    Real-time detection websocket
    Sends detection updates every 2 seconds
    """
    await manager.connect(websocket)

    # Get services
    detector = get_detector(settings.yolo_model_path, settings.yolo_device, settings.yolo_confidence)
    ocr = get_ocr_service(use_gpu=settings.ocr_gpu)
    stream_manager = get_stream_manager()
    cooldown = get_detection_cooldown()

    try:
        while True:
            # Get database session
            async for db in get_db():
                tracker = VehicleTracker(db)

                # Process both cameras
                results = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "cameras": {}
                }

                for camera_name in ["entrada", "salida"]:
                    stream = stream_manager.get_stream(camera_name)

                    if stream and stream.is_alive():
                        frame = stream.get_latest_frame()

                        if frame is not None:
                            # Detect
                            detections = detector.detect(frame)
                            plate_detections = [d for d in detections if d.class_id == 1]

                            plates = []
                            for plate_det in plate_detections:
                                plate_text, ocr_conf = ocr.extract_from_bbox(frame, plate_det.bbox)

                                if plate_text and ocr_conf > 0.6 and cooldown.allow(plate_text, camera_name):
                                    plates.append({
                                        "text": plate_text,
                                        "confidence": plate_det.confidence,
                                        "ocr_confidence": ocr_conf
                                    })

                                    # Auto-register
                                    if camera_name == "entrada":
                                        await tracker.register_entry(plate_text, plate_det.confidence)
                                    elif camera_name == "salida":
                                        await tracker.register_exit(plate_text, plate_det.confidence)

                            results["cameras"][camera_name] = {
                                "connected": True,
                                "detections_count": len(detections),
                                "plates": plates
                            }
                        else:
                            results["cameras"][camera_name] = {"connected": False}
                    else:
                        results["cameras"][camera_name] = {"connected": False}

                # Get stats
                stats = await tracker.get_stats()
                results["stats"] = stats

                # Send to client
                await websocket.send_json(results)

                break  # Exit db session loop

            # Wait before next update
            await asyncio.sleep(2)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@router.websocket("/ws/stats")
async def websocket_stats(websocket: WebSocket):
    """
    Stats-only websocket (lighter weight)
    Updates every 5 seconds
    """
    await manager.connect(websocket)

    try:
        while True:
            async for db in get_db():
                tracker = VehicleTracker(db)
                stats = await tracker.get_stats()

                await websocket.send_json({
                    "timestamp": datetime.utcnow().isoformat(),
                    "stats": stats
                })

                break

            await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
