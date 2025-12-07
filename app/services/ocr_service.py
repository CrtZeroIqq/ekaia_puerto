"""
EKAIA Puerto - OCR Service
PaddleOCR integration optimized for Chilean license plates
"""
import re
import numpy as np
from typing import Optional, Tuple
from paddleocr import PaddleOCR
from PIL import Image
import cv2


class LicensePlateOCR:
    """OCR optimized for Chilean license plates"""

    # Chilean plate patterns
    PATTERNS = [
        r'^[A-Z]{4}\d{2}$',      # ABCD12
        r'^[A-Z]{2}\d{4}$',      # AB1234
        r'^[A-Z]{3}\d{3}$',      # ABC123
        r'^[A-Z]{2}\s?\d{2}\s?\d{2}$',  # AB 12 34
    ]

    def __init__(self, use_gpu: bool = True, lang: str = 'en'):
        """Initialize PaddleOCR with GPU support"""
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=use_gpu,
            show_log=False,
            det_db_thresh=0.3,
            det_db_box_thresh=0.5,
            rec_batch_num=6,
        )

    def preprocess_plate(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess plate image for better OCR
        - Resize to optimal size
        - Enhance contrast
        - Denoise
        """
        # Resize if too small (min height 60px)
        h, w = image.shape[:2]
        if h < 60:
            scale = 60 / h
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Adaptive histogram equalization
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Denoise
        denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)

        # Binarization
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return binary

    def normalize_text(self, text: str) -> str:
        """
        Normalize OCR output to Chilean plate format
        - Remove spaces and special chars
        - Fix common OCR errors (O->0, I->1, etc.)
        - Uppercase
        """
        # Remove spaces and special chars
        text = re.sub(r'[^A-Z0-9]', '', text.upper())

        # Fix common OCR errors
        replacements = {
            'O': '0', 'o': '0',
            'I': '1', 'l': '1', '|': '1',
            'S': '5', 's': '5',
            'Z': '2', 'z': '2',
            'B': '8',
            'G': '6',
        }

        # Apply replacements only in digit positions (last 2-4 chars)
        if len(text) >= 4:
            prefix = text[:-4]
            suffix = text[-4:]
            for old, new in replacements.items():
                suffix = suffix.replace(old, new)
            text = prefix + suffix

        return text

    def validate_plate(self, text: str) -> bool:
        """Check if text matches Chilean plate patterns"""
        for pattern in self.PATTERNS:
            if re.match(pattern, text):
                return True
        return False

    def extract_text(self, image: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Extract and normalize license plate text
        Returns: (plate_text, confidence)
        """
        # Preprocess
        preprocessed = self.preprocess_plate(image)

        # Run OCR
        result = self.ocr.ocr(preprocessed, cls=True)

        if not result or not result[0]:
            return None, 0.0

        # Get best result
        best_text = ""
        best_conf = 0.0

        for line in result[0]:
            text = line[1][0]
            conf = line[1][1]

            if conf > best_conf:
                best_text = text
                best_conf = conf

        # Normalize
        normalized = self.normalize_text(best_text)

        # Validate
        if not self.validate_plate(normalized):
            # Try without strict validation if confidence is high
            if best_conf < 0.7:
                return None, 0.0

        return normalized, best_conf

    def extract_from_bbox(self, frame: np.ndarray, bbox: list) -> Tuple[Optional[str], float]:
        """
        Extract plate from bounding box coordinates
        bbox: [x1, y1, x2, y2]
        """
        x1, y1, x2, y2 = map(int, bbox)

        # Add padding (10%)
        h, w = frame.shape[:2]
        pad_x = int((x2 - x1) * 0.1)
        pad_y = int((y2 - y1) * 0.1)

        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(w, x2 + pad_x)
        y2 = min(h, y2 + pad_y)

        # Crop
        plate_img = frame[y1:y2, x1:x2]

        if plate_img.size == 0:
            return None, 0.0

        return self.extract_text(plate_img)


# Singleton instance
_ocr_instance = None


def get_ocr_service(use_gpu: bool = True) -> LicensePlateOCR:
    """Get or create OCR service singleton"""
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = LicensePlateOCR(use_gpu=use_gpu)
    return _ocr_instance
