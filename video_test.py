import sys
import cv2
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from djitellopy import Tello


class VideoThread(QThread):
    # Signal to send the processed image to the GUI
    change_pixmap_signal = pyqtSignal(QImage)

    def __init__(self):
        super().__init__()
        self._run_flag = True
        self.tello = Tello()

    def run(self):
        # Connect to Tello and start video stream
        self.tello.connect()
        self.tello.streamon()

        # Get the background frame reader
        frame_read = self.tello.get_frame_read()

        while self._run_flag:
            # Capture frame-by-frame
            frame = frame_read.frame
            if frame is not None:
                # Convert OpenCV BGR to RGB
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w

                # Convert to QImage
                qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

                # Emit the image to the UI
                self.change_pixmap_signal.emit(qt_image)

            self.msleep(10)  # Brief sleep to prevent CPU hogging

    def stop(self):
        self._run_flag = False
        self.tello.streamoff()
        self.wait()


class TelloApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJI Tello PyQt Broadcast")
        self.resize(800, 600)

        # UI Setup
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setText("Connecting to Tello...")

        layout = QVBoxLayout()
        layout.addWidget(self.image_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Start Video Thread
        self.thread = VideoThread()
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.start()

    def update_image(self, qt_image):
        # Update the QLabel with the new frame
        pixmap = QPixmap.fromImage(qt_image)
        self.image_label.setPixmap(pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    def closeEvent(self, event):
        self.thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TelloApp()
    window.show()
    sys.exit(app.exec())