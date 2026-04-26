import cv2
import os
import time
import threading
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage
# from ml_interface import MLModel



# --- ULTRA LOW LATENCY FFMPEG TUNING ---
# We set these environment variables before initializing VideoCapture
# to ensure the backend uses the fastest possible settings.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "protocol_whitelist;file,rtp,udp|"
    "fflags;nobuffer|"
    "flags;low_delay|"
    "probesize;32|"
    "analyzeduration:0|"
    "discard;corrupt|"
    "threads;auto|"
    "hwaccel;auto"
)


class TelloVideoThread(QThread):
    """
    Dedicated thread for capturing and decoding the Tello video stream.
    Separating this prevents the UI from stuttering during heavy decoding.
    """
    frame_received = pyqtSignal(QImage)

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self.cap = None
        # Tello default video stream address
        self.video_url = 'udp://@0.0.0.0:11111?overrun_nonfatal=1&fifo_size=5000000'

    def run(self):
        """Main decoding loop."""
        """
        if self.ml_enabled:
            class_name, conf = self.ml_model.predict(frame)

            label = f"{class_name} ({conf * 100:.1f}%)"

            cv2.putText(frame,
                        label,
                        (frame.shape[1] - 250, frame.shape[0] - 20),  # bottom right
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2)
            
        self._stop_event.clear()
        
        self.ml_enabled = False
        self.ml_model = MLModel(model_path, labels_path)
        """
        # Initialize capture inside the thread to ensure the FFmpeg
        # context is local to this thread's execution.
        self.cap = cv2.VideoCapture(self.video_url, cv2.CAP_FFMPEG)

        # Set internal buffer to minimum to reduce lag
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        while not self._stop_event.is_set():
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.1)
                continue

            try:
                ret, frame = self.cap.read()

                # Check for stop signal immediately after blocking read
                if self._stop_event.is_set():
                    break

                if ret and frame is not None:
                    # Convert BGR (OpenCV) to RGB (Qt)
                    height, width, channel = frame.shape
                    bytes_per_line = 3 * width

                    # Create QImage from raw data
                    q_img = QImage(
                        frame.data,
                        width,
                        height,
                        bytes_per_line,
                        QImage.Format.Format_RGB888
                    ).rgbSwapped()

                    self.frame_received.emit(q_img)
                else:
                    # Small sleep prevents CPU pinning if the stream is interrupted
                    time.sleep(0.01)

            except Exception as e:
                print(f"Video stream error: {e}")
                time.sleep(0.1)

        # Cleanup: Ensure the capture resource is released when the thread finishes
        if self.cap:
            self.cap.release()
            self.cap = None

    def stop(self):
        """
        Signals the loop to terminate. The thread will finish its
        current iteration and clean up self.cap internally.
        """
        self._stop_event.set()