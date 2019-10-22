from instamatic import TEMController
import threading
import queue
import socket
import pickle
import logging
import datetime
from instamatic import config
from instamatic.TEMController import Microscope
import traceback

# import sys
# sys.setswitchinterval(0.001)  # seconds

condition = threading.Condition()
box = []

# HOST = 'localhost'
# PORT = 8088

HOST = config.cfg.tem_server_host
PORT = config.cfg.tem_server_port
BUFSIZE = 1024


class TemServer(threading.Thread):
    """TEM communcation server. Takes a logger object `log`, command queue `q`, and
    name of the microscope `name` that is used to initialize the connection to the microscope.
    Start the server using `TemServer.run` which will wait for items to appear on `q` and
    execute them on the specified microscope instance.
    """
    def __init__(self, log=None, q=None, name=None):
        super().__init__()

        self.log = log
        self.q = q

        # self.name is a reserved parameter for threads
        self._name = name
    
    def run(self):
        """Start the server thread"""
        self.tem = Microscope(name=self._name, use_server=False)
        print(f"Initialized connection to microscope: {self.tem.name}")

        while True:
            now = datetime.datetime.now().strftime("%H:%M:%S.%f")
            
            cmd = self.q.get()

            with condition:
                func_name = cmd["func_name"]
                args = cmd.get("args", ())
                kwargs = cmd.get("kwargs", {})
    
                try:
                    ret = self.evaluate(func_name, args, kwargs)
                    status = 200
                except Exception as e:
                    traceback.print_exc()
                    if self.log:
                        self.log.exception(e)
                    ret = e
                    status = 500
    
                box.append((status, ret))
                condition.notify()
                print(f"{now} | {status} {func_name}: {ret}")

    def evaluate(self, func_name: str, args: list, kwargs: dict):
        """Evaluate the function `func_name` on `self.tem` with *args and **kwargs."""
        # print(func_name, args, kwargs)
        f = getattr(self.tem, func_name)
        ret = f(*args, **kwargs)
        return ret


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
                conn.send(pickle.dumps(response))


def main():
    if config.cfg.tem_require_admin:
        from instamatic import admin
        if not admin.is_admin():
            admin.run_as_admin(__file__)
            exit()

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--microscope", action="store", dest="microscope",
                        help="""Override microscope to use""")

    parser.set_defaults(microscope=None)
    options = parser.parse_args()
    microscope = options.microscope

    date = datetime.datetime.now().strftime("%Y-%m-%d")
    logfile = config.logs_drc / f"instamatic_TEMServer_{date}.log"
    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename=logfile, 
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    q = queue.Queue(maxsize=100)
    
    tem_reader = TemServer(name=microscope, log=log, q=q)
    tem_reader.start()
    
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