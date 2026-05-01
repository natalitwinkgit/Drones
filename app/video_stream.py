import cv2
import os
import time
import threading
from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage
import numpy as np


# --- ULTRA LOW LATENCY FFMPEG TUNING ---
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
    Captures / decodes the Tello video stream at full speed.

    ML integration
    --------------
    Set self.ml_worker to an MLWorker instance and toggle self.ml_enabled
    to start/stop inference. Frames are submitted non-blocking — this thread
    is NEVER delayed by inference. The latest predictions are stored and drawn
    onto every outgoing frame as an overlay, so the video feed always runs at
    full speed while labels update at the model's own pace.
    """

    frame_received = pyqtSignal(QImage)
    status_message = pyqtSignal(str)
    recording_state_changed = pyqtSignal(bool, str)
    snapshot_saved = pyqtSignal(str)

    def __init__(self, demo_mode: bool = False):
        super().__init__()
        self.demo_mode = demo_mode
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self.cap = None
        self.video_url = 'udp://@0.0.0.0:11111?overrun_nonfatal=1&fifo_size=5000000'

        # ML state
        self.ml_enabled: bool = False
        self.ml_worker = None               # injected by main.py
        self.filter_mode = "normal"

        base_output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "captures"))
        self.recordings_dir = os.path.join(base_output_dir, "recordings")
        self.snapshots_dir = os.path.join(base_output_dir, "snapshots")
        os.makedirs(self.recordings_dir, exist_ok=True)
        os.makedirs(self.snapshots_dir, exist_ok=True)

        self.recording_enabled = False
        self.recording_output_path = ""
        self._video_writer = None
        self._last_display_frame = None

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------

    def run(self):
        self._stop_event.clear()

        if self.demo_mode:
            self.status_message.emit("Demo video mode enabled.")
            self._run_demo_stream()
            self._release_video_writer()
            return

        self.cap = cv2.VideoCapture(self.video_url, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        while not self._stop_event.is_set():
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.1)
                continue

            try:
                ret, frame = self.cap.read()

                if self._stop_event.is_set():
                    break

                if not ret or frame is None:
                    time.sleep(0.01)
                    continue

                # --- Submit to ML worker (non-blocking, never waits) ---
                if self.ml_enabled and self.ml_worker is not None:
                    self.ml_worker.submit_frame(frame)

                filtered_frame = self._apply_filter(frame)
                output_frame = self._draw_hud(filtered_frame)

                with self._state_lock:
                    self._last_display_frame = output_frame.copy()

                if self.recording_enabled and not self._write_recording_frame(output_frame):
                    self.status_message.emit("Recording failed. Check codec support and output path.")

                # --- Convert BGR → QImage and emit ---
                h, w, _ = output_frame.shape
                q_img = QImage(
                    output_frame.data, w, h, 3 * w,
                    QImage.Format.Format_RGB888
                ).rgbSwapped()

                self.frame_received.emit(q_img)

            except Exception as e:
                print(f"[VideoThread] Error: {e}")
                time.sleep(0.1)

        if self.cap:
            self.cap.release()
            self.cap = None
        self._release_video_writer()

    def stop(self):
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Public controls
    # ------------------------------------------------------------------

    def set_filter_mode(self, mode: str) -> None:
        if mode not in {"normal", "gray", "edges", "night"}:
            return
        with self._state_lock:
            self.filter_mode = mode
        self.status_message.emit(f"Video filter set to {mode.upper()}")

    def start_recording(self) -> bool:
        if not self.isRunning():
            self.status_message.emit("Start the video stream before recording.")
            return False

        with self._state_lock:
            if self.recording_enabled:
                return True
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.recording_enabled = True
            self.recording_output_path = os.path.join(
                self.recordings_dir,
                f"tello_recording_{timestamp}.mp4"
            )

        self.recording_state_changed.emit(True, self.recording_output_path)
        self.status_message.emit(f"Recording armed: {os.path.basename(self.recording_output_path)}")
        return True

    def stop_recording(self) -> bool:
        with self._state_lock:
            if not self.recording_enabled and self._video_writer is None:
                return False
            output_path = self.recording_output_path
            self.recording_enabled = False

        self._release_video_writer()
        self.recording_state_changed.emit(False, output_path)
        if output_path:
            self.status_message.emit(f"Recording saved: {os.path.basename(output_path)}")
        return True

    def save_snapshot(self) -> str:
        with self._state_lock:
            if self._last_display_frame is None:
                self.status_message.emit("No video frame available for snapshot yet.")
                return ""
            frame = self._last_display_frame.copy()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(self.snapshots_dir, f"tello_snapshot_{timestamp}.png")
        if not cv2.imwrite(output_path, frame):
            self.status_message.emit("Snapshot save failed.")
            return ""

        self.snapshot_saved.emit(output_path)
        self.status_message.emit(f"Snapshot saved: {os.path.basename(output_path)}")
        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_filter(self, frame):
        with self._state_lock:
            mode = self.filter_mode

        if mode == "gray":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        if mode == "edges":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 80, 160)
            return cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

        if mode == "night":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            enhanced = cv2.equalizeHist(gray)
            night = np.zeros_like(frame)
            night[:, :, 0] = (enhanced * 0.25).astype(np.uint8)
            night[:, :, 1] = enhanced
            night[:, :, 2] = (enhanced * 0.15).astype(np.uint8)
            return night

        return frame.copy()

    def _run_demo_stream(self):
        frame_idx = 0

        while not self._stop_event.is_set():
            frame = self._generate_demo_frame(frame_idx)
            filtered_frame = self._apply_filter(frame)
            output_frame = self._draw_hud(filtered_frame)

            with self._state_lock:
                self._last_display_frame = output_frame.copy()

            if self.recording_enabled and not self._write_recording_frame(output_frame):
                self.status_message.emit("Recording failed. Check codec support and output path.")

            h, w, _ = output_frame.shape
            q_img = QImage(
                output_frame.data, w, h, 3 * w,
                QImage.Format.Format_RGB888
            ).rgbSwapped()
            self.frame_received.emit(q_img)

            frame_idx += 1
            time.sleep(1 / 30)

    def _generate_demo_frame(self, frame_idx: int):
        height, width = 720, 960
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Background gradient
        gradient = np.linspace(20, 90, width, dtype=np.uint8)
        frame[:, :, 0] = gradient
        frame[:, :, 1] = gradient[::-1]
        frame[:, :, 2] = 40

        # Grid
        for x in range(0, width, 80):
            cv2.line(frame, (x, 0), (x, height), (40, 70, 100), 1)
        for y in range(0, height, 80):
            cv2.line(frame, (0, y), (width, y), (40, 70, 100), 1)

        # Moving drone marker
        cx = int(width / 2 + np.sin(frame_idx * 0.04) * 260)
        cy = int(height / 2 + np.cos(frame_idx * 0.03) * 170)
        cv2.circle(frame, (cx, cy), 28, (0, 212, 255), -1)
        cv2.circle(frame, (cx, cy), 54, (255, 255, 255), 2)
        cv2.line(frame, (cx - 75, cy), (cx + 75, cy), (255, 255, 255), 1)
        cv2.line(frame, (cx, cy - 75), (cx, cy + 75), (255, 255, 255), 1)

        # Simulated horizon
        horizon_y = int(height / 2 + np.sin(frame_idx * 0.02) * 50)
        cv2.line(frame, (0, horizon_y), (width, horizon_y), (0, 255, 120), 2)

        # Labels
        cv2.putText(
            frame,
            "TELLO DEMO FEED",
            (width - 310, height - 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        return frame

    def _draw_hud(self, frame):
        output = frame.copy()
        overlay = output.copy()
        cv2.rectangle(overlay, (12, 12), (220, 68), (10, 20, 36), -1)
        cv2.addWeighted(overlay, 0.55, output, 0.45, 0, output)

        with self._state_lock:
            filter_mode = self.filter_mode.upper()
            recording = self.recording_enabled

        cv2.putText(
            output,
            f"FILTER: {filter_mode}",
            (24, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 212, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            output,
            datetime.now().strftime("%H:%M:%S"),
            (24, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

        if recording:
            cv2.circle(output, (output.shape[1] - 86, 34), 8, (0, 0, 255), -1)
            cv2.putText(
                output,
                "REC",
                (output.shape[1] - 70, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        return output

    def _write_recording_frame(self, frame) -> bool:
        if not self._ensure_video_writer(frame.shape[1], frame.shape[0]):
            with self._state_lock:
                failed_path = self.recording_output_path
                self.recording_enabled = False
                self.recording_output_path = ""
            self.recording_state_changed.emit(False, failed_path)
            return False

        self._video_writer.write(frame)
        return True

    def _ensure_video_writer(self, width: int, height: int) -> bool:
        if self._video_writer is not None:
            return True

        fps = 30.0
        if self.cap is not None:
            detected_fps = self.cap.get(cv2.CAP_PROP_FPS)
            if 1 <= detected_fps <= 120:
                fps = detected_fps

        writer = cv2.VideoWriter(
            self.recording_output_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            writer.release()
            return False

        self._video_writer = writer
        return True

    def _release_video_writer(self) -> None:
        with self._state_lock:
            writer = self._video_writer
            self._video_writer = None

        if writer is not None:
            writer.release()
