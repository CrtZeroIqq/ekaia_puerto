"""
EKAIA Puerto - Vehicle Tracking Service
Manages vehicle entry/exit and duration tracking
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import VehicleRecord, DetectionLog, VehicleStatus


class VehicleTracker:
    """Manages vehicle tracking logic"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def log_detection(
        self,
        camera: str,
        plate: str,
        confidence: float,
        bbox: list,
        ocr_text: Optional[str] = None
    ) -> DetectionLog:
        """Log raw detection for debugging"""
        log = DetectionLog(
            camera=camera,
            plate=plate,
            confidence=confidence,
            bbox=str(bbox),
            ocr_text=ocr_text
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def register_entry(
        self,
        plate: str,
        confidence: float,
        camera: str = "entrada"
    ) -> VehicleRecord:
        """
        Register vehicle entry
        If vehicle already inside, update entry time
        """
        # Check if vehicle is already inside
        stmt = select(VehicleRecord).where(
            and_(
                VehicleRecord.plate == plate,
                VehicleRecord.status == VehicleStatus.INSIDE
            )
        ).order_by(VehicleRecord.entry_time.desc())

        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update entry time (vehicle re-entered?)
            existing.entry_time = datetime.utcnow()
            existing.entry_confidence = confidence
            existing.updated_at = datetime.utcnow()
            record = existing
        else:
            # Create new record
            record = VehicleRecord(
                plate=plate,
                entry_time=datetime.utcnow(),
                entry_camera=camera,
                entry_confidence=confidence,
                status=VehicleStatus.INSIDE
            )
            self.db.add(record)

        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def register_exit(
        self,
        plate: str,
        confidence: float,
        camera: str = "salida"
    ) -> Optional[VehicleRecord]:
        """
        Register vehicle exit
        Calculate duration and close record
        """
        # Find active record for this plate
        stmt = select(VehicleRecord).where(
            and_(
                VehicleRecord.plate == plate,
                VehicleRecord.status == VehicleStatus.INSIDE
            )
        ).order_by(VehicleRecord.entry_time.desc())

        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            # No entry found - log exit only
            record = VehicleRecord(
                plate=plate,
                exit_time=datetime.utcnow(),
                exit_camera=camera,
                exit_confidence=confidence,
                status=VehicleStatus.EXITED
            )
            self.db.add(record)
        else:
            # Update exit
            record.exit_time = datetime.utcnow()
            record.exit_camera = camera
            record.exit_confidence = confidence
            record.status = VehicleStatus.EXITED

            # Calculate duration
            if record.entry_time:
                delta = record.exit_time - record.entry_time
                record.duration_minutes = delta.total_seconds() / 60

            record.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_vehicles_inside(self) -> List[VehicleRecord]:
        """Get all vehicles currently inside"""
        stmt = select(VehicleRecord).where(
            VehicleRecord.status == VehicleStatus.INSIDE
        ).order_by(VehicleRecord.entry_time.desc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_exits(self, limit: int = 50) -> List[VehicleRecord]:
        """Get recent exits"""
        stmt = select(VehicleRecord).where(
            VehicleRecord.status == VehicleStatus.EXITED
        ).order_by(VehicleRecord.exit_time.desc()).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_vehicle_history(self, plate: str, limit: int = 10) -> List[VehicleRecord]:
        """Get history for specific plate"""
        stmt = select(VehicleRecord).where(
            VehicleRecord.plate == plate
        ).order_by(VehicleRecord.created_at.desc()).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(self) -> dict:
        """Get current statistics"""
        vehicles_inside = await self.get_vehicles_inside()

        # Calculate average duration for exited vehicles today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        stmt = select(VehicleRecord).where(
            and_(
                VehicleRecord.status == VehicleStatus.EXITED,
                VehicleRecord.exit_time >= today_start,
                VehicleRecord.duration_minutes.isnot(None)
            )
        )

        result = await self.db.execute(stmt)
        exited_today = list(result.scalars().all())

        avg_duration = 0
        if exited_today:
            avg_duration = sum(v.duration_minutes for v in exited_today) / len(exited_today)

        return {
            "vehicles_inside": len(vehicles_inside),
            "exits_today": len(exited_today),
            "avg_duration_minutes": round(avg_duration, 2),
            "current_vehicles": [v.to_dict() for v in vehicles_inside]
        }
