import socket
import time
from PyQt6.QtCore import QThread, pyqtSignal


class TelloWorker(QThread):
    """
    Handles sending commands to the Tello on Port 8889.
    Runs in a background thread to prevent UI freezing during network waits.
    """
    response_received = pyqtSignal(str)

    def __init__(self, demo_mode: bool = False):
        super().__init__()
        self.demo_mode = demo_mode
        self.tello_address = ('192.168.10.1', 8889)
        self.sock = None
        if not self.demo_mode:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # Bind to local port 9000 to receive responses
                self.sock.bind(('', 9000))
            except Exception as e:
                print(f"Command socket bind error: {e}")

            self.sock.settimeout(2.0)
        self.current_command = None

    def run(self):
        if self.demo_mode:
            if self.current_command:
                self.response_received.emit(f"demo ok: {self.current_command}")
                self.current_command = None
            return

        if self.current_command:
            try:
                self.sock.sendto(self.current_command.encode('utf-8'), self.tello_address)
                response, _ = self.sock.recvfrom(1024)
                self.response_received.emit(response.decode('utf-8').strip())
            except Exception as e:
                self.response_received.emit(f"Error: {str(e)}")
            finally:
                self.current_command = None

    def send(self, cmd):
        print("SEND:", cmd)  # 👈 THIS is where it goes

        if self.demo_mode:
            self.current_command = cmd
            self.response_received.emit(f"demo ok: {cmd}")
            return

        try:
            self.sock.sendto(cmd.encode("utf-8"), self.tello_address)
        except Exception as e:
            print("Send error:", e)


class TelloStatusThread(QThread):
    """
    Listens for state packets from the Tello on Port 8890.
    Parses strings like 'bat:90;h:10;...' into a dictionary.
    """
    status_updated = pyqtSignal(dict)

    def __init__(self, demo_mode: bool = False):
        super().__init__()
        self.demo_mode = demo_mode
        self.sock = None
        self.running = True
        if not self.demo_mode:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                self.sock.bind(('', 8890))
                self.sock.settimeout(0.5)
            except Exception as e:
                print(f"Status socket bind error: {e}")

    def run(self):
        if self.demo_mode:
            self._run_demo()
            return

        while self.running:
            try:
                data, _ = self.sock.recvfrom(1024)
                status_str = data.decode('utf-8')
                stats = {}
                # Tello state format is key:value;key:value;
                for item in status_str.strip().split(';'):
                    if ':' in item:
                        k, v = item.split(':')
                        stats[k] = v
                if stats:
                    self.status_updated.emit(stats)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Status thread error: {e}")
                break

    def _run_demo(self):
        battery = 100
        direction = -1
        speed_values = ["0", "10", "20", "30", "20", "10"]
        index = 0

        while self.running:
            stats = {
                "bat": str(battery),
                "templ": str(58 + (index % 4)),
                "speed": speed_values[index % len(speed_values)],
            }
            self.status_updated.emit(stats)

            if battery <= 72:
                direction = 1
            elif battery >= 100:
                direction = -1

            battery += direction
            index += 1
            time.sleep(0.5)

    def stop(self):
        """Safely stops the status listener and closes the socket."""
        self.running = False
        if self.sock is not None:
            self.sock.close()
