from PyQt6.QtWidgets import (QWidget, QPushButton, QGridLayout, QVBoxLayout,
                             QHBoxLayout, QLineEdit, QSlider, QFrame, QLabel,
                             QSizePolicy, QDialog, QCheckBox, QComboBox)
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QTimer, QRectF


class StickVisualizer(QWidget):
    def __init__(self, label="Stick"):
        super().__init__()
        self.setFixedSize(100, 100)
        self.label = label
        self.pos_x = 0.0
        self.pos_y = 0.0

    def update_pos(self, x, y):
        self.pos_x = x
        self.pos_y = y
        self.repaint()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#334466"), 2))
        p.setBrush(QColor("#0a1424"))
        p.drawRoundedRect(5, 5, 90, 90, 5, 5)
        p.setPen(QPen(QColor("#223344"), 1))
        p.drawLine(50, 10, 50, 90)
        p.drawLine(10, 50, 90, 50)
        ix, iy = int(50 + (self.pos_x * 35)), int(50 + (self.pos_y * 35))
        p.setPen(QPen(QColor("#00d4ff"), 3))
        p.drawLine(ix - 5, iy, ix + 5, iy)
        p.drawLine(ix, iy - 5, ix, iy + 5)
        p.setPen(QColor("#ffffff"))
        p.drawText(10, 95, self.label)


class PatternDialog(QDialog):
    last_saved_state = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("8x8 LED Pattern Designer")
        self.setFixedSize(420, 560)
        self.pattern_string = ""
        self.colors = {0: ("#444", "0"), 1: ("#ff0000", "r"), 2: ("#0000ff", "b"), 3: ("#800080", "p")}
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
        self.btn_load_saved.setStyleSheet(
            "background-color: #009688; color: white; border-radius: 4px; font-size: 11px;")
        self.btn_load_saved.clicked.connect(self.load_saved_pattern)
        if PatternDialog.last_saved_state is None:
            self.btn_load_saved.setEnabled(False)
        header_layout.addWidget(info_label, 1)
        header_layout.addWidget(self.btn_load_saved)
        layout.addLayout(header_layout)
        grid_widget = QWidget()
        grid_lay = QGridLayout(grid_widget)
        grid_lay.setSpacing(2)
        for i in range(64):
            btn = QPushButton()
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(f"background-color: {self.colors[0][0]}; border: 1px solid #222;")
            btn.clicked.connect(lambda checked, idx=i: self.cycle_color(idx))
            grid_lay.addWidget(btn, i // 8, i % 8)
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
        self.buttons[idx].setStyleSheet(
            f"background-color: {self.colors[self.grid_state[idx]][0]}; border: 1px solid #222;")

    def clear_grid(self):
        for i in range(64):
            self.grid_state[i] = 0
            self.update_button_style(i)

    def save_current_pattern(self):
        PatternDialog.last_saved_state = list(self.grid_state)
        self.btn_load_saved.setEnabled(True)

    def load_saved_pattern(self):
        if PatternDialog.last_saved_state:
            self.grid_state = list(PatternDialog.last_saved_state)
            [self.update_button_style(i) for i in range(64)]

    def accept_pattern(self):
        self.pattern_string = "".join([self.colors[s][1] for s in self.grid_state])
        self.accept()


class MLOverlayWidget(QWidget):
    """
    Transparent widget that floats on top of the video QLabel.
    Draws ML predictions using QPainter — crisp, resolution-independent,
    never touches the video frames themselves.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._results: list = []    # list of (class_name, confidence)

    def update_results(self, results: list) -> None:
        self._results = results
        self.update()   # schedules a repaint

    def paintEvent(self, event):
        if not self._results:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        font = QFont("Helvetica Neue", 13, QFont.Weight.Bold)
        p.setFont(font)
        fm = QFontMetrics(font)

        pad_x = 14
        pad_y = 10
        line_gap = 6
        line_h = fm.height() + line_gap

        # Measure the widest label to size the box
        max_w = max(fm.horizontalAdvance(f"{n}  {c * 100:.1f}%") for n, c in self._results)
        box_w = max_w + pad_x * 2
        box_h = pad_y * 2 + line_h * len(self._results) - line_gap

        margin = 12
        x = self.width() - box_w - margin
        y = self.height() - box_h - margin

        # Background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(QRectF(x, y, box_w, box_h), 8, 8)

        # Border
        p.setPen(QPen(QColor(0, 212, 255, 200), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x, y, box_w, box_h), 8, 8)

        # Labels
        for i, (name, conf) in enumerate(self._results):
            text = f"{name}  {conf * 100:.1f}%"
            ty = y + pad_y + line_h * i + fm.ascent()
            color = QColor(0, 255, 120) if i == 0 else QColor(180, 180, 180)
            p.setPen(color)
            p.drawText(int(x + pad_x), int(ty), text)


class TelloFullPanel(QWidget):
    def __init__(self, worker, status_thread, video_thread, gamepad, ml_worker=None):
        super().__init__()
        self.worker = worker
        self.status_thread = status_thread
        self.video_thread = video_thread
        self.gp_worker = gamepad
        self.ml_worker = ml_worker

        self.video_thread.status_message.connect(self.handle_video_status)
        self.video_thread.recording_state_changed.connect(self.handle_recording_state)
        self.video_thread.snapshot_saved.connect(self.handle_snapshot_saved)

        self.initUI()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def initUI(self):
        self.setWindowTitle('Tello Command Center')
        self.setMinimumWidth(1200)
        self.setMinimumHeight(800)

        self.setStyleSheet("""
            QWidget { background-color: #1a2a44; border: none; }
            QPushButton { background-color: #e0e0e0; border: 1px solid #999; font-weight: bold; min-height: 40px; border-radius: 4px; color: #333; font-size: 12px; padding: 4px; }
            QPushButton:pressed { background-color: #bbbbbb; }
            QLineEdit { background-color: white; border-radius: 4px; padding: 5px; color: black; font-weight: bold; min-height: 35px; }
            QComboBox { background-color: #0a1424; border: 1px solid #334466; border-radius: 4px; padding: 6px 10px; color: white; min-height: 36px; font-weight: bold; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView { background-color: #0a1424; color: white; selection-background-color: #00d4ff; selection-color: #0a1424; }
            QLabel#Terminal { background-color: #000; color: #0f0; font-family: 'Courier New'; font-weight: bold; padding-left: 15px; border-right: 2px solid #334466; }
            QFrame#HeaderBar { background-color: #000; border: 2px solid #334466; border-radius: 6px; }
            QLabel#StatLabel { color: #00d4ff; font-size: 12px; font-weight: bold; background: transparent; }
            QLabel#VideoDisplay { background-color: #000; border: 2px solid #334466; border-radius: 4px; color: #555; font-size: 18px; font-weight: bold; }
            QSlider::groove:horizontal { border: 1px solid #334466; height: 8px; background: #0a1424; border-radius: 4px; }
            QSlider::handle:horizontal { background: #00d4ff; border: 1px solid #00d4ff; width: 18px; margin: -5px 0; border-radius: 9px; }
        """)

        main_vbox = QVBoxLayout()
        main_vbox.setContentsMargins(15, 15, 15, 15)
        main_vbox.setSpacing(15)

        # Header
        self.header_frame = QFrame()
        self.header_frame.setObjectName("HeaderBar")
        self.header_frame.setFixedHeight(60)
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 15, 0)
        header_layout.setSpacing(15)
        self.terminal_display = QLabel(" > READY FOR COMMANDS")
        if self.video_thread.demo_mode:
            self.terminal_display.setText(" > DEMO MODE READY")
        self.terminal_display.setObjectName("Terminal")
        header_layout.addWidget(self.terminal_display, 1)
        self.lbl_bat = QLabel("🔋 --%")
        self.lbl_bat.setObjectName("StatLabel")
        self.lbl_temp = QLabel("🌡️ --°C")
        self.lbl_temp.setObjectName("StatLabel")
        self.lbl_speed = QLabel("⚡ --")
        self.lbl_speed.setObjectName("StatLabel")
        self.lbl_vid_status = QLabel("📺 VIDEO: OFF")
        self.lbl_vid_status.setStyleSheet(
            "color: #f44336; font-size: 11px; font-weight: bold; background: transparent;")
        self.lbl_filter_status = QLabel("🎛️ NORMAL")
        self.lbl_filter_status.setObjectName("StatLabel")
        self.lbl_rec_status = QLabel("⏺ REC OFF")
        self.lbl_rec_status.setStyleSheet(
            "color: #f44336; font-size: 11px; font-weight: bold; background: transparent;")
        header_layout.addWidget(self.lbl_bat)
        header_layout.addWidget(self.lbl_temp)
        header_layout.addWidget(self.lbl_speed)
        header_layout.addWidget(self.lbl_filter_status)
        header_layout.addWidget(self.lbl_rec_status)
        header_layout.addWidget(self.lbl_vid_status)
        main_vbox.addWidget(self.header_frame)

        # Middle Layout (Video + Main Controls)
        mid_layout = QHBoxLayout()
        mid_layout.setSpacing(15)
        self.video_display = QLabel("VIDEO OFF")
        self.video_display.setObjectName("VideoDisplay")
        self.video_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Transparent overlay for ML labels — floats on top of video_display
        self.ml_overlay = MLOverlayWidget(self.video_display)
        self.ml_overlay.hide()

        mid_layout.addWidget(self.video_display, 7)

        m_pnl = QFrame()
        m_lay = QGridLayout(m_pnl)
        m_lay.setContentsMargins(0, 0, 0, 0)
        m_lay.setSpacing(6)
        m_data = [
            ('🚁 Takeoff', 0, 0, 'takeoff'), ('⬆️ Forward', 0, 1, 'forward 50'), ('🅿️ Land', 0, 2, 'land'),
            ('⬅️ Left', 1, 0, 'left 50'), ('🚦 CMD', 1, 1, 'command'), ('➡️ Right', 1, 2, 'right 50'),
            ('👆 Up', 2, 0, 'up 50'), ('⬇️ Back', 2, 1, 'back 50'), ('👇 Down', 2, 2, 'down 50'),
            ('🔄 CCW', 3, 0, 'ccw 90'), ('🔄 CW', 3, 2, 'cw 90')
        ]
        for l, r, c, cmd in m_data:
            btn = self.create_btn(l)
            btn.clicked.connect(lambda chk, x=cmd: self.send_cmd(x))
            m_lay.addWidget(btn, r, c)

        stack_layout = QVBoxLayout()
        stack_layout.setSpacing(4)
        em = self.create_btn('🚨 EMERGENCY')
        em.setStyleSheet("background-color: #d32f2f; color: white; min-height: 35px; border: none;")
        em.clicked.connect(lambda: self.send_cmd('emergency'))

        self.btn_ml = self.create_btn('🤖 ML: OFF')
        self.btn_ml.clicked.connect(self.toggle_ml)
        self.btn_ml.setStyleSheet("background-color: #455a64; color: white; min-height: 35px; border: none;")
        if self.ml_worker is None:
            self.btn_ml.setText("🤖 ML: N/A")
            self.btn_ml.setEnabled(False)

        stack_layout.addWidget(em)
        stack_layout.addWidget(self.btn_ml)
        m_lay.addLayout(stack_layout, 3, 1)

        stream_tools = QFrame()
        stream_tools_lay = QVBoxLayout(stream_tools)
        stream_tools_lay.setContentsMargins(0, 6, 0, 0)
        stream_tools_lay.setSpacing(6)

        filter_row = QHBoxLayout()
        filter_lbl = QLabel("VIDEO FILTER")
        filter_lbl.setStyleSheet("color: #00d4ff; font-size: 10px; font-weight: bold;")
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Normal", "normal")
        self.filter_combo.addItem("Gray", "gray")
        self.filter_combo.addItem("Edges", "edges")
        self.filter_combo.addItem("Night Vision", "night")
        self.filter_combo.currentIndexChanged.connect(self.on_filter_changed)
        filter_row.addWidget(filter_lbl)
        filter_row.addStretch()
        filter_row.addWidget(self.filter_combo)
        stream_tools_lay.addLayout(filter_row)

        record_row = QHBoxLayout()
        self.btn_record = self.create_btn("⏺ Start REC")
        self.btn_record.setStyleSheet("background-color: #b71c1c; color: white; min-height: 35px; border: none;")
        self.btn_record.clicked.connect(self.toggle_recording)
        self.btn_snapshot = self.create_btn("📷 Snapshot")
        self.btn_snapshot.setStyleSheet("background-color: #1565c0; color: white; min-height: 35px; border: none;")
        self.btn_snapshot.clicked.connect(self.take_snapshot)
        record_row.addWidget(self.btn_record)
        record_row.addWidget(self.btn_snapshot)
        stream_tools_lay.addLayout(record_row)
        m_lay.addWidget(stream_tools, 4, 0, 1, 3)
        mid_layout.addWidget(m_pnl, 3)
        main_vbox.addLayout(mid_layout, 6)

        # Bottom Panels
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(15)

        # Panel 1: LED
        l_pnl = QFrame()
        l_lay = QGridLayout(l_pnl)
        l_lay.setContentsMargins(0, 0, 0, 0)
        l_lay.setSpacing(5)
        leds = [('🔴 Red', 0, 0, 'led 255 0 0'), ('🟢 Green', 0, 1, 'led 0 255 0'), ('🔵 Blue', 0, 2, 'led 0 0 255'),
                ('🔵 Pulse', 1, 0, 'led 0 0 255 2'), ('⚫ Off', 1, 1, 'led 0 0 0'), ('🚔 POLICE', 1, 2, 'led 255 0 0 5')]
        for l, r, c, cmd in leds:
            btn = self.create_btn(l)
            btn.clicked.connect(lambda chk, x=cmd: self.send_cmd(x))
            l_lay.addWidget(btn, r, c)
        self.input_text = QLineEdit("Hello")
        btn_text = self.create_btn("Send Text")
        btn_text.clicked.connect(lambda: self.send_cmd(f"EXT mled l b 1 {self.input_text.text()}"))
        l_lay.addWidget(self.input_text, 2, 0, 1, 2)
        l_lay.addWidget(btn_text, 2, 2)
        btn_patt = self.create_btn("Pattern Designer")
        btn_patt.setStyleSheet("background-color: #673AB7; color: white; border: none;")
        btn_patt.clicked.connect(self.open_pattern_designer)
        l_lay.addWidget(btn_patt, 3, 0, 1, 3)
        bottom_layout.addWidget(l_pnl, 1)

        # Panel 2: Speed + Gamepad
        mid_btm_pnl = QFrame()
        mid_btm_lay = QVBoxLayout(mid_btm_pnl)
        mid_btm_lay.setContentsMargins(0, 0, 0, 0)
        mid_btm_lay.setSpacing(10)
        spd_box = QWidget()
        spd_lay = QVBoxLayout(spd_box)
        spd_lay.setContentsMargins(5, 5, 5, 5)
        spd_hdr = QHBoxLayout()
        spd_lbl = QLabel("🚀 SPEED SETTING")
        spd_lbl.setStyleSheet("color: #00d4ff; font-weight: bold; font-size: 10px;")
        self.spd_val_lbl = QLabel("50 cm/s")
        self.spd_val_lbl.setStyleSheet("color: white; font-weight: bold;")
        spd_hdr.addWidget(spd_lbl)
        spd_hdr.addStretch()
        spd_hdr.addWidget(self.spd_val_lbl)
        self.spd_slider = QSlider(Qt.Orientation.Horizontal)
        self.spd_slider.setRange(10, 100)
        self.spd_slider.setValue(50)
        self.spd_slider.valueChanged.connect(self.update_speed_label)
        self.spd_slider.sliderReleased.connect(lambda: self.send_cmd(f"speed {self.spd_slider.value()}"))
        spd_lay.addLayout(spd_hdr)
        spd_lay.addWidget(self.spd_slider)
        mid_btm_lay.addWidget(spd_box)
        vis_box = QWidget()
        vis_lay = QVBoxLayout(vis_box)
        vis_lay.setContentsMargins(5, 0, 5, 5)
        gp_hdr = QHBoxLayout()
        gp_lbl = QLabel("🎮 GAMEPAD")
        gp_lbl.setStyleSheet("color: #00d4ff; font-weight: bold; font-size: 10px;")
        self.gp_chk = QCheckBox("Enable")
        self.gp_chk.stateChanged.connect(self.toggle_gamepad)
        self.gp_chk.setStyleSheet("color: white;")
        gp_hdr.addWidget(gp_lbl)
        gp_hdr.addStretch()
        gp_hdr.addWidget(self.gp_chk)
        vis_lay.addLayout(gp_hdr)
        sticks_lay = QHBoxLayout()
        self.ls = StickVisualizer("L")
        self.rs = StickVisualizer("R")
        sticks_lay.addWidget(self.ls)
        sticks_lay.addWidget(self.rs)
        vis_lay.addLayout(sticks_lay)
        mid_btm_lay.addWidget(vis_box)
        bottom_layout.addWidget(mid_btm_pnl, 1)

        # Panel 3: Extra Controls
        u_pnl = QFrame()
        u_lay = QGridLayout(u_pnl)
        u_lay.setContentsMargins(0, 0, 0, 0)
        u_lay.setSpacing(5)

        motor_stack_widget = QWidget()
        motor_v_lay = QVBoxLayout(motor_stack_widget)
        motor_v_lay.setContentsMargins(0, 0, 0, 0)
        motor_v_lay.setSpacing(5)
        btn_mon = self.create_btn("🥶 Motor ON")
        btn_mon.clicked.connect(lambda: self.send_cmd('motoron'))
        btn_moff = self.create_btn("📴 Motor OFF")
        btn_moff.clicked.connect(lambda: self.send_cmd('motoroff'))
        motor_v_lay.addWidget(btn_mon)
        motor_v_lay.addWidget(btn_moff)
        u_lay.addWidget(motor_stack_widget, 0, 0)

        btn_f_flip = self.create_btn("⬆️ Flip F")
        btn_f_flip.clicked.connect(lambda: self.send_cmd('flip f'))
        u_lay.addWidget(btn_f_flip, 0, 1)
        btn_photo = self.create_btn("📸 Photo")
        btn_photo.clicked.connect(lambda: self.send_cmd('takephoto'))
        u_lay.addWidget(btn_photo, 0, 2)

        flips_mid = [("⬅️ Flip L", 1, 0, 'flip l'), ("🏈 ThrowFly", 1, 1, 'throwfly'), ("➡️ Flip R", 1, 2, 'flip r')]
        for lbl, r, c, cmd in flips_mid:
            btn = self.create_btn(lbl)
            btn.clicked.connect(lambda chk, x=cmd: self.send_cmd(x))
            u_lay.addWidget(btn, r, c)

        btn_vid_on = self.create_btn("📺 Video ON")
        btn_vid_on.setStyleSheet("background-color: #4CAF50; color: white;")
        btn_vid_on.clicked.connect(self.video_on)
        u_lay.addWidget(btn_vid_on, 2, 0)
        btn_b_flip = self.create_btn("⬇️ Flip B")
        btn_b_flip.clicked.connect(lambda: self.send_cmd('flip b'))
        u_lay.addWidget(btn_b_flip, 2, 1)
        btn_vid_off = self.create_btn("📺 Video OFF")
        btn_vid_off.setStyleSheet("background-color: #f44336; color: white;")
        btn_vid_off.clicked.connect(self.video_off)
        u_lay.addWidget(btn_vid_off, 2, 2)

        bottom_layout.addWidget(u_pnl, 1)
        main_vbox.addLayout(bottom_layout, 4)
        self.setLayout(main_vbox)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def create_btn(self, label):
        b = QPushButton(label)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return b

    def handle_response(self, text):
        self.terminal_display.setText(f" > {text.upper()}")

    def send_cmd(self, cmd):
        if self.worker:
            self.worker.send(cmd)
        self.terminal_display.setText(f" > {cmd.upper()}")

    def update_speed_label(self, val):
        self.spd_val_lbl.setText(f"{val} cm/s")

    def handle_status_update(self, stats):
        if 'bat' in stats: self.lbl_bat.setText(f"🔋 {stats['bat']}%")
        if 'templ' in stats: self.lbl_temp.setText(f"🌡️ {stats['templ']}°C")
        if 'speed' in stats: self.lbl_speed.setText(f"⚡ {stats['speed']}")

    def update_video_frame(self, q_img):
        pixmap = QPixmap.fromImage(q_img)
        scaled = pixmap.scaled(self.video_display.size(), Qt.AspectRatioMode.KeepAspectRatio)
        self.video_display.setPixmap(scaled)
        # Keep overlay covering the full video widget
        self.ml_overlay.resize(self.video_display.size())

    def video_on(self):
        if self.video_thread.isRunning():
            self.handle_video_status("Video stream is already running.")
            return
        self.send_cmd('streamon')
        QTimer.singleShot(1000, lambda: self.video_thread.start())
        self.lbl_vid_status.setText("📺 VIDEO: ON")
        self.lbl_vid_status.setStyleSheet("color: #4CAF50; background: transparent;")

    def video_off(self):
        self.video_thread.stop_recording()
        self.send_cmd('streamoff')
        self.video_thread.stop()
        self.video_thread.wait(1500)
        self.video_display.clear()
        self.video_display.setText("VIDEO OFF")
        self.lbl_vid_status.setText("📺 VIDEO: OFF")
        self.lbl_vid_status.setStyleSheet("color: #f44336; background: transparent;")
        self.lbl_rec_status.setText("⏺ REC OFF")
        self.lbl_rec_status.setStyleSheet("color: #f44336; font-size: 11px; font-weight: bold; background: transparent;")

    def open_pattern_designer(self):
        d = PatternDialog(self)
        if d.exec():
            self.send_cmd(f"EXT mled g {d.pattern_string}")

    def toggle_gamepad(self, state):
        if state == 2:
            self.gp_worker.start()
        else:
            self.gp_worker.stop()
            self.ls.update_pos(0, 0)
            self.rs.update_pos(0, 0)

    def update_visualizer_sticks(self, axes):
        if len(axes) == 4:
            self.ls.update_pos(axes[0], axes[1])
            self.rs.update_pos(axes[2], axes[3])

    def toggle_ml(self):
        if self.ml_worker is None:
            return

        self.video_thread.ml_enabled = not self.video_thread.ml_enabled

        if self.video_thread.ml_enabled:
            self.btn_ml.setText("🤖 ML: ON")
            self.btn_ml.setStyleSheet(
                "background-color: #2e7d32; color: white; min-height: 35px; border: none;")
            self.ml_overlay.show()
        else:
            self.btn_ml.setText("🤖 ML: OFF")
            self.btn_ml.setStyleSheet(
                "background-color: #455a64; color: white; min-height: 35px; border: none;")
            self.ml_overlay.update_results([])
            self.ml_overlay.hide()

    def on_filter_changed(self, index):
        filter_mode = self.filter_combo.itemData(index)
        if not filter_mode:
            return
        self.video_thread.set_filter_mode(filter_mode)
        self.lbl_filter_status.setText(f"🎛️ {self.filter_combo.currentText().upper()}")

    def toggle_recording(self):
        if self.video_thread.recording_enabled:
            self.video_thread.stop_recording()
            return
        self.video_thread.start_recording()

    def take_snapshot(self):
        self.video_thread.save_snapshot()

    def handle_video_status(self, text):
        self.terminal_display.setText(f" > {text}")

    def handle_recording_state(self, is_recording, output_path):
        if is_recording:
            self.btn_record.setText("⏹ Stop REC")
            self.btn_record.setStyleSheet("background-color: #e53935; color: white; min-height: 35px; border: none;")
            self.lbl_rec_status.setText("⏺ REC ON")
            self.lbl_rec_status.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold; background: transparent;")
        else:
            self.btn_record.setText("⏺ Start REC")
            self.btn_record.setStyleSheet("background-color: #b71c1c; color: white; min-height: 35px; border: none;")
            self.lbl_rec_status.setText("⏺ REC OFF")
            self.lbl_rec_status.setStyleSheet("color: #f44336; font-size: 11px; font-weight: bold; background: transparent;")

        self.lbl_rec_status.setToolTip(output_path or "")

    def handle_snapshot_saved(self, output_path):
        self.terminal_display.setText(f" > Snapshot saved to {output_path}")

    def keyPressEvent(self, e):
        keys = {Qt.Key.Key_Space: 'takeoff', Qt.Key.Key_L: 'land',
                Qt.Key.Key_Up: 'forward 50', Qt.Key.Key_Down: 'back 50'}
        if e.key() in keys:
            self.send_cmd(keys[e.key()])
