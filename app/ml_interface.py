import sys
import os

# Ensure venv site-packages are visible inside QThread on macOS
venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "lib", "python3.9", "site-packages")
if venv_path not in sys.path:
    sys.path.insert(0, venv_path)

import queue
import threading
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

np.set_printoptions(suppress=True)


class MLWorker(QThread):
    """
    Runs Teachable Machine inference in a dedicated thread.

    Flow:
        VideoThread  --(submit_frame)-→  [queue, size=1]  -→  MLWorker  -→  prediction_ready signal
                                                                                      |
                                                                            UI stores latest labels
                                                                            (drawn on every video frame)

    The queue holds at most 1 frame. If the model is still busy when a new
    frame arrives, the stale pending frame is evicted and replaced — so
    inference always runs on the freshest available frame, with zero backlog.
    """

    # Emits a list of (class_name, confidence) tuples, sorted by confidence desc
    prediction_ready = pyqtSignal(list)

    def __init__(self, model_path: str, labels_path: str, parent=None):
        super().__init__(parent)
        self.model_path = model_path
        self.labels_path = labels_path

        self.frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()

        self.model = None
        self.class_names: list = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_frame(self, bgr_frame) -> None:
        """Non-blocking submit. Evicts stale frame if queue is full."""
        try:
            self.frame_queue.put_nowait(bgr_frame.copy())
        except queue.Full:
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.frame_queue.put_nowait(bgr_frame.copy())
            except queue.Full:
                pass

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self.frame_queue.put_nowait(None)
        except queue.Full:
            pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_model(self) -> bool:
        try:
            from tensorflow.keras.models import load_model
            self.model = load_model(self.model_path, compile=False)
            with open(self.labels_path, "r") as f:
                self.class_names = [line.strip() for line in f.readlines()]
            print("[MLWorker] Model loaded OK.")
            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False

    def _preprocess(self, bgr_frame) -> np.ndarray:
        from PIL import Image, ImageOps
        rgb = bgr_frame[:, :, ::-1]
        img = Image.fromarray(rgb.astype("uint8"), "RGB")
        img = ImageOps.fit(img, (224, 224), Image.Resampling.LANCZOS)
        arr = (np.asarray(img, dtype=np.float32) / 127.5) - 1.0
        return np.expand_dims(arr, axis=0)

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------

    def run(self) -> None:
        if not self._load_model():
            return

        while not self._stop_event.is_set():
            try:
                frame = self.frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if frame is None:
                break

            try:
                data = self._preprocess(frame)
                prediction = self.model.predict(data, verbose=0)

                results = []
                for i, conf in enumerate(prediction[0]):
                    raw = self.class_names[i]
                    # Teachable Machine labels are formatted "0 ClassName"
                    name = raw[2:] if len(raw) > 2 and raw[1] == " " else raw
                    results.append((name, float(conf)))

                # Sort highest confidence first
                results.sort(key=lambda x: x[1], reverse=True)

                self.prediction_ready.emit(results)

            except Exception as e:
                print(f"[MLWorker] Inference error: {e}")