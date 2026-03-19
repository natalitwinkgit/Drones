import sys
import socket
from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QGridLayout, 
                             QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox, 
                             QSlider, QFrame, QLabel, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# --- WORKER THREAD FOR TELLO COMMUNICATION ---
class TelloWorker(QThread):
    response_received = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.tello_address = ('192.168.10.1', 8889)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(('', 9000)) # Local port for receiving responses
        except Exception as e:
            print(f"Bind error: {e}")
        self.sock.settimeout(3.0)
        self.current_command = None

    def run(self):
        """This runs in a background thread"""
        if self.current_command:
            try:
                print(f"Sending: {self.current_command}")
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

class TelloFullPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = TelloWorker()
        self.worker.response_received.connect(self.handle_response)
        self.initUI()
        
        # Send SDK command on launch
        self.send_cmd('command')

    def handle_response(self, text):
        print(f"Tello says: {text}")
        self.terminal_display.setText(f" > {text}")
        self.setWindowTitle(f"Tello - Status: {text}")

    def send_cmd(self, cmd):
        """Helper to call worker from UI"""
        self.worker.send(cmd)

    def initUI(self):
        self.setWindowTitle('Tello Command Center')
        self.setMinimumWidth(800)
        
        self.setStyleSheet("""
            QWidget { background-color: #1a2a44; }
            QPushButton { background-color: #e0e0e0; border: 1px solid #999; font-weight: bold; min-height: 50px; border-radius: 4px; color: #333; font-size: 14px; }
            QPushButton:pressed { background-color: #bbbbbb; }
            QLineEdit { background-color: white; border-radius: 2px; padding: 5px; color: black; font-weight: bold; min-height: 40px; }
            QCheckBox { color: black; font-weight: bold; background-color: white; padding: 5px; border-radius: 4px; min-height: 50px; }
            QLabel#Terminal { background-color: #000; color: #0f0; font-family: 'Courier New'; font-weight: bold; padding-left: 10px; border-radius: 4px; border: 1px solid #334466; }
            QSlider::groove:horizontal { border: 1px solid #999; height: 8px; background: white; margin: 2px 0; border-radius: 4px; }
            QSlider::handle:horizontal { background: #334466; border: 1px solid #555; width: 14px; height: 18px; margin: -6px 0; border-radius: 4px; }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- TERMINAL RESPONSE ---
        self.terminal_display = QLabel(" > Initializing...")
        self.terminal_display.setObjectName("Terminal")
        self.terminal_display.setFixedHeight(40)
        main_layout.addWidget(self.terminal_display)

        # --- SECTION 1: FLIGHT CONTROLS ---
        section1 = QGridLayout()
        self.setup_grid_columns(section1, 3)
        
        btn_data1 = [
            ('🚁 Takeoff 🚁', 0, 0, 'takeoff'), ('⬆️ Forward ⬆️', 0, 1, 'forward 50'), ('🅿️ Land 🅿️', 0, 2, 'land'),
            ('⬅️ Left ⬅️', 1, 0, 'left 50'), ('🚦 Command 🚦', 1, 1, 'command'), ('➡️ Right ➡️', 1, 2, 'right 50'),
            ('👆 Up 👆', 2, 0, 'up 50'), ('⬇️ Back ⬇️', 2, 1, 'back 50'), ('👇 Down 👇', 2, 2, 'down 50'),
            ('🔄 Rotate ccw 🔄', 3, 0, 'ccw 90'), ('🔄 Rotate cw 🔄', 3, 2, 'cw 90')
        ]
        
        for label, row, col, cmd in btn_data1:
            btn = self.create_expanding_btn(label)
            btn.clicked.connect(lambda checked, c=cmd: self.send_cmd(c))
            section1.addWidget(btn, row, col)

        emergency_ml_container = QWidget()
        em_layout = QHBoxLayout(emergency_ml_container)
        em_layout.setContentsMargins(0, 0, 0, 0)
        btn_emergency = QPushButton('🚨 EMERGENCY 🚨')
        btn_emergency.clicked.connect(lambda: self.send_cmd('emergency'))
        btn_ml = QPushButton('Start ML Model')
        em_layout.addWidget(btn_emergency)
        em_layout.addWidget(btn_ml)
        section1.addWidget(emergency_ml_container, 3, 1)

        main_layout.addLayout(section1)
        main_layout.addWidget(self.create_separator())

        # --- SECTION 2: ACROBATICS & MOTORS ---
        section2 = QGridLayout()
        self.setup_grid_columns(section2, 3)
        
        motor_container = QWidget()
        motor_lay = QHBoxLayout(motor_container)
        motor_lay.setContentsMargins(0, 0, 0, 0)
        btn_on = self.create_expanding_btn("🥶 Motor ON 🥶")
        btn_on.clicked.connect(lambda: self.send_cmd('motoron'))
        btn_off = self.create_expanding_btn("📴 Motor OFF 📴")
        btn_off.clicked.connect(lambda: self.send_cmd('motoroff'))
        motor_lay.addWidget(btn_on)
        motor_lay.addWidget(btn_off)
        section2.addWidget(motor_container, 0, 0)

        fwd_flip = self.create_expanding_btn("⬆️ Flip forward ⬆️")
        fwd_flip.clicked.connect(lambda: self.send_cmd('flip f'))
        section2.addWidget(fwd_flip, 0, 1)
        section2.addWidget(QCheckBox("Enter joysticks control"), 0, 2)

        flips = [("⬅️ Flip left ⬅️", 1, 0, 'flip l'), ("🏈 Throw&Fly 🏈", 1, 1, 'throwfly'), ("➡️ Flip right ➡️", 1, 2, 'flip r'),
                 ("📸 Take photo 📸", 2, 0, 'takephoto'), ("⬇️ Flip back ⬇️", 2, 1, 'flip b')]
        
        for lbl, r, c, cmd in flips:
            btn = self.create_expanding_btn(lbl)
            btn.clicked.connect(lambda checked, cmd=cmd: self.send_cmd(cmd))
            section2.addWidget(btn, r, c)
        
        speed_container = QFrame()
        speed_layout = QHBoxLayout(speed_container)
        speed_slider = QSlider(Qt.Orientation.Horizontal)
        speed_slider.setRange(10, 100)
        speed_slider.valueChanged.connect(lambda val: self.send_cmd(f'speed {val}'))
        speed_layout.addWidget(QLabel("Speed:"))
        speed_layout.addWidget(speed_slider)
        section2.addWidget(speed_container, 2, 2)

        main_layout.addLayout(section2)
        main_layout.addWidget(self.create_separator())

        # --- SECTION 3: LED & TEXT INPUTS ---
        section3 = QGridLayout()
        self.setup_grid_columns(section3, 3)
        
        led_data = [
            ('🔴 Red LED 🔴', 0, 0, 'EXT led 255 0 0'), 
            ('🟢 Green LED 🟢', 0, 1, 'EXT led 0 255 0'), 
            ('🔵 Blue LED 🔵', 0, 2, 'EXT led 0 0 255'),
            ('🔵 Pulse Blue 🔵', 1, 0, 'EXT led br 1 0 0 255'), 
            ('⚫ Turn OFF LED ⚫', 1, 1, 'EXT led 0 0 0'), 
            ('🚔 POLICE! 🚔', 1, 2, 'EXT led bl 5 0 0 255 255 0 0') # Red flashing
        ]
        
        for label, row, col, cmd in led_data:
            btn = self.create_expanding_btn(label)
            btn.clicked.connect(lambda checked, c=cmd: self.send_cmd(c))
            section3.addWidget(btn, row, col)

        # Text Input Group
        text_display_container = QWidget()
        text_display_layout = QHBoxLayout(text_display_container)
        text_display_layout.setContentsMargins(0, 0, 0, 0)
        self.input_text = QLineEdit("Mykola")
        btn_text = QPushButton("Display text")
        btn_text.clicked.connect(lambda: self.send_cmd(f"EXT mled l b 1 {self.input_text.text()}"))
        text_display_layout.addWidget(self.input_text, 2)
        text_display_layout.addWidget(btn_text, 3)
        section3.addWidget(text_display_container, 2, 0)
        
        section3.addWidget(self.create_expanding_btn("Display pattern"), 2, 1)
        
        # Char Input Group
        char_input_container = QWidget()
        char_input_layout = QHBoxLayout(char_input_container)
        char_input_layout.setContentsMargins(0, 0, 0, 0)
        self.input_char = QLineEdit("M")
        btn_char = QPushButton("Display char")
        btn_char.clicked.connect(lambda: self.send_cmd(f"EXT mled s p {self.input_char.text()}"))
        char_input_layout.addWidget(self.input_char, 1)
        char_input_layout.addWidget(btn_char, 2)
        section3.addWidget(char_input_container, 2, 2)

        main_layout.addLayout(section3)
        self.setLayout(main_layout)

    def setup_grid_columns(self, grid, count=3):
        for i in range(count):
            grid.setColumnStretch(i, 1)

    def create_expanding_btn(self, label):
        btn = QPushButton(label)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return btn

    def create_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #334466; max-height: 2px; border: none;")
        return line

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = TelloFullPanel()
    window.show()
    sys.exit(app.exec())