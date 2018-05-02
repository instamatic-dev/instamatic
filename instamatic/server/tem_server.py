from instamatic import TEMController
import threading
import queue
import socket
import pickle
import logging
import datetime
from instamatic import config

# import sys
# sys.setswitchinterval(0.001)  # seconds

condition = threading.Condition()
box = []

# HOST = 'localhost'
# PORT = 8088

HOST = config.cfg.host
PORT = config.cfg.port
BUFSIZE = 1024


def init_tem(name=None):
    if not name:
        name = config.cfg.microscope

    if name == "jeol":
        from instamatic.TEMController.jeol_microscope import JeolMicroscope
        tem = JeolMicroscope()
    elif name == "fei_simu":
        from instamatic.TEMController.fei_simu_microscope import FEISimuMicroscope
        tem = FEISimuMicroscope()
    elif name == "simulate":
        from instamatic.TEMController.simu_microscope import SimuMicroscope
        tem = SimuMicroscope()
    else:
        raise ValueError("No such microscope: `{}`".format(name))

    return tem


class TemServer(threading.Thread):
    def __init__(self, log=None, q=None):
        super().__init__()

        self.log = log
        self.q = q
    
    def run(self):
        self.tem = init_tem()

        while True:
            now = datetime.datetime.now().strftime("%H:%M:%S.%f")
            
            cmd = self.q.get()
            condition.acquire()

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
            print(f"{now} | {status} {func_name}: {ret}")

            condition.release()

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
    
            condition.acquire()            
            q.put(data)
            condition.wait()
            response = box.pop()
            conn.send(pickle.dumps(response))
            condition.release()


def main():
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    logfile = config.logs_drc / f"instamatic_TEMServer_{date}.log"
    logging.basicConfig(format="%(asctime)s | %(module)s:%(lineno)s | %(levelname)s | %(message)s", 
                        filename=logfile, 
                        level=logging.DEBUG)
    logging.captureWarnings(True)
    log = logging.getLogger(__name__)

    q = queue.Queue(maxsize=100)
    
    tem_reader = TemServer(log=log, q=q)
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