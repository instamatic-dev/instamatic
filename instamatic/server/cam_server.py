import threading
import queue
import socket
import pickle
import logging
import datetime
from instamatic import config
from instamatic.camera import Camera

from instamatic.utils import high_precision_timers
high_precision_timers.enable()

# import sys
# sys.setswitchinterval(0.001)  # seconds

condition = threading.Condition()
box = []

# HOST = 'localhost'
# PORT = 8088

HOST = config.cfg.cam_server_host
PORT = config.cfg.cam_server_port
BUFSIZE = 4096


class CamServer(threading.Thread):
    """Camera communcation server. Takes a logger object `log`, command queue `q`, and
    name of the camera `name` that is used to initialize the connection to the camera.
    Start the server using `CamServer.run` which will wait for items to appear on `q` and
    execute them on the specified camera instance.
    """
    def __init__(self, log=None, q=None, name=None):
        super().__init__()

        self.log = log
        self.q = q
    
        # self.name is a reserved parameter for threads
        self._name = name
    
    def run(self):
        """Start server thread"""
        self.cam = Camera(name=self._name, use_server=False)
        self.cam.get_attrs = self.get_attrs

        print(f"Initialized connection to camera: {self.cam.name}")

        while True:
            now = datetime.datetime.now().strftime("%H:%M:%S.%f")
            
            cmd = self.q.get()

            with condition:
                attr_name = cmd["attr_name"]
                args = cmd.get("args", ())
                kwargs = cmd.get("kwargs", {})

                try:
                    ret = self.evaluate(attr_name, args, kwargs)
                    status = 200
                except Exception as e:
                    # traceback.print_exc()
                    # self.log.exception(e)
                    ret = e
                    status = 500

                box.append((status, ret))
                condition.notify()
                print(f"{now} | {status} {attr_name}: {ret}")

    def evaluate(self, attr_name: str, args: list, kwargs: dict):
        """Evaluate the function `attr_name` on `self.cam` with *args and **kwargs."""
        # print(attr_name, args, kwargs)
        f = getattr(self.cam, attr_name)
        if callable(f):
            ret = f(*args, **kwargs)
        else:
            ret = f
        return ret

    def get_attrs(self):
        """Get attributes from cam object to update __dict__ on client side"""
        attrs = {}
        for item in dir(self.cam):
            if item.startswith("_"):
                continue
            obj = getattr(self.cam, item)
            if not callable(obj):
                attrs[item] = type(obj)
        
        return attrs

def handle(conn, q):
    """Handle incoming connection, put command on the Queue `q`,
    which is then handled by TEMServer."""
    with conn:
        while True:
            data = conn.recv(BUFSIZE)
            if not data:
                break

            data = pickle.loads(data)

            if data == "exit":
                break

            if data == "kill":
                # killEvent.set() ?
                # s.shutdown() ?
                break
    
            with condition:
                q.put(data)
                condition.wait()
                response = box.pop()
                conn.sendall(pickle.dumps(response))
                # conn.send(pickle.dumps(response))


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--camera", action="store", dest="camera",
                        help="""Override camera to use""")

    parser.set_defaults(camera=None)
    options = parser.parse_args()
    camera = options.camera

    date = datetime.datetime.now().strftime("%Y-%m-%d")
    logfile = config.logs_drc / f"instamatic_CAMServer_{date}.log"
    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename=logfile, 
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    q = queue.Queue(maxsize=100)
    
    cam_reader = CamServer(name=camera, log=log, q=q)
    cam_reader.start()
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST,PORT))
    s.listen(5)

    log.info(f"Server listening on {HOST}:{PORT}")
    print(f"Server listening on {HOST}:{PORT}")

    with s:
        while True:
            conn, addr = s.accept()
            log.info('Connected by %s', addr)
            print('Connected by', addr)
            threading.Thread(target=handle, args=(conn, q)).start()

    
if __name__ == '__main__':
    main()
