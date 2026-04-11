import pygame
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class GamepadWorker(QObject):
    """
    High-performance Gamepad handler for Tello.
    Optimized for low-latency response and reliable stopping.
    Coordinates:
    - Sticks: Up/Forward = 1.0, Down/Back = -1.0
    - Tello: Up/Forward = positive (1 to 100), Down/Back = negative (-1 to -100)
    """
    command_signal = pyqtSignal(str)
    axis_signal = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_gamepad)

        # 50Hz polling for responsiveness
        self.interval = 20
        self.deadzone = 0.12
        self.last_rc_was_zero = True

    def start(self):
        pygame.joystick.quit()
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.timer.start(self.interval)
            print(f"Gamepad started: {self.joystick.get_name()}")
        else:
            print("No gamepad detected.")

    def stop(self):
        self.timer.stop()
        if self.joystick:
            self.joystick.quit()
            self.joystick = None
        print("Gamepad stopped.")

    def poll_gamepad(self):
        if not self.joystick:
            return

        # 1. Handle Events First
        pygame.event.pump()
        button_pressed_this_tick = False
        for event in pygame.event.get():
            if event.type == pygame.JOYBUTTONDOWN:
                self.handle_button(event.button)
                button_pressed_this_tick = True

        # 2. Get Stick Data
        raw_lx = self.joystick.get_axis(0)
        raw_ly = self.joystick.get_axis(1)
        raw_rx = self.joystick.get_axis(2)
        raw_ry = self.joystick.get_axis(3)

        # Natural mapping: Up is positive, Down is negative
        lx = raw_lx
        ly = -raw_ly
        rx = raw_rx
        ry = -raw_ry

        # Update Visualizer with inverted values so sticks display correctly
        self.axis_signal.emit([lx, -ly, rx, -ry])

        # 3. Channel Management
        # If a button was pressed (Emergency, Land, etc.), we skip the RC command
        # for this tick to ensure the drone processes the discrete command.
        if button_pressed_this_tick:
            return

        def scale_and_deadzone(val):
            if abs(val) < self.deadzone:
                return 0
            sign = 1 if val > 0 else -1
            scaled = (abs(val) - self.deadzone) / (1.0 - self.deadzone)
            # travel limits the power of the rc command
            travel = 50
            return int(sign * scaled * travel)

        a = scale_and_deadzone(rx)  # roll
        b = scale_and_deadzone(ry)  # pitch
        c = scale_and_deadzone(ly)  # throttle
        d = scale_and_deadzone(lx)  # yaw

        # 4. Movement / Stop Logic
        if a == 0 and b == 0 and c == 0 and d == 0:
            if not self.last_rc_was_zero:
                # Immediate stop
                self.command_signal.emit("rc 0 0 0 0")
                self.last_rc_was_zero = True
        else:
            # Send RC movement
            self.command_signal.emit(f"rc {a} {b} {c} {d}")
            self.last_rc_was_zero = False

    def handle_button(self, button_idx):
        # Optimized button mapping: only crucial commands
        mapping = {
            0: "takeoff",
            1: "land",
            2: "emergency"
        }
        if button_idx in mapping:
            cmd = mapping[button_idx]
            # Prioritize emergency by printing and sending immediately
            if cmd == "emergency":
                print("!!! EMERGENCY BUTTON PRESSED !!!")
            self.command_signal.emit(cmd)
