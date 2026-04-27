import sys
import os
from PyQt6.QtWidgets import QApplication
import pygame

from ui_panel import TelloFullPanel
from drone_controller import TelloWorker, TelloStatusThread
from video_stream import TelloVideoThread
from gamepad import GamepadWorker
from ml_interface import MLWorker


def main():
    # 1. Qt Application
    app = QApplication(sys.argv)

    # 2. Backend threads
    worker = TelloWorker()
    status_thread = TelloStatusThread()
    video_thread = TelloVideoThread()

    pygame.init()
    pygame.joystick.init()
    gamepad = GamepadWorker()

    # 3. ML Worker — paths relative to this file
    base_dir = os.path.dirname(__file__)
    model_path  = os.path.join(base_dir, "model", "keras_model.h5")
    labels_path = os.path.join(base_dir, "model", "labels.txt")
    ml_worker = MLWorker(model_path, labels_path)

    # Inject worker into video thread so it can submit frames
    video_thread.ml_worker = ml_worker

    # Route ML predictions back to the video thread for overlay drawing
    # (signal is emitted on Qt main thread — set_prediction is thread-safe)
    ml_worker.prediction_ready.connect(video_thread.set_prediction)

    # 4. UI
    window = TelloFullPanel(worker, status_thread, video_thread, gamepad, ml_worker)

    # 5. Connect signals
    worker.response_received.connect(window.handle_response)
    status_thread.status_updated.connect(window.handle_status_update)
    video_thread.frame_received.connect(window.update_video_frame)

    gamepad.command_signal.connect(worker.send)
    gamepad.button_signal.connect(worker.send)
    gamepad.axis_signal.connect(window.update_visualizer_sticks)

    # 6. Start threads
    status_thread.start()
    ml_worker.start()   # loads model in background — app is usable immediately
    worker.send('command')

    # 7. Show UI
    window.show()

    # 8. Clean exit
    exit_code = app.exec()

    gamepad.stop()
    ml_worker.stop()
    ml_worker.wait()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()