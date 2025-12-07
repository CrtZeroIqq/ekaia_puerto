"""
EKAIA Puerto - YOLO Detection Service
Real-time vehicle and license plate detection with GPU acceleration
"""
import torch
import cv2
import numpy as np
from typing import List, Dict, Tuple
from ultralytics import YOLO
from dataclasses import dataclass


@dataclass
class Detection:
    """Detection result"""
    class_id: int
    class_name: str
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2]
    bbox_normalized: List[float]  # normalized [0-1]


class YOLODetector:
    """YOLO detector optimized for RTSP streams"""

    CLASS_NAMES = {
        0: "vehicle",
        1: "plate"
    }

    def __init__(
        self,
        model_path: str,
        device: str = "0",
        confidence: float = 0.5,
        iou_threshold: float = 0.45
    ):
        """
        Initialize YOLO detector
        Args:
            model_path: Path to .pt model
            device: GPU device (0, 1, etc.) or 'cpu'
            confidence: Detection confidence threshold
            iou_threshold: NMS IOU threshold
        """
        self.device = device
        self.confidence = confidence
        self.iou_threshold = iou_threshold

        # Load model
        self.model = YOLO(model_path)
        self.model.to(device)

        # Warm up GPU
        self._warmup()

    def _warmup(self):
        """Warm up GPU with dummy inference"""
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(
            dummy,
            conf=self.confidence,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False
        )

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run detection on frame
        Args:
            frame: BGR image from OpenCV
        Returns:
            List of Detection objects
        """
        # Run inference
        results = self.model.predict(
            frame,
            conf=self.confidence,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False,
            stream=False
        )[0]

        detections = []
        h, w = frame.shape[:2]

        # Parse results
        for box in results.boxes:
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])
            bbox = box.xyxy[0].cpu().numpy().tolist()

            # Normalized bbox
            x1, y1, x2, y2 = bbox
            bbox_norm = [x1/w, y1/h, x2/w, y2/h]

            detection = Detection(
                class_id=class_id,
                class_name=self.CLASS_NAMES.get(class_id, "unknown"),
                confidence=confidence,
                bbox=bbox,
                bbox_normalized=bbox_norm
            )
            detections.append(detection)

        return detections

    def detect_plates(self, frame: np.ndarray) -> List[Detection]:
        """Detect only license plates (class 1)"""
        all_detections = self.detect(frame)
        return [d for d in all_detections if d.class_id == 1]

    def detect_vehicles(self, frame: np.ndarray) -> List[Detection]:
        """Detect only vehicles (class 0)"""
        all_detections = self.detect(frame)
        return [d for d in all_detections if d.class_id == 0]

    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        show_conf: bool = True
    ) -> np.ndarray:
        """
        Draw bounding boxes on frame
        Args:
            frame: Input frame
            detections: List of detections
            show_conf: Show confidence scores
        Returns:
            Annotated frame
        """
        annotated = frame.copy()

        colors = {
            0: (0, 255, 0),    # Green for vehicles
            1: (255, 0, 0),    # Blue for plates
        }

        for det in detections:
            x1, y1, x2, y2 = map(int, det.bbox)
            color = colors.get(det.class_id, (255, 255, 255))

            # Draw box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Draw label
            label = f"{det.class_name}"
            if show_conf:
                label += f" {det.confidence:.2f}"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 10), (x1 + tw, y1), color, -1)
            cv2.putText(
                annotated, label, (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1
            )

        return annotated


# Singleton instance
_detector_instance = None


def get_detector(model_path: str, device: str = "0", confidence: float = 0.5) -> YOLODetector:
    """Get or create detector singleton"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = YOLODetector(model_path, device, confidence)
    return _detector_instance
