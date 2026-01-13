from __future__ import annotations

import datetime
import inspect
import logging
import queue
import socket
import threading
import traceback
import uuid

import numpy as np

from instamatic import config
from instamatic.camera import get_camera
from instamatic.server.serializer import dumper, loader
from instamatic.utils import high_precision_timers

high_precision_timers.enable()

if config.settings.cam_use_shared_memory:
    from multiprocessing import shared_memory

_generators = {}
condition = threading.Condition()
box = []

HOST = config.settings.cam_server_host
PORT = config.settings.cam_server_port
BUFSIZE = 4096


is_local_connection = HOST in ('127.0.0.1', 'localhost')


class CamServer(threading.Thread):
    """Camera communcation server.

    Takes a logger object `log`, command queue `q`, and name of the
    camera `name` that is used to initialize the connection to the
    camera. Start the server using `CamServer.run` which will wait for
    items to appear on `q` and execute them on the specified camera
    instance.
    """

    def __init__(self, log=None, q=None, name=None):
        super().__init__()

        self.log = log
        self.q = q

        # self.name is a reserved parameter for threads
        self._name = name

        self._bufsize = BUFSIZE

        self.verbose = False

        self.buffers = {}

        self.use_shared_memory = config.settings.cam_use_shared_memory
        print('Use shared memory:', self.use_shared_memory)

    def setup_shared_buffer(self, arr):
        """Set up shared memory buffer.

        Make a buffer for each binsize, and store the buffers to a dict.
        """
        self.shmem = shared_memory.SharedMemory(create=True, size=arr.nbytes)
        buffer = np.ndarray(arr.shape, dtype=arr.dtype, buffer=self.shmem.buf)
        self.buffers[arr.shape] = buffer
        if self.verbose:
            print(f'Created new buffer: `{self.shmem.name}` | {arr.shape} ({arr.dtype})')

    def copy_data_to_shared_buffer(self, arr):
        """Copy numpy image array to shared memory."""
        if arr.shape not in self.buffers:
            self.setup_shared_buffer(arr)

        buffer = self.buffers[arr.shape]
        buffer[:] = arr[:]  # copy data to buffer

    def run(self):
        """Start server thread."""
        self.cam = get_camera(name=self._name, use_server=False)
        self.cam.get_attrs = self.get_attrs

        print(f'Initialized camera: {self.cam.interface}')

        while True:
            now = datetime.datetime.now().strftime('%H:%M:%S.%f')

            cmd = self.q.get()

            with condition:
                attr_name = cmd['attr_name']
                args = cmd.get('args', ())
                kwargs = cmd.get('kwargs', {})

                try:
                    ret = self.evaluate(attr_name, args, kwargs)
                    status = 200
                    if inspect.isgenerator(ret):
                        gen_id = uuid.uuid4().hex
                        _generators[gen_id] = ret
                        ret = {'__generator__': gen_id}
                except Exception as e:
                    traceback.print_exc()
                    if self.log:
                        self.log.exception(e)
                    ret = (e.__class__.__name__, e.args)
                    status = 500
                else:
                    if self.use_shared_memory:
                        if attr_name == 'get_image':
                            self.copy_data_to_shared_buffer(ret)
                            ret = {
                                'shape': ret.shape,
                                'dtype': str(ret.dtype),
                                'name': self.shmem.name,
                            }

                box.append((status, ret))
                condition.notify()
                if self.verbose:
                    print(f'{now} | {status} {attr_name}: {ret}')

    def evaluate(self, attr_name: str, args: list, kwargs: dict):
        """Evaluate the function or attribute `attr_name` on `self.cam`, if
        `attr_name` refers to a function, call it with *args and **kwargs."""

        if attr_name == '__gen_next__':
            gen = _generators[kwargs['id']]
            try:
                return next(gen)
            except StopIteration:
                del _generators[kwargs['id']]
                return

        if attr_name == '__gen_close__':
            _generators.pop(kwargs['id'], None)
            return

        f = getattr(self.cam, attr_name)
        return f(*args, **kwargs) if callable(f) else f

    def get_attrs(self):
        """Get attributes from cam object to update __dict__ on client side."""
        attrs = {}
        for item in dir(self.cam):
            if item.startswith('_'):
                continue
            obj = getattr(self.cam, item)
            if not callable(obj):
                attrs[item] = type(obj)

        return attrs


def handle(conn, q):
    """Handle incoming connection, put command on the Queue `q`, which is then
    handled by TEMServer."""
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
                conn.sendall(dumper(response))


def main():
    import argparse

    description = f"""
Connects to the camera and starts a server for camera communication. Opens a socket on port {HOST}:{PORT}.

This program initializes a connection to the camera as defined in the config. This separates the communication from the main process and allows for remote connections from different PCs. The connection goes over a TCP socket.

The host and port are defined in `config/settings.yaml`.

The data sent over the socket is a serialized dict with the following elements:

- `attr_name`: Name of the function to call or attribute to return (str)
- `args`: (Optional) List of arguments for the function (list)
- `kwargs`: (Optiona) Dictionary of keyword arguments for the function (dict)

The response is returned as a serialized object.
"""

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '-c', '--camera', action='store', dest='camera', help="""Override camera to use."""
    )

    parser.set_defaults(camera=None)
    options = parser.parse_args()
    camera = options.camera

    date = datetime.datetime.now().strftime('%Y-%m-%d')
    logfile = config.locations['logs'] / f'instamatic_CAMServer_{date}.log'
    logging.basicConfig(
        format='%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s',
        filename=logfile,
        level=logging.DEBUG,
    )
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    q = queue.Queue(maxsize=100)

    cam_reader = CamServer(name=camera, log=log, q=q)
    cam_reader.start()

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
