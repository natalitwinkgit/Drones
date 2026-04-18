import sys
from PyQt6.QtWidgets import QApplication
import pygame

# Local project imports
from ui_panel import TelloFullPanel
from drone_controller import TelloWorker, TelloStatusThread
from video_stream import TelloVideoThread
from gamepad import GamepadWorker


def main():
    # 1. Initialize the Qt Application
    app = QApplication(sys.argv)

    # 2. Initialize Logic/Backend Threads
    worker = TelloWorker()
    status_thread = TelloStatusThread()
    video_thread = TelloVideoThread()

    # This thread monitors hardware via the 'inputs' library (0 lag)
    pygame.init()
    pygame.joystick.init()
    gamepad = GamepadWorker()

    # 3. Initialize UI
    # Note: We pass the backend objects so the UI can interact with them
    window = TelloFullPanel(worker, status_thread, video_thread, gamepad)

    # 4. Connect Backend Signals to UI Slots

    # Drone response and status updates
    worker.response_received.connect(window.handle_response)
    status_thread.status_updated.connect(window.handle_status_update)
    video_thread.frame_received.connect(window.update_video_frame)

    # Gamepad Signal Connections
    # This sends "rc a b c d" strings directly to the drone worker
    gamepad.command_signal.connect(worker.send)
    gamepad.button_signal.connect(worker.send)
    gamepad.axis_signal.connect(window.update_visualizer_sticks)

    # 5. Start Background Threads
    status_thread.start()
    # gamepad_thread.start()

    # Enter SDK mode immediately to enable RC commands
    worker.send('command')

    # 6. Show the interface
    window.show()

    # 7. Handle clean exit
    exit_code = app.exec()

    # Clean up the hardware monitoring thread before closing
    gamepad.stop()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()