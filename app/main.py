import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# These will be the files we create next
from ui_panel import TelloFullPanel
from drone_controller import TelloWorker, TelloStatusThread
from video_stream import TelloVideoThread


def main():
    app = QApplication(sys.argv)

    # 1. Initialize Logic/Backend Components
    worker = TelloWorker()
    status_thread = TelloStatusThread()
    video_thread = TelloVideoThread()

    # 2. Initialize UI
    # We pass the logic objects to the UI so it can trigger commands
    window = TelloFullPanel(worker, status_thread, video_thread)

    # 3. Connect Backend Signals to UI Slots
    worker.response_received.connect(window.handle_response)
    status_thread.status_updated.connect(window.handle_status_update)
    video_thread.frame_received.connect(window.update_video_frame)

    # 4. Start Background Processes
    status_thread.start()

    # Enter SDK mode immediately
    worker.send('command')

    window.show()

    # Handle clean exit
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
