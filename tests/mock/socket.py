from instamatic.camera.gatansocket3 import GatanSocket


class SockMock:
    """Class to mock a socket connection."""

    def __init__(self):
        self.sent = []

    def reset(self):
        self.sent.clear()

    def shutdown(self, how: int) -> None:
        self.reset()

    def close(self) -> None:
        self.reset()

    def connect(self, address) -> None:
        self.reset()

    def disconnect(self) -> None:
        self.reset()

    def sendall(self, data) -> None:
        self.sent.append(data)

    def recv(self, bufsize: int) -> bytes:
        return bytes([0] * bufsize)


class GatanSocketMock(GatanSocket):
    def connect(self):
        self.sock = SockMock()
