import datetime
import logging
import pickle
import queue
import socket
import threading
import traceback

from .serializer import dumper
from .serializer import loader
from instamatic import config
from instamatic.goniotool import GonioToolWrapper

barrier = threading.Barrier(2, timeout=60)

condition = threading.Condition()
box = []


HOST = config.settings.goniotool_server_host
PORT = config.settings.goniotool_server_port
BUFSIZE = 1024


class GonioToolServer(threading.Thread):
    """GonioTool communcation server.

    Takes a logger object `log`, command queue `q`, and name of the
    microscope `name` that is used to initialize the connection to the
    microscope. Start the server using `GonioToolServer.run` which will
    wait for items to appear on `q` and execute them on the specified
    microscope instance.
    """

    def __init__(self, log=None, q=None, name=None):
        super().__init__()

        self.log = log
        self.q = q

        # self.name is a reserved parameter for threads
        self._name = name

        self.verbose = False

    def run(self):
        """Start the server thread."""
        self.goniotool = GonioToolWrapper(barrier=barrier)
        print(f'Initialized connection to GonioTool')

        while True:
            now = datetime.datetime.now().strftime('%H:%M:%S.%f')

            cmd = self.q.get()

            with condition:
                func_name = cmd['func_name']
                args = cmd.get('args', ())
                kwargs = cmd.get('kwargs', {})

                try:
                    ret = self.evaluate(func_name, args, kwargs)
                    status = 200
                except Exception as e:
                    traceback.print_exc()
                    if self.log:
                        self.log.exception(e)
                    ret = (e.__class__.__name__, e.args)
                    status = 500

                box.append((status, ret))
                condition.notify()
                if self.verbose:
                    print(f'{now} | {status} {func_name}: {ret}')

    def evaluate(self, func_name: str, args: list, kwargs: dict):
        """Evaluate the function `func_name` on `self.goniotool` and call it
        with *args and **kwargs."""
        # print(func_name, args, kwargs)
        f = getattr(self.goniotool, func_name)
        ret = f(*args, **kwargs)
        return ret


def handle(conn, q):
    """Handle incoming connection, put command on the Queue `q`, which is then
    handled by GonioToolServer."""
    with conn:
        while True:
            data = conn.recv(BUFSIZE)
            if not data:
                break

            data = loader(data)

            if data == 'exit':
                break

            if data == 'kill':
                break

            with condition:
                q.put(data)
                condition.wait()
                response = box.pop()
                conn.send(dumper(response))


def main():
    import argparse

    description = f"""
Connects to `Goniotool.exe` and starts a server for network communication. Opens a socket on port {HOST}:{PORT}.

The host and port are defined in `config/settings.yaml`.

The data sent over the socket is a serialized dictionary with the following elements:

- `func_name`: Name of the function to call (str)
- `args`: (Optional) List of arguments for the function (list)
- `kwargs`: (Optiona) Dictionary of keyword arguments for the function (dict)

The response is returned as a pickle object.
"""

    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    options = parser.parse_args()

    date = datetime.datetime.now().strftime('%Y-%m-%d')
    logfile = config.locations['logs'] / f'instamatic_goniotool_{date}.log'
    logging.basicConfig(format='%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s',
                        filename=logfile,
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    q = queue.Queue(maxsize=100)

    goniotool_server = GonioToolServer(log=log, q=q)
    goniotool_server.start()

    barrier.wait()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(5)

    log.info(f'Server listening on {HOST}:{PORT}')
    print(f'Server listening on {HOST}:{PORT}')

    with s:
        while True:
            conn, addr = s.accept()
            log.info('Connected by %s', addr)
            print('Connected by', addr)
            threading.Thread(target=handle, args=(conn, q)).start()


if __name__ == '__main__':
    main()
