import time
import pygame
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class GamepadWorker(QObject):
    """
    Polls the joystick using a QTimer so all pygame calls happen on the
    main thread — required on macOS (AppKit enforces this strictly).
    Emits the same signals as before so main.py needs no changes.
    """
    command_signal = pyqtSignal(str)
    button_signal = pyqtSignal(str)
    axis_signal = pyqtSignal(list)

    def __init__(self):
        super().__init__()

        self.deadzone = 10  # percentage, out of 100
        self.prev_buttons = {}
        self.last_button_time = 0
        self.button_cooldown = 0.2

        self._timer = QTimer()
        self._timer.setInterval(10)  # 10 ms = 100 Hz
        self._timer.timeout.connect(self._poll)

        if pygame.joystick.get_count() == 0:
            print("❌ No joystick")
            self.joystick = None
        else:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            print("✅ Gamepad:", self.joystick.get_name())

    # ------------------------------------------------------------------
    # Public API — same as before so main.py / ui_panel.py need no edits
    # ------------------------------------------------------------------

    def start(self):
        if self.joystick is None:
            print("❌ Cannot start: no joystick connected")
            return
        print("🎮 Gamepad polling started")
        self._timer.start()

    def stop(self):
        self._timer.stop()
        print("🎮 Gamepad polling stopped")

    # QThread compat shim — kept in case anything calls it
    def wait(self):
        pass

    # ------------------------------------------------------------------
    # Internal poll — runs on the main thread via QTimer
    # ------------------------------------------------------------------

    def _dz(self, v):
        return 0 if abs(v) < self.deadzone else v

    def _poll(self):
        if self.joystick is None:
            return

        try:
            # Must be called from the main thread — now it is.
            pygame.event.pump()

            # Read and scale axes to -100..100
            lx_raw = int(self.joystick.get_axis(0) * 100)   # yaw
            ly_raw = int(-self.joystick.get_axis(1) * 100)  # throttle (invert Y)
            rx_raw = int(self.joystick.get_axis(2) * 100)   # roll
            ry_raw = int(-self.joystick.get_axis(3) * 100)  # pitch (invert Y)

            lx = self._dz(lx_raw)   # yaw
            ly = self._dz(ly_raw)   # throttle
            rx = self._dz(rx_raw)   # roll
            ry = self._dz(ry_raw)   # pitch

            # UI stick visualizer (flip Y so up=up on screen)
            self.axis_signal.emit([lx / 100, -ly / 100, rx / 100, -ry / 100])

            # Tello SDK: rc <roll> <pitch> <throttle> <yaw>
            self.command_signal.emit(f"rc {rx} {ry} {ly} {lx}")

            # Buttons
            buttons = {
                "A": self.joystick.get_button(0),
                "X": self.joystick.get_button(2),
                "Y": self.joystick.get_button(3),
            }

            now = time.time()
            for name, state in buttons.items():
                prev = self.prev_buttons.get(name, 0)
                if state == 1 and prev == 0 and (now - self.last_button_time > self.button_cooldown):
                    print(f"🎮 {name}")
                    if name == "A":
                        self.button_signal.emit("takeoff")
                    elif name == "Y":
                        self.button_signal.emit("land")
                    elif name == "X":
                        print("⚠️ EMERGENCY")
                        self.button_signal.emit("emergency")
                    self.last_button_time = now
                self.prev_buttons[name] = state

        except Exception as e:
            print("Gamepad poll error:", e)
            self._timer.stop()