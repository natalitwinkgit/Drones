import sys
import socket
import re
import cv2
import numpy as np
from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QGridLayout, 
                             QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox, 
                             QSlider, QFrame, QLabel, QSizePolicy, QDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QSize
from PyQt6.QtGui import QKeyEvent, QImage, QPixmap

# --- VIDEO THREAD (Port 11111) ---
class TelloVideoThread(QThread):
    frame_received = pyqtSignal(QImage)

    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        # Tello sends video to port 11111 via UDP
        # Simplified URL for better compatibility on macOS/Homebrew FFMPEG
        video_url = 'udp://@0.0.0.0:11111'
        
        # Adding a small delay to ensure 'streamon' command has reached the drone
        self.msleep(1000)
        
        cap = cv2.VideoCapture(video_url)
        
        # Optional: Set buffer size to reduce latency
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

        if not cap.isOpened():
            print("Error: Could not open video stream. Retrying with fallback...")
            # Fallback for some OpenCV versions
            cap = cv2.VideoCapture(video_url, cv2.CAP_FFMPEG)

        if not cap.isOpened():
            print("Error: Video stream failed to open. Check if drone is connected and 'streamon' sent.")
            return

        while self.running:
            ret, frame = cap.read()
            if ret:
                # Convert BGR (OpenCV) to RGB (Qt)
                height, width, channel = frame.shape
                bytes_per_line = 3 * width
                q_img = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).rgbSwapped()
                self.frame_received.emit(q_img)
            else:
                # If frame capture fails, don't crash, just wait and retry
                self.msleep(10)
        
        cap.release()

    def stop(self):
        self.running = False
        self.wait()

# --- PATTERN DESIGNER DIALOG ---
class PatternDialog(QDialog):
    last_saved_state = None 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("8x8 LED Pattern Designer")
        self.setFixedSize(420, 560)
        self.pattern_string = ""
        
        self.colors = {
            0: ("#444", "0"),      # Off
            1: ("#ff0000", "r"),   # Red
            2: ("#0000ff", "b"),   # Blue
            3: ("#800080", "p")    # Purple
        }
        
        self.grid_state = [0] * 64
        self.buttons = []
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        header_layout = QHBoxLayout()
        info_label = QLabel("Click pixels to cycle colors:\nGray -> Red -> Blue -> Purple")
        info_label.setStyleSheet("color: white; font-size: 11px; font-weight: bold;")
        
        self.btn_load_saved = QPushButton("Display Saved")
        self.btn_load_saved.setFixedSize(110, 35)
        self.btn_load_saved.setStyleSheet("""
            background-color: #009688; color: white; border-radius: 4px; font-size: 11px;
        """)
        self.btn_load_saved.clicked.connect(self.load_saved_pattern)
        
        if PatternDialog.last_saved_state is None:
            self.btn_load_saved.setEnabled(False)

        header_layout.addWidget(info_label, 1)
        header_layout.addWidget(self.btn_load_saved)
        layout.addLayout(header_layout)

        grid_widget = QWidget()
        self.grid_layout = QGridLayout(grid_widget)
        self.grid_layout.setSpacing(2)
        
        for i in range(64):
            btn = QPushButton()
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(f"background-color: {self.colors[0][0]}; border: 1px solid #222;")
            btn.clicked.connect(lambda checked, idx=i: self.cycle_color(idx))
            self.grid_layout.addWidget(btn, i // 8, i % 8)
            self.buttons.append(btn)
            
        layout.addWidget(grid_widget)

        controls = QHBoxLayout()
        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self.clear_grid)
        btn_clear.setStyleSheet("background-color: #f44336; color: white; min-height: 40px;")
        
        btn_save = QPushButton("Save Pattern")
        btn_save.clicked.connect(self.save_current_pattern)
        btn_save.setStyleSheet("background-color: #2196F3; color: white; min-height: 40px;")

        btn_ok = QPushButton("Send to Drone")
        btn_ok.clicked.connect(self.accept_pattern)
        btn_ok.setStyleSheet("background-color: #4CAF50; color: white; min-height: 40px;")
        
        controls.addWidget(btn_clear)
        controls.addWidget(btn_save)
        controls.addWidget(btn_ok)
        layout.addLayout(controls)
        
        self.setLayout(layout)
        self.setStyleSheet("background-color: #1a2a44;")

    def cycle_color(self, idx):
        self.grid_state[idx] = (self.grid_state[idx] + 1) % 4
        self.update_button_style(idx)

    def update_button_style(self, idx):
        color_hex = self.colors[self.grid_state[idx]][0]
        self.buttons[idx].setStyleSheet(f"background-color: {color_hex}; border: 1px solid #222;")

    def clear_grid(self):
        for i in range(64):
            self.grid_state[i] = 0
            self.update_button_style(i)

    def save_current_pattern(self):
        PatternDialog.last_saved_state = list(self.grid_state)
        self.btn_load_saved.setEnabled(True)
        self.btn_load_saved.setStyleSheet("background-color: #009688; color: white; border-radius: 4px; font-size: 11px;")

    def load_saved_pattern(self):
        if PatternDialog.last_saved_state is not None:
            self.grid_state = list(PatternDialog.last_saved_state)
            for i in range(64):
                self.update_button_style(i)

    def accept_pattern(self):
        result = "".join([self.colors[state][1] for state in self.grid_state])
        self.pattern_string = result
        self.accept()

# --- WORKER THREAD FOR COMMANDS (Port 8889) ---
class TelloWorker(QThread):
    response_received = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.tello_address = ('192.168.10.1', 8889)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(('', 9000)) 
        except Exception as e:
            print(f"Command bind error: {e}")
        self.sock.settimeout(3.0)
        self.current_command = None

    def run(self):
        if self.current_command:
            try:
                self.sock.sendto(self.current_command.encode('utf-8'), self.tello_address)
                response, _ = self.sock.recvfrom(1024)
                self.response_received.emit(response.decode('utf-8'))
            except Exception as e:
                self.response_received.emit(f"Error: {str(e)}")
            finally:
                self.current_command = None

    def send(self, command):
        if not self.isRunning():
            self.current_command = command
            self.start()

# --- STATUS THREAD (Port 8890) ---
class TelloStatusThread(QThread):
    status_updated = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.running = True
        try:
            self.sock.bind(('', 8890))
        except Exception as e:
            print(f"Status bind error: {e}")

    def run(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(1024)
                status_str = data.decode('utf-8')
                stats = {}
                items = status_str.strip().split(';')
                for item in items:
                    if ':' in item:
                        key, val = item.split(':')
                        stats[key] = val
                self.status_updated.emit(stats)
            except Exception:
                pass

    def stop(self):
        self.running = False
        self.sock.close()

class TelloFullPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = TelloWorker()
        self.worker.response_received.connect(self.handle_response)
        
        self.status_thread = TelloStatusThread()
        self.status_thread.status_updated.connect(self.handle_status_update)
        self.status_thread.start()

        # Initialize Video Thread
        self.video_thread = TelloVideoThread()
        self.video_thread.frame_received.connect(self.update_video_frame)

        self.initUI()
        self.send_cmd('command')
        # Start Video Stream on initialization
        self.send_cmd('streamon')
        self.video_thread.start()
        
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def handle_response(self, text):
        self.terminal_display.setText(f" > {text}")
        self.setWindowTitle(f"Tello - Status: {text}")

    def handle_status_update(self, stats):
        if 'bat' in stats: self.update_stat('bat', stats['bat'])
        if 'templ' in stats and 'temph' in stats:
            avg_temp = (int(stats['templ']) + int(stats['temph'])) // 2
            self.update_stat('temp', str(avg_temp))

    def update_stat(self, stat_type, value):
        if stat_type == 'bat': self.lbl_bat.setText(f"🔋 {value}%")
        elif stat_type == 'temp': self.lbl_temp.setText(f"🌡️ {value}°C")
        elif stat_type == 'speed': self.lbl_speed.setText(f"⚡ {value}")

    def update_video_frame(self, q_img):
        # Scale the image to fit the label while maintaining aspect ratio
        pixmap = QPixmap.fromImage(q_img)
        scaled_pixmap = pixmap.scaled(self.video_display.size(), 
                                      Qt.AspectRatioMode.KeepAspectRatio, 
                                      Qt.TransformationMode.SmoothTransformation)
        self.video_display.setPixmap(scaled_pixmap)

    def send_cmd(self, cmd):
        self.worker.send(cmd)
        if cmd.startswith("speed"):
            val = cmd.split(" ")[1]
            self.update_stat('speed', val)

    def open_pattern_designer(self):
        dialog = PatternDialog(self)
        if dialog.exec():
            pattern_cmd = f"EXT mled g {dialog.pattern_string}"
            self.send_cmd(pattern_cmd)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if isinstance(self.focusWidget(), QLineEdit):
            super().keyPressEvent(event)
            return

        commands = {
            Qt.Key.Key_Space: 'takeoff',
            Qt.Key.Key_L: 'land',
            Qt.Key.Key_0: 'emergency',
            Qt.Key.Key_Up: 'forward 50',
            Qt.Key.Key_Down: 'back 50',
            Qt.Key.Key_Left: 'left 50',
            Qt.Key.Key_Right: 'right 50',
            Qt.Key.Key_W: 'up 50',
            Qt.Key.Key_S: 'down 50',
            Qt.Key.Key_A: 'ccw 90',
            Qt.Key.Key_D: 'cw 90'
        }

        if key in commands:
            self.send_cmd(commands[key])
        else:
            super().keyPressEvent(event)

    def initUI(self):
        self.setWindowTitle('Tello Command Center')
        self.setMinimumWidth(1200)
        self.setMinimumHeight(800)
        
        self.setStyleSheet("""
            QWidget { background-color: #1a2a44; }
            QPushButton { 
                background-color: #e0e0e0; 
                border: 1px solid #999; 
                font-weight: bold; 
                min-height: 45px; 
                border-radius: 4px; 
                color: #333; 
                font-size: 13px;
                padding: 4px;
            }
            QPushButton:pressed { background-color: #bbbbbb; }
            QLineEdit { background-color: white; border-radius: 2px; padding: 5px; color: black; font-weight: bold; min-height: 35px; }
            QCheckBox { color: white; font-weight: bold; padding: 5px; border-radius: 4px; }
            QLabel#Terminal { background-color: #000; color: #0f0; font-family: 'Courier New'; font-weight: bold; padding-left: 10px; border: 1px solid #334466; border-top-left-radius: 4px; border-bottom-left-radius: 4px; border-right: none; }
            QLabel#StatusBar { background-color: #0a1424; color: #fff; font-weight: bold; border: 1px solid #334466; border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
            QLabel#VideoDisplay { background-color: #000; border: 2px solid #334466; border-radius: 4px; }
            QLabel#VisualizerPlaceholder { background-color: #000; border: 1px solid #334466; color: #444; font-size: 14px; font-weight: bold; border-radius: 4px; }
            QSlider::groove:horizontal { border: 1px solid #999; height: 8px; background: white; margin: 2px 0; border-radius: 4px; }
            QSlider::handle:horizontal { background: #334466; border: 1px solid #555; width: 14px; height: 18px; margin: -6px 0; border-radius: 4px; }
        """)

        main_vbox = QVBoxLayout()
        main_vbox.setContentsMargins(15, 15, 15, 15)
        main_vbox.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(0)
        self.terminal_display = QLabel(" > Initializing Video Stream...")
        self.terminal_display.setObjectName("Terminal")
        header_layout.addWidget(self.terminal_display, 1)

        self.status_bar = QFrame()
        self.status_bar.setObjectName("StatusBar")
        status_inner_layout = QHBoxLayout(self.status_bar)
        status_inner_layout.setContentsMargins(15, 0, 15, 0)
        status_inner_layout.setSpacing(20)
        self.lbl_bat = QLabel("🔋 --%")
        self.lbl_temp = QLabel("🌡️ --°C")
        self.lbl_speed = QLabel("⚡ --")
        for lbl in [self.lbl_bat, self.lbl_temp, self.lbl_speed]:
            lbl.setStyleSheet("color: #00d4ff; font-size: 13px;")
            status_inner_layout.addWidget(lbl)
        header_layout.addWidget(self.status_bar)

        header_container = QWidget()
        header_container.setFixedHeight(45)
        header_container.setLayout(header_layout)
        main_vbox.addWidget(header_container)

        # Middle (Video & Grid 1)
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(15)

        self.video_display = QLabel()
        self.video_display.setObjectName("VideoDisplay")
        self.video_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        middle_layout.addWidget(self.video_display, 6) 

        panel1_container = QFrame()
        panel1_layout = QGridLayout(panel1_container)
        panel1_layout.setContentsMargins(0, 0, 0, 0)
        panel1_layout.setSpacing(5)
        self.setup_grid_columns(panel1_layout, 3)
        
        btn_move_data = [
            ('🚁 Takeoff (Space)', 0, 0, 'takeoff'), ('⬆️ Forward', 0, 1, 'forward 50'), ('🅿️ Land (L)', 0, 2, 'land'),
            ('⬅️ Left', 1, 0, 'left 50'), ('🚦 CMD', 1, 1, 'command'), ('➡️ Right', 1, 2, 'right 50'),
            ('👆 Up (W)', 2, 0, 'up 50'), ('⬇️ Back', 2, 1, 'back 50'), ('👇 Down (S)', 2, 2, 'down 50'),
            ('🔄 CCW (A)', 3, 0, 'ccw 90'), ('🔄 CW (D)', 3, 2, 'cw 90')
        ]
        for label, row, col, cmd in btn_move_data:
            btn = self.create_expanding_btn(label)
            btn.clicked.connect(lambda checked, c=cmd: self.send_cmd(c))
            panel1_layout.addWidget(btn, row, col)

        emergency_ml_stack = QWidget()
        stack_layout = QVBoxLayout(emergency_ml_stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.setSpacing(5)
        
        btn_emergency = self.create_expanding_btn('🚨 EMERGENCY')
        btn_emergency.setStyleSheet("background-color: #d32f2f; color: white; min-height: 20px; font-size: 11px;")
        btn_emergency.clicked.connect(lambda: self.send_cmd('emergency'))
        
        btn_ml = self.create_expanding_btn('Start ML')
        btn_ml.setStyleSheet("background-color: #455a64; color: white; min-height: 20px; font-size: 11px;")
        
        stack_layout.addWidget(btn_emergency)
        stack_layout.addWidget(btn_ml)
        panel1_layout.addWidget(emergency_ml_stack, 3, 1)
            
        middle_layout.addWidget(panel1_container, 4)
        main_vbox.addLayout(middle_layout, 6)

        main_vbox.addWidget(self.create_separator())

        # Bottom (Grid 2, Visualizer, Grid 3)
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(15)

        panel3_container = QFrame()
        panel3_layout = QGridLayout(panel3_container)
        panel3_layout.setContentsMargins(0, 0, 0, 0)
        panel3_layout.setSpacing(5)
        self.setup_grid_columns(panel3_layout, 3)
        
        led_btns = [
            ('🔴 Red', 0, 0, 'led 255 0 0'), ('🟢 Green', 0, 1, 'led 0 255 0'), ('🔵 Blue', 0, 2, 'led 0 0 255'),
            ('🔵 Pulse Blue', 1, 0, 'led 0 0 255 2'), ('⚫ Off', 1, 1, 'led 0 0 0'), ('🚔 POLICE!', 1, 2, 'led 255 0 0 5')
        ]
        for l, r, c, cmd in led_btns:
            btn = self.create_expanding_btn(l)
            btn.clicked.connect(lambda checked, cmd=cmd: self.send_cmd(cmd))
            panel3_layout.addWidget(btn, r, c)

        text_input_container = QWidget()
        text_input_lay = QHBoxLayout(text_input_container)
        text_input_lay.setContentsMargins(0, 0, 0, 0)
        text_input_lay.setSpacing(2)
        self.input_text = QLineEdit("Hello")
        self.input_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn_text_send = QPushButton("Send Text")
        btn_text_send.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn_text_send.clicked.connect(lambda: self.send_cmd(f"EXT mled l b 1 {self.input_text.text()}"))
        text_input_lay.addWidget(self.input_text, 6)
        text_input_lay.addWidget(btn_text_send, 4)

        btn_pattern = QPushButton("Pattern Designer")
        btn_pattern.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn_pattern.setStyleSheet("background-color: #673AB7; color: white;")
        btn_pattern.clicked.connect(self.open_pattern_designer)

        panel3_layout.addWidget(text_input_container, 2, 0, 1, 2)
        panel3_layout.addWidget(btn_pattern, 2, 2)
        bottom_layout.addWidget(panel3_container, 1)

        self.visualizer_placeholder = QLabel("GAMEPAD VISUALIZER\n(Reserved)")
        self.visualizer_placeholder.setObjectName("VisualizerPlaceholder")
        self.visualizer_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.visualizer_placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        bottom_layout.addWidget(self.visualizer_placeholder, 1)

        section2_container = QFrame()
        section2 = QGridLayout(section2_container)
        section2.setContentsMargins(0, 0, 0, 0)
        section2.setSpacing(5)
        self.setup_grid_columns(section2, 3)
        
        motor_stack_widget = QWidget()
        motor_v_lay = QVBoxLayout(motor_stack_widget)
        motor_v_lay.setContentsMargins(0, 0, 0, 0)
        motor_v_lay.setSpacing(5)
        btn_on = self.create_expanding_btn("🥶 Motor ON")
        btn_on.clicked.connect(lambda: self.send_cmd('motoron'))
        btn_off = self.create_expanding_btn("📴 Motor OFF")
        btn_off.clicked.connect(lambda: self.send_cmd('motoroff'))
        motor_v_lay.addWidget(btn_on)
        motor_v_lay.addWidget(btn_off)
        section2.addWidget(motor_stack_widget, 0, 0)

        fwd_flip = self.create_expanding_btn("⬆️ Flip fwd")
        fwd_flip.clicked.connect(lambda: self.send_cmd('flip f'))
        section2.addWidget(fwd_flip, 0, 1)
        
        btn_photo = self.create_expanding_btn("📸 Take photo")
        btn_photo.clicked.connect(lambda: self.send_cmd('takephoto'))
        section2.addWidget(btn_photo, 0, 2)

        flips_row1 = [
            ("⬅️ Flip L", 1, 0, 'flip l'), 
            ("🏈 ThrowFly", 1, 1, 'throwfly'), 
            ("➡️ Flip R", 1, 2, 'flip r')
        ]
        for lbl, r, c, cmd in flips_row1:
            btn = self.create_expanding_btn(lbl)
            btn.clicked.connect(lambda checked, cmd=cmd: self.send_cmd(cmd))
            section2.addWidget(btn, r, c)
            
        section2.addWidget(QCheckBox("Joystick"), 2, 0)
        back_flip = self.create_expanding_btn("⬇️ Flip back")
        back_flip.clicked.connect(lambda: self.send_cmd('flip b'))
        section2.addWidget(back_flip, 2, 1)
        
        speed_container = QFrame()
        speed_layout = QVBoxLayout(speed_container)
        speed_layout.setContentsMargins(5, 0, 5, 0)
        speed_layout.setSpacing(2)
        speed_label = QLabel("Set Speed:")
        speed_label.setStyleSheet("color: white; font-weight: bold; font-size: 10px;")
        speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        speed_slider = QSlider(Qt.Orientation.Horizontal)
        speed_slider.setRange(10, 100)
        speed_slider.valueChanged.connect(lambda val: self.send_cmd(f'speed {val}'))
        speed_layout.addWidget(speed_label)
        speed_layout.addWidget(speed_slider)
        section2.addWidget(speed_container, 2, 2)

        bottom_layout.addWidget(section2_container, 1)
        main_vbox.addLayout(bottom_layout, 4)
        self.setLayout(main_vbox)

    def setup_grid_columns(self, grid, count=3):
        for i in range(count):
            grid.setColumnStretch(i, 1)

    def create_expanding_btn(self, label):
        btn = QPushButton(label)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    def create_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #334466; max-height: 1px; border: none;")
        return line

    def closeEvent(self, event):
        self.status_thread.stop()
        self.video_thread.stop()
        self.status_thread.wait()
        self.video_thread.wait()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = TelloFullPanel()
    window.show()
    sys.exit(app.exec())