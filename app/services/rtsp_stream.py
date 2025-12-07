"""
EKAIA Puerto - RTSP Stream Manager
Handles RTSP camera streams with reconnection and buffering
"""
import cv2
import numpy as np
from typing import Optional, Generator
import threading
import time
from queue import Queue, Full
import logging

logger = logging.getLogger(__name__)


class RTSPStream:
    """Thread-safe RTSP stream handler with auto-reconnect"""

    def __init__(
        self,
        rtsp_url: str,
        name: str = "camera",
        buffer_size: int = 2,
        reconnect_delay: int = 5
    ):
        """
        Args:
            rtsp_url: RTSP URL
            name: Stream name for logging
            buffer_size: Frame buffer size (small for low latency)
            reconnect_delay: Seconds to wait before reconnect
        """
        self.rtsp_url = rtsp_url
        self.name = name
        self.buffer_size = buffer_size
        self.reconnect_delay = reconnect_delay

        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_queue = Queue(maxsize=buffer_size)
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.last_frame: Optional[np.ndarray] = None
        self.last_frame_time = 0

    def connect(self) -> bool:
        """Connect to RTSP stream"""
        try:
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)

            # Set buffer size to minimum for low latency
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # TCP transport for reliability (optional)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'H264'))

            if not self.cap.isOpened():
                logger.error(f"[{self.name}] Failed to open stream")
                return False

            logger.info(f"[{self.name}] Connected to {self.rtsp_url}")
            return True

        except Exception as e:
            logger.error(f"[{self.name}] Connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from stream"""
        if self.cap:
            self.cap.release()
            self.cap = None
        logger.info(f"[{self.name}] Disconnected")

    def _read_loop(self):
        """Background thread for reading frames"""
        consecutive_failures = 0
        max_failures = 10

        while self.is_running:
            if not self.cap or not self.cap.isOpened():
                logger.warning(f"[{self.name}] Stream disconnected, reconnecting...")
                self.disconnect()
                time.sleep(self.reconnect_delay)

                if self.connect():
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        logger.error(f"[{self.name}] Max reconnection attempts reached")
                        break
                continue

            ret, frame = self.cap.read()

            if not ret:
                consecutive_failures += 1
                logger.warning(f"[{self.name}] Failed to read frame ({consecutive_failures})")

                if consecutive_failures >= max_failures:
                    logger.error(f"[{self.name}] Too many failures, reconnecting...")
                    self.disconnect()
                    consecutive_failures = 0

                time.sleep(0.1)
                continue

            consecutive_failures = 0
            self.last_frame = frame.copy()
            self.last_frame_time = time.time()

            # Put frame in queue (drop old frames if full)
            try:
                self.frame_queue.put(frame, block=False)
            except Full:
                # Remove old frame and add new one
                try:
                    self.frame_queue.get_nowait()
                    self.frame_queue.put(frame, block=False)
                except:
                    pass

    def start(self):
        """Start stream reading thread"""
        if self.is_running:
            logger.warning(f"[{self.name}] Stream already running")
            return

        if not self.connect():
            raise RuntimeError(f"Failed to connect to {self.rtsp_url}")

        self.is_running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        logger.info(f"[{self.name}] Stream started")

    def stop(self):
        """Stop stream reading thread"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.disconnect()
        logger.info(f"[{self.name}] Stream stopped")

    def read(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """
        Read latest frame
        Returns None if no frame available
        """
        try:
            frame = self.frame_queue.get(timeout=timeout)
            return frame
        except:
            # Return last known frame if available
            return self.last_frame

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Get last captured frame (non-blocking)"""
        return self.last_frame

    def is_alive(self) -> bool:
        """Check if stream is receiving frames"""
        if not self.is_running:
            return False

        # Check if we received a frame in the last 10 seconds
        if self.last_frame_time > 0:
            age = time.time() - self.last_frame_time
            return age < 10

        return False

    def generate_jpeg_stream(self, quality: int = 80) -> Generator[bytes, None, None]:
        """
        Generate MJPEG stream for HTTP streaming
        Yields JPEG frames
        """
        while self.is_running:
            frame = self.read(timeout=1.0)

            if frame is None:
                # Send blank frame if no data
                blank = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    blank, "No Signal", (200, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2
                )
                frame = blank

            # Encode as JPEG
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            frame_bytes = buffer.tobytes()

            # MJPEG format
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


class StreamManager:
    """Manages multiple RTSP streams"""

    def __init__(self):
        self.streams: dict[str, RTSPStream] = {}

    def add_stream(self, name: str, rtsp_url: str) -> RTSPStream:
        """Add and start a new stream"""
        if name in self.streams:
            logger.warning(f"Stream {name} already exists")
            return self.streams[name]

        stream = RTSPStream(rtsp_url, name)
        stream.start()
        self.streams[name] = stream
        return stream

    def get_stream(self, name: str) -> Optional[RTSPStream]:
        """Get stream by name"""
        return self.streams.get(name)

    def stop_all(self):
        """Stop all streams"""
        for stream in self.streams.values():
            stream.stop()
        self.streams.clear()


# Global stream manager
_stream_manager = None


def get_stream_manager() -> StreamManager:
    """Get stream manager singleton"""
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = StreamManager()
    return _stream_manager
