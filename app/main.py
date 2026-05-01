import argparse
import sys
import os


def parse_args():
    parser = argparse.ArgumentParser(description="DJI Tello Command Center")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the UI without a real Tello drone using simulated status and video.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    from PyQt6.QtWidgets import QApplication
    import pygame

    from ui_panel import TelloFullPanel
    from drone_controller import TelloWorker, TelloStatusThread
    from video_stream import TelloVideoThread
    from gamepad import GamepadWorker
    from ml_interface import MLWorker

    # 1. Qt Application
    app = QApplication(sys.argv)

    # 2. Backend threads
    worker = TelloWorker(demo_mode=args.demo)
    status_thread = TelloStatusThread(demo_mode=args.demo)
    video_thread = TelloVideoThread(demo_mode=args.demo)

    pygame.init()
    pygame.joystick.init()
    gamepad = GamepadWorker()

    # 3. ML Worker — paths relative to this file
    base_dir = os.path.dirname(__file__)
    model_path  = os.path.join(base_dir, "model", "keras_model.h5")
    labels_path = os.path.join(base_dir, "model", "labels.txt")
    ml_worker = None
    if os.path.exists(model_path) and os.path.exists(labels_path):
        ml_worker = MLWorker(model_path, labels_path)
    else:
        print("ML model files not found. Continuing without ML support.")

    # Inject worker into video thread so it can submit frames
    if ml_worker is not None:
        video_thread.ml_worker = ml_worker

    # 4. UI — must be created before connecting ML signal so ml_overlay exists
    window = TelloFullPanel(worker, status_thread, video_thread, gamepad, ml_worker)

    # Route ML predictions to the overlay widget (Qt main thread, no locking needed)
    if ml_worker is not None:
        ml_worker.prediction_ready.connect(window.ml_overlay.update_results)

    # 5. Connect signals
    worker.response_received.connect(window.handle_response)
    status_thread.status_updated.connect(window.handle_status_update)
    video_thread.frame_received.connect(window.update_video_frame)

    gamepad.command_signal.connect(worker.send)
    gamepad.button_signal.connect(worker.send)
    gamepad.axis_signal.connect(window.update_visualizer_sticks)

    # 6. Start threads
    status_thread.start()
    if ml_worker is not None:
        ml_worker.start()   # loads model in background — app is usable immediately
    worker.send('command')

    # 7. Show UI
    window.show()

    # 8. Clean exit
    exit_code = app.exec()

    gamepad.stop()
    video_thread.stop_recording()
    video_thread.stop()
    video_thread.wait()
    status_thread.stop()
    status_thread.wait()
    if ml_worker is not None:
        ml_worker.stop()
        ml_worker.wait()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
