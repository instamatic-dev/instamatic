
from instamatic import TEMController
import threading
import queue
import socket
import pickle
import logging
import datetime
from instamatic import config
from instamatic.TEMController import Microscope

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
    def __init__(self, log=None, q=None, name=None):
        super().__init__()

        self.log = log
        self.q = q

        # self.name is a reserved parameter for threads
        self._name = name
    
    def run(self):
        self.tem = Microscope(name=self._name, use_server=False)
        print("Initialized connection to microscope: {}".format(self.tem.name))

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
                    # traceback.print_exc()
                    # self.log.exception(e)
                    ret = e
                    status = 500
    
                box.append((status, ret))
                condition.notify()
                print("{now} | {status} {func_name}: {ret}".format(now=now, status=status, func_name=func_name, ret=ret))

    def evaluate(self, func_name, args, kwargs):
        # print(func_name, args, kwargs)
        f = getattr(self.tem, func_name)
        ret = f(*args, **kwargs)
        return ret


def handle(conn, q):
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
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--microscope", action="store", dest="microscope",
                        help="""Override microscope to use""")

    parser.set_defaults(microscope=None)
    options = parser.parse_args()
    microscope = options.microscope

    date = datetime.datetime.now().strftime("%Y-%m-%d")
    logfile = config.logs_drc / "instamatic_TEMServer_{date}.log".format(date=date)
    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename=str(logfile), 
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    q = queue.Queue(maxsize=100)
    
    tem_reader = TemServer(name=microscope, log=log, q=q)
    tem_reader.start()
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST,PORT))
    s.listen(5)

    log.info("Server listening on {HOST}:{PORT}".format(HOST=HOST, PORT=PORT))
    print("Server listening on {HOST}:{PORT}".format(HOST=HOST, PORT=PORT))

    with s:
        while True:
            conn, addr = s.accept()
            log.info('Connected by %s', addr)
            print('Connected by', addr)
            threading.Thread(target=handle, args=(conn, q)).start()

    
if __name__ == '__main__':
    main()